import coc
import discord
import logging
import math
import typing

from discord.ext import commands
from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils.error_handler import error_handler
from cogs.utils import formatters
from cogs.utils.db_objects import SlimDummyLogConfig

log = logging.getLogger(__name__)


class Events(commands.Cog):
    """Find historical clan donation or trophy data for your clan, or setup logging and events.
    """
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def recent_events(table_name, ctx, limit):
        query = f"""SELECT player_tag, donations, received, time, player_name
                    FROM {table_name}
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

        p = formatters.LogsPaginator(ctx, fetch, page_count=no_pages, title=title)
        await p.paginate()

    @staticmethod
    async def user_events(table_name, ctx, user, limit):
        query = f"""SELECT {table_name}.player_tag, 
                           {table_name}.donations, 
                           {table_name}.received, 
                           {table_name}.time, 
                           {table_name}.player_name
                    FROM {table_name} 
                        INNER JOIN players
                        ON {table_name}.player_tag = players.player_tag 
                    WHERE players.user_id = $1 
                    ORDER BY time DESC 
                    LIMIT $2;
                """
        fetch = await ctx.db.fetch(query, user.id, limit)
        if not fetch:
            return await ctx.send(f'No events found.')

        title = f'Recent Events for {str(user)}'
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.LogsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @staticmethod
    async def player_events(table_name, ctx, player, limit):
        query = f"""SELECT player_tag, donations, received, time, player_name
                    FROM {table_name} 
                    WHERE player_tag = $1 
                    ORDER BY time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, player.tag, limit)
        if not fetch:
            return await ctx.send('Account has not been added/claimed.')

        title = f'Recent Events for {player.name}'

        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.LogsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @staticmethod
    async def clan_events(table_name, ctx, clans, limit):
        query = f"""SELECT player_tag, donations, received, time, player_name
                    FROM {table_name}
                    WHERE clan_tag = ANY($1::TEXT[])
                    ORDER BY time DESC 
                    LIMIT $2
                """
        fetch = await ctx.db.fetch(query, list(set(n.tag for n in clans)), limit)
        if not fetch:
            return await ctx.send('No events found.')

        title = f"Recent Events for {', '.join(n.name for n in clans)}"
        no_pages = math.ceil(len(fetch) / 20)

        p = formatters.LogsPaginator(ctx, data=fetch, title=title, page_count=no_pages)
        await p.paginate()

    @commands.group(invoke_without_command=True)
    async def donationevents(self, ctx, limit: typing.Optional[int] = 20, *,
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
        • `+donationevents 20 #CLAN_TAG`
        • `+donationevents @mention`
        • `+donationevents #PLAYER_TAG`
        • `+donationevents player name`
        • `+donationevents 1000 all`
        • `+donationevents`
        """
        ctx.config = SlimDummyLogConfig('donation', 'Donation Events', None)
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = limit

        if isinstance(arg, int):
            await ctx.invoke(self.donation_events_recent, limit=arg)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.donation_events_player, player=arg, limit=limit)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.donation_events_user, user=arg, limit=limit)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.donation_events_clan, clans=arg, limit=limit)

    @donationevents.command(name='recent', hidden=True)
    async def donation_events_recent(self, ctx, limit: int = None):
        await self.recent_events('donationevents', ctx, limit)

    @donationevents.command(name='user', hidden=True)
    async def donation_events_user(self, ctx, limit: typing.Optional[int] = 20, *,
                          user: discord.Member = None):
        """Get donation history/events for a discord user.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+donationevents user @mention`
        • `+donationevents user USER_ID`
        • `+donationevents user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        await self.user_events('donationevents', ctx, user, limit)

    @donationevents.command(name='player', hidden=True)
    async def donation_events_player(self, ctx, limit: typing.Optional[int] = 20,
                            *, player: PlayerConverter):
        """Get donation history/events for a player.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ------------
        • `+donationevents player #PLAYER_TAG`
        • `+donationevents player player name`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        await self.player_events('donationevents', ctx, player, limit)

    @donationevents.command(name='clan', hidden=True)
    async def donation_events_clan(self, ctx, limit: typing.Optional[int] = 20, *, clans: ClanConverter):
        """Get donation history/events for a clan.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ------------
        • `+donationevents clan #CLAN_TAG`
        • `+donationevents clan clan name`
        • `+donationevents clan all`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        await self.clan_events('donationevents', ctx, clans, limit)

    @commands.group(invoke_without_command=True)
    async def trophyevents(self, ctx, limit: typing.Optional[int] = 20, *,
                           arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """Check recent trophy events for a player, user, clan or guild.

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
        • `+trophyevents 20 #CLAN_TAG`
        • `+trophyevents @mention`
        • `+trophyevents #PLAYER_TAG`
        • `+trophyevents player name`
        • `+trophyevents 1000 all`
        • `+trophyevents`
        """
        ctx.config = SlimDummyLogConfig('trophy', 'Donation Events', None)
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = limit

        if isinstance(arg, int):
            await ctx.invoke(self.trophy_events_recent, limit=arg)
        elif isinstance(arg, coc.BasicPlayer):
            await ctx.invoke(self.trophy_events_player, player=arg, limit=limit)
        elif isinstance(arg, discord.Member):
            await ctx.invoke(self.trophy_events_user, user=arg, limit=limit)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.Clan):
                await ctx.invoke(self.trophy_events_clan, clans=arg, limit=limit)

    @trophyevents.command(name='recent', hidden=True)
    async def trophy_events_recent(self, ctx, limit: int = None):
        await self.recent_events('trophyevents', ctx, limit)

    @trophyevents.command(name='user', hidden=True)
    async def trophy_events_user(self, ctx, limit: typing.Optional[int] = 20, *,
                          user: discord.Member = None):
        """Get trophy history/events for a discord user.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord @mention, user#discrim or user id
            • None passed will divert to donations for your discord account

        Example
        ------------
        • `+trophyevents user @mention`
        • `+trophyevents user USER_ID`
        • `+trophyevents user`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        if not user:
            user = ctx.author

        await self.user_events('trophyevents', ctx, user, limit)

    @trophyevents.command(name='player', hidden=True)
    async def trophy_events_player(self, ctx, limit: typing.Optional[int] = 20,
                            *, player: PlayerConverter):
        """Get trophy history/events for a player.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in a clan claimed to server)

        Example
        ------------
        • `+trophyevents player #PLAYER_TAG`
        • `+trophyevents player player name`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        await self.player_events('trophyevents', ctx, player, limit)

    @trophyevents.command(name='clan', hidden=True)
    async def trophy_events_clan(self, ctx, limit: typing.Optional[int] = 20, *, clans: ClanConverter):
        """Get trophy history/events for a clan.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed to server)
            • `all`, `server`, `guild`: all clans claimed to server

        Example
        ------------
        • `+trophyevents clan #CLAN_TAG`
        • `+trophyevents clan clan name`
        • `+trophyevents clan all`

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.
        """
        await self.clan_events('trophyevents', ctx, clans, limit)


def setup(bot):
    bot.add_cog(Events(bot))
