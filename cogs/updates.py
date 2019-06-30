from discord.ext import commands, tasks
import discord
from cogs.utils import fuzzy
import coc
import math
from cogs.donations import TabularData
from datetime import datetime


class Updates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.clan_updates = []
        self.player_updates = []
        self._new_month = False
        self._message_cache = {}
        self.clear_message_cache.start()
        self.bot.coc.add_events(self.on_clan_member_join, self.on_clan_member_donation,
                                self.on_clan_member_received)
        self.bot.coc._clan_retry_interval = 60
        self.bot.coc.start_updates('clan')

    def cog_unload(self):
        self.clear_message_cache.cancel()

    @tasks.loop(hours=1.0)
    async def clear_message_cache(self):
        self._message_cache.clear()

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

    async def update_clan_tags(self):
        query = "SELECT DISTINCT clan_tag FROM guilds"
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

    async def reset_message_id(self, channel_id, old_message_id=None):
        print('resetting...')
        msg = await self.bot.get_channel(channel_id).send('Placeholder')
        if not old_message_id:
            query = "INSERT INTO messages (message_id, guild_id) VALUES ($1, $2)"
            await self.bot.pool.execute(query, msg.id, self.bot.get_channel(channel_id).guild.id)
            return msg

        query = "UPDATE messages SET message_id = $1 WHERE message_id = $2"
        await self.bot.pool.execute(query, msg.id, old_message_id)
        return msg

    async def delete_message_id(self, channel_id, message_id):
        query = "DELETE FROM messages WHERE message_id = $1"
        await self.bot.pool.execute(query, message_id)
        msg = await self.bot.http.delete_message(channel_id, message_id)

    async def get_header_message(self, guild_id):
        query = "SELECT updates_channel_id, updates_message_id FROM guilds " \
                "WHERE guild_id = $1 AND updates_toggle = True"
        fetch = await self.bot.pool.fetchrow(query, guild_id)
        if not fetch:
            return None
        msg = await self.bot.get_channel(fetch[0]).fetch_message(fetch[1])
        return msg

    async def get_updates_messages(self, guild_id, number_of_msg=None):
        query = "SELECT guilds.updates_channel_id, DISTINCT messages.message_id FROM guilds INNER JOIN messages " \
                "ON guilds.guild_id = messages.guild_id WHERE guilds.guild_id = $1 AND guilds.updates_toggle = True"
        fetch = await self.bot.pool.fetch(query, guild_id)
        if not fetch:
            return None

        messages = []
        for c, m in fetch:
            msg = await self.get_message(c[0], m[0])
            if not msg:
                msg = await self.reset_message_id(c[0], m[0])

            messages.append(msg)

        if not number_of_msg:
            return messages
        if len(messages) == number_of_msg:
            return messages
        if len(messages) < number_of_msg:
            for i in range(number_of_msg - len(messages)):
                messages.append(await self.reset_message_id(fetch[0][0]))
            return messages
        if len(messages) > number_of_msg:
            for n in messages[number_of_msg:]:
                await self.delete_message_id(fetch[0][0], n.id)
            return messages[:number_of_msg]

    async def edit_updates_for_clan(self, clan):
        guilds = await self.bot.get_guilds(clan.tag)
        query = f"SELECT DISTINCT clan_tag FROM guilds WHERE guild_id IN " \
                f"({', '.join(str(n.id) for n in guilds)}) AND updates_toggle = True"
        fetch_guilds = await self.bot.pool.fetch(query)
        if not fetch_guilds:
            print('first sql query')
            return

        clans = await self.bot.coc.get_clans((n[0] for n in fetch_guilds)).flatten()
        print([n.name for n in clans])
        players = []
        for n in clans:
            players.extend(p for p in n._members)
        print(f'{len(players)} len players')

        query = "SELECT player_tag, donations, received, user_id FROM players " \
                f"WHERE player_tag = $1"

        player_info = []
        for n in players:
            fetch = await self.bot.pool.fetchrow(query, n.tag)
            if fetch:
                player_info.append([p for p in fetch])
            else:
                print(n)
        player_info.sort(key=lambda m: m[1], reverse=True)

        message_count = math.ceil(len(player_info) / 20)
        for result in guilds:
            print(message_count)
            messages = await self.get_updates_messages(result.id, number_of_msg=message_count)
            ign, don, rec, tag, claimed_by = await self.bot.guild_settings(result.id)
            if not messages:
                continue

            for i, v in enumerate(messages):
                settings = {'IGN': ign, 'Don': don, "Rec'd": rec, 'Player Tag': tag, 'Claimed By': claimed_by}
                final = []

                results = player_info[i*20:(i+1)*20]
                table = TabularData()

                table.set_columns([n for n in settings if settings[n] is True])

                for c, n in enumerate(results):
                    info = []
                    if ign:
                        player = discord.utils.find(lambda m: m.tag == n[0], players)
                        info.append(player.name)
                    if don:
                        info.append(n[1])
                    if rec:
                        info.append(n[2])
                    if tag:
                        info.append(n[0])
                    if claimed_by:
                        user = self.bot.get_user(n[3])
                        info.append(str(user) or 'None')
                    final.append(info)

                table.add_rows(final)

                fmt = f'```\n{table.render()}\n```'
                if len([n for n in settings if settings[n] is True]) > 3:
                    await v.edit(content=fmt, embed=None)
                    continue

                e = discord.Embed(colour=self.bot.colour)
                e.description = fmt
                await v.edit(embed=e, content=None)

            header = await self.get_header_message(result.id)
            await header.edit(embed=discord.Embed(colour=self.bot.colour,
                                                  description=f'Last updated {datetime.now():%Y-%m-%d %H:%M:%S%z}'),
                              content=None)

    async def on_clan_member_join(self, member, clan):
        query = "INSERT INTO players (player_tag, donations, received) VALUES ($1, $2, $3) " \
                "ON CONFLICT (player_tag) DO NOTHING"
        await self.bot.pool.execute(query, member.tag, member.donations, member.received)

        guilds = await self.bot.get_guilds(clan.tag)
        for n in guilds:
            results = await self.match_player(member, n)
            if not results:
                await self.bot.log_info(clan, f'{member.name} ({member.tag}) joined '
                                              f'{str(clan)} ({clan.tag}), but no corresponding '
                                              f'discord names were found.',
                                        colour=discord.Colour.red())
                # no members found in guild with that player name
            if isinstance(results, discord.Member):
                await self.bot.log_info(clan, f'{member.name} ({member.tag}) joined {str(clan)} ({clan.tag}) '
                                              f'and I found a singular matching discord account: {str(results)} '
                                              f'(ID {results.id}), so linked the 2 [auto]',
                                        colour=discord.Colour.green())

            table = TabularData()
            table.set_columns(['user#disrim', 'UserID'])
            table.add_rows([str(n), n.id] for n in results)
            await self.bot.log_info(clan, f'{member.name} ({member.tag}) joined {str(clan)} ({clan.tag}).\n'
                                          f'Corresponding members found, none claimed:\n'
                                          f'```\n{table.render()}\n```',
                                    colour=discord.Colour.gold())

    async def new_month(self):
        query = "UPDATE players SET donations = 0, received = 0"
        await self.bot.db.execute(query)

    async def on_clan_member_leave(self, member, clan):
        pass

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
        print('donated')
        print(player.name)

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
        print('received')
        print(player.name)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        for clan in await self.bot.get_clans(member.guild.id):
            results = await self.match_member(member, clan)
            if not results:
                await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined '
                                                      'the guild, but no corresponding COC players were found.',
                                        colour=discord.Colour.gold())
                return  # no members found in clan with that name
            if isinstance(results, coc.BasicPlayer):
                await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined '
                                                      'the guild, and was auto-claimed to '
                                                      f'{str(results)} ({results.tag}).',
                                        colour=discord.Colour.green())
                return  # we claimed a member
            if results is True:
                return  # member already claimed

            table = TabularData()
            table.set_columns(['IGN', 'Tag'])
            table.add_rows([n.name, n.tag] for n in results)
            await self.bot.log_info(member.guild, f'{str(member)} ({member.id}) joined the guild.\n'
                                                  f'Corresponding clan members found, none claimed:\n'
                                                  f'```\n{table.render()}\n```',
                                    colour=discord.Colour.gold())


def setup(bot):
    bot.add_cog(Updates(bot))
