import discord
import asyncio
import math
import typing
import datetime
import re
import coc
import logging

from discord.ext import commands
from cogs.utils import checks, cache
from cogs.utils.db_objects import DatabaseBoard
from cogs.utils.error_handler import error_handler
from cogs.utils.formatters import CLYTable
from cogs.utils.converters import PlayerConverter, ClanConverter, DateConverter
from .utils import paginator, checks, formatters, fuzzy

log = logging.getLogger(__name__)


def requires_config(config_type, invalidate=False):
    async def pred(ctx):
        ctx.config_type = config_type
        ctx.config_invalidate = invalidate
        return True
    return commands.check(pred)


class GuildConfiguration(commands.Cog):
    """All commands related to setting up the server for the first time,
    and managing configurations."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        config_type = getattr(ctx, 'config_type', None)
        if not config_type:
            return
        invalidate = getattr(ctx, 'config_invalidate', False)

        key = ctx.guild.id
        if config_type == 'donationboard':
            if invalidate:
                ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)
            config = await ctx.bot.utils.board_config(key, 'donation')

        elif config_type == 'trophyboard':
            if invalidate:
                ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

            config = await ctx.bot.utils.board_config(key, 'trophy')

        elif config_type == 'log':
            channel = getattr(ctx, 'log_channel', ctx.channel)
            key = channel.id
            if invalidate:
                ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

            config = await ctx.bot.utils.log_config(key)

        elif config_type == 'events':
            if invalidate:
                ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

            config = await ctx.bot.utils.event_config(key)
        else:
            return

        ctx.config = config
        ctx.config_key = key
        return

    async def cog_after_invoke(self, ctx):
        config_type = getattr(ctx, 'config_type', None)
        if not config_type:
            return
        invalidate = getattr(ctx, 'config_invalidate', False)
        if not invalidate:
            return

        key = ctx.guild.id
        if config_type == 'donationboard':
            ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

        elif config_type == 'trophyboard':
            ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

        elif config_type == 'log':
            channel = getattr(ctx, 'log_channel', ctx.channel)
            ctx.bot.utils.board_config.invalidate(ctx.bot.utils, channel.id)

        elif config_type == 'events':
            ctx.bot.utils.board_config.invalidate(ctx.bot.utils, key)

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        await error_handler(ctx, error)

    async def match_player(self, player, guild: discord.Guild, prompt=False, ctx=None,
                           score_cutoff=20, claim=True):
        matches = fuzzy.extract_matches(player.name, [n.name for n in guild.members],
                                        score_cutoff=score_cutoff, scorer=fuzzy.partial_ratio,
                                        limit=9)
        if len(matches) == 0:
            return None
        if len(matches) == 1:
            user = guild.get_member_named(matches[0][0])
            if prompt:
                m = await ctx.prompt(f'[auto-claim]: {player.name} ({player.tag}) '
                                     f'to be claimed to {str(user)} ({user.id}). '
                                     f'If already claimed, this will do nothing.')
                if m is True and claim is True:
                    query = "UPDATE players SET user_id = $1 " \
                            "WHERE player_tag = $2 AND user_id IS NULL AND season_id = $3"
                    await self.bot.pool.execute(query, user.id, player.tag,
                                                await self.bot.seasonconfig.get_season_id())
                else:
                    return False
            return user
        return [guild.get_member_named(n[0]) for n in matches]

    async def match_member(self, member, clan, claim):
        matches = fuzzy.extract_matches(member.name, [n.name for n in clan.members],
                                        score_cutoff=60)
        if len(matches) == 0:
            return None
        for i, n in enumerate(matches):
            query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
            m = clan.get_member(name=n[0])
            fetch = await self.bot.pool.fetchrow(query, m.tag,
                                                 await self.bot.seasonconfig.get_season_id())
            if fetch is None:
                continue
            del matches[i]

        if len(matches) == 1 and claim is True:
            player = clan.get_member(name=matches[0][0])
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 " \
                    "AND user_id IS NULL AND season_id = $3"
            await self.bot.pool.execute(query, member.id, player.tag,
                                        await self.bot.seasonconfig.get_season_id())
            return player
        elif len(matches) == 1:
            return True

        return [clan.get_member(name=n) for n in matches]

    @commands.group(invoke_without_subcommand=True)
    async def add(self, ctx):
        """Allows the user to add a variety of features to the bot.

        Available Commands
        ------------------
        • `add clan`
        • `add player`
        • `add event`
        • `add donationboard`
        • `add trophyboard`
        • `add attackboard`

        Required Permissions
        --------------------
        • `manage_server` permissions
        """
        if ctx.invoke_subcommand is None:
            return await ctx.send_help(ctx.command)

    @add.command(name='clan')
    @checks.manage_guild()
    @requires_config('event')
    async def add_clan(self, ctx, clan_tag: str):
        """Link a clan to your server.
        This will add all accounts in clan to the database, if not already present.

        Note: As a security feature, the clan must have the letters `dt` added
        at the end of the clan's description.

        This is a security feature of the bot to ensure you have proper (co)ownership of the clan.
        `dt` should be removed once the command has been sucessfully run.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag

        Example
        -----------
        • `+add clan #CLAN_TAG`

        Required Permissions
        ------------------------------
        • `manage_server` permissions
        """
        current_clans = await self.bot.get_clans(ctx.guild.id)
        if len(current_clans) > 3 and not checks.is_patron_pred(ctx):
            return await ctx.send('You must be a patron to have more than 4 clans claimed per server. '
                                  'See more info with `+patron`, or join the support server for more help: '
                                  f'{self.bot.support_invite}')

        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "SELECT id FROM clans WHERE clan_tag = $1 AND guild_id = $2"
        fetch = await ctx.db.fetch(query, clan_tag, ctx.guild.id)
        if fetch:
            return await ctx.send('This clan has already been linked to the server.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag, cache=False, update_cache=False)
        except coc.NotFound:
            return await ctx.send(f'Clan not found with `{clan_tag}` tag.')

        if not clan.description.strip().endswith('dt'):
            return await ctx.send('Please add the letters `dt` to the end of '
                                  f'`{clan.name}`\'s clan description. Wait 5 minutes and try again.'
                                  '\n\nThis is a security feature of the bot and should '
                                  'be removed once the clan has been added.')

        if ctx.config.in_event:
            prompt = await ctx.prompt('Would you like this clan to be in the current event?')

            if prompt is True:
                in_event = True
            else:
                in_event = False
        else:
            in_event = False

        query = "INSERT INTO clans (clan_tag, guild_id, clan_name, in_event) VALUES ($1, $2, $3, $4)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, clan.name, in_event)

        query = "INSERT INTO players (player_tag, donations, received, trophies, season_id) " \
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (player_tag, season_id) DO NOTHING"

        season_id = await self.bot.seasonconfig.get_season_id()
        for member in clan.itermembers:
            await ctx.db.execute(query, member.tag, member.donations, member.received, member.trophies, season_id)

        if in_event:
            query = "INSERT INTO players (player_tag, donations, received, trophies, event_id) " \
                    "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (player_tag, event_id) DO NOTHING"
            for member in clan.itermembers:
                await ctx.db.execute(query, member.tag, member.donations, member.received, member.trophies,
                                     ctx.config.event_id)

        await ctx.confirm()
        await ctx.send('Clan and all members have been added to the database (if not already added)')
        self.bot.dispatch('clan_claim', ctx, clan)

    @add.command(name='player')
    async def add_player(self, ctx, *, player: PlayerConverter):
        """Manually add a clash account to the database. This does not claim the account.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in clan claimed in server)

        Example
        ------------
        • `+add player #PLAYER_TAG`
        • `+add player my account name`
        """
        query = "INSERT INTO players (player_tag, donations, received, trophies, season_id) " \
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (player_tag, season_id) DO NOTHING"
        await ctx.db.execute(query, player.tag, player.donations, player.received, player.trophies,
                             await self.bot.seasonconfig.get_season_id())
        await ctx.confirm()

    @add.command(name='discord', aliases=['claim', 'link'])
    async def add_discord(self, ctx, user: typing.Optional[discord.Member] = None, *,
                          player: PlayerConverter):
        """Link a clash account to your discord account

        Parameters
        ------------------
        First, pass in an optional discord user:
            • User ID
            • Mention (@user)
            • user#discrim (must be 1-word)

            • **Optional**: Defaults to the user calling the command.

        Then, pass in a clash account:
            • Player tag
            • Player name (must be in clan claimed in server)

        Examples
        -------------
        • `+add discord #PLAYER_TAG`
        • `+add discord @user my account name`
        • `+add discord @user #playertag`
        """
        if not user:
            user = ctx.author

        season_id = await self.bot.seasonconfig.get_season_id()
        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
        fetch = await ctx.db.fetchrow(query, player.tag, season_id)

        if not fetch:
            query = "INSERT INTO players (player_tag, donations, received, trophies, user_id, season_id) " \
                    "VALUES ($1, $2, $3, $4, $5, $6)"
            await ctx.db.execute(query, player.tag, player.donations, player.received, player.trophies,
                                 user.id, season_id)
            return await ctx.confirm()

        if fetch[0]:
            user = self.bot.get_user(fetch[0])
            raise commands.BadArgument(f'Player {player.name} '
                                       f'({player.tag}) has already been claimed by {str(user)}')

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3"
        await ctx.db.execute(query, user.id, player.tag, season_id)
        await ctx.confirm()

    @add.command(name='multidiscord', aliases=['multi_discord', 'multiclaim', 'multi_claim', 'multilink', 'multi_link'])
    async def multi_discord(self, ctx, user: discord.Member,
                            players: commands.Greedy[PlayerConverter]):
        """Helper command to link many clas accounts to a user's discord.

        Note: unlike `+claim`, a discord mention **is not optional** - mention yourself if you want.

        Parameters
        ------------------
        First, pass in a discord member:
            • User ID
            • Mention
            • user#discrim (can only be 1-word)

        Second, pass in a clash player:
            • Player tag
            • Player name (must be in clan claimed in server, can only be 1-word)

        Example
        -------------
        • `+multiclaim @mathsman #PLAYER_TAG #PLAYER_TAG2 name1 name2 #PLAYER_TAG3`
        • `+multiclaim @user #playertag name1`
        """
        for n in players:
            # TODO: fix this
            await ctx.invoke(self.add_discord, user=user, player=n)

    @add.command(name="event")
    @checks.manage_guild()
    @requires_config('event', invalidate=True)
    async def add_event(self, ctx, event_name: str = None):
        """Allows user to add a new trophy push event. Trophy Push events override season statistics for trophy
        counts.

        This command is interactive and will ask you questions about the new event.  After the initial command,
        the bot will ask you further questions about the event.

        Parameters
        ------------------
        • Name of the event

        Example
        ------------------
        • `+add event`
        • `+add event Summer Mega Push`

        Required Permissions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.config.event_start > datetime.datetime.now():
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
                start_date = await DateConverter().convert(ctx, response)
                break
            except ValueError:
                await ctx.send(f'Date must be in the YYYY-MM-DD format.')
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

        msg = await ctx.send('Does the event end at the same time of day?')
        reactions = ["🇾", "🇳"]
        for r in reactions:
            await msg.add_reaction(r)

        def check(r, u):
            return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

        try:
            r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
            if r == reactions[0]:
                end_time = start_time
            else:
                try:
                    await ctx.send('What time does the event end? (Please provide HH:MM in UTC)')
                    response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
                    hour, minute = map(int, response.content.split(':'))
                    end_time = datetime.time(hour, minute)
                except asyncio.TimeoutError:
                    end_time = start_time
                    await ctx.send('You must have fallen asleep. I\'ll just set the end time to match the start time.')
        except asyncio.TimeoutError:
            end_time = start_time
            await ctx.send('No answer? I\'ll assume that\'s a yes then!')

        event_end = datetime.datetime.combine(end_date, end_time)

        query = 'INSERT INTO events (guild_id, event_name, start, finish) VALUES ($1, $2, $3, $4)'
        await ctx.db.execute(query, ctx.guild.id, event_name, event_start, event_end)
        log.info(f"{event_name} added to events table for {ctx.guild} by {ctx.author}")

        try:
            await ctx.send('Alright now I just need to know what clans will be in this event. You can provide the '
                           'clan tags all at once (separated by a space) or individually.')
            response = await self.bot.wait_for('message', check=check_author, timeout=180.00)
            clans = response.split(' ')
            clan_names = ''
            for clan in clans:
                clan = await ClanConverter().convert(ctx, clan)

                query = 'INSERT INTO clans (clan_tag, clan_name, channel_id, guild_id, in_event) VALUES ' \
                        '($1, $2, $3, $4, $5) ON CONFLICT (clan_tag, guild_id) DO UPDATE SET in_event = $5'
                await ctx.db.execute(query, clan.tag, clan.name, ctx.channel.id, ctx.guild.id, True)

                clan_names += f'\n{clan.name}'

            fmt_tag = (f'Clans added for this event:\n' 
                       f'{clan_names}')

        except asyncio.TimeoutError:
            fmt_tag = "Please use the `+add clan` command later to add clans to this event."

        fmt = (f'**Event Created:**\n\n{event_name}\n{event_start.strftime("%d %b %Y %H:%M")}\n'
               f'{event_end.strftime("%d %b %Y %H:%M")}\n\n{fmt_tag}\n\nEnjoy your event!')
        e = discord.Embed(colour=discord.Colour.green(),
                          description=fmt)
        await ctx.send(embed=e)

    @add.command(name="trophyboard")
    @checks.manage_guild()
    @requires_config('trophyboard', invalidate=True)
    async def add_trophyboard(self, ctx, *, name="trophyboard"):
        """Creates a trophyboard channel for trophy updates.

        Parameters
        ----------------
        Pass in any of the following:

            • A name for the channel. Defaults to `trophyboard`

        Example
        -----------
        • `+add trophyboard`
        • `+add trophyboard my cool trophyboard name`

        Required Permissions
        ----------------------------
        • `manage_server` permissions

        Bot Required Permissions
        --------------------------------
        • `manage_channels` permissions
        """
        if ctx.config.channel is not None:
            return await ctx.send(
                f'This server already has a trophyboard ({ctx.config.channel.mention}')

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

        query = """INSERT INTO messages (message_id, 
                                         guild_id, 
                                         channel_id) 
                   VALUES ($1, $2, $3);
                   INSERT INTO boards (guild_id, 
                                       channel_id, 
                                       board_type) 
                   VALUES ($2, $3, $4) 
                   ON CONFLICT (channel_id) 
                   DO UPDATE SET channel_id = $3, 
                                 toggle     = True;
                """
        await ctx.db.executemany(query, msg.id, ctx.guild.id, channel.id, 'trophy')
        await ctx.send(f'Trophyboard channel created: {channel.mention}')

    @add.command(name='donationboard')
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True)
    async def add_donationboard(self, ctx, *, name='donationboard'):
        """Creates a donationboard channel for donation updates.

        Parameters
        ----------------
        Pass in any of the following:

            • A name for the channel. Defaults to `donationboard`

        Example
        -----------
        • `+add donationboard`
        • `+add donationboard my cool donationboard name`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions

        Bot Required Permissions
        --------------------------------
        • `manage_channels` permissions
        """
        if ctx.config.channel is not None:
            return await ctx.send(
                f'This server already has a donationboard ({ctx.config.channel.mention})')

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

        query = """INSERT INTO messages (message_id, 
                                         guild_id, 
                                         channel_id) 
                   VALUES ($1, $2, $3);
                   INSERT INTO boards (guild_id, 
                                       channel_id, 
                                       board_type) 
                   VALUES ($2, $3, $4) 
                   ON CONFLICT (channel_id) 
                   DO UPDATE SET channel_id = $3, 
                                 toggle     = True;
                """

        await ctx.db.execute(query, msg.id, ctx.guild.id, channel.id, 'donation')
        await ctx.send(f'Donationboard channel created: {channel.mention}')

    @commands.command()
    async def claim(self, ctx, user: typing.Optional[discord.Member] = None, *,
                    player: PlayerConverter):
        """Link a clash account to your discord account

        Parameters
        ------------------
        First, pass in an optional discord user:
            • User ID
            • Mention (@user)
            • user#discrim (must be 1-word)

            • **Optional**: Defaults to the user calling the command.

        Then, pass in a clash account:
            • Player tag
            • Player name (must be in clan claimed in server)

        Examples
        -------------
        • `+claim #PLAYER_TAG`
        • `+claim @user my account name`
        • `+claim @user #playertag`
        """
        if await self.add_discord.can_run(ctx):
            await ctx.invoke(self.add_discord, user=user, player=player)

    @commands.command(name='multiclaim')
    async def multi_claim(self, ctx, user: discord.Member,
                          players: commands.Greedy[PlayerConverter]):
        """Helper command to link many clash accounts to a user's discord.

        Note: unlike `+claim`, a discord mention **is not optional** - mention yourself if you want.

        Parameters
        ------------------
        First, pass in a discord member:
            • User ID
            • Mention
            • user#discrim (can only be 1-word)

        Second, pass in a clash player:
            • Player tag
            • Player name (must be in clan claimed in server, can only be 1-word)

        Example
        -------------
        • `+multiclaim @mathsman #PLAYER_TAG #PLAYER_TAG2 name1 name2 #PLAYER_TAG3`
        • `+multiclaim @user #playertag name1`
        """
        if await self.multi_discord.can_run(ctx):
            await ctx.invoke(self.multi_discord, user=user, players=players)

    @commands.group(invoke_without_subcommands=True)
    async def remove(self, ctx):
        """Allows the user to remove a variety of features from the bot.

        Available Commands
        ------------------
        • `remove clan`
        • `remove player`
        • `remove event`
        • `remove donationboard`
        • `remove trophyboard`
        • `remove attackboard`

        Required Permissions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.invoke_subcommand is None:
            return await ctx.send_help(ctx.command)

    @remove.command(name='clan')
    @checks.manage_guild()
    async def remove_clan(self, ctx, clan_tag: str):
        """Unlink a clan from your server.

        Parameters
        -----------------
        Pass in any of the following:

            • A clan tag

        Example
        -------------
        • `+remove clan #CLAN_TAG`

        Required Permissions
        ----------------------------
        • `manage_server` permissions
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

    @remove.command()
    async def remove_player(self, ctx, *, player: PlayerConverter):
        """Manually remove a clash account from the database.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name

        Example
        ------------
        • `+remove player #PLAYER_TAG`
        • `+remove player my account name`
        """
        query = "DELETE FROM players WHERE player_tag = $1 and guild_id = $2"
        result = await ctx.db.execute(query, player.tag, ctx.guild.id)
        if result[:-1] == 0:
            return await ctx.send(f'{player.name}({player.tag}) was not found in the database.')
        await ctx.confirm()

    @remove.command()
    async def remove_discord(self, ctx, *, player: PlayerConverter):
        """Unlink a clash account from your discord account

        Parameters
        ----------------
        Pass in a clash account - either:
            • Player tag
            • Player name (must be in clan claimed in server)

        Example
        -------------
        • `+remove claim #PLAYER_TAG`
        • `+remove claim my account name`
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
    async def remove_trophyboard(self, ctx):
        """Removes the guild donationboard.

        Example
        -----------
        • `+remove donationboard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.config.channel is None:
            return await ctx.send(
                f'This server doesn\'t have a donationboard.')

        query = "SELECT message_id FROM messages WHERE channel_id=$1;"
        messages = await self.bot.pool.fetch(query, ctx.config.channel_id)
        for n in messages:
            await self.bot.donationboard.safe_delete(n[0])

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

        Example
        -----------
        • `+remove trophyboard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if ctx.config.channel is None:
            return await ctx.send(
                f'This server doesn\'t have a trophyboard.')

        query = "SELECT message_id FROM messages WHERE channel_id=$1;"
        messages = await self.bot.pool.fetch(query, ctx.config.channel_id)
        for n in messages:
            await self.bot.donationboard.safe_delete(n[0])

        query = """UPDATE boards 
                   SET channel_id = NULL,
                       toggle     = False 
                   WHERE channel_id = $1
                """
        await self.bot.pool.execute(query, ctx.config.channel_id)
        await ctx.send('Trophyboard sucessfully removed.')

    @commands.command()
    async def unclaim(self, ctx, *, player: PlayerConverter):
        """Unlink a clash account from your discord account

        Parameters
        ----------------
        Pass in a clash account - either:
            • Player tag
            • Player name (must be in clan claimed in server)

        Example
        -------------
        • `+unclaim #PLAYER_TAG`
        • `+unclaim my account name`
        """
        if await self.remove_discord.can_run(ctx):
            await ctx.invoke(self.remove_discord, player=player)

    @commands.group(invoke_without_command=True)
    async def edit(self, ctx):
        pass

    @edit.group(name='donationboard')
    @checks.manage_guild()
    @requires_config('donationboard', invalidate=True)
    async def edit_donationboard(self, ctx):
        """Run through an interactive process of editting the guild's donationboard.

        Example
        -----------
        • `+edit donationboard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        # todo: interactive process to run through all subcommands one at time
        #  (note: need to manually convert and pass in args)
        pass

    @edit_donationboard.command(name='format')
    @requires_config('donationboard', invalidate=True)
    async def edit_donationboard_format(self, ctx):
        """Edit the format of the guild's donationboard. The bot will provide 2 options and you must select 1.

        Example
        -----------
        • `+edit donationboard format`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """

        table = CLYTable()
        table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                        [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                        ])
        table.title = '**Option 1 Example**'
        option_1_render = f'**Option 1 Example**\n{table.render_option_1()}'
        table.clear_rows()
        table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                        [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                        ])

        option_2_render = f'**Option 2 Example**\n{table.render_option_2()}'

        embed = discord.Embed(colour=self.bot.colour)
        fmt = f'{option_1_render}\n\n\n{option_2_render}\n\n\n' \
            f'These are the 2 available default options.\n' \
            f'Please hit the reaction of the format you \nwish to display on the donationboard.'
        embed.description = fmt
        msg = await ctx.send(embed=embed)

        query = "UPDATE guilds SET donationboard_render=$1 WHERE guild_id=$2"

        reactions = ['1\N{combining enclosing keycap}', '2\N{combining enclosing keycap}']
        for r in reactions:
            await msg.add_reaction(r)

        def check(r, u):
            return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

        try:
            r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.db.execute(query, 1, ctx.guild.id)
            return await ctx.send('You took too long. Option 1 was chosen.')

        await ctx.db.execute(query, reactions.index(str(r)) + 1, ctx.guild.id)
        await ctx.confirm()

    @edit_donationboard.command(name='icon')
    @requires_config('donationboard', invalidate=True)
    async def edit_donationboard_icon(self, ctx, *, url: str = None):
        """Specify an icon for the guild's donationboard.

        Parameters
        -----------------
            • URL: url of the icon to use. Must only be JPEG, JPG or PNG.

            OR:

            • Attach/upload an image to use.

        Example
        ------------
        • `+edit donationboard icon https://catsareus/thecrazycatbot/123.jpg`
        • `+edit donationboard icon` (with an attached image)

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                                   r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")
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

        Parameters
        -----------------
        Pass in any of the following:

            • Title - the title you wish to use. It must be less than 50 characters.

        Example
        ------------
        • `+edit donationboard title The Donation Tracker DonationBoard`
        • `+edit donationboard title My Awesome Clan Family DonatinoBoard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
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
        """Run through an interactive process of editting the guild's trophyboard.

        Example
        -----------
        • `+edit trophyboard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        # todo: interactive process to run through all subcommands one at time
        #  (note: need to manually convert and pass in args)
        pass

    @edit_trophyboard.command(name='format')
    @requires_config('trophyboard', invalidate=True)
    async def edit_trophyboard_format(self, ctx):
        """Edit the format of the guild's trophyboard. The bot will provide 2 options and you must select 1.

        Example
        -----------
        • `+edit trophyboard format`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        # TODO: make trophy examples
        table = CLYTable()
        table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                        [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                        ])
        table.title = '**Option 1 Example**'
        option_1_render = f'**Option 1 Example**\n{table.render_option_1()}'
        table.clear_rows()
        table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                        [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                        ])

        option_2_render = f'**Option 2 Example**\n{table.render_option_2()}'

        embed = discord.Embed(colour=self.bot.colour)
        fmt = f'{option_1_render}\n\n\n{option_2_render}\n\n\n' \
            f'These are the 2 available default options.\n' \
            f'Please hit the reaction of the format you \nwish to display on the donationboard.'
        embed.description = fmt
        msg = await ctx.send(embed=embed)

        query = "UPDATE guilds SET donationboard_render=$1 WHERE guild_id=$2"

        reactions = ['1\N{combining enclosing keycap}', '2\N{combining enclosing keycap}']
        for r in reactions:
            await msg.add_reaction(r)

        def check(r, u):
            return str(r) in reactions and u.id == ctx.author.id and r.message.id == msg.id

        try:
            r, u = await self.bot.wait_for('reaction_add', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.db.execute(query, 1, ctx.guild.id)
            return await ctx.send('You took too long. Option 1 was chosen.')

        await ctx.db.execute(query, reactions.index(str(r)) + 1, ctx.guild.id)
        await ctx.confirm()

    @edit_trophyboard.command(name='icon')
    @requires_config('trophyboard', invalidate=True)
    async def edit_trophyboard_icon(self, ctx, *, url: str = None):
        """Specify an icon for the guild's donationboard.

        Parameters
        -----------------
        Pass in any of the following:

            • URL: url of the icon to use. Must only be JPEG, JPG or PNG.
            • Attach/upload an image to use.

        Example
        ------------
        • `+edit trophyboard icon https://catsareus/thecrazycatbot/123.jpg`
        • `+edit trophyboard icon` (with an attached image)

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                                   r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")
        if not url or not url_validator.match(url):
            attachments = ctx.message.attachments
            if not attachments:
                return await ctx.send('You must pass in a url or upload an attachment.')
            url = attachments[0].url

        query = "UPDATE boards SET icon_url = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, url, ctx.config.channel_id)
        await ctx.confirm()

    @edit_donationboard.command(name='title')
    @requires_config('trophyboard', invalidate=True)
    async def edit_trophyboard_title(self, ctx, *, title: str):
        """Specify a title for the guild's trophyboard.

        Parameters
        -----------------
        Pass in any of the following:

            • Title - the title you wish to use. This must be less than 50 characters.

        Example
        ------------
        • `+edit trophyboard title The Donation Tracker DonationBoard`
        • `+edit trophyboard title My Awesome Clan Family DonatinoBoard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if len(title) >= 50:
            return await ctx.send('Titles must be less than 50 characters.')

        query = "UPDATE boards SET title = $1 WHERE channel_id = $2"
        await ctx.db.execute(query, title, ctx.config.channel_id)
        await ctx.confirm()

    @commands.command()
    @checks.manage_guild()
    @commands.cooldown(1, 43200, commands.BucketType.guild)
    async def refresh(self, ctx, *, clans: ClanConverter = None):
        """Manually refresh all players in the database with current donations and received.

        Note: it will only update their donations if the
              amount recorded in-game is more than in the database.
              Ie. if they have left and re-joined it won't update them, usually.

        Cool-downs
        ----------------
        You can only call this command once every **12 hours** due to the
        amount of resources it requires to run, and to prevent future abuse.

        Parameters
        --------------------
        **Optional**: this command will default to all clans in guild.

        Pass a clash clan:
            • Clan tag
            • Clan name (must be claimed to server)
            • `all`, `server`, `guild` for all clans in guild

        Required Permissions
        -------------------
        You must have `manage server` permissions to run this command.

        Example
        ---------------
        `+refresh all`
        `+refresh`
        `+refresh #CLAN_TAG`
        """
        if not clans:
            clans = await ctx.get_clans()
        query = """UPDATE players 
                   SET donations = $1, received = $2
                   WHERE player_tag = $3
                   AND donations <= $1
                   AND received <= $2
                """
        for clan in clans:
            for member in clan.members:
                await ctx.db.execute(query, member.donations, member.received, member.tag)
        await ctx.confirm()

    @commands.command()
    @commands.is_owner()
    async def reset_cooldown(self, ctx, guild_id: int = None):
        if guild_id:
            ctx.guild = self.bot.get_guild(guild_id)

        self.refresh.reset_cooldown(ctx)
        await ctx.confirm()

    @commands.command()
    async def accounts(self, ctx, *, clans: ClanConverter = None):
        """Get accounts and claims for all accounts in clans in a server.

        Parameters
        ------------------
        **Optional**: this command will default to all clans in guild.

        Pass in a clash clan:
            • Clan tag
            • Clan name (must be claimed to server)
            • `all`, `server`, `guild` for all clans in guild

        Example
        ------------
        • `+accounts #CLAN_TAG`
        • `+accounts all`
        """
        if not clans:
            clans = await ctx.get_clans()

        players = []
        for n in clans:
            players.extend(x for x in n.members)

        final = []

        season_id = await self.bot.seasonconfig.get_season_id()
        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"
        for n in players:
            fetch = await ctx.db.fetchrow(query, n.tag, season_id)
            if not fetch:
                final.append([n.name, n.tag, ' '])
                continue
            name = str(self.bot.get_user(fetch[0]))

            if len(name) > 20:
                name = name[:20] + '..'
            final.append([n.name, n.tag, name])

        table = formatters.TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)

        messages = math.ceil(len(final) / 20)
        entries = []

        for i in range(int(messages)):

            results = final[i*20:(i+1)*20]

            table = formatters.TabularData()
            table.set_columns(['IGN', 'Tag', "Claimed By"])
            table.add_rows(results)

            entries.append(f'```\n{table.render()}\n```')

        p = paginator.Pages(ctx, entries=entries, per_page=1)
        p.embed.colour = self.bot.colour
        p.embed.title = f"Accounts for {', '.join(f'{c.name}' for c in clans)}"

        await p.paginate()

    @commands.command(name='getclaims', aliases=['gc', 'gclaims', 'get_claims'])
    async def get_claims(self, ctx, *,
                         player: typing.Union[discord.Member, PlayerConverter] = None):
        """Get accounts and claims for a player or discord user.

        Parameters
        ------------------
        **Optional**: this command will default to all accounts for the person calling the command.

        Pass in a clash account, or a discord user:
            • User ID (discord)
            • Mention (@user, discord)
            • user#discrim (discord)
            • Player tag (clash account)
            • Player name (must be in a clan claimed in server)

        Example
        --------------
        • `+get_claims @my_friend`
        • `+get_claims my_friend#1208
        • `+gclaims #PLAYER_TAG`
        • `+gc player name`

        Aliases
        -------------
        • `+get_claims` (primary)
        • `+gclaims`
        • `+gc`
        """
        season_id = await self.bot.seasonconfig.get_season_id()
        if not player:
            player = ctx.author

        if isinstance(player, discord.Member):
            query = "SELECT player_tag FROM players WHERE user_id = $1 AND season_id = $2"
            fetch = await ctx.db.fetch(query, player.id, season_id)
            if not fetch:
                return await ctx.send(f'{str(player)} has no claimed accounts.')
            player = await ctx.coc.get_players(n[0] for n in fetch).flatten()
        else:
            player = [player]

        query = "SELECT user_id FROM players WHERE player_tag = $1 AND season_id = $2"

        final = []
        for n in player:
            fetch = await ctx.db.fetch(query, n.tag, season_id)
            if not fetch:
                final.append([n.name, n.tag, ' '])
                continue

            name = str(self.bot.get_user(fetch[0]))

            if len(name) > 20:
                name = name[:20] + '..'
            final.append([n.name, n.tag, name])

        table = formatters.TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)
        await ctx.send(f'```\n{table.render()}\n```')

    @commands.command(name='autoclaim', aliases=['auto_claim'])
    @checks.manage_guild()
    async def auto_claim(self, ctx, *, clan: ClanConverter = None):
        """Automatically claim all accounts in server, through an interactive process.

        It will go through all players in claimed clans in server, matching them to discord users where possible.
        The interactive process is easy to use, and will try to guide you through as easily as possible

        Parameters
        -----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed clan)
            • `all`, `server`, `guild` will get all clans claimed in the server
            • None passed will get all clans claimed in the server

        Example
        -------------
        • `+auto_claim #CLAN_TAG`
        • `+auto_claim my clan name`
        • `+aclaim all`
        • `+aclaim`

        Aliases
        --------------
        • `+auto_claim` (primary)
        • `+aclaim`

        Required Permissions
        ------------------------------
        • `manage_server` permissions
        """
        season_id = await self.bot.seasonconfig.get_season_id()
        failed_players = []

        if not clan:
            clan = await ctx.get_clans()

        prompt = await ctx.prompt('Would you like to be asked to confirm before the bot claims matching accounts? '
                                  'Else you can un-claim and reclaim if there is an incorrect claim.')
        if prompt is None:
            return

        match_player = self.match_player

        for c in clan:
            for member in c.members:
                query = "SELECT * FROM players WHERE player_tag = $1 AND user_id IS NOT NULL " \
                        "AND season_id = $2;"
                fetch = await ctx.db.fetchrow(query, member.tag, season_id)
                if fetch:
                    continue

                results = await match_player(member, ctx.guild, prompt, ctx)
                if not results:
                    await self.bot.log_info(ctx.channel.id, f'[auto-claim]: No members found for {member.name} ({member.tag})',
                                            colour=discord.Colour.red())
                    failed_players.append(member)
                    continue
                    # no members found in guild with that player name
                if isinstance(results, discord.abc.User):
                    await self.bot.log_info(ctx.channel.id, f'[auto-claim]: {member.name} ({member.tag}) '
                                            f'has been claimed to {str(results)} ({results.id})',
                                            colour=discord.Colour.green())
                    continue

                table = formatters.TabularData()
                table.set_columns(['Option', 'user#disrim', 'UserID'])
                table.add_rows([i + 1, str(n), n.id] for i, n in enumerate(results))
                result = await ctx.prompt(f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                          f'Corresponding members found:\n'
                                          f'```\n{table.render()}\n```', additional_options=len(results))
                if isinstance(result, int):
                    query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3"
                    await self.bot.pool.execute(query, results[result].id, member.tag, season_id)
                if result is None or result is False:
                    await self.bot.log_info(ctx.channel.id, f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                               f'Corresponding members found, none claimed:\n'
                                               f'```\n{table.render()}\n```',
                                            colour=discord.Colour.gold())
                    failed_players.append(member)
                    continue

                await self.bot.log_info(ctx.channel.id, f'[auto-claim]: {member.name} ({member.tag}) '
                                                        f'has been claimed to {str(results[result])} ({results[result].id})',
                                        colour=discord.Colour.green())
        prompt = await ctx.prompt("Would you like to go through a list of players who weren't claimed and "
                                  "claim them now?\nI will walk you through it...")
        if not prompt:
            await ctx.confirm()
            return
        for fail in failed_players:
            m = await ctx.send(f'Player: {fail.name} ({fail.tag}), Clan: {fail.clan.name} ({fail.clan.tag}).'
                               f'\nPlease send either a UserID, user#discrim combo, '
                               f'or mention of the person you wish to claim this account to.')

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            msg = await self.bot.wait_for('message', check=check)
            try:
                member = await commands.MemberConverter().convert(ctx, msg.content)
            except commands.BadArgument:
                await ctx.send('Discord user not found. Moving on to next clan member. Please claim them manually.')
                continue
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3"
            await self.bot.pool.execute(query, member.id, fail.tag, season_id)
            await self.bot.log_info(ctx.channel.id, f'[auto-claim]: {fail.name} ({fail.tag}) '
                                               f'has been claimed to {str(member)} ({member.id})',
                                    colour=discord.Colour.green())
            try:
                await m.delete()
                await msg.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        prompt = await ctx.prompt('Would you like to have the bot to search for players to claim when '
                                  'someone joins the clan/server? I will let you know what I find '
                                  'and you must confirm/deny if you want them claimed.')
        if prompt is True:
            query = "UPDATE guilds SET auto_claim = True WHERE guild_id = $1;"
            await ctx.db.execute(query, ctx.guild.id)

        await ctx.send('All done. Thanks!')
        await ctx.confirm()


def setup(bot):
    bot.add_cog(GuildConfiguration(bot))
