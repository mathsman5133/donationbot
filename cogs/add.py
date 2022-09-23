import discord
import asyncio
import typing
import datetime
import re
import coc
import logging
import math

import emoji as pckgemoji

from discord import app_commands
from discord.ext import commands

from syncboards import emojis, titles, default_sort_by, BOARD_PLACEHOLDER
from cogs.utils.checks import manage_guild, helper_check
from cogs.utils import checks
from cogs.utils.paginator import StatsAccountsPaginator

RCS_GUILD_ID = 295287647075827723
MONZETTI_GUILD_ID = 228438771966672896

log = logging.getLogger(__name__)

url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                           r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")

custom_emoji = re.compile("<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>")
unicode_regex = re.compile(u'(' + u'|'.join(re.escape(u)  for u in sorted(pckgemoji.unicode_codes.EMOJI_ALIAS_UNICODE_ENGLISH.values(), key=len, reverse=True)) + u')')


class Add(commands.Cog, name="add"):
    """Add clans, players, trophy and donationboards, logs and more."""

    def __init__(self, bot):
        self.bot = bot
        # super().__init__()

    add_group = app_commands.Group(name="add", description="Add clans, players, trophy and donationboards, logs and more.")

    @add_group.command(name="clan", description="Link a clan to a channel in your server.")
    @app_commands.describe(clan_tag="The clan tag to add", channel="The channel to add the clan to. Will default to current channel.")
    # @app_commands.checks.has_permissions(manage_guild=True)
    async def add_clan(self, intr: discord.Interaction, clan_tag: str, channel: discord.TextChannel):
        """Link a clan to a channel in your server.
                This will add all accounts in clan to the database, if not already added.

                Note: you must be an Elder or above in-game to add a clan. In order for the bot to verify this, please run `+verify #playertag`

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
        await intr.response.defer(thinking=True)
        channel = channel or intr.channel

        real_clan_tag = coc.utils.correct_tag(clan_tag)
        fake_clan_tag = clan_tag.strip() if clan_tag.strip().isdigit() and len(clan_tag) == 6 else None

        if not (coc.utils.is_valid_tag(clan_tag) or fake_clan_tag):
            return await intr.edit_original_response(content="That doesn't look like a proper clan tag. Please try again.")

        current = await self.bot.pool.fetch("SELECT DISTINCT clan_tag FROM clans WHERE guild_id = $1", intr.guild_id)
        # if len(current) > 3 and not checks.is_patron_pred(ctx):
        #     return await ctx.send('You must be a patron to have more than 4 clans claimed per server. '
        #                           'See more info with `+patron`, or join the support server for more help: '
        #                           f'{self.bot.support_invite}')

        if await self.bot.pool.fetch("SELECT id FROM clans WHERE clan_tag = $1 AND channel_id = $2", real_clan_tag, channel.id):
            return await intr.edit_original_response(content='This clan has already been linked to the channel. Please try again.')

        if "#" in real_clan_tag:
            try:
                clan = await self.bot.coc.get_clan(real_clan_tag)
            except coc.NotFound:
                return await intr.response.edit_original_response(f'Clan not found with `{real_clan_tag}` tag.')

            fetch = await self.bot.pool.fetch("SELECT player_tag FROM players WHERE user_id = $1 AND verified = True", intr.user.id)
            members = [n for n in (clan.get_member(m['player_tag']) for m in fetch) if n]
            is_verified = any(
                member.role in (coc.Role.elder, coc.Role.co_leader, coc.Role.leader) for member in members)

            check = is_verified \
                    or await self.bot.is_owner(intr.user) \
                    or real_clan_tag in (n['clan_tag'] for n in current) \
                    or intr.guild_id in (RCS_GUILD_ID, MONZETTI_GUILD_ID) \
                    or await helper_check(self.bot, intr.user) is True

            if not check and not fetch:
                return await intr.edit_original_response(content="Please verify your account before adding a clan: `+verify #playertag`. "
                                                        "See `+help verify` for more information.\n\n"
                                                        "This is a security feature of the bot to ensure you are an elder or above of the clan.")
            if not members and not check:
                return await intr.edit_original_response(content="Please ensure your verified account(s) are in the clan, and try again.")
            if members and not check:
                return await intr.edit_original_response(content="Your verified account(s) are not an elder or above. Please try again.")
        else:
            clan = "FakeClan"

        query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name, fake_clan) VALUES ($1, $2, $3, $4, $5)"
        await self.bot.pool.execute(query, fake_clan_tag or clan.tag, intr.guild_id, channel.id, str(clan), fake_clan_tag is not None)

        if not fake_clan_tag:
            log.info("Adding clan members, clan %s has %s members", real_clan_tag, len(clan.members))
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
            # async with ctx.db.transaction():
            async for member in clan.get_detailed_members():
                log.info("`+add clan`, adding member: %s to clan %s", real_clan_tag, member)
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

        await intr.edit_original_response(content=f"👌 {clan} ({fake_clan_tag or clan.tag}) successfully added to {channel.mention}.")
        self.bot.dispatch('clan_claim', intr, clan)

    @add_group.command(name='emoji', description="Add an emoji to a clan for use with leaderboard commands.")
    @app_commands.describe(clan="A clan name or tag", emoji="An emoji to add, either custom or normal.")
    @checks.manage_guild()
    async def add_emoji(self, intr: discord.Interaction, clan: str, emoji: str):
        """Add an emoji to a clan for use with leaderboard commands.

        The emoji will appear after the number ranking on commands such as `+don` to show which clan the member is in.
        Ensure that the emoji is in a shared server with the bot.

        **Parameters**
        :key: A clan name or tag
        :key: The emoji; can be custom or unicode

        **Format**
        :information_source: `+add emoji #CLANTAG :emoji:`
        :information_source: `+add emoji CLAN NAME :emoji:`

        **Example**
        :white_check_mark: `+add emoji #P0LYJC8C :the_best_clan:`
        :white_check_mark: `+add emoji Reddit Elephino :elephino:`
        """
        custom = custom_emoji.search(emoji)
        if custom:
            emoji = self.bot.get_emoji(int(custom.group('id')))
            emoji_id = emoji.id
        else:

            find = unicode_regex.search(emoji)
            if not find:
                return await intr.response.send_message("I couldn't find an emoji in your message!")

            emoji = find[0]
            emoji_id = emoji

        if not emoji:
            return await intr.response.send_message(
                ":x: It seems as though I don't have access to that emoji! "
                "\nMake sure it's on a server I share, and try again."
            )

        if coc.utils.is_valid_tag(coc.utils.correct_tag(clan)):
            clan_tag = coc.utils.correct_tag(clan)
        else:
            fetch = await self.bot.pool.fetchrow("SElECT clan_tag FROM clans WHERE clan_name LIKE $1 AND guild_id = $2", clan, intr.guild_id)
            if not fetch:
                return await intr.response.send_message(":x: I couldn't find that clan. Please try again with the tag.")
            clan_tag = fetch['clan_tag']

        result = await self.bot.pool.fetchrow("UPDATE clans SET emoji = $1 WHERE clan_tag = $2 AND guild_id = $3 RETURNING clan_tag", str(emoji_id), clan_tag, intr.guild_id)
        if result:
            await intr.response.send_message("👌 Emoji added successfully.")
        else:
            await intr.response.send_message("That clan has not been added. Try adding it and try again.")

    @add_group.command(name='discord', description="Link a clash account to your discord account")
    @app_commands.describe(player="A player name or #tag", user="The user to link the player to.")
    async def add_discord(self, intr: discord.Interaction, player: str, user: discord.Member):
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
        user = user or intr.user

        if not coc.utils.is_valid_tag(player):
            fetch = await self.bot.pool.fetchrow("SELECT DISTINCT player_tag FROM players WHERE player_name LIKE $1", player)
            if not fetch:
                return await intr.response.send_message(
                    f"{player} is not a valid player tag, and "
                    f"I couldn't find a player with that name in my database. Ensure their clan is added and try again."
                )
            player = fetch['player_tag']

        season_id = await self.bot.seasonconfig.get_season_id()
        existing = await self.bot.links.get_link(player)
        if existing is not None:
            member = intr.guild.get_member(existing) or self.bot.get_user(existing) or await self.bot.fetch_user(existing) or existing
            return await intr.response.send_message(f"Sorry, {player} has already been added by {member}. You can try removing and re-adding their link.")

        await self.bot.pool.execute("UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3", user.id, player, season_id)
        await self.bot.links.add_link(player, user.id)
        await intr.response.send_message(f"👌 Player successfully added.")

    # @add.command(name='multidiscord', aliases=['multi_discord', 'multiclaim', 'multi_claim', 'multilink', 'multi_link'])
    # async def add_multi_discord(self, ctx, user: discord.Member, *players: str):
    #     """Helper command to link many clash accounts to a user's discord.
    #
    #     **Parameters**
    #     :key: A discord user (mention etc.)
    #     :key: Player tags OR names
    #
    #     **Format**
    #     :information_source: `+add discord @MENTION #PLAYER_TAG #PLAYER_TAG2 #PLAYER_TAG3`
    #     :information_source: `+add discord @MENTION PLAYERNAME PLAYERNAME2 PLAYERNAME3`
    #
    #     **Example**
    #     :white_check_mark: `+add discord @mathsman #P0LYJC8C #C0LLJC8 #P0CC8JY`
    #     :white_check_mark: `+add discord @mathsman mathsman raptor217 johnny36`
    #     """
    #     for n in players:
    #         # TODO: fix this
    #         await ctx.invoke(self.add_discord, user=user, player=n)
    #
    async def do_add_board(self, intr: discord.Interaction, channel: discord.TextChannel, type_, invoked_from_command=True):
        if channel and invoked_from_command:
            fetch = await self.bot.pool.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                log.info('+add %sboard with a non-board channel', type_)
                await intr.response.send_message(
                    ":x: I cannot setup a board here, "
                    "because the bot didn't create the channel! Try again with `+add boards`."
                )
                return
            if any(n['type'] == type_ for n in fetch):
                log.info('+add %sboard with a an existing legend board channel', type_)
                await intr.response.send_message(f":x: A {type_}board is already setup here.")
                return

        elif not channel:
            me = intr.guild.get_member(intr.client.user.id)
            if not me.guild_permissions.manage_channels:
                log.info('+add %sboard no create channel permissions', type_)
                await intr.response.send_message(f':x: I need manage channels permission to create your {type_}board channel!')
                return

            overwrites = {
                me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                read_message_history=True, embed_links=True,
                                                manage_messages=True, add_reactions=True),
                intr.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                     send_messages=False,
                                                                     read_message_history=True)
            }
            try:
                channel = await intr.guild.create_text_channel(name="dt-boards",
                                                               overwrites=overwrites,
                                                               reason=f'{intr.user} created a boards channel.')
            except discord.Forbidden:
                log.info('+add %sboard no channel permissions (HTTP exception caught)', type_)
                await intr.response.send_message(f':x: I do not have permissions to create the {type_}board channel.')
                return
            except discord.HTTPException:
                log.info('+add %sboard creating channel failed', type_)
                await intr.response.send_message(f':x: Creating the channel failed. Try checking the name?')
                return

        msg = await channel.send(BOARD_PLACEHOLDER.format(board=type_))

        for reaction in emojis[type_]:
            await msg.add_reaction(reaction)

        log.info('+add %sboard new log created, channel_id: %s, message_id: %s', type_, channel.id, msg.id)
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
        await self.bot.pool.execute(query, intr.guild_id, channel.id, msg.id, type_, titles[type_], default_sort_by[type_])
        await self.bot.donationboard.update_board(message_id=msg.id)
        await intr.response.send_message(
            f"👌 Your board channel: {channel} now has a registered {type_}board. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )
        return channel

    @add_group.command(name="boards", description="Convenient method to create a board channel, and setup donation and trophyboards in one command.")
    @app_commands.describe(clan_tag="The clan to add to the board.")
    @manage_guild()
    async def add_boards(self, intr: discord.Interaction, clan_tag: str):
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
        boards_channel = await self.do_add_board(intr, None, "donation", invoked_from_command=False)
        if not boards_channel:
            return  # we sent an error message already

        await self.do_add_board(intr, boards_channel, "trophy", invoked_from_command=False)
        f = await self.bot.pool.fetchrow('SELECT 1 FROM players INNER JOIN clans '
                                         'ON clans.clan_tag = players.clan_tag '
                                         'WHERE clans.guild_id = $1 AND players.season_id = $2 '
                                         'AND players.league_id = 29000022', intr.guild_id,
                                         await self.bot.seasonconfig.get_season_id())
        if f:
            await self.do_add_board(intr, boards_channel, "legend", invoked_from_command=False)
            await boards_channel.send(
                f"I've noticed you have legend players added in your server, so I added a legend board. "
                f"If this board was added in error, please delete the Placeholder message above.\n\n"
                f"At the end of each day at 5AM GMT, the bot will reset the legend board. "
                f'If you wish for the bot to post a log of the board each day in a different channel '
                f'before resetting it, please use `+add legendlog #{boards_channel} #logs-channel`.\n\n'
                f'Feel free to delete this message.'
            )

        await self.add_clan(intr, channel=boards_channel, clan_tag=clan_tag)

    @add_group.command(name="trophyboard", description="Registers a trophy-board to the channel, or creates a new channel for you.")
    @app_commands.describe(channel="Channel to add the board to.")
    @manage_guild()
    async def add_trophyboard(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_add_board(intr, channel, "trophy", invoked_from_command=True)

    @add_group.command(name='donationboard', description="Registers a donation-board to the channel, or creates a new channel for you.")
    @app_commands.describe(channel="Channel to add the board to.")
    @manage_guild()
    async def add_donationboard(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_add_board(intr, channel, "donation", invoked_from_command=True)

    @add_group.command(name='legendboard', description="Create a legend board for your server.")
    @app_commands.describe(channel="Channel to add the board to.")
    @manage_guild()
    async def add_legendboard(self, intr: discord.Interaction, channel: discord.TextChannel):
        """Create a legend board for your server.

        This is a mini-board (like a donation or trophyboard) that will update when legend players attack,
        archiving itself at the end of the day and sending a new board for the next legend day.

        **Parameters**
        :key: Discord channel (mention etc.)

        **Format**
        :information_source: `+add legendboard #CHANNEL`

        **Example**
        :white_check_mark: `+add legendboard #logging`

        **Required Permissions**
        :warning: Manage Server
        """
        board = await self.do_add_board(intr, channel, "legend", invoked_from_command=True)
        if board:
            await board.send(f'At the end of each day at 5AM GMT, the bot will reset the legend board. '
                             f'If you wish for the bot to post a log of the board each day in a different channel '
                             f'before resetting it, please use `+add legendlog #{channel} #logs-channel`.\n\n'
                             f'Feel free to delete this message.')
    #
    # @add.command(name='warboard', disabled=True)
    # @manage_guild()
    # async def add_warboard(self, ctx, channel: discord.TextChannel = None):
    #     """Create a war board for your server.
    #
    #     **Parameters**
    #     :key: Discord channel (mention etc.)
    #
    #     **Format**
    #     :information_source: `+add warboard #CHANNEL`
    #
    #     **Example**
    #     :white_check_mark: `+add warboard #logging`
    #
    #     **Required Permissions**
    #     :warning: Manage Server
    #     """
    #     await self.do_add_board(ctx, channel, "war", invoked_from_command=True)
    #
    async def do_log_add(self, intr: discord.Interaction, channel: discord.TextChannel, type_: str):
        if await self.bot.pool.fetchrow("SELECT id FROM boards WHERE channel_id=$1", channel.id):
            return await intr.response.send_message('You can\'t have the same channel for a board and log!')

        perms = channel.permissions_for(intr.guild.get_member(self.bot.user.id))
        if not (perms.send_messages or perms.read_messages):
            return await intr.response.send_message('I need permission to send and read messages here!')

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
        await self.bot.pool.execute(query, channel.guild.id, channel.id, type_)

        # prompt = await ctx.prompt(f'Would you like me to add all clans claimed on the server to this {type_}log?\n'
        #                           f'Else you can manually add clans with `+add clan #CLAN_TAG` to this channel.\n')
        # if not prompt:
        return await intr.response.send_message(f'{channel.mention} has been added as a {type_}log channel.\n'
                              f'Please note that only clans claimed to {channel.mention} will appear in this log.')

        query = """INSERT INTO clans (
                            clan_tag,
                            guild_id,
                            channel_id,
                            clan_name,
                            in_event,
                            fake_clan
                            )
                   SELECT
                        clan_tag,
                        guild_id,
                        $2,
                        clan_name,
                        in_event,
                        fake_clan

                   FROM clans
                   WHERE guild_id = $1
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, channel.guild.id, channel.id)
        return await intr.response.send_message(f'{channel.mention} has been added as a {type_}log channel. '
                              'See all clans claimed with `+info clans`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @add_group.command(name='donationlog', description="Create a donation log for your server.")
    @app_commands.describe(channel="The #channel to add the log to.")
    @manage_guild()
    async def add_donationlog(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_log_add(intr, channel or intr.channel, "donation")
        await intr.response.send_message("Want a detailed donation log? Try the `+edit donationlog style` command.")

    @add_group.command(name='trophylog', description="Create a trophy log for your server.")
    @app_commands.describe(channel="The #channel to add the log to.")
    @manage_guild()
    async def add_trophylog(self, intr: discord.Interaction, channel: discord.TextChannel):
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
        await self.do_log_add(intr, channel or intr.channel, "trophy")

    @add_group.command(name='legendlog', description="Add a channel where legend board logs are sent at the end of each legend day.")
    @app_commands.describe(board_channel="The channel the legendboard is located in.", log_channel="The #channel to add the log to.")
    async def edit_legendboard_logs(self, intr: discord.Interaction, board_channel: discord.TextChannel, log_channel: discord.TextChannel):
        """Add a channel where legend board logs are sent at the end of each legend day.

        It is suggested to make this channel different from #dt-boards, in order to improve readability of other boards.

        The bot must have `Send Messages` and `Attach Files` permissions in this channel.

        **Parameters**
        :key: A channel where the legendboard is located (#mention).
        :key: A channel where you wish to divert logs (#mention).

        **Format**
        :information_source: `+add legendlog #BOARD-CHANNEL #LOG-CHANNEL`

        **Example**
        :white_check_mark: `+add legendlog #legend-boards #legend-logs`
        :white_check_mark: `+add legendlog #dt-boards #legend-archives`

        **Required Permissions**
        :warning: Manage Server
        """
        async def validate_channel(id_):
            return await self.bot.pool.fetchrow('SELECT id FROM boards WHERE channel_id = $1 AND type = $2', id_, 'legend')

        if board_channel and log_channel:
            channels = [board_channel, log_channel]
        elif board_channel:
            channels = [board_channel, intr.channel]
        elif log_channel:
            channels = [intr.channel, log_channel]
        else:
            return await intr.response.send_message("I only expected 2 channels in your command: the board channel and the log channel. Please try again.")

        for channel in channels:
            if await validate_channel(channel.id):
                b_channel = channel
                channels.remove(channel)
                break
        else:
            return await intr.response.send_message("I expected 2 channels in your command: the board channel and the log channel, "
                                  "and couldn't find the board channel. Please try again.")

        if not channels:
            l_channel = b_channel
        else:
            l_channel = channels[0]

        perms = l_channel.permissions_for(intr.guild.get_member(self.bot.user.id))
        if not perms.send_messages and perms.read_messages and perms.attach_files:
            return await intr.response.send_message(f"I need permission to send and read messages, and attach files in {l_channel.mention}. Please try again.")

        query = "UPDATE boards SET divert_to_channel_id = $1 WHERE channel_id = $2 AND type = 'legend'"
        await self.bot.pool.execute(query, l_channel.id, b_channel.id)
        await intr.response.send_message(f":white_check_mark: Legend board logs will now be diverted to {l_channel.mention}.")

    @app_commands.command(description="Verify your clash account in order to add clans to the bot.")
    @app_commands.describe(player_tag="Your player #tag", token="Your player API token")
    async def verify(self, intr: discord.Interaction, player_tag: str, token: str):
        """Verify your clash account in order to add clans to the bot.

        This uses the in-game API token to verify your ownership.

        **Parameters**
        :key: You player tag or name.

        **Format**
        :information_source: `+verify #PLAYERTAG`
        :information_source: `+verify Player Name`

        **Example**
        :white_check_mark: `+verify showtags`
        :white_check_mark: `+verify #JY9J2Y99`
        """
        resp = await self.bot.coc.verify_player_token(player_tag, token)
        if resp is True:
            await self.bot.pool.execute(
                "INSERT INTO players (player_tag, user_id, season_id, verified) VALUES ($1, $2, $3, True)"
                "ON CONFLICT (player_tag, season_id) DO UPDATE SET verified = True, user_id = $2",
                player_tag,
                intr.user.id,
                await self.bot.seasonconfig.get_season_id()
            )
            await self.bot.links.delete_link(player_tag)
            await self.bot.links.add_link(player_tag, intr.user.id)
            await intr.response.send_message(f"👌 Player successfully verified.")
        else:
            await intr.response.send_message("Sorry, that token wasn't correct. Please run the command again. For additional help with player tokens, see the below:\n\n"
                                             "To find your player API token, please follow these steps:\n"
                                             "1. Go in-game and ensure the account is the one you're trying to verify\n"
                                             "2. Go to the 'Settings' tab and click 'More Settings' in the bottom-right\n"
                                             "3. Scroll to the bottom of that page, and click the 'Show' button next to 'API Token'.\n"
                                             "4. Click it again top 'Copy' the 8-character code.\n"
                                             "5. Run this command again.\n"
                                             "https://cdn.discordapp.com/attachments/681438398455742536/766911636375601162/PSX_20201017_1731392.jpg"
                                             )

    # @commands.group(invoke_without_command=True)
    # async def fakeclan(self, ctx):
    #     """[Group] Make a "FakeClan" that is comprised of members you want; independant of any real clash of clans clan.
    #
    #     This may be a niche feature, but is helpful for those running competitions and leaderboards between a few
    #     members of their clan, and/or over a few clans, but don't want the noise of those not involved to appear.
    #
    #     A fake clan works in exactly the same way as a normal clan - once you set it up you use the FakeClan ID
    #     (a 6-digit number) instead of the clan tag. For example, `+add boards 123456` will create leaderboards for your
    #     fake clan, provided your ID is 123456.
    #
    #     You can add, remove or list fake clans and their members.
    #     """
    #     await ctx.send_help(ctx.command)
    #
    # @fakeclan.command(name="create", aliases=["add", "make"])
    # async def fakeclan_create(self, ctx, *player_tags: str):
    #     """Create a "FakeClan" that is comprised of members you want; independant of any real clash of clans clan.
    #
    #     This may be a niche feature, but is helpful for those running competitions and leaderboards between a few
    #     members of their clan, and/or over a few clans, but don't want the noise of those not involved to appear.
    #
    #     A fake clan works in exactly the same way as a normal clan - once you set it up you use the FakeClan ID
    #     (a 6-digit number) instead of the clan tag. For example, `+add boards 123456` will create leaderboards for your
    #     fake clan, provided your ID is 123456.
    #
    #     If you run this command in the same channel as where an existing FakeClan has been created, it will add more players
    #     to that FakeClan.
    #
    #     **Parameters**
    #     :key: A list of player tags, seperated by a space.
    #
    #     **Format**
    #     :information_source: `+fakeclan create #PLAYERTAG #PLAYERTAG2 #PLAYERTAG3 #PLAYERTAG4`
    #
    #     **Example**
    #     :white_check_mark: `+fakeclan create #JY9J2Y99 #2PP #2PL`
    #     """
    #     valid_tags = [coc.utils.correct_tag(tag) for tag in player_tags if coc.utils.is_valid_tag(tag)]
    #     if not valid_tags:
    #         return await ctx.send("I couldn't find any valid #player tags from your message. Please try again.")
    #
    #     clan_id = discord.utils.find(lambda tag: tag and tag.strip().isdigit(), player_tags)
    #     if clan_id:
    #         clan_id = clan_id.strip()
    #     else:
    #         query = "SELECT clan_tag FROM clans WHERE channel_id = $1 AND fake_clan = True"
    #         fetch = await ctx.db.fetchrow(query, ctx.channel.id)
    #         clan_id = fetch and fetch['clan_tag']
    #
    #     if not clan_id:
    #         query = "INSERT INTO clans (channel_id, guild_id, clan_tag, fake_clan) VALUES ($1, $2, $3, True)"
    #         clan_id = str(ctx.channel.id)[-6:]
    #         await ctx.db.execute(query, ctx.channel.id, ctx.guild.id, clan_id)
    #
    #     query = "UPDATE players SET fake_clan_tag = $1 WHERE player_tag = ANY($2::TEXT[]) AND season_id = $3 RETURNING 1"
    #     result = await ctx.db.fetch(query, clan_id, valid_tags, await self.bot.seasonconfig.get_season_id())
    #     if not result:
    #         return await ctx.send("Those players weren't in my database. "
    #                               "Try adding the clans that they're in first, and try again.")
    #
    #     await ctx.send(f"I've added {len(result)} players to your FakeClan ID: {clan_id}.")
    #     await ctx.invoke(self.fakeclan_list, clan_id=clan_id)
    #
    # @fakeclan.command(name="remove", aliases=["delete"])
    # async def makeclan_remove(self, ctx, *player_tags: str):
    #     """Remove members from a "FakeClan". It will use the FakeClan added to the current channel.
    #
    #     **Parameters**
    #     :key: A list of player tags, seperated by a space.
    #
    #     **Format**
    #     :information_source: `+fakeclan remove #PLAYERTAG #PLAYERTAG2 #PLAYERTAG3 #PLAYERTAG4`
    #
    #     **Example**
    #     :white_check_mark: `+fakeclan remove #JY9J2Y99 #2PP #2PL`
    #     """
    #     valid_tags = [coc.utils.correct_tag(tag) for tag in player_tags if coc.utils.is_valid_tag(tag)]
    #     if not valid_tags:
    #         return await ctx.send("I couldn't find any valid #player tags from your message. Please try again.")
    #
    #     clan_id = discord.utils.find(lambda tag: tag and tag.strip().isdigit(), player_tags)
    #     if clan_id:
    #         clan_id = clan_id.strip()
    #     else:
    #         query = "SELECT clan_tag FROM clans WHERE channel_id = $1 AND fake_clan = True"
    #         fetch = await ctx.db.fetchrow(query, ctx.channel.id)
    #         clan_id = fetch and fetch['clan_tag']
    #
    #     if not clan_id:
    #         return await ctx.send("I couldn't find a FakeClan setup in this channel. Use `+help fakeclan` for more info.")
    #
    #     query = "UPDATE players SET fake_clan_tag = null WHERE player_tag = ANY($1::TEXT[]) AND season_id = $2 RETURNING 1"
    #     result = await ctx.db.fetch(query, valid_tags, await self.bot.seasonconfig.get_season_id())
    #
    #     await ctx.send(f"I've removed {len(result)} from your FakeClan ID: {clan_id}.")
    #     await ctx.invoke(self.fakeclan_list, clan_id=clan_id)
    #
    # @fakeclan.command(name="list", aliases=["show"])
    # async def fakeclan_list(self, ctx, clan_id: str = ""):
    #     """List all members added to a "FakeClan" in the current channel.
    #
    #     **Format**
    #     :information_source: `+makeclan list`
    #
    #     **Example**
    #     :white_check_mark: `+makeclan list`
    #     """
    #     clan_id = clan_id.strip() if clan_id and clan_id.strip().isdigit() else None
    #     if not clan_id:
    #         query = "SELECT clan_tag FROM clans WHERE channel_id = $1 AND fake_clan = True"
    #         fetch = await ctx.db.fetchrow(query, ctx.channel.id)
    #         clan_id = fetch and fetch['clan_tag']
    #
    #     if not clan_id:
    #         return await ctx.send(
    #             "I couldn't find a FakeClan setup in this channel. Use `+help makeclan` for more info.")
    #
    #     query = "SELECT player_tag, player_name FROM players WHERE fake_clan_tag = $1 AND season_id = $2"
    #     fetch = await ctx.db.fetch(query, clan_id, await self.bot.seasonconfig.get_season_id())
    #     if not fetch:
    #         return await ctx.send(f"I couldn't find any players added to the fake clan with ID {clan_id} fake clan.")
    #
    #     title = f"FakeClan Members: {clan_id}"
    #
    #     data = sorted(((p['player_name'], p['player_tag'], "") for p in fetch), key=lambda p: p[1], reverse=True)
    #
    #     p = StatsAccountsPaginator(ctx, data=data, page_count=math.ceil(len(fetch) / 20), title=title)
    #     await p.paginate()

    # @add.command(name="event")
    # @checks.manage_guild()
    # async def add_event(self, ctx, *, event_name: str = None):
    #     """Allows user to add a new trophy push event. Trophy Push events override season statistics for trophy
    #     counts.
    #
    #     This command is interactive and will ask you questions about the new event. After the initial command,
    #     the bot will ask you further questions about the event.
    #
    #     **Parameters**
    #     :key: Name of the event
    #
    #     **Format**
    #     :information_source: `+add event EVENT NAME`
    #
    #     **Example**
    #     :white_check_mark: `+add event Donation Bot Event`
    #
    #     **Required Permissions**
    #     :warning: Manage Server
    #     """
    #     if ctx.config:
    #         if ctx.config.start > datetime.datetime.now():
    #             return await ctx.send(f'This server is already set up for {ctx.config.event_name}. Please use '
    #                                   f'`+remove event` if you would like to remove this event and create a new one.')
    #
    #     def check_author(m):
    #         return m.author == ctx.author
    #
    #     if not event_name:
    #         try:
    #             await ctx.send('Please enter the name of the new event.')
    #             response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #             event_name = response.content
    #         except asyncio.TimeoutError:
    #             return await ctx.send('I can\'t wait all day. Try again later.')
    #
    #     for i in range(5):
    #         try:
    #             await ctx.send(f'What date does the {event_name} begin?  (YYYY-MM-DD)')
    #             response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #             start_date = await DateConverter().convert(ctx, response.clean_content)
    #             break
    #         except (ValueError, commands.BadArgument):
    #             await ctx.send('Date must be in the YYYY-MM-DD format.')
    #         except asyncio.TimeoutError:
    #             return await ctx.send('Yawn! Time\'s up. You\'re going to have to start over some other time.')
    #     else:
    #         return await ctx.send(
    #             'I don\'t really know what happened, but I can\'t figure out what the start '
    #             'date is. Please start over and let\'s see what happens')
    #
    #     try:
    #         await ctx.send('And what time does this fantastic event begin? (Please provide HH:MM in UTC)')
    #         response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #         hour, minute = map(int, response.content.split(':'))
    #         if hour < 13:
    #             try:
    #                 await ctx.send('And is that AM or PM?')
    #                 response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #                 if response.content.lower() == 'pm':
    #                     hour += 12
    #             except asyncio.TimeoutError:
    #                 if hour < 6:
    #                     await ctx.send('Well I\'ll just go with PM then.')
    #                     hour += 12
    #                 else:
    #                     await ctx.send('I\'m going to assume you want AM.')
    #         start_time = datetime.time(hour, minute)
    #     except asyncio.TimeoutError:
    #         return await ctx.send('I was asking for time, but you ran out of it. You\'ll have to start over again.')
    #
    #     event_start = datetime.datetime.combine(start_date, start_time)
    #
    #     try:
    #         await ctx.send('What is the end date for the event? (YYYY-MM-DD)')
    #         response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #         year, month, day = map(int, response.content.split('-'))
    #         end_date = datetime.date(year, month, day)
    #     except asyncio.TimeoutError:
    #         return await ctx.send('I can\'t wait all day. Try again later.')
    #
    #     answer = await ctx.prompt('Does the event end at the same time of day?')
    #     if answer:
    #         end_time = start_time
    #     elif answer is None:
    #         end_time = start_time
    #         await ctx.send('You must have fallen asleep. I\'ll just set the end time to match the start time.')
    #     else:
    #         try:
    #             await ctx.send('What time does the event end? (Please provide HH:MM in UTC)')
    #             response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #             hour, minute = map(int, response.content.split(':'))
    #             end_time = datetime.time(hour, minute)
    #         except asyncio.TimeoutError:
    #             end_time = start_time
    #             await ctx.send('You must have fallen asleep. I\'ll just set the end time to match the start time.')
    #
    #     event_end = datetime.datetime.combine(end_date, end_time)
    #
    #     try:
    #         await ctx.send('Which #channel do you want me to send updates '
    #                        '(event starting, ending, records broken etc.) to?')
    #         response = await ctx.bot.wait_for('message', check=check_author, timeout=60.0)
    #         try:
    #             channel = await commands.TextChannelConverter().convert(ctx, response.content)
    #         except commands.BadArgument:
    #             return await ctx.send('Uh oh.. I didn\'t like that channel! '
    #                                   'Try the command again with a channel # mention or ID.')
    #     except asyncio.TimeoutError:
    #         return await ctx.send('I can\'t wait all day. Try again later.')
    #
    #     query = 'INSERT INTO events (guild_id, event_name, start, finish, channel_id) VALUES ($1, $2, $3, $4, $5) RETURNING id'
    #     event_id = await ctx.db.fetchrow(query, ctx.guild.id, event_name, event_start, event_end, channel.id)
    #     log.info(f"{event_name} added to events table for {ctx.guild} by {ctx.author}")
    #
    #     query = 'UPDATE clans SET in_event = True WHERE guild_id = $1'
    #     await ctx.db.execute(query, ctx.guild.id)
    #
    #     fmt = (f'**Event Created:**\n\n{event_name}\n{event_start.strftime("%d %b %Y %H:%M")}\n'
    #            f'{event_end.strftime("%d %b %Y %H:%M")}\n\nEnjoy your event!')
    #     e = discord.Embed(colour=discord.Colour.green(),
    #                       description=fmt)
    #     await ctx.send(embed=e)
    #     self.bot.dispatch('event_register')


async def setup(bot):
    await bot.add_cog(Add(bot))
