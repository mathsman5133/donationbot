from discord.ext import commands, tasks
import discord
import math
from datetime import datetime
from collections import OrderedDict
from .utils import fuzzy
from .utils.formatters import TabularData
import coc


class MockPlayer:
    def __init__(self):
        MockPlayer.name = 'Unknown'
        MockPlayer.clan = 'Unknown'


class GuildConfig:
    __slots__ = ('bot', 'guild_id', 'updates_channel_id', 'updates_header_id', 'updates_toggle',
                 'log_channel_id', 'log_toggle', 'ign', 'don', 'rec', 'tag', 'claimed_by', 'clan',
                 'auto_claim')

    def __init__(self, *, guild_id, bot, record=None):
        self.guild_id = guild_id
        self.bot = bot

        if record:
            self.updates_channel_id = record['updates_channel_id']
            self.updates_header_id = record['updates_message_id']
            self.updates_toggle = record['updates_toggle']
            self.log_channel_id = record['log_channel_id']
            self.log_toggle = record['log_toggle']
            self.ign = record['updates_ign']
            self.don = record['updates_don']
            self.rec = record['updates_rec']
            self.tag = record['updates_tag']
            self.claimed_by = record['updates_claimed_by']
            self.clan = record['updates_clan']  # record['updates_clan']
            self.auto_claim = record['auto_claim']
        else:
            self.updates_channel_id = None
            self.log_channel_id = None
            self.updates_toggle = False
            self.log_toggle = False
            self.auto_claim = False

    @property
    def updates_channel(self):
        guild = self.bot.get_guild(self.guild_id)
        return guild and guild.get_channel(self.updates_channel_id)

    @property
    def log_channel(self):
        guild = self.bot.get_guild(self.guild_id)
        return guild and guild.get_channel(self.log_channel_id)

    async def updates_message_ids(self):
        query = "SELECT * FROM messages WHERE guild_id = $1"
        fetch = await self.bot.pool.fetch(query, self.guild_id)
        return [n['message_id'] for n in fetch]


