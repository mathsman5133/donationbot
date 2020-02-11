import discord
import asyncio
import typing
import datetime
import re
import logging

from discord.ext import commands
from cogs.utils.checks import requires_config, manage_guild
from cogs.utils.formatters import CLYTable
from cogs.utils.converters import ClanConverter, DateConverter, SortByConverter, TextChannel
from cogs.utils import checks

log = logging.getLogger(__name__)

url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                           r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")


class Edit(commands.Cog):
    """Allows a user to edit a variety of the bot's features."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def edit(self, ctx):
        """[Group] Allows a user to edit a variety of the bot's features."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @edit.command(name='prefix')
    @checks.manage_guild()
    async def edit_prefix(self, ctx, new_prefix: str = None):
        """Allows a user to select a custom prefix for the bot.

        **Format**
        :information_source: `+edit prefix`

        **Examples**
        :white_check_mark: `+edit prefix $`
        :white_check_mark: `+edit prefix !`
        :white_check_mark: `+edit prefix +`

        **Required Permissions**
        :warning: Manage Server
        """
        if not new_prefix:
            return await ctx.send_help(ctx.command)

        query = "UPDATE guilds SET prefix = $1 WHERE guild_id = $2"
        await self.bot.pool.execute(query, new_prefix, ctx.guild.id)
        self.bot.prefixes[ctx.guild.id] = new_prefix
        await ctx.send(f"The prefix for the bot has been changed to `{new_prefix}`")

    @edit.group(name='donationboard')
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True, error=True)
    async def edit_donationboard(self, ctx):
        """[Group] Run through an interactive process of editting the guild's donationboard.

        **Format**
        :information_source: `+edit donationboard`

        **Example**
        :white_check_mark: `+edit donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if ctx.invoked_subcommand:
            return

        p = await ctx.prompt('Would you like to edit all settings for the guild donationboard? ')
        if not p or p is False:
            return await ctx.send_help(ctx.command)

        await ctx.invoke(self.edit_donationboard_format)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send('Please send the URL of the icon you wish to use.')
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long! Aborting command...')
        await ctx.invoke(self.edit_donationboard_icon, url=msg.clean_content)

        await ctx.send('Please send the title message you want to display.')
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long! Aborting command...')

        await ctx.invoke(self.edit_donationboard_title, title=msg.clean_content)

        return await ctx.send('All done. Thanks!')

    @edit_donationboard.command(name='format')
    async def edit_donationboard_format(self, ctx):
        """Edit the format of the server's donationboard.

        The bot will provide 2 options and you must select 1 via reactions.

        **Format**
        :information_source: `+edit donationboard format`

        **Example**
        :white_check_mark: `+edit donationboard format`

        **Required Permissions**
        :warning: Manage Server
        """

        table = CLYTable()
        table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                        [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                        ])
        table.title = '**Option 1 Example**'
        option_1_render = f'**Option 1 Example**\n{table.donationboard_1()}'
        table.clear_rows()
        table.add_rows([[0, 6532, 'Member'], [1, 4453, 'Nearly #1'],
                        [2, 5589, 'Another Member'], [3, 0, 'Winner']
                        ])

        option_2_render = f'**Option 2 Example**\n{table.donationboard_2()}'

        embed = discord.Embed(colour=self.bot.colour)
        fmt = f'{option_1_render}\n\n\n{option_2_render}\n\n\n' \
            f'These are the 2 available default options.\n' \
            f'Please hit the reaction of the format you \nwish to display on the donationboard.'
        embed.description = fmt
        msg = await ctx.send(embed=embed)

        query = "UPDATE boards SET render=$1 WHERE channel_id=$2"

        reactions = ['1\N{combining enclosing keycap}', '2\N{combining enclosing keycap}']
        for r in reactions:
            await msg.add_reaction(r)

        def check(r, u):
            return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

        try:
            r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.db.execute(query, 1, ctx.config.channel_id)
            return await ctx.send('You took too long. Option 1 was chosen.')

        await ctx.db.execute(query, reactions.index(str(r)) + 1, ctx.config.channel_id)
        await ctx.confirm()

    @edit_donationboard.command(name='icon')
    async def edit_donationboard_icon(self, ctx, *, url: str = None):
        """Specify an icon for the guild's donationboard.

        **Parameters**
        :key: A URL (jpeg, jpg or png only) or uploaded attachment.

        **Format**
        :information_source: `+edit donationboard icon URL`

        **Example**
        :white_check_mark: `+edit donationboard icon https://catsareus/thecrazycatbot/123.jpg`
        :white_check_mark: `+edit donationboard icon` (with an attached image)

        **Required Permissions**
        :warning: Manage Server
        """
        if not url or not url_validator.match(url):
            attachments = ctx.message.attachments
            if not attachments:
                return await ctx.send('You must pass in a url or upload an attachment.')
            url = attachments[0].url

        if url == 'https://catsareus/thecrazycatbot/123.jpg':
            return await ctx.send('Uh oh! That\'s an example URL - it doesn\'t work!')

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, url, ctx.config.channel_id)
        await ctx.confirm()

    @edit_donationboard.command(name='title')
    async def edit_donationboard_title(self, ctx, *, title: str):
        """Specify a title for the guild's donationboard.

        **Parameters**
        :key: Title (must be less than 50 characters).

        **Format**
        :information_source: `+edit donationboard title TITLE`

        **Example**
        :white_check_mark: `+edit donationboard title The Crazy Cat Bot Title`

        **Required Permissions**
        :warning: Manage Server
        """
        if len(title) >= 50:
            return await ctx.send('Titles must be less than 50 characters.')

        query = "UPDATE boards SET title = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, title, ctx.config.channel_id)
        await ctx.confirm()

    @edit_donationboard.command(name='sort')
    async def edit_donationboard_sort(self, ctx, *, sort_by: SortByConverter):
        """Change which column the donationboard is sorted by.

        **Parameters**
        :key: Column to sort by (must be either `donations` or `received`).

        **Format**
        :information_source: `+edit donationboard sort COLUMN`

        **Example**
        :white_check_mark: `+edit donationboard sort donations`
        :white_check_mark: `+edit donationboard sort received`

        **Required Permissions**
        :warning: Manage Server
        """
        if sort_by not in ['donations', 'received']:
            return await ctx.send("Oops, that didn't look right! Try `donations` or `received` instead.")

        query = "UPDATE boards SET sort_by = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, sort_by, ctx.config.channel_id)
        await self.bot.donationboard.update_board(ctx.config.channel_id)
        await ctx.confirm()

    @edit.group(name='trophyboard')
    @manage_guild()
    @requires_config('trophyboard', invalidate=True, error=True)
    async def edit_trophyboard(self, ctx):
        """[Group] Run through an interactive process of editing the guild's trophyboard.

        **Format**
        :information_source: `+edit trophyboard`

        **Example**
        :white_check_mark: `+edit trophyboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if ctx.invoked_subcommand:
            return

        p = await ctx.prompt('Would you like to edit all settings for the guild trophyboard? ')
        if not p or p is False:
            return await ctx.send_help(ctx.command)

        await ctx.invoke(self.edit_trophyboard_format)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send('Please send the URL of the icon you wish to use.')
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long! Aborting command...')
        await ctx.invoke(self.edit_trophyboard_icon, url=msg.clean_content)

        await ctx.send('Please send the title message you want to display.')
        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await ctx.send('You took too long! Aborting command...')

        await ctx.invoke(self.edit_trophyboard_title, title=msg.clean_content)

        return await ctx.send('All done. Thanks!')

    @edit_trophyboard.command(name='format')
    async def edit_trophyboard_format(self, ctx):
        """Edit the format of the guild's trophyboard.

        The bot will provide 2 options and you must select 1 via reactions.

        **Format**
        :information_source: `+edit trophyboard format`

        **Example**
        :white_check_mark: `+edit trophyboard format`

        **Required Permissions**
        :warning: Manage Server
        """
        table = CLYTable()
        table.add_rows([[0, 4320, 955, 'Member Name'], [1, 4500, 870, 'Another Member'],
                        [2, 3900, -600, 'Yet Another'], [3, 1500, -1000, 'Worst Pusher']
                        ])
        table.title = '**Option 1 Example**'
        option_1_render = f'**Option 1 Example**\n{table.trophyboard_1()}'

        table.clear_rows()
        table.add_rows([[0, 2000, 'Member'], [1, 1500, 'Nearly #1'],
                        [2, 1490, 'Another Member'], [3, -600, 'Winner']
                        ])

        option_2_render = f'**Option 2 Example**\n{table.trophyboard_2()}'

        embed = discord.Embed(colour=self.bot.colour)
        fmt = f'{option_1_render}\n\n\n{option_2_render}\n\n\n' \
            f'These are the 2 available default options.\n' \
            f'Please hit the reaction of the format you \nwish to display on the trophyboard.'
        embed.description = fmt
        msg = await ctx.send(embed=embed)

        query = "UPDATE boards SET render=$1 WHERE channel_id=$2"

        reactions = ['1\N{combining enclosing keycap}', '2\N{combining enclosing keycap}']
        for r in reactions:
            await msg.add_reaction(r)

        def check(r, u):
            return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

        try:
            r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.db.execute(query, 1, ctx.config.channel_id)
            return await ctx.send('You took too long. Option 1 was chosen.')

        await ctx.db.execute(query, reactions.index(str(r)) + 1, ctx.config.channel_id)
        await ctx.confirm()

    @edit_trophyboard.command(name='icon')
    async def edit_trophyboard_icon(self, ctx, *, url: str = None):
        """Specify an icon for the server's trophyboard.

        **Parameters**
        :key: A URL (jpeg, jpg or png only) or uploaded attachment.

        **Format**
        :information_source: `+edit trophyboard icon URL`

        **Example**
        :white_check_mark: `+edit tropyboard icon https://catsareus/thecrazycatbot/123.jpg`
        :white_check_mark: `+edit donatiotrophyboardnboard icon` (with an attached image)

        **Required Permissions**
        :warning: Manage Server
        """
        if not url or not url_validator.match(url):
            attachments = ctx.message.attachments
            if not attachments:
                return await ctx.send('You must pass in a url or upload an attachment.')
            url = attachments[0].url

        if url == 'https://catsareus/thecrazycatbot/123.jpg':
            return await ctx.send('Uh oh! That\'s an example URL - it doesn\'t work!')

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, url, ctx.config.channel_id)
        await ctx.confirm()

    @edit_trophyboard.command(name='title')
    async def edit_trophyboard_title(self, ctx, *, title: str):
        """Specify a title for the guild's trophyboard.

        **Parameters**
        :key: Title (must be less than 50 characters).

        **Format**
        :information_source: `+edit trophyboard title TITLE`

        **Example**
        :white_check_mark: `+edit trophyboard title The Crazy Cat Bot Title`

        **Required Permissions**
        :warning: Manage Server
        """
        if len(title) >= 50:
            return await ctx.send('Titles must be less than 50 characters.')

        query = "UPDATE boards SET title = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, title, ctx.config.channel_id)
        await ctx.confirm()

    @edit_trophyboard.command(name='sort')
    async def edit_trophyboard_sort(self, ctx, *, sort_by: SortByConverter):
        """Change which column the trophyboard is sorted by.

        **Parameters**
        :key: Column to sort by (must be either `trophies`, `gain` or `loss` (opposite gain)).

        **Format**
        :information_source: `+edit trophyboard sort COLUMN`

        **Example**
        :white_check_mark: `+edit trophyboard sort trophies`
        :white_check_mark: `+edit trophyboard sort gain`
        :white_check_mark: `+edit trophyboard sort loss`

        **Required Permissions**
        :warning: Manage Server
        """
        if sort_by not in ['trophies', 'gain', 'loss']:
            return await ctx.send("Oops, that didn't look right! Try `trophies`, `gain` or `loss` instead.")

        query = "UPDATE boards SET sort_by = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, sort_by, ctx.config.channel_id)
        await self.bot.donationboard.update_board(ctx.config.channel_id)
        await ctx.confirm()

    @edit.group(name='donationlog')
    @manage_guild()
    @requires_config('donationlog', invalidate=True)
    async def edit_donationlog(self, ctx):
        """[Group] Edit the donationlog settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @edit_donationlog.command(name='interval')
    async def edit_donationlog_interval(self, ctx, channel: typing.Optional[TextChannel], minutes: int = 1):
        """Update the interval (in minutes) for which the bot will log your donations.

        **Parameters**
        :key: Discord Channel (mention etc.)
        :key: Interval length (in minutes)

        **Format**
        :information_source: `+edit donationlog interval #CHANNEL MINUTES`

        **Example**
        :white_check_mark: `+edit donationlog interval #logging 5`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send('Oops! It doesn\'t look like a donationlog is setup here. '
                                  'Try `+info` to find where the registered channels are!')

        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                """
        await ctx.db.execute(query, str(minutes), ctx.config.channel_id, 'donation')
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been changed to {minutes} minutes. '
                       f'Find which clans this affects with `+info {ctx.config.channel}`')

    @edit_donationlog.command(name='toggle')
    async def edit_donationlog_toggle(self, ctx):
        """Toggle the donation log on and off.

        **Format**
        :information_source: `+edit donationlog toggle`

        **Example**
        :white_check_mark: `+edit donationlog toggle`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send('Oops! It doesn\'t look like a donationlog is setup here. '
                                  'Try `+info` to find where the registered channels are!')

        query = """UPDATE logs
                   SET toggle = NOT toggle
                   WHERE channel_id=$1
                   AND type = $2
                   RETURNING toggle
                """
        toggle = await ctx.db.fetch(query, ctx.config.channel_id, 'donation')
        if toggle:
            condition = 'on'
        else:
            condition = 'off'
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been turned {condition}.')

    @edit.group(name='trophylog')
    @manage_guild()
    @requires_config('trophylog', invalidate=True)
    async def edit_trophylog(self, ctx):
        """[Group] Edit the trophylog settings."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @edit_trophylog.command(name='interval')
    async def edit_trophylog_interval(self, ctx, channel: typing.Optional[TextChannel], minutes: int = 1):
        """Update the interval (in minutes) for which the bot will log your trophies.

        **Parameters**
        :key: Discord Channel (mention etc.)
        :key: Interval length (in minutes)

        **Format**
        :information_source: `+edit trophylog interval #CHANNEL MINUTES`

        **Example**
        :white_check_mark: `+edit trophylog interval #logging 5`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send('Oops! It doesn\'t look like a trophylog is setup here. '
                                  'Try `+info` to find where the registered channels are!')

        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                """
        await ctx.db.execute(query, str(minutes), ctx.config.channel_id, 'trophy')
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been changed to {minutes} minutes. '
                       f'Find which clans this affects with `+info {ctx.config.channel}`')

    @edit_trophylog.command(name='toggle')
    async def edit_trophylog_toggle(self, ctx):
        """Toggle the trophy log on and off.

        **Format**
        :information_source: `+edit trophylog toggle`

        **Example**
        :white_check_mark: `+edit trophylog toggle`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send('Oops! It doesn\'t look like a trophylog is setup here. '
                                  'Try `+info` to find where the registered channels are!')

        query = """UPDATE logs
                   SET toggle = NOT toggle
                   WHERE channel_id=$1
                   AND type = $2
                   RETURNING toggle
                """
        toggle = await ctx.db.execute(query, ctx.config.channel_id, 'trophy')
        if toggle:
            condition = 'on'
        else:
            condition = 'off'
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been turned {condition}.')

    @edit.command(name='event')
    @manage_guild()
    @requires_config('event', invalidate=True)
    async def edit_event(self, ctx, *, event_name: str = None):
        """Edit a variety of settings for the current event.

        **Parameters**
        :key: Event name

        **Format**
        :information_source: `+edit event EVENT_NAME`

        **Example**
        :white_check_mark: `+edit event Donation Bot Event`

        **Required Permissions**
        :warning: Manage Server
        """
        if event_name:
            query = """SELECT id FROM events 
                       WHERE guild_id = $1 
                       AND event_name = $2"""
            fetch = await self.bot.pool.fetchrow(query, ctx.guild.id, event_name)
            if fetch:
                event_id = fetch['id']
            else:
                # ideally this would just display a list of events and let the user pick, but I
                # couldn't figure out the proper sequence of if event_name/if event_id
                return await ctx.send("There is no event on this server with that name. Try `+edit event` "
                                      "to pick from a list of events on this server.")
        else:
            # No event name provided or I didn't understand the name I was given
            query = """SELECT id, event_name, start 
                               FROM events
                               WHERE guild_id = $1 
                               ORDER BY start"""
            fetch = await self.bot.pool.fetch(query, ctx.guild.id)
            if len(fetch) == 0 or not fetch:
                return await ctx.send("There are no events currently set up on this server. "
                                      "Try `+add event`")
            elif len(fetch) == 1:
                event_id = fetch[0]['id']
            else:
                table = CLYTable()
                fmt = f"Events on {ctx.guild}:\n\n"
                reactions = []
                counter = 0
                for event in fetch:
                    days_until = event['start'].date() - datetime.datetime.utcnow().date()
                    table.add_row([counter, days_until.days, event['event_name']])
                    counter += 1
                    reactions.append(f"{counter}\N{combining enclosing keycap}")
                render = table.events_list()
                fmt += f'{render}\n\nPlease select the reaction that corresponds with the event you would ' \
                       f'like to remove.'
                e = discord.Embed(colour=self.bot.colour,
                                  description=fmt)
                msg = await ctx.send(embed=e)
                for r in reactions:
                    await msg.add_reaction(r)

                def check(r, u):
                    return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

                try:
                    r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
                except asyncio.TimeoutError:
                    await msg.clear_reactions()
                    return await ctx.send("I feel like I'm being ignored. MAybe try again later?")

                index = reactions.index(str(r))
                event_id = fetch[index]['id']

            # Now that we have the event_id, let's edit things
            query = """SELECT event_name, start, finish 
                       FROM events
                       WHERE id = $1"""
            event = await self.bot.pool.fetchrow(query, event_id)

            def check_author(m):
                return m.author == ctx.author

            answer = await ctx.prompt(f"Event Name: **{event['event_name']}**\n"
                                      f"Would you like to edit the event name?")
            if answer:
                try:
                    await ctx.send('Please enter the new name for this event.')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    new_event_name = response.content
                except asyncio.TimeoutError:
                    new_event_name = event['event_name']
            else:
                new_event_name = event['event_name']
            answer = await ctx.prompt(f"Start Date: **{event['start'].date()}\n"
                                      f"Would you like to edit the date?")
            if answer:
                try:
                    await ctx.send('Please enter the new start date.  (YYYY-MM-DD)')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    new_start_date = await DateConverter().convert(ctx, response.clean_content)
                except (ValueError, commands.BadArgument):
                    await ctx.send('Date must be in the YYYY-MM-DD format. I\'m going to keep '
                                   'the current start date and you can change it later if you like.')
                    new_start_date = event['start'].date()
                except asyncio.TimeoutError:
                    await ctx.send('Seems as though you don\'t really know the answer. I\'m just going '
                                   'to keep the date I have for now.')
                    new_start_date = event['start'].date()
            else:
                new_start_date = event['start'].date()
            answer = await ctx.prompt(f"Start Time: **{event['start'].time()}\n"
                                      f"Would you like to edit the time?")
            if answer:
                try:
                    await ctx.send('Please enter the new start time. (Please provide HH:MM in UTC)')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    hour, minute = map(int, response.content.split(':'))
                    if hour < 13:
                        try:
                            await ctx.send('And is that AM or PM?')
                            response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                            if response.content.lower() == 'pm':
                                hour += 12
                        except asyncio.TimeoutError:
                            if hour < 6:
                                await ctx.send('Well I\'ll just go with PM then.')
                                hour += 12
                            else:
                                await ctx.send('I\'m going to assume you want AM.')
                    new_start_time = datetime.time(hour, minute)
                except asyncio.TimeoutError:
                    await ctx.send('Time\'s up my friend. Start time will remain the same!')
                    new_start_time = event['start'].time()
            else:
                new_start_time = event['start'].time()
            answer = await ctx.prompt(f"End Date: **{event['finish'].date()}\n"
                                      f"Would you like to edit the date?")
            if answer:
                try:
                    await ctx.send('Please enter the new end date.  (YYYY-MM-DD)')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    new_end_date = await DateConverter().convert(ctx, response.clean_content)
                except (ValueError, commands.BadArgument):
                    await ctx.send('Date must be in the YYYY-MM-DD format. I\'m going to keep '
                                   'the current end date and you can change it later if you like.')
                    new_end_date = event['finish'].date()
                except asyncio.TimeoutError:
                    await ctx.send('Seems as though you don\'t really know the answer. I\'m just going '
                                   'to keep the date I have for now.')
                    new_end_date = event['finish'].date()
            else:
                new_end_date = event['finish'].date()
            answer = await ctx.prompt(f"End Time: **{event['finish'].time()}\n"
                                      f"Would you like to edit the time?")
            if answer:
                try:
                    await ctx.send('Please enter the new end time. (Please provide HH:MM in UTC)')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    hour, minute = map(int, response.content.split(':'))
                    if hour < 13:
                        try:
                            await ctx.send('And is that AM or PM?')
                            response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                            if response.content.lower() == 'pm':
                                hour += 12
                        except asyncio.TimeoutError:
                            if hour < 6:
                                await ctx.send('Well I\'ll just go with PM then.')
                                hour += 12
                            else:
                                await ctx.send('I\'m going to assume you want AM.')
                    new_end_time = datetime.time(hour, minute)
                except asyncio.TimeoutError:
                    await ctx.send('Time\'s up my friend. Start time will remain the same!')
                    new_end_time = event['finish'].time()
            else:
                new_end_time = event['finish'].time()

            # Assemble answers and update db
            new_start = datetime.datetime.combine(new_start_date, new_start_time)
            new_finish = datetime.datetime.combine(new_end_date, new_end_time)
            query = """UPDATE events 
                       SET event_name = $1, start = $2, finish = $3 
                       WHERE id = $4"""
            await ctx.db.execute(query, new_event_name, new_start, new_finish, event_id)

            fmt = (f'**Event Info:**\n\n{new_event_name}\n{new_start.strftime("%d %b %Y %H:%M")}\n'
                   f'{new_finish.strftime("%d %b %Y %H:%M")}')
            e = discord.Embed(colour=discord.Colour.green(),
                              description=fmt)
            await ctx.send(embed=e)
            self.bot.dispatch('event_register')

    @commands.command()
    @checks.manage_guild()
    @requires_config('event')
    @commands.cooldown(1, 43200, commands.BucketType.guild)
    async def refresh(self, ctx, *, clans: ClanConverter = None):
        """Manually refresh all players in the database with current donations and received.

        Note: it will only update their donations if the
              amount recorded in-game is more than in the database.
              Ie. if they have left and re-joined it won't update them, usually.

        **Parameters**
        :key: Clan - tag, name or `all`.

        **Format**
        :information_source: `+refresh CLAN_TAG` or
        :information_source: `+refresh CLAN NAME` or
        :information_source: `+refresh all`

        **Example**
        :white_check_mark: `+refresh #P0LYJC8C`
        :white_check_mark: `+refresh Rock Throwers`
        :white_check_mark: `+refresh all`

        **Required Permissions**
        :warning: Manage Server

        **Cooldowns**
        :hourglass: You can only call this command once every **12 hours**
        """
        async with ctx.typing():
            if not clans:
                clans = await ctx.get_clans()
            query = """UPDATE players 
                       SET donations = $1
                       WHERE player_tag = $2
                       AND donations <= $1
                       AND season_id = $3
                       RETURNING player_tag;
                    """
            query2 = """UPDATE players 
                        SET received = $1
                        WHERE player_tag = $2
                        AND received <= $1  
                        AND season_id = $3
                        RETURNING player_tag;
                     """
            query3 = """UPDATE players
                        SET trophies = $1
                        WHERE player_tag = $2
                        AND trophies != $1
                        AND season_id = $3
                        RETURNING player_tag;               
                     """
            query4 = """UPDATE eventplayers
                        SET live=TRUE
                        WHERE player_tag = ANY($1::TEXT[])
                        AND event_id = $2
                    """
            season_id = await self.bot.seasonconfig.get_season_id()
            for clan in clans:
                for member in clan.members:
                    await ctx.db.execute(query, member.donations, member.tag, season_id)
                    await ctx.db.execute(query2, member.received, member.tag, season_id)
                    await ctx.db.execute(query3, member.trophies, member.tag, season_id)
                if ctx.config:
                    await ctx.db.execute(query4, [m.tag for m in clan.members], ctx.config.id)

            dboard_channels = await self.bot.utils.get_board_channels(ctx.guild.id, 'donation')
            for id_ in dboard_channels:
                await self.bot.donationboard.update_board(int(id_))

            tboard_channels = await self.bot.utils.get_board_channels(ctx.guild.id, 'trophy')
            for id_ in tboard_channels:
                await self.bot.donationboard.update_board(int(id_))

            await ctx.send('All done - I\'ve force updated the boards too!')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reset_cooldown(self, ctx, guild_id: int = None):
        if guild_id:
            ctx.guild = self.bot.get_guild(guild_id)

        self.refresh.reset_cooldown(ctx)
        await ctx.confirm()


def setup(bot):
    bot.add_cog(Edit(bot))
