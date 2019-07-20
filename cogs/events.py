import asyncio
import asyncpg
import coc
import discord
import logging
import math

from discord.ext import commands, tasks
from cogs.donations import ArgConverter, ClanConverter, PlayerConverter
from cogs.utils import formatters, checks, emoji_lookup
from cogs.utils.db_objects import DatabaseEvent

log = logging.getLogger(__name__)


class EventsConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            to_fetch = int(argument)
        except ValueError:
            to_fetch = await ArgConverter().convert(ctx, argument)
        return to_fetch


class Events(commands.Cog):
    """Find historical clan donation data for your clan, or setup logging and events.
    """
    def __init__(self, bot):
        self.bot = bot
        self._batch_data = []
        self._batch_lock = asyncio.Lock(loop=bot.loop)
        self.batch_insert_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.batch_insert_loop.start()
        self.bulk_report.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_report.start()

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @tasks.loop(seconds=60.0)
    async def batch_insert_loop(self):
        async with self._batch_lock:
            await self.bulk_insert()

    async def bulk_insert(self):
        query = """INSERT INTO events (player_tag, player_name, clan_tag, donations, received, time)
                        SELECT x.player_tag, x.clan_tag, x.donations, x.received, x.time
                           FROM jsonb_to_recordset($1::jsonb) 
                        AS x(player_tag TEXT, clan_tag TEXT, 
                             donations INTEGER, received INTEGER, time TIMESTAMP
                             )
                """

        if self._batch_data:
            await self.bot.pool.execute(query, self._batch_data)
            total = len(self._batch_data)
            if total > 1:
                log.info('Registered %s events to the database.', total)
            self._batch_data.clear()

    @tasks.loop(seconds=60.0)
    async def bulk_report(self):
        query = """SELECT DISTINCT clans.guild_id FROM clans 
                        INNER JOIN events 
                        ON clans.clan_tag = events.clan_tag
                        INNER JOIN guilds
                        ON guilds.guild_id = clans.guild_id 
                    WHERE events.clan_tag = ANY(
                                SELECT DISTINCT clan_tag FROM events WHERE reported=False
                                )
                    AND (CURRENT_TIMESTAMP - events.time) >= guilds.log_interval
                """
        fetch = await self.bot.pool.fetch(query)
        query = """SELECT * FROM events 
                        INNER JOIN clans 
                        ON clans.clan_tag = events.clan_tag 
                    WHERE clans.guild_id=$1 
                    AND events.reported=False
                    ORDER BY events.clan_tag, 
                             time DESC;
                """
        for n in fetch:
            guild_config = await self.bot.get_guild_config(n[0])
            events = [DatabaseEvent(bot=self.bot, record=n) for
                      n in await self.bot.pool.fetch(query, n[0])
                      ]
            # we just wanna load up + cache all players now for fast access later
            table = formatters.CLYTable()
            for x in events:
                emoji = emoji_lookup.misc['donated'] \
                    if x.donations else emoji_lookup.misc['received']
                table.add_row([
                    emoji,
                    x.donations if x.donations else x.received,
                    x.player_name,
                    await self.bot.donationboard.get_clan_name(n[0], x.clan_tag)
                ]
                )
            split = table.render_events_log().split('\n')
            new_table_renders = []
            for i in range(math.ceil(len(split) / 21)):
                new_table_renders.append(split[i*21:(i+1)*21])

            fmt = f"Recent Events{f' for {guild_config.donationboard_title}' if guild_config.donationboard_title else ''}\n"
            for x in new_table_renders:
                fmt += '\n'.join(x)
                fmt += f"\nKey: {emoji_lookup.misc['donated']} - Donated," \
                    f" {emoji_lookup.misc['received']} - Received," \
                    f" {emoji_lookup.misc['number']} - Number of troops."
                await self.bot.log_info(n[0], fmt)

        query = """UPDATE events
                        SET reported=True
                    FROM (SELECT clans.clan_tag FROM clans WHERE guild_id=ANY($1::BIGINT[])) AS x
                WHERE events.clan_tag=x.clan_tag
                """
        await self.bot.pool.execute(query, [n[0] for n in fetch])
        log.info('Reported donations for %s guilds', len(fetch))

    @commands.group(invoke_without_subcommand=True)
    @checks.manage_guild()
    async def log(self, ctx):
        """Manage the donation log for the server.

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @log.command(name='interval')
    async def log_interval(self, ctx, minutes: int = 1):
        """Update the interval (in minutes) for which the bot will log your donations.

        Parameters
        ----------------
        Pass in any of the following:

            • Minutes: the number of minutes between logs. Defaults to 1.

        Example
        -----------
        • `+log interval 2`
        • `+log interval 1440`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        query = """"UPDATE guilds SET log_interval = ($1 ||' minutes')::interval
                        WHERE guild_id=$2"""
        await ctx.db.execute(query, minutes, ctx.guild.id)
        await ctx.confirm()
        await ctx.send(f'Set log interval to {minutes}minutes.')

    @log.command(name='create')
    async def log_create(self, ctx, channel: discord.TextChannel = None):
        """Create a donation log for your server.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord channel: #channel or a channel id. This defaults to the channel you are in.

        Example
        -----------
        • `+log create #CHANNEL`
        • `+log create CHANNEL_ID`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not channel:
            channel = ctx.channel
        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(
                ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        query = "UPDATE guilds SET log_channel_id=$1, log_toggle=True WHERE guild_id=$2"
        await ctx.db.execute(query, channel.id, ctx.guild.id)
        await ctx.send(f'Events log channel has been set to {channel.mention}, '
                       f'and logging is enabled.')
        await ctx.confirm()

    @log.command(name='toggle')
    async def log_toggle(self, ctx, toggle: bool = True):
        """Toggle the donation log on/off for your server.

        Parameters
        ----------------
        Pass in any of the following:

            • A toggle - `True` or `False`

        Example
        -----------
        • `+log toggle True`
        • `+log toggle False`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        query = "UPDATE guilds SET log_toggle=$1 WHERE guild_id=$2"
        await ctx.db.execute(query, toggle, ctx.guild.id)
        await ctx.send(f'Events logging has been {"enabled" if toggle else "disabled"}.')
        await ctx.confirm()

    @commands.group(invoke_without_command=True)
    async def events(self, ctx, *, arg: EventsConverter = None, limit=20):
        """Check recent donation events for a player, user, clan or guild.

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
            await ctx.invoke(self.events_recent, limit=arg)
        elif isinstance(arg, coc.Player):
            await ctx.invoke(self.events_player, player=arg, limit=limit)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.events_user, user=arg, limit=limit)
        elif isinstance(arg, coc.Clan):
            await ctx.invoke(self.events_clan, clan=[arg], limit=limit)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.events_clan, clans=arg, limit=limit)

    @events.command(name='recent')
    async def events_recent(self, ctx, limit: int = None):
        query = """SELECT player_tag, donations, received, time
                    FROM events
                            INNER JOIN clans
                            ON clans.clan_tag = events.clan_tag
                            INNER JOIN guilds
                            ON guilds.guild_id = clans.guild_id
                    WHERE events.clan_tag = ANY(
                                SELECT DISTINCT clan_tag FROM clans
                                WHERE guild_id=$1
                                )
                    ORDER BY events.time DESC
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, ctx.guild.id, limit)
        if not fetch:
            return await ctx.send('No events found. Please ensure you have '
                                  'enabled logging and have claimed a clan.')

        no_pages = math.ceil(len(fetch) / 20)
        title = f"Recent Events for Guild {ctx.guild.name}"

        p = formatters.EventsPaginator(ctx, fetch, page_count=no_pages, title=title)
        await p.paginate()

    @events.command(name='user')
    async def events_user(self, ctx, user: discord.Member = None, limit=20):
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

        query = """SELECT events.player_tag, events.donations, events.received, events.time 
                    FROM events 
                        INNER JOIN players
                        ON events.player_tag = players.player_tag 
                    WHERE players.user_id = $1 
                    ORDER BY time DESC 
                    LIMIT $2;
                """
        fetch = await ctx.db.fetch(query, user.id, limit)
        title = f'Recent Events for {str(user)}'
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @events.command(name='player')
    async def events_player(self, ctx, *, player: PlayerConverter, limit=20):
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
        query = """SELECT events.player_tag, events.donations, events.received, events.time
                    FROM events 
                        INNER JOIN players 
                        ON players.player_tag = events.player_tag 
                    WHERE events.player_tag = $1 
                    ORDER BY events.time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, player.tag, limit)
        if not fetch:
            return await ctx.send('Account has not been added/claimed.')

        title = f'Recent Events for {player.name}'

        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @events.command(name='clan')
    async def events_clan(self, ctx, *, clans: ClanConverter, limit=20):
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

        query = """SELECT player_tag, donations, received, time 
                        FROM events
                    WHERE clan_tag = ANY($1::TEXT[])
                    ORDER BY time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, [n.tag for n in clans], limit)
        if not fetch:
            return await ctx.send('No events found.')

        title = f"Recent Events for {', '.join(n.name for n in clans)}"
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @commands.command(name='eventslim')
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
