from discord.ext import commands

class Aliases(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_aliases(self, full_name):
        return None

def setup(bot):
    bot.add_cog(Aliases(bot))
