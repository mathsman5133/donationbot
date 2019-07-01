from discord.ext import commands
import discord


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['join'])
    async def invite(self, ctx):
        """Get an invite to add the bot to your server.
        """
        perms = discord.Permissions.none()
        perms.read_messages = True
        perms.external_emojis = True
        perms.send_messages = True
        perms.manage_channels = True
        perms.manage_messages = True
        perms.embed_links = True
        perms.read_message_history = True
        perms.add_reactions = True
        perms.attach_files = True
        await ctx.send(f'<{discord.utils.oauth_url(self.bot.client_id, perms)}>')

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
        e = discord.Embed(colour=0x53dda4, title='New Guild')  # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES ($1)"
        await self.bot.pool.execute(query, guild.id)

        if guild.system_channel:
            await guild.system_channel.send('Hi There! Thanks for adding my. My prefix is `+`, '
                                            'and all commands can be found with `+help`.'
                                            ' To start off, you might be looking for the `+updates` command, the '
                                            '`+log` command, the `+aclan` command and the `+auto_claim` command.\n\n'
                                            'Feel free to join the support server if you get stuck: discord.gg/ePt8y4V,'
                                            '\n\nHere is the invite link to share me with your friends: '
                                            'https://discordapp.com/oauth2/authorize?client_id=427301910291415051&'
                                            'scope=bot&permissions=388176. \n\nHave a good day!')
        else:
            for c in guild.channels:
                if c.permissions_for(self.bot.user).send_messages:
                    await c.send('Hi There! Thanks for adding my. My prefix is `+`, '
                                 'and all commands can be found with `+help`.'
                                 ' To start off, you might be looking for the `+updates` command, '
                                 'the `+log` command, the `+aclan` command and the `+auto_claim` command. '
                                 'Feel free to join the support server if you get stuck: discord.gg/ePt8y4V,'
                                 ' and here is the invite link to share me with your friends: '
                                 'https://discordapp.com/oauth2/authorize?client_id=427301910291415051&'
                                 'scope=bot&permissions=388176. Have a good day!')
                    return

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        e = discord.Embed(colour=0xdd5f53, title='Left Guild') # red colour
        await self.send_guild_stats(e, guild)


def setup(bot):
    bot.add_cog(Info(bot))
