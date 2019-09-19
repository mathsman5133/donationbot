import logging
import dbl
import psutil
import os
import asyncio
import discord
import itertools

from discord.ext import commands, tasks
from cogs.utils.paginator import Pages
from cogs.utils.error_handler import error_handler
from cogs.utils.formatters import CLYTable
from cogs.guildsetup import requires_config
from datetime import datetime, time
from collections import Counter

log = logging.getLogger(__name__)


class HelpPaginator(Pages):
    def __init__(self, help_command, ctx, entries, *, per_page=4):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.title = ''
        self.description = ''
        self.prefix = help_command.clean_prefix
        self.total = len(entries)
        self.help_command = help_command
        if ctx.author.id not in ctx.bot.front_help_page_false:
            self.show_first_help = True
            ctx.bot.front_help_page_false.append(ctx.author.id)
        else:
            self.show_first_help = False

    def get_first_page(self):
        self.title = 'The Donation Tracker Bot Help'
        description = 'This is the help command for the bot.\nA few points to notice:\n\n' \
                      '• This command is powered by reactions: \n' \
                      ':track_previous: goes to the first page\n' \
                      ':arrow_backward: goes to the previous page\n' \
                      ':arrow_forward: goes to the next page\n' \
                      ':track_next: goes to the last page\n' \
                      ':1234: lets you type a page number to go to\n' \
                      ':stop_button: stops the interactive pagination session\n\n' \
                      '• Help for a specific command can be found with `+help commandname`\n' \
                      '• e.g `+help don` or `+help donationboard create`.\n\n' \
                      '• Press :arrow_forward: to proceed.'
        self.description = description
        self.prepare_embed([], 1)
        return self.embed

    def get_bot_page(self, page):
        cog, description, commands = self.entries[page - 1]
        self.title = f'{cog} Commands'
        self.description = description
        return commands

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = f'{self.description}\n\u200b'
        self.embed.title = self.title

        self.embed.set_footer(text=f'Use "{self.prefix}help command" for more info on a command.')
        self.embed.timestamp = datetime.utcnow()

        for i, entry in enumerate(entries):
            sig = f'{self.help_command.get_command_signature(command=entry)}'
            fmt = entry.short_doc or "No help given"
            self.embed.add_field(name=sig,
                                 value=fmt + '\n\u200b' if i == (len(entries) - 1) else fmt,
                                 inline=False
                                 )

        self.embed.add_field(name='Support', value='Problem? Bug? Please join the support '
                                                   'server for more help: '
                                                   'https://discord.gg/ePt8y4V')

        if self.maximum_pages:
            self.embed.set_author(name=f'Page {page}/{self.maximum_pages} ({self.total} commands)')

    # async def get_embed(self, entries, page, *, first=False):
    #     if first and self.show_first_help:
    #         self.show_first_help = False
    #         return self.get_first_page()
    #
    #     self.prepare_embed(entries, page, first=first)
    #     return self.embed
    #
    # async def paginate(self):
    #     if self.show_first_help:
    #         self.paginating = True
    #         self.maximum_pages += 1
    #     await super().paginate()


class HelpCommand(commands.HelpCommand):
    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = ', '.join(command.aliases)
            fmt = f'[aliases: {aliases}]'
            if parent:
                fmt = f'{self.clean_prefix}{parent} {fmt}'
            else:
                fmt = f'{self.clean_prefix}{command.name} {fmt}'
            alias = fmt
        else:
            alias = f'{self.clean_prefix}{parent} {command.name}'
        return alias

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bNo Category'

        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        nested_pages = []
        per_page = 9
        total = 0

        for cog, commands in itertools.groupby(entries, key=key):
            commands = sorted(commands, key=lambda c: c.name)
            if len(commands) == 0:
                continue

            total += len(commands)
            actual_cog = bot.get_cog(cog)
            # get the description if it exists (and the cog is valid) or return Empty embed.
            description = (actual_cog and actual_cog.description) or discord.Embed.Empty
            nested_pages.extend((cog, description, commands[i:i + per_page])
                                for i in range(0, len(commands), per_page
                                               )
                                )

        # a value of 1 forces the pagination session
        pages = HelpPaginator(self, self.context, entries=nested_pages, per_page=1)

        # swap the get_page implementation to work with our nested pages.
        pages.is_bot = True
        pages.total = total
        pages.get_page = pages.get_bot_page
        await self.context.release()
        await pages.paginate()

    async def send_cog_help(self, cog):
        entries = await self.filter_commands(cog.get_commands(), sort=True)
        pages = HelpPaginator(self, self.context, entries)
        pages.title = f'{cog.qualified_name} Commands'
        pages.description = f'{cog.description}\n\n'

        await self.context.release()
        await pages.paginate()

    def common_command_formatting(self, page_or_embed, command):
        page_or_embed.title = self.get_command_signature(command)
        if command.description:
            page_or_embed.description = f'{command.description}\n\n{command.help}'
        else:
            page_or_embed.description = command.help or 'No help found...'

    async def send_command_help(self, command):
        # No pagination necessary for a single command.
        embed = discord.Embed(colour=discord.Colour.blurple())
        self.common_command_formatting(embed, command)
        await self.context.send(embed=embed)

    async def send_group_help(self, group):
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        pages = HelpPaginator(self, self.context, entries)
        self.common_command_formatting(pages, group)

        await self.context.release()
        await pages.paginate()


