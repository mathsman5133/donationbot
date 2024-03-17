import logging
import psutil
import os
import asyncio
import discord
import itertools
import io
import math
import copy
import csv
import statistics

from matplotlib import pyplot as plt
import numpy as np

from discord import app_commands
from discord.ext import commands
from cogs.utils.db_objects import LogConfig, BoardConfig, SlimEventConfig
from cogs.utils.paginator import Pages, EmbedPages
from cogs.utils.formatters import CLYTable, readable_time, TabularData
from cogs.utils.emoji_lookup import misc
from cogs.utils.checks import requires_config
from cogs.utils.converters import GlobalChannel, ConvertToPlayers
from datetime import datetime
from collections import Counter

log = logging.getLogger(__name__)

WELCOME_MESSAGE = """
Some handy hints:

 • Type `/` to see some of my commands!
 • If you don't want to use slash commands, you can use <@!427301910291415051> command. For example, `@Donation Tracker help`.

 
A few frequently used commands to get started:

 • `/add` (check out the subcommands)
 • `/add donationlog #channel #clantag` will setup a donationlog for your clan.
 • `/setup-boards` will help you setup donation and trophyboards for your clan.

 
Other Info:

 • There are lots of how-to's and other support on the [support server](https://discord.gg/ePt8y4V) if you get stuck.
 • Please share the bot with your friends! [Bot Invite]({invite})
 • Please support us on [Patreon](https://www.patreon.com/donationtracker)!
 • Have a good day!
"""


class Help(commands.DefaultHelpCommand):
    def send_bot_help(self, mapping):
        return self.context.invoke(self.context.bot.get_command("help"))
    def send_cog_help(self, cog):
        return self.context.invoke(self.context.bot.get_command("help"), query=str(cog))
    def send_command_help(self, command):
        return self.context.invoke(self.context.bot.get_command("help"), query=str(command.qualified_name))
    def send_group_help(self, group):
        return self.context.invoke(self.context.bot.get_command("help"), query=str(group.qualified_name))


