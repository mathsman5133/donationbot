import logging
import dbl
import psutil
import os
import asyncio
import discord
import itertools
import math

from discord.ext import commands, tasks
from cogs.utils.paginator import Pages
from cogs.utils.error_handler import error_handler
from cogs.utils.db_objects import SlimEventConfig
from cogs.utils.formatters import CLYTable, readable_time, TabularData
from cogs.utils.emoji_lookup import misc
from cogs.utils.checks import requires_config
from datetime import datetime, time
from collections import Counter

log = logging.getLogger(__name__)


class HelpPaginator(Pages):
    def __init__(self, help_command, ctx, entries, *, per_page=9):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.ctx = ctx
        self.embed.colour = discord.Colour.green()
        self.title = ''
        self.description = ''
        self.prefix = help_command.clean_prefix
        self.total = len(entries)
        self.help_command = help_command
        self.reaction_emojis = [
            ('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
            ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
            ('\N{INPUT SYMBOL FOR NUMBERS}', self.numbered_page),
            ('\N{WHITE QUESTION MARK ORNAMENT}', self.show_help)
        ]

    def get_bot_page(self, page):
        cog, description, commands = self.entries[page - 1]
        self.title = cog.qualified_name
        self.description = description
        return commands

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.title = self.title
        self.embed.description = self.description

        self.embed.set_footer(text=f'Use the reactions to navigate pages, '
                                   f'and "{self.prefix}help command" for more help.')
        self.embed.timestamp = datetime.utcnow()

        for i, entry in enumerate(entries):
            sig = f'{self.help_command.get_command_signature(command=entry)}'
            fmt = misc['online'] + entry.short_doc
            if entry.short_doc.startswith('[Group]'):
                fmt += f"\n{misc['idle']}Use `{self.prefix}help {entry.name}` for subcommands."
            if not entry._can_run:
                fmt += f"\n{misc['offline']}You don't have the required permissions to run this command."

            self.embed.add_field(name=sig,
                                 value=fmt + '\n\u200b' if i == (len(entries) - 1) else fmt,
                                 inline=False
                                 )

        self.embed.add_field(name='Support', value='Problem? Bug? Please join the support '
                                                   'server for more help: '
                                                   'https://discord.gg/ePt8y4V')

        if self.maximum_pages:
            self.embed.set_author(name=f'Page {page}/{self.maximum_pages} ({self.total} commands)')

    async def show_help(self):
        self.title = 'The Donation Tracker Bot Help'
        description = 'This is the help command for the bot.\nA few points to notice:\n\n' \
                      f"{misc['online']}This command is powered by reactions: \n" \
                      ':arrow_backward: goes to the previous page\n' \
                      ':arrow_forward: goes to the next page\n' \
                      ':1234: lets you type a page number to go to\n' \
                      ':grey_question: Takes you to this page\n' \
                      f"{misc['online']}Help for a specific command can be found with `+help commandname`\n" \
                      f"{misc['online']}e.g `+help don` or `+help add donationboard`.\n\n" \
                      f"{misc['online']}Press :arrow_forward: to proceed."

        self.description = description
        embed = self.embed.copy() if self.embed else discord.Embed(colour=self.bot.colour)
        embed.clear_fields()
        embed.description = description
        embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(content=None, embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(60.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())


class HelpCommand(commands.HelpCommand):
    def get_command_signature(self, command):
        parent = command.full_parent_name

        aliases = self.context.bot.get_cog('Aliases').get_aliases(command.full_parent_name)
        if aliases:
            if parent:
                return f'{self.clean_prefix}{parent} or {self.clean_prefix}{aliases}'
            return f'{self.clean_prefix}{command.name} or {self.clean_prefix}{aliases}'
        else:
            if parent:
                return f'{self.clean_prefix}{parent} {command.name}'
            return f'{self.clean_prefix}{command.name}'

    async def send_bot_help(self, mapping):
        def key(c):
            return c.cog_name or '\u200bNo Category'

        bot = self.context.bot
        entries = await self.filter_commands(bot.commands, sort=True, key=key)
        nested_pages = []
        per_page = 9
        total = len(entries)

        for cog, commands in itertools.groupby(entries, key=key):
            def key(c):
                if c.short_doc.startswith('[Group]'):
                    c.name = f'\u200b{c.name}'
                return c.name
            commands = sorted(commands, key=key)
            if len(commands) == 0:
                continue

            total += len(commands)
            actual_cog = bot.get_cog(cog)
            # get the description if it exists (and the cog is valid) or return Empty embed.
            description = actual_cog.description or discord.Embed.Empty
            nested_pages.extend((actual_cog, description, commands[i:i + per_page])
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

    async def filter_commands(self, _commands, *, sort=False, key=None):
        self.verify_checks = False
        valid = await super().filter_commands(_commands, sort=sort, key=key)
        for n in valid:
            try:
                can_run = await n.can_run(self.context)
                n._can_run = can_run
            except commands.CommandError:
                n._can_run = False
        return valid

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


class Info(commands.Cog, name='\u200bInfo'):
    """Misc commands related to the bot."""
    def __init__(self, bot):
        self.bot = bot

        bot.help_command = HelpCommand()
        bot.help_command.cog = self
        bot.invite = self.invite_link
        bot.support_invite = self.support_invite
        bot.front_help_page_false = []

        self.dbl_client = dbl.DBLClient(self.bot, self.bot.dbl_token)
        self.dbl_task.start()

        self.process = psutil.Process()

    def cog_unload(self):
        self.dbl_task.cancel()

    async def cog_before_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.before_invoke(ctx)

    async def cog_after_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.after_invoke(ctx)

    @tasks.loop(time=time(hour=0))
    async def dbl_task(self):
        log.info('Attempting to post server count')
        try:
            await self.dbl_client.post_guild_count()
            log.info('Posted server count ({})'.format(self.dbl_client.guild_count()))
        except Exception as e:
            log.exception('Failed to post server count\n{}: {}'.format(type(e).__name__, e))

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

    @property
    def welcome_message(self):
        fmt = '**Some handy hints:**\n' \
            f'• My prefix is `+`, or {self.bot.user.mention}\n' \
              '• All commands have super-detailed help commands; please use them!\n' \
              '• Usage: `+help command_name`\n\n' \
              'A few frequently used ones to get started:\n' \
              '• `+help add` (check out the subcommands)\n' \
              '• `+help info` (check out the subcommands)\n\n' \
              '• There are lots of how-to\'s and other ' \
              'support on the [support server](https://discord.gg/ePt8y4V) if you get stuck.\n' \
            f'• Please share the bot with your friends! [Bot Invite]({self.invite_link})\n' \
              '• Please support us on [Patreon](https://www.patreon.com/donationtracker)!\n' \
              '• Have a good day!'
        e = discord.Embed(colour=self.bot.colour,
                          description=fmt)
        e.set_author(name='Hello! I\'m the Donation Tracker!',
                     icon_url=self.bot.user.avatar_url
                     )
        return e

    @commands.command(aliases=['join'])
    async def invite(self, ctx):
        """Get an invite to add the bot to your server."""
        await ctx.send(f'<{self.invite_link}>')

    @commands.command()
    async def support(self, ctx):
        """Get an invite link to the support server."""
        await ctx.send(f'<{self.support_invite}>')

    @commands.command(aliases=['patreon', 'patrons'])
    async def patron(self, ctx):
        """Get information about the bot's patreon."""
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
        """Give feedback on the bot."""
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

    @commands.command()
    async def welcome(self, ctx):
        """Displays my welcome message."""
        await ctx.send(embed=self.welcome_message)

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

    @commands.group(invoke_without_subcommand=True)
    async def info(self, ctx):
        """[Group] Allows the user to get info about a variety of the bot's features."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @info.command(name='log')
    async def info_log(self, ctx):
        """Get information about donation log channels for the guild.

        Example
        -----------
        • `+log info`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        e = discord.Embed(color=self.bot.colour,
                          description=f'Donation Log info for {ctx.guild}.')

        query = """SELECT channel_id,
                          interval,
                          toggle,
                          type
                   FROM logs
                   WHERE guild_id = $1
                   ORDER BY type
                """
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        for n in fetch:
            fmt = f"Channel: <#{n['channel_id']}> (ID: {n['channel_id']})\n" \
                f"Toggle: {'Enabled' if n['toggle'] else 'Disabled'}\n" \
                f"Interval: {int(n['interval'].total_seconds() / 60)}min"
            e.add_field(name=f"{n['type'].capitalize()} Log", value=fmt)

        query = """SELECT clan_tag, 
                          clan_name,
                          channel_id 
                   FROM clans 
                   WHERE guild_id=$1
                   ORDER BY channel_id
                """
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        fmt = '\n'.join(f"• {n['clan_name']} ({n['clan_tag']}) --> <#{n['channel_id']}>" for n in fetch) or 'No Clans.'
        e.add_field(name='Clans',
                    value=fmt if len(fmt) < 1024 else f'{fmt[:1000]}...')

        await ctx.send(embed=e)

    @info.command(name='donationboard')
    @requires_config('donationboard')
    async def info_donationboard(self, ctx):
        """Gives you info about guild's donationboard.
        """
        if not ctx.config:
            return await ctx.send('Please setup a donationboard using `+add donationboard`.')

        table = CLYTable()
        if ctx.config.render == 2:
            table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                            [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                            ])
            table.title = ctx.config.title or 'DonationBoard'
            render = table.donationboard_2()
        else:
            table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                            [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                            ])
            table.title = ctx.config.title or 'DonationBoard'
            render = table.donationboard_1()

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
                          description=fmt if len(fmt) < 2048 else f'{fmt[:2040]}...')

        e.set_author(name='DonationBoard Info',
                     icon_url=ctx.config.icon_url or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        await ctx.send(embed=e)

    @info.command(name='trophyboard')
    @requires_config('trophyboard')
    async def info_trophyboard(self, ctx):
        """Gives you info about guild's trophyboard.
        """
        if not ctx.config:
            return await ctx.send('Please setup a trophyboard using `+add trophyboard`.')

        table = CLYTable()
        if ctx.config.render == 1:
            table.add_rows([[0, 4320, 955, 'Member Name'], [1, 4500, 870, 'Another Member'],
                            [2, 3900, -600, 'Yet Another'], [3, 1500, -1000, 'Worst Pusher']
                            ])

            table.title = ctx.config.title or 'TrophyBoard'
            render = table.trophyboard_1()
        else:
            table.add_rows([[0, 2000, 'Member'], [1, 1500, 'Nearly #1'],
                            [2, 1490, 'Another Member'], [3, -600, 'Winner']
                            ])

            table.title = ctx.config.title or 'TrophyBoard'
            render = table.trophyboard_2()

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
                          description=fmt if len(fmt) < 2048 else f'{fmt[:2040]}...')
        e.set_author(name='TrophyBoard Info',
                     icon_url=ctx.config.icon_url or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        await ctx.send(embed=e)

    @info.command(name='event')
    @requires_config('event', invalidate=True)
    async def info_event(self, ctx):
        """Gives you info about guild's event"""
        if not ctx.config:
            return await ctx.send('Please setup an event using `+add event`.')

        e = discord.Embed(colour=self.bot.colour)

        e.set_author(name=f'Event Information: {ctx.config.event_name}')

        now = datetime.utcnow()
        start_seconds = (ctx.config.start - now).total_seconds()
        end_seconds = (ctx.config.finish - now).total_seconds()

        fmt = f':name_badge: **Name:** {ctx.config.event_name}\n' \
              f':id: **Event ID:** {ctx.config.id}\n' \
              f"{misc['green_clock']} **{'Starts In ' if start_seconds > 0 else 'Started'}:**" \
              f" {readable_time(start_seconds)}\n" \
              f":alarm_clock: **{'Ends In' if end_seconds > 0 else 'Ended'}:** {readable_time(end_seconds)}\n"

        channel = self.bot.get_channel(ctx.config.channel_id)
        data = []

        if channel is None:
            data.append(f"{misc['number']}**Updates Channel:** #deleted-channel")
        else:
            data.append(f"{misc['number']}**Updates Channel:** {channel.mention}")

        query = "SELECT DISTINCT clan_tag, clan_name FROM clans WHERE guild_id = $1 AND in_event=True ORDER BY clan_name;"
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        e.add_field(name='Participating Clans',
                    value='\n'.join(f"{misc['online']}{n[1]} ({n[0]})" for n in fetch) or 'None Found.'
                    )

        fmt += '\n'.join(data)
        e.description = fmt

        await ctx.send(embed=e)

    @info.command(name='events')
    async def info_events(self, ctx):
        """GET Event IDs and start/finish times for events."""
        query = "SELECT id, event_name, start, finish FROM events WHERE guild_id = $1 ORDER BY start DESC"
        fetch = await ctx.db.fetch(query, ctx.guild.id)
        table = TabularData()
        table.set_columns(['ID', 'Name', 'Start', 'Finish'])
        for n in fetch:
            table.add_row([n[0], n[1], n[2].strftime('%d-%b-%Y'), n[3].strftime('%d-%b-%Y')])

        e = discord.Embed(colour=self.bot.colour,
                          description=f'```\n{table.render()}\n```',
                          title='Event Info',
                          timestamp=datetime.utcnow()
                          )
        await ctx.send(embed=e)

    @info.command(name='season')
    async def info_season(self, ctx):
        """Get Season IDs and start/finish times and info."""
        query = "SELECT id, start, finish FROM seasons ORDER BY id DESC"
        fetch = await ctx.db.fetch(query)
        table = TabularData()
        table.set_columns(['ID', 'Start', 'Finish'])
        for n in fetch:
            table.add_row([n[0], n[1].strftime('%d-%b-%Y'), n[2].strftime('%d-%b-%Y')])

        e = discord.Embed(colour=self.bot.colour,
                          description=f'```\n{table.render()}\n```',
                          title='Season Info',
                          timestamp=datetime.utcnow()
                          )
        e.add_field(name='Current Season',
                    value=readable_time((fetch[0][2] - datetime.utcnow()).total_seconds())[:-4] + ' left',
                    inline=False)
        await ctx.send(embed=e)

def setup(bot):
    if not hasattr(bot, 'command_stats'):
        bot.command_stats = Counter()

    bot.add_cog(Info(bot))
