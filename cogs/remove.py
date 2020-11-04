import discord
import asyncio
import datetime
import coc
import logging

from discord.ext import commands
from cogs.utils.checks import manage_guild
from cogs.utils.formatters import CLYTable
from cogs.utils import checks

log = logging.getLogger(__name__)


class Remove(commands.Cog):
    """Remove clans, players, boards, logs and more."""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_subcommands=True)
    async def remove(self, ctx):
        """[Group] Allows the user to remove a variety of features from the bot."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @remove.command(name='clan')
    @checks.manage_guild()
    async def remove_clan(self, ctx, *, channel: str, clan_tag: str = None):
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
        clan_tag = channel  # need to fool the help parser
        channel = ctx.message.channel_mentions and ctx.message.channel_mentions[0] or ctx.channel
        clan_tag = coc.utils.correct_tag(clan_tag)

        fetch = await ctx.db.fetchrow("DELETE FROM clans WHERE clan_tag=$1 AND channel_id=$2 RETURNING clan_name", clan_tag, channel.id)
        if fetch:
            await ctx.send(f"👌 {fetch['clan_name']} successfully removed from {channel.mention}.")
            self.bot.dispatch('clan_unclaim', ctx, await self.bot.coc.get_clan(clan_tag))
        else:
            await ctx.send(f":x: {clan_tag} wasn't added in {channel.mention}.")

    @remove.command(name='discord')
    async def remove_discord(self, ctx, *, player: str):
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
            fetch = await ctx.db.fetchrow("SELECT DISTINCT player_tag FROM players WHERE player_name LIKE $1", player)
            if not fetch:
                return await ctx.send(f":x: {player} is not a valid player tag, and I couldn't find a player with that name in my database. Please try again.")
            player = fetch['player_tag']

        if ctx.channel.permissions_for(ctx.author).manage_guild \
                or await self.bot.is_owner(ctx.author):
            await ctx.db.execute("UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2", player, season_id)
            await self.bot.links.delete_link(player)
            return await ctx.send("👌 Player successfully removed.")

        link = await self.bot.links.get_link(player)
        if link != ctx.author.id:
            member = ctx.guild.get_member(link) or self.bot.get_user(link) or await self.bot.fetch_user(link) or link
            return await ctx.send(
                f':x: Player has been claimed by {member}.\n'
                f'Please contact them, or someone with `Manage Server` permissions to unclaim it.'
            )

        await ctx.db.execute("UPDATE players SET user_id = NULL WHERE player_tag = $1 AND season_id = $2", player, season_id)
        await self.bot.links.delete_link(player)
        return await ctx.send("👌 Player successfully removed.")

    async def do_board_remove(self, ctx, channel, type_):
        fetch = await ctx.db.fetchrow("DELETE FROM boards WHERE channel_id=$1 AND type=$2 RETURNING message_id", channel.id, type_)
        if not fetch:
            return await ctx.send(f":x: I couldn't find a {type_}board in {channel.mention}.")

        if await ctx.db.fetchrow("SELECT id FROM boards WHERE channel_id = $1", channel.id) is not None:
            try:
                await self.bot.http.delete_message(channel.id, fetch['message_id'])
                msg = f"👌 {type_.capitalize()}board successfully removed"
            except discord.HTTPException:
                msg = f"👌 {type_.capitalize()}board successfully removed, but deleting the message failed."

        else:
            try:
                await channel.delete(reason=f'Command done by {ctx.author} ({ctx.author.id})')
                msg = f"👌 {type_.capitalize()}board sucessfully removed and channel deleted."
            except (discord.Forbidden, discord.HTTPException):
                msg = f"👌 {type_.capitalize()}board successfully removed.\n" \
                       "⚠ I don't have permissions to delete the channel. Please manually delete it."
            await ctx.db.execute("DELETE FROM clans WHERE channel_id = $1", channel.id)

        await ctx.send(msg)

    @staticmethod
    async def do_log_remove(ctx, channel, type_):
        fetch = await ctx.db.fetch("DELETE FROM logs WHERE channel_id=$1 AND type=$2 RETURNING id", channel.id, type_)
        if fetch:
            return await ctx.send(f"👌 {type_.capitalize()}log successfully deleted.")
        else:
            return await ctx.send(f":x: No {type_}log found for {channel.mention}.")

    @remove.command(name='donationboard', aliases=['donation board', 'donboard'])
    @checks.manage_guild()
    async def remove_donationboard(self, ctx, channel: discord.TextChannel = None):
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
        await self.do_board_remove(ctx, channel or ctx.channel, "donation")

    @remove.command(name='trophyboard', aliases=['trophy board', 'tropboard'])
    @manage_guild()
    async def remove_trophyboard(self, ctx, channel: discord.TextChannel = None):
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
        await self.do_board_remove(ctx, channel or ctx.channel, "trophy")

    @remove.command(name='legendboard')
    @manage_guild()
    async def remove_legendboard(self, ctx, channel: discord.TextChannel = None):
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
        await self.do_board_remove(ctx, channel or ctx.channel, 'legend')

    @remove.command(name='donationlog')
    @manage_guild()
    async def remove_donationlog(self, ctx, channel: discord.TextChannel = None):
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
        await self.do_log_remove(ctx, channel or ctx.channel, 'donation')

    @remove.command(name='trophylog')
    @manage_guild()
    async def remove_trophylog(self, ctx, channel: discord.TextChannel = None):
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
        await self.do_log_remove(ctx, channel or ctx.channel, 'trophy')

    @remove.command(name='legendlog', aliases=['legendlogs'])
    async def remove_legendlog(self, ctx, board_channel: discord.TextChannel = None):
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
        channel = board_channel or ctx.channel
        query = "UPDATE boards SET divert_to_channel_id = null WHERE channel_id = $1 AND type = 'legend' RETURNING id"
        fetch = await ctx.db.fetchrow(query, channel.id)
        if fetch:
            await ctx.send(f"👌 Legend board log channel removed. No logs will be posted.")
        else:
            await ctx.send(f":x: No Legend board found in {channel.mention}. Please try again.")

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
        # ctx.bot.utils.event_config.invalidate(ctx.bot.utils, ctx.guild.id)
        self.bot.dispatch('event_register')
        return await ctx.send(f"{fetch[index]['event_name']} has been removed.")


def setup(bot):
    bot.add_cog(Remove(bot))
