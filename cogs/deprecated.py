from discord.ext import commands


def deprecated(fmt):
    async def pred(ctx):
        await ctx.send(f'This command has been deprecated. Please use `{ctx.prefix}{fmt}` instead.')
        return False
    return commands.check(pred)


class Deprecated(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    @deprecated('add donationboard')
    async def donationboard(self, ctx):
        return

    @donationboard.command()
    @deprecated('add donationboard')
    async def create(self, ctx):
        return

    @donationboard.command()
    @deprecated('edit donationboard')
    async def edit(self, ctx):
        return

    @donationboard.command()
    @deprecated('remove donationboard')
    async def remove(self, ctx):
        return

    @donationboard.command()
    @deprecated('edit donationboard icon')
    async def icon(self, ctx):
        return

    @donationboard.command()
    @deprecated('edit donationboard title')
    async def title(self, ctx):
        return

    @donationboard.command()
    @deprecated('info donationboard')
    async def info(self, ctx):
        return

    @commands.group()
    @deprecated('add log')
    async def log(self, ctx):
        return

    @log.command(name='create')
    @deprecated('add log')
    async def log_add(self, ctx):
        return

    @log.command(name='info')
    @deprecated('info log')
    async def log_info(self, ctx):
        return

    @log.command(name='interval')
    @deprecated('edit log interval')
    async def edit_log_interval(self, ctx):
        return

    @log.command(name='toggle')
    @deprecated('edit log toggle')
    async def edit_log_toggle(self, ctx):
        return

    @commands.command()
    @deprecated('add clan')
    async def addclan(self, ctx):
        return

    @commands.command()
    @deprecated('add player')
    async def addplayer(self, ctx):
        return

    @commands.command()
    @deprecated('add clan')
    async def addclan(self, ctx):
        return

    @commands.command()
    @deprecated('remove clan')
    async def removeclan(self, ctx):
        return


def setup(bot):
    bot.add_cog(Deprecated(bot))
