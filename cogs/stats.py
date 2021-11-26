import itertools
import time
import math

from collections import namedtuple, defaultdict

import coc
import discord
import disnake

from disnake.ext import commands

# from discord.ext import commands
# from discord.ext.commands.core import _CaseInsensitiveDict

from cogs.utils.converters import ConvertToPlayers
from cogs.utils.paginator import StatsAttacksPaginator, StatsDefensesPaginator, StatsTrophiesPaginator, \
                                 StatsDonorsPaginator, StatsLastOnlinePaginator, StatsAchievementPaginator, \
                                 StatsAccountsPaginator


FakeClan = namedtuple("FakeClan", "tag")
Achievements = commands.option_enum(coc.enums.ACHIEVEMENT_ORDER)

async def autocomp_achievement(intr: disnake.ApplicationCommandInteraction, user_input: str):
    return [ach for ach in coc.enums.ACHIEVEMENT_ORDER if user_input.lower() in ach]


class CustomPlayer(coc.Player):
    def get_caseinsensitive_achievement(self, name):
        # if self._achievements is None:
        #     self._achievements = _CaseInsensitiveDict()
        #     for achievement in getattr(self, "_iter_achievements"):
        #         self._achievements[achievement.name] = achievement

        try:
            return self._achievements[name]
        except KeyError:
            return None

    def get_ach_value(self, name):
        ach = self.get_caseinsensitive_achievement(name)
        return ach and ach.value or 0


class SuperPlayer:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getitem__(self, item):
        return getattr(self, item, None)


