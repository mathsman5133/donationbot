from discord.ext import commands
import discord


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['join'])
    async def invite(self, ctx):
        """Get an invite to add the bot to your server.
        """
        await ctx.send(f'<{discord.utils.oauth_url(self.bot.client_id)}>')

    @commands.group()
    async def info(self, ctx):
        pass


def setup(bot):
    bot.add_cog(Info(bot))
