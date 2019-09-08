import asyncio
import asyncpg
import coc
import discord
import logging
import math

from collections import namedtuple
from datetime import datetime
from discord.ext import commands, tasks

from cogs.utils.db_objects import DatabaseGuild, DatabaseMessage, DatabasePlayer
from cogs.utils.formatters import TabularData, clean_name, CLYTable
from cogs.utils import checks, cache


log = logging.getLogger(__name__)

MockPlayer = namedtuple('MockPlayer', 'clan name')
mock = MockPlayer('Unknown', 'Unknown')


class DonationBoard(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot):
        self.bot = bot

        self.clan_updates = []

        self._to_be_deleted = set()

        self.bot.coc.add_events(
            self.on_clan_member_donation,
            self.on_clan_member_received,
            self.on_clan_member_join
                                )
        self.bot.coc._clan_retry_interval = 60
        self.bot.coc.start_updates('clan')

        self._batch_lock = asyncio.Lock(loop=bot.loop)
        self._data_batch = {}
        self._clan_events = set()
        self.bulk_insert_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_insert_loop.start()

        self.update_board_loops.add_exception_type(asyncpg.PostgresConnectionError)
        self.update_board_loops.add_exception_type(coc.ClashOfClansException)
        self.update_board_loops.start()

    def cog_unload(self):
        self.bulk_insert_loop.cancel()
        self.update_board_loops.cancel()
        self.bot.coc.remove_events(
            self.on_clan_member_donation,
            self.on_clan_member_received,
            self.on_clan_member_join
        )

    @tasks.loop(seconds=30.0)
    async def bulk_insert_loop(self):
        async with self._batch_lock:
            await self.bulk_insert()

    @tasks.loop(seconds=60.0)
    async def update_board_loops(self):
        async with self._batch_lock:
            clan_tags = list(self._clan_events)
            self._clan_events.clear()

        query = "SELECT DISTINCT channel_id FROM clans WHERE clan_tag = ANY($1::TEXT[])"
        fetch = await self.bot.pool.fetch(query, clan_tags)

        for n in fetch:
            await self.update_board(n['channel_id'])

    async def bulk_insert(self):
        query = """UPDATE players SET donations = players.donations + x.donations, 
                                      received = players.received + x.received, 
                                      trophies = players.trophies + x.trophies
                        FROM(
                            SELECT x.player_tag, x.donations, x.received, x.attacks, x.trophies
                                FROM jsonb_to_recordset($1::jsonb)
                            AS x(player_tag TEXT, 
                                 donations INTEGER, 
                                 received INTEGER, 
                                 trophies INTEGER)
                            )
                    AS x
                    WHERE players.player_tag = x.player_tag
                    AND players.season_id=$2
                """

        query2 = """UPDATE playersevent SET donations = players.donations + x.donations, 
                                            received = players.received + x.received,
                                            trophies = players.trophies + x.trophies   
                        FROM(
                            SELECT x.player_tag, x.donations, x.received
                                FROM jsonb_to_recordset($1::jsonb)
                            AS x(player_tag TEXT, 
                                 donations INTEGER, 
                                 received INTEGER, 
                                 trophies INTEGER)
                            )
                    AS x
                    WHERE playersevent.player_tag = x.player_tag
                    AND playersevent.live = true                    
                """
        if self._data_batch:  # todo: make sure values() is converted to conventional list by asyncpg
            response = await self.bot.pool.execute(query, self._data_batch.values(),
                                                   await self.bot.seasonconfig.get_season_id())
            log.debug(f'Registered donations/received to the database. Status Code {response}.')

            response = await self.bot.pool.execute(query2, self._data_batch.values())
            log.debug(f'Registered donations/received to the events database. Status Code {response}.')
            self._data_batch.clear()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return

        query = """"DELETE FROM messages WHERE channel_id = $1;
                    UPDATE channels
                        SET channel_id = NULL,
                            toggle     = False
                        WHERE channel_id = $1;
                """
        await self.bot.pool.executemany(query, channel.id)
        self.bot.utils.get_board_config.invalidate(self.bot.utils, channel.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        config = await self.bot.utils.get_board_config(channel_id=payload.channel_id)

        if not config:
            return
        if config.channel_id != payload.channel_id:
            return
        if payload.message_id in self._to_be_deleted:
            self._to_be_deleted.discard(payload.message_id)
            return

        self.bot.utils.get_message.invalidate(self.bot.utils, payload.message_id)

        message = await self.safe_delete(message_id=payload.message_id, delete_message=False)
        if message:
            await self.new_board_message(payload.channel_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        config = await self.bot.utils.get_board_config(payload.channel_id)

        if not config:
            return
        if config.channel_id != payload.channel_id:
            return

        for n in payload.message_ids:
            if n in self._to_be_deleted:
                self._to_be_deleted.discard(n)
                continue

            self.bot.utils.get_message.invalidate(self, n)

            message = await self.safe_delete(message_id=n, delete_message=False)
            if message:
                await self.new_board_message(payload.channel_id)

    async def on_clan_member_donation(self, old_donations, new_donations, player, clan):
        log.debug(f'Received on_clan_member_donation event for player {player} of clan {clan}')
        if old_donations > new_donations:
            donations = new_donations
        else:
            donations = new_donations - old_donations

        async with self._batch_lock:
            try:
                self._data_batch[player.tag]['donations'] = donations
            except KeyError:
                self._data_batch[player.tag] = {
                    'player_tag': player.tag,
                    'donations': donations,
                    'received': 0,
                    'trophies': 0
                }
            self._clan_events.add(clan.tag)

    async def on_clan_member_received(self, old_received, new_received, player, clan):
        log.debug(f'Received on_clan_member_received event for player {player} of clan {clan}')
        if old_received > new_received:
            received = new_received
        else:
            received = new_received - old_received

        async with self._batch_lock:
            try:
                self._data_batch[player.tag]['received'] = received
            except KeyError:
                self._data_batch[player.tag] = {
                    'player_tag': player.tag,
                    'donations': 0,
                    'received': received,
                    'trophies': 0
                }
            self._clan_events.add(clan.tag)

    async def on_clan_member_trophy_change(self, old_trophies, new_trophies, player, clan):
        log.debug(f'Received on_clan_member_trophy_change event for player {player} of clan {clan}')
        trophies = new_trophies - old_trophies

        async with self._batch_lock:
            try:
                self._data_batch[player.tag]['trophies'] = trophies
            except KeyError:
                self._data_batch[player.tag] = {
                    'player_tag': player.tag,
                    'donations': 0,
                    'received': 0,
                    'trophies': trophies
                }
            self._clan_events.add(clan.tag)

    async def on_clan_member_join(self, member, clan):
        query = """INSERT INTO players (player_tag, donations, received, season_id) 
                    VALUES ($1,$2,$3, $4) 
                    ON CONFLICT (player_tag, season_id) 
                    DO NOTHING
                """
        # todo: test query2
        query2 = """INSERT INTO playerevents (player_tag, donations, received, live, event_id) 
                        SELECT $1, $2, $3, $4, true, donationevents.id
                        FROM donationevents
                            INNER JOIN clans ON clans.guild_id = donationevents.guild_id
                        WHERE clans.clan_tag = $5
                    ON CONFLICT (player_tag, event_id) 
                    DO NOTHING
                """

        response = await self.bot.pool.execute(query, member.tag, member.donations, member.received,
                                               await self.bot.seasonconfig.get_season_id())
        log.debug(f'New member {member} joined clan {clan}. Performed a query to insert them into players. '
                  f'Status Code: {response}')

        response = await self.bot.pool.execute(query2, member.tag, member.donations,
                                               member.received, clan.tag)
        log.debug(f'New member {member} joined clan {clan}. '
                  f'Performed a query to insert them into eventplayers. Status Code: {response}')

    async def new_board_message(self, channel_id):
        config = await self.bot.utils.get_board_config(channel_id=channel_id)

        new_msg = await config.channel.send('Placeholder')
        query = "INSERT INTO messages (guild_id, message_id, channel_id) VALUES ($1, $2, $3)"
        await self.bot.pool.execute(query, new_msg.guild.id, new_msg.id, new_msg.channel.id)
        return new_msg

    async def safe_delete(self, message_id, delete_message=True):
        query = "DELETE FROM messages WHERE message_id = $1 RETURNING id, guild_id, message_id, channel_id"
        fetch = await self.bot.pool.fetchrow(query, message_id)
        if not fetch:
            return None

        message = DatabaseMessage(bot=self.bot, record=fetch)
        if not delete_message:
            return message

        self._to_be_deleted.add(message_id)
        m = await message.get_message()
        if not m:
            return

        await m.delete()

    async def get_board_messages(self, channel_id, number_of_msg=None):
        config = await self.bot.utils.get_board_config(channel_id=channel_id)
        fetch = await config.messages()

        messages = [await n.get_message() for n in fetch]
        messages = [n for n in messages if n]
        size_of = len(messages)

        if not number_of_msg or size_of == number_of_msg:
            return messages

        if size_of > number_of_msg:
            for n in messages[number_of_msg:]:
                await self.safe_delete(n.id)
            return messages[:number_of_msg]

        for _ in range(number_of_msg - size_of):
            messages.append(await self.new_board_message(channel_id))
        return messages

    async def get_top_players(self, players, board_type, in_event):
        if board_type == 'donation':
            column_1 = 'donations'
            column_2 = 'received'
        elif board_type == 'trophy':
            column_1 = 'trophies'
            column_2 = None
        else:
            return

        if in_event:
            query = f"""SELECT player_tag, {column_1}, {column_2} 
                        FROM eventplayers 
                        WHERE player_tag=ANY($1::TEXT[])
                        AND live=true
                        ORDER BY {column_1} DESC
                        LIMIT 100;
                    """
            fetch = await self.bot.pool.fetch(query, [n.tag for n in players])

        else:
            query = f"""SELECT player_tag, {column_1}, {column_2}
                        FROM players 
                        WHERE player_tag=ANY($1::TEXT[])
                        AND season_id=$2
                        ORDER BY {column_1} DESC
                        LIMIT 100;
                    """
            fetch = await self.bot.pool.fetch(query, [n.tag for n in players],
                                              await self.bot.seasonconfig.get_season_id())
        return fetch

    async def update_board(self, channel_id):
        config = await self.bot.utils.get_board_config(channel_id=channel_id)

        if not config.toggle:
            return
        if not config.channel:
            return

        query = "SELECT DISTINCT clan_tag FROM clans WHERE guild_id=$1"
        fetch = await self.bot.pool.fetch(query, config.guild_id)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()

        players = []
        for n in clans:
            players.extend(p for p in n.itermembers)

        top_players = await self.get_top_players(players, config.board_type, config.in_event)
        players = {n.tag: n for n in players if n.tag in set(x['player_tag'] for x in top_players)}

        message_count = math.ceil(len(fetch) / 20)

        messages = await self.get_board_messages(channel_id, number_of_msg=message_count)
        if not messages:
            return

        for i, v in enumerate(messages):
            player_data = fetch[i*20:(i+1)*20]
            table = CLYTable()

            for x, y in enumerate(player_data):
                index = i*20 + x
                if config.render == 2:
                    table.add_row([index,
                                   y[0],
                                   players.get(y['player_tag'], mock).name])
                else:
                    table.add_row([index,
                                   y[0],
                                   y[1],
                                   players.get(y['player_tag'], mock).name])

            fmt = table.render_option_2() if \
                config.render == 2 else table.render_option_1()

            e = discord.Embed(colour=self.bot.colour,
                              description=fmt,
                              timestamp=datetime.utcnow()
                              )
            e.set_author(name=f'Event in Progress!' if config.in_event
                              else config.title,
                         icon_url=config.icon_url or 'https://cdn.discordapp.com/'
                                                     'emojis/592028799768592405.png?v=1')
            e.set_footer(text='Last Updated')
            await v.edit(embed=e, content=None)

    # todo: organise or move these out of here, use decorator to add config to ctx attr, create same for trophyboards.

    @commands.group(invoke_without_command=True)
    @checks.manage_guild()
    async def donationboard(self, ctx):
        """Manage the donationboard for the guild.
        """
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @donationboard.command(name='create')
    async def donationboard_create(self, ctx, *, name='donationboard'):
        """Creates a donationboard channel for donation updates.

        Parameters
        ----------------
        Pass in any of the following:

            • A name for the channel. Defaults to `donationboard`

        Example
        -----------
        • `+donationboard create`
        • `+donationboard create my cool donationboard name`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions

        Bot Required Permissions
        --------------------------------
        • `manage_channels` permissions
        """
        guild_id = ctx.guild.id
        self.get_guild_config.invalidate(self, guild_id)
        guild_config = await self.bot.get_guild_config(guild_id)

        if guild_config.donationboard is not None:
            return await ctx.send(
                f'This server already has a donationboard ({guild_config.donationboard.mention})')

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

        query = "INSERT INTO messages (message_id, guild_id, channel_id) VALUES ($1, $2, $3)"
        await ctx.db.execute(query, msg.id, ctx.guild.id, channel.id)
        query = "UPDATE guilds SET updates_channel_id=$1, updates_toggle=True WHERE guild_id=$2"
        await ctx.db.execute(query, channel.id, ctx.guild.id)
        await ctx.send(f'Donationboard channel created: {channel.mention}')

        await ctx.invoke(self.donationboard_edit)

    @donationboard.command(name='delete', aliases=['remove', 'destroy'])
    async def donationboard_delete(self, ctx):
        """Deletes the guild donationboard.

        Example
        -----------
        • `+donationboard delete`
        • `+donationboard remove`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        guild_id = ctx.guild.id
        guild_config = await self.get_guild_config(guild_id)

        if guild_config.donationboard is None:
            return await ctx.send(
                f'This server doesn\'t have a donationboard.')

        query = "SELECT message_id FROM messages WHERE channel_id=$1;"
        messages = await self.bot.pool.fetch(query, guild_config.donationboard.id)
        for n in messages:
            await self.safe_delete(n[0])

        query = """UPDATE guilds 
                    SET updates_channel_id = NULL,
                        updates_toggle = False 
                    WHERE guild_id = $1
                """
        await self.bot.pool.execute(query, guild_id)
        await ctx.send('Donationboard sucessfully removed.')
        self.get_guild_config.invalidate(self, guild_id)

    @donationboard.command(name='edit')
    async def donationboard_edit(self, ctx):
        """Edit the format of the guild's donationboard.

        Example
        -----------
        • `+donationboard edit`

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
        await ctx.send('All done. Thanks!')
        self.get_guild_config.invalidate(self, ctx.guild.id)

    @donationboard.command(name='icon')
    async def donationboard_icon(self, ctx, *, url: str = None):
        """Specify an icon for the guild's donationboard.

        Parameters
        -----------------
        Pass in any of the following:

            • URL: url of the icon to use. Must only be JPEG, JPG or PNG.
            • Attach/upload an image to use.

        Example
        ------------
        • `+donationboard icon https://catsareus/thecrazycatbot/123.jpg`
        • `+donationboard icon` (with an attached image)

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not url or not url.startswith('https://'):
            attachments = ctx.message.attachments
            if not attachments:
                return await ctx.send('You must pass in a url or upload an attachment.')
            url = attachments[0].url

        query = "UPDATE guilds SET icon_url=$1 WHERE guild_id=$2"
        await ctx.db.execute(query, url, ctx.guild.id)
        await ctx.confirm()
        self.get_guild_config.invalidate(self, ctx.guild.id)

    @donationboard.command(name='title')
    async def donationboard_title(self, ctx, *, title: str = None):
        """Specify a title for the guild's donationboard.

        Parameters
        -----------------
        Pass in any of the following:

            • Title - the title you wish to use.

        Example
        ------------
        • `+donationboard title The Donation Tracker DonationBoard`
        • `+donationboard title My Awesome Clan Family DonatinoBoard`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        query = "UPDATE guilds SET donationboard_title=$1 WHERE guild_id=$2"
        await ctx.db.execute(query, title, ctx.guild.id)
        await ctx.confirm()
        self.get_guild_config.invalidate(self, ctx.guild.id)

    @donationboard.command(name='info')
    async def donationboard_info(self, ctx):
        """Gives you info about guild's donationboard.
        """
        guild_config = await self.bot.get_guild_config(ctx.guild.id)

        table = CLYTable()
        if guild_config.donationboard_render == 2:
            table.add_rows([[0, 6532, 'Member (Awesome Clan)'], [1, 4453, 'Nearly #1 (Bad Clan)'],
                            [2, 5589, 'Another Member (Awesome Clan)'], [3, 0, 'Winner (Bad Clan)']
                            ])
            table.title = guild_config.donationboard_title or 'DonationBoard'
            render = table.render_option_2()
        else:
            table.add_rows([[0, 9913, 12354, 'Member Name'], [1, 524, 123, 'Another Member'],
                            [2, 321, 444, 'Yet Another'], [3, 0, 2, 'The Worst Donator']
                            ])
            table.title = guild_config.donationboard_title or 'DonationBoard'
            render = table.render_option_1()

        fmt = f'**DonationBoard Example Format:**\n\n{render}\n**Icon:** ' \
            f'Please see the icon displayed above.\n'

        channel = guild_config.donationboard
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
                     icon_url=guild_config.icon_url or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(DonationBoard(bot))