class ExpiringCache(dict):
    def __init__(self, seconds):
        self.ttl = seconds
        super().__init__()

    def clean_old(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (v, t)) in self.items() if current_time > (t + self.ttl)]
        for k in to_remove:
            del self[k]

    def __getitem__(self, key):
        self.clean_old()
        return super().__getitem__(key)[0]

    def __setitem__(self, key, value):
        super().__setitem__(key, (value, time.monotonic()))

    def __contains__(self, key):
        self.clean_old()
        return super().__contains__(key)


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._players = ExpiringCache(seconds=3600.0)

    async def convert_argument_to_players(self, player: str, clan: str, user: disnake.Member, channel: disnake.TextChannel, guild_id: int, conn):
        season_id = await self.bot.seasonconfig.get_season_id()

        fake_clan_in_server = guild_id in self.bot.fake_clan_guilds
        join = "(clans.clan_tag = players.clan_tag OR " \
               "(players.fake_clan_tag IS NOT NULL AND clans.clan_tag = players.fake_clan_tag))" \
               if fake_clan_in_server else "clans.clan_tag = players.clan_tag"

        if player:
            query = """SELECT DISTINCT player_tag, 
                                       player_name,
                                       players.clan_tag,
                                       donations, 
                                       received, 
                                       trophies, 
                                       trophies - start_trophies AS "gain", 
                                       last_updated - now() AS "since",
                                       user_id 
                       FROM players 
                       WHERE player_tag = $1 
                       AND players.season_id = $3
                       OR player_name LIKE $2 
                       AND players.season_id = $3
                    """
            return await conn.fetch(query, coc.utils.correct_tag(player), player, season_id)

        if clan:
            if clan.strip().isdigit():
                corrected = clan.strip()
            else:
                corrected = coc.utils.correct_tag(clan)

            query = f"""SELECT DISTINCT player_tag, 
                                        player_name,
                                        clans.clan_name,
                                        players.clan_tag,
                                        donations, 
                                        received, 
                                        trophies, 
                                        trophies - start_trophies AS "gain", 
                                        last_updated - now() AS "since",
                                        user_id 
                         FROM players 
                         INNER JOIN clans 
                         ON {join}
                         WHERE clans.clan_tag = $1 
                         AND players.season_id = $3
                         OR clans.clan_name LIKE $2 
                         AND players.season_id = $3
                    """

            return await conn.fetch(query, corrected, clan, season_id)

        if user:
            links = await self.bot.links.get_linked_players(user.id)
            query = """SELECT DISTINCT player_tag, 
                                       player_name,
                                       players.clan_tag,
                                       donations, 
                                       received, 
                                       trophies, 
                                       trophies - start_trophies AS "gain", 
                                       last_updated - now() AS "since",
                                       user_id 
                       FROM players 
                       WHERE player_tag = ANY($1::TEXT[])
                       AND players.season_id = $2
                    """
            return await conn.fetch(query, links, season_id)

        if channel:
            query = f"""SELECT DISTINCT player_tag, 
                                        player_name,
                                        clans.clan_name,
                                        players.clan_tag,
                                        donations, 
                                        received, 
                                        trophies, 
                                        trophies - start_trophies AS "gain", 
                                        last_updated - now() AS "since",
                                        user_id 
                        FROM players 
                        INNER JOIN clans 
                        ON {join}
                        WHERE clans.channel_id = $1 
                        AND players.season_id = $2
                     """
            return await conn.fetch(query, channel.id, season_id)

        query = f"""SELECT DISTINCT player_tag, 
                                    player_name,
                                    clans.clan_name,
                                    players.clan_tag,
                                    donations, 
                                    received, 
                                    trophies, 
                                    trophies - start_trophies AS "gain", 
                                    last_updated - now() AS "since",
                                    user_id 
                    FROM players
                    INNER JOIN clans
                    ON {join}
                    WHERE clans.guild_id = $1 
                    AND players.season_id = $2
                 """
        return await conn.fetch(query, guild_id, season_id)

    async def _get_players(self, player_tags):
        need_to_get = [tag for tag in player_tags if tag not in self._players.keys()]
        if need_to_get:
            async for player in self.bot.coc.get_players([tag for tag in player_tags if tag not in self._players.keys()], cls=CustomPlayer):
                self._players[player.tag] = player

        return [v for (k, (v, _)) in self._players.items() if k in player_tags]

    async def _group_players_by_user(self, players, guild, fetch_api=False, achievement=None):
        to_return = []

        user_ids = {row['user_id'] for row in players if row['user_id']}
        discord_members = {member.id: member for member in await self.bot.query_member_by_id_batch(guild, user_ids)}

        for user_id, accounts in itertools.groupby(sorted(players, key=lambda r: (r['user_id'] or 0)), key=lambda r: (r['user_id'] or 0)):
            accounts = list(accounts)
            if fetch_api:
                api_players = [self._players[row['player_tag']] for row in accounts]

                if user_id == 0:
                    to_return.extend(api_players)
                else:
                    super_player = SuperPlayer(
                        tag=user_id,
                        name=str(discord_members.get(user_id, "NotFound")),
                        attack_wins=sum(p.attack_wins for p in api_players),
                        defense_wins=sum(p.defense_wins for p in api_players),
                        donations=sum(p.trophies for p in api_players),
                        clan=FakeClan(accounts[0]['clan_tag']),
                        aggr_achievement=sum(p.get_ach_value(achievement) for p in api_players) if achievement else 0,
                    )
                    to_return.append(super_player)

            else:
                if user_id == 0:
                    to_return.extend(accounts)
                else:
                    super_player = SuperPlayer(
                        player_tag=user_id,
                        player_name=str(discord_members.get(user_id, "NotFound")),
                        trophies=sum(p['trophies'] for p in accounts),
                        gain=sum(p['gain'] for p in accounts),
                        donations=sum(p['donations'] for p in accounts),
                        received=sum(p['received'] for p in accounts),
                        since=min(p['since'] for p in accounts),
                        user_id=user_id,
                        clan=FakeClan(accounts[0]['clan_tag']),
                    )
                    to_return.append(super_player)

        return to_return

    async def _get_emojis(self, guild_id):
        query = "SElECT DISTINCT clan_tag, emoji FROM clans WHERE guild_id = $1 AND emoji != ''"
        return {n['clan_tag']: f"<:x:{n['emoji']}>" if n['emoji'].isdigit() else n['emoji'] for n in await self.bot.pool.fetch(query, guild_id)}

    def _get_description(self, emojis, players, get_summary, total: int = None):
        clan_names = set((p.get('clan_name'), p['clan_tag']) for p in players if p.get('clan_name'))
        if clan_names:
            description = "Showing Stats For:\n" + "".join(
                f"{emojis.get(tag, '•')} {name} {get_summary(tag)}\n" for name, tag in clan_names) + "\n"
        else:
            description = ""

        if isinstance(total, int):
            description += f"Grand Total: {total:,d}\n\n"
        elif isinstance(total, str):
            description += f"Grand Total: {total}\n\n"

        if not emojis:
            description += "Want to see who is in which clan?\nTry adding a clan emoji: `+add emoji #clantag :emoji:`\n\n"

        return description

    async def cog_before_invoke(self, ctx):
        await ctx.trigger_typing()

    @commands.slash_command(
        name="attacks",
        description="Get top attack wins for a clan or player. If you specify nobody, it will get all attacks for your server."
    )
    async def attacks(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get top attack wins for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+attacks`
        :information_source: `+attacks #CLAN_TAG`
        :information_source: `+attacks CLAN NAME`
        :information_source: `+attacks #PLAYER_TAG`
        :information_source: `+attacks Player Name`
        :information_source: `+attacks #channel`
        :information_source: `+attacks @user`
        :information_source: `+attacks all`

        **Example**
        :white_check_mark: `+attacks`
        :white_check_mark: `+attacks #JY9J2Y99`
        :white_check_mark: `+attacks Reddit --byuser`
        :white_check_mark: `+attacks Mathsman`
        :white_check_mark: `+attacks @mathsman#1208`
        :white_check_mark: `+attacks #donation-log`
        :white_check_mark: `+attacks all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = await self._get_players([p['player_tag'] for p in players])
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        att_sum = defaultdict(int)
        for player in data:
            att_sum[player.clan.tag] += player.attack_wins

        title = f"Top Attack Wins"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(emojis, players, lambda tag: f"({att_sum[tag]})", sum(att_sum.values()))

        p = StatsAttacksPaginator(
            intr,
            data=data,
            page_count=math.ceil(len(data) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.slash_command(
        name="defenses",
        description="Get top defense wins for a clan or player. If you specify nobody, it will get all defenses for your server."
    )
    async def defenses(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get top defense wins for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+defenses`
        :information_source: `+defenses #CLAN_TAG`
        :information_source: `+defenses CLAN NAME`
        :information_source: `+defenses #PLAYER_TAG`
        :information_source: `+defenses Player Name`
        :information_source: `+defenses #channel`
        :information_source: `+defenses @user`
        :information_source: `+defenses all`

        **Example**
        :white_check_mark: `+defenses`
        :white_check_mark: `+defenses #JY9J2Y99`
        :white_check_mark: `+defenses Reddit --byuser`
        :white_check_mark: `+defenses Mathsman`
        :white_check_mark: `+defenses @mathsman#1208`
        :white_check_mark: `+defenses #donation-log`
        :white_check_mark: `+defenses all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = await self._get_players([p['player_tag'] for p in players])
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        def_sum = defaultdict(int)
        for player in data:
            def_sum[player.clan.tag] += player.defense_wins

        title = f"Top Defense Wins"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(emojis, players, lambda tag: f"({def_sum[tag]})", sum(def_sum.values()))

        p = StatsDefensesPaginator(
            intr,
            data=data,
            page_count=math.ceil(len(data) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(
        name="donations",
        description="Get top donations for a clan or player. If you specify nobody, it will get all donations for your server."
    )
    async def donations(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get top donations for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+donations`
        :information_source: `+donations #CLAN_TAG`
        :information_source: `+donations CLAN NAME`
        :information_source: `+donations #PLAYER_TAG`
        :information_source: `+donations Player Name`
        :information_source: `+donations #channel`
        :information_source: `+donations @user`
        :information_source: `+donations all`

        **Example**
        :white_check_mark: `+donations`
        :white_check_mark: `+donations #JY9J2Y99`
        :white_check_mark: `+donations Reddit --byuser`
        :white_check_mark: `+donations Mathsman`
        :white_check_mark: `+donations @mathsman#1208`
        :white_check_mark: `+donations #donation-log`
        :white_check_mark: `+donations all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = sorted(players, key=lambda p: p['donations'], reverse=True)
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        don_sum, rec_sum = defaultdict(int), defaultdict(int)
        for player in data:
            don_sum[player['clan_tag']] += player['donations']
            rec_sum[player['clan_tag']] += player['received']

        def get_summary(tag):
            return f"({don_sum[tag]:,d}/{rec_sum[tag]:,d})"

        title = "Top Donations"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(
            emojis,
            players,
            get_summary,
            f"{sum(don_sum.values()):,d}/{sum(rec_sum.values()):,d}",
        )

        p = StatsDonorsPaginator(
            intr,
            data=data,
            page_count=math.ceil(len(data) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(
        name="received",
        description="Get top troops received for a clan or player. If you specify nobody, it will get all received stats for your server."
    )
    async def received(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):

        """Get top troops received for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+received`
        :information_source: `+received #CLAN_TAG`
        :information_source: `+received CLAN NAME`
        :information_source: `+received #PLAYER_TAG`
        :information_source: `+received Player Name`
        :information_source: `+received #channel`
        :information_source: `+received @user`
        :information_source: `+received all`

        **Example**
        :white_check_mark: `+received`
        :white_check_mark: `+received #JY9J2Y99`
        :white_check_mark: `+received Reddit --byuser`
        :white_check_mark: `+received Mathsman`
        :white_check_mark: `+received @mathsman#1208`
        :white_check_mark: `+received #donation-log`
        :white_check_mark: `+received all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = sorted(players, key=lambda p: p['received'], reverse=True)
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        don_sum, rec_sum = defaultdict(int), defaultdict(int)
        for player in data:
            don_sum[player['clan_tag']] += player['donations']
            rec_sum[player['clan_tag']] += player['received']

        def get_summary(tag):
            return f"({don_sum[tag]:,d}/{rec_sum[tag]:,d})"

        title = "Top Receivers"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(
            emojis,
            players,
            get_summary,
            f"{sum(don_sum.values()):,d}/{sum(rec_sum.values()):,d}",
        )

        p = StatsDonorsPaginator(
            intr,
            data=data,
            page_count=math.ceil(len(data) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(
        name="trophies",
        description="Get top trophies counts for a clan or player. If you specify nobody, it will get all counts for your server."
    )
    async def trophies(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get top trophy counts for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+trophies`
        :information_source: `+trophies #CLAN_TAG`
        :information_source: `+trophies CLAN NAME`
        :information_source: `+trophies #PLAYER_TAG`
        :information_source: `+trophies Player Name`
        :information_source: `+trophies #channel`
        :information_source: `+trophies @user`
        :information_source: `+trophies all`

        **Example**
        :white_check_mark: `+trophies`
        :white_check_mark: `+trophies #JY9J2Y99`
        :white_check_mark: `+trophies Reddit --byuser`
        :white_check_mark: `+trophies Mathsman`
        :white_check_mark: `+trophies @mathsman#1208`
        :white_check_mark: `+trophies #donation-log`
        :white_check_mark: `+trophies all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = sorted(players, key=lambda p: p['trophies'], reverse=True)
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        cup_sum = defaultdict(int)
        for player in data:
            cup_sum[player['clan_tag']] += player['trophies']

        title = "Top Trophies"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(emojis, players, lambda tag: f"({cup_sum[tag]})", sum(cup_sum.values()))

        p = StatsTrophiesPaginator(
            intr, data=data, page_count=math.ceil(len(data) / 20), title=title, description=description, emojis=emojis
        )
        await p.paginate()

    @commands.command(
        name="lastonline",
        description="Get recent last-online status for a clan or player. If you specify nobody, it will get all stats for your server."
    )
    async def lastonline(
            self,
            intr: disnake.ApplicationCommandInteraction,
            player: str = commands.Param(default=None, description="Player #tag or name."),
            clan: str = commands.Param(default=None, description="Clan #tag or name."),
            user: disnake.Member = commands.Param(default=None, description="User in this server."),
            channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
            by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get recent last-online status for a clan or player.

        Use `--byuser` to group accounts based on their linked discord users.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+lastonline`
        :information_source: `+lastonline #CLAN_TAG`
        :information_source: `+lastonline CLAN NAME`
        :information_source: `+lastonline #PLAYER_TAG`
        :information_source: `+lastonline Player Name`
        :information_source: `+lastonline #channel`
        :information_source: `+lastonline @user`
        :information_source: `+lastonline all`

        **Example**
        :white_check_mark: `+lastonline`
        :white_check_mark: `+lastonline #JY9J2Y99`
        :white_check_mark: `+lastonline Reddit --byuser`
        :white_check_mark: `+lastonline Mathsman`
        :white_check_mark: `+lastonline @mathsman#1208`
        :white_check_mark: `+lastonline #donation-log`
        :white_check_mark: `+lastonline all`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Last Online"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(emojis, players, lambda _: "")

        data = sorted(players, key=lambda p: p['since'], reverse=True)
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True)

        p = StatsLastOnlinePaginator(
            intr, data=data, page_count=math.ceil(len(data) / 20), title=title, description=description, emojis=emojis
        )
        await p.paginate()

    @commands.command(
        name="achievements",
        description="Get top achievement counts for a clan/player. If you specify nobody, it will get all stats for your server."
    )
    async def achievement(
        self,
        intr: disnake.ApplicationCommandInteraction,
        achievement: Achievements,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        by_user: bool = commands.Param(default=False, description="Group users by their linked discord users.")
    ):
        """Get top achievement counts for all clan/players in the server.

        Use `--byuser` to group accounts based on their linked discord users.

        A few common achievements have been included:
            - `gg` -> `Gold Grab`
            - `ee` -> `Elixir Escapade`
            - `hh` -> `Heroic Heist`
            - `fin` -> `Friend in Need`
            - `sic` -> `Sharing is caring`

        **Parameters**
        :key: Achievement: the name of the achievement you want to get stats for. Can be case-insensitive, but must have correct spelling!

        **Format**
        :information_source: `+achievement ACHIEVEMENT_NAME`

        **Example**
        :white_check_mark: `+achievement gg`
        :white_check_mark: `+achievement Gold Grab --byuser`
        :white_check_mark: `+achievement Unbreakable`
        :white_check_mark: `+achievement Get those goblins!`
        """

        # common_lookups = [
        #     ("gg", "Gold Grab"),
        #     ("ee", "Elixir Escapade"),
        #     ("hh", "Heroic Heist"),
        #     ("fin", "Friend in Need"),
        #     ("sic", "Sharing is caring"),
        # ]
        # for common, replacement in common_lookups:
        #     achievement = achievement.replace(common, replacement)

        title = f"Achievement Stats: {achievement}"

        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        data = await self._get_players([p['player_tag'] for p in players])
        if by_user:
            data = await self._group_players_by_user(players, intr.guild, fetch_api=True, achievement=achievement)

        if not data[0].get_caseinsensitive_achievement(achievement):
            return await intr.send("I couldn't find that achievement, sorry. Please make sure your spelling is correct!")

        data = sorted(data, key=lambda p: p.get_ach_value(achievement), reverse=True)

        data_sum = defaultdict(int)
        for player in data:
            data_sum[player.clan.tag] += player.get_ach_value(achievement)

        emojis = await self._get_emojis(intr.guild.id)
        description = "*" + data[0].get_caseinsensitive_achievement(achievement).info + "*\n\n"
        description += self._get_description(emojis, players, lambda tag: f"({data_sum[tag]})", sum(data_sum.values()))

        p = StatsAchievementPaginator(
            intr, data=data, page_count=math.ceil(len(data) / 20), title=title, description=description, achievement=achievement, emojis=emojis
        )
        await p.paginate()

    @commands.command(
        name="accounts",
        description="Get accounts added to the bot for clan/players. If you specify nobody, it will get all accounts for your server."
    )
    async def accounts(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        user: disnake.Member = commands.Param(default=None, description="User in this server."),
        channel: disnake.TextChannel = commands.Param(default=None, description="Channel in this server."),
        show_tags: bool = commands.Param(default=False, description="Show player tags instead of discord IDs")
    ):
        """Get accounts added to the bot for clan/players.

        If you wish to see the player tags instead of discord users, add `showtags` to the end of your message.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+accounts`
        :information_source: `+accounts showtags`
        :information_source: `+accounts #CLAN_TAG`
        :information_source: `+accounts CLAN NAME`
        :information_source: `+accounts #PLAYER_TAG`
        :information_source: `+accounts Player Name`
        :information_source: `+accounts #channel`
        :information_source: `+accounts @user`
        :information_source: `+accounts all`

        **Example**
        :white_check_mark: `+accounts`
        :white_check_mark: `+accounts showtags`
        :white_check_mark: `+accounts #JY9J2Y99`
        :white_check_mark: `+accounts Reddit`
        :white_check_mark: `+accounts Mathsman`
        :white_check_mark: `+accounts @mathsman#1208`
        :white_check_mark: `+accounts #donation-log`
        :white_check_mark: `+accounts all showtags`
        """
        players = await self.convert_argument_to_players(player, clan, user, channel, intr.guild_id, intr.db)
        if not players:
            return
        #     return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Accounts Added"
        emojis = await self._get_emojis(intr.guild.id)
        description = self._get_description(emojis, players, lambda _: "")

        tags_to_name = {p['player_tag']: p for p in players}

        async def get_claim(tag, discord_id):
            player = tags_to_name.get(tag, {'player_name': 'Unknown', 'clan_tag': ''})
            if discord_id is None or show_tags is True:
                return player['player_name'] or 'Unknown', tag, emojis.get(player['clan_tag'], '')

            member = intr.guild.get_member(discord_id) or self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id) or 'Unknown.....'
            return player['player_name'] or 'Unknown', str(member)[:-5], emojis.get(player['clan_tag'], '')

        links = await self.bot.links.get_links(*tags_to_name.keys())
        data = sorted([await get_claim(player_tag, discord_id) for player_tag, discord_id in links], key=lambda p: (p[1], p[0]), reverse=True)

        p = StatsAccountsPaginator(
            intr, data=data, page_count=math.ceil(len(players) / 20), title=title, description=description
        )
        await p.paginate()


def setup(bot):
    bot.add_cog(Stats(bot))
