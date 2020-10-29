import discord
import asyncio
import typing
import datetime
import re
import coc
import logging

from discord.ext import commands
from cogs.utils.checks import requires_config, manage_guild, helper_check
from cogs.utils.converters import PlayerConverter, DateConverter, TextChannel
from cogs.utils import checks

RCS_GUILD_ID = 295287647075827723

log = logging.getLogger(__name__)

url_validator = re.compile(r"^(?:http(s)?://)?[\w.-]+(?:.[\w.-]+)+[\w\-_~:/?#[\]@!$&'()*+,;=.]+"
                           r"(.jpg|.jpeg|.png|.gif)+[\w\-_~:/?#[\]@!$&'()*+,;=.]*$")
unicode_emoji = re.compile(
    "(?:\U0001f1e6[\U0001f1e8-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f2\U0001f1f4\U0001f1f6-\U0001f1fa\U0001f1fc\U0001f1fd\U0001f1ff])|(?:\U0001f1e7[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ef\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1e8[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ee\U0001f1f0-\U0001f1f5\U0001f1f7\U0001f1fa-\U0001f1ff])|(?:\U0001f1e9[\U0001f1ea\U0001f1ec\U0001f1ef\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1ff])|(?:\U0001f1ea[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ed\U0001f1f7-\U0001f1fa])|(?:\U0001f1eb[\U0001f1ee-\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1f7])|(?:\U0001f1ec[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ee\U0001f1f1-\U0001f1f3\U0001f1f5-\U0001f1fa\U0001f1fc\U0001f1fe])|(?:\U0001f1ed[\U0001f1f0\U0001f1f2\U0001f1f3\U0001f1f7\U0001f1f9\U0001f1fa])|(?:\U0001f1ee[\U0001f1e8-\U0001f1ea\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9])|(?:\U0001f1ef[\U0001f1ea\U0001f1f2\U0001f1f4\U0001f1f5])|(?:\U0001f1f0[\U0001f1ea\U0001f1ec-\U0001f1ee\U0001f1f2\U0001f1f3\U0001f1f5\U0001f1f7\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1f1[\U0001f1e6-\U0001f1e8\U0001f1ee\U0001f1f0\U0001f1f7-\U0001f1fb\U0001f1fe])|(?:\U0001f1f2[\U0001f1e6\U0001f1e8-\U0001f1ed\U0001f1f0-\U0001f1ff])|(?:\U0001f1f3[\U0001f1e6\U0001f1e8\U0001f1ea-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f4\U0001f1f5\U0001f1f7\U0001f1fa\U0001f1ff])|\U0001f1f4\U0001f1f2|(?:\U0001f1f4[\U0001f1f2])|(?:\U0001f1f5[\U0001f1e6\U0001f1ea-\U0001f1ed\U0001f1f0-\U0001f1f3\U0001f1f7-\U0001f1f9\U0001f1fc\U0001f1fe])|\U0001f1f6\U0001f1e6|(?:\U0001f1f6[\U0001f1e6])|(?:\U0001f1f7[\U0001f1ea\U0001f1f4\U0001f1f8\U0001f1fa\U0001f1fc])|(?:\U0001f1f8[\U0001f1e6-\U0001f1ea\U0001f1ec-\U0001f1f4\U0001f1f7-\U0001f1f9\U0001f1fb\U0001f1fd-\U0001f1ff])|(?:\U0001f1f9[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ed\U0001f1ef-\U0001f1f4\U0001f1f7\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1ff])|(?:\U0001f1fa[\U0001f1e6\U0001f1ec\U0001f1f2\U0001f1f8\U0001f1fe\U0001f1ff])|(?:\U0001f1fb[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ee\U0001f1f3\U0001f1fa])|(?:\U0001f1fc[\U0001f1eb\U0001f1f8])|\U0001f1fd\U0001f1f0|(?:\U0001f1fd[\U0001f1f0])|(?:\U0001f1fe[\U0001f1ea\U0001f1f9])|(?:\U0001f1ff[\U0001f1e6\U0001f1f2\U0001f1fc])|(?:\U0001f3f3\ufe0f\u200d\U0001f308)|(?:\U0001f441\u200d\U0001f5e8)|(?:[\U0001f468\U0001f469]\u200d\u2764\ufe0f\u200d(?:\U0001f48b\u200d)?[\U0001f468\U0001f469])|(?:(?:(?:\U0001f468\u200d[\U0001f468\U0001f469])|(?:\U0001f469\u200d\U0001f469))(?:(?:\u200d\U0001f467(?:\u200d[\U0001f467\U0001f466])?)|(?:\u200d\U0001f466\u200d\U0001f466)))|(?:(?:(?:\U0001f468\u200d\U0001f468)|(?:\U0001f469\u200d\U0001f469))\u200d\U0001f466)|[\u2194-\u2199]|[\u23e9-\u23f3]|[\u23f8-\u23fa]|[\u25fb-\u25fe]|[\u2600-\u2604]|[\u2638-\u263a]|[\u2648-\u2653]|[\u2692-\u2694]|[\u26f0-\u26f5]|[\u26f7-\u26fa]|[\u2708-\u270d]|[\u2753-\u2755]|[\u2795-\u2797]|[\u2b05-\u2b07]|[\U0001f191-\U0001f19a]|[\U0001f1e6-\U0001f1ff]|[\U0001f232-\U0001f23a]|[\U0001f300-\U0001f321]|[\U0001f324-\U0001f393]|[\U0001f399-\U0001f39b]|[\U0001f39e-\U0001f3f0]|[\U0001f3f3-\U0001f3f5]|[\U0001f3f7-\U0001f3fa]|[\U0001f400-\U0001f4fd]|[\U0001f4ff-\U0001f53d]|[\U0001f549-\U0001f54e]|[\U0001f550-\U0001f567]|[\U0001f573-\U0001f57a]|[\U0001f58a-\U0001f58d]|[\U0001f5c2-\U0001f5c4]|[\U0001f5d1-\U0001f5d3]|[\U0001f5dc-\U0001f5de]|[\U0001f5fa-\U0001f64f]|[\U0001f680-\U0001f6c5]|[\U0001f6cb-\U0001f6d2]|[\U0001f6e0-\U0001f6e5]|[\U0001f6f3-\U0001f6f6]|[\U0001f910-\U0001f91e]|[\U0001f920-\U0001f927]|[\U0001f933-\U0001f93a]|[\U0001f93c-\U0001f93e]|[\U0001f940-\U0001f945]|[\U0001f947-\U0001f94b]|[\U0001f950-\U0001f95e]|[\U0001f980-\U0001f991]|\u00a9|\u00ae|\u203c|\u2049|\u2122|\u2139|\u21a9|\u21aa|\u231a|\u231b|\u2328|\u23cf|\u24c2|\u25aa|\u25ab|\u25b6|\u25c0|\u260e|\u2611|\u2614|\u2615|\u2618|\u261d|\u2620|\u2622|\u2623|\u2626|\u262a|\u262e|\u262f|\u2660|\u2663|\u2665|\u2666|\u2668|\u267b|\u267f|\u2696|\u2697|\u2699|\u269b|\u269c|\u26a0|\u26a1|\u26aa|\u26ab|\u26b0|\u26b1|\u26bd|\u26be|\u26c4|\u26c5|\u26c8|\u26ce|\u26cf|\u26d1|\u26d3|\u26d4|\u26e9|\u26ea|\u26fd|\u2702|\u2705|\u270f|\u2712|\u2714|\u2716|\u271d|\u2721|\u2728|\u2733|\u2734|\u2744|\u2747|\u274c|\u274e|\u2757|\u2763|\u2764|\u27a1|\u27b0|\u27bf|\u2934|\u2935|\u2b1b|\u2b1c|\u2b50|\u2b55|\u3030|\u303d|\u3297|\u3299|\U0001f004|\U0001f0cf|\U0001f170|\U0001f171|\U0001f17e|\U0001f17f|\U0001f18e|\U0001f201|\U0001f202|\U0001f21a|\U0001f22f|\U0001f250|\U0001f251|\U0001f396|\U0001f397|\U0001f56f|\U0001f570|\U0001f587|\U0001f590|\U0001f595|\U0001f596|\U0001f5a4|\U0001f5a5|\U0001f5a8|\U0001f5b1|\U0001f5b2|\U0001f5bc|\U0001f5e1|\U0001f5e3|\U0001f5e8|\U0001f5ef|\U0001f5f3|\U0001f6e9|\U0001f6eb|\U0001f6ec|\U0001f6f0|\U0001f930|\U0001f9c0|[#|0-9]\u20e3")
