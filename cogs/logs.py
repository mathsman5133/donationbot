import discord

from discord.ext import commands


class Logs(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot: "DonationBot"):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Logs(bot))
