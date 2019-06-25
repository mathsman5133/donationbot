from discord.ext import commands
import coc
import discord
import re
import math
from cogs.utils import paginator
tag_validator = re.compile("(?P<tag>^\s*#?[PYLQGRJCUV0289]+\s*$)")


class TabularData:
    def __init__(self):
        self._widths = []
        self._columns = []
        self._rows = []

    def set_columns(self, columns):
        self._columns = columns
        self._widths = [len(c) + 2 for c in columns]

    def add_row(self, row):
        rows = [str(r) for r in row]
        self._rows.append(rows)
        for index, element in enumerate(rows):
            width = len(element) + 2
            if width > self._widths[index]:
                self._widths[index] = width

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def render(self):
        """Renders a table in rST format.
        Example:
        +-------+-----+
        | Name  | Age |
        +-------+-----+
        | Alice | 24  |
        |  Bob  | 19  |
        +-------+-----+
        """

        sep = '+'.join('-' * w for w in self._widths)
        sep = f'+{sep}+'

        to_draw = [sep]

        def get_entry(d):
            elem = '|'.join(f'{e:^{self._widths[i]}}' for i, e in enumerate(d))
            return f'|{elem}|'

        to_draw.append(get_entry(self._columns))
        to_draw.append(sep)

        for row in self._rows:
            to_draw.append(get_entry(row))

        to_draw.append(sep)
        return '\n'.join(to_draw)


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
                raise commands.BadArgument(f'You appear to be passing the clan tag/name for `{str(g)}`')

            member = g.get_member(name=argument)
            if member:
                return member  # finding don for clash player
            member_by_tag = g.get_member(tag=argument)
            if member_by_tag:
                return member_by_tag

        raise commands.BadArgument(f"Invalid tag or IGN in `{','.join(str(n) for n in guild_clans)}` clans.")


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
            return await commands.MemberConverter().convert(ctx, argument)  # finding don for a discord member
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
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.group(name='donations', aliases=['don'])
    async def _donations(self, ctx, *, arg: ArgConverter=None):
        """Check donations for a player, user, clan or guild.

        Parameters
        -----------
        Pass in any of the following:

            • A clan tag
            • A clan name (clan must be claimed to the server)
            • A discord @mention, user#discrim or user id
            • A player tag
            • A player name (must be in clan claimed to server)
            • `all`, `server`, `guild` for all clans in guild
            • None passed will divert to donations for your discord account

        Example
        ---------
        • `+donations #CLAN_TAG`
        • `+donations @mention`
        • `+don #PLAYER_TAG`
        • `+don player name`
        • `+don all`
        • `+don`

        Aliases
        --------
        • `+donations` (primary)
        • `+don`

        Group Commands
        ---------------
        • `+donations clan`
        • `+donations player`
        • `+donations user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if ctx.invoked_subcommand is not None:
            print('1')
            return
        if not arg:
            await ctx.invoke(self._user, ctx.author)
        if isinstance(arg, discord.Member):
            print('2')
            await ctx.invoke(self._user, arg)
        if isinstance(arg, coc.BasicClan):
            await ctx.invoke(self._clan, clans=[arg])
        if isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self._player, player=arg)
        if isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self._clan, clans=arg)

    @_donations.command(name='user')
    async def _user(self, ctx, user: discord.Member=None):
        """Get donations for a discord user.

        Parameters
        -----------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to donations for your discord account

        Example
        ---------
        • `+donations user @mention`
        • `+don user USER_ID`
        • `+don user`

        Aliases
        --------
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
            raise commands.BadArgument(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                       f"have any accounts claimed")

        e = discord.Embed(colour=self.bot.colour)
        e.set_author(name=str(user), icon_url=user.avatar_url)

        final = []
        for n in fetch:
            player = await self.bot.coc.get_player(n[0])
            final.append([player.name, player.tag, n[1], n[2]])

        table = TabularData()
        table.set_columns(['IGN', 'Tag', 'Don', "Rec'd"])
        table.add_rows(final)
        e.description = f'```\n{table.render()}\n```'
        await ctx.send(embed=e)

    @_donations.command(name='player')
    async def _player(self, ctx, *, player: PlayerConverter):
        """Get donations for a player.

        Parameters
        -----------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ---------
        • `+donations player #PLAYER_TAG`
        • `+don player player name`

        Aliases
        --------
        • `+donations player` (primary)
        • `+don player`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """

        query = "SELECT player_tag, donations, received, user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)

        if not fetch:
            raise commands.BadArgument(f"{str(player)} ({player.tag}) has not been claimed.")

        user = self.bot.get_user(fetch[3])
        player = await self.bot.coc.get_player(fetch[0])
        final = [player.name, player.tag, fetch[1], fetch[2], str(user)]

        e = discord.Embed(colour=self.bot.colour)
        e.set_author(name=str(user), icon_url=user.avatar_url)

        table = TabularData()
        table.set_columns(['IGN', 'Tag', 'Don', "Rec'd", 'Claimed By'])
        table.add_row(final)

        e.description = table.render()
        await ctx.send(embed=e)

    @_donations.command(name='clan')
    async def _clan(self, ctx, *, clans: ClanConverter):
        """Get donations for a clan.

        Parameters
        -----------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ---------
        • `+donations clan #CLAN_TAG`
        • `+don clan clan name`
        • `+don clan all`

        Aliases
        --------
        • `+donations clan` (primary)
        • `+don clan`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """

        query = f"SELECT player_tag, donations, received, user_id FROM players WHERE player_tag  = $1"

        players = []
        for n in clans:
            players.extend(x for x in n.members)

        final = []

        async for player in ctx.coc.get_players(n.tag for n in players):
            fetch = await ctx.db.fetchrow(query, player.tag)
            if fetch:
                final.append([player.name, fetch[1], fetch[2], player.tag])

        if not final:
            raise commands.BadArgument(f"No players claimed for clans "
                                       f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`")

        final.sort(key=lambda m: m[1], reverse=True)

        messages = math.ceil(len(final) / 20)
        entries = []

        for i in range(messages):

            results = final[i*20:(i+1)*20]

            table = TabularData()
            table.set_columns(['IGN', 'Don', "Rec'd", 'Tag'])
            table.add_rows(results)

            entries.append(f'```\n{table.render()}\n```')

        p = paginator.Pages(ctx, entries=entries, per_page=1)
        p.embed.colour = self.bot.colour
        p.embed.title = f"Donations for {', '.join(f'{c.name}' for c in clans)}"

        await p.paginate()


def setup(bot):
    bot.add_cog(Donations(bot))
