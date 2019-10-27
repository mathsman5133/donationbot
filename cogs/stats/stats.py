import typing

from discord.ext import commands

from cogs.utils.checks import requires_config


class Stats(commands.Cog):
    """Redirect stats commands to the appropriate place"""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True)
    async def stats(self, ctx):
        """The main stats command for all donation, trophy, attacks and defense statistics.

        This command does nothing by itself, however - check out the subcommands!

        If your server is currently in an event (`+info event`), this will automatically divert your command to
        `+eventstats...`, otherwise it will automatically call `+seasonstats...`.
        """
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @stats.command(name='attacks')
    @requires_config('event')
    async def stats_attacks(self, ctx, season_id: typing.Optional[int] = None):
        """Get top attack wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Format**
        :information_source: `+stats attacks SEASON_ID`

        **Example**
        :white_check_mark: `+stats attacks`
        :white_check_mark: `+stats attacks 2`
        """
        if ctx.config:
            return await ctx.invoke(self.bot.get_command('eventstats attacks'))
        await ctx.invoke(self.bot.get_command('seasonstats attacks'), season_id)

    @stats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    @requires_config('event')
    async def stats_defenses(self, ctx, season_id: typing.Optional[int] = None):
        """Get top defense wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Format**
        :information_source: `+stats defenses SEASON_ID`

        **Example**
        :white_check_mark: `+stats defenses`
        :white_check_mark: `+stats defenses 1`
        """
        if ctx.config:
            return await ctx.invoke(self.bot.get_command('eventstats defenses'))
        await ctx.invoke(self.bot.get_command('seasonstats defenses'), season_id)

    @stats.command(name='gains', aliases=['gain', 'trophies'])
    @requires_config('event')
    async def stats_gains(self, ctx, season_id: typing.Optional[int] = None):
        """Get top trophy gainers for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Format**
        :information_source: `+stats gains SEASON_ID`

        **Example**
        :white_check_mark: `+stats gains`
        :white_check_mark: `+stats gains 3`
        """
        if ctx.config:
            return await ctx.invoke(self.bot.get_command('eventstats gains'))
        await ctx.invoke(self.bot.get_command('seasonstats gains'), season_id)

    @stats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    @requires_config('event')
    async def stats_donors(self, ctx, season_id: typing.Optional[int] = None):
        """Get top donors for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Format**
        :information_source: `+stats donors SEASON_ID`

        **Example**
        :white_check_mark: `+stats donors`
        :white_check_mark: `+stats donors 4`
        """
        if ctx.config:
            return await ctx.infoke(self.bot.get_command('eventstats donors'))
        await ctx.invoke(self.bot.get_command('seasonstats donors'), season_id)


def setup(bot):
    bot.add_cog(Stats(bot))
