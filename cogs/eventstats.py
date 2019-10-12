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
    async def eventstats_attacks(self, ctx):
        """Get attack wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+eventstats attacks`
        :white_check_mark: `+eventstats attacks 2`
        """
        if not ctx.config:
            # TODO Consider pulling most recent event and if time is between end of event and end of season, show stats.
            return ctx.send('It would appear that you aren\'t currently in an event. Did you mean `+season attacks`?')
        query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY attacks DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        attacks = {n['player_tag']: n['attacks'] for n in fetch}
        table = formatters.CLYTable()
        title = f"Attack wins for {ctx.config.event_name}"
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, attacks[player.tag], player.trophies, player.name])
        render = table.trophyboard_attacks()

        e = discord.Embed(colour=discord.Colour.gold(),
                          title=title,
                          description=render)
        await ctx.send(embed=e)

    @eventstats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    @requires_config('event', invalidate=True)
    async def eventstats_defenses(self, ctx):
        """Get defense wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+eventstats defenses`
        :white_check_mark: `+eventstats defenses 1`
        """
        if not ctx.config:
            return ctx.send('It would appear that you aren\'t currently in an event. Did you mean `+season defenses`?')
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
        render = table.trophyboard_defenses()

        e = discord.Embed(colour=discord.Colour.dark_red(),
                          title=title,
                          description=render)
        await ctx.send(embed=e)

    @eventstats.command(name='gains', aliases=['trophies'])
    @requires_config('event', invalidate=True)
    async def eventstats_gains(self, ctx):
        """Get trophy gains for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+eventstats gains`
        :white_check_mark: `+eventstats gains 3`
        """
        if not ctx.config:
            return ctx.send('It would appear that you aren\'t currently in an event. Did you mean `+season gains`?')
        query = """SELECT player_tag, trophies - start_trophies as gain, trophies 
                        FROM eventplayers 
                        WHERE event_id = $1
                        ORDER BY gain DESC
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        gains = {n['player_tag']: n['gains'] for n in fetch}
        table = formatters.CLYTable()
        title = f"Trophy Gains for {ctx.config.event_name}"
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, gains[player.tag], player.trophies, player.name])
        render = table.trophyboard_gain()

        e = discord.Embed(colour=discord.Colour.green(),
                          title=title,
                          description=render)
        await ctx.send(embed=e)

    @eventstats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    @requires_config('event', invalidate=True)
    async def eventstats_donors(self, ctx):
        """Get donations for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+eventstats donations`
        :white_check_mark: `+eventstats donors 4`
        """
        if not ctx.config:
            return ctx.send('It would appear that you aren\'t currently in an event. Did you mean `+season donors`?')
        query = """SELECT player_tag,  
                    (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                    FROM eventplayers 
                    WHERE event_id = $1
                    ORDER BY gain DESC
                    LIMIT 15
                """
        fetch = await ctx.db.fetch(query, ctx.config.id)
        donations = {}
        for row in fetch:
            donations[row['playertag']] = row['donations']
        table = formatters.CLYTable()
        title = f"Donations for {ctx.config.event_name}"
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, donations[player.tag], player.name])
        render = table.donationboard_2()

        e = discord.Embed(colour=discord.Colour.green(),
                          title=title,
                          description=render)
        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(Event(bot))
