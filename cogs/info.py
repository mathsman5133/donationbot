import logging
import psutil
import os
import asyncio
import discord
import itertools
import io
import math
import copy

from matplotlib import pyplot as plt

from discord.ext import commands
from cogs.utils.paginator import Pages, EmbedPages
from cogs.utils.formatters import CLYTable, readable_time, TabularData
from cogs.utils.emoji_lookup import misc
from cogs.utils.checks import requires_config
from cogs.utils.converters import GlobalChannel
from datetime import datetime
from collections import Counter

log = logging.getLogger(__name__)

WELCOME_MESSAGE = """
Some handy hints:

 • My prefix is `+`, or <@!427301910291415051>. See how to change it with `+help edit prefix`
 • All commands have super-detailed help commands; please use them!
 • Usage: `+help command_name`. For example, try `+help donationlog`

 
A few frequently used commands to get started:

 • `+help add` (check out the subcommands)
 • `+add donationlog #channel #clantag` will setup a donationlog for your clan.
 • `+add boards #clantag` will setup donation and trophyboards for your clan.
 • `+info` will show you info about boards and logs on the server.

 
Other Info:

 • There are lots of how-to's and other support on the [support server](https://discord.gg/ePt8y4V) if you get stuck.
 • Please share the bot with your friends! [Bot Invite]({self.invite_link})
 • Please support us on [Patreon](https://www.patreon.com/donationtracker)!
 • Have a good day!
"""


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
        if hasattr(cog, 'qualified_name'):
            self.title = cog.qualified_name
        else:
            self.title = cog.name
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
    async def command_callback(self, ctx, *, command=None):
        category = self.context.bot.get_category(command)
        if category:
            return await self.send_category_help(category)
        return await super().command_callback(ctx, command=command)

    def get_command_signature(self, command):
        parent = command.full_parent_name

        aliases = self.context.bot.get_cog('\u200bAliases').get_aliases(command.full_parent_name)
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
            if c.cog:
                if hasattr(c.cog, 'category'):
                    return c.cog.category.name or '\u200bNo Category'
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
            actual_cog = bot.get_cog(cog) or bot.get_category(cog)
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

    async def send_category_help(self, category):
        entries = await self.filter_commands(category.commands, sort=True)
        pages = HelpPaginator(self, self.context, entries)
        pages.title = f'{category.name} Commands'
        pages.description = f'{category.description}\n\n'

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
        if isinstance(page_or_embed, discord.Embed):
            print(page_or_embed.to_dict())

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

        self.process = psutil.Process()

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
        e = discord.Embed(colour=self.bot.colour, description=WELCOME_MESSAGE)
        e.set_author(name='Hello! I\'m the Donation Tracker!', icon_url=self.bot.user.avatar_url)
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
        stats = self.bot.coc.http.stats.items()
        if len(stats) > 2:
            columns = 2
            rows = math.ceil(len(stats) / 2)
        else:
            columns = 1
            rows = len(stats)

        if len(stats) == 1:
            fig, (axs, ) = plt.subplots(rows, columns)
        else:
            fig, (*axs, ) = plt.subplots(rows, columns)

        for i, (key, values) in enumerate(stats):
            axs[i].bar(range(len(values)), list(values), color="blue")
            axs[i].set_ylabel(key)
        fig.suptitle(f"Latency for last minute to {datetime.utcnow().strftime('%H:%M %d/%m')}")
        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        fmt = "\n".join(f'Shard ID: {i}, Latency: {n*1000:.2f}ms' for i, n in self.bot.latencies)
        await ctx.send(f'Pong!\n{fmt}\nAverage Latency: {self.bot.latency*1000:.2f}ms', file=discord.File(b, f'cocapi.png'))
        plt.close()

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

    @commands.group(invoke_without_command=True)
    async def info(self, ctx, channel: GlobalChannel = None):
        """[Group] Allows the user to get info about a variety of the bot's features.

        Use this command to get info about all clans, boards and logs for the server.

        **Parameters**
        :key: A discord channel (#mention). If you don't have this, it will get info for all the channels in the server.

        **Format**
        :information_source: `+info`
        :information_source: `+info #CHANNEL`

        **Example**
        :white_check_mark: `+info`
        :white_check_mark: `+info #donationlog`
        """
        if ctx.invoked_subcommand:
            return

        channels = {channel.id} if channel else set()
        guild = channel and channel.guild or ctx.guild

        if not channels:
            query = "SELECT channel_id FROM logs WHERE guild_id = $1"
            log_channels = await ctx.db.fetch(query, guild.id)
            channels.update({n["channel_id"] for n in log_channels})

            query = "SELECT channel_id FROM boards WHERE guild_id = $1"
            board_channels = await ctx.db.fetch(query, guild.id)
            channels.update({n["channel_id"] for n in board_channels})

        embeds = []

        for channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            embed = discord.Embed(colour=self.bot.colour, description="")
            embed.set_author(name=f"Info for #{channel}", icon_url=guild.me.avatar_url)

            donationlog = await self.bot.utils.log_config(channel.id, "donation")
            if donationlog:
                embed.description += f"**DonationLog**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f"{misc['online'] + 'Enabled' if donationlog.toggle else misc['offline'] + 'Disabled'}\n" \
                                     f":hourglass: Wait time of {readable_time(donationlog.seconds)}\n\n"

            trophylog = await self.bot.utils.log_config(channel.id, "trophy")
            if trophylog:
                embed.description += f"**TrophyLog**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f"{misc['online'] + 'Enabled' if trophylog.toggle else misc['offline'] + 'Disabled'}\n" \
                                     f":hourglass: Wait time of {readable_time(trophylog.seconds)}\n\n"

            board = await self.bot.utils.board_config(channel.id)
            if board:
                embed.description += f"**{board.type.capitalize()}Board**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f":paperclip: [Icon URL]({board.icon_url})\n" \
                                     f":rosette: Render Type: *#{board.render}*\n" \
                                     f":chart_with_upwards_trend: Sorted by: *{board.sort_by}*\n" \
                                     f":notebook_with_decorative_cover: Title: *{board.title}*\n\n"

            query = "SELECT clan_tag FROM clans WHERE channel_id = $1"
            clan_tags = await ctx.db.fetch(query, channel.id)
            if clan_tags:
                embed.description += "**Clans**\n"
            async for clan in self.bot.coc.get_clans((n["clan_tag"] for n in clan_tags)):
                embed.description += f":notepad_spiral: {clan} ({clan.tag})\n" \
                                     f":paperclip: [In-Game Link]({clan.share_link})\n" \
                                     f":paperclips: [Icon URL]({clan.badge.url})\n" \
                                     f":person_bowing: Members: {clan.member_count}/50\n\n"

            if embed.description:
                embeds.append(embed)

        if not embeds:
            return await ctx.send(f"No info found. Try using `+help add`.")

        p = EmbedPages(ctx, entries=embeds, per_page=1)
        await p.paginate()

    @info.command(name="clan", aliases=["clans"])
    async def info_clans(self, ctx):
        """Gets info for all the clans in the server.

        **Format**
        :information_source: `+info clan`

        **Example**
        :white_check_mark: `+info clan`
        """
        clans = await ctx.get_clans()

        if not clans:
            return await ctx.send("Please see how to add a clan with `+help add clan`")

        embeds = []
        for clan in clans:
            embed = discord.Embed(description="")
            embed.set_author(name=f"{clan} ({clan.tag})", icon_url=clan.badge.medium)

            query = "SELECT channel_id FROM clans WHERE clan_tag = $1 AND guild_id = $2"
            channel_ids = [n["channel_id"] for n in await ctx.db.fetch(query, clan.tag, ctx.guild.id)]

            for channel_id in channel_ids:
                log_config = await self.bot.utils.log_config(channel_id, "donation")
                channel = self.bot.get_channel(channel_id)
                if not (log_config and channel):
                    continue

                embed.description += f"**DonationLog**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f"{misc['online'] + 'Enabled' if log_config.toggle else misc['offline'] + 'Disabled'}\n" \
                                     f":hourglass: Wait time of {readable_time(log_config.seconds)}\n\n"

            for channel_id in channel_ids:
                log_config = await self.bot.utils.log_config(channel_id, "trophy")
                channel = self.bot.get_channel(channel_id)

                if not (log_config and channel):
                    continue

                embed.description += f"**TrophyLog**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f"{misc['online'] + 'Enabled' if log_config.toggle else misc['offline'] + 'Disabled'}\n" \
                                     f":hourglass: Wait time of {readable_time(log_config.seconds)}\n\n"

            for channel_id in channel_ids:
                board_config = await self.bot.utils.board_config(channel_id)
                channel = self.bot.get_channel(channel_id)
                if not (board_config and channel):
                    continue

                embed.description += f"**{board_config.type.capitalize()}Board**\n" \
                                     f":notepad_spiral: {channel.mention}\n" \
                                     f":paperclip: [Icon URL]({board_config.icon_url})\n" \
                                     f":rosette: Render Type: *#{board_config.render}*\n" \
                                     f":chart_with_upwards_trend: Sorted by: *{board_config.sort_by}*\n" \
                                     f":notebook_with_decorative_cover: Title: *{board_config.title}*\n\n"

            embeds.append(embed)

        p = EmbedPages(ctx, entries=embeds, per_page=1)
        await p.paginate()

    @info.command(name='log', disabled=True, hidden=True)
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

    @info.command(name='donationboard', disabled=True, hidden=True)
    @requires_config('donationboard', error=True)
    async def info_donationboard(self, ctx):
        """Gives you info about guild's donationboard.
        """
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

    @info.command(name='trophyboard', disabled=True, hidden=True)
    @requires_config('trophyboard', error=True)
    async def info_trophyboard(self, ctx):
        """Gives you info about guild's trophyboard.
        """
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
    @requires_config('event', invalidate=True, error=True)
    async def info_event(self, ctx, id_: int = None):
        """Gives you info about guild's event"""
        if not ctx.config and not (id_ and await self.bot.is_owner(ctx.author)):
            return await ctx.send('Please setup an event using `+add event`.')
        if id_:
            ctx.config = await ctx.bot.utils.event_config_id(id_)

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
        fetch = await ctx.db.fetch(query, ctx.config.guild_id)

        e.add_field(name='Participating Clans',
                    value='\n'.join(f"{misc['online']}{n[1]} ({n[0]})" for n in fetch) or 'None Found.'
                    )

        fmt += '\n'.join(data)
        e.description = fmt

        await ctx.send(embed=e)

    @info.command(name='events')
    async def info_events(self, ctx):
        """GET Event IDs and start/finish times for events."""
        if not await self.bot.is_owner(ctx.author):
            query = "SELECT id, event_name, start, finish FROM events WHERE guild_id = $1 ORDER BY start DESC"
            fetch = await ctx.db.fetch(query, ctx.guild.id)
        else:
            query = "SELECT id, event_name, start, finish FROM events ORDER BY start DESC"
            fetch = await ctx.db.fetch(query)

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

    async def say_permissions(self, ctx, member, channel):
        permissions = channel.permissions_for(member)
        allowed, denied = [], []
        for name, value in permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)

        e = discord.Embed(colour=member.colour, title=f'Permissions for Donation Tracker in #{channel}')
        e.description = "**Allowed**" + "\n".join(f"{misc['online']}{n}" for n in allowed)
        await ctx.send(embed=e)

        e.description = "Denied" + f"\n".join(f"{misc['offline']}{n}" for n in denied)
        await ctx.send(embed=e)

    @commands.command(hidden=True, aliases=['perms'])
    async def permissions(self, ctx, channel: discord.TextChannel = None):
        await self.say_permissions(ctx, ctx.me, channel or ctx.channel)

    @commands.command(hidden=True)
    async def guildid(self, ctx):
        await ctx.send(ctx.guild.id)

    @commands.command(hidden=True)
    async def channelid(self, ctx):
        await ctx.send(f"Guild ID: {ctx.guild.id}\nChannel ID: {ctx.channel.id}")


def setup(bot):
    if not hasattr(bot, 'command_stats'):
        bot.command_stats = Counter()

    bot.add_cog(Info(bot))
