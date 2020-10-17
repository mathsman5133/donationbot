import math

import coc

from discord.ext import commands
from discord.ext.commands.core import _CaseInsensitiveDict

from cogs.utils.cache import ExpiringCache
from cogs.utils.converters import ConvertToPlayers
from cogs.utils.emoji_lookup import misc
from cogs.utils.paginator import StatsAttacksPaginator, StatsDefensesPaginator, StatsTrophiesPaginator, StatsDonorsPaginator, StatsGainsPaginator, StatsLastOnlinePaginator, StatsAchievementPaginator, StatsAccountsPaginator


class CustomPlayer(coc.Player):
    def get_caseinsensitive_achievement(self, name):
        if self._achievements is None:
            self._achievements = _CaseInsensitiveDict()
            for achievement in getattr(self, "_Player__iter_achievements"):
                self._achievements[achievement.name] = achievement

        try:
            return self._achievements[name]
        except KeyError:
            return None

    def get_ach_value(self, name):
        ach = self.get_caseinsensitive_achievement(name)
        return ach and ach.value or 0


class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._players = ExpiringCache(seconds=3600.0)

    async def _get_players(self, player_tags):
        need_to_get = [tag for tag in player_tags if tag not in self._players.keys()]
        if need_to_get:
            async for player in self.bot.coc.get_players([tag for tag in player_tags if tag not in self._players.keys()], cls=CustomPlayer):
                self._players[player.tag] = player

        return [v for (k, (v, _)) in self._players.items() if k in player_tags]

    async def _get_emojis(self, guild_id):
        query = "SElECT DISTINCT clan_tag, emoji FROM clans WHERE guild_id = $1 AND emoji != ''"
        return {n['clan_tag']: n['emoji'] for n in await self.bot.pool.fetch(query, guild_id)}

    def _get_description(self, emojis, players):
        clan_names = set((p.get('clan_name'), p['clan_tag']) for p in players if p.get('clan_name'))
        if clan_names:
            description = "Showing Stats For:\n" + "".join(
                f"{emojis.get(tag, '•')} {name}\n" for name, tag in clan_names) + "\n"
        else:
            description = ""

        if not emojis:
            description += "Want to see who is in which clan?\nTry adding a clan emoji: `+add emoji #clantag :emoji:`\n\n"

        return description

    async def cog_before_invoke(self, ctx):
        await ctx.trigger_typing()

    @commands.command(name='attacks')
    async def attacks(self, ctx, *, argument: ConvertToPlayers = None):
        """Get top attack wins for a clan or player.

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
        :white_check_mark: `+attacks Reddit`
        :white_check_mark: `+attacks Mathsman`
        :white_check_mark: `+attacks @mathsman#1208`
        :white_check_mark: `+attacks #donation-log`
        :white_check_mark: `+attacks all`
        """
        if argument is None:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = f"Top Attack Wins"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        p = StatsAttacksPaginator(
            ctx,
            data=await self._get_players([p['player_tag'] for p in argument]),
            page_count=math.ceil(len(argument) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    async def defenses(self, ctx, *, argument: ConvertToPlayers = None):
        """Get top defense wins for a clan or player.

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
        :white_check_mark: `+defenses Reddit`
        :white_check_mark: `+defenses Mathsman`
        :white_check_mark: `+defenses @mathsman#1208`
        :white_check_mark: `+defenses #donation-log`
        :white_check_mark: `+defenses all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")

        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = f"Top Defense Wins"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        p = StatsDefensesPaginator(
            ctx,
            data=await self._get_players([p['player_tag'] for p in argument]),
            page_count=math.ceil(len(argument) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(aliases=['don', 'dons', 'donation'])
    async def donations(self, ctx, *, argument: ConvertToPlayers = None):
        """Get top donations for a clan or player.

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
        :white_check_mark: `+donations Reddit`
        :white_check_mark: `+donations Mathsman`
        :white_check_mark: `+donations @mathsman#1208`
        :white_check_mark: `+donations #donation-log`
        :white_check_mark: `+donations all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Top Donations"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        data = sorted(argument, key=lambda p: p['donations'], reverse=True)
        p = StatsDonorsPaginator(
            ctx,
            data=data,
            page_count=math.ceil(len(argument) / 20),
            title=title,
            description=description,
            emojis=emojis,
        )
        await p.paginate()

    @commands.command(aliases=['rec', 'recs', 'receives'])
    async def received(self, ctx, *, argument: ConvertToPlayers = None):
        """Get top troops received for a clan or player.

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
        :white_check_mark: `+received Reddit`
        :white_check_mark: `+received Mathsman`
        :white_check_mark: `+received @mathsman#1208`
        :white_check_mark: `+received #donation-log`
        :white_check_mark: `+received all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Top Receivers"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        data = sorted(argument, key=lambda p: p['received'], reverse=True)
        p = StatsDonorsPaginator(
            ctx, data=data, page_count=math.ceil(len(argument) / 20), title=title, description=description, emojis=emojis
        )
        await p.paginate()

    @commands.command(aliases=['troph', 'trophy'])
    async def trophies(self, ctx, *, argument: ConvertToPlayers = None):
        """Get top trophy counts for a clan or player.

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
        :white_check_mark: `+trophies Reddit`
        :white_check_mark: `+trophies Mathsman`
        :white_check_mark: `+trophies @mathsman#1208`
        :white_check_mark: `+trophies #donation-log`
        :white_check_mark: `+trophies all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")

        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Top Trophies"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        data = sorted(argument, key=lambda p: p['trophies'], reverse=True)
        p = StatsTrophiesPaginator(
            ctx, data=data, page_count=math.ceil(len(argument) / 20), title=title, description=description, emojis=emojis
        )
        await p.paginate()

    @commands.command(aliases=['lo', 'laston'])
    async def lastonline(self, ctx, *, argument: ConvertToPlayers = None):
        """Get recent last-online status for a clan or player.

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
        :white_check_mark: `+lastonline Reddit`
        :white_check_mark: `+lastonline Mathsman`
        :white_check_mark: `+lastonline @mathsman#1208`
        :white_check_mark: `+lastonline #donation-log`
        :white_check_mark: `+lastonline all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")

        if not argument:
            return await ctx.send("I couldn't find any players. Perhaps try adding a clan?")

        title = "Last Online"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        data = sorted(argument, key=lambda p: p['since'], reverse=True)
        p = StatsLastOnlinePaginator(
            ctx, data=data, page_count=math.ceil(len(argument) / 20), title=title, description=description, emojis=emojis
        )
        await p.paginate()

    @commands.command(aliases=["ach"])
    async def achievement(self, ctx, *, achievement: str):
        """Get top achievement counts for all clan/players in the server.

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
        :white_check_mark: `+achievement Gold Grab`
        :white_check_mark: `+achievement Unbreakable`
        :white_check_mark: `+achievement Get those goblins!`
        """
        if not achievement:
            return await ctx.send_help(ctx.command)

        common_lookups = [
            ("gg", "Gold Grab"),
            ("ee", "Elixir Escapade"),
            ("hh", "Heroic Heist"),
            ("fin", "Friend in Need"),
            ("sic", "Sharing is caring"),
        ]
        for common, replacement in common_lookups:
            achievement = achievement.replace(common, replacement)

        title = f"Achievement Stats: {achievement}"

        players = await ConvertToPlayers().convert(ctx, "all")
        data = await self._get_players([p['player_tag'] for p in players])

        if not data[0].get_caseinsensitive_achievement(achievement):
            return await ctx.send("I couldn't find that achievement, sorry. Please make sure your spelling is correct!")

        emojis = await self._get_emojis(ctx.guild.id)
        description = "*" + data[0].get_caseinsensitive_achievement(achievement).info + "*\n\n"
        description += self._get_description(emojis, data)

        data = sorted(data, key=lambda p: p.get_ach_value(achievement), reverse=True)
        p = StatsAchievementPaginator(
            ctx, data=data, page_count=math.ceil(len(data) / 20), title=title, description=description, achievement=achievement
        )
        await p.paginate()

    @commands.command(aliases=['acc'])
    async def accounts(self, ctx, *, argument: str = None):
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
        show_tags = False
        if not argument:
            argument = "all"
        elif 'showtags' in argument:
            argument = argument.replace('showtags', '').strip()
            show_tags = True

        argument = await ConvertToPlayers().convert(ctx, argument)

        title = "Accounts Added"
        emojis = await self._get_emojis(ctx.guild.id)
        description = self._get_description(emojis, argument)

        tags_to_name = {p['player_tag']: p for p in argument}

        async def get_claim(tag, discord_id):
            player = tags_to_name.get(tag, {'player_name': 'Unknown', 'clan_tag': ''})
            if discord_id is None or show_tags is True:
                return player['player_name'], tag, emojis.get(player['clan_tag'], '')

            member = ctx.guild.get_member(discord_id) or self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id) or 'Unknown.....'
            return player['player_name'], str(member)[:-5], emojis.get(player['clan_tag'], '')

        links = await self.bot.links.get_links(*tags_to_name.keys())
        data = sorted([await get_claim(player_tag, discord_id) for player_tag, discord_id in links], key=lambda p: (p[1], p[0]), reverse=True)

        p = StatsAccountsPaginator(
            ctx, data=data, page_count=math.ceil(len(argument) / 20), title=title, description=description
        )
        await p.paginate()


def setup(bot):
    bot.add_cog(Stats(bot))
