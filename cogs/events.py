import coc
import discord
import logging
import math
import typing

from discord.ext import commands
from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils import formatters, checks
from cogs.utils.db_objects import DatabaseClan

log = logging.getLogger(__name__)


class Events(commands.Cog):
    """Find historical clan donation data for your clan, or setup logging and events.
    """
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.group(invoke_without_subcommand=True)
    @checks.manage_guild()
    async def log(self, ctx):
        """Manage the donation log for the server.

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @log.command(name='info')
    async def log_info(self, ctx, *, channel: discord.TextChannel = None):
        """Get information about log channels for the guild.

        Parameters
        ----------------
            • Channel: Optional, the channel to get log info for.
                       Defaults to all channels in the server.

        Example
        -----------
        • `+log info #channel`
        • `+log info`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if channel:
            query = """SELECT clan_tag, channel_id, log_toggle, 
                              log_interval, clan_name 
                       FROM clans 
                       WHERE channel_id=$1
                    """
            fetch = await ctx.db.fetch(query, channel.id)
        else:
            query = """SELECT clan_tag, channel_id, log_toggle, 
                              log_interval, clan_name 
                       FROM clans 
                       WHERE guild_id=$1
                    """
            fetch = await ctx.db.fetch(query, ctx.guild.id)

        if channel:
            fmt = channel.mention
        else:
            fmt = ctx.guild.name

        e = discord.Embed(color=self.bot.colour,
                          description=f'Log info for {fmt}')

        for n in fetch:
            config = DatabaseClan(bot=self.bot, record=n)
            fmt = f"Tag: {config.clan_tag}\n"
            fmt += f"Channel: {config.channel.mention if config.channel else 'None'}\n"
            fmt += f"Log Toggle: {'enabled' if config.log_toggle else 'disabled'}\n"
            fmt += f"Log Interval: {config.interval_seconds} seconds\n"
            e.add_field(name=n['clan_name'],
                        value=fmt)
        await ctx.send(embed=e)

    @log.command(name='interval')
    async def log_interval(self, ctx, channel: typing.Optional[discord.TextChannel] = None,
                           minutes: int = 1):
        """Update the interval (in minutes) for which the bot will log your donations.

        Parameters
        ----------------
            • Channel: Optional, the channel to change log interval for.
                       Defaults to the one you're in.
            • Minutes: the number of minutes between logs. Defaults to 1.

        Example
        -----------
        • `+log interval #channel 2`
        • `+log interval 1440`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not channel:
            channel = ctx.channel

        query = """UPDATE clans SET log_interval = ($1 ||' minutes')::interval
                    WHERE channel_id=$2
                    RETURNING clan_name
                """
        fetch = await ctx.db.fetch(query, str(minutes), channel.id)

        if not fetch:
            return await ctx.send('Please add a clan.')

        await ctx.confirm()
        fmt = '\n'.join(n[0] for n in fetch)
        await ctx.send(f'Set log interval to {minutes} minutes for {fmt}.')
        self.bot.utils.invalidate_channel_configs(channel.id)

    @log.command(name='create')
    async def log_create(self, ctx, channel: typing.Optional[discord.TextChannel] = None, *,
                         clan: ClanConverter):
        """Create a donation log for your server.

        Parameters
        ----------------

            • Channel: #channel or a channel id. This defaults to the channel you are in.
            • Clan: clan tag or name to set logs for.

        Example
        -----------
        • `+log create #CHANNEL #P0LYJC8C`
        • `+log create #P0LYJC8C`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not channel:
            channel = ctx.channel
        guild_config = await self.bot.donationboard.get_guild_config(ctx.guild.id)
        if guild_config.donationboard == ctx.channel:
            return await ctx.send('You can\'t have the same channel for the donationboard and log channel!')
        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(
                ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        query = "UPDATE clans SET channel_id=$1, log_toggle=True WHERE clan_tag=$2 AND guild_id=$3"
        await ctx.db.execute(query, channel.id, clan[0].tag, ctx.guild.id)
        await ctx.send(f'Events log channel has been set to {channel.mention} for {clan[0].name} '
                       f'and logging is enabled.')
        await ctx.confirm()
        self.bot.utils.invalidate_channel_configs(channel.id)

    @log.command(name='toggle')
    async def log_toggle(self, ctx, channel: discord.TextChannel = None):
        """Toggle the donation log on/off for your server.

        Parameters
        ----------------
        Pass in any of the following:

            • Channel: #channel or a channel id. This defaults to the channel you are in.

        Example
        -----------
        • `+log toggle #CHANNEL`
        • `+log toggle`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not channel:
            channel = ctx.channel
        config = await self.bot.utils.get_channel_config(channel.id)
        if not config:
            return await ctx.send('Please setup a log channel with `+help log create` first.')

        toggle = not config.log_toggle  # false if true else false - opposite to what it is now.

        query = "UPDATE clans SET log_toggle=$1 WHERE channel_id=$2 RETURNING clan_name"
        fetch = await ctx.db.fetch(query, toggle, channel.id)

        if not fetch:
            return await ctx.send('Please add a clan.')

        fmt = '\n'.join(n[0] for n in fetch)
        await ctx.send(f'Events logging has been {"enabled" if toggle else "disabled"} for {fmt}')
        await ctx.confirm()
        self.bot.utils.invalidate_channel_configs(channel.id)

    @commands.group(invoke_without_command=True)
    async def events(self, ctx, limit: typing.Optional[int] = 20, *,
                     arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """Check recent donation events for a player, user, clan or guild.

        Parameters
        ----------------
        • Optional: Pass in a limit (number of events) to get. Defaults to 20.

        Then pass in any of the following:

            • A clan tag
            • A clan name (clan must be claimed to the server)
            • A discord @mention, user#discrim or user id
            • A player tag
            • A player name (must be in clan claimed to server)
            • `all`, `server`, `guild` for all clans in guild
            • None passed will divert to donations for your discord account

        Example
        -----------
        • `+events 20 #CLAN_TAG`
        • `+events @mention`
        • `+events #PLAYER_TAG`
        • `+events player name`
        • `+events 1000 all`
        • `+events`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = limit

        if isinstance(arg, int):
            await ctx.invoke(self.events_recent, limit=arg)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.events_player, player=arg, limit=limit)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.events_user, user=arg, limit=limit)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.events_clan, clans=arg, limit=limit)

    @events.command(name='recent', hidden=True)
    async def events_recent(self, ctx, limit: int = None):
        query = """SELECT player_tag, donations, received, time, player_name
                    FROM events
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

    @events.command(name='user', hidden=True)
    async def events_user(self, ctx, limit: typing.Optional[int] = 20, *,
                          user: discord.Member = None):
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

        query = """SELECT events.player_tag, events.donations, events.received, events.time, events.player_name
                    FROM events 
                        INNER JOIN players
                        ON events.player_tag = players.player_tag 
                    WHERE players.user_id = $1 
                    ORDER BY time DESC 
                    LIMIT $2;
                """
        fetch = await ctx.db.fetch(query, user.id, limit)
        if not fetch:
            return await ctx.send(f'No events found.')

        title = f'Recent Events for {str(user)}'
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @events.command(name='player', hidden=True)
    async def events_player(self, ctx, limit: typing.Optional[int] = 20,
                            *, player: PlayerConverter):
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
        query = """SELECT player_tag, donations, received, time, player_name
                    FROM events 
                    WHERE player_tag = $1 
                    ORDER BY time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, player.tag, limit)
        if not fetch:
            return await ctx.send('Account has not been added/claimed.')

        title = f'Recent Events for {player.name}'

        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @events.command(name='clan', hidden=True)
    async def events_clan(self, ctx, limit: typing.Optional[int] = 20, *, clans: ClanConverter):
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

        query = """SELECT player_tag, donations, received, time, player_name
                        FROM events
                    WHERE clan_tag = ANY($1::TEXT[])
                    ORDER BY time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, list(set(n.tag for n in clans)), limit)
        if not fetch:
            return await ctx.send('No events found.')

        title = f"Recent Events for {', '.join(n.name for n in clans)}"
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.EventsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()


def setup(bot):
    bot.add_cog(Events(bot))