class Info(commands.Cog):
    """Misc commands related to the bot."""
    def __init__(self, bot):
        self.bot = bot
        bot.help_command = HelpCommand()
        bot.help_command.cog = self
        self.bot.invite = self.invite_link
        self.bot.support_invite = self.support_invite
        self.bot.front_help_page_false = []

        self.dblpy = dbl.DBLClient(self.bot, self.bot.dbl_token)
        self.dbl_task.start()

        self.process = psutil.Process()
        self.cog_before_invoke = bot.get_cog('GuildSetup').cog_before_invoke
        self.cog_after_invoke = bot.get_cog('GuildSetup').cog_after_invoke

    @tasks.loop(time=time(hour=0))
    async def dbl_task(self):
        log.info('Attempting to post server count')
        try:
            await self.dblpy.post_guild_count()
            log.info('Posted server count ({})'.format(self.dblpy.guild_count()))
        except Exception as e:
            log.exception('Failed to post server count\n{}: {}'.format(type(e).__name__, e))

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        await error_handler(ctx, error)

    async def bot_check(self, ctx):
        if ctx.guild is None:
            await ctx.send(f'This command cannot be used in private messages. '
                           f'Please invite the bot to a server with '
                           f'the invite: {self.invite_link}')
            return False
        return True

    @property
    def invite_link(self):
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
        return discord.utils.oauth_url(self.bot.client_id, perms)

    @property
    def support_invite(self):
        return 'https://discord.gg/ePt8y4V'

    @commands.command(aliases=['join'])
    async def invite(self, ctx):
        """Get an invite to add the bot to your server.
        """
        await ctx.send(f'<{self.invite_link}>')

    @commands.command()
    async def support(self, ctx):
        """Get an invite link to the support server."""
        await ctx.send(f'<{self.support_invite}>')

    @commands.command(aliases=['patreon', 'patrons'])
    async def patron(self, ctx):
        e = discord.Embed(
            title='Donation Tracker Patrons',
            colour=self.bot.colour
        )
        e.description = 'Patreon provides funds to keep the Donation Tracker servers alive, ' \
                        'and to enable future development.\n\nTracking donations requires a lot of ' \
                        'processing power; that\'s how you can help!\n\nAs a patron, ' \
                        'you will get a few special rewards:\n' \
                        '• A special hoisted role and a secret patreon channel\n' \
                        '• Ability to claim more than 4 clans per guild.\n' \
                        '• The nice warm fuzzy feeling knowing you\'re keeping the ' \
                        'bot free for everyone else.\n\n' \
                        '[Link to sign up](https://www.patreon.com/join/donationtracker?)' \
                        '\n\nThese are our current patrons!\n• '
        e.description += '\n• '.join(str(n) for n in self.bot.get_guild(594276321937326091).members if
                                     any(r.id == 605349824472154134 for r in n.roles))
        await ctx.send(embed=e)

    @commands.command()
    async def feedback(self, ctx, *, content):
        """Give feedback on the bot.
        """
        e = discord.Embed(title='Feedback', colour=discord.Colour.green())
        channel = self.bot.get_channel(595384367573106718)
        if channel is None:
            return

        e.set_author(name=str(ctx.author), icon_url=ctx.author.avatar_url)
        e.description = content
        e.timestamp = ctx.message.created_at

        if ctx.guild is not None:
            e.add_field(name='Guild', value=f'{ctx.guild.name} (ID: {ctx.guild.id})', inline=False)

        e.add_field(name='Channel', value=f'{ctx.channel} (ID: {ctx.channel.id})', inline=False)
        e.set_footer(text=f'Author ID: {ctx.author.id}')

        await channel.send(embed=e)
        await ctx.send(f'{ctx.tick(True)} Successfully sent feedback')

    @commands.command(hidden=True)
    async def ping(self, ctx):
        await ctx.send(f'Pong! {self.bot.latency*1000:.2f}ms')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def process(self, ctx):
        memory_usage = self.process.memory_full_info().uss / 1024 ** 2
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        await ctx.send(f'{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def tasks(self, ctx):
        task_retriever = asyncio.Task.all_tasks
        all_tasks = task_retriever(loop=self.bot.loop)

        event_tasks = [
            t for t in all_tasks
            if 'Client._run_event' in repr(t) and not t.done()
        ]

        cogs_directory = os.path.dirname(__file__)
        tasks_directory = os.path.join('discord', 'ext', 'tasks', 'init.py')
        inner_tasks = [
            t for t in all_tasks
            if cogs_directory in repr(t) or tasks_directory in repr(t)
        ]

        bad_inner_tasks = ", ".join(hex(id(t)) for t in inner_tasks if t.done() and t._exception is not None)
        embed = discord.Embed()
        embed.add_field(name='Inner Tasks',
                        value=f'Total: {len(inner_tasks)}\nFailed: {bad_inner_tasks or "None"}')
        embed.add_field(name='Events Waiting', value=f'Total: {len(event_tasks)}', inline=False)
        await ctx.send(embed=embed)

    @commands.group(hidden=True)
    async def info(self, ctx):
        pass
    # TODO: maybe need some stats on in events and what not for donationboard/trophyboard info.

    @info.command(name='donationboard')
    @requires_config('donationboard')
    async def donationboard_info(self, ctx):
        """Gives you info about guild's donationboard.
        """
        table = CLYTable()
        if ctx.config.render == 2:
            table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                            [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                            ])
            table.title = ctx.config.title or 'DonationBoard'
            render = table.render_option_2()
        else:
            table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                            [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                            ])
            table.title = ctx.config.title or 'DonationBoard'
            render = table.render_option_1()

        fmt = f'**DonationBoard Example Format:**\n\n{render}\n**Icon:** ' \
            f'Please see the icon displayed above.\n'

        channel = ctx.config.channel
        data = []

        if channel is None:
            data.append('**Channel:** #deleted-channel')
        else:
            data.append(f'**Channel:** {channel.mention}')

        query = "SELECT clan_name, clan_tag FROM clans WHERE guild_id = $1;"
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        data.append(f"**Clans:** {', '.join(f'{n[0]} ({n[1]})' for n in fetch)}")

        fmt += '\n'.join(data)

        e = discord.Embed(colour=self.bot.colour,
                          description=fmt)
        e.set_author(name='DonationBoard Info',
                     icon_url=ctx.config.icon_url or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        await ctx.send(embed=e)

    @info.command(name='trophyboard')
    @requires_config('trophyboard')
    async def donationboard_info(self, ctx):
        """Gives you info about guild's trophyboard.
        """
        # TODO: fix this when we get new renders for trophyboard
        table = CLYTable()
        if ctx.config.render == 2:
            table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                            [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                            ])
            table.title = ctx.config.title or 'TrophyBoard'
            render = table.render_option_2()
        else:
            table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                            [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                            ])
            table.title = ctx.config.title or 'TrophyBoard'
            render = table.render_option_1()

        fmt = f'**Trophyboard Example Format:**\n\n{render}\n**Icon:** ' \
            f'Please see the icon displayed above.\n'

        channel = ctx.config.channel
        data = []

        if channel is None:
            data.append('**Channel:** #deleted-channel')
        else:
            data.append(f'**Channel:** {channel.mention}')

        query = "SELECT clan_name, clan_tag FROM clans WHERE guild_id = $1;"
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        data.append(f"**Clans:** {', '.join(f'{n[0]} ({n[1]})' for n in fetch)}")

        fmt += '\n'.join(data)

        e = discord.Embed(colour=self.bot.colour,
                          description=fmt)
        e.set_author(name='TrophyBoard Info',
                     icon_url=ctx.config.icon_url or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        await ctx.send(embed=e)

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

        await self.bot.join_log_webhook.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53dda4, title='New Guild')  # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING"
        await self.bot.pool.execute(query, guild.id)
        fmt = '**Some handy hints:**\n' \
              f'• My prefix is `+`, or {self.bot.user.mention}\n' \
              '• All commands have super-detailed help commands; please use them!\n' \
              '• Usage: `+help command_name`\n\n' \
              'A few frequently used ones to get started:\n' \
              '• `+help addclan`\n' \
              '• `+help donationboard` and `+help donationboard create`\n' \
              '• `+help log` and `+help log create`\n\n' \
              '• There are lots of how-to\'s and other ' \
              'support on the [support server](https://discord.gg/ePt8y4V) if you get stuck.\n' \
              f'• Please share the bot with your friends! [Bot Invite]({self.invite})\n' \
              '• Please support us on [Patreon](https://www.patreon.com/donationtracker)!\n' \
              '• Have a good day!'
        e = discord.Embed(colour=self.bot.colour,
                          description=fmt)
        e.set_author(name='Hello! I\'m the Donation Tracker!',
                     icon_url=self.bot.user.avatar_url
                     )

        if guild.system_channel:
            try:
                await guild.system_channel.send(embed=e)
                return
            except (discord.Forbidden, discord.HTTPException):
                pass
        for c in guild.channels:
            if not isinstance(c, discord.TextChannel):
                continue
            if c.permissions_for(c.guild.get_member(self.bot.user.id)).send_messages:
                try:
                    await c.send(embed=e)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        e = discord.Embed(colour=0xdd5f53, title='Left Guild')  # red colour
        await self.send_guild_stats(e, guild)
        query = "UPDATE guilds SET log_toggle = False, updates_toggle = False WHERE guild_id = $1"
        await self.bot.pool.execute(query, guild.id)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        self.bot.command_stats[command] += 1
        message = ctx.message
        if ctx.guild is None:
            guild_id = None
        else:
            guild_id = ctx.guild.id

        query = """INSERT INTO commands (guild_id, channel_id, author_id, used, prefix, command)
                           VALUES ($1, $2, $3, $4, $5, $6)
                """

        await self.bot.pool.execute(query, guild_id, ctx.channel.id, ctx.author.id,
                                    message.created_at, ctx.prefix, command
                                    )

    async def send_claim_clan_stats(self, e, clan, guild):
        e.add_field(name='Name', value=clan.name)
        e.add_field(name='Tag', value=clan.tag)

        total = len(clan.members)
        e.add_field(name='Member Count', value=str(total))

        if clan.badge:
            e.set_thumbnail(url=clan.badge.url)

        e.add_field(name='Guild Name', value=guild.name)
        e.add_field(name='Guild ID', value=guild.id)
        e.add_field(name='Guild Owner', value=f'{guild.owner} (ID: {guild.owner.id})')

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count
        online = sum(m.status is discord.Status.online for m in guild.members)
        e.add_field(name='Guild Members', value=str(total))
        e.add_field(name='Guild Bots', value=f'{bots} ({bots / total:.2%})')
        e.add_field(name='Guild Online', value=f'{online} ({online / total:.2%})')

        if guild.me:
            e.set_footer(text='Bot Added').timestamp = guild.me.joined_at

        await self.bot.join_log_webhook.send(embed=e)

    @commands.Cog.listener()
    async def on_clan_claim(self, ctx, clan):
        e = discord.Embed(colour=0x53dda4, title='Clan Claimed')  # green colour
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.donationboard.update_clan_tags()
        self.bot.get_guilds.invalidate(self.bot, clan.tag)
        self.bot.get_clans.invalidate(self.bot, ctx.guild.id)
        await self.bot.events.sync_temp_event_tasks()

    @commands.Cog.listener()
    async def on_clan_unclaim(self, ctx, clan):
        e = discord.Embed(colour=0xdd5f53, title='Clan Unclaimed')  # green colour
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.donationboard.update_clan_tags()
        self.bot.get_guilds.invalidate(self.bot, clan.tag)
        self.bot.get_clans.invalidate(self.bot, ctx.guild.id)
        await self.bot.events.sync_temp_event_tasks()


def setup(bot):
    if not hasattr(bot, 'command_stats'):
        bot.command_stats = Counter()

    bot.add_cog(Info(bot))
