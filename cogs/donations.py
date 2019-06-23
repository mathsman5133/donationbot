from discord.ext import commands
import coc
import discord
import re


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
                raise commands.BadArgument(f'You appear to be passing the clan tag for `{str(g)}`')

            member = g.get_member(name=argument)
            if member:
                return member  # finding don for clash player
            member_by_tag = g.get_member(tag=argument)
            if member_by_tag:
                return member_by_tag

        raise commands.BadArgument(f"Invalid tag or IGN in `{','.join(str(n) for n in guild_clans)}` clans.")


class ClanConverter(commands.Converter):
    async def convert(self, ctx, argument):
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
        if argument == 'all':
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

    @commands.group(name='donations')
    async def _donations(self, ctx, *, arg: ArgConverter):
        if ctx.invoked_subcommands is not None:
            return
        if isinstance(arg, discord.Member):
            await ctx.invoke(self._user, arg)
        if isinstance(arg, coc.BasicClan):
            await ctx.invoke(self._clan, [arg])
        if isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self._player, arg)
        if isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self._clan, arg)

    @_donations.command(name='user')
    async def _user(self, ctx, user: discord.Member=None):
        if not user:
            user = ctx.author

        query = "SELECT player_tag, donations, received FROM donations WHERE user_id = $1"
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

        e.description = table.render()
        await ctx.send(embed=e)

    @_donations.command(name='player')
    async def _player(self, ctx, player: PlayerConverter):
        query = "SELECT player_tag, donations, received, user_id FROM donations WHERE tag = $1"
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
    async def _clan(self, ctx, clans: ClanConverter):
        query = f"""SELECT ign, tag, donations, user_id FROM donations 
                WHERE clan_tag IN ({', '.join(n.tag for n in clans)})
                """
        fetch = await ctx.db.fetch(query)

        if not fetch:
            raise commands.BadArgument(f"No players claimed for clans `{f'{c.name} ({c.tag})' for c in clans}`")

        e = discord.Embed(colour=self.bot.colour)

        for n in fetch:
            n[3] = self.bot.get_user(n[3])

        table = TabularData()
        table.set_columns(['IGN', 'Tag', 'Donations', 'Claimed By'])
        table.add_rows(fetch)
        render = table.render()
        if len(render) > 2040:
            pass  # TODO: paginate

        e.description = f'```\n{table.render()}\n```'
        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(Donations(bot))
