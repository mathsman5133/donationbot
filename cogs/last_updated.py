import math
import typing

import coc
import discord

from discord.ext import commands

from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils.formatters import readable_time
from cogs.utils.paginator import LastOnlinePaginator


class LastUpdated(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_updated = {}

    @commands.group(name='lastonline')
    async def last_online(self, ctx, *, arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Check an approximate last online time for a player, user, clan or guild.

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+lastonline @MENTION`
        :information_source: `+lastonline #PLAYER_TAG`
        :information_source: `+lastonline Player Name`
        :information_source: `+lastonline #CLAN_TAG`
        :information_source: `+lastonline Clan Name`
        :information_source: `+lastonline all`

        **Example**
        :white_check_mark: `+lastonline @mathsman`
        :white_check_mark: `+lastonline #JJ6C8PY`
        :white_check_mark: `+lastonline mathsman`
        :white_check_mark: `+lastonline #P0LYJC8C`
        :white_check_mark: `+lastonline Rock Throwers`
        :white_check_mark: `+lastonline all`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = await ctx.get_clans()

        if not arg:
            return await ctx.send('Please claim a clan.')
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.last_online_user, user=arg)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.last_online_player, player=arg)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.last_online_clan, clan=arg)

    @last_online.command(name='clan')
    async def last_online_clan(self, ctx, *, clan: ClanConverter):
        """Get an approximation for the last time members of a clan were online.

        **Parameters**
        :key: Clan name OR tag

        **Format**
        :information_source: `+lastonline clan #CLANTAG`
        :information_source: `+lastonline clan Clan Name`

        **Example**
        :white_check_mark: `+lastonline clan #P0LYJC8C`
        :white_check_mark: `+lastonline clan Rock Throwers`
        """
        query = """SELECT player_tag, 
                          last_updated - now() AS "since" 
                   FROM players 
                   WHERE player_tag = ANY($1::TEXT[]) 
                   AND season_id=$2 
                   ORDER BY since DESC
                """

        tags = []
        for n in clan:
            tags.extend(x.tag for x in n.itermembers)

        fetch = await ctx.db.fetch(query, tags, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            return await ctx.send(
                f"No players claimed for clans `{', '.join(f'{c.name} ({c.tag})' for c in clan)}`"
            )

        page_count = math.ceil(len(fetch) / 20)
        title = f"Last Online Estimates for {', '.join(str(n) for n in clan)}"

        p = LastOnlinePaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @last_online.command(name='player')
    async def last_online_player(self, ctx, *, player: PlayerConverter):
        """Get an approximation for the last time a player was online.

        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+lastonline player #PLAYER_TAG`
        :information_source: `+lastonline player Player Name`

        **Example**
        :white_check_mark: `+lastonline player #P0LYJC8C`
        :white_check_mark: `+lastonline player mathsman`
        """

        query = """SELECT player_tag, 
                          last_updated - now() AS "since" 
                   FROM players 
                   WHERE player_tag = $1 
                   AND season_id = $2
                   ORDER BY since DESC
                """
        fetch = await ctx.db.fetchrow(query, player.tag, await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send(
                f"{player} ({player.tag}) was not found in the database. Try `+add player {player.tag}`."
            )
        last_updated = fetch['since']

        time = readable_time(last_updated.total_seconds())
        await ctx.send(f"A good guess for the last time {player} ({player.tag}) was online was: `{time}`.")

    @last_online.command(name='user')
    async def last_online_user(self, ctx, *, user: discord.Member = None):
        """Get an approximation for the last time a player was online.

        **Parameters**
        :key: Discord user (optional - defaults to yourself)

        **Format**
        :information_source: `+lastonline user @MENTION`
        :information_source: `+lastonline user`

        **Example**
        :white_check_mark: `+lastonline user @mathsman`
        :white_check_mark: `+lastonline user`
        """
        user = user or ctx.author
        query = """SELECT player_tag, 
                          last_updated - now() AS "since" 
                   FROM players 
                   WHERE user_id = $1 
                   AND season_id = $2
                   ORDER BY since DESC
                """
        fetch = await ctx.db.fetch(query, user.id, await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send(f"{user} doesn't have any claimed accounts.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Last Online Estimate for {user}'

        p = LastOnlinePaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()


def setup(bot):
    bot.add_cog(LastUpdated(bot))
