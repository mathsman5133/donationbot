import discord

from discord.ext import commands

from cogs.utils import formatters
from cogs.utils.checks import requires_config
from cogs.utils.emoji_lookup import misc


class EventStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.before_invoke(ctx)

    async def cog_after_invoke(self, ctx):
        after_invoke = getattr(ctx, 'after_invoke', None)
        if after_invoke:
            await after_invoke(ctx)

    @commands.group(name='eventstats', invoke_without_command=True)
    async def eventstats(self, ctx):
        """[Group] Provide statistics for the current (or most recent) event for this server.

        This command does nothing by itself - check out the subcommands!

        Your server **must** be in an event for this command to work.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @eventstats.command(name='attacks')
    @requires_config('event')
    async def eventstats_attacks(self, ctx):
        """Get attack wins for all clans.

        **Format**
        :information_source: `+eventstats attacks`

        **Example**
        :white_check_mark: `+eventstats attacks`
        """
        if not ctx.config:
            # TODO Consider pulling most recent event and if time is between end of event and end of season, show stats.
            return await ctx.send(
                'It would appear that you aren\'t currently in an event. Did you mean `+seasonstats attacks`?'
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
    async def eventstats_defenses(self, ctx):
        """Get defense wins for all clans.

        **Format**
        :information_source: `+eventstats defenses`

        **Example**
        :white_check_mark: `+eventstats defenses`
        """
        if not ctx.config:
            return await ctx.send(
                'It would appear that you aren\'t currently in an event. Did you mean `+seasonstats defenses`?'
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
    async def eventstats_gains(self, ctx):
        """Get trophy gains for all clans.

        **Format**
        :information_source: `+eventstats gains`

        **Example**
        :white_check_mark: `+eventstats gains`
        """
        if not ctx.config:
            return await ctx.send(
                'It would appear that you aren\'t currently in an event. Did you mean `+seasonstats gains`?'
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
    async def eventstats_donors(self, ctx):
        """Get donations for all clans.

        **Format**
        :information_source: `+eventstats donors`

        **Example**
        :white_check_mark: `+eventstats donors`
        """
        if not ctx.config:
            return await ctx.send(
                'It would appear that you aren\'t currently in an event. Did you mean `+seasonstats donors`?'
            )

        query = """SELECT player_tag,  
                    (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY donations DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)

        table = formatters.CLYTable()
        title = f"Donations for {ctx.config.event_name}"

        donations = {n['player_tag']: n['donations'] for n in fetch}
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, donations[player.tag], player.name])

        fmt = table.donationboard_2()

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(EventStats(bot))
