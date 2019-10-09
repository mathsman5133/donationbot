from discord.ext import commands


class Stats(commands.Cog):
    """Redirect stats commands to the appropriate place"""
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Stats(bot))
