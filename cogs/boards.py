import asyncio
import discord
import logging

from collections import namedtuple
from discord.ext import commands

from cogs.add import BOARD_PLACEHOLDER
from cogs.utils.db_objects import DatabaseMessage, BoardConfig
from syncboards import SyncBoards


log = logging.getLogger(__name__)

MockPlayer = namedtuple('MockPlayer', 'clan name')
mock = MockPlayer('Unknown', 'Unknown')

REFRESH_EMOJI = discord.PartialEmoji(name="refresh", id=694395354841350254, animated=False)
LEFT_EMOJI = discord.PartialEmoji(name="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)    # [:arrow_left:]
RIGHT_EMOJI = discord.PartialEmoji(name="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)   # [:arrow_right:]
PERCENTAGE_EMOJI = discord.PartialEmoji(name="percent", id=694463772135260169, animated=False)
GAIN_EMOJI = discord.PartialEmoji(name="gain", id=696280508933472256, animated=False)
LAST_ONLINE_EMOJI = discord.PartialEmoji(name="lastonline", id=696292732599271434, animated=False)
HISTORICAL_EMOJI = discord.PartialEmoji(name="historical", id=694812540290465832, animated=False)

GLOBAL_BOARDS_CHANNEL_ID = 663683345108172830


class DonationBoard(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot):
        self.bot = bot

        self.clan_updates = []

        self._to_be_deleted = set()

        self._batch_lock = asyncio.Lock(loop=bot.loop)
        self._data_batch = {}

        self.tags_to_update = set()
        self.last_updated_tags = {}
        self.last_updated_channels = {}
        self._board_channels = []
        self.season_meta = {}

        self.board_updater = None

        bot.loop.create_task(self.on_init())

    async def on_init(self):
        await self.bot.wait_until_ready()
        self.board_updater = SyncBoards(self.bot, start_loop=False, session=self.bot.session)

    @commands.command()
    async def rb(self, ctx, *, fonts: str = None):
        fetch = await ctx.db.fetchrow("SELECT * FROM boards OFFSET random() LIMIT 1")
        config = BoardConfig(bot=self.bot, record=fetch)
        await self.update_board(None, config, fonts=fonts, send_to_channel=ctx.channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return

        query = "DELETE FROM messages WHERE channel_id = $1;"
        query2 = "DELETE FROM boards WHERE channel_id = $1"
        query3 = "DELETE FROM logs WHERE channel_id = $1"
        query4 = "DELETE FROM clans WHERE channel_id = $1"

        for q in (query, query2, query3, query4):
            await self.bot.pool.execute(q, channel.id)

        # self.bot.utils.board_config.invalidate(self.bot.utils, channel.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        config = await self.bot.utils.board_config(payload.channel_id)

        if not config:
            return
        if config.channel_id != payload.channel_id:
            return
        if payload.message_id in self._to_be_deleted:
            self._to_be_deleted.discard(payload.message_id)
            return

        self.bot.utils._messages.pop(payload.message_id, None)

        message = await self.safe_delete(message_id=payload.message_id, delete_message=False)
        if message:
            await self.new_board_message(self.bot.get_channel(payload.channel_id), config.type)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        config = await self.bot.utils.board_config(payload.channel_id)

        if not config:
            return
        if config.channel_id != payload.channel_id:
            return

        for n in payload.message_ids:
            if n in self._to_be_deleted:
                self._to_be_deleted.discard(n)
                continue

            self.bot.utils._messages.pop(n, None)

            message = await self.safe_delete(message_id=n, delete_message=False)
            if message:
                await self.new_board_message(self.bot.get_channel(payload.channel_id), config.type)

    async def new_board_message(self, channel, board_type):
        if not channel:
            return

        try:
            new_msg = await channel.send(BOARD_PLACEHOLDER.format(board=board_type))
        except (discord.NotFound, discord.Forbidden):
            return

        query = "INSERT INTO messages (guild_id, message_id, channel_id) VALUES ($1, $2, $3)"
        await self.bot.pool.execute(query, new_msg.guild.id, new_msg.id, new_msg.channel.id)

        event_config = await self.bot.utils.event_config(channel.id)
        if event_config:
            await self.bot.background.remove_event_msg(event_config.id, channel, board_type)
            await self.bot.background.new_event_message(event_config, channel.guild.id, channel.id, board_type)

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

    @commands.command(hidden=True)
    @commands.is_owner()
    async def forceboard(self, ctx, message_id: int = None):
        await self.update_board(message_id=message_id)
        await ctx.confirm()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.reaction_action(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.reaction_action(payload)

    async def reaction_action(self, payload):
        await self.bot.wait_until_ready()
        if payload.user_id == self.bot.user.id:
            return
        if payload.emoji not in (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI, PERCENTAGE_EMOJI, GAIN_EMOJI, LAST_ONLINE_EMOJI, HISTORICAL_EMOJI):
            return

        message = await self.bot.utils.get_message(self.bot.get_channel(payload.channel_id), payload.message_id)
        if not message:
            return
        if not message.author.id == self.bot.user.id:
            return

        query = "SELECT * FROM boards WHERE message_id = $1"
        fetch = await self.bot.pool.fetchrow(query, payload.message_id)
        if not fetch:
            return

        if payload.emoji == RIGHT_EMOJI:
            fetch = await self.bot.pool.fetchrow('UPDATE boards SET page = page + 1, toggle=True WHERE message_id = $1 RETURNING *', payload.message_id)

        elif payload.emoji == LEFT_EMOJI:
            fetch = await self.bot.pool.fetchrow('UPDATE boards SET page = page - 1, toggle=True WHERE message_id = $1 AND page > 1 RETURNING *', payload.message_id)

        elif payload.emoji == REFRESH_EMOJI:
            lookup = {'donation': 'donations', 'legend': 'finishing', 'trophy': 'trophies'}
            original_sort = lookup[fetch['type']]
            query = "UPDATE boards SET sort_by = $1, page=1, season_id=0, toggle=True WHERE message_id = $2 RETURNING *"
            fetch = await self.bot.pool.fetchrow(query, original_sort, payload.message_id)

        elif payload.emoji == PERCENTAGE_EMOJI:
            query = "UPDATE boards SET sort_by = 'ratio', toggle=True WHERE message_id = $1 RETURNING *"
            fetch = await self.bot.pool.fetchrow(query, payload.message_id)

        elif payload.emoji == GAIN_EMOJI:
            query = "UPDATE boards SET sort_by = 'gain', toggle=True WHERE message_id = $1 RETURNING *"
            fetch = await self.bot.pool.fetchrow(query, payload.message_id)

        elif payload.emoji == LAST_ONLINE_EMOJI:
            query = "UPDATE boards SET sort_by = 'last_online ASC, player_name', toggle=True WHERE message_id = $1 RETURNING *"
            fetch = await self.bot.pool.fetchrow(query, payload.message_id)

        elif payload.emoji == HISTORICAL_EMOJI:
            fetch = await self.bot.pool.fetchrow('UPDATE boards SET season_id = season_id - 1, toggle=True WHERE message_id = $1 RETURNING *', payload.message_id)

        if not fetch:
            return

        config = BoardConfig(bot=self.bot, record=fetch)
        await self.update_board(None, config=config)

    async def update_board(self, message_id, config=None, **kwargs):
        if config is None:
            config = await self.bot.utils.board_config(message_id)

        if self.board_updater.webhooks is None:
            await self.board_updater.on_init()

        await self.board_updater.update_board(config, update_global=True, **kwargs)


def setup(bot):
    bot.add_cog(DonationBoard(bot))
