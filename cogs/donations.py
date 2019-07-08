from discord.ext import commands
import coc
import discord
from datetime import datetime
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


class EventsConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            to_fetch = int(argument)
        except ValueError:
            to_fetch = await ArgConverter().convert(ctx, argument)
        return to_fetch


class Donations(commands.Cog):
    """All commands related to donations of clans, players, users and servers."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.group(name='donations', aliases=['don'],  invoke_without_command=True)
    async def donations(self, ctx, *, arg: ArgConverter=None, mobile=False):
        """Check donations for a player, user, clan or guild.

        For a mobile-friendly table that is guaranteed to fit on a mobile screen, please use `+donmob`.

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
        print(arg)
        if ctx.invoked_subcommand is not None:
            return
        if not arg:
            await ctx.invoke(self.donations_user, ctx.author, mobile=mobile)
        if isinstance(arg, discord.Member):
            await ctx.invoke(self.donations_user, arg)
        if isinstance(arg, coc.BasicClan):
            await ctx.invoke(self.donations_clan, clans=[arg], mobile=mobile)
        if isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.donations_player, player=arg, mobile=mobile)
        if isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.donations_clan, clans=arg, mobile=mobile)

    @donations.command(name='user')
    async def donations_user(self, ctx, user: discord.Member=None, mobile=False):
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
            raise commands.BadArgument(f"{'You dont' if ctx.author == user else f'{str(user)} doesnt'} "
                                       f"have any accounts claimed")

        e = discord.Embed(colour=self.bot.colour)
        e.set_author(name=str(user), icon_url=user.avatar_url)

        final = []
        for n in fetch:
            player = await self.bot.coc.get_player(n[0])
            if mobile:
                final.append([player.name, n[1], n[2]])
            else:
                final.append([player.name, player.tag, n[1], n[2]])

        table = TabularData()
        if mobile:
            table.set_columns(['IGN', 'Don', "Rec'd"])
        else:
            table.set_columns(['IGN', 'Tag', 'Don', "Rec'd"])
        table.add_rows(final)
        e.description = f'```\n{table.render()}\n```'
        await ctx.send(embed=e)

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

        user = self.bot.get_user(fetch[3])
        player = await self.bot.coc.get_player(fetch[0])
        if mobile:
            final = [player.name, fetch[1], fetch[2]]
        else:
            final = [player.name, player.tag, fetch[1], fetch[2], str(user)]

        e = discord.Embed(colour=self.bot.colour)
        if user:
            e.set_author(name=str(user), icon_url=user.avatar_url)

        table = TabularData()
        if mobile:
            table.set_columns(['IGN', 'Don', "Rec'd"])
        else:
            table.set_columns(['IGN', 'Tag', 'Don', "Rec'd", 'Claimed By'])
        table.add_row(final)

        await ctx.send(f'```\n{table.render()}\n```')

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
        query = f"SELECT player_tag, donations, received, user_id FROM players WHERE player_tag  = $1"

        players = []
        for n in clans:
            players.extend(x for x in n.members)

        final = []

        async for player in ctx.coc.get_players(n.tag for n in players):
            fetch = await ctx.db.fetchrow(query, player.tag)
            if fetch:
                if mobile:
                    final.append([player.name, fetch[1], fetch[2]])
                else:
                    name = str(self.bot.get_user(fetch[3]))
                    if len(name) > 20:
                        name = name[:20] + '..'
                    final.append([player.name, fetch[1], fetch[2], player.tag, name])

        if not final:
            raise commands.BadArgument(f"No players claimed for clans "
                                       f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`")

        final.sort(key=lambda m: m[1], reverse=True)

        messages = math.ceil(len(final) / 20)
        entries = []

        for i in range(int(messages)):

            results = final[i*20:(i+1)*20]

            table = TabularData()
            if mobile:
                table.set_columns(['IGN', 'Don', "Rec'd"])
            else:
                table.set_columns(['IGN', 'Don', "Rec'd", 'Tag', 'Claimed By'])
            table.add_rows(results)

            entries.append(f'```\n{table.render()}\n```')

        p = paginator.MessagePaginator(ctx, entries=entries, per_page=1,
                                       title=f"Donations for {', '.join(f'{c.name}' for c in clans)}")

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

    @staticmethod
    def _readable_time(delta_seconds):
        hours, remainder = divmod(int(delta_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if days:
            fmt = '{d}d {h}h {m}m {s}s ago'
        elif hours:
            fmt = '{h}h {m}m {s}s ago'
        else:
            fmt = '{m}m {s}s ago'

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.group()
    async def events(self, ctx, *, arg: EventsConverter = None, mobile=False, limit=20):
        """Check recent donation events for a player, user, clan or guild.

        For a mobile-friendly table that is guaranteed to fit on a mobile screen, please use `+eventsmob`.

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
        • `+events #CLAN_TAG`
        • `+events @mention`
        • `+events #PLAYER_TAG`
        • `+events player name`
        • `+events all`
        • `+events`
        """
        if not arg:
            arg = 20

        if isinstance(arg, int):
            await ctx.invoke(self.events_recent, number=arg, mobile=mobile)
        elif isinstance(arg, coc.Player):
            await ctx.invoke(self.events_player, player=arg, mobile=mobile, limit=limit)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.events_user, user=arg, mobile=mobile, limit=limit)
        elif isinstance(arg, coc.Clan):
            await ctx.invoke(self.events_clan, clan=[arg], mobile=mobile, limit=limit)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.events_clan, clans=arg, mobile=mobile, limit=limit)

    @events.command(name='recent')
    async def events_recent(self, ctx, number: int = None, mobile: bool = False):
        clans = await self.bot.get_clans(ctx.guild.id)
        if not clans:
            return await ctx.send('You have not claimed any clans. See `+help aclan`.')

        players = []
        for n in clans:
            players.extend(x for x in n.members)

        query = f"SELECT player_tag, donations, received, time, clan_tag FROM events " \
                f"WHERE clan_tag = $1 ORDER BY time DESC LIMIT $2"
        results = []

        for n in clans:
            fetch = await ctx.db.fetch(query, n.tag, number)
            results.extend(fetch)

        if not results:
            return await ctx.send('Your clan doesn\'t have any events recorded yet.')

        no_entries = math.ceil(len(results) / 20)
        entries = []
        time = datetime.utcnow()

        for i in range(int(no_entries)):
            table = TabularData()
            if mobile:
                table.set_columns(['IGN', 'Don', "Rec'd"])
            else:
                table.set_columns(['IGN', 'Don', "Rec'd", 'Time', 'Clan'])

            data = results[i*20:(i+1)*20]

            for n in data:
                player = discord.utils.get(players, tag=n[0])
                if not player:
                    player = await self.bot.coc.get_player(n[0])
                    print('fetch')
                else:
                    print('ok')

                delta = time - n[3]
                if mobile:
                    table.add_row([player.name, n[1], n[2]])
                else:
                    clan = await self.bot.coc.get_clan(n[4])
                    table.add_row([player.name, n[1], n[2],
                                   self._readable_time(delta.total_seconds()), clan.name])

            if mobile:
                entries.append(f'```\n{table.render()}\n```')
            else:
                entries.append(f"Recent Events for {', '.join(n.name for n in clans)}\n"
                               f"```\n{table.render()}\n```")

        if mobile:
            p = paginator.Pages(ctx, entries=entries, per_page=1)
            p.embed.colour = self.bot.colour
            p.embed.title = f"Recent Events for {', '.join(f'{n.name} ({n.tag})' for n in clans)}"
        else:
            p = paginator.MessagePaginator(ctx, entries=entries, per_page=1)

        await p.paginate()

    @events.command(name='user')
    async def events_user(self, ctx, user: discord.Member=None, mobile=False, limit=20):
        """Get donation history/events for a discord user.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+events user @mention`
        • `+events user USER_ID`
        • `+events user`

        Aliases
        -----------
        • `+events user` (primary)
        • `+don user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        query = "SELECT events.player_tag, events.donations, events.received, events.time, events.clan_tag " \
                "FROM events INNER JOIN players ON events.player_tag = players.player_tag " \
                "WHERE players.user_id = $1 ORDER BY time DESC LIMIT $2;"
        fetch = await ctx.db.fetch(query, user.id, limit)

        time = datetime.utcnow()
        table = TabularData()
        if mobile:
            table.set_columns(['IGN', 'Don', "Rec'd"])
        else:
            table.set_columns(['IGN', 'Don', "Rec'd", 'Time', 'Clan'])

        for n in fetch:
            player = await self.bot.coc.get_player(n[0])
            clan = await self.bot.coc.get_clan(n[4])
            if mobile:
                table.add_row([player.name, n[1], n[2]])
            else:
                table.add_row([player.name, n[1], n[2], self._readable_time((time - n[3]).total_seconds()), clan.name])

        fmt = f'```\n{table.render()}\n```'
        if mobile:
            e = discord.Embed(colour=self.bot.colour,
                              description=f'Recent Events\n{fmt}',
                              )
            e.set_author(name=str(user), icon_url=user.avatar_url)
            await ctx.send(embed=e)
        else:
            await ctx.send(f'Recent Events for {str(user)}\n{fmt}')

    @events.command(name='player')
    async def events_player(self, ctx, *, player: PlayerConverter, mobile=False, limit=20):
        """Get donation history/events for a player.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ------------
        • `+events player #PLAYER_TAG`
        • `+events player player name`

        Aliases
        -----------
        • `+events player` (primary)
        • `+events player`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        query = "SELECT events.donations, events.received, events.time, players.user_id, events.clan_tag " \
                "FROM events INNER JOIN players ON players.player_tag = events.player_tag " \
                "WHERE events.player_tag = $1 ORDER BY events.time DESC LIMIT $2"
        fetch = await ctx.db.fetch(query, player.tag, limit)
        if not fetch:
            return await ctx.send('No accounts added/claimed. Please see `+help claim` or `+help aplayer`')

        time = datetime.utcnow()
        table = TabularData()
        if mobile:
            table.set_columns(['IGN', 'Don', "Rec'd"])
        else:
            table.set_columns(['IGN', 'Don', "Rec'd", 'Time', 'Clan'])

        for n in fetch:
            if mobile:
                table.add_row([player.name, n[1], n[2]])
            else:
                clan = await self.bot.coc.get_clan(n[4])
                table.add_row([player.name, n[1], n[2], self._readable_time((time - n[3]).total_seconds()), clan.name])

        fmt = f'```\n{table.render()}\n```'
        if mobile:
            e = discord.Embed(colour=self.bot.colour,
                              description=f'Recent Events for {player.name}\n{fmt}',
                              )
            user = ctx.guild.get_member(fetch[4])
            if user:
                e.set_author(name=str(user), icon_url=user.avatar_url)

            return await ctx.send(embed=e)
        else:
            return await ctx.send(f'Recent Events for {player.name}\n{fmt}')

    @events.command(name='clan')
    async def events_clan(self, ctx, *, clans: ClanConverter, mobile=False, limit=20):
        """Get donation history/events for a clan.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ------------
        • `+events clan #CLAN_TAG`
        • `+events clan clan name`
        • `+events clan all`

        Aliases
        -----------
        • `+events clan` (primary)
        • `+events clan`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """

        query = f"SELECT player_tag, donations, received, time, clan_tag FROM events " \
                f"WHERE clan_tag = $1 " \
                f"ORDER BY time DESC LIMIT $2"
        results = []
        players = []
        for n in clans:
            fetch = await ctx.db.fetch(query, n.tag, limit)
            results.extend(fetch)
            players.extend(x for x in n.members)

        time = datetime.utcnow()
        table = TabularData()
        if mobile:
            table.set_columns(['IGN', 'Don', "Rec'd"])
        else:
            table.set_columns(['IGN', 'Don', "Rec'd", 'Time', 'Clan'])

        for n in results:
            player = discord.utils.get(players, tag=n[0])
            if not player:
                player = await self.bot.coc.get_player(n[0])

            if mobile:
                table.add_row([player.name, n[1], n[2]])
            else:
                clan = await self.bot.coc.get_clan(n[4])
                table.add_row([player.name, n[1], n[2], self._readable_time((time - n[3]).total_seconds()), clan.name])

        fmt = f"Recent Events for {', '.join(n.name for n in clans)}\n```\n{table.render()}\n```"
        if mobile:
            e = discord.Embed(colour=self.bot.colour,
                              description=fmt,
                              )
            await ctx.send(embed=e)
        else:
            await ctx.send(fmt)

    @commands.command(name='eventsmob', aliases=['mobevents', 'mevents', 'eventsm'])
    async def events_mobile(self, ctx, *, arg: EventsConverter = None, limit=20):
        """Get a mobile-friendly version of donation events/history.

        This command is identical in usage to `+events`. The only difference is the return of a mobile-friendly table.
        For a complete table with time and clan name columns, please use `+events`.

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
        • `+eventsmob #CLAN_TAG`
        • `+mobevents @mention`
        • `+mevents #PLAYER_TAG`
        • `+eventsm player name`
        • `+eventsmob all`
        • `+mobevents`

        Aliases
        -----------
        • `+eventsmob` (primary)
        • `+mobevents`
        • `+mevents`
        • `+eventsm`
        """
        await ctx.invoke(self.events, arg=arg, limit=limit, mobile=True)

    @commands.command(name='eventslim', hidden=True)
    async def events_limit(self, ctx, limit: int = 20, *, arg: EventsConverter = None):
        """Get a specific limit of donation events/history.

        This command is similar in usage to `+events`. The only difference is you must specify the limit to fetch
        before your clan/player/user argument.

        Parameters
        ----------------
        Pass in any of the following, in this order:
            • First: limit: `1`, `2`, `5`, `50` etc.

            • Then:
            • A clan tag
            • A clan name (clan must be claimed to the server)
            • A discord @mention, user#discrim or user id
            • A player tag
            • A player name (must be in clan claimed to server)
            • `all`, `server`, `guild` for all clans in guild
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+eventsmob #CLAN_TAG`
        • `+mobevents @mention`
        • `+mevents #PLAYER_TAG`
        • `+eventsm player name`
        • `+eventsmob all`
        • `+mobevents`

        Aliases
        -----------
        • `+eventsmob` (primary)
        • `+mobevents`
        • `+mevents`
        • `+eventsm`
        """
        await ctx.invoke(self.events, arg=arg, limit=limit)


def setup(bot):
    bot.add_cog(Donations(bot))
