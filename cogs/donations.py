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
    async def donations(self, ctx, *, arg: ArgConverter = None, mobile=False):
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
            • None passed will divert to donations for your discord account

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
            await ctx.invoke(self.donations_user, ctx.author, mobile=mobile)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.donations_user, arg)
        elif isinstance(arg, coc.BasicClan):
            await ctx.invoke(self.donations_clan, clans=[arg], mobile=mobile)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.donations_player, player=arg, mobile=mobile)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.donations_clan, clans=arg, mobile=mobile)

    @donations.command(name='user')
    async def donations_user(self, ctx, user: discord.Member = None, mobile=False):
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

        query = "SELECT player_tag, donations, received FROM players WHERE user_id = $1"
        fetch = await ctx.db.fetch(query, user.id)
        if not fetch:
            return await ctx.send(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                  f"have any accounts claimed")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {str(user)}'

        if mobile:
            p = formatters.MobilePaginator(ctx, data=fetch, page_count=page_count, title=title)
            p.embed.set_author(name=str(user), icon_url=user.avatar_url)
        else:
            p = formatters.DonationsPaginator(ctx, data=fetch, page_count=page_count, title=title)

        await p.paginate()

    @donations.command(name='player')
    async def donations_player(self, ctx, *, player: PlayerConverter, mobile=False):
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

        query = "SELECT player_tag, donations, received, user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)

        if not fetch:
            raise commands.BadArgument(f"{str(player)} ({player.tag}) has not been claimed.")

        page_count = math.ceil(len(fetch) / 20)
        title = f'Donations for {player.name}'

        if mobile:
            p = formatters.MobilePaginator(ctx, data=fetch, title=title, page_count=page_count)
        else:
            p = formatters.DonationsPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

    @donations.command(name='clan')
    async def donations_clan(self, ctx, *, clans: ClanConverter, mobile=False):
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
        query = f"SELECT player_tag, donations, received, user_id " \
                f"FROM players WHERE player_tag  = $1"

        data = []
        for n in clans:
            for player in n.members:
                fetch = await ctx.db.fetchrow(query, player.tag)
                if fetch:
                    data.append(fetch)

        if not data:
            return await ctx.send(f"No players claimed for clans "
                                  f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`"
                                  )

        data.sort(key=lambda m: m[1], reverse=True)
        print(data)

        page_count = math.ceil(len(data) / 20)
        title = f"Donations for {', '.join(f'{c.name}' for c in clans)}"

        if mobile:
            p = formatters.MobilePaginator(ctx, data=data, title=title, page_count=page_count)
        else:
            p = formatters.DonationsPaginator(ctx, data=data, title=title, page_count=page_count)

        await p.paginate()

    @commands.command(name='donmobile', aliases=['donmob', 'mobdon', 'mdon', 'donm'])
    async def donations_mobile(self, ctx, *, arg: ArgConverter=None):
        """Get a mobile-friendly version of donations.

        This command is identical in usage to `+don`. The only difference is the return of a mobile-friendly table.
        For a complete table with #PLAYER_TAG and Claimed By columns, please use `+don`.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (clan must be claimed to the server)
            • A discord @mention, user#discrim or user id
            • A player tag
            • A player name (must be in clan claimed to server)
            • `all`, `server`, `guild` for all clans in guild
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+donmobile #CLAN_TAG`
        • `+donmob @mention`
        • `+mdon #PLAYER_TAG`
        • `+donm player name`
        • `+donmobile all`
        • `+mobdon`

        Aliases
        -----------
        • `+donmobile` (primary)
        • `+donmob`
        • `+mobdon`
        • `+mdon`
        • `+donm`
        """
        await ctx.invoke(self.donations, arg=arg, mobile=True)


def setup(bot):
    bot.add_cog(Donations(bot))
