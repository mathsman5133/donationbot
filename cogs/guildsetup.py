import discord
import asyncio
import typing
import datetime
import re
import coc
import logging

from discord.ext import commands
from cogs.utils.checks import requires_config, manage_guild
from cogs.utils.formatters import CLYTable
from cogs.utils.converters import PlayerConverter, ClanConverter, DateConverter, TextChannel
from .utils import checks

log = logging.getLogger(__name__)

url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                           r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")


class GuildConfiguration(commands.Cog, name='Server Setup'):
    """Setup and manage the bot's configurations for your server."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.before_invoke(ctx)

    async def cog_after_invoke(self, ctx):
        after_invoke = getattr(ctx, 'after_invoke', None)
        if after_invoke:
            await after_invoke(ctx)

    @staticmethod
    async def insert_player(connection, player, season_id, in_event: bool = False, event_id: int = None):
        query = """INSERT INTO players (
                                    player_tag,
                                    donations,
                                    received,
                                    trophies,
                                    season_id,
                                    start_friend_in_need,
                                    start_sharing_is_caring,
                                    start_attacks,
                                    start_defenses,
                                    start_best_trophies,
                                    start_update
                                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, True)
                    ON CONFLICT (player_tag, season_id) 
                    DO NOTHING
                """
        await connection.execute(query,
                                 player.tag,
                                 player.donations,
                                 player.received,
                                 player.trophies,
                                 season_id,
                                 player.achievements_dict['Friend in Need'].value,
                                 player.achievements_dict['Sharing is caring'].value,
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
                                            event_id,
                                            start_friend_in_need,
                                            start_sharing_is_caring,
                                            start_attacks,
                                            start_defenses,
                                            start_best_trophies,
                                            start_update
                                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, True)
                            ON CONFLICT (player_tag, event_id)
                            DO NOTHING
                        """
            await connection.execute(event_query,
                                     player.tag,
                                     player.donations,
                                     player.received,
                                     player.trophies,
                                     event_id,
                                     player.achievements_dict['Friend in Need'].value,
                                     player.achievements_dict['Sharing is caring'].value,
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
    @requires_config('event')
    async def add_clan(self, ctx, clan_tag: str):
        """Link a clan to your server.
        This will add all accounts in clan to the database, if not already added.

        Note: As a security feature, the clan must have the letters `dt` added
        at the end of the clan's description.

        This is a security feature of the bot to ensure you have proper (co)ownership of the clan.
        `dt` should be removed once the command has been sucessfully run.

        **Parameters**
        :key: A clan tag

        **Format**
        :information_source: `+add clan #CLAN_TAG`

        **Example**
        :white_check_mark: `+add clan #P0LYJC8C`

        **Required Permissions**
        :warning: Manage Server
        """
        current_clans = await self.bot.get_clans(ctx.guild.id)
        if len(current_clans) > 3 and not checks.is_patron_pred(ctx):
            return await ctx.send('You must be a patron to have more than 4 clans claimed per server. '
                                  'See more info with `+patron`, or join the support server for more help: '
                                  f'{self.bot.support_invite}')

        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "SELECT id FROM clans WHERE clan_tag = $1 AND channel_id = $2"
        fetch = await ctx.db.fetch(query, clan_tag, ctx.channel.id)
        if fetch:
            return await ctx.send('This clan has already been linked to the channel.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag, cache=False, update_cache=False)
        except coc.NotFound:
            return await ctx.send(f'Clan not found with `{clan_tag}` tag.')

        check = clan.description.strip().endswith('dt') \
                or await self.bot.is_owner(ctx.author) or clan_tag in (n.tag for n in current_clans)

        if not check:
            return await ctx.send('Please add the letters `dt` to the end of '
                                  f'`{clan.name}`\'s clan description. Wait 5 minutes and try again.'
                                  '\n\nThis is a security feature of the bot and should '
                                  'be removed once the clan has been added.')
        in_event = False
        if ctx.config:
            if ctx.config.start < datetime.datetime.utcnow():
                in_event = await ctx.prompt('Would you like this clan to be in the current event?')

        query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name, in_event) VALUES ($1, $2, $3, $4, $5)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, ctx.channel.id, clan.name, in_event)

        await ctx.send('Clan has been added. Please wait a moment while all players are added.')

        season_id = await self.bot.seasonconfig.get_season_id()
        async for member in clan.get_detailed_members():
            await self.insert_player(ctx.db, member, season_id, in_event,
                                     getattr(ctx.config, 'event_id', None))

        await ctx.send('Clan and all members have been added to the database (if not already added)')
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

        season_id = await self.bot.seasonconfig.get_season_id()
        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
        fetch = await ctx.db.fetchrow(query, player.tag, season_id)

        if fetch:
            return await ctx.send(f'Player {player.name} ({player.tag}) '
                                  f'has already been claimed by {self.bot.get_user(fetch[0])}')

        if ctx.config:
            if ctx.config.start < datetime.datetime.utcnow():
                prompt = await ctx.prompt(f'Do you wish to add {player} to the current event?')
                await self.insert_player(ctx.db, player, season_id, prompt, ctx.config.event_id)

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
        await self.bot.dispatch('event_register')

    @add.command(name="trophyboard")
    @checks.manage_guild()
    @requires_config('trophyboard', invalidate=True)
    async def add_trophyboard(self, ctx, *, name="trophyboard"):
        """Creates a trophyboard channel for trophy updates.

        **Format**
        :information_source: `+add trophyboard`

        **Example**
        :white_check_mark: `+add trophyboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if ctx.config is not None:
            return await ctx.send(
                f'This server already has a trophyboard (#{ctx.config.channel}). '
                f'If this has been deleted, please use `+remove trophyboard`.')

        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.manage_channels:
            return await ctx.send(
                'I need manage channels permission to create the trophyboard!')

        overwrites = {
            ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                read_message_history=True, embed_links=True,
                                                manage_messages=True),
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                send_messages=False,
                                                                read_message_history=True)
        }
        reason = f'{str(ctx.author)} created a trophyboard channel.'

        try:
            channel = await ctx.guild.create_text_channel(name=name,
                                                          overwrites=overwrites,
                                                          reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                'I do not have permissions to create the trophyboard channel.')
        except discord.HTTPException:
            return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send('Placeholder')

        query = """WITH t AS (
                        INSERT INTO messages (message_id, 
                                              guild_id, 
                                              channel_id) 
                        VALUES ($1, $2, $3)
                )
                   
                INSERT INTO boards (guild_id, 
                                    channel_id, 
                                    type,
                                    title) 
                VALUES ($2, $3, $4, $5) 
                ON CONFLICT (channel_id) 
                DO UPDATE SET channel_id = $3, 
                              toggle     = True;
                
                """
        await ctx.db.execute(query, msg.id, ctx.guild.id, channel.id, 'trophy', 'TrophyBoard')
        await ctx.send(f'Trophyboard channel created: {channel.mention}')

    @add.command(name='donationboard')
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True)
    async def add_donationboard(self, ctx, *, name='donationboard'):
        """Creates a donationboard channel for donation updates.

        **Format**
        :information_source: `+add donationboard`

        **Example**
        :white_check_mark: `+add donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if ctx.config:
            if ctx.config.channel is not None:
                return await ctx.send(
                    f'This server already has a donationboard (#{ctx.config.channel}).'
                    f'If this channel has been deleted, use `+remove donationboard`.')

        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.manage_channels:
            return await ctx.send(
                'I need manage channels permission to create the donationboard!')

        overwrites = {
            ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                read_message_history=True, embed_links=True,
                                                manage_messages=True),
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                send_messages=False,
                                                                read_message_history=True)
        }
        reason = f'{str(ctx.author)} created a donationboard channel.'

        try:
            channel = await ctx.guild.create_text_channel(name=name, overwrites=overwrites,
                                                          reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                'I do not have permissions to create the donationboard channel.')
        except discord.HTTPException:
            return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send('Placeholder')

        query = """WITH t AS (
                        INSERT INTO messages (message_id, 
                                              guild_id, 
                                              channel_id)
                        VALUES ($1, $2, $3)
                    )
                   INSERT INTO boards (guild_id, 
                                       channel_id, 
                                       type,
                                       title) 
                   VALUES ($2, $3, $4, $5) 
                   ON CONFLICT (channel_id) 
                   DO UPDATE SET channel_id = $3, 
                                 toggle     = True;
                """

        await ctx.db.execute(query, msg.id, ctx.guild.id, channel.id, 'donation', 'DonationBoard')
        await ctx.send(f'Donationboard channel created: {channel.mention}')

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

        query = """WITH t AS (
                        SELECT clan_tag,
                               guild_id,
                               channel_id,
                               in_event
                        FROM clans
                        WHERE guild_id = $1
                        )
                   INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   VALUES (
                        t.clan_tag,
                        t.guild_id,
                        $2,
                        t.clan_name,
                        t.in_event
                        )
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a donationlog channel. '
                              'See all clans claimed with `+info log`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @add.command(name='trophylog')
    @requires_config('trophylog', invalidate=True)
    @manage_guild()
    async def add_trophylog(self, ctx, channel: TextChannel = None):
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

        query = """WITH t AS (
                        SELECT clan_tag,
                               guild_id,
                               channel_id,
                               in_event
                        FROM clans
                        WHERE guild_id = $1
                        )
                   INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   VALUES (
                        t.clan_tag,
                        t.guild_id,
                        $2,
                        t.clan_name,
                        t.in_event
                        )
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a trophylog channel. '
                              'See all clans claimed with `+info log`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @commands.command()
    @requires_config('event')
    async def claim(self, ctx, user: typing.Optional[discord.Member] = None, *,
                    player: PlayerConverter):
        """Link a clash account to your discord account

        **Parameters**
        :key: Discord user (optional - defaults to yourself)
        :key: A player tag OR name

        **Format**
        :information_source: `+claim @MENTION #PLAYERTAG`
        :information_source: `+claim @MENTION PLAYER NAME`
        :information_source: `+claim #PLAYERTAG`

        **Example**
        :white_check_mark: `+claim @mathsman #P0LYJC8C`
        :white_check_mark: `+claim @mathsman mathsman5133`
        :white_check_mark: `+claim #P0LYJC8C`
        """
        if await self.add_discord.can_run(ctx):
            await ctx.invoke(self.add_discord, user=user, player=player)

    @commands.command(name='multiclaim')
    @requires_config('event')
    async def multi_claim(self, ctx, user: discord.Member,
                          players: commands.Greedy[PlayerConverter]):
        """Helper command to link many clash accounts to a user's discord.

        Note: unlike `+claim`, a discord mention **is not optional** - mention yourself if you want.

        **Parameters**
        :key: A discord user (mention etc.)
        :key: Player tags OR names

        **Format**
        :information_source: `+multiclaim @MENTION #PLAYER_TAG #PLAYER_TAG2 #PLAYER_TAG3`
        :information_source: `+multiclaim @MENTION PLAYERNAME PLAYERNAME2 PLAYERNAME3`

        **Example**
        :white_check_mark: `+multiclaim @mathsman #P0LYJC8C #C0LLJC8 #P0CC8JY`
        :white_check_mark: `+multiclaim @mathsman mathsman raptor217 johnny36`
        """
        if await self.add_multi_discord.can_run(ctx):
            await ctx.invoke(self.add_multi_discord, user=user, players=players)

    @commands.group(invoke_without_subcommands=True)
    async def remove(self, ctx):
        """[Group] Allows the user to remove a variety of features from the bot."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @remove.command(name='clan')
    @checks.manage_guild()
    async def remove_clan(self, ctx, clan_tag: str):
        """Unlink a clan from your server.

        **Parameters**
        :key: A clan tag

        **Format**
        :information_source: `+remove clan #CLAN_TAG`

        **Example**
        :white_check_mark: `+remove clan #P0LYJC8C`

        **Required Permissions**
        :warning: Manage Server
        """
        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "DELETE FROM clans WHERE clan_tag = $1 AND guild_id = $2"
        await ctx.db.execute(query, clan_tag, ctx.guild.id)

        try:
            clan = await self.bot.coc.get_clan(clan_tag)
            self.bot.dispatch('clan_unclaim', ctx, clan)
        except coc.NotFound:
            return await ctx.send('Clan not found.')
        await ctx.confirm()

    @remove.command(name='player')
    async def remove_player(self, ctx, *, player: PlayerConverter):
        """Manually remove a clash account from the database.

        **Parameters**
        :key: Player name OR tag.

        **Format**
        :information_source: `+remove player #PLAYER_TAG`
        :information_source: `+remove player PLAYER NAME`

        **Example**
        :white_check_mark: `+remove player #P0LYJC8C`
        :white_check_mark: `+remove player mathsman`
        """
        query = "DELETE FROM players WHERE player_tag = $1 and guild_id = $2"
        result = await ctx.db.execute(query, player.tag, ctx.guild.id)
        if result[:-1] == 0:
            return await ctx.send(f'{player.name}({player.tag}) was not found in the database.')
        await ctx.confirm()

    @remove.command(name='discord')
    async def remove_discord(self, ctx, *, player: PlayerConverter):
        """Unlink a clash account from your discord account.

        If you have not claimed the account, you must have `Manage Server` permissions.

        **Parameters**
        :key: Player name OR tag.

        **Format**
        :information_source: `+remove discord #PLAYER_TAG`
        :information_source: `+remove discord PLAYER NAME`

        **Example**
        :white_check_mark: `+remove discord #P0LYJC8C`
        :white_check_mark: `+remove discord mathsman`
        """
        season_id = await self.bot.seasonconfig.get_season_id()
        if ctx.channel.permissions_for(ctx.author).manage_guild \
                or await self.bot.is_owner(ctx.author):
            query = "UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2"
            await ctx.db.execute(query, player.tag, season_id)
            return await ctx.confirm()

        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
        fetch = await ctx.db.fetchrow(query, player.tag, season_id)
        if not fetch:
            query = "UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2"
            await ctx.db.execute(query, player.tag, season_id)
            return await ctx.confirm()

        if fetch[0] != ctx.author.id:
            return await ctx.send(f'Player has been claimed by '
                                  f'{self.bot.get_user(fetch[0]) or "unknown"}.\n'
                                  f'Please contact them, or someone '
                                  f'with `manage_guild` permissions to unclaim it.')

        query = "UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2"
        await ctx.db.execute(query, player.tag, season_id)
        await ctx.confirm()

    @remove.command(name='donationboard', aliases=['donation board', 'donboard'])
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True)
    async def remove_donationboard(self, ctx):
        """Removes the guild donationboard.

        **Format**
        :information_source: `+remove donationboard`

        **Example**
        :white_check_mark: `+remove donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send(f'This server doesn\'t have a donationboard.')

        query = "SELECT message_id FROM messages WHERE channel_id=$1;"
        messages = await self.bot.pool.fetch(query, ctx.config.channel_id)
        for n in messages:
            await self.bot.donationboard.safe_delete(n[0], delete_message=False)

        try:
            await ctx.config.channel.delete(reason=f'Command done by {ctx.author} ({ctx.author.id})')
        except (discord.Forbidden, discord.HTTPException):
            pass

        query = """UPDATE boards 
                   SET channel_id = NULL,
                       toggle     = False 
                   WHERE channel_id = $1
                """
        await self.bot.pool.execute(query, ctx.config.channel_id)
        await ctx.send('Donationboard sucessfully removed.')

    @remove.command(name='trophyboard', aliases=['trophy board', 'tropboard'])
    @checks.manage_guild()
    @requires_config('trophyboard', invalidate=True)
    async def remove_trophyboard(self, ctx):
        """Removes the guild trophyboard.

        **Format**
        :information_source: `+remove trophyboard`

        **Example**
        :white_check_mark: `+remove trophyboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send(
                f'This server doesn\'t have a trophyboard.')

        query = "SELECT message_id FROM messages WHERE channel_id=$1;"
        messages = await self.bot.pool.fetch(query, ctx.config.channel_id)
        for n in messages:
            await self.bot.donationboard.safe_delete(n[0], delete_message=False)

        try:
            await ctx.config.channel.delete(reason=f'Command done by {ctx.author} ({ctx.author.id})')
        except (discord.Forbidden, discord.HTTPException):
            pass

        query = "DELETE FROM boards WHERE channel_id = $1"
        await self.bot.pool.execute(query, ctx.config.channel_id)
        await ctx.send('Trophyboard sucessfully removed.')

    @remove.command(name='donationlog')
    @requires_config('donationlog', invalidate=True)
    @manage_guild()
    async def remove_donationlog(self, ctx, channel: TextChannel = None):
        """Removes a channel's donationlog.

        **Parameters**
        :key: A discord channel to remove the donationlog from.

        **Format**
        :information_source: `+remove donationlog #CHANNEL`

        **Example**
        :white_check_mark: `+remove donationlog #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        query = "DELETE FROM logs WHERE channel_id = $1 AND type = $2"
        await ctx.db.execute(query, ctx.config.channel_id, 'donation')
        await ctx.confirm()

    @remove.command(name='trophylog')
    @requires_config('trophylog', invalidate=True)
    @manage_guild()
    async def remove_trophylog(self, ctx, channel: TextChannel = None):
        """Removes a channel's trophylog.

        **Parameters**
        :key: A discord channel to remove the trophylog from.

        **Format**
        :information_source: `+remove trophylog #CHANNEL`

        **Example**
        :white_check_mark: `+remove trophylog #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        query = "DELETE FROM logs WHERE channel_id = $1 AND type = $2"
        await ctx.db.execute(query, ctx.config.channel_id, 'trophy')
        await ctx.confirm()

    @remove.command(name='event')
    @manage_guild()
    async def remove_event(self, ctx, *, event_name: str = None):
        """Removes a currently running event.

        **Parameters**
        :key: The event name to remove.

        **Format**
        :information_source: `+remove event EVENT_NAME`

        **Example**
        :white_check_mark: `+remove event my special event`

        **Required Permissions**
        :warning: Manage Server
        """
        if event_name:
            # Event name provided
            query = """DELETE FROM events
                       WHERE guild_id = $1 
                       AND event_name = $2
                       RETURNING id;
                    """
            fetch = await self.bot.pool.fetchrow(query, ctx.guild.id, event_name)
            if fetch:
                return await ctx.send(f"{event_name} has been removed.")

        # No event name provided or I didn't understand the name I was given
        query = """SELECT id, event_name, start 
                   FROM events
                   WHERE guild_id = $1 
                   ORDER BY start"""
        fetch = await self.bot.pool.fetch(query, ctx.guild.id)
        if len(fetch) == 0 or not fetch:
            return await ctx.send("I have no events to remove. You should create one... then remove it.")
        elif len(fetch) == 1:
            query = "DELETE FROM events WHERE id = $1"
            await ctx.db.execute(query, fetch[0]['id'])
            return await ctx.send(f"{fetch[0]['event_name']} has been removed.")

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
            return await ctx.send("We'll just hang on to all the events we have for now.")

        index = reactions.index(str(r))
        query = "DELETE FROM events WHERE id = $1"
        await ctx.db.execute(query, fetch[index]['id'])
        await msg.delete()
        ctx.bot.utils.event_config.invalidate(ctx.bot.utils, ctx.guild.id)
        await self.bot.dispatch('event_register')
        return await ctx.send(f"{fetch[index]['event_name']} has been removed.")

    @commands.command()
    async def unclaim(self, ctx, *, player: PlayerConverter):
        """Unlink a clash account from your discord account.

        If you have not claimed the account, you must have `Manage Server` permissions.

        **Parameters**
        :key: Player name OR tag.

        **Format**
        :information_source: `+unclaim #PLAYER_TAG`
        :information_source: `+unclaim PLAYER NAME`

        **Example**
        :white_check_mark: `+unclaim #P0LYJC8C`
        :white_check_mark: `+unclaim mathsman`
        """
        if await self.remove_discord.can_run(ctx):
            await ctx.invoke(self.remove_discord, player=player)

    @commands.group(invoke_without_command=True)
    async def edit(self, ctx):
        """[Group] Allows a user to edit a variety of the bot's features."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @edit.group(name='donationboard')
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True)
    async def edit_donationboard(self, ctx):
        """[Group] Run through an interactive process of editting the guild's donationboard.

        **Format**
        :information_source: `+edit donationboard`

        **Example**
        :white_check_mark: `+edit donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        if not ctx.config:
            return await ctx.send('Please create a donationboard with `+help add donationboard`')

        p = await ctx.prompt('Would you like to edit all settings for the guild donationboard? '
                             'Else please see valid subcommands with `+help edit donationboard`.')
        if not p or p is False:
            return

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
    @requires_config('donationboard', invalidate=True)
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
    @requires_config('donationboard', invalidate=True)
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

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, url, ctx.config.channel_id)
        await ctx.confirm()

    @edit_donationboard.command(name='title')
    @requires_config('donationboard', invalidate=True)
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

    @edit.group(name='trophyboard')
    @checks.manage_guild()
    @requires_config('trophyboard', invalidate=True)
    async def edit_trophyboard(self, ctx):
        """[Group] Run through an interactive process of editing the guild's trophyboard.

        **Format**
        :information_source: `+edit trophyboard`

        **Example**
        :white_check_mark: `+edit trophyboard`

        **Required Permissions**
        :warning: Manage Server
        """
        p = await ctx.prompt('Would you like to edit all settings for the guild trophyboard? '
                             'Else please see valid subcommands with `+help edit trophyboard`.')
        if not p or p is False:
            return

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
    @requires_config('trophyboard', invalidate=True)
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
    @requires_config('trophyboard', invalidate=True)
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

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, url, ctx.config.channel_id)
        await ctx.confirm()

    @edit_trophyboard.command(name='title')
    @requires_config('trophyboard', invalidate=True)
    @manage_guild()
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

    @edit.group(name='donationlog')
    @manage_guild()
    async def edit_donationlog(self, ctx):
        """[Group] Edit the donationlog settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @edit_donationlog.command(name='interval')
    @requires_config('donationlog', invalidate=True)
    @manage_guild()
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
                                  'Try `+info log` to find where the registered channels are!')

        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                """
        await ctx.db.execute(query, str(minutes), ctx.config.channel_id, 'donation')
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been changed to {minutes} minutes. '
                       'Find which clans this affects with `+help info donationlog`')

    @edit.group(name='trophylog')
    @checks.manage_guild()
    async def edit_trophylog(self, ctx):
        """[Group] Edit the trophylog settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @edit_trophylog.command(name='interval')
    @requires_config('trophylog', invalidate=True)
    @manage_guild()
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
                                  'Try `+info log` to find where the registered channels are!')

        query = """UPDATE logs
                   SET interval = ($1 ||' minutes')::interval
                   WHERE channel_id=$2
                   AND type = $3
                """
        await ctx.db.execute(query, str(minutes), ctx.config.channel_id, 'trophy')
        await ctx.send(f'Logs for {ctx.config.channel.mention} have been changed to {minutes} minutes. '
                       'Find which clans this affects with `+help info trophylog`')

    @edit.command(name='event')
    @manage_guild()
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
            await self.bot.dispatch('event_register')

    @commands.command()
    @checks.manage_guild()
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
            query = """WITH t AS 
                        (
                            UPDATE players 
                            SET donations = $1
                            WHERE player_tag = $3
                            AND donations <= $1
                        )
                        UPDATE players 
                        SET received = $2
                        WHERE player_tag = $3
                        AND received <= $2                 
                    """
            query2 = """UPDATE players
                        SET trophies = $1
                        WHERE player_tag = $2
                        AND trophies != $1
                    """
            for clan in clans:
                for member in clan.members:
                    await ctx.db.execute(query, member.donations, member.received, member.tag)
                    await ctx.db.execute(query2, member.trophies, member.tag)

            dboard_channel = await self.bot.utils.get_board_channel(ctx.guild.id, 'donation')
            if dboard_channel:
                await self.bot.donationboard.update_board(int(dboard_channel))

            tboard_channel = await self.bot.utils.get_board_channel(ctx.guild.id, 'trophy')
            if tboard_channel:
                await self.bot.donationboard.update_board(int(tboard_channel))

            await ctx.send('All done - I\'ve force updated the boards too!')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reset_cooldown(self, ctx, guild_id: int = None):
        if guild_id:
            ctx.guild = self.bot.get_guild(guild_id)

        self.refresh.reset_cooldown(ctx)
        await ctx.confirm()


def setup(bot):
    bot.add_cog(GuildConfiguration(bot))
