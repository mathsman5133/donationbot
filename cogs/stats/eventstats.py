import discord

from discord.ext import commands

from cogs.utils import formatters
from cogs.utils.checks import requires_config
from cogs.utils.emoji_lookup import misc


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

    @commands.group(name='eventstats', invoke_without_command=True)
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
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        table = formatters.CLYTable()
        title = f"Attack wins for {ctx.config.event_name}"

        attacks = {n['player_tag']: n['attacks'] for n in fetch}

        async with ctx.typing():
            for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
                table.add_row([index, attacks[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_attacks()
        fmt += f"**Key:**\n{misc['attack']} - Attacks\n{misc['trophygold']} - Trophies"

        e = discord.Embed(
            colour=discord.Colour.gold(), description=fmt, title=title
        )
        await ctx.send(embed=e)

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
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        defenses = {n['player_tag']: n['defenses'] for n in fetch}

        table = formatters.CLYTable()
        title = f"Defense wins for {ctx.config.event_name}"

        async with ctx.typing():
            for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
                table.add_row([index, defenses[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_defenses()
        fmt += f"**Key:**\n{misc['defense']} - Defenses\n{misc['trophygold']} - Trophies"

        e = discord.Embed(
            colour=discord.Colour.dark_red(), description=fmt, title=title
        )
        await ctx.send(embed=e)

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
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        table = formatters.CLYTable()
        title = f"Trophy Gains for {ctx.config.event_name}"

        gains = {n['player_tag']: n['gain'] for n in fetch}

        async with ctx.typing():
            for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
                table.add_row([index, gains[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_gain()
        fmt += f"**Key:**\n{misc['trophygreen']} - Trophy Gain\n{misc['trophygold']} - Total Trophies"

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )
        await ctx.send(embed=e)

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
                    ORDER BY donations DESC NULLS LAST
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        table = formatters.CLYTable()
        title = f"Donations for {ctx.config.event_name}"

        donations = {n['player_tag']: n['donations'] for n in fetch}

        async with ctx.typing():
            for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
                table.add_row([index, donations[player.tag], player.name])

        fmt = table.donationboard_2()

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(EventStats(bot))
