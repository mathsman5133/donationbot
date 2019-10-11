import discord

from cogs.utils import formatters
from cogs.utils.checks import requires_config
from discord.ext import commands


class Event(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='eventstats', invoke_without_command=True)
    async def eventstats(self, ctx):
        """[Group] Provide statistics for the current (or most recent) event for this server.

        **Parameters**
        :key: Category

        **Format**
        :information_source: `+eventstats catgory`

        **Examples**
        :white_check_mark: `+eventstats attacks`
        :white_check_mark: `+eventstats defenses`
        :white_check_mark: `+eventstats gains`
        :white_check_mark: `+eventstats donations`
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @eventstats.command(name='attacks')
    @requires_config('event', invalidate=True)
    async def attacks(self, ctx):
        """Get attack wins for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+eventstats attacks`
        """
        query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY attacks DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        table = formatters.CLYTable()
        table.title = f"Attack wins for {ctx.config.event_name}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['attacks'], player.trophies, player.name])
        render = table.trophyboard_attacks()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.gold(), description=fmt)
        await ctx.send(embed=e)

    @eventstats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    @requires_config('event', invalidate=True)
    async def defenses(self, ctx):
        """Get defense wins for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+eventstats defenses`
        """
        query = """SELECT player_tag, end_defenses - start_defenses as defenses, trophies 
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY defenses DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        table = formatters.CLYTable()
        table.title = f"Defense wins for {ctx.config.event_name}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['defenses'], player.trophies, player.name])
        render = table.trophyboard_defenses()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.dark_red(), description=fmt)
        await ctx.send(embed=e)

    @eventstats.command(name='gains', aliases=['trophies'])
    @requires_config('event', invalidate=True)
    async def gains(self, ctx):
        """Get trophy gains for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+eventstats gains`
        """
        query = """SELECT player_tag, trophies - start_trophies as gain, trophies 
                        FROM eventplayers 
                        WHERE event_id = $1
                        ORDER BY gain DESC
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        table = formatters.CLYTable()
        table.title = f"Trophy Gains for {ctx.config.event_name}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['gains'], player.trophies, player.name])
        render = table.trophyboard_gain()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.green(), description=fmt)
        await ctx.send(embed=e)

    @eventstats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    @requires_config('event', invalidate=True)
    async def donors(self, ctx):
        """Get donations for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+eventstats donations`
        """
        query = """SELECT player_tag,  
                    (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY gain DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        table = formatters.CLYTable()
        table.title = f"Donations for {ctx.config.event_name}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['donations'], player.name])
        render = table.donationboard_2()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.green(), description=fmt)
        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(Event(bot))
