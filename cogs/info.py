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

    async def send_guild_stats(self, e, guild):
        e.add_field(name='Name', value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Owner', value=f'{guild.owner} (ID: {guild.owner.id})')

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count
        online = sum(m.status is discord.Status.online for m in guild.members)
        e.add_field(name='Members', value=str(total))
        e.add_field(name='Bots', value=f'{bots} ({bots/total:.2%})')
        e.add_field(name='Online', value=f'{online} ({online/total:.2%})')

        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)

        if guild.me:
            e.timestamp = guild.me.joined_at

        await self.bot.webhook.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53dda4, title='New Guild') # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES $1"
        await self.pool.execute(query, guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        e = discord.Embed(colour=0xdd5f53, title='Left Guild') # red colour
        await self.send_guild_stats(e, guild)


def setup(bot):
    bot.add_cog(Info(bot))
