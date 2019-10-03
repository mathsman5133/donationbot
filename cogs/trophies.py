import coc
import discord
import math
import typing

from discord.ext import commands
from cogs.utils import formatters
from cogs.utils.error_handler import error_handler
from cogs.utils.converters import ClanConverter, PlayerConverter


class Trophies(commands.Cog):
    """All commands related to donations of clans, players, users and servers."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        await error_handler(ctx, error)

    @commands.group(name='trophies', aliases=['trophy', 'troph', 'trop'],  invoke_without_command=True)
    async def trophies(self, ctx, *,
                       arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """Check trophies for a player, user, clan or guild.

        For a mobile-friendly table that is guaranteed to fit on a mobile screen,
        please use `+tromob`.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (clan must be claimed to the server)
            • A discord @mention, user#discrim or user id
            • A player tag
            • A player name (must be in clan claimed to server)
            • `all`, `server`, `guild` for all clans in guild
            • None passed will divert to donations for your guild

        Example
        -----------
        • `+trophies #CLAN_TAG`
        • `+trophies @mention`
        • `+trop #PLAYER_TAG`
        • `+trophy player name`
        • `+trop all`
        • `+top`

        Aliases
        -----------
        • `+trophies` (primary)
        • `+trophy`
        • `+troph`
        • `+trop`
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

    @trophies.command(name='user', hidden=True)
    async def trophies_user(self, ctx, *, user: discord.Member = None):
        """Get trophies for a discord user.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to trophies for your discord account

        Example
        ------------
        • `+trophies user @mention`
        • `+trop user USER_ID`
        • `+trop user`

        Aliases
        -----------
        • `+trophiess user` (primary)
        • `+trophy user`
        • `+troph user`
        • `+trop user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        query = """SELECT player_tag, trophies, user_id 
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

    @trophies.command(name='player', hidden=True)
    async def trophies_player(self, ctx, *, player: PlayerConverter):
        """Get trophies for a player.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ------------
        • `+trophies player #PLAYER_TAG`
        • `+trophy player player name`

        Aliases
        -----------
        • `+trophies player` (primary)
        • `+trophy player`
        • `+troph player`
        • `+trop player`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        query = """SELECT player_tag, trophies, user_id 
                    FROM players 
                    WHERE player_tag = $1 
                    AND season_id=$2
                    ORDER BY donations DESC
                """
        fetch = await ctx.db.fetch(query, player.tag, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            raise commands.BadArgument(f"{str(player)} ({player.tag}) has not been claimed.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Trophies for {player.name}'

        p = formatters.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @trophies.command(name='clan', hidden=True)
    async def trophies_clan(self, ctx, *, clans: ClanConverter):
        """Get trophies for a clan.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ------------
        • `+trophies clan #CLAN_TAG`
        • `+troph clan clan name`
        • `+trop clan all`

        Aliases
        -----------
        • `+trophies clan` (primary)
        • `+trophy clan`
        • `+troph clan`
        • `+trop clan`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        query = """SELECT player_tag, trophies, user_id 
                    FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY trophies DESC
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

    @trophies.command(name='attacks', hidden=True)
    async def trophies_attacks(self, ctx):
        """Get top trophies gained across all clans.

            Example
            ------------
            • `+trophies attacks`

            Aliases
            -----------
            • `+trophies attacks` (primary)
            • `+trophy attacks`
            • `+troph attacks`
            • `+trop attacks`

            By default, you shouldn't need to call these sub-commands as the bot will
            parse your argument and direct it to the correct sub-command automatically.
            """
        query = """SELECT clan_tag
                    FROM clans
                    WHERE guild_id = $1
                """
        tags = []
        clans = await ctx.db.fetch(query, ctx.guild.id)
        for n in clans:
            tags.extend(x.tag for x in n.itermembers)
        query = """SELECT player_tag, end_attacks - start_attacks as attacks, user_id 
                    FROM players p
                    INNER JOIN clans c ON 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY attacks DESC
                """
        fetch = await ctx.db.fetch(query, tags, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            return await ctx.send(f"No players claimed for clans "
                                  f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`"
                                  )

        page_count = math.ceil(len(fetch) / 20)
        title = f"Attack wins for {', '.join(f'{c.name}' for c in clans)}"

        p = formatters.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @trophies.command(name='defenses', aliases=['defences'], hidden=True)
    async def trophies_defenses(self, ctx):
        """Get top trophies gained across all clans.

            Example
            ------------
            • `+trophies defenses`

            Aliases
            -----------
            • `+trophies defenses` (primary)
            • `+trophy defenses`
            • `+troph defenses`
            • `+trop defenses`

            By default, you shouldn't need to call these sub-commands as the bot will
            parse your argument and direct it to the correct sub-command automatically.
            """
        query = """SELECT clan_tag
                    FROM clans
                    WHERE guild_id = $1
                """
        tags = []
        clans = await ctx.db.fetch(query, ctx.guild.id)
        for n in clans:
            tags.extend(x.tag for x in n.itermembers)
        query = """SELECT player_tag, end_defenses - start_defenses as defenses, user_id 
                    FROM players p
                    INNER JOIN clans c ON 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY defenses DESC
                """
        fetch = await ctx.db.fetch(query, tags, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            return await ctx.send(f"No players claimed for clans "
                                  f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`"
                                  )

        page_count = math.ceil(len(fetch) / 20)
        title = f"Defense wins for {', '.join(f'{c.name}' for c in clans)}"

        p = formatters.BoardPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @trophies.command(name='gain', hidden=True)
    async def trophies_gain(self, ctx):
        """Get top trophies gained across all clans.

            Example
            ------------
            • `+trophies gain`

            Aliases
            -----------
            • `+trophies gain` (primary)
            • `+trophy gain`
            • `+troph gain`
            • `+trop gain`

            By default, you shouldn't need to call these sub-commands as the bot will
            parse your argument and direct it to the correct sub-command automatically.
            """
        # TODO Unfinished: not sure how to calculate gains
        query = """SELECT player_tag, trophies, user_id 
                            FROM players 
                            WHERE player_tag=ANY($1::TEXT[])
                            AND season_id=$2
                            ORDER BY trophies DESC
                        """


def setup(bot):
    bot.add_cog(Trophies(bot))
