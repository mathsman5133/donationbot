import coc
import discord
import math

from discord.ext import commands
from cogs.donations import ArgConverter, ClanConverter, PlayerConverter
from cogs.utils import formatters


class EventsConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            to_fetch = int(argument)
        except ValueError:
            to_fetch = await ArgConverter().convert(ctx, argument)
        return to_fetch


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.group(invoke_without_command=True)
    async def events(self, ctx, *, arg: EventsConverter = None, mobile=False, limit=20):
        """Check recent donation events for a player, user, clan or guild.

        For a mobile-friendly table that is guaranteed to fit on a mobile screen,
        please use `+eventsmob`.

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
        if ctx.invoked_subcommand is not None:
            return

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

        # await ctx.send('This may take a while. Please be patient.')
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

        no_pages = math.ceil(len(results) / 20)
        title = f"Recent Events for {', '.join(n.name for n in clans)}"

        if mobile:
            p = formatters.MobilePaginator(ctx, results, page_count=no_pages, title=title)
        else:
            p = formatters.EventsPaginator(ctx, results, page_count=no_pages, title=title)

        await p.paginate()

    @events.command(name='user')
    async def events_user(self, ctx, user: discord.Member = None, mobile=False, limit=20):
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

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        query = "SELECT events.player_tag, events.donations, events.received, " \
                "events.time, events.clan_tag FROM events INNER JOIN players " \
                "ON events.player_tag = players.player_tag " \
                "WHERE players.user_id = $1 ORDER BY time DESC LIMIT $2;"
        fetch = await ctx.db.fetch(query, user.id, limit)
        title = f'Recent Events for {str(user)}'
        no_pages = math.ceil(len(fetch) / 20)

        if mobile:
            p = formatters.MobilePaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)
        else:
            p = formatters.EventsPaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)

        await p.paginate()

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
        query = "SELECT events.donations, events.received, " \
                "events.time, players.user_id, events.clan_tag " \
                "FROM events INNER JOIN players ON players.player_tag = events.player_tag " \
                "WHERE events.player_tag = $1 ORDER BY events.time DESC LIMIT $2"
        fetch = await ctx.db.fetch(query, player.tag, limit)
        if not fetch:
            return await ctx.send(
                'No accounts added/claimed. Please see `+help claim` or `+help aplayer`')

        title = f'Recent Events for {player.name}'

        no_pages = math.ceil(len(fetch) / 20)

        if mobile:
            p = formatters.MobilePaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)
        else:
            p = formatters.EventsPaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)
        await p.paginate()

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
        for n in clans:
            fetch = await ctx.db.fetch(query, n.tag, limit)
            results.extend(fetch)

        title = f"Recent Events for {', '.join(n.name for n in clans)}"
        no_pages = math.ceil(len(fetch) / 20)

        if mobile:
            p = formatters.MobilePaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)
        else:
            p = formatters.EventsPaginator(ctx, data=fetch, title=title,
                                           page_count=no_pages)
        await p.paginate()

    @commands.command(name='eventsmob', aliases=['mobevents', 'mevents', 'eventsm'])
    async def events_mobile(self, ctx, *, arg: EventsConverter = None, limit=20):
        """Get a mobile-friendly version of donation events/history.

        This command is identical in usage to `+events`.
        The only difference is the return of a mobile-friendly table.
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

        This command is similar in usage to `+events`.
        The only difference is you must specify the limit to fetch
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
        • `+eventslim #CLAN_TAG`
        • `+eventslim @mention`
        • `+eventslim #PLAYER_TAG`
        • `+eventslim player name`
        • `+eventslim all`
        • `+eventslim`
        """
        await ctx.invoke(self.events, arg=arg, limit=limit)


def setup(bot):
    bot.add_cog(Events(bot))
