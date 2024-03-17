import asyncio
import typing
import re

import asyncpg as asyncpg
import coc
import discord
import logging

from collections import namedtuple

from discord import Interaction, app_commands
from discord.ext import commands

from cogs.add import BOARD_PLACEHOLDER, titles, default_sort_by
from cogs.utils.checks import manage_guild
from cogs.utils.db_objects import DatabaseMessage, BoardConfig
from syncboards import SyncBoards, default_sort_by

if typing.TYPE_CHECKING:
    from bot import DonationBot


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
LEGEND_EMOJI = discord.PartialEmoji.from_str("<:LegendLeague:601612163169255436>")
TROPHY_EMOJI = discord.PartialEmoji.from_str("<:trophygold:632521243278442505>")
DONATE_EMOJI = discord.PartialEmoji.from_str("<:donated_cc:684682634277683405>")

GLOBAL_BOARDS_CHANNEL_ID = 663683345108172830


CHANNEL_CONFIRMATION_MESSAGE = \
    f"Would you like me to create a new channel, or would you like to use an existing channel?\n\n" \
    f"It is important that the board channel is an empty channel where I am the only one with " \
    f"permission to send messages.\nI will send one message per board - and continue to edit " \
    f"them forever. Many board messages are now years old and still working normally."


class BoardButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template="board:(?P<type>(donation|trophy|legend)):(?P<id>[0-9]+):(?P<command>(refresh|edit|prev|next))"
):
    emojis = {
        "refresh": REFRESH_EMOJI,
        "edit": GEAR_EMOJI,
        "prev": LEFT_EMOJI,
        "next": RIGHT_EMOJI,
    }

    def __init__(self, config: BoardConfig, cog: "DonationBoard", label, key):
        super().__init__(discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"board:{config.type}:{config.message_id}:{key}",
            emoji=self.emojis.get(key),
            row=self.get_row(key),
        ))
        self.config = config
        self.cog = cog
        self.key = key

    @staticmethod
    def get_row(key):
        return 0 if key in ("refresh", "edit") else 1

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction["DonationBot"], item: discord.ui.Button, match: re.Match[str]):
        cog: typing.Optional[DonationBoard] = interaction.client.get_cog("DonationBoard")
        if cog is None:
            await interaction.response.send_message(
                "Sorry, this button doesn't work at the moment. Please try again later.", ephemeral=True
            )
            return

        config = await cog.get_board_config(interaction.message.id)
        if config is None:
            await interaction.response.send_message("Sorry, we couldn't find your board.", ephemeral=True)
            log.info(f"Couldn't find board config from button match, ID {match['id']}, channel {interaction.channel_id}")
            return
        return cls(config, cog, item.label, match["command"])

    async def callback(self, interaction: discord.Interaction["DonationBot"]):
        message_id = interaction.message.id

        fetch = None
        if self.key == "prev":
            fetch = await self.cog.bot.pool.fetchrow('UPDATE boards SET page = page - 1, toggle=True WHERE message_id = $1 AND page > 1 RETURNING *', message_id)
            if not fetch:
                await interaction.response.send_message("You can't go back past the first page.")
                return

        elif self.key == "next":
            fetch = await self.cog.bot.pool.fetchrow('UPDATE boards SET page = page + 1, toggle=True WHERE message_id = $1 RETURNING *', message_id)

        elif self.key == "refresh":
            query = "UPDATE boards SET page=1, season_id=0, toggle=True WHERE message_id = $1 RETURNING *"
            fetch = await self.cog.bot.pool.fetchrow(query, message_id)

        elif self.key == "edit":
            await interaction.response.send_modal(EditBoardModal(self.config, self.cog))
            return

        if not fetch:
            await interaction.response.send_message("Sorry, something went wrong. Please try again later.", ephemeral=True)
            return

        config = BoardConfig(bot=self.cog.bot, record=fetch)
        await interaction.response.defer()
        await self.cog.update_board(None, config=config)

    async def interaction_check(self, interaction: discord.Interaction["DonationBot"], /):
        if self.key == "edit" and not interaction.permissions.manage_guild:
            await interaction.response.send_message(
                "Sorry, you need Manage Server permissions to edit the board. Perhaps ask an admin?", ephemeral=True
            )
            return False

        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

        # Make sure we know what the error actually is
        log.exception(f"Board Modal Error. Channel ID: {self.config.channel_id}", exc_info=error)


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
    def __init__(self, config: BoardConfig, cog: "DonationBoard"):
        super().__init__()

        self.bot = cog.bot
        self.config = config
        self.cog = cog

        self.title_input = discord.ui.TextInput(
            label="Board Title",
            placeholder="The title to show at the top of your board image.",
            default=self.config.title,
            required=False
        )
        self.perpage_input = discord.ui.TextInput(
            label="Players per page",
            placeholder="Enter a number (e.g. 20), or leave blank",
            default=str(self.config.per_page or ""),
            required=False
        )
        self.sortby_input = discord.ui.TextInput(
            label=f"Sort by ({ValidBoardSorting.get_human_readable(self.config.type)})",
            placeholder=ValidBoardSorting.reverseparse(self.config.type, self.config.sort_by),
            required=False
        )
        self.iconurl_input = discord.ui.TextInput(
            label="Background Image URL",
            placeholder="URL of the image",
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

        fetch = await self.bot.pool.fetchrow(query, self.title_input.value, perpage, sortby, url, self.config.message_id)

        await interaction.response.send_message(f"Configuration successfully updated!", ephemeral=True)

        config = BoardConfig(bot=self.bot, record=fetch)
        await self.cog.update_board(None, config=config)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

        # Make sure we know what the error actually is
        log.exception(f"Board Modal Error. Channel ID: {self.config.channel_id}", exc_info=error)


class BoardChannelSelectView(discord.ui.View):
    channel: discord.TextChannel

    def __init__(self, author_id):
        super().__init__()
        self.author_id = author_id
        self.message = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect, placeholder="Choose a channel...", channel_types=[discord.ChannelType.text]
    )
    async def callback(self, interaction: Interaction["DonationBot"], select: discord.ui.ChannelSelect):
        channel = select.values[0].resolve()
        if not channel.permissions_for(channel.guild.get_member(interaction.client.user.id)).send_messages:
            await interaction.response.send_message(
                "I don't have permission to send messages in that channel!", ephemeral=True
            )
            return

        self.channel = channel
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            await self.message.delete()


