import discord
import asyncio
import typing
import datetime
import re
import coc
import logging

from discord.ext import commands
from cogs.utils.checks import requires_config, manage_guild, helper_check
from cogs.utils.converters import PlayerConverter, DateConverter, TextChannel
from cogs.utils import checks

RCS_GUILD_ID = 295287647075827723

log = logging.getLogger(__name__)

url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                           r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")


class Add(commands.Cog):
    """Add clans, players, trophy and donationboards, logs and more."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def insert_player(connection, player, season_id, in_event: bool = False, event_id: int = None):
        query = """INSERT INTO players (
                                    player_tag,
                                    donations,
                                    received,
                                    trophies,
                                    start_trophies,
                                    season_id,
                                    start_friend_in_need,
                                    start_sharing_is_caring,
                                    start_attacks,
                                    start_defenses,
                                    start_best_trophies,
                                    start_update
                                    )
                    VALUES ($1, $2, $3, $4, $4, $5, $6, $7, $8, $9, $10, True)
                    ON CONFLICT (player_tag, season_id) 
                    DO NOTHING
                """
        await connection.execute(query,
                                 player.tag,
                                 player.donations,
                                 player.received,
                                 player.trophies,
                                 season_id,
                                 player.get_achievement('Friend in Need').value,
                                 player.get_achievement('Sharing is caring').value,
                                 player.attack_wins,
                                 player.defense_wins,
                                 player.best_trophies
                                 )
        if in_event:
            event_query = """INSERT INTO eventplayers (
                                            player_tag,
                                            donations,
                                            received,
                                            trophies,
                                            start_trophies,
                                            event_id,
                                            start_friend_in_need,
                                            start_sharing_is_caring,
                                            start_attacks,
                                            start_defenses,
                                            start_best_trophies,
                                            start_update
                                            )
                            VALUES ($1, $2, $3, $4, $4, $5, $6, $7, $8, $9, $10, True)
                            ON CONFLICT (player_tag, event_id)
                            DO NOTHING
                        """
            await connection.execute(event_query,
                                     player.tag,
                                     player.donations,
                                     player.received,
                                     player.trophies,
                                     event_id,
                                     player.get_achievement('Friend in Need').value,
                                     player.get_achievement('Sharing is caring').value,
                                     player.attack_wins,
                                     player.defense_wins,
                                     player.best_trophies
                                     )

    @commands.group()
    async def add(self, ctx):
        """[Group] Allows the user to add a variety of features to the bot."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @add.command(name='clan')
    @checks.manage_guild()
    async def add_clan(self, ctx, channel: typing.Optional[discord.TextChannel], clan_tag: str):
        """Link a clan to your server.
        This will add all accounts in clan to the database, if not already added.

        Note: As a security feature, the clan must have the letters `dt` added
        at the end of the clan's description.

        This is a security feature of the bot to ensure you have proper (co)ownership of the clan.
        `dt` should be removed once the command has been sucessfully run.

        **Parameters**
        :key: A discord channel (#mention). If you don't have this, it will use the channel you're in
        :key: A clan tag

        **Format**
        :information_source: `+add clan #CLAN_TAG`
        :information_source: `+add clan #CHANNEL #CLAN_TAG`

        **Example**
        :white_check_mark: `+add clan #P0LYJC8C`
        :white_check_mark: `+add clan #trophyboard #P0LYJC8C`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or ctx.channel

        current_clans = await self.bot.get_clans(ctx.guild.id)
        if len(current_clans) > 3 and not checks.is_patron_pred(ctx):
            return await ctx.send('You must be a patron to have more than 4 clans claimed per server. '
                                  'See more info with `+patron`, or join the support server for more help: '
                                  f'{self.bot.support_invite}')

        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "SELECT id FROM clans WHERE clan_tag = $1 AND channel_id = $2"
        fetch = await ctx.db.fetch(query, clan_tag, channel.id)
        if fetch:
            return await ctx.send('This clan has already been linked to the channel.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag)
        except coc.NotFound:
            return await ctx.send(f'Clan not found with `{clan_tag}` tag.')

        check = clan.description.strip().endswith('dt') \
                or await self.bot.is_owner(ctx.author) \
                or clan_tag in (n.tag for n in current_clans) \
                or ctx.guild.id == RCS_GUILD_ID \
                or helper_check(self.bot, ctx.author) is True

        if not check:
            return await ctx.send('Please add the letters `dt` to the end of '
                                  f'`{clan.name}`\'s clan description. Wait 5 minutes and try again.'
                                  '\n\nThis is a security feature of the bot and should '
                                  'be removed once the clan has been added.\n'
                                  '<https://cdn.discordapp.com/attachments/'
                                  '605352421929123851/634226338852503552/Screenshot_20191017-140812.png>')

        query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name) VALUES ($1, $2, $3, $4)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, channel.id, clan.name)

        await ctx.send('Clan has been added. Please wait a moment while all players are added.')

        season_id = await self.bot.seasonconfig.get_season_id()
        async for member in clan.get_detailed_members():
            await self.insert_player(ctx.db, member, season_id, False, None)

        await ctx.send('Clan and all members have been added to the database (if not already added)')
        ctx.channel = channel  # modify for `on_clan_claim` listener
        self.bot.dispatch('clan_claim', ctx, clan)

    @add.command(name='player')
    @requires_config('event')
    async def add_player(self, ctx, *, player: PlayerConverter):
        """Manually add a clash account to the database. This does not claim the account.


        **Parameters**
        :key: A player name OR tag

        **Format**
        :information_source: `+add player #PLAYER_TAG`
        :information_source: `+add player PLAYER NAME`

        **Example**
        :white_check_mark: `+add player #P0LYJC8C`
        :white_check_mark: `+add player mathsman`
        """
        if not isinstance(player, coc.Player):
            player = await self.bot.coc.get_player(player.tag)
        if ctx.config:
            prompt = await ctx.prompt(f'Do you wish to add {player} to the current event?')
        else:
            prompt = False

        season_id = await self.bot.seasonconfig.get_season_id()
        await self.insert_player(ctx.db, player, season_id, prompt,
                                 getattr(ctx.config, 'event_id', None))

        await ctx.send('All done!')

    @add.command(name='discord', aliases=['claim', 'link'])
    @requires_config('event')
    async def add_discord(self, ctx, user: typing.Optional[discord.Member] = None, *,
                          player: PlayerConverter):
        """Link a clash account to your discord account

        **Parameters**
        :key: A discord user (mention etc.)
        :key: A player name OR tag

        **Format**
        :information_source: `+add discord @MENTION #PLAYER_TAG`
        :information_source: `+add discord @MENTION PLAYER NAME`

        **Example**
        :white_check_mark: `+add discord @mathsman #P0LYJC8C`
        :white_check_mark: `+add discord @mathsman mathsman`
        """
        if not user:
            user = ctx.author
        if not isinstance(player, coc.Player):
            player = await self.bot.coc.get_player(player.tag)

        season_id = await self.bot.seasonconfig.get_season_id()
        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
        fetch = await ctx.db.fetchrow(query, player.tag, season_id)

        if fetch and fetch[0] is not None:
            return await ctx.send(f'Player {player.name} ({player.tag}) '
                                  f'has already been claimed by {self.bot.get_user(fetch[0])}')

        if ctx.config:
            if ctx.config.start < datetime.datetime.utcnow():
                prompt = await ctx.prompt(f'Do you wish to add {player} to the current event?')
                await self.insert_player(ctx.db, player, season_id, prompt, ctx.config.event_id)
        else:
            await self.insert_player(ctx.db, player, season_id)

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3"
        await ctx.db.execute(query, user.id, player.tag, season_id)
        await ctx.confirm()

    @add.command(name='multidiscord', aliases=['multi_discord', 'multiclaim', 'multi_claim', 'multilink', 'multi_link'])
    @requires_config('event')
    async def add_multi_discord(self, ctx, user: discord.Member,
                                players: commands.Greedy[PlayerConverter]):
        """Helper command to link many clash accounts to a user's discord.

        **Parameters**
        :key: A discord user (mention etc.)
        :key: Player tags OR names

        **Format**
        :information_source: `+add discord @MENTION #PLAYER_TAG #PLAYER_TAG2 #PLAYER_TAG3`
        :information_source: `+add discord @MENTION PLAYERNAME PLAYERNAME2 PLAYERNAME3`

        **Example**
        :white_check_mark: `+add discord @mathsman #P0LYJC8C #C0LLJC8 #P0CC8JY`
        :white_check_mark: `+add discord @mathsman mathsman raptor217 johnny36`
        """
        for n in players:
            # TODO: fix this
            await ctx.invoke(self.add_discord, user=user, player=n)

    @add.command(name="event")
    @checks.manage_guild()
    @requires_config('event', invalidate=True)
    async def add_event(self, ctx, *, event_name: str = None):
        """Allows user to add a new trophy push event. Trophy Push events override season statistics for trophy
        counts.

        This command is interactive and will ask you questions about the new event. After the initial command,
        the bot will ask you further questions about the event.

        **Parameters**
        :key: Name of the event

        **Format**
        :information_source: `+add event EVENT NAME`

        **Example**
        :white_check_mark: `+add event Donation Bot Event`

        **Required Permissions**
        :warning: Manage Server
        """
        if ctx.config:
            if ctx.config.start > datetime.datetime.now():
                return await ctx.send(f'This server is already set up for {ctx.config.event_name}. Please use '
                                      f'`+remove event` if you would like to remove this event and create a new one.')

        def check_author(m):
            return m.author == ctx.author

        if not event_name:
            try:
                await ctx.send('Please enter the name of the new event.')
                response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                event_name = response.content
            except asyncio.TimeoutError:
                return await ctx.send('I can\'t wait all day. Try again later.')

        for i in range(5):
            try:
                await ctx.send(f'What date does the {event_name} begin?  (YYYY-MM-DD)')
                response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                start_date = await DateConverter().convert(ctx, response.clean_content)
                break
            except (ValueError, commands.BadArgument):
                await ctx.send('Date must be in the YYYY-MM-DD format.')
            except asyncio.TimeoutError:
                return await ctx.send('Yawn! Time\'s up. You\'re going to have to start over some other time.')
        else:
            return await ctx.send(
                'I don\'t really know what happened, but I can\'t figure out what the start '
                'date is. Please start over and let\'s see what happens')

        try:
            await ctx.send('And what time does this fantastic event begin? (Please provide HH:MM in UTC)')
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
            start_time = datetime.time(hour, minute)
        except asyncio.TimeoutError:
            return await ctx.send('I was asking for time, but you ran out of it. You\'ll have to start over again.')

        event_start = datetime.datetime.combine(start_date, start_time)

        try:
            await ctx.send('What is the end date for the event? (YYYY-MM-DD)')
            response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
            year, month, day = map(int, response.content.split('-'))
            end_date = datetime.date(year, month, day)
        except asyncio.TimeoutError:
            return await ctx.send('I can\'t wait all day. Try again later.')

        answer = await ctx.prompt('Does the event end at the same time of day?')
        if answer:
            end_time = start_time
        elif answer is None:
            end_time = start_time
            await ctx.send('You must have fallen asleep. I\'ll just set the end time to match the start time.')
        else:
            try:
                await ctx.send('What time does the event end? (Please provide HH:MM in UTC)')
                response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                hour, minute = map(int, response.content.split(':'))
                end_time = datetime.time(hour, minute)
            except asyncio.TimeoutError:
                end_time = start_time
                await ctx.send('You must have fallen asleep. I\'ll just set the end time to match the start time.')

        event_end = datetime.datetime.combine(end_date, end_time)

        try:
            await ctx.send('Which #channel do you want me to send updates '
                           '(event starting, ending, records broken etc.) to?')
            response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
            try:
                channel = await commands.TextChannelConverter().convert(ctx, response.content)
            except commands.BadArgument:
                return await ctx.send('Uh oh.. I didn\'t like that channel! '
                                      'Try the command again with a channel # mention or ID.')
        except asyncio.TimeoutError:
            return await ctx.send('I can\'t wait all day. Try again later.')

        query = 'INSERT INTO events (guild_id, event_name, start, finish, channel_id) VALUES ($1, $2, $3, $4, $5) RETURNING id'
        event_id = await ctx.db.fetchrow(query, ctx.guild.id, event_name, event_start, event_end, channel.id)
        log.info(f"{event_name} added to events table for {ctx.guild} by {ctx.author}")

        query = 'UPDATE clans SET in_event = True WHERE guild_id = $1'
        await ctx.db.execute(query, ctx.guild.id)

        fmt = (f'**Event Created:**\n\n{event_name}\n{event_start.strftime("%d %b %Y %H:%M")}\n'
               f'{event_end.strftime("%d %b %Y %H:%M")}\n\nEnjoy your event!')
        e = discord.Embed(colour=discord.Colour.green(),
                          description=fmt)
        await ctx.send(embed=e)
        self.bot.dispatch('event_register')

    @add.command(name="boards", aliases=["board"])
    @manage_guild()
    async def add_boards(self, ctx, *clan_tags):
        """Convenient method to create a board channel, and setup donation and trophyboards in one command.

        Pass in a list of clan tags seperated by a space ( ) to claim these clans to the board.
        Please make sure all clans have `dt` attached to the end of the clan description, before running this command.

        **Parameters**
        :key: Clan tags (#clantag) seperated by a space.

        **Format**
        :information_source: `+add boards #CLANTAG`

        **Example**
        :white_check_mark: `+add boards`
        :white_check_mark: `+add boards #P0LYJC8C`
        :white_check_mark: `+add boards #P0LYJC8C #8J8QJ2LV #P9U9YVG`

        **Required Permissions**
        :warning: Manage Server

        """
        if not ctx.me.guild_permissions.manage_channels:
            return await ctx.send('I need manage channels permission to create your board channel!')

        overwrites = {
            ctx.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                manage_messages=True
            ),
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                read_message_history=True)
        }
        reason = f'{str(ctx.author)} created a boards channel.'

        try:
            channel = await ctx.guild.create_text_channel(name="dt-boards", overwrites=overwrites, reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                'I do not have permissions to create the trophyboard channel.')
        except discord.HTTPException:
            return await ctx.send('Creating the channel failed. Try checking the name?')

        old_channel = ctx.channel
        for tag in clan_tags:
            await ctx.invoke(self.add_clan, channel=channel, clan_tag=tag)
        ctx.channel = old_channel  # add_clan modifies this so we need to revert it

        await ctx.invoke(self.add_donationboard, channel=channel, use_channel=True)
        await ctx.invoke(self.add_trophyboard, channel=channel, use_channel=True)

    @add.command(name="trophyboard")
    @manage_guild()
    async def add_trophyboard(self, ctx, *, channel: discord.TextChannel = None, use_channel=False):
        """Registers a trophy-board to the channel, or creates a new channel for you.

        If you don't pass in a channel (#mention), it will create a new #dt-boards channel for you.

        **Parameters**
        :key: A channel (#mention etc.)

        **Format**
        :information_source: `+add trophyboard #CHANNEL`

        **Example**
        :white_check_mark: `+add trophyboard`
        :white_check_mark: `+add trophyboard #CHANNEL`

        **Required Permissions**
        :warning: Manage Server
        """
        if channel and not use_channel:
            fetch = await ctx.db.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                return await ctx.send(
                    "I cannot setup a board here, because the bot didn't create the channel! Try again with `+add boards`.")
            if any(n['type'] == 'trophy' for n in fetch):
                return await ctx.send("A trophyboard is already setup here.")

        elif not channel:
            if not ctx.me.guild_permissions.manage_channels:
                return await ctx.send(
                    'I need manage channels permission to create your board channel!'
                )

            overwrites = {
                ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    read_message_history=True, embed_links=True,
                                                    manage_messages=True),
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                    send_messages=False,
                                                                    read_message_history=True)
            }
            reason = f'{str(ctx.author)} created a boards channel.'

            try:
                channel = await ctx.guild.create_text_channel(name="dt-boards",
                                                              overwrites=overwrites,
                                                              reason=reason)
            except discord.Forbidden:
                return await ctx.send(
                    'I do not have permissions to create the trophyboard channel.')
            except discord.HTTPException:
                return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send('Trophyboard Placeholder. Please do not delete me!')
        await msg.add_reaction("<:refresh:694395354841350254>")
        await msg.add_reaction("\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("<:gain:696280508933472256>")
        await msg.add_reaction("<:lastonline:696292732599271434>")
        await msg.add_reaction("<:historical:694812540290465832>")

        query = """INSERT INTO boards (
                        guild_id, 
                        channel_id, 
                        message_id,
                        type,
                        title,
                        sort_by
                    ) 
                VALUES ($1, $2, $3, $4, $5, $6) 
                ON CONFLICT (channel_id, type) 
                DO UPDATE SET message_id = $3, toggle = True;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id, msg.id, 'trophy', "Trophy Leaderboard", 'trophies')
        await self.bot.donationboard.update_board(message_id=msg.id)
        await ctx.send(
            f"Your board channel: {channel} now has a registered trophyboard. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )

    @add.command(name='donationboard')
    @manage_guild()
    async def add_donationboard(self, ctx, *, channel: discord.TextChannel = None, use_channel=False):
        """Registers a donation-board to the channel, or creates a new channel for you.

        If you don't pass in a channel (#mention), it will create a new #dt-boards channel for you.

        **Parameters**
        :key: A channel (#mention etc.)

        **Format**
        :information_source: `+add donationboard #CHANNEL`

        **Example**
        :white_check_mark: `+add donationboard`
        :white_check_mark: `+add donationboard #CHANNEL`

        **Required Permissions**
        :warning: Manage Server
        """
        if channel and not use_channel:
            fetch = await ctx.db.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                return await ctx.send(
                    "I cannot setup a board here, because the bot didn't create the channel! Try again with `+add boards`.")
            if any(n['type'] == 'donation' for n in fetch):
                return await ctx.send("A donationboard is already setup here.")

        elif not channel:
            if not ctx.me.guild_permissions.manage_channels:
                return await ctx.send(
                    'I need manage channels permission to create your board channel!'
                )

            overwrites = {
                ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    read_message_history=True, embed_links=True,
                                                    manage_messages=True),
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                    send_messages=False,
                                                                    read_message_history=True)
            }
            reason = f'{str(ctx.author)} created a boards channel.'

            try:
                channel = await ctx.guild.create_text_channel(name="dt-boards",
                                                              overwrites=overwrites,
                                                              reason=reason)
            except discord.Forbidden:
                return await ctx.send(
                    'I do not have permissions to create the boards channel.')
            except discord.HTTPException:
                return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send('Donationboard Placeholder. Please don\'t delete me!')
        await msg.add_reaction("<:refresh:694395354841350254>")
        await msg.add_reaction("\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("<:percent:694463772135260169>")
        await msg.add_reaction("<:lastonline:696292732599271434>")
        await msg.add_reaction("<:historical:694812540290465832>")

        query = """INSERT INTO boards (
                        guild_id, 
                        channel_id, 
                        message_id,
                        type,
                        title,
                        sort_by
                    ) 
                VALUES ($1, $2, $3, $4, $5, $6) 
                ON CONFLICT (channel_id, type) 
                DO UPDATE SET message_id = $3, toggle = True;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id, msg.id, 'donation', "Donation Leaderboard", 'donations')
        await self.bot.donationboard.update_board(message_id=msg.id)
        await ctx.send(
            f"Your board channel: {channel} now has a registered donationboard. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )

    @add.command(name='lastonlineboard')
    @manage_guild()
    async def add_lastonlineboard(self, ctx, *, name='lastonlineboard'):
        """Last online boards are deprecated. Please use a donationboard or trophyboard instead - or even better, both!
        """
        return await ctx.send(
            "Last online boards are deprecated. Please use a donationboard or trophyboard instead - or even better, both!")

    @add.command(name='donationlog')
    @requires_config('donationlog', invalidate=True)
    @manage_guild()
    async def add_donationlog(self, ctx, channel: TextChannel = None):
        """Create a donation log for your server.

        **Parameters**
        :key: Discord channel (mention etc.)

        **Format**
        :information_source: `+add donationlog #CHANNEL`

        **Example**
        :white_check_mark: `+add donationlog #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        if not channel:
            channel = ctx.channel

        board_config = await self.bot.utils.board_config(channel.id)
        if board_config:
            return await ctx.send('You can\'t have the same channel for a board and log!')

        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(
                ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        query = """INSERT INTO logs (
                                guild_id,
                                channel_id,
                                toggle,
                                type
                                )
                VALUES ($1, $2, True, $3) 
                ON CONFLICT (channel_id, type)
                DO UPDATE SET channel_id = $2;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id, 'donation')

        prompt = await ctx.prompt(f'Would you like me to add all clans claimed on the server to this donationlog?\n'
                                  f'Else you can manually add clans with `+add clan #CLAN_TAG` to this channel.\n')
        if not prompt:
            return await ctx.send(f'{channel.mention} has been added as a donationlog channel.\n'
                                  f'Please note that only clans claimed to {channel.mention} will appear in this log.')

        query = """INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   SELECT 
                        clan_tag,
                        guild_id,
                        $2,
                        clan_name,
                        in_event

                   FROM clans
                   WHERE guild_id = $1
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a donationlog channel. '
                              'See all clans claimed with `+info clans`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @add.command(name='trophylog')
    @requires_config('trophylog', invalidate=True)
    @manage_guild()
    async def add_trophylog(self, ctx, channel: discord.TextChannel = None):
        """Create a trophy log for your server.

        **Parameters**
        :key: Discord channel (mention etc.)

        **Format**
        :information_source: `+add trophylog #CHANNEL`

        **Example**
        :white_check_mark: `+add trophylog #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        if not channel:
            channel = ctx.channel

        board_config = await self.bot.utils.board_config(channel.id)
        if board_config:
            return await ctx.send('You can\'t have the same channel for a board and log!')

        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(
                ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        query = """INSERT INTO logs (
                                    guild_id,
                                    channel_id,
                                    toggle,
                                    type
                                    )
                    VALUES ($1, $2, True, $3) 
                    ON CONFLICT (channel_id, type)
                    DO UPDATE SET channel_id = $2;
                    """
        await ctx.db.execute(query, ctx.guild.id, channel.id, 'trophy')

        prompt = await ctx.prompt(
            f'Would you like me to add all clans claimed on the server to this trophylog?\n'
            f'Else you can manually add clans with `+add clan #CLAN_TAG` to this channel.\n')
        if not prompt:
            return await ctx.send(f'{channel.mention} has been added as a trophylog channel.\n'
                                  f'Please note that only clans claimed to {channel.mention} will appear in this log.')

        query = """INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   SELECT 
                        clan_tag,
                        guild_id,
                        $2,
                        clan_name,
                        in_event

                   FROM clans
                   WHERE guild_id = $1
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a trophylog channel. '
                              'See all clans claimed with `+info clans`. '
                              'Please note that only clans claimed to this channel will appear in the log.')


def setup(bot):
    bot.add_cog(Add(bot))
