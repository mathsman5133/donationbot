import coc
import discord
import math
import typing

from collections import namedtuple
from discord.ext import commands
from datetime import datetime
from cogs.utils import formatters
from cogs.utils.checks import requires_config
from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils.db_objects import SlimDummyBoardConfig

DummyRender = namedtuple('DummyRender', 'render type icon_url')


class Trophies(commands.Cog):
    """Get trophies of clans, players and users."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='trophies', aliases=['troph'],  invoke_without_command=True)
    async def trophies(self, ctx, *,
                        arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Check trophies for a player, user, clan or guild.

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+trophies @MENTION`
        :information_source: `+trophies #PLAYER_TAG`
        :information_source: `+trophies Player Name`
        :information_source: `+trophies #CLAN_TAG`
        :information_source: `+trophies Clan Name`
        :information_source: `+trophies all`

        **Example**
        :white_check_mark: `+trophies @mathsman`
        :white_check_mark: `+trophies #JJ6C8PY`
        :white_check_mark: `+trophies mathsman`
        :white_check_mark: `+trophies #P0LYJC8C`
        :white_check_mark: `+trophies Rock Throwers`
        :white_check_mark: `+trophies all`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = await ctx.get_clans()

        if not arg:
            return await ctx.send('Please claim a clan.')
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.trophies_user, user=arg)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.trophies_player, player=arg)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.trophies_clan, clans=arg)
                
    @trophies.command(name='user')
    async def trophies_user(self, ctx, *, user: discord.Member = None):
        """Get trophies for a discord user.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Discord user (optional - defaults to yourself)

        **Format**
        :information_source: `+trophies user @MENTION`
        :information_source: `+trophies user`

        **Example**
        :white_check_mark: `+trophies user @mathsman`
        :white_check_mark: `+trophies user`
        """
        if not user:
            user = ctx.author

        query = """SELECT player_tag, trophies, start_trophies - trophies AS "gain", user_id 
                    FROM players 
                    WHERE user_id = $1 
                    AND season_id=$2
                    ORDER BY trophies DESC
                """
        fetch = await ctx.db.fetch(query, user.id, await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                  f"have any accounts claimed")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Trophies for {str(user)}'

        p = formatters.BoardPaginator(ctx, data=fetch, page_count=page_count, title=title)

        await p.paginate()

    @trophies.command(name='player')
    async def trophies_player(self, ctx, *, player: PlayerConverter):
        """Get trophies for a player.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.


        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+trophies player #PLAYER_TAG`
        :information_source: `+trophies player Player Name`

        **Example**
        :white_check_mark: `+trophies player #P0LYJC8C`
        :white_check_mark: `+trophies player mathsman`
        """

        query = """SELECT player_tag, trophies, start_trophies - trophies, user_id 
                    FROM players 
                    WHERE player_tag = $1 
                    AND season_id=$2
                    ORDER BY donations DESC
                """
        fetch = await ctx.db.fetch(query, player.tag, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            return await ctx.send(f"{str(player)} ({player.tag}) has not been claimed.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Trophies for {player.name}'

        p = formatters.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @trophies.command(name='clan')
    async def trophies_clan(self, ctx, *, clans: ClanConverter):
        """Get trophies for a clan.
                
        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Clan name OR tag OR `all` to get all clans.

        **Format**
        :information_source: `+trophies clan #CLAN_TAG`
        :information_source: `+trophies clan Clan Name`
        :information_source: `+trophies clan all`

        **Example**
        :white_check_mark: `+trophies clan #P0LYJC8C`
        :white_check_mark: `+trophies clan Rock Throwers`
        :white_check_mark: `+trophies clan all`
        """
        
        query = """SELECT player_tag, trophies, trophies - start_trophies, user_id 
                    FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY trophies DESC NULLS LAST
                """
        tags = []
        for n in clans:
            tags.extend(x.tag for x in n.itermembers)

        fetch = await ctx.db.fetch(query, tags, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            return await ctx.send(f"No players claimed for clans "
                                  f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`"
                                  )

        page_count = math.ceil(len(fetch) / 20)
        title = f"Trophies for {', '.join(f'{c.name}' for c in clans)}"
        p = formatters.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()


def setup(bot):
    bot.add_cog(Trophies(bot))
