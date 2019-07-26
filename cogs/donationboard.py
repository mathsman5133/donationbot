import asyncio
import asyncpg
import discord
import logging
import math

from collections import OrderedDict
from datetime import datetime
from discord.ext import commands, tasks

from cogs.utils.db_objects import DatabaseGuild, DatabaseMessage, DatabasePlayer, DatabaseClan, DatabaseEvent
from cogs.utils.formatters import TabularData, clean_name, CLYTable
from cogs.utils import checks


log = logging.getLogger(__name__)


class MockPlayer:
    def __init__(self):
        MockPlayer.name = 'Unknown'
        MockPlayer.clan = 'Unknown'


class DonationBoard(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot):
        self.bot = bot

        self.clan_updates = []
        self.player_updates = []

        self._clan_names = OrderedDict()
        self._message_cache = OrderedDict()
        self._guild_config_cache = OrderedDict()

        self.clean_message_cache.start()

        self._to_be_deleted = set()

        self._join_prompts = {}

        self.bot.coc.add_events(
            self.on_clan_member_donation,
            self.on_clan_member_received,
            self.on_clan_member_join
                                )
        self.bot.coc._clan_retry_interval = 60
        self.bot.coc.start_updates('clan')

        self._batch_lock = asyncio.Lock(loop=bot.loop)
        self._data_batch = []
        self._clan_events = set()
        self.bulk_insert_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_insert_loop.start()
        self.update_donationboard_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.update_donationboard_loop.start()

    def cog_unload(self):
        self.clean_message_cache.cancel()
        self.bulk_insert_loop.cancel()
        self.update_donationboard_loop.cancel()
        try:
            self.bot.coc.extra_events['on_clan_member_donation'].remove(
                self.on_clan_member_donation)
            self.bot.coc.extra_events['on_clan_member_received'].remove(
                self.on_clan_member_received)
            self.bot.coc.extra_events['on_clan_member_join'].remove(
                self.on_clan_member_join)
        except ValueError:
            pass

    @tasks.loop(hours=1.0)
    async def clean_message_cache(self):
        self._message_cache.clear()

    @tasks.loop(seconds=30.0)
    async def bulk_insert_loop(self):
        async with self._batch_lock:
            await self.bulk_insert()

    @tasks.loop(seconds=60)
    async def update_donationboard_loop(self):
        async with self._batch_lock:
            clan_tags = list(self._clan_events)
            self._clan_events.clear()

        query = "SELECT DISTINCT guild_id FROM clans WHERE clan_tag = ANY($1::TEXT[])"
        fetch = await self.bot.pool.fetch(query, clan_tags)

        for n in fetch:
            await self.update_donationboard(n['guild_id'])

    async def bulk_insert(self):
        query = """UPDATE players SET donations = players.donations + x.donations, 
                                      received = players.received + x.received 
                        FROM(
                            SELECT x.player_tag, x.donations, x.received
                                FROM jsonb_to_recordset($1::jsonb)
                            AS x(player_tag TEXT, donations INTEGER, received INTEGER)
                            )
                    AS x
                    WHERE players.player_tag = x.player_tag
                """

        if self._data_batch:
            await self.bot.pool.execute(query, self._data_batch)
            total = len(self._data_batch)
            if total > 1:
                log.info('Registered %s donations/received to the database.', total)
            self._data_batch.clear()

    async def get_guild_config(self, guild_id):
        cache = self._guild_config_cache.get(guild_id)
        if cache:
            return cache

        query = "SELECT * FROM guilds WHERE guild_id = $1"
        fetch = await self.bot.pool.fetchrow(query, guild_id)

        config = DatabaseGuild(guild_id=guild_id, bot=self.bot, record=fetch)
        self._guild_config_cache[guild_id] = config
        return config

    async def get_clan_name(self, guild_id, tag):
        try:
            name = self._clan_names[guild_id][tag]
            if name:
                return name
        except KeyError:
            pass

        query = "SELECT clan_name FROM clans WHERE clan_tag=$1 AND guild_id=$2"
        fetch = await self.bot.pool.fetchrow(query, tag, guild_id)
        if not fetch:
            return 'Unknown'

        try:
            self._clan_names[guild_id][tag] = fetch[0]
        except KeyError:
            self._clan_names[guild_id] = {}
            self._clan_names[guild_id][tag] = fetch[0]
        return fetch[0]

    async def get_message(self, channel, message_id):
        try:
            return self._message_cache[message_id]
        except KeyError:
            try:
                o = discord.Object(id=message_id + 1)
                # don't wanna use get_message due to poor rate limit (1/1s) vs (50/1s)
                msg = await channel.history(limit=1, before=o).next()

                if msg.id != message_id:
                    return None

                self._message_cache[message_id] = msg
                return msg
            except Exception:
                return None

    async def new_donationboard_message(self, guild_id):
        guild_config = await self.get_guild_config(guild_id)

        new_msg = await guild_config.donationboard.send('Placeholder')
        query = "INSERT INTO messages (guild_id, message_id, channel_id) VALUES ($1, $2, $3)"
        await self.bot.pool.execute(query, new_msg.guild.id, new_msg.id, new_msg.channel.id)
        return new_msg

    async def safe_delete(self, message_id, delete_message=True):
        query = "DELETE FROM messages WHERE message_id = $1 RETURNING *"
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

    async def get_message_database(self, message_id):
        query = "SELECT * FROM messages WHERE message_id = $1"
        fetch = await self.bot.pool.fetchrow(query, message_id)
        if not fetch:
            return
        return DatabaseMessage(bot=self.bot, record=fetch)

    async def update_clan_tags(self):
        query = "SELECT DISTINCT clan_tag FROM clans"
        fetch = await self.bot.pool.fetch(query)
        self.bot.coc._clan_updates = [n[0] for n in fetch]

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return

        guild_config = await self.get_guild_config(channel.guild.id)
        if guild_config.updates_channel_id != channel.id:
            return

        query = "DELETE FROM messages WHERE channel_id = $1;"
        await self.bot.pool.execute(query, channel.id)

        query = "UPDATE guilds SET updates_channel_id = NULL, " \
                "updates_message_id = NULL, updates_toggle = False WHERE " \
                "guild_id = $1"
        await self.bot.pool.execute(query, channel.guild.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)

        if guild_config.updates_channel_id != payload.channel_id:
            return
        if payload.message_id in self._to_be_deleted:
            self._to_be_deleted.discard(payload.message_id)
            return

        self._message_cache.pop(payload.message_id, None)

        message = await self.safe_delete(message_id=payload.message_id, delete_message=False)
        if message:
            await self.new_donationboard_message(payload.guild_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild_config = await self.get_guild_config(payload.guild_id)
        if guild_config.updates_channel_id != payload.channel_id:
            return

        for n in payload.message_ids:
            if n in self._to_be_deleted:
                self._to_be_deleted.discard(n)
                continue

            self._message_cache.pop(n, None)

            message = await self.safe_delete(message_id=n, delete_message=False)
            if message:
                await self.new_donationboard_message(payload.guild_id)

    async def on_clan_member_donation(self, old_donations, new_donations, player, clan):
        if old_donations > new_donations:
            donations = new_donations
        else:
            donations = new_donations - old_donations

        async with self._batch_lock:
            self._data_batch.append({
                'player_tag': player.tag,
                'donations': donations,
                'received': 0
            })
            self._clan_events.add(clan.tag)

    async def on_clan_member_received(self, old_received, new_received, player, clan):
        if old_received > new_received:
            received = new_received
        else:
            received = new_received - old_received

        async with self._batch_lock:
            self._data_batch.append({
                'player_tag': player.tag,
                'donations': 0,
                'received': received
            })
            self._clan_events.add(clan.tag)

    async def on_clan_member_join(self, member, clan):
        query = "INSERT INTO players (player_tag, donations, received) VALUES ($1,$2,$3) " \
                "ON CONFLICT (player_tag) DO NOTHING"
        await self.bot.pool.execute(query, member.tag, member.donations, member.received)

    async def get_updates_messages(self, guild_id, number_of_msg=None):
        guild_config = await self.get_guild_config(guild_id)
        fetch = await guild_config.updates_messages()

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
            messages.append(await self.new_donationboard_message(guild_id))
        return messages

    async def update_donationboard(self, guild_id):
        guild_config = await self.get_guild_config(guild_id)
        if not guild_config.updates_toggle:
            return
        if not guild_config.donationboard:
            return

        query = "SELECT DISTINCT clan_tag FROM clans WHERE guild_id=$1"
        fetch = await self.bot.pool.fetch(query, guild_id)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()

        players = []
        for n in clans:
            players.extend(p for p in n.itermembers)

        query = """SELECT *
                        FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    ORDER BY donations DESC
                """
        fetch = await self.bot.pool.fetch(query, [n.tag for n in players])
        db_players = [DatabasePlayer(bot=self.bot, record=n) for n in fetch][:100]
        players = {n.tag: n for n in players if n.tag in set(x.player_tag for x in db_players)}

        message_count = math.ceil(len(db_players) / 20)

        messages = await self.get_updates_messages(guild_id, number_of_msg=message_count)
        if not messages:
            return

        for i, v in enumerate(messages):
            player_data = db_players[i*20:(i+1)*20]
            table = CLYTable()

            for x, y in enumerate(player_data):
                index = i*20 + x
                if guild_config.donationboard_render == 2:
                    table.add_row([index,
                                   y.donations,
                                   players.get(y.player_tag, MockPlayer()).name])
                else:
                    table.add_row([index,
                                   y.donations,
                                   y.received,
                                   players.get(y.player_tag, MockPlayer()).name
                                   ]
                                  )

            fmt = table.render_option_2() if \
                guild_config.donationboard_render == 2 else table.render_option_1()
            e = discord.Embed(colour=self.bot.colour,
                              description=fmt,
                              timestamp=datetime.utcnow())
            e.set_author(name=guild_config.donationboard_title or 'DonationBoard',
                         icon_url=guild_config.icon_url or 'https://cdn.discordapp.com/'
                                                           'emojis/592028799768592405.png?v=1')
            e.set_footer(text='Last Updated')
            await v.edit(embed=e, content=None)

    @commands.group(invoke_without_command=True)
    async def donationboard(self, ctx):
        """Manage the donationboard for the guild.
        """
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)
        if not ctx.channel.permissions_for(ctx.author).manage_channels \
                or not await self.bot.is_owner(ctx.author):
            return

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
        self.bot.invalidate_guild_cache(guild_id)
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
        self.bot.invalidate_guild_cache(ctx.guild.id)

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
        self.bot.invalidate_guild_cache(ctx.guild.id)

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
        self.bot.invalidate_guild_cache(ctx.guild.id)

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