class Info(commands.Cog, name='\u200bInfo'):
    """Misc commands related to the bot."""
    def __init__(self, bot):
        self.bot = bot

        self._old_help = bot.help_command
        bot.help_command = Help()
        bot.remove_command("help")
        # bot.help_command = self.help()
        # bot.help_command.cog = self
        bot.invite = self.invite_link
        bot.support_invite = self.support_invite
        bot.front_help_page_false = []

        self.process = psutil.Process()

    def cog_unload(self):
        self.bot.help_command = self._old_help

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
        return discord.utils.oauth_url(self.bot.client_id, permissions=perms)

    @property
    def support_invite(self):
        return 'https://discord.gg/ePt8y4V'

    @property
    def welcome_message(self):
        e = discord.Embed(colour=self.bot.colour, description=WELCOME_MESSAGE.format(invite=self.invite_link))
        e.set_author(name='Hello! I\'m the Donation Tracker!', icon_url=self.bot.user.display_avatar.url)
        return e

    @app_commands.command(description="Get an invite to add the bot to your server.")
    async def invite(self, intr: discord.Interaction):
        """Get an invite to add the bot to your server."""
        await intr.response.send_message(f'<{self.invite_link}>')

    @app_commands.command(description="Get an invite link to the support server.")
    async def support(self, intr: discord.Interaction):
        """Get an invite link to the support server."""
        await intr.response.send_message(f'<{self.support_invite}>')

    @app_commands.command()
    async def welcome(self, intr: discord.Interaction):
        """Displays my welcome message."""
        await intr.response.send_message(embed=self.welcome_message)

    @commands.command()
    async def ping(self, ctx):
        # stats = self.bot.coc.http.stats
        # med = []
        # l_err = []
        # h_err = []
        # for key, perf in stats.items():
        #     median = statistics.median(perf)
        #     l_err.append(median - statistics.median_low(perf))
        #     h_err.append(statistics.median_high(perf) - median)
        #     med.append(median)
        #
        # y_pos = np.arange(len(stats))
        # fig, ax = plt.subplots()
        # ax.barh(y_pos, med, xerr=[l_err, h_err])
        # ax.set_yticks(y_pos)
        # ax.set_yticklabels([k.replace("locations/global", "loc") for k in stats.keys()])
        # ax.invert_yaxis()  # labels read top-to-bottom
        # ax.set_xlabel("Median Latency (ms)")
        # ax.set_title("Median COC API Latency by Endpoint.")
        #
        # plt.tight_layout()
        # b = io.BytesIO()
        # plt.savefig(b, format='png', pad_inches=0.2)
        # b.seek(0)
        fmt = "\n".join(f'Shard ID: {i}, Latency: {n*1000:.2f}ms' for i, n in self.bot.latencies)
        await ctx.send(f'Pong!\n{fmt}\nAverage Latency: {self.bot.latency*1000:.2f}ms')
        # await ctx.send(f'Pong!\n{fmt}\nAverage Latency: {self.bot.latency*1000:.2f}ms', file=discord.File(b, f'cocapi.png'))
        plt.close()

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

            query = "SELECT channel_id FROM clans WHERE guild_id = $1"
            clan_channels = await ctx.db.fetch(query, guild.id)
            channels.update({n["channel_id"] for n in clan_channels})

        embeds = []

        for channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            embed = discord.Embed(colour=self.bot.colour, description="")
            embed.set_author(name=f"Info for #{channel}", icon_url=guild.me.avatar.url)

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

            fetch = await ctx.db.fetch("SELECT * FROM boards WHERE channel_id = $1", channel_id)
            for row in fetch:
                board_config = BoardConfig(bot=self.bot, record=row)

                embed.description += f"**{board_config.type.capitalize()}Board**\n" \
                                     f":notepad_spiral: {board_config.channel.mention}\n" \
                                     f":paperclip: [Background URL]({board_config.icon_url})\n" \
                                     f":chart_with_upwards_trend: Sorted by: *{board_config.sort_by}*\n" \
                                     f":notebook_with_decorative_cover: Title: *{board_config.title}*\n\n"

            query = "SELECT clan_tag, fake_clan FROM clans WHERE channel_id = $1"
            clan_tags = await ctx.db.fetch(query, channel.id)
            if clan_tags:
                embed.description += "**Clans**\n"
            async for clan in self.bot.coc.get_clans((n["clan_tag"] for n in clan_tags if not n["fake_clan"])):
                fmt = f":notepad_spiral: {clan} ({clan.tag})\n" \
                      f":paperclip: [In-Game Link]({clan.share_link})\n" \
                      f":paperclips: [Icon URL]({clan.badge.url})\n" \
                      f":person_bowing: Members: {clan.member_count}/50\n\n"
                embed.add_field(name="\u200b", value=fmt)

            query = "SELECT COUNT(*) FROM players WHERE fake_clan_tag = $1 AND season_id = $2"
            for clan_tag in (c["clan_tag"] for c in clan_tags if c["fake_clan"]):
                fetch = await ctx.db.fetchrow(query, clan_tag, await self.bot.seasonconfig.get_season_id())
                fmt = f":notepad_spiral: FakeClan ID: {clan_tag}\n" \
                      f":person_bowing: Members: {fetch[0]}\n\n"
                embed.add_field(name="\u200b", value=fmt)

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

            fetch = await ctx.db.fetch(
                "SELECT * FROM boards "
                "INNER JOIN clans ON clans.channel_id = boards.channel_id "
                "WHERE boards.guild_id = $1 AND clan_tag = $2",
                ctx.guild.id, clan.tag
            )
            for row in fetch:
                board_config = BoardConfig(bot=self.bot, record=row)

                embed.description += f"**{board_config.type.capitalize()}Board**\n" \
                                     f":notepad_spiral: {board_config.channel.mention}\n" \
                                     f":paperclip: [Background URL]({board_config.icon_url})\n" \
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

    @app_commands.command(name='season_info')
    async def info_season(self, intr: discord.Interaction):
        """Get Season IDs and start/finish times and info."""
        query = "SELECT id, start, finish FROM seasons ORDER BY id DESC"
        fetch = await self.bot.pool.fetch(query)
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
        await intr.response.send_message(embed=e)

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

    @staticmethod
    def convert_rows_to_bytes(rows):
        f = io.StringIO()
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        content = f.getvalue()

        return io.BytesIO(content.encode("utf-8-sig"))

        # csv = ""
        # for i, row in enumerate(rows):
        #     if i == 0:
        #         # headers
        #         csv += ''.join(f"{col}," for col in row.keys())
        #         csv += '\n'
        #
        #     csv += ''.join(f"{r}," for r in row.values())
        #     csv += '\n'
        #
        # return io.BytesIO(csv.encode("utf-8"))

    @commands.group(invoke_without_command=True)
    async def dump(self, ctx, *, argument: ConvertToPlayers = None):
        """Get a .csv of all player data the bot has stored for a clan/players.

        Use `+dump legends` to get a .csv of recent legend data, as seen on the legend boards.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+dump`
        :information_source: `+dump #CLAN_TAG`
        :information_source: `+dump CLAN NAME`
        :information_source: `+dump #PLAYER_TAG`
        :information_source: `+dump Player Name`
        :information_source: `+dump #channel`
        :information_source: `+dump @user`
        :information_source: `+dump all`

        **Example**
        :white_check_mark: `+dump`
        :white_check_mark: `+dump #JY9J2Y99`
        :white_check_mark: `+dump Reddit`
        :white_check_mark: `+dump Mathsman`
        :white_check_mark: `+dump @mathsman#1208`
        :white_check_mark: `+dump #donation-log`
        :white_check_mark: `+dump all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("Couldn't find any players - try adding a clan?")
        query = """SELECT player_tag, 
                          player_name, 
                          donations, 
                          received, 
                          trophies, 
                          start_trophies, 
                          clan_tag, 
                          last_updated,
                          user_id,
                          season_id
                    FROM players
                    WHERE player_tag = ANY($1::TEXT[])
                    AND clan_tag = ANY($2::TEXT[])
                    ORDER BY season_id DESC
                    """
        fetch = await ctx.db.fetch(query, [p['player_tag'] for p in argument], list({p['clan_tag'] for p in argument}))
        if not fetch:
            return await ctx.send(
                "Sorry, I have not collected enough data yet. Please try again later, or try changing your query."
            )

        rows = [{k: v for k, v in row.items()} for row in fetch]
        await ctx.send(file=discord.File(filename="donation-tracker-player-export.csv", fp=self.convert_rows_to_bytes(rows)))

    @dump.command(name="legend", aliases=["legends", "leg"])
    async def dump_legends(self, ctx, *, argument: ConvertToPlayers = None):
        """Get a .csv of all legend data the bot has stored for a clan/players.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+dump legends`
        :information_source: `+dump legends #CLAN_TAG`
        :information_source: `+dump legends CLAN NAME`
        :information_source: `+dump legends #PLAYER_TAG`
        :information_source: `+dump legends Player Name`
        :information_source: `+dump legends #channel`
        :information_source: `+dump legends @user`
        :information_source: `+dump legends all`

        **Example**
        :white_check_mark: `+dump legends`
        :white_check_mark: `+dump legends #JY9J2Y99`
        :white_check_mark: `+dump legends Reddit`
        :white_check_mark: `+dump legends Mathsman`
        :white_check_mark: `+dump legends @mathsman#1208`
        :white_check_mark: `+dump legends #donation-log`
        :white_check_mark: `+dump legends all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("Couldn't find any players - try adding a clan?")

        query = """SELECT player_tag, 
                          player_name, 
                          clan_tag,
                          starting,
                          finishing,
                          gain,
                          loss,
                          attacks,
                          defenses,
                          day 
                    FROM legend_days
                    WHERE player_tag = ANY($1::TEXT[])
                    AND clan_tag = ANY($2::TEXT[])
                    ORDER BY day DESC
                    """
        fetch = await ctx.db.fetch(query, [p['player_tag'] for p in argument], list({p['clan_tag'] for p in argument}))
        if not fetch:
            return await ctx.send(
                "Sorry, I have not collected enough data yet. Please try again later, or try changing your query."
            )

        rows = [{k: v for k, v in row.items()} for row in fetch]
        await ctx.send(file=discord.File(filename="donation-tracker-legends-export.csv", fp=self.convert_rows_to_bytes(rows)))

    @dump.command(name="war")
    async def dump_war(self, ctx, *, argument: ConvertToPlayers = None):
        """Get a .csv of all war data the bot has stored for a clan/players.

        **Parameters**
        :key: The argument: Can be a clan tag, name, player tag, name, channel #mention, user @mention or `server` for all clans linked to the server.

        **Format**
        :information_source: `+dump war`
        :information_source: `+dump war #CLAN_TAG`
        :information_source: `+dump war CLAN NAME`
        :information_source: `+dump war #PLAYER_TAG`
        :information_source: `+dump war Player Name`
        :information_source: `+dump war #channel`
        :information_source: `+dump war @user`
        :information_source: `+dump war all`

        **Example**
        :white_check_mark: `+dump war`
        :white_check_mark: `+dump war #JY9J2Y99`
        :white_check_mark: `+dump war Reddit`
        :white_check_mark: `+dump war Mathsman`
        :white_check_mark: `+dump war @mathsman#1208`
        :white_check_mark: `+dump war #donation-log`
        :white_check_mark: `+dump war all`
        """
        if not argument:
            argument = await ConvertToPlayers().convert(ctx, "all")
        if not argument:
            return await ctx.send("Couldn't find any players - try adding a clan?")

        query = """
        WITH cte AS (
                SELECT DISTINCT player_tag, player_name 
                FROM players 
                WHERE (player_tag = ANY($1::TEXT[])
                OR clan_tag = ANY($2::TEXT[])
                OR fake_clan_tag = ANY($2::TEXT[]))
                AND season_id = $3                
        )
        SELECT COUNT(*) as star_count, SUM(destruction) as destruction_count, cte.player_tag, cte.player_name, stars, seasons.id as season_id
        FROM war_attacks 
        INNER JOIN cte 
        ON cte.player_tag = war_attacks.player_tag 
        INNER JOIN seasons 
        ON start < load_time 
        AND load_time < finish
        GROUP BY season_id, cte.player_tag, cte.player_name, stars
        UNION ALL
        SELECT SUM(attacks_missed) as star_count, 0 as destruction_count, cte.player_tag, cte.player_name, -1 as stars, seasons.id as season_id
        FROM war_missed_attacks
        INNER JOIN cte 
        ON cte.player_tag = war_missed_attacks.player_tag
        INNER JOIN seasons 
        ON start < load_time 
        AND load_time < finish
        GROUP BY season_id, cte.player_tag, cte.player_name, stars
        ORDER BY season_id DESC, star_count DESC, destruction_count DESC
        """
        fetch = await ctx.db.fetch(query, [p['player_tag'] for p in argument], list({p['clan_tag'] for p in argument}), await self.bot.seasonconfig.get_season_id())
        if not fetch:
            return await ctx.send("Sorry, I have not collected enough data yet. Please try again later.")

        to_send = []
        for (player_tag, season_id), rows in itertools.groupby(fetch, key=lambda r: (r['player_tag'], r['season_id'])):
            rows = list(rows)
            by_star = {r['stars']: r for r in rows}

            to_send.append({
                "player_tag": player_tag,
                "player_name": rows[0]['player_name'],
                "season_id": season_id,
                "total_stars": sum(r['stars'] * r['star_count'] for r in rows if r['stars'] >= 0),
                "total_destruction": sum(r['destruction_count'] for r in rows),
                "three_star_count": by_star.get(3, {}).get('star_count', 0),
                "two_star_count": by_star.get(2, {}).get('star_count', 0),
                "one_star_count": by_star.get(1, {}).get('stars', 0),
                "zero_star_count": by_star.get(0, {}).get('stars', 0),
                "missed_attack_count": by_star.get(-1, {}).get('star_count', 0),
            })

        await ctx.send(file=discord.File(filename="donation-tracker-war-export.csv", fp=self.convert_rows_to_bytes(to_send)))

    @dump.before_invoke
    @dump_legends.before_invoke
    @dump_war.before_invoke
    async def before_dump(self, ctx):
        await ctx.trigger_typing()


async def setup(bot):
    if not hasattr(bot, 'command_stats'):
        bot.command_stats = Counter()

    await bot.add_cog(Info(bot))
