from discord.ext import commands, tasks
import discord
import math
from .updates import TabularData
from datetime import datetime
from collections import OrderedDict
from .utils import fuzzy

class GuildConfig:
    __slots__ = ('bot', 'guild_id', 'updates_channel_id', 'updates_header_id', 'updates_toggle',
                 'log_channel_id', 'log_toggle', 'ign', 'don', 'rec', 'tag', 'claimed_by', 'clan')

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
            self.clan = False  # record['updates_clan']
        else:
            self.updates_channel_id = None
            self.log_channel_id = None
            self.updates_toggle = False
            self.log_toggle = False

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
    def __init__(self, bot):
        self.bot = bot

        self._new_month = False
        self.clan_updates = []
        self.player_updates = []

        self._message_cache = {}
        self.clean_message_cache.start()

        self._guild_config_cache = OrderedDict()
        self.bot.coc.add_events(self.on_clan_member_donation,
                                self.on_clan_member_received)
        self.bot.coc._clan_retry_interval = 60
        self.bot.coc.start_updates('clan')

    def cog_unload(self):
        self.clean_message_cache.cancel()
        self.bot.coc.extra_events.pop('on_clan_member_donation')
        self.bot.coc.extra_events.pop('on_clan_member_received')

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
                await msg.delete()
                return

        new_msg = await guild_config.updates_channel.send('Placeholder')
        query = "INSERT INTO messages (guild_id, message_id) VALUES ($1, $2)"
        await self.bot.pool.execute(query, new_msg.guild.id, new_msg.id)
        return new_msg

    async def update_clan_tags(self):
        query = "SELECT DISTINCT clan_tag FROM clans"
        fetch = await self.bot.pool.fetch(query)
        self.bot.coc._clan_updates = [n[0] for n in fetch]

    async def match_player(self, player, guild: discord.Guild, prompt=False, ctx=None, score_cutoff=80):
        matches = fuzzy.extract_matches(player.name, [n.name for n in guild.members], score_cutoff=20,
                                        scorer=fuzzy.partial_ratio, limit=9)
        if len(matches) == 0:
            return None
        if len(matches) == 1:
            user = guild.get_member_named(matches[0][0])
            if prompt:
                m = await ctx.prompt(f'[auto-claim]: {player.name} ({player.tag}) '
                                     f'to be claimed to {str(user)} ({user.id}).')
                if m is True:
                    query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
                    await self.bot.pool.execute(query, user.id, player.tag)
                else:
                    return False
            return user
        return [guild.get_member_named(n[0]) for n in matches]

    async def match_member(self, member, clan):
        matches = fuzzy.extract_matches(member.name, [n.name for n in clan.members], score_cutoff=60)
        if len(matches) == 0:
            return None
        for i, n in enumerate(matches):
            query = "SELECT user_id FROM players WHERE player_tag = $1"
            fetch = await self.bot.pool.fetchrow(query, n.tag)
            if fetch is None:
                continue
            del matches[i]

        if len(matches) == 1:
            player = clan.get_member(name=matches[0][0])
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND user_id = NULL"
            await self.bot.pool.execute(query, member.id, player.tag)
            return [player]

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
            query = "UPDATE guilds SET log_channel_id = NULL, log_toggle = False WHERE guild_id = $1"
            await self.bot.pool.execute(query, channel.guild.id)

        query = "DELETE FROM messages WHERE guild_id = $1;"
        await self.bot.pool.execute(query, channel.guild.id)
        query = "UPDATE guilds SET updates_channel_id = NULL, updates_message_id = NULL, updates_toggle = False WHERE" \
                " guild_id = $1"
        await self.bot.pool.execute(query, channel.guild.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)
        if guild_config.updates_channel is None or guild_config.updates_channel.id != payload.channel_id:
            return

        await self.reset_message_id(payload.guild_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)
        if guild_config.updates_channel is None or guild_config.updates_channel.id != payload.channel_id:
            return

        for n in payload.message_ids:
            await self.reset_message_id(payload.guild_id, n)

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
        await self.edit_updates_for_clan(clan)

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

    async def get_updates_messages(self, guild_id, number_of_msg=None):
        guild_config = await self.get_guild_config(guild_id)
        msg_ids = await guild_config.updates_message_ids()

        messages = [await self.get_message(guild_config.updates_channel, n) for n in msg_ids]
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
        query = "UPDATE players SET donations = 0, received = 0"
        await self.bot.db.execute(query)

    async def edit_updates_for_clan(self, clan):
        guilds = await self.bot.get_guilds(clan.tag)

        query = f"SELECT DISTINCT clan_tag FROM clans WHERE guild_id IN ({', '.join(str(n.id) for n in guilds)})"
        fetch = await self.bot.pool.fetch(query)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()

        players = []
        for n in clans:
            players.extend(p for p in n._members)

        query = "SELECT player_tag, donations, received, user_id FROM players WHERE player_tag = $1"

        player_info = []
        for n in players:
            fetch = await self.bot.pool.fetchrow(query, n.tag)
            if fetch:
                player_info.append([p for p in fetch])

        player_info.sort(key=lambda m: m[1], reverse=True)
        message_count = math.ceil(len(player_info) / 20)

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
                           'Claimed By': guild_config.claimed_by
                           }
                player_data = player_info[i*20:(i+1)*20]

                table = TabularData()
                table.set_columns([n for n in headers if headers[n] is True])

                for n in player_data:
                    info = []
                    if guild_config.ign:
                        player = discord.utils.find(lambda m: m.tag == n[0], players)
                        info.append(player.name)
                    if guild_config.don:
                        info.append(n[1])
                    if guild_config.rec:
                        info.append(n[2])
                    if guild_config.tag:
                        info.append(n[0])
                    if guild_config.claimed_by:
                        user = guild.get_member(n[3])
                        info.append(str(user) or 'None')
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
            await header.edit(embed=discord.Embed(colour=self.bot.colour,
                                                  description=f'Last updated {datetime.now():%Y-%m-%d %H:%M:%S%z}'),
                              content=None)


def setup(bot):
    bot.add_cog(Updates(bot))