custom_emoji = re.compile("<(?P<animated>a?):(?P<name>[a-zA-Z0-9_]{2,32}):(?P<id>[0-9]{18,22})>")


BOARD_PLACEHOLDER = """
This is a Placeholder message for your {board} board.

Please don't delete this message, otherwise the board will be deleted.
This message should be replaced shortly by your {board} board.

If a board doesn't appear, please make sure you have `+add clan #clantag #dt-boards` properly, by using `+info`.
"""


class Add(commands.Cog):
    """Add clans, players, trophy and donationboards, logs and more."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group()
    async def add(self, ctx):
        """[Group] Allows the user to add a variety of features to the bot."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(ctx.command)

    @add.command(name='clan')
    @checks.manage_guild()
    async def add_clan(self, ctx, *, clan_tag: str, channel: str = None):
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
        if channel:
            pass  # it's been invoked from another command
        elif not ctx.message.channel_mentions:
            channel = ctx.channel
        elif len(ctx.message.channel_mentions) > 1:
            return await ctx.send("Please only mention 1 channel.")
        else:
            channel = ctx.message.channel_mentions[0]

        clan_tag = coc.utils.correct_tag(clan_tag.replace(channel.mention, "").strip())
        if not coc.utils.is_valid_tag(clan_tag):
            return await ctx.send("That doesn't look like a proper clan tag. Please try again.")

        current = await ctx.db.fetch("SELECT DISTINCT clan_tag FROM clans WHERE guild_id = $1 AND clan_tag != $2", ctx.guild.id, clan_tag)
        if len(current) > 3 and not checks.is_patron_pred(ctx):
            return await ctx.send('You must be a patron to have more than 4 clans claimed per server. '
                                  'See more info with `+patron`, or join the support server for more help: '
                                  f'{self.bot.support_invite}')

        if await ctx.db.fetch("SELECT id FROM clans WHERE clan_tag = $1 AND channel_id = $2", clan_tag, channel.id):
            return await ctx.send('This clan has already been linked to the channel. Please try again.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag)
        except coc.NotFound:
            return await ctx.send(f'Clan not found with `{clan_tag}` tag.')

        fetch = await ctx.db.fetch("SELECT player_tag FROM players WHERE user_id = $1 AND verified = True", ctx.author.id)
        members = [n for n in (clan.get_member(m['player_tag']) for m in fetch) if n]
        is_verified = any(member.role in (coc.Role.elder, coc.Role.co_leader, coc.Role.leader) for member in members)

        check = is_verified \
                or await self.bot.is_owner(ctx.author) \
                or clan_tag in (n['clan_tag'] for n in current) \
                or ctx.guild.id == RCS_GUILD_ID \
                or helper_check(self.bot, ctx.author) is True

        if not check and not fetch:
            return await ctx.send("Please verify your account before adding a clan: `+verify #playertag`. "
                                  "See `+help verify` for more information.\n\n"
                                  "This is a security feature of the bot to ensure you are an elder or above of the clan.")
        if not members and not check:
            return await ctx.send("Please ensure your verified account(s) are in the clan, and try again.")
        if members and not check:
            return await ctx.send("Your verified account(s) are not an elder or above. Please try again.")

        query = "INSERT INTO clans (clan_tag, guild_id, channel_id, clan_name) VALUES ($1, $2, $3, $4)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, channel.id, clan.name)

        season_id = await self.bot.seasonconfig.get_season_id()
        query = """INSERT INTO players (
                                        player_tag, 
                                        donations, 
                                        received, 
                                        trophies, 
                                        start_trophies, 
                                        season_id,
                                        start_update,
                                        clan_tag,
                                        player_name
                                        ) 
                    VALUES ($1,$2,$3,$4,$4,$5,True, $6, $7) 
                    ON CONFLICT (player_tag, season_id) 
                    DO UPDATE SET clan_tag = $6
                """
        async with ctx.db.transaction():
            for member in clan.members:
                await ctx.db.execute(query, member.tag, member.donations, member.received, member.trophies, season_id, clan.tag, member.name)

        await ctx.send(f"👌 {clan} ({clan.tag}) successfully added to {channel.mention}.")
        ctx.channel = channel  # modify for `on_clan_claim` listener
        self.bot.dispatch('clan_claim', ctx, clan)

    @add.command(name='emoji')
    @checks.manage_guild()
    async def add_emoji(self, ctx, *, clan: str, emoji: str = None):
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
        :white_check_mark: `+add player Reddit Elephino :elephino:`
        """
        custom = custom_emoji.search(clan)
        if not custom:
            unicode = unicode_emoji.search(clan)
            if not unicode:
                return await ctx.send("I couldn't find an emoji in your message!")

        if custom:
            emoji = self.bot.get_emoji(int(custom.group('id')))
            emoji_id = emoji.id
        else:
            emoji = unicode[0]
            emoji_id = emoji

        if not emoji:
            return await ctx.send(
                "It seems as though I don't have access to that emoji! Make sure it's on a server I share, and try again."
            )

        clan = clan.replace(str(emoji), "").strip()

        if coc.utils.is_valid_tag(coc.utils.correct_tag(clan)):
            clan_tag = coc.utils.correct_tag(clan)
        else:
            fetch = await ctx.db.fetchrow("SElECT clan_tag FROM clans WHERE clan_name LIKE $1 AND guild_id = $2", clan, ctx.guild.id)
            if not fetch:
                return await ctx.send("I couldn't find that clan. Please try again with the tag.")
            clan_tag = fetch['clan_tag']

        result = await ctx.db.fetchrow("UPDATE clans SET emoji = $1 WHERE clan_tag = $2 AND guild_id = $3 RETURNING clan_tag", str(emoji_id), clan_tag, ctx.guild.id)
        if result:
            await ctx.send("👌 Emoji added successfully.")
        else:
            await ctx.send("That clan has not been added. Try adding it and try again.")

    @add.command(name='discord', aliases=['claim', 'link'])
    async def add_discord(self, ctx, user: typing.Optional[discord.Member] = None, *, player: str):
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

        if not coc.utils.is_valid_tag(player):
            fetch = await ctx.db.fetchrow("SELECT DISTINCT player_tag FROM players WHERE player_name LIKE $1", player)
            if not fetch:
                return await ctx.send(
                    f"{player} is not a valid player tag, and "
                    f"I couldn't find a player with that name in my database. Ensure their clan is added and try again."
                )
            player = fetch['player_tag']

        season_id = await self.bot.seasonconfig.get_season_id()
        existing = await self.bot.links.get_link(player)
        if existing is not None:
            member = ctx.guild.get_member(existing) or self.bot.get_user(existing) or await self.bot.fetch_user(existing) or existing
            return await ctx.send(f"Sorry, {player} has already been added by {member}. You can try removing and re-adding their link.")

        await ctx.db.execute("UPDATE players SET user_id = $1 WHERE player_tag = $2 AND season_id = $3", user.id, player, season_id)
        await self.bot.links.add_link(player, user.id)
        await ctx.send(f"👌 Player successfully added.")

    @add.command(name='multidiscord', aliases=['multi_discord', 'multiclaim', 'multi_claim', 'multilink', 'multi_link'])
    async def add_multi_discord(self, ctx, user: discord.Member, *players: str):
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

    @add.command(name="boards", aliases=["board"])
    @manage_guild()
    async def add_boards(self, ctx, *clan_tags):
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
        if not ctx.me.guild_permissions.manage_channels:
            return await ctx.send('I need manage channels permission to create your board channel!')

        overwrites = {
            ctx.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                manage_messages=True
            ),
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                read_message_history=True)
        }
        reason = f'{str(ctx.author)} created a boards channel.'

        try:
            channel = await ctx.guild.create_text_channel(name="dt-boards", overwrites=overwrites, reason=reason)
        except discord.Forbidden:
            return await ctx.send(
                'I do not have permissions to create the boards channel.')
        except discord.HTTPException:
            return await ctx.send('Creating the channel failed. Try checking the name?')

        old_channel = ctx.channel
        for tag in clan_tags:
            await ctx.invoke(self.add_clan, channel=channel, clan_tag=tag)
        ctx.channel = old_channel  # add_clan modifies this so we need to revert it

        await ctx.invoke(self.add_donationboard, channel=channel, use_channel=True)
        await ctx.invoke(self.add_trophyboard, channel=channel, use_channel=True)
        # check if any legend players
        f = await ctx.db.fetchrow('SELECT players.id FROM players INNER JOIN clans '
                                  'ON clans.clan_tag = players.clan_tag '
                                  'WHERE clans.guild_id = $1 AND players.season_id = $2 '
                                  'AND players.league_id = 29000022', ctx.guild.id, await self.bot.seasonconfig.get_season_id())
        if f:
            await ctx.invoke(self.add_legendboard, channel=channel, use_channel=True)

    @add.command(name="trophyboard")
    @manage_guild()
    async def add_trophyboard(self, ctx, *, channel: discord.TextChannel = None, use_channel=False):
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
        if channel and not use_channel:
            fetch = await ctx.db.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                return await ctx.send(
                    "I cannot setup a board here, because the bot didn't create the channel! Try again with `+add boards`.")
            if any(n['type'] == 'trophy' for n in fetch):
                return await ctx.send("A trophyboard is already setup here.")

        elif not channel:
            if not ctx.me.guild_permissions.manage_channels:
                return await ctx.send(
                    'I need manage channels permission to create your board channel!'
                )

            overwrites = {
                ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    read_message_history=True, embed_links=True,
                                                    manage_messages=True),
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                    send_messages=False,
                                                                    read_message_history=True)
            }
            reason = f'{str(ctx.author)} created a boards channel.'

            try:
                channel = await ctx.guild.create_text_channel(name="dt-boards",
                                                              overwrites=overwrites,
                                                              reason=reason)
            except discord.Forbidden:
                return await ctx.send('I do not have permissions to create the trophyboard channel.')
            except discord.HTTPException:
                return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send(BOARD_PLACEHOLDER.format(board="trophy"))
        await msg.add_reaction("<:refresh:694395354841350254>")
        await msg.add_reaction("\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("<:gain:696280508933472256>")
        await msg.add_reaction("<:lastonline:696292732599271434>")
        await msg.add_reaction("<:historical:694812540290465832>")

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
        await ctx.db.execute(query, ctx.guild.id, channel.id, msg.id, 'trophy', "Trophy Leaderboard", 'trophies')
        await self.bot.donationboard.update_board(message_id=msg.id)
        await ctx.send(
            f"Your board channel: {channel} now has a registered trophyboard. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )

    @add.command(name='donationboard')
    @manage_guild()
    async def add_donationboard(self, ctx, *, channel: discord.TextChannel = None, use_channel=False):
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
        if channel and not use_channel:
            fetch = await ctx.db.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                return await ctx.send(
                    "I cannot setup a board here, because the bot didn't create the channel! Try again with `+add boards`.")
            if any(n['type'] == 'donation' for n in fetch):
                return await ctx.send("A donationboard is already setup here.")

        elif not channel:
            if not ctx.me.guild_permissions.manage_channels:
                return await ctx.send(
                    'I need manage channels permission to create your board channel!'
                )

            overwrites = {
                ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    read_message_history=True, embed_links=True,
                                                    manage_messages=True),
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                    send_messages=False,
                                                                    read_message_history=True)
            }
            reason = f'{str(ctx.author)} created a boards channel.'

            try:
                channel = await ctx.guild.create_text_channel(name="dt-boards",
                                                              overwrites=overwrites,
                                                              reason=reason)
            except discord.Forbidden:
                return await ctx.send(
                    'I do not have permissions to create the boards channel.')
            except discord.HTTPException:
                return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send(BOARD_PLACEHOLDER.format(board="donation"))
        await msg.add_reaction("<:refresh:694395354841350254>")
        await msg.add_reaction("\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("<:percent:694463772135260169>")
        await msg.add_reaction("<:lastonline:696292732599271434>")
        await msg.add_reaction("<:historical:694812540290465832>")

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
        await ctx.db.execute(query, ctx.guild.id, channel.id, msg.id, 'donation', "Donation Leaderboard", 'donations')
        await self.bot.donationboard.update_board(message_id=msg.id)
        await ctx.send(
            f"Your board channel: {channel} now has a registered donationboard. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )

    @add.command(name='legendboard')
    @manage_guild()
    async def add_legendboard(self, ctx, channel: discord.TextChannel = None, use_channel=False):
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
        if channel and not use_channel:
            fetch = await ctx.db.fetch("SELECT type FROM boards WHERE channel_id = $1", channel.id)
            if not fetch:
                log.info('+add legendboard with a non-board channel')
                return await ctx.send("I cannot setup a board here, because the bot didn't create the channel! "
                                      "Try again with `+add boards`.")
            if any(n['type'] == 'legend' for n in fetch):
                log.info('+add legendboard with a an existing legend board channel')
                return await ctx.send("A legend board is already setup here.")

        elif not channel:
            if not ctx.me.guild_permissions.manage_channels:
                log.info('+add legendboard no create channel permissions')
                return await ctx.send('I need manage channels permission to create your board channel!')

            overwrites = {
                ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                    read_message_history=True, embed_links=True,
                                                    manage_messages=True),
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True,
                                                                    send_messages=False,
                                                                    read_message_history=True)
            }
            reason = f'{str(ctx.author)} created a boards channel.'

            try:
                channel = await ctx.guild.create_text_channel(name="dt-boards", overwrites=overwrites, reason=reason)
            except discord.Forbidden:
                log.info('+add legendboard no channel permissions (HTTP exception caught)')
                return await ctx.send('I do not have permissions to create the boards channel.')
            except discord.HTTPException:
                log.info('+add legendboard creating channel failed')
                return await ctx.send('Creating the channel failed. Try checking the name?')

        msg = await channel.send(BOARD_PLACEHOLDER.format(board="legend"))
        await msg.add_reaction("<:refresh:694395354841350254>")
        await msg.add_reaction("\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f")
        await msg.add_reaction("\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f")

        log.info('+add legendlog new log created, channel_id: %s, message_id: %s', channel.id, msg.id)
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
        await ctx.db.execute(query, ctx.guild.id, channel.id, msg.id, 'legend', "Legend Leaderboard", 'finishing')
        await self.bot.donationboard.update_board(message_id=msg.id)

        await channel.send(f'At the end of the day, the bot will create a new legend board message '
                           f'and the old one will be archived. If you wish to divert these archived '
                           f'boards (recommended) to a different channel, please use '
                           f'`+edit legendboard logs #board-channel #log-channel`.')

        await ctx.send(
            f"Your board channel: {channel} now has a registered legendboard. "
            f"Please use `+info` to see which clans are registered, "
            f"and use `+add clan #{channel.name} #clantag` to add more clans."
        )

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

        query = """INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   SELECT 
                        clan_tag,
                        guild_id,
                        $2,
                        clan_name,
                        in_event

                   FROM clans
                   WHERE guild_id = $1
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a donationlog channel. '
                              'See all clans claimed with `+info clans`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @add.command(name='trophylog')
    @requires_config('trophylog', invalidate=True)
    @manage_guild()
    async def add_trophylog(self, ctx, channel: discord.TextChannel = None):
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

        query = """INSERT INTO clans (
                            clan_tag, 
                            guild_id, 
                            channel_id, 
                            clan_name, 
                            in_event
                            ) 
                   SELECT 
                        clan_tag,
                        guild_id,
                        $2,
                        clan_name,
                        in_event

                   FROM clans
                   WHERE guild_id = $1
                   ON CONFLICT (channel_id, clan_tag)
                   DO NOTHING;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id)
        return await ctx.send(f'{channel.mention} has been added as a trophylog channel. '
                              'See all clans claimed with `+info clans`. '
                              'Please note that only clans claimed to this channel will appear in the log.')

    @commands.command()
    async def verify(self, ctx, *, player_tag: str):
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
        if player_tag and coc.utils.is_valid_tag(coc.utils.correct_tag(player_tag)):
            tag = coc.utils.correct_tag(player_tag)
        else:
            fetch = await ctx.db.fetchrow("SELECT DISTINCT player_tag FROM players WHERE player_name LIKE $1", player_tag)
            if not fetch:
                return await ctx.send("I couldn't find that player - perhaps try their tag?")
            tag = fetch['player_tag']

        def check(m):
            return m.author.id == ctx.author.id and m.channel == ctx.channel
        await ctx.send("To find your player API token, please follow these steps:\n"
                       "1. Go in-game and ensure the account is the one you're trying to verify\n"
                       "2. Go to the 'Settings' tab and click 'More Settings' in the bottom-right\n"
                       "3. Scroll to the bottom of that page, and click the 'Show' button next to 'API Token'.\n"
                       "4. Click it again top 'Copy' the 8-character code.\n"
                       "5. Post it in this channel and I will verify it is correct.\n\nYou have 2 minutes before I time-out.\n"
                       "https://cdn.discordapp.com/attachments/681438398455742536/766911636375601162/PSX_20201017_1731392.jpg")
        try:
            message = await self.bot.wait_for("message", check=check, timeout=120.0)
        except asyncio.TimeoutError:
            return await ctx.send("You took too long. Please try again.")

        response = await self.bot.coc.http.request(coc.http.Route("POST", f"/players/{tag}/verifytoken", {}), json={"token": message.content.strip()})
        if response and response['status'] == "ok":
            await ctx.db.execute(
                "INSERT INTO players (player_tag, user_id, season_id, verified) VALUES ($1, $2, $3, True)"
                "ON CONFLICT (player_tag, season_id) DO UPDATE SET verified = True, user_id = $2",
                tag,
                ctx.author.id,
                await self.bot.seasonconfig.get_season_id()
            )
            await self.bot.links.delete_link(tag)
            await self.bot.links.add_link(tag, ctx.author.id)
            await ctx.send(f"👌 Player successfully verified.")
        else:
            await ctx.send("Sorry, that token wasn't correct. Please run the command again.")

def setup(bot):
    bot.add_cog(Add(bot))
