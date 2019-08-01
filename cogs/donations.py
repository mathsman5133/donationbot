from discord.ext import commands
import coc
import discord
import re
import math
from cogs.utils import formatters


tag_validator = re.compile("(?P<tag>^\s*#?[PYLQGRJCUV0289]+\s*$)")


class PlayerConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument:
            raise commands.BadArgument('No player tag or name supplied')
        if isinstance(argument, coc.BasicPlayer):
            return argument
        if tag_validator.match(argument):
            return await ctx.coc.get_player(argument)
        guild_clans = await ctx.get_clans()
        for g in guild_clans:
            if g.name == argument or g.tag == argument:
                raise commands.BadArgument(f'You appear to be passing '
                                           f'the clan tag/name for `{str(g)}`')

            member = g.get_member(name=argument)
            if member:
                return member  # finding don for clash player
            member_by_tag = g.get_member(tag=argument)
            if member_by_tag:
                return member_by_tag

        raise commands.BadArgument(f"Invalid tag or IGN in "
                                   f"`{','.join(str(n) for n in guild_clans)}` clans.")


class ClanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if argument in ['all', 'guild', 'server'] or not argument:
            return await ctx.get_clans()

        if not argument:
            raise commands.BadArgument('No clan tag or name supplied.')
        if isinstance(argument, coc.BasicClan):
            return argument
        if tag_validator.match(argument):
            return [await ctx.coc.get_clan(argument)]
        guild_clans = await ctx.get_clans()
        matches = [n for n in guild_clans if n.name == argument or n.tag == argument]
        if not matches:
            raise commands.BadArgument(f'Clan name or tag `{argument}` not found')
        return matches


class ArgConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument:
            return ctx.author
        if argument in ['all', 'server', 'guild']:
            return await ctx.get_clans()
        try:
            return await commands.MemberConverter().convert(ctx, argument)
            # finding don for a discord member
        except commands.BadArgument:
            pass
        guild_clans = await ctx.get_clans()
        for g in guild_clans:
            if g.name == argument or g.tag == argument:
                return [g]  # finding don for a clan

            member = g.get_member(name=argument)
            if member:
                return member  # finding don for clash player
            member_by_tag = g.get_member(tag=argument)
            if member_by_tag:
                return member
        return ctx.author


class Donations(commands.Cog):
    """All commands related to donations of clans, players, users and servers."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.group(name='donations', aliases=['don'],  invoke_without_command=True)
    async def donations(self, ctx, *, arg: ArgConverter = None):
        """Check donations for a player, user, clan or guild.

        For a mobile-friendly table that is guaranteed to fit on a mobile screen,
        please use `+donmob`.

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
        • `+donations #CLAN_TAG`
        • `+donations @mention`
        • `+don #PLAYER_TAG`
        • `+don player name`
        • `+don all`
        • `+don`

        Aliases
        -----------
        • `+donations` (primary)
        • `+don`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = await ctx.get_clans()

        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.donations_user, arg)
        elif isinstance(arg, coc.BasicClan):
            await ctx.invoke(self.donations_clan, clans=[arg])
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.donations_player, player=arg)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.donations_clan, clans=arg)

    @donations.command(name='user', hidden=True)
    async def donations_user(self, ctx, user: discord.Member = None):
        """Get donations for a discord user.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+donations user @mention`
        • `+don user USER_ID`
        • `+don user`

        Aliases
        -----------
        • `+donations user` (primary)
        • `+don user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        query = """SELECT player_tag, donations, received, user_id 
                        FROM players 
                    WHERE user_id = $1 
                    AND season_id=$2
                    ORDER BY donations DESC
                """
        fetch = await ctx.db.fetch(query, user.id, await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                  f"have any accounts claimed")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {str(user)}'

        p = formatters.DonationsPaginator(ctx, data=fetch, page_count=page_count, title=title)

        await p.paginate()

    @donations.command(name='player', hidden=True)
    async def donations_player(self, ctx, *, player: PlayerConverter):
        """Get donations for a player.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ------------
        • `+donations player #PLAYER_TAG`
        • `+don player player name`

        Aliases
        -----------
        • `+donations player` (primary)
        • `+don player`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """

        query = """SELECT player_tag, donations, received, user_id 
                        FROM players 
                    WHERE player_tag = $1 
                    AND season_id=$2
                    ORDER BY donations DESC
                """
        fetch = await ctx.db.fetch(query, player.tag, await self.bot.seasonconfig.get_season_id())

        if not fetch:
            raise commands.BadArgument(f"{str(player)} ({player.tag}) has not been claimed.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {player.name}'

        p = formatters.DonationsPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @donations.command(name='clan', hidden=True)
    async def donations_clan(self, ctx, *, clans: ClanConverter):
        """Get donations for a clan.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ------------
        • `+donations clan #CLAN_TAG`
        • `+don clan clan name`
        • `+don clan all`

        Aliases
        -----------
        • `+donations clan` (primary)
        • `+don clan`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        query = """SELECT player_tag, donations, received, user_id 
                        FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY donations DESC
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

        p = formatters.DonationsPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()


def setup(bot):
    bot.add_cog(Donations(bot))