class BoardCreateConfirmation(discord.ui.View):
    def __init__(self, *, author_id: int):
        super().__init__()
        self.author_id = author_id
        self.message = None
        self.value = None
        self.channel = None

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id == self.author_id:
            return True
        else:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return False

    async def on_timeout(self) -> None:
        if self.message:
            await self.message.delete()

    async def stop_and_set_response(self, interaction: discord.Interaction["DonationBot"], value: str):
        self.value = value
        await interaction.defer()
        await interaction.delete_original_response()
        self.stop()

    @discord.ui.button(label="Create New Channel", style=discord.ButtonStyle.green)
    async def new_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = "new_channel"
        await interaction.defer()
        await interaction.delete_original_response()
        self.stop()

    @discord.ui.button(label="Use Existing Channel", style=discord.ButtonStyle.blurple)
    async def existing_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BoardChannelSelectView(interaction.user.id)
        await interaction.response.send_message(
            "Select which existing channel I should create the boards in.", view=view
        )
        view.message = interaction.original_response()
        await view.wait()

        await interaction.followup.send(
            f"Added {view.channel.mention} as a new board channel. "
            f"Feel free to add clans and boards with the original menu."
        )
        await interaction.delete_original_response()
        self.channel = view.channel
        self.value = "existing_channel"
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = ""
        await interaction.defer()
        await interaction.delete_original_response()
        self.stop()


