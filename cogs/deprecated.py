from disnake.ext import commands


def deprecated(fmt):
    async def pred(ctx):
        raise commands.CheckFailure(f'This command has been deprecated. Please use `{ctx.prefix}{fmt}` instead.')
    return commands.check(pred)


class Deprecated(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='donationboard create')
    @deprecated('add donationboard')
    async def donationboard(self, ctx):
        return

    @commands.command(name='donationboard edit')
    @deprecated('edit donationboard')
    async def edit(self, ctx):
        return

    @commands.command(name='donationboard remove')
    @deprecated('remove donationboard')
    async def remove(self, ctx):
        return

    @commands.command(name='donationboard icon')
    @deprecated('edit donationboard icon')
    async def icon(self, ctx):
        return

    @commands.command(name='donationboard title')
    @deprecated('edit donationboard title')
    async def title(self, ctx):
        return

    @commands.command(name='donationboard info')
    @deprecated('info donationboard')
    async def info(self, ctx):
        return

    @commands.command(name='log create')
    @deprecated('add donationlog')
    async def log(self, ctx):
        return

    @commands.command(name='log info')
    @deprecated('info log')
    async def log_info(self, ctx):
        return

    @commands.command(name='log interval')
    @deprecated('edit donationlog interval')
    async def edit_log_interval(self, ctx):
        return

    @commands.command(name='log toggle')
    @deprecated('remove donationlog')
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
