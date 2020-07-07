import coc
import discord
import math
import typing

from discord.ext import commands
from cogs.utils import paginator
from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils.db_objects import SlimDummyBoardConfig


class Donations(commands.Cog):
    """All commands related to donations of clans, players, users and servers."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        ctx.config = SlimDummyBoardConfig('donation', 1, 'Top Donations', None, 'donations')

    @commands.group(name='donations', aliases=['don'],  invoke_without_command=True)
    async def donations(self, ctx, *,
                        arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Check donations for a player, user, clan or guild.

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+don @MENTION`
        :information_source: `+don #PLAYER_TAG`
        :information_source: `+don Player Name`
        :information_source: `+don #CLAN_TAG`
        :information_source: `+don Clan Name`
        :information_source: `+don all`

        **Example**
        :white_check_mark: `+don @mathsman`
        :white_check_mark: `+don #JJ6C8PY`
        :white_check_mark: `+don mathsman`
        :white_check_mark: `+don #P0LYJC8C`
        :white_check_mark: `+don Rock Throwers`
        :white_check_mark: `+don all`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = await ctx.get_clans()

        if not arg:
            return await ctx.send('Please claim a clan.')
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.donations_user, user=arg)
        elif isinstance(arg, coc.Player):
            await ctx.invoke(self.donations_player, player=arg)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.donations_clan, clans=arg)

    @donations.command(name='user')
    async def donations_user(self, ctx, *, user: discord.Member = None):
        """Get donations for a discord user.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Discord user (optional - defaults to yourself)

        **Format**
        :information_source: `+don user @MENTION`
        :information_source: `+don user`

        **Example**
        :white_check_mark: `+don user @mathsman`
        :white_check_mark: `+don user`
        """
        if not user:
            user = ctx.author

        query = """SELECT player_tag, donations, received, user_id 
                   FROM players 
                   WHERE user_id = $1 
                   AND season_id=$2
                   ORDER BY donations DESC NULLS LAST
                """
        fetch = await ctx.db.fetch(query, user.id, await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                  f"have any accounts claimed")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {str(user)}'

        p = paginator.BoardPaginator(ctx, data=fetch, page_count=page_count, title=title)

        await p.paginate()

    @donations.command(name='player')
    async def donations_player(self, ctx, *, player: PlayerConverter):
        """Get donations for a player.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+don player #PLAYER_TAG`
        :information_source: `+don player Player Name`

        **Example**
        :white_check_mark: `+don player #P0LYJC8C`
        :white_check_mark: `+don player mathsman`
        """
        query = """SELECT player_tag, donations, received, user_id 
                    FROM players 
                    WHERE player_tag = $1 
                    AND season_id=$2
                    ORDER BY donations DESC NULLS LAST
                """
        fetch = await ctx.db.fetch(query, player.tag, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            raise commands.BadArgument(f"{str(player)} ({player.tag}) has not been claimed.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {player.name}'

        p = paginator.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @donations.command(name='clan')
    async def donations_clan(self, ctx, *, clans: ClanConverter):
        """Get donations for a clan.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Clan name OR tag OR `all` to get all clans.

        **Format**
        :information_source: `+don clan #CLAN_TAG`
        :information_source: `+don clan Clan Name`
        :information_source: `+don clan all`

        **Example**
        :white_check_mark: `+don clan #P0LYJC8C`
        :white_check_mark: `+don clan Rock Throwers`
        :white_check_mark: `+don clan all`
        """
        query = """SELECT player_tag, donations, received, user_id 
                    FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY donations DESC NULLS LAST
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
        title = f"Donations for {', '.join(f'{c.name}' for c in clans)}"

        p = paginator.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()


def setup(bot):
    bot.add_cog(Donations(bot))
