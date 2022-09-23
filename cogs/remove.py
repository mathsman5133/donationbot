import discord
import asyncio
import datetime
import coc
import logging

from discord import app_commands
from discord.ext import commands
from cogs.utils.checks import manage_guild
from cogs.utils.formatters import CLYTable
from cogs.utils import checks

log = logging.getLogger(__name__)


class Remove(commands.Cog):
    """Remove clans, players, boards, logs and more."""
    def __init__(self, bot):
        self.bot = bot

    remove_group = app_commands.Group(name="remove", description="Allows the user to remove a variety of features from the bot.")

    @remove_group.command(name='clan', description="Unlink a clan from a channel.")
    @app_commands.describe(channel="The channel to remove the clan from", clan_tag="The clan #tag to remove")
    @checks.manage_guild()
    async def remove_clan(self, intr: discord.Interaction, channel: discord.TextChannel, clan_tag: str):
        """Unlink a clan from a channel.

        **Parameters**
        :key: A discord channel (#mention). If not present, it will use the channel you're currently in.
        :key: A clan tag

        **Format**
        :information_source: `+remove clan #CLAN_TAG`
        :information_source: `+remove clan #CHANNEL #CLAN_TAG`

        **Example**
        :white_check_mark: `+remove clan #P0LYJC8C`
        :white_check_mark: `+remove clan #donationlog #CLAN_TAG`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or intr.channel
        fetch = await self.bot.pool.fetchrow("DELETE FROM clans WHERE clan_tag=$1 AND channel_id=$2 RETURNING clan_name", clan_tag, channel.id)
        if fetch:
            await intr.response.send_message(f"👌 {fetch['clan_name']} successfully removed from {channel.mention}.")
        else:
            await intr.response.send_message(f":x: {clan_tag} wasn't added in {channel.mention}.")

    @remove_group.command(name='emoji', description="Remove an emoji assosiated with a clan.")
    @app_commands.describe(clan="The clan #tag to remove")
    @checks.manage_guild()
    async def remove_emoji(self, intr: discord.Interaction, clan: str):
        """Remove an emoji assosiated with a clan.

        **Parameters**
        :key: A clan name or tag

        **Format**
        :information_source: `+remove emoji #CLANTAG`
        :information_source: `+remove emoji CLAN NAME`

        **Example**
        :white_check_mark: `+remove emoji #P0LYJC8C`
        :white_check_mark: `+remove emoji Reddit Elephino`"""
        if coc.utils.is_valid_tag(coc.utils.correct_tag(clan)):
            clan = coc.utils.correct_tag(clan)

        fetch = await self.bot.pool.fetchrow(
            "UPDATE clans SET emoji=null WHERE clan_tag = $1 OR clan_name LIKE $1 AND guild_id=$2 RETURNING clan_name",
            clan, intr.guild.id
        )
        if fetch:
            await intr.response.send_message(f"👌 Removed emoji for {fetch['clan_name']}.")
        else:
            await intr.response.send_message(f":x: I couldn't find a clan called {clan}. Perhaps try the tag?")

    @remove_group.command(name='discord', description="Unlink a clash account from your discord account.")
    @app_commands.describe(player="The player #tag to remove")
    async def remove_discord(self, intr: discord.Interaction, player: str):
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

        if not coc.utils.is_valid_tag(player):
            fetch = await self.bot.pool.fetchrow("SELECT DISTINCT player_tag FROM players WHERE player_name LIKE $1", player)
            if not fetch:
                return await intr.response.send_message(f":x: {player} is not a valid player tag, and I couldn't find a player with that name in my database. Please try again.")
            player = fetch['player_tag']

        if intr.channel.permissions_for(intr.user).manage_guild \
                or await self.bot.is_owner(intr.user):
            await self.bot.pool.execute("UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2", player, season_id)
            await self.bot.links.delete_link(player)
            return await intr.response.send_message("👌 Player successfully removed.")

        link = await self.bot.links.get_link(player)
        if link != intr.user.id:
            member = intr.guild.get_member(link) or self.bot.get_user(link) or await self.bot.fetch_user(link) or link
            return await intr.response.send_message(
                f':x: Player has been claimed by {member}.\n'
                f'Please contact them, or someone with `Manage Server` permissions to unclaim it.'
            )

        await self.bot.pool.execute("UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2", player, season_id)
        await self.bot.links.delete_link(player)
        return await intr.response.send_message("👌 Player successfully removed.")

    async def do_board_remove(self, intr: discord.Interaction, channel, type_):
        fetch = await self.bot.pool.fetchrow("DELETE FROM boards WHERE channel_id=$1 AND type=$2 RETURNING message_id", channel.id, type_)
        if not fetch:
            return await intr.response.send_message(f":x: I couldn't find a {type_}board in {channel.mention}.")

        if await self.bot.pool.fetchrow("SELECT id FROM boards WHERE channel_id = $1", channel.id) is not None:
            try:
                await self.bot.http.delete_message(channel.id, fetch['message_id'])
                msg = f"👌 {type_.capitalize()}board successfully removed"
            except discord.HTTPException:
                msg = f"👌 {type_.capitalize()}board successfully removed, but deleting the message failed."

        else:
            try:
                await channel.delete(reason=f'Command done by {intr.user} ({intr.user.id})')
                msg = f"👌 {type_.capitalize()}board sucessfully removed and channel deleted."
            except (discord.Forbidden, discord.HTTPException):
                msg = f"👌 {type_.capitalize()}board successfully removed.\n" \
                       "⚠ I don't have permissions to delete the channel. Please manually delete it."
            await self.bot.pool.execute("DELETE FROM clans WHERE channel_id = $1", channel.id)

        await intr.response.send_message(msg)

    async def do_log_remove(self, intr: discord.Interaction, channel, type_):
        fetch = await self.bot.pool.fetch("DELETE FROM logs WHERE channel_id=$1 AND type=$2 RETURNING id", channel.id, type_)
        if fetch:
            return await intr.response.send_message(f"👌 {type_.capitalize()}log successfully deleted.")
        else:
            return await intr.response.send_message(f":x: No {type_}log found for {channel.mention}.")

    @remove_group.command(name='donationboard', description="Removes the channel's donationboard.")
    @app_commands.describe(channel="The channel the donationboard is located.")
    @checks.manage_guild()
    async def remove_donationboard(self, intr: discord.Interaction, channel: discord.TextChannel):
        """Removes the guild donationboard.

        **Parameters**
        :key: A discord channel. If not present, it will use the channel you're currently in.

        **Format**
        :information_source: `+remove donationboard`
        :information_source: `+remove donationboard #CHANNEL`

        **Example**
        :white_check_mark: `+remove donationboard`
        :white_check_mark: `+remove donationboard #donationboard`

        **Required Permissions**
        :warning: Manage Server
        """
        await self.do_board_remove(intr, channel or intr.channel, "donation")

    @remove_group.command(name='trophyboard', description="Removes the channel's trophyboard.")
    @app_commands.describe(channel="The channel the trophyboard is located.")
    @manage_guild()
    async def remove_trophyboard(self, intr: discord.Interaction, channel: discord.TextChannel):
        """Removes a trophyboard.

        **Parameters**
        :key: A discord channel. If not present, it will use the channel you're currently in.

        **Format**
        :information_source: `+remove trophyboard`
        :information_source: `+remove trophyboard #CHANNEL`

        **Example**
        :white_check_mark: `+remove trophyboard`
        :white_check_mark: `+remove trophyboard #trophyboard`

        **Required Permissions**
        :warning: Manage Server
        """
        await self.do_board_remove(intr, channel or intr.channel, "trophy")

    @remove_group.command(name='legendboard', description="Removes the channel's legendboard.")
    @app_commands.describe(channel="The channel the legendboard is located.")
    @manage_guild()
    async def remove_legendboard(self, intr: discord.Interaction, channel: discord.TextChannel):
        """Removes a channel's legend board.

        **Parameters**
        :key: A discord channel to remove the legend board from.

        **Format**
        :information_source: `+remove legendboard #CHANNEL`

        **Example**
        :white_check_mark: `+remove legendboard #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        await self.do_board_remove(intr, channel or intr.channel, 'legend')

    # @remove_group.command(name='warboard', aliases=['war board', 'warsboard'])
    # @checks.manage_guild()
    # async def remove_warboard(self, intr: discord.Interaction, channel: discord.TextChannel = None):
    #     """Removes the guild warboard.
    #
    #     **Parameters**
    #     :key: A discord channel. If not present, it will use the channel you're currently in.
    #
    #     **Format**
    #     :information_source: `+remove warboard`
    #     :information_source: `+remove warboard #CHANNEL`
    #
    #     **Example**
    #     :white_check_mark: `+remove warboard`
    #     :white_check_mark: `+remove warboard #dt-boards`
    #
    #     **Required Permissions**
    #     :warning: Manage Server
    #     """
    #     await self.do_board_remove(intr, channel or intr.channel, "war")

    @remove_group.command(name='donationlog', description="Removes the channel's donationlog.")
    @app_commands.describe(channel="The channel the donationlog is located.")
    @manage_guild()
    async def remove_donationlog(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_log_remove(intr, channel or intr.channel, 'donation')

    @remove_group.command(name='trophylog', description="Removes the channel's trophylog.")
    @app_commands.describe(channel="The channel the trophylog is located.")
    @manage_guild()
    async def remove_trophylog(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_log_remove(intr, channel or intr.channel, 'trophy')

    @remove_group.command(name='legendlog', description="Remove the legend log channel.")
    @app_commands.describe(channel="The channel the legendlog is located.")
    async def remove_legendlog(self, intr: discord.Interaction, channel: discord.TextChannel):
        """Remove the legend log channel.

        **Parameters**
        :key: A channel where the legendboard is located (#mention).

        **Format**
        :information_source: `+remove legendlog #BOARD-CHANNEL`

        **Example**
        :white_check_mark: `+remove legendlog #legend-boards`
        :white_check_mark: `+remove legendlog #dt-boards`

        **Required Permissions**
        :warning: Manage Server
        """
        channel = channel or intr.channel
        query = "UPDATE boards SET divert_to_channel_id = null WHERE channel_id = $1 AND type = 'legend' RETURNING id"
        fetch = await self.bot.pool.fetchrow(query, channel.id)
        if fetch:
            await intr.response.send_message(f"👌 Legend board log channel removed. No logs will be posted.")
        else:
            await intr.response.send_message(f":x: No Legend board found in {channel.mention}. Please try again.")



async def setup(bot):
    await bot.add_cog(Remove(bot))
