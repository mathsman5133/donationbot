import discord
import asyncio
import typing
import datetime
import re
import logging

from discord.ext import commands
from cogs.utils.checks import requires_config, manage_guild
from cogs.utils.formatters import CLYTable
from cogs.utils.converters import ClanConverter, DateConverter, TextChannel
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

    @edit.command(name='timezone', aliases=['tz'])
    async def edit_timezone(self, ctx, offset: int = 0):
        """Edit the timezone in which the bot sees you. This is useful for the `+activity` command.

        Timezone offset should be the number of hours +/- UTC which you are, for example, if you want to
        set your timezone to "US East Coast" (4 hours behind UTC), you would do use `+edit timezone -4`.

        This is a per-user command. Timezones will appear as the default unless you run this command.

        **Format**
        :information_source: `+edit timezone OFFSET`

        **Examples**
        :white_check_mark: `+edit timezone -4` (for US East Coast)
        :white_check_mark: `+edit timezone +5` (for India)
        :white_check_mark: `+edit timezone +10` (for Australia)
        """
        if not -12 <= offset <= 12:
            return await ctx.send("Your offset must be between -12 and 12 hours away from UTC.")

        query = "INSERT INTO user_config (user_id, timezone_offset) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone_offset = $2"
        await ctx.db.execute(query, ctx.author.id, offset)
        await ctx.send(":ok_hand: Updated server timezone offset.")

    @edit.command(name='darkmode')
    async def edit_darkmode(self, ctx):
        """Toggle your dark mode setting. This is useful for the `+activity` command.

        If this is set to "on", all commands will return a dark-mode-friendly colour theme.

        This defaults to "off".

        This is a per-user command. Dark mode will appear as the default (off) unless you run this command.

        **Format**
        :information_source: `+edit darkmode`

        **Example**
        :white_check_mark: `+edit darkmode` (to turn on)
        """
        query = """INSERT INTO user_config (user_id, dark_mode) 
                   VALUES ($1, TRUE) 
                   ON CONFLICT (user_id) 
                   DO UPDATE SET dark_mode = NOT user_config.dark_mode 
                   RETURNING dark_mode
                """
        fetch = await ctx.db.fetchrow(query, ctx.author.id)
        await ctx.send(f":ok_hand: Updated dark mode to: {'on' if fetch['dark_mode'] else 'off'}")

    @edit.group(name='donationboard')
    @checks.manage_guild()
    async def edit_donationboard(self, ctx):
        """[Group] Run through an interactive process of editting a donationboard.

        **Format**
        :information_source: `+edit donationboard`

        **Example**
        :white_check_mark: `+edit donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @edit_donationboard.command(name='background', aliases=['icon', 'bg'])
    async def edit_donationboard_icon(self, ctx, channel: typing.Optional[discord.TextChannel], *, url: str = None):
        """Change or add an background for a donationboard.

        **Parameters**
        :key: A channel where the donationboard is located (#mention)
        :key: A URL (jpeg, jpg or png only). Use `default` to remove any background and use the bot default one.

        **Format**
        :information_source: `+edit donationboard background #CHANNEL URL`

        **Example**
        :white_check_mark: `+edit donationboard background #dt-boards https://catsareus/thecrazycatbot/123.jpg`
        :white_check_mark: `+edit donationboard background #dt-boards default`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        # if not url or not url_validator.match(url):
        #     attachments = ctx.message.attachments
        #     if not attachments:
        #         return await ctx.send('You must pass in a url or upload an attachment.')
        #     url = attachments[0].url

        if url in ['default', 'none', 'remove']:
            url = None

        if url == 'https://catsareus/thecrazycatbot/123.jpg':
            return await ctx.send('Uh oh! That\'s an example URL - it doesn\'t work!')

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2 AND type = 'donation' RETURNING message_id"
        result = await ctx.db.fetchrow(query, url, channel.id)
        if not result:
            return await ctx.send(f"I couldn't find a donationboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add donationboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Icon URL updated.")

    @edit_donationboard.command(name='title')
    async def edit_donationboard_title(self, ctx, channel: typing.Optional[discord.TextChannel], *, title: str):
        """Specify a title for a donationboard.

        **Parameters**
        :key: A channel where the donationboard is located (#mention)
        :key: Title (must be less than 50 characters).

        **Format**
        :information_source: `+edit donationboard title #CHANNEL TITLE`

        **Example**
        :white_check_mark: `+edit donationboard title #dt-boards The Crazy Cat Bot Title`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel
        if len(title) >= 50:
            return await ctx.send('Titles must be less than 50 characters.')

        query = "UPDATE boards SET title = $1 WHERE channel_id = $2 AND type = 'donation' RETURNING message_id"
        result = await ctx.db.fetchrow(query, title, channel.id)

        if not result:
            return await ctx.send(f"I couldn't find a donationboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add donationboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Title updated.")

    @edit_donationboard.command(name='perpage')
    async def edit_donationboard_per_page(self, ctx, channel: typing.Optional[discord.TextChannel], per_page: int):
        """Change how many players are displayed on each page of a donationboard.

        By default, it is 15 for the first and second pages, then 20, 25, 25, 50 etc.
        You can restore the default settings by running `+edit donationboard perpage 0`.

        **Parameters**
        :key: A channel where the donationboard is located (#mention)
        :key: The number of players per page. Must be a number (25).

        **Format**
        :information_source: `+edit donationboard perpage #CHANNEL NUMBER`

        **Example**
        :white_check_mark: `+edit donationboard perpage #dt-boards 15`
        :white_check_mark: `+edit donationboard perpage #dt-boards 50`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel
        if per_page < 0:
            return await ctx.send("You can't have a negative number of players per page!")

        query = "UPDATE boards SET per_page = $1 WHERE channel_id = $2 AND type = 'donation' RETURNING message_id"
        result = await ctx.db.fetchrow(query, per_page, channel.id)

        if not result:
            return await ctx.send(f"I couldn't find a donationboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add donationboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Per-page count updated.")

    @edit.group(name='trophyboard')
    @manage_guild()
    async def edit_trophyboard(self, ctx):
        """[Group] Edit a trophyboard. See the subcommands for more info.
        """
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @edit_trophyboard.command(name='background', aliases=['bg', 'icon'])
    async def edit_trophyboard_icon(self, ctx, channel: typing.Optional[discord.TextChannel], *, url: str = None):
        """Add or change the background for a trophyboard.

        **Parameters**
        :key: A channel where the trophyboard is located (#mention)
        :key: A URL (jpeg, jpg or png only). Use `default` to remove any background and use the bot default.

        **Format**
        :information_source: `+edit trophyboard background #CHANNEL URL`

        **Example**
        :white_check_mark: `+edit tropyboard background #dt-boards https://catsareus/thecrazycatbot/123.jpg`
        :white_check_mark: `+edit tropyboard background #dt-boards default`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        # if not url or not url_validator.match(url):
        #     attachments = ctx.message.attachments
        #     if not attachments:
        #         return await ctx.send('You must pass in a url or upload an attachment.')
        #     url = attachments[0].url

        if url in ['none', 'remove', 'default']:
            url = None

        if url == 'https://catsareus/thecrazycatbot/123.jpg':
            return await ctx.send('Uh oh! That\'s an example URL - it doesn\'t work!')

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2 AND type = 'trophy' RETURNING message_id"
        result = await ctx.db.fetchrow(query, url, channel.id)
        if not result:
            return await ctx.send(
                f"I couldn't find a trophyboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add trophyboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Icon URL updated.")

    @edit_trophyboard.command(name='title')
    async def edit_trophyboard_title(self, ctx, channel: typing.Optional[discord.TextChannel], *, title: str):
        """Change the title for a trophyboard.

        **Parameters**
        :key: A channel where the trophyboard is located (#mention)
        :key: Title (must be less than 50 characters).

        **Format**
        :information_source: `+edit trophyboard title #CHANNEL TITLE`

        **Example**
        :white_check_mark: `+edit trophyboard title #dt-boards The Crazy Cat Bot Title`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel
        if len(title) >= 50:
            return await ctx.send('Titles must be less than 50 characters.')

        query = "UPDATE boards SET title = $1 WHERE channel_id = $2 AND type = 'trophy' RETURNING message_id"
        result = await ctx.db.fetchrow(query, title, channel.id)

        if not result:
            return await ctx.send(
                f"I couldn't find a trophyboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add trophyboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Title updated.")

    @edit_trophyboard.command(name='perpage')
    async def edit_trophyboard_per_page(self, ctx, channel: typing.Optional[discord.TextChannel], per_page: int):
        """Change how many players are displayed on each page of a trophyboard.

        By default, it is 15 for the first and second pages, then 20, 25, 25, 50 etc.
        You can restore the default settings by running `+edit trophyboard perpage 0`.

        **Parameters**
        :key: A channel where the trophyboard is located (#mention)
        :key: The number of players per page. Must be a number (25).

        **Format**
        :information_source: `+edit trophyboard perpage #CHANNEL NUMBER`

        **Example**
        :white_check_mark: `+edit trophyboard perpage #dt-boards 15`
        :white_check_mark: `+edit trophyboard perpage #dt-boards 50`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel
        if per_page < 0:
            return await ctx.send("You can't have a negative number of players per page!")

        query = "UPDATE boards SET per_page = $1 WHERE channel_id = $2 AND type = 'trophy' RETURNING message_id"
        result = await ctx.db.fetchrow(query, per_page, channel.id)

        if not result:
            return await ctx.send(f"I couldn't find a trophyboard setup in {channel}. Either #mention a valid board channel, or set one up with `+help add trophyboard`.")

        await self.bot.donationboard.update_board(message_id=result['message_id'])
        await ctx.send(f":white_check_mark: Per-page count updated.")

    @edit.group(name='donationlog')
    @manage_guild()
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
        channel = channel or ctx.channel

        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                   RETURNING id;
                """
        fetch = await ctx.db.fetchrow(query, str(minutes), channel.id, 'donation')
        if not fetch:
            return await ctx.send(
                "Oops! It doesn't look like a donationlog is setup here. "
                "Try `+info` to find where the registered channels are!"
            )

        await ctx.send(f'Logs for {channel.mention} have been changed to {minutes} minutes.')

    @edit_donationlog.command(name='toggle')
    async def edit_donationlog_toggle(self, ctx, channel: discord.TextChannel = None):
        """Toggle the donation log on.

        **Format**
        :information_source: `+edit donationlog toggle`

        **Example**
        :white_check_mark: `+edit donationlog toggle`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        query = """UPDATE logs
                   SET toggle = TRUE
                   WHERE channel_id=$1
                   AND type = $2
                   RETURNING toggle
                """
        toggle = await ctx.db.fetchrow(query, channel.id, 'donation')
        if not toggle:
            return await ctx.send(
                "Oops! It doesn't look like a donationlog is setup here. "
                "Try `+info` to find where the registered channels are!"
            )

        await ctx.send(f'Logs for {channel.mention} have been turned on.')

    @edit_donationlog.command(name='style')
    async def edit_donationlog_style(self, ctx, channel: discord.TextChannel = None):
        """Toggle the donation style. This alternates between detailed and basic versions.

        **Format**
        :information_source: `+edit donationlog style`

        **Example**
        :white_check_mark: `+edit donationlog style`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        query = """UPDATE logs
                   SET detailed = NOT detailed
                   WHERE channel_id = $1
                   AND type = $2
                   RETURNING detailed;
                """
        detailed = await ctx.db.fetchrow(query, channel.id, 'donation')
        if not detailed:
            return await ctx.send(
                "Oops! It doesn't look like a donationlog is setup here. "
                "Try `+info` to find where the registered channels are!"
            )

        if detailed['detailed']:
            embed = discord.Embed(
                description=f"Donationlog has been set to maximum detail. An example is below. Use `{ctx.prefix}edit donationlog style` to change to the basic version."
            )
            embed.set_image(url="https://cdn.discordapp.com/attachments/681438398455742536/681438506857398307/demo_detailed.JPG")

        else:
            embed = discord.Embed(
                description=f"Donationlog has been set to basic detail. An example is below. Use `{ctx.prefix}edit donationlog style` to change to maximum detail version."
            )
            embed.set_image(url="https://cdn.discordapp.com/attachments/681438398455742536/681438471805861926/demo_basic.JPG")

        return await ctx.send(embed=embed)

    @edit.group(name='trophylog')
    @manage_guild()
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
        channel = channel or ctx.channel
        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                   RETURNING id
                """
        fetch = await ctx.db.fetchrow(query, str(minutes), channel.id, 'trophy')
        if not fetch:
            return await ctx.send(
                "Oops! It doesn't look like a trophylog is setup here. "
                "Try `+info` to find where the registered channels are!"
            )

        await ctx.send(f'Logs for {channel.mention} have been changed to {minutes} minutes.')

    @edit_trophylog.command(name='toggle')
    async def edit_trophylog_toggle(self, ctx, channel: discord.TextChannel = None):
        """Toggle the trophy log on and off.

        **Format**
        :information_source: `+edit trophylog toggle`

        **Example**
        :white_check_mark: `+edit trophylog toggle`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        query = """UPDATE logs
                   SET toggle = TRUE
                   WHERE channel_id=$1
                   AND type = $2
                   RETURNING toggle
                """
        toggle = await ctx.db.fetchrow(query, channel.id, 'trophy')
        if not toggle:
            return await ctx.send(
                "Oops! It doesn't look like a trophylog is setup here. "
                "Try `+info` to find where the registered channels are!"
            )

        await ctx.send(f'Trophy logs for {channel.mention} have been turned on.')

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

    @commands.command(hidden=True)
    @commands.is_owner()
    async def globalrefresh(self, ctx):
        query = "SELECT DISTINCT(clan_tag) FROM clans"
        fetch = await ctx.db.fetch(query)

        player_data = []
        async for clan in self.bot.coc.get_clans((n[0] for n in fetch)):
            for player in clan.members:
                player_data.append({
                    "player_tag": player.tag,
                    "donations": player.donations,
                    "received": player.received,
                    "trophies": player.trophies,
                    "clan_tag": clan.tag,
                    "player_name": player.name,
                    "league_id": player.league and player.league.id
                })

        query = """
        UPDATE players SET donations = public.get_don_rec_max(x.donations, x.donations, COALESCE(players.donations, 0)), 
                           received  = public.get_don_rec_max(x.received, x.received, COALESCE(players.received, 0)), 
                           trophies  = public.get_trophies(x.trophies, players.trophies, players.league_id),
                           clan_tag  = x.clan_tag,
                           player_name = x.player_name,
                           league_id = x.league_id
        FROM(
            SELECT x.player_tag, x.donations, x.received, x.trophies, x.clan_tag, x.player_name, x.league_id
                FROM jsonb_to_recordset($1::jsonb)
            AS x(player_tag TEXT, 
                 donations INTEGER,
                 received INTEGER,
                 trophies INTEGER,
                 clan_tag TEXT,
                 player_name TEXT,
                 league_id INTEGER)
            )
        AS x
        WHERE players.player_tag = x.player_tag
        AND players.season_id=$2
        """
        await ctx.db.execute(query, player_data, await self.bot.seasonconfig.get_season_id())
        await ctx.tick()

    @commands.command()
    @commands.cooldown(1, 60 * 60, commands.BucketType.guild)
    async def refresh(self, ctx, *, clans: ClanConverter = None):
        """Manually refresh all players in the database with current donations and received.

        Note: this will update all players in the clan based on achievement counts at the season start.

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

        **Cooldowns**
        :hourglass: You can only call this command once every **1 hour**
        """
        query = """UPDATE players SET donations   = public.get_don_rec_max(x.donations, x.donations, players.donations),
                                      received    = public.get_don_rec_max(x.received, x.received, players.received),
                                      trophies    = x.trophies,
                                      player_name = x.player_name,
                                      clan_tag    = x.clan_tag
                   FROM (
                      SELECT x.player_tag, x.donations, x.received, x.trophies, x.player_name, x.clan_tag
                      FROM jsonb_to_recordset($1::jsonb)
                      AS x(
                         player_tag TEXT,
                         donations INTEGER,
                         received INTEGER,
                         trophies INTEGER,
                         player_name TEXT,
                         clan_tag TEXT
                      )
                   )
                   AS x
                   WHERE players.player_tag = x.player_tag
                   AND players.season_id = $2                      
                """
        query3 = "UPDATE players SET clan_tag = NULL WHERE clan_tag = ANY($1::TEXT[]) AND NOT player_tag = ANY($2::TEXT[])"
        players = []
        async with ctx.typing():
            if not clans:
                clans = await ctx.get_clans()

            season_id = await self.bot.seasonconfig.get_season_id()
            player_tags = []
            for clan in clans:
                for player in clan.members:
                    players.append({
                        "player_tag": player.tag,
                        "donations": player.donations,
                        "received": player.received,
                        "trophies": player.trophies,
                        "player_name": player.name,
                        "clan_tag": player.clan and player.clan.tag
                    })
                    player_tags.append(player.tag)

            await ctx.db.execute(query3, [n.tag for n in clans], player_tags)

            await ctx.db.execute(query, players, season_id)

            dboard_channels = await self.bot.utils.get_board_channels(ctx.guild.id, 'donation')
            tboard_channels = await self.bot.utils.get_board_channels(ctx.guild.id, 'trophy')
            for id_ in (*dboard_channels, *tboard_channels):
                await self.bot.donationboard.update_board(message_id=int(id_))

            await ctx.send('All done - I\'ve force updated the boards too!')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def nuke(self, ctx, clan_tag: str = None):
        query = "UPDATE players SET donations = 0, received = 0 WHERE clan_tag = $1 AND season_id = $2"
        await ctx.db.execute(query, clan_tag, await self.bot.seasonconfig.get_season_id())
        ctx.config = None
        await ctx.invoke(self.refresh, clans=[await self.bot.coc.get_clan(clan_tag)])

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reset_cooldown(self, ctx, guild_id: int = None):
        if guild_id:
            ctx.guild = self.bot.get_guild(guild_id)

        self.refresh.reset_cooldown(ctx)
        await ctx.confirm()


def setup(bot):
    bot.add_cog(Edit(bot))