class Updates(commands.Cog):
    """Commands related to the donationboard, and auto-updating of it."""
    def __init__(self, bot):
        self.bot = bot

        self._new_month = False
        self.clan_updates = []
        self.player_updates = []

        self._message_cache = {}
        self.clean_message_cache.start()

        self._to_be_deleted = set()

        self._join_prompts = {}

        self._guild_config_cache = OrderedDict()
        self.bot.coc.add_events(self.on_clan_member_donation,
                                self.on_clan_member_received,
                                self.on_clan_member_join,
                                self.on_clan_batch_updates)
        self.bot.coc._clan_retry_interval = 60
        self.bot.coc.start_updates('clan')

    def cog_unload(self):
        self.clean_message_cache.cancel()
        self.bot.coc.extra_events.pop('on_clan_member_donation')
        self.bot.coc.extra_events.pop('on_clan_member_received')
        self.bot.coc.extra_events.pop('on_clan_member_join')
        self.bot.coc.extra_events.pop('on_clan_batch_updates')

    @tasks.loop(hours=1.0)
    async def clean_message_cache(self):
        self._message_cache.clear()

    async def get_guild_config(self, guild_id):
        cache = self._guild_config_cache.get(guild_id)
        if cache:
            return cache

        query = "SELECT * FROM guilds WHERE guild_id = $1"
        fetch = await self.bot.pool.fetchrow(query, guild_id)

        config = GuildConfig(guild_id=guild_id, bot=self.bot, record=fetch)
        self._guild_config_cache[guild_id] = config
        return config

    async def get_message(self, channel, message_id):
        try:
            return self._message_cache[message_id]
        except KeyError:
            try:
                o = discord.Object(id=message_id + 1)
                pred = lambda m: m.id == message_id
                # don't wanna use get_message due to poor rate limit (1/1s) vs (50/1s)
                msg = await channel.history(limit=1, before=o).next()

                if msg.id != message_id:
                    return None

                self._message_cache[message_id] = msg
                return msg
            except Exception:
                return None

    async def reset_message_id(self, guild_id, message_id=None, delete=False):
        guild_config = await self.get_guild_config(guild_id)
        if message_id:
            query = "DELETE FROM messages WHERE message_id = $1"
            await self.bot.pool.execute(query, message_id)
            if delete:
                msg = await self.get_message(guild_config.updates_channel_id, message_id)
                self._to_be_deleted.add(msg.id)
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass

                return

        new_msg = await guild_config.updates_channel.send('Placeholder')
        query = "INSERT INTO messages (guild_id, message_id) VALUES ($1, $2)"
        await self.bot.pool.execute(query, new_msg.guild.id, new_msg.id)
        return new_msg

    async def update_clan_tags(self):
        query = "SELECT DISTINCT clan_tag FROM clans"
        fetch = await self.bot.pool.fetch(query)
        self.bot.coc._clan_updates = [n[0] for n in fetch]

    async def match_player(self, player, guild: discord.Guild, prompt=False, ctx=None,
                           score_cutoff=20, claim=True):
        matches = fuzzy.extract_matches(player.name, [n.name for n in guild.members],
                                        score_cutoff=score_cutoff, scorer=fuzzy.partial_ratio,
                                        limit=9)
        if len(matches) == 0:
            return None
        if len(matches) == 1:
            user = guild.get_member_named(matches[0][0])
            if prompt:
                m = await ctx.prompt(f'[auto-claim]: {player.name} ({player.tag}) '
                                     f'to be claimed to {str(user)} ({user.id}). '
                                     f'If already claimed, this will do nothing.')
                if m is True and claim is True:
                    query = "UPDATE players SET user_id = $1 " \
                            "WHERE player_tag = $2 AND user_id = NULL"
                    await self.bot.pool.execute(query, user.id, player.tag)
                else:
                    return False
            return user
        return [guild.get_member_named(n[0]) for n in matches]

    async def match_member(self, member, clan, claim):
        matches = fuzzy.extract_matches(member.name, [n.name for n in clan.members],
                                        score_cutoff=60)
        if len(matches) == 0:
            return None
        for i, n in enumerate(matches):
            query = "SELECT user_id FROM players WHERE player_tag = $1"
            m = clan.get_member(name=n[0])
            fetch = await self.bot.pool.fetchrow(query, m.tag)
            if fetch is None:
                continue
            del matches[i]

        if len(matches) == 1 and claim is True:
            player = clan.get_member(name=matches[0][0])
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND user_id = NULL"
            await self.bot.pool.execute(query, member.id, player.tag)
            return player
        elif len(matches) == 1:
            return True

        return [clan.get_member(name=n) for n in matches]

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return

        guild_config = await self.get_guild_config(channel.guild.id)
        if guild_config.updates_channel is None or guild_config.updates_channel.id != channel.id:
            if guild_config.log_channel is None or guild_config.log_channel.id != channel.id:
                return
            # the log channel got deleted, remove it from the database.
            query = "UPDATE guilds SET log_channel_id = NULL, " \
                    "log_toggle = False WHERE guild_id = $1"
            await self.bot.pool.execute(query, channel.guild.id)

        query = "DELETE FROM messages WHERE guild_id = $1;"
        await self.bot.pool.execute(query, channel.guild.id)
        query = "UPDATE guilds SET updates_channel_id = NULL, " \
                "updates_message_id = NULL, updates_toggle = False WHERE" \
                " guild_id = $1"
        await self.bot.pool.execute(query, channel.guild.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)
        if guild_config.updates_channel is None or \
                guild_config.updates_channel.id != payload.channel_id:
            return
        if payload.message_id in self._to_be_deleted:
            self._to_be_deleted.discard(payload.message_id)
            return

        await self.reset_message_id(payload.guild_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)
        if guild_config.updates_channel is None or \
                guild_config.updates_channel.id != payload.channel_id:
            return

        for n in payload.message_ids:
            if n in self._to_be_deleted:
                self._to_be_deleted.discard(n)
                continue
            await self.reset_message_id(payload.guild_id, n)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        info = self._join_prompts.get(payload.message_id)
        if not info:
            return

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND user_id = NULL"
        await self.bot.pool.execute(query, info[1].id, info[0].tag)

        try:
            await self.bot.http.delete_message(payload.channel_id, payload.message_id,
                                               reason=f'Member {str(info[0])} '
                                                      f'claimed by '
                                                      f'{str(self.bot.get_user(payload.user_id))}.')
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_config = await self.get_guild_config(member.guild.id)
        if not (guild_config.auto_claim or guild_config.log_toggle):
            return

        for clan in await self.bot.get_clans(member.guild.id):
            results = await self.match_member(member, clan, claim=False)
            if not results:
                await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined '
                                                      'the guild, but no corresponding '
                                                      'COC players were found.',
                                        colour=discord.Colour.gold())
                return  # no members found in clan with that name
            if isinstance(results, coc.BasicPlayer):
                await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined '
                                                      'the guild, and was auto-claimed to '
                                                      f'{str(results)} ({results.tag}).',
                                        colour=discord.Colour.green())
                return  # we claimed a member
            if results is True:
                return

            table = TabularData()
            table.set_columns(['IGN', 'Tag'])
            table.add_rows([n.name, n.tag] for n in results)
            await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined the guild.\n'
                                                  f'Corresponding clan members found, none claimed:'
                                                  f'\n```\n{table.render()}\n```',
                                    colour=discord.Colour.gold())

    async def on_clan_member_join(self, member, clan):
        query = "INSERT INTO players (player_tag, donations, received) VALUES ($1, $2, $3) " \
                "ON CONFLICT (player_tag) DO NOTHING"
        await self.bot.pool.execute(query, member.tag, member.donations, member.received)

        guilds = await self.bot.get_guilds(clan.tag)
        for n in guilds:
            guild_config = await self.get_guild_config(n.id)
            if not guild_config.log_toggle:
                continue

            results = await self.match_player(member, n, claim=False)
            if not results:
                await self.bot.log_info(clan, f'{member.name} ({member.tag}) joined '
                                              f'{str(clan)} ({clan.tag}), but no corresponding '
                                              f'discord names were found.',
                                        colour=discord.Colour.red())
                return
                # no members found in guild with that player name
            if isinstance(results, discord.Member):
                msg_ids = await self.bot.log_info(clan, f'{member.name} ({member.tag}) '
                                                        f'joined {str(clan)} ({clan.tag}) '
                                                        f'and I found a singular '
                                                        f'matching discord account: '
                                                        f'{str(results)} (ID {results.id}). '
                                                        f'Do you wish to claim them?',
                                                  colour=discord.Colour.green(),
                                                  prompt=True)
                for x in msg_ids:
                    self._join_prompts[x] = [member, results]
                return

            table = TabularData()
            table.set_columns(['user#disrim', 'UserID'])
            table.add_rows([str(n), n.id] for n in results)
            await self.bot.log_info(clan, f'{member.name} ({member.tag}) '
                                          f'joined {str(clan)} ({clan.tag}).\n'
                                          f'Corresponding members found, none claimed:\n'
                                          f'```\n{table.render()}\n```',
                                    colour=discord.Colour.gold())

    async def on_clan_member_donation(self, old_donations, new_donations, player, clan):
        if old_donations > new_donations:
            await self.new_month()
            self._new_month = True
        else:
            self._new_month = False

        if self._new_month is True:
            return False

        query = "UPDATE players SET donations = donations + $1 WHERE player_tag = $2"
        await self.bot.pool.execute(query, new_donations - old_donations, player.tag)
        # await self.edit_updates_for_clan(clan)
        # technically received gets dispatched after donations so hopefully this query will be made
        # before received triggers. When a clan is just claimed and both these trigger before other
        # has finished, it ends up sending double rounds of messages. hopefully this will fix that,
        # and if donations/received havent updated this time round they will be added next time.
        # nobody will know any different.

    async def on_clan_member_received(self, old_received, new_received, player, clan):
        if old_received > new_received:
            self._new_month = True
        else:
            self._new_month = False

        if self._new_month is True:
            return

        query = "UPDATE players SET received = received + $1 WHERE player_tag = $2"
        await self.bot.pool.execute(query, new_received - old_received, player.tag)
        await self.edit_updates_for_clan(clan)

    async def on_clan_batch_updates(self, all_updates):
        received_events = [n for n in all_updates if n[0] == 'on_clan_member_received']
        donation_events = [n for n in all_updates if n[0] == 'on_clan_member_donation']

        time = datetime.utcnow()
        query = "INSERT INTO events (player_tag, clan_tag, donations, received, time) " \
                "VALUES ($1, $2, $3, $4, $5)"
        for n in received_events:
            await self.bot.pool.execute(query, n[3].tag, n[4].tag, 0, n[2] - n[1], time)
        for n in donation_events:
            await self.bot.pool.execute(query, n[3].tag, n[4].tag, n[2] - n[1], 0, time)

        query = "SELECT DISTINCT clan_tag FROM events WHERE time = $1"
        fetch = await self.bot.pool.fetch(query, time)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()

        query = "SELECT player_tag, donations, received FROM events " \
                "WHERE clan_tag = $1 AND time = $2"
        for clan in clans:
            print(clan)
            fetch = await self.bot.pool.fetch(query, clan.tag, time)
            table = TabularData()
            table.set_columns(['IGN', 'Don', "Rec'd"])
            for n in fetch:
                player = clan.get_member(tag=n[0])
                table.add_row([player.name, n[1], n[2]])

            fmt = f'Recent Events for {clan.name} ({clan.tag})\n```\n{table.render()}\n```'
            print(fmt)
            await self.bot.log_info(clan, fmt)

        pass

    async def get_updates_messages(self, guild_id, number_of_msg=None):
        guild_config = await self.get_guild_config(guild_id)
        msg_ids = await guild_config.updates_message_ids()

        messages = [await self.get_message(guild_config.updates_channel, n) for n in msg_ids]
        messages = [n for n in messages if n]

        if not number_of_msg or len(messages) == number_of_msg:
            return messages
        elif len(messages) > number_of_msg:
            for n in messages[number_of_msg:]:
                await self.reset_message_id(guild_id, message_id=n.id, delete=True)
            return messages[:number_of_msg]
        elif len(messages) < number_of_msg:
            for n in range(number_of_msg - len(messages)):
                messages.append(await self.reset_message_id(guild_id))
            return messages

    async def new_month(self):
        msg = await self.bot.get_channel(594286547449282587).send('Is it a new month?')
        for n in ['\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}']:
            await msg.add_reaction(n)

        def check(r, u):
            if not u.id == self.bot.owner_id:
                return False
            if not r.message.id == msg.id:
                return False
            return True
        r, u = await self.bot.wait_for('reaction_add', check=check)
        if str(r) == '\N{WHITE HEAVY CHECK MARK}':
            query = "UPDATE players SET donations = 0, received = 0"
            await self.bot.db.execute(query)

    async def edit_updates_for_clan(self, clan):
        guilds = await self.bot.get_guilds(clan.tag)
        if not guilds:
            return

        query = f"SELECT DISTINCT clan_tag FROM clans " \
                f"WHERE guild_id IN ({', '.join(str(n.id) for n in guilds)})"
        fetch = await self.bot.pool.fetch(query)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()

        players = []
        for n in clans:
            players.extend(p for p in n.itermembers)

        query = "SELECT player_tag, donations, received, user_id FROM players WHERE player_tag = $1"

        player_info = []
        for n in players:
            fetch = await self.bot.pool.fetchrow(query, n.tag)
            if fetch:
                player_info.append([p for p in fetch])

        player_info.sort(key=lambda m: m[1], reverse=True)
        player_info = player_info[:100]
        message_count = math.ceil(len(player_info) / 20)

        players = {n.tag: n for n in players if n.tag in set(n[0] for n in player_info)}

        for guild in guilds:
            guild_config = await self.get_guild_config(guild.id)
            if not guild_config.updates_toggle:
                continue

            messages = await self.get_updates_messages(guild.id, number_of_msg=message_count)
            if not messages:
                continue

            for i, v in enumerate(messages):
                headers = {'IGN': guild_config.ign,
                           'Don': guild_config.don,
                           "Rec'd": guild_config.rec,
                           'Player Tag': guild_config.tag,
                           'Claimed By': guild_config.claimed_by,
                           'Clan': guild_config.clan
                           }
                player_data = player_info[i*20:(i+1)*20]

                table = TabularData()
                table.set_columns([n for n in headers if headers[n] is True])

                for n in player_data:
                    info = []
                    if guild_config.ign:
                        info.append(players.get(n[0], MockPlayer()).name)
                    if guild_config.don:
                        info.append(n[1])
                    if guild_config.rec:
                        info.append(n[2])
                    if guild_config.tag:
                        info.append(n[0])
                    if guild_config.claimed_by:
                        user = guild.get_member(n[3])
                        info.append(str(user) or 'None')
                    if guild_config.clan:
                        info.append(str(players.get(n[4], MockPlayer()).clan))

                    table.add_row(info)
                fmt = f'```\n{table.render()}\n```'

                if len(table._columns) > 3:
                    await v.edit(content=fmt, embed=None)
                    continue

                e = discord.Embed(colour=self.bot.colour,
                                  description=fmt)
                await v.edit(embed=e, content=None)

            header = await self.get_message(guild_config.updates_channel,
                                            guild_config.updates_header_id)
            embed = discord.Embed(colour=self.bot.colour, timestamp=datetime.utcnow())
            embed.title = f"Tracking Updates For {', '.join(n.name for n in clans)}"
            embed.set_footer(text='Last Updated')
            await header.edit(embed=embed, content=None)


def setup(bot):
    bot.add_cog(Updates(bot))