class AddClanModal(discord.ui.Modal, title="Add Clan"):
    clan_tag = discord.ui.TextInput(label="Clan Tag", placeholder="#clantag as found in-game.", max_length=10)

    def __init__(self, menu: "BoardSetupMenu"):
        super().__init__()
        self.menu = menu
        self.bot = menu.bot

    async def on_submit(self, interaction: Interaction["DonationBot"], /) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        coc_client: "coc.Client" = self.menu.cog.bot.coc
        try:
            clan = await coc_client.get_clan(self.clan_tag.value)
        except coc.NotFound:
            await interaction.response.send_message("Sorry, that clan tag was invalid. Please try again", ephemeral=True)
            return
        except coc.HTTPException as exc:
            await interaction.response.send_message("Sorry, something broke. Please try again.", ephemeral=True)
            log.error("Error trying to add / find coc clan", exc_info=exc)
            return

        query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name, fake_clan) VALUES ($1, $2, $3, $4, $5)"
        try:
            await self.bot.pool.execute(query, clan.tag, interaction.guild_id, self.menu.channel.id, str(clan), False)
        except asyncpg.UniqueViolationError:
            await interaction.followup.send("You've already added that clan!", ephemeral=True)
            return

        message = f"Successfully added {clan.name} ({clan.tag}) to {self.menu.channel.mention}.\n\n"
        sent = await interaction.followup.send(
            message + f"Please wait while I add all the clan members.", ephemeral=True
        )

        log.info("Adding clan members, clan %s has %s members", clan.tag, len(clan.members))
        season_id = await self.bot.seasonconfig.get_season_id()
        query = """INSERT INTO players (
                                        player_tag, 
                                        donations, 
                                        received, 
                                        trophies, 
                                        start_trophies, 
                                        season_id,
                                        clan_tag,
                                        player_name,
                                        best_trophies,
                                        legend_trophies
                                        ) 
                    VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8,$9) 
                    ON CONFLICT (player_tag, season_id) 
                    DO UPDATE SET clan_tag = $6
                """
        async for member in clan.get_detailed_members():
            log.info("`+add clan`, adding member: %s to clan %s", clan.tag, member)
            await self.bot.pool.execute(
                query,
                member.tag,
                member.donations,
                member.received,
                member.trophies,
                season_id,
                clan.tag,
                member.name,
                member.best_trophies,
                member.legend_statistics and member.legend_statistics.legend_trophies or 0
            )

        await sent.edit(content=message + "Successfully added all clan members.")
        await self.menu.sync_clans()


