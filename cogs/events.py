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
    """Find historical clan donation or trophy data for your clan."""
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def recent_events(table_name, ctx, limit):
        query = f"""SELECT player_tag, donations, received, time, player_name
                    FROM {table_name}
                    WHERE {table_name}.clan_tag = ANY(
                                SELECT DISTINCT clan_tag FROM clans
                                WHERE guild_id=$1
                                )
                    ORDER BY {table_name}.time DESC
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
    async def donationevents(self, ctx, limit: typing.Optional[int] = 1000, *,
                             arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Check recent donation events for a player, user, clan or guild.

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+donationevents @MENTION`
        :information_source: `+donationevents #PLAYER_TAG`
        :information_source: `+donationevents Player Name`
        :information_source: `+donationevents #CLAN_TAG`
        :information_source: `+donationevents Clan Name`
        :information_source: `+donationevents all`

        **Example**
        :white_check_mark: `+donationevents @mathsman`
        :white_check_mark: `+donationevents #JJ6C8PY`
        :white_check_mark: `+donationevents mathsman`
        :white_check_mark: `+donationevents #P0LYJC8C`
        :white_check_mark: `+donationevents Rock Throwers`
        :white_check_mark: `+donationevents all`
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

    @donationevents.command(name='user')
    async def donation_events_user(self, ctx, limit: typing.Optional[int] = 20, *,
                          user: discord.Member = None):
        """Get donation history/events for a discord user.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Discord user (optional - defaults to yourself)

        **Format**
        :information_source: `+donationevents user @MENTION`
        :information_source: `+donationevents user`

        **Example**
        :white_check_mark: `+donationevents user @mathsman`
        :white_check_mark: `+donationevents user`
        """
        if not user:
            user = ctx.author

        await self.user_events('donationevents', ctx, user, limit)

    @donationevents.command(name='player')
    async def donation_events_player(self, ctx, limit: typing.Optional[int] = 20,
                            *, player: PlayerConverter):
        """Get donation history/events for a player.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+donationevents player #PLAYER_TAG`
        :information_source: `+donationevents player Player Name`

        **Example**
        :white_check_mark: `+donationevents player #P0LYJC8C`
        :white_check_mark: `+donationevents player mathsman`
        """
        await self.player_events('donationevents', ctx, player, limit)

    @donationevents.command(name='clan')
    async def donation_events_clan(self, ctx, limit: typing.Optional[int] = 20, *, clans: ClanConverter):
        """Get donation history/events for a clan.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Clan name OR tag OR `all` to get all clans.

        **Format**
        :information_source: `+donationevents clan #CLAN_TAG`
        :information_source: `+donationevents clan Clan Name`
        :information_source: `+donationevents clan all`

        **Example**
        :white_check_mark: `+donationevents clan #P0LYJC8C`
        :white_check_mark: `+donationevents clan Rock Throwers`
        :white_check_mark: `+donationevents clan all`
        """
        await self.clan_events('donationevents', ctx, clans, limit)

    @commands.group(invoke_without_command=True)
    async def trophyevents(self, ctx, limit: typing.Optional[int] = 1000, *,
                           arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Check recent trophy events for a player, user or clan(s).

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+trophyevents @MENTION`
        :information_source: `+trophyevents #PLAYER_TAG`
        :information_source: `+trophyevents Player Name`
        :information_source: `+trophyevents #CLAN_TAG`
        :information_source: `+trophyevents Clan Name`
        :information_source: `+trophyevents all`

        **Example**
        :white_check_mark: `+trophyevents @mathsman`
        :white_check_mark: `+trophyevents #JJ6C8PY`
        :white_check_mark: `+trophyevents mathsman`
        :white_check_mark: `+trophyevents #P0LYJC8C`
        :white_check_mark: `+trophyevents Rock Throwers`
        :white_check_mark: `+trophyevents all`
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
        """Get donation history/events for a discord user.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Discord user (optional - defaults to yourself)

        **Format**
        :information_source: `+trophyevents user @MENTION`
        :information_source: `+trophyevents user`

        **Example**
        :white_check_mark: `+trophyevents user @mathsman`
        :white_check_mark: `+trophyevents user`
        """
        if not user:
            user = ctx.author

        await self.user_events('trophyevents', ctx, user, limit)

    @trophyevents.command(name='player', hidden=True)
    async def trophy_events_player(self, ctx, limit: typing.Optional[int] = 20,
                            *, player: PlayerConverter):
        """Get trophy history/events for a player.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+trophyevents player #PLAYER_TAG`
        :information_source: `+trophyevents player Player Name`

        **Example**
        :white_check_mark: `+trophyevents player #P0LYJC8C`
        :white_check_mark: `+trophyevents player mathsman`
        """
        await self.player_events('trophyevents', ctx, player, limit)

    @trophyevents.command(name='clan', hidden=True)
    async def trophy_events_clan(self, ctx, limit: typing.Optional[int] = 20, *, clans: ClanConverter):
        """Get trophy history/events for a clan.

        By default, you shouldn't need to call these sub-commands as the bot will
        parse your argument and direct it to the correct sub-command automatically.

        **Parameters**
        :key: Clan name OR tag OR `all` to get all clans.

        **Format**
        :information_source: `+trophyevents clan #CLAN_TAG`
        :information_source: `+trophyevents clan Clan Name`
        :information_source: `+trophyevents clan all`

        **Example**
        :white_check_mark: `+trophyevents clan #P0LYJC8C`
        :white_check_mark: `+trophyevents clan Rock Throwers`
        :white_check_mark: `+trophyevents clan all`
        """
        await self.clan_events('trophyevents', ctx, clans, limit)


def setup(bot):
    bot.add_cog(Events(bot))
