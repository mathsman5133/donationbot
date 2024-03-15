import asyncio
import typing

import discord
import logging

from collections import namedtuple

from discord import Interaction
from discord.ext import commands

from cogs.add import BOARD_PLACEHOLDER
from cogs.utils.db_objects import DatabaseMessage, BoardConfig
from syncboards import SyncBoards, default_sort_by


log = logging.getLogger(__name__)

MockPlayer = namedtuple('MockPlayer', 'clan name')
mock = MockPlayer('Unknown', 'Unknown')

REFRESH_EMOJI = discord.PartialEmoji(name="refresh", id=694395354841350254, animated=False)
GEAR_EMOJI = discord.PartialEmoji(name="dtgear", id=1218024515578105907, animated=False)
LEFT_EMOJI = discord.PartialEmoji(name="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)    # [:arrow_left:]
RIGHT_EMOJI = discord.PartialEmoji(name="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)   # [:arrow_right:]
PERCENTAGE_EMOJI = discord.PartialEmoji(name="percent", id=694463772135260169, animated=False)
GAIN_EMOJI = discord.PartialEmoji(name="gain", id=696280508933472256, animated=False)
LAST_ONLINE_EMOJI = discord.PartialEmoji(name="lastonline", id=696292732599271434, animated=False)
HISTORICAL_EMOJI = discord.PartialEmoji(name="historical", id=694812540290465832, animated=False)

GLOBAL_BOARDS_CHANNEL_ID = 663683345108172830


class CustomButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        self.bot = kwargs.pop("bot")
        self.update_board = kwargs.pop("update_board")

        super().__init__(*args, **kwargs)

    async def callback(self, interaction: discord.Interaction):
        # await self.bot.wait_until_ready()
        message_id = interaction.message.id

        query = "SELECT * FROM boards WHERE message_id = $1"
        fetch = await self.bot.pool.fetchrow(query, message_id)
        if not fetch:
            return

        if self.label == "Previous":
            fetch = await self.bot.pool.fetchrow('UPDATE boards SET page = page + 1, toggle=True WHERE message_id = $1 RETURNING *', message_id)

        elif self.label == "Next Page":
            fetch = await self.bot.pool.fetchrow('UPDATE boards SET page = page - 1, toggle=True WHERE message_id = $1 AND page > 1 RETURNING *', message_id)

        elif self.label == "Refresh":
            query = "UPDATE boards SET page=1, season_id=0, toggle=True WHERE message_id = $1 RETURNING *"
            fetch = await self.bot.pool.fetchrow(query, message_id)

        elif self.label == "Edit Board":
            config = BoardConfig(bot=self.bot, record=fetch)
            await interaction.response.send_modal(EditBoardModal(self.bot, config))
            return

        if not fetch:
            return

        await interaction.response.defer()

        config = BoardConfig(bot=self.bot, record=fetch)
        await self.update_board(None, config=config)

        # msg = await interaction.channel.fetch_message(message_id)
        # await msg.edit(view=PersistentBoardView(
        #     self.bot, self.update_board, interaction.guild_id, interaction.channel_id, config.type
        # ))


class ValidBoardSorting:
    options = {
        "donation": {
            "donations": "donations",
            "received": "received",
            "ratio": "ratio",
            "last on": "last_online ASC, player_name",
            "default": "donations",
        },
        "trophy": {
            "trophies": "trophies",
            "gain": "gain",
            "last on": "last_online ASC, player_name",
            "default": "donations",
        },
        "legend": {
            "initial": "starting",
            "gain": "gain",
            "loss": "loss",
            "final": "finishing",
            "default": "donations",
        }
    }

    @staticmethod
    def parse_item(board_type, value):
        value = value.strip()
        try:
            return ValidBoardSorting.options[board_type][value]
        except KeyError:
            return ValidBoardSorting.options[board_type]["default"]

    @staticmethod
    def get_human_readable(board_type):
        if board_type == "donation":
            return "donations, received or last on"
        if board_type == "trophy":
            return "trophies, gain or last on"
        if board_type == "legend":
            return "initial, gain, loss or final"

    @staticmethod
    def reverseparse(board_type, value):
        opts = ValidBoardSorting.options[board_type]
        reverse = {v: k for v, k in opts.items()}
        return reverse.get(value, opts["default"])


class EditBoardModal(discord.ui.Modal, title="Edit Board"):
    def __init__(self, bot, config: BoardConfig):
        self.bot = bot
        self.config = config

        self.title_input = discord.ui.TextInput(
            label="Board Title",
            placeholder="The title to show at the top of your board image.",
            default=self.config.title,
            required=False
        )
        self.perpage_input = discord.ui.TextInput(
            label="Players per page",
            placeholder="Enter a number (e.g. 20), or leave blank for default.",
            default=self.config.per_page,
            required=False
        )
        self.sortby_input = discord.ui.TextInput(
            label=f"Sort by ({ValidBoardSorting.get_human_readable(self.config.type)}), or blank for default.",
            placeholder=ValidBoardSorting.reverseparse(self.config.type, self.config.sort_by),
            required=False
        )
        self.iconurl_input = discord.ui.TextInput(
            label="Background Image URL",
            placeholder="Paste the URL of the image you want on the board background.",
            default=self.config.icon_url,
            required=False,
            max_length=50,
        )

        self.add_item(self.title_input)
        self.add_item(self.perpage_input)
        self.add_item(self.sortby_input)
        self.add_item(self.iconurl_input)

    async def on_submit(self, interaction: Interaction, /) -> None:
        query = """UPDATE boards SET title=$1,
                                     per_page=$2,
                                     sort_by=$3,
                                     icon_url=$4
                    WHERE message_id = $5
                    RETURNING *
                """

        try:
            perpage = int(self.perpage_input.value)
        except ValueError:
            perpage = 0

        sortby = ValidBoardSorting.parse_item(self.config.type, self.sortby_input.value)
        url = self.iconurl_input.value
        if url in ['default', 'none', 'remove']:
            url = None

        fetch = await self.bot.pool.fetchrow(query, self.title_input.value, perpage, sortby, url)

        await interaction.response.send_message(f"Configuration successfully updated!", ephemeral=True)

        config = BoardConfig(bot=self.bot, record=fetch)
        await self.update_board(None, config=config)


class PersistentBoardView(discord.ui.View):
    def __init__(self, bot, update_board, guild_id, channel_id, board_type):
        super().__init__(timeout=None)
        self.add_item(CustomButton(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            custom_id=f"board:{board_type}:{channel_id}:refresh",
            emoji=REFRESH_EMOJI,
            bot=bot,
            update_board=update_board,
            row=0,
        ))

        self.add_item(CustomButton(
            label="Edit Board",
            style=discord.ButtonStyle.secondary,
            custom_id=f"board:{board_type}:{channel_id}:edit",
            emoji=GEAR_EMOJI,
            bot=bot,
            update_board=update_board,
            row=0,
        ))

        self.add_item(CustomButton(
            label="Previous",
            style=discord.ButtonStyle.secondary,
            custom_id=f"board:{board_type}:{channel_id}:prev",
            emoji=LEFT_EMOJI,
            bot=bot,
            update_board=update_board,
            row=1,
        ))

        self.add_item(CustomButton(
            label="Next Page",
            style=discord.ButtonStyle.secondary,
            custom_id=f"board:{board_type}:{channel_id}:next",
            emoji=RIGHT_EMOJI,
            bot=bot,
            update_board=update_board,
            row=1,
        ))


class DonationBoard(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot):
        self.bot = bot

        self.clan_updates = []

        self._to_be_deleted = set()

        self._batch_lock = asyncio.Lock()
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
        self.board_updater = SyncBoards(
            self.bot, start_loop=False, session=self.bot.session, fake_clan_guilds=self.bot.fake_clan_guilds
        )

        fetch = await self.bot.pool.fetch("SELECT channel_id, guild_id, type FROM boards WHERE toggle=True")
        for row in fetch:
            if row["type"] == "donation":
                self.bot.add_view(
                    PersistentBoardView(self.bot, self.update_board, row["guild_id"], row["channel_id"], row["type"])
                )

    @commands.command()
    @commands.is_owner()
    async def test_button(self, ctx, channel: discord.TextChannel, message_id: int, board_type: str):
        msg = await channel.fetch_message(message_id)
        await msg.edit(view=PersistentBoardView(self.bot, self.update_board, ctx.guild.id, channel.id, board_type))
        try:
            await msg.clear_reactions()
        except:
            await ctx.send("No permission to clear reactions.")
        else:
            await ctx.send("Done.")

    @commands.command()
    async def rb(self, ctx, *, board_type: str = None):
        if board_type:
            fetch = await ctx.db.fetchrow("SELECT * FROM boards WHERE type = $1 OFFSET random() LIMIT 1", board_type)
        else:
            fetch = await ctx.db.fetchrow("SELECT * FROM boards OFFSET random() LIMIT 1")

        config = BoardConfig(bot=self.bot, record=fetch)
        await self.update_board(None, config, divert_to=ctx.channel.id)

    @commands.command()
    async def showboard(self, ctx, *, board_type: str = "donation"):
        """Show boards in your server. If no boards are setup it will create one with clans added to the current channel.

        **Parameters**
        :key: Board Type: `donation`, `trophy` or `legend`. Defaults to `donation`.

        **Format**
        :information_source: `+showboard BOARD_TYPE`

        **Example**
        :white_check_mark: `+showboard`
        :white_check_mark: `+showboard donation`
        :white_check_mark: `+showboard trophy`
        """
        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
            board_type = board_type.replace(channel.mention, "").strip()

        else:
            channel = ctx.channel

        if board_type not in ("donation", "trophy", "legend", "war"):
            board_type = "donation"

        query = """
        SELECT DISTINCT boards.*
        FROM boards
        INNER JOIN clans
        ON clans.channel_id = boards.channel_id
        WHERE clans.clan_tag IN (SELECT clan_tag FROM clans WHERE channel_id = $1)
        AND boards.guild_id = $2
        AND type = $3
        """
        fetch = await ctx.db.fetch(query, channel.id, ctx.guild.id, board_type)
        if not fetch:
            exists = await ctx.db.fetch("SELECT 1 FROM clans WHERE channel_id = $1", channel.id)
            if not exists:
                return await ctx.send("I couldn't find any clans added to this channel.")

            fake_record = {
                "guild_id": ctx.guild.id,
                "channel_id": ctx.channel.id,
                "icon_url": None,
                "title": None,
                "sort_by": default_sort_by[board_type],
                "toggle": True,
                "type": board_type,
                "in_event": False,
                "message_id": None,
                "per_page": 0,
                "page": 1,
                "season_id": None,
            }

            configs = [BoardConfig(bot=self.bot, record=fake_record)]
        else:
            configs = [BoardConfig(bot=self.bot, record=row) for row in fetch]

        async with ctx.typing():
            for config in configs:
                await self.update_board(None, config, divert_to=ctx.channel.id)

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
            lookup = {'donation': 'donations', 'legend': 'finishing', 'trophy': 'trophies', 'war': 'stars'}
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

        await self.board_updater.update_board(config, **kwargs)


async def setup(bot):
    await bot.add_cog(DonationBoard(bot))