class BoardSetupMenu(discord.ui.View):
    message: discord.Message
    channel: discord.TextChannel

    def __init__(self, cog: "DonationBoard", user: discord.abc.User, guild: discord.Guild):
        super().__init__(timeout=600)

        self.clan_name_lookup = {}

        self.user = user
        self.guild = guild
        self.cog = cog
        self.bot = cog.bot

        self.channel = None
        self.message = None
        self.configs = []

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id == self.user.id:
            return True
        else:
            await interaction.response.send_message("This menu is not for you!", ephemeral=True)
            return False

    async def on_timeout(self) -> None:
        try:
            await self.message.delete()
        except:
            pass

    async def create_board(self, board_type):
        msg = await self.channel.send(BOARD_PLACEHOLDER.format(board=board_type))
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
                        DO UPDATE SET message_id = $3, toggle = True
                        RETURNING *;
                        """
        fetch = await self.cog.bot.pool.fetchrow(
            query, self.channel.guild.id, self.channel.id, msg.id, board_type, titles[board_type], default_sort_by[board_type]
        )
        config = BoardConfig(bot=self.cog.bot, record=fetch)
        await msg.edit(view=self.cog.create_new_board_view(config))
        await self.bot.donationboard.update_board(message_id=msg.id)

    async def delete_board(self, board_type):
        fetch = await self.cog.bot.pool.fetchrow(
            "DELETE FROM boards WHERE channel_id=$1 AND type=$2 RETURNING message_id", self.channel.id, board_type
        )
        try:
            msg = await self.channel.fetch_message(fetch['message_id'])
            await msg.delete()
        except:
            pass

    async def get_board_types(self) -> set[str]:
        fetch = await self.cog.bot.pool.fetch("SELECT type FROM boards WHERE channel_id=$1", self.channel.id)
        if not fetch:
            return set()
        return {r["type"] for r in fetch}

    async def get_all_boards_config(self, channel_id: int):
        fetch = await self.cog.bot.pool.fetch("SELECT * FROM boards WHERE channel_id=$1", channel_id)
        return [BoardConfig(bot=self.cog.bot, record=row) for row in fetch]

    async def load_default_channel(self):
        fetch = await self.cog.bot.pool.fetch("SELECT DISTINCT channel_id FROM boards WHERE guild_id=$1", self.guild.id)
        channels = [self.guild.get_channel(row["channel_id"]) for row in fetch]
        channels = [c for c in channels if c]
        if not channels:
            return

        channel = channels[0]
        self.configs = await self.get_all_boards_config(channel.id)
        await self.set_new_channel_selected(channel)

        self.channel_select_action.options = [
            discord.SelectOption(
                label=f"#{c.name} ({c.category} category)",
                value=str(c.id),
                default=c == channel
            ) for c in channels
        ]

    async def set_new_channel_selected(self, channel):
        types_enabled = [c.type for c in self.configs]
        self.channel = channel
        for option in self.board_type_select_action.options:
            option.default = option.value in types_enabled

        log.info(f"setting {', '.join(types_enabled)} as enabled")

        await self.sync_clans()

        self.channel_select_action.disabled = False
        self.board_type_select_action.disabled = False
        self.clan_select_action.disabled = False

    async def create_board_channel(self, interaction: discord.Interaction["DonationBot"]):
        if not interaction.app_permissions.manage_channels:
            log.info('+add board no create channel permissions')
            await interaction.response.send_message(
                f'Failed! I need manage channels permission to create your board channel.', ephemeral=True
            )
            return

        overwrites = {
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, read_message_history=True,
                embed_links=True, manage_messages=True, add_reactions=True,
            ),
            interaction.guild.default_role: discord.PermissionOverwrite(
                read_messages=True, send_messages=False, read_message_history=True,
            ),
        }

        try:
            channel = await interaction.guild.create_text_channel(
                name="dt-boards", overwrites=overwrites, reason=f'{interaction.user} created a boards channel.'
            )
        except discord.Forbidden:
            log.info('+add board no channel permissions (HTTP exception caught)')
            await interaction.response.send_message(f'I do not have permissions to create the board channel.', ephemeral=True)
            return
        except discord.HTTPException:
            log.info('+add board creating channel failed')
            await interaction.response.send_message(f'Creating the channel failed. Try checking the name?', ephemeral=True)
            return

        self.configs = []
        await self.set_new_channel_selected(channel)
        await interaction.response.send_message(
            f"Successfully created the new boards channel {channel.mention}. "
            f"Feel free to add clans and boards using the menu above.", ephemeral=True
        )
        await interaction.message.edit(view=self)

    @discord.ui.select(placeholder="Select board channel to configure...", row=0, options=[], max_values=1)
    async def channel_select_action(self, interaction: discord.Interaction["DonationBot"], select: discord.ui.Select):
        channel = self.bot.get_channel(int(select.values[0]))
        configs = await self.get_all_boards_config(channel.id)

        log.info(f"resolving channel {channel.id} and config {configs}")

        self.configs = configs
        await self.set_new_channel_selected(channel)
        await interaction.response.defer()
        await interaction.message.edit(view=self)

    @discord.ui.select(placeholder='Select board types to enable...', row=1, max_values=3, options=[
        discord.SelectOption(label="Donation Board", value="donation", description="An auto-updating donations leaderboard", emoji=DONATE_EMOJI),
        discord.SelectOption(label="Trophy Board", value="trophy", description="An auto-updating trophy leaderboard", emoji=TROPHY_EMOJI),
        discord.SelectOption(label="Legend Board", value="legend", description="An auto-updating legends leaderboard", emoji=LEGEND_EMOJI)
    ])
    async def board_type_select_action(self, interaction: discord.Interaction["DonationBot"], select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True, thinking=True)

        parse = {"donation": "Donation Board", "trophy": "Trophy Board", "legend": "Legend Board"}

        current = await self.get_board_types()
        new_select = set(select.values)
        new = new_select - current
        old = current - new_select

        for row in new:
            await self.create_board(row)
            await interaction.followup.send(f"Successfully created a new {parse[row].lower()} in {self.channel.mention}.", ephemeral=True)
        for row in old:
            await self.delete_board(row)
            await interaction.followup.send(f"Successfully removed the {parse[row].lower()} from {self.channel.mention}.", ephemeral=True)

        if not (new or old):
            await interaction.followup.send(f"All your boards are already setup.", ephemeral=True)

    async def get_clan_name(self, tag):
        try:
            return self.clan_name_lookup[tag]
        except KeyError:
            clan = await self.cog.bot.coc.get_clan(tag)
            return clan and clan.name

    async def get_channel_clans(self) -> set[str]:
        fetch = await self.cog.bot.pool.fetch("SELECT DISTINCT clan_tag FROM clans WHERE channel_id = $1", self.channel.id)
        return fetch and {r["clan_tag"] for r in fetch} or set()

    @discord.ui.select(placeholder="Select clans to add to the board...", row=2, options=[], max_values=1)
    async def clan_select_action(self, interaction: discord.Interaction["DonationBot"], select: discord.ui.Select):
        await interaction.response.defer(ephemeral=True)

        current = await self.get_channel_clans()

        new = set(select.values) - current
        old = current - set(select.values)

        added = []
        removed = []

        for tag in new:
            name = await self.get_clan_name(tag)
            query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name, fake_clan) VALUES ($1, $2, $3, $4, $5)"
            await self.bot.pool.execute(query, tag, self.channel.guild.id, self.channel.id, name, "#" in tag)
            added.append((name, tag))

        for tag in old:
            name = await self.get_clan_name(tag)
            await self.bot.pool.execute("DELETE FROM clans WHERE channel_id=$1 AND clan_tag=$2", self.channel.id, tag)
            removed.append((name, tag))

        message = (added and ("Successfully added " + ", ".join(f"{name} ({tag})" for name, tag in added) + f" to {self.channel.mention}.\n\n") or "") + \
                  (removed and ("Successfully removed " + ", ".join(f"{name} ({tag})" for name, tag in removed) + f" from {self.channel.mention}.") or "")

        if message:
            await interaction.followup.send(message, ephemeral=True)

    async def sync_clans(self):
        fetch = await self.bot.pool.fetch(
            "SELECT DISTINCT clan_tag, clan_name FROM clans WHERE guild_id=$1", self.channel.guild.id
        )
        current_clans = await self.get_channel_clans()

        self.clan_name_lookup = {r["clan_tag"]: r["clan_name"] for r in fetch}

        self.clan_select_action.options = [
            discord.SelectOption(
                label=f"{name} ({tag})",
                value=tag,
                default=tag in current_clans,
            ) for tag, name in self.clan_name_lookup.items()
        ]
        self.clan_select_action.max_values = len(self.clan_name_lookup)
        log.info(f"set clans enabled for channel {self.channel.id}: " + ", ".join(current_clans))

    @discord.ui.button(label="Add Clan", style=discord.ButtonStyle.green, row=3)
    async def add_clan_action(self, interaction: discord.Interaction["DonationBot"], button: discord.ui.Button):
        await interaction.response.send_modal(AddClanModal(self))

    @discord.ui.button(label="Add Channel", style=discord.ButtonStyle.green, row=3)
    async def add_channel_action(self, interaction: discord.Interaction["DonationBot"], button: discord.ui.Button):
        confirm = BoardCreateConfirmation(author_id=interaction.user.id)
        msg = await interaction.response.send_message(CHANNEL_CONFIRMATION_MESSAGE, view=confirm)
        confirm.message = msg
        await confirm.wait()
        if not confirm.value:
            return

        if confirm.value == "new_channel":
            await self.create_board_channel(interaction)
        else:
            await self.set_new_channel_selected(confirm.channel)

        await interaction.message.edit(view=self)

    # @discord.ui.button(label="Edit Config", style=discord.ButtonStyle.blue, row=3)
    # async def edit_config_action(self, interaction: discord.Interaction["DonationBot"], button: discord.ui.Button):

    @discord.ui.button(label="Help", style=discord.ButtonStyle.red, row=3)
    async def help_action(self, interaction: discord.Interaction["DonationBot"], button: discord.ui.Button):
        message = """
