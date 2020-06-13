import discord
import math

from discord.ext import commands

from cogs.utils.checks import requires_config
from cogs.utils.emoji_lookup import misc
from cogs.utils.paginator import (
    StatsAttacksPaginator, StatsDefensesPaginator, StatsDonorsPaginator, StatsGainsPaginator
)


class EventStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_recent_event(self, guild_id):
        query = "SELECT get_event_id($1)"
        row = await self.bot.pool.fetchrow(query, guild_id)
        if row[0] > 0:
            return row[0]
        else:
            return None

    @commands.group(name='eventstats', invoke_without_command=True, hidden=True)
    async def eventstats(self, ctx):
        """[Group] Provide statistics for the current (or most recent) event for this server.

        This command does nothing by itself - check out the subcommands!

        If you choose to pass in an Event ID, the event **must** have been one registered to your server.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @eventstats.command(name='attacks')
    @requires_config('event')
    async def eventstats_attacks(self, ctx, event_id: int = None):
        """Get attack wins for all clans.

        **Parameters**
        :key: Event ID (optional - defaults to last event)

        **Format**
        :information_source: `+eventstats attacks EVENT_ID`

        **Example**
        :white_check_mark: `+eventstats attacks`
        :white_check_mark: `+eventstats attacks 3`
        """
        if event_id:
            ctx.config = await self.bot.utils.event_config_id(event_id)
            if ctx.config and ctx.config.guild_id != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(
                    "Uh oh! You're trying to get info for an event not registered to this server! "
                    "Please try again with a different Event ID."
                )

        if not ctx.config:
            event_id = await self.get_recent_event(ctx.guild.id)
            if event_id:
                ctx.config = await self.bot.utils.event_config_id(event_id)
            else:
                return await ctx.send(
                    'It would appear that there are no recent events connected with this server. You can:\n'
                    'Use `+add event` to create an event.\n'
                    'Use `+info events` to list all events on this server.\n'
                    'Use `+seasonstats attacks` to see results for the season.'
                )

        query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY attacks DESC
                    NULLS LAST
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        title = f"Attack wins for {ctx.config.event_name}"
        key = f"**Key:**\n{misc['attack']} - Attacks\n{misc['trophygold']} - Trophies"

        p = StatsAttacksPaginator(ctx, fetch, title, key=key)
        await p.paginate()

    @eventstats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    @requires_config('event')
    async def eventstats_defenses(self, ctx, event_id: int = None):
        """Get defense wins for all clans.

        **Parameters**
        :key: Event ID (optional - defaults to last event)

        **Format**
        :information_source: `+eventstats defenses EVENT_ID`

        **Example**
        :white_check_mark: `+eventstats defenses`
        :white_check_mark: `+eventstats defenses 3`
        """
        if event_id:
            ctx.config = await self.bot.utils.event_config_id(event_id)
            if ctx.config and ctx.config.guild_id != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(
                    "Uh oh! You're trying to get info for an event not registered to this server! "
                    "Please try again with a different Event ID."
                )

        if not ctx.config:
            event_id = await self.get_recent_event(ctx.guild.id)
            if event_id:
                ctx.config = await self.bot.utils.event_config_id(event_id)
            else:
                return await ctx.send(
                    'It would appear that there are no recent events connected with this server. You can:\n'
                    'Use `+add event` to create an event.\n'
                    'Use `+info events` to list all events on this server.\n'
                    'Use `+seasonstats defenses` to see results for the season.'
                )

        query = """SELECT player_tag, end_defenses - start_defenses as defenses, trophies 
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY defenses DESC
                    NULLS LAST
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        title = f"Defense wins for {ctx.config.event_name}"
        key = f"**Key:**\n{misc['defense']} - Defenses\n{misc['trophygold']} - Trophies"

        p = StatsDefensesPaginator(ctx, fetch, title, key=key, page_count=math.ceil(len(fetch) / 20))
        await p.paginate()

    @eventstats.command(name='gains', aliases=['trophies'])
    @requires_config('event')
    async def eventstats_gains(self, ctx, event_id: int = None):
        """Get trophy gains for all clans.

        **Parameters**
        :key: Event ID (optional - defaults to last season)

        **Format**
        :information_source: `+eventstats gains EVENT_ID`

        **Example**
        :white_check_mark: `+eventstats gains`
        :white_check_mark: `+eventstats gains 3`
        """
        if event_id:
            ctx.config = await self.bot.utils.event_config_id(event_id)
            if ctx.config and ctx.config.guild_id != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(
                    "Uh oh! You're trying to get info for an event not registered to this server! "
                    "Please try again with a different Event ID."
                )

        if not ctx.config:
            event_id = await self.get_recent_event(ctx.guild.id)
            if event_id:
                ctx.config = await self.bot.utils.event_config_id(event_id)
            else:
                return await ctx.send(
                    'It would appear that there are no recent events connected with this server. You can:\n'
                    'Use `+add event` to create an event.\n'
                    'Use `+info events` to list all events on this server.\n'
                    'Use `+seasonstats gains` to see results for the season.'
                )

        query = """SELECT player_tag, trophies - start_trophies as gain, trophies 
                   FROM eventplayers 
                   WHERE event_id = $1
                   ORDER BY gain DESC
                   NULLS LAST
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        title = f"Trophy Gains for {ctx.config.event_name}"
        key = f"**Key:**\n{misc['trophygreen']} - Trophy Gain\n{misc['trophygold']} - Total Trophies"

        p = StatsGainsPaginator(ctx, fetch, title, key=key, page_count=math.ceil(len(fetch) / 20))
        await p.paginate()

    @eventstats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    @requires_config('event')
    async def eventstats_donors(self, ctx, event_id: int = None):
        """Get donations for all clans.

        **Parameters**
        :key: Event ID (optional - defaults to last season)

        **Format**
        :information_source: `+eventstats donors EVENT_ID`

        **Example**
        :white_check_mark: `+eventstats donors`
        :white_check_mark: `+eventstats donors 3`
        """
        if event_id:
            ctx.config = await self.bot.utils.event_config_id(event_id)
            if ctx.config and ctx.config.guild_id != ctx.guild.id and not await self.bot.is_owner(ctx.author):
                return await ctx.send(
                    "Uh oh! You're trying to get info for an event not registered to this server! "
                    "Please try again with a different Event ID."
                )

        if not ctx.config:
            event_id = await self.get_recent_event(ctx.guild.id)
            if event_id:
                ctx.config = await self.bot.utils.event_config_id(event_id)
            else:
                return await ctx.send(
                    'It would appear that there are no recent events connected with this server. You can:\n'
                    'Use `+add event` to create an event.\n'
                    'Use `+info events` to list all events on this server.\n'
                    'Use `+seasonstats attacks` to see results for the season.'
                )

        query = """SELECT player_tag,  
                    (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY donations DESC
                    NULLS LAST
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        title = f"Donations for {ctx.config.event_name}"

        p = StatsDonorsPaginator(ctx, fetch, title, page_count=math.ceil(len(fetch) / 20))
        await p.paginate()


def setup(bot):
    bot.add_cog(EventStats(bot))