This is the board configuration menu. I'll explain how it works a bit now.

Boards are custom leaderboards for clans and families in Clash.
You can choose between donation boards for showing donation information, trophy boards for trophy information and legend boards for more legend-specific data.

When setting them up for the first time, I will send a message in the channel. Every time someone donates troops or gains / loses trophies, I will update the board. 
I will edit the original message I send - forever. Many people have boards which are years old. This means it's really important that nobody else sends messages in that channel - it's a view-only channel.

In this menu, you can create new boards or remove old ones, and add or remove clans from already configured boards.

- The "Add Clan" button will let you add a new clan to the board that doesn't exist in the server yet.
- The "Add Channel" button will let you add new board channel - perhaps for a second clan or different family.
- The "Help" button will give you this message!

This is a new feature - so if you find any bugs or have feedback, please let us know!
        """
# - The "Edit Config" button will let you edit the configuration for the current channel - title, players per page, etc.
        await interaction.response.send_message(message, ephemeral=True)


class DonationBoard(commands.Cog):
    """Contains all DonationBoard Configurations.
    """
    def __init__(self, bot: "DonationBot"):
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

        bot.add_dynamic_items(BoardButton)
        bot.loop.create_task(self.on_init())

    async def on_init(self):
        await self.bot.wait_until_ready()
        self.board_updater = SyncBoards(
            self.bot, start_loop=False, session=self.bot.session, fake_clan_guilds=self.bot.fake_clan_guilds
        )

    async def cog_unload(self) -> None:
        self.bot.remove_dynamic_items(BoardButton)

    async def get_board_config(self, message_id: int) -> typing.Optional[BoardConfig]:
        query = "SELECT * FROM boards WHERE message_id = $1"
        fetch = await self.bot.pool.fetchrow(query, message_id)
        if fetch:
            return BoardConfig(bot=self.bot, record=fetch)
        return None

    async def get_board_config_type(self, channel_id, board_type):
        query = "SELECT * FROM boards WHERE channel_id = $1 AND type = $2"
        fetch = await self.bot.pool.fetchrow(query, channel_id, board_type)
        if fetch:
            return BoardConfig(bot=self.bot, record=fetch)
        return None

    def create_new_board_view(self, config):
        view = discord.ui.View(timeout=None)
        for label, key in (("Refresh\u200b", "refresh"), ("Edit Board", "edit"), ("Previous", "prev"), ("Next Page", "next")):
            view.add_item(BoardButton(config, self, label, key))

        return view

    @app_commands.command(name='setup-boards', description="Setup or configure boards for the server")
    @manage_guild()
    async def setupboard(self, interaction: discord.Interaction):
        view = BoardSetupMenu(self, interaction.user, interaction.guild)
        await view.load_default_channel()

        message = "This menu allows you to configure boards for your sever.\n\n" \
                  "I've selected a board channel to get you started.\n" \
                  "If you have multiple board channels, simply change the selected channel.\n\n" \
                  "If you're still confused, press the 'Help' button."

        no_channel_message = "It seems you haven't yet configured a channel for boards.\n\n"
        if view.channel is None:
            confirm = BoardCreateConfirmation(author_id=interaction.user.id)

            msg = await interaction.response.send_message(
                no_channel_message + CHANNEL_CONFIRMATION_MESSAGE, view=confirm
            )
            confirm.message = msg
            await confirm.wait()
            if not confirm.value:
                return

            if confirm.value == "new_channel":
                await view.create_board_channel(interaction)
            else:
                await view.set_new_channel_selected(confirm.channel)

            msg = await interaction.edit_original_response(message, view=view)
        else:
            msg = await interaction.response.send_message(message, view=view)

        view.message = msg

    @commands.command()
    @commands.is_owner()
    async def test_button(self, ctx, message_id: int):
        config = await self.get_board_config(message_id)
        msg = await config.channel.fetch_message(message_id)

        await msg.edit(view=self.create_new_board_view(config))
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
