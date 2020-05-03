import coc
import discord
import logging
import re
import time

from datetime import datetime
from discord.ext import commands
from coc.utils import correct_tag

from cogs.utils.checks import is_patron_pred


tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")
activity_days_re = re.compile(r"\b\d*d$")
log = logging.getLogger(__name__)


class PlayerConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if isinstance(argument, coc.BasicPlayer):
            return argument

        tag = coc.utils.correct_tag(argument)
        name = argument.strip()

        if tag_validator.match(argument):
            try:
                return await ctx.coc.get_player(tag)
            except coc.NotFound:
                raise commands.BadArgument('I detected a player tag; and couldn\'t '
                                           'find an account with that tag! '
                                           'If you didn\'t pass in a tag, '
                                           'please drop the owner a message.'
                                           )
        guild_clans = await ctx.get_clans()
        for g in guild_clans:
            if g.name.lower() == name or g.tag == tag:
                raise commands.BadArgument(f'You appear to be passing '
                                           f'the clan tag/name for `{str(g)}`')

            clan_members = {n.name.lower(): n for n in g.itermembers}
            try:
                member = clan_members[name.lower()]
                return member
            except KeyError:
                pass

            member_by_tag = g.get_member(tag=tag)
            if member_by_tag:
                return member_by_tag

        raise commands.BadArgument(f"Invalid tag or IGN in "
                                   f"`{','.join(str(n) for n in guild_clans)}` clans.")


class ClanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if argument in ['all', 'guild', 'server'] or not argument:
            return await ctx.get_clans()
        if isinstance(argument, coc.BasicClan):
            return [argument]

        tag = coc.utils.correct_tag(argument)
        name = argument.strip().lower()

        if tag_validator.match(tag):
            try:
                clan = await ctx.coc.get_clan(tag)
            except coc.NotFound:
                raise commands.BadArgument(f'{tag} is not a valid clan tag.')

            if clan:
                return [clan]

            raise commands.BadArgument(f'{tag} is not a valid clan tag.')

        guild_clans = await ctx.get_clans()
        matches = [n for n in guild_clans if n.name.lower() == name or n.tag == tag]

        if not matches:
            raise commands.BadArgument(f'Clan name or tag `{argument}` not found')

        return matches


class AddClanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        clan = await ClanConverter().convert(ctx, argument)
        clan = clan[0]

        current_clans = await ctx.bot.get_clans(ctx.guild.id)
        if len(current_clans) > 3 and not is_patron_pred(ctx):
            raise commands.BadArgument(
                'You must be a patron to have more than 4 clans claimed per server. '
                'See more info with `+patron`, or join the support server for more help: '
                f'{ctx.bot.support_invite}'
            )

        check = clan.description.strip().endswith('dt') or await ctx.bot.is_owner(ctx.author) or clan.tag in (n.tag for n in current_clans)

        if not check:
            raise commands.BadArgument(
                'Please add the letters `dt` to the end of '
                f'`{clan.name}`\'s clan description. Wait 5 minutes and try again.'
                '\n\nThis is a security feature of the bot and should '
                'be removed once the clan has been added.\n'
                '<https://cdn.discordapp.com/attachments/'
                '605352421929123851/634226338852503552/Screenshot_20191017-140812.png>'
            )

        return clan


class DateConverter(commands.Converter):
    """Convert user input into standard format date (YYYY-MM-DD)"""

    async def convert(self, ctx, argument):
        error_msg = 'You may think that\'s a date, but I don\'t. Try using the DD-MM-YYYY format.'
        year_options = (f'{datetime.today().year}|{datetime.today().year + 1}|'
                        f'{str(datetime.today().year)[2:]}|{str(datetime.today().year + 1)[2:]}')

        # Check for text based month with day first
        pattern = (r'(?P<Date>\d{1,2})[/.\- ]'
                   r'(?P<Month>Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|Jun(e)?|'
                   r'Jul(y)?|Aug(ust)?|Sep(tember)?|Sept|Oct(ober)?|Nov(ember)?|Dec(ember)?)[/.\- ]'
                   r'(?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')[:3]} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %b %d'
            else:
                fmt = '%Y %b %d'

        # Check for text based month with month first
        pattern = (r'(?P<Month>Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|Jun(e)?|'
                   r'Jul(y)?|Aug(ust)?|Sep(tember)?|Sept|Oct(ober)?|Nov(ember)?|Dec(ember)?)[/.\- ]'
                   r'(?P<Date>\d{1,2})[/.\- ]'
                   r'(?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')[:3]} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %b %d'
            else:
                fmt = '%Y %b %d'

        # Check for YYYY-MM-DD
        pattern = (r'(?P<Year>' + year_options + r')[/.\- ](?P<Month>\d{1,2})[/.\- ](?P<Date>\d{1,2})')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %m %d'
            else:
                fmt = '%Y %m %d'

        # Check for DD-MM-(YY)YY
        pattern = (r'(?P<Date>\d{1,2})[/.\- ](?P<Month>\d{1,2})[/.\- ](?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %m %d'
            else:
                fmt = '%Y %m %d'

        try:
            return datetime.strptime(date_string, fmt)
        except (ValueError, NameError):
            raise commands.BadArgument(error_msg)


class GlobalChannel(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            # Not found... so fall back to ID + global lookup
            try:
                channel_id = int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(f'Could not find a channel by ID {argument!r}.')
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(f'Could not find a channel by ID {argument!r}.')
                return channel


class FetchedUser(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.isdigit():
            raise commands.BadArgument('Not a valid user ID.')
        try:
            return await ctx.bot.fetch_user(argument)
        except discord.NotFound:
            raise commands.BadArgument('User not found.') from None
        except discord.HTTPException:
            raise commands.BadArgument('An error occurred while fetching the user.') from None


class TextChannel(commands.TextChannelConverter):
    async def convert(self, ctx, argument):
        channel = await super().convert(ctx, argument)
        ctx.custom_channel = channel
        return channel


class SortByConverter(commands.Converter):
    async def convert(self, ctx, argument):
        argument = argument.lower()
        choices = [
            'donations',
            'received',
            'gain',
            'loss',
            'trophies'
        ]
        if argument not in choices:
            raise commands.BadArgument(f"That didn't look right! Try one of these: {', '.join(choices)}")
        return argument


class ClanChannelComboConverter(commands.Converter):
    async def convert(self, ctx, argument):
        parts = argument.split(" ")

        channel = None
        clan = None

        for n in parts:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, n)
            except commands.BadArgument:
                try:
                    clan = await AddClanConverter().convert(ctx, n)
                except (commands.BadArgument, IndexError):
                    pass

        return channel, clan


class ActivityBarConverter(commands.Converter):
    async def convert(self, ctx, argument):
        guild = None  # channel
        channel = None  # guild
        clan = None  # (tag, name)
        player = None  # (tag, name)

        time_ = None

        match = activity_days_re.search(argument)
        if match:
            argument = argument.replace(match.group(0), "").strip()
            time_ = int(match.group(0)[:-1])

        if tag_validator.match(argument) and argument.startswith("#"):
            argument = coc.utils.correct_tag(argument)

        if argument == "all":
            guild = ctx.guild
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, argument)
            except commands.BadArgument:
                if not await ctx.bot.is_owner(ctx.author):
                    query = "SELECT DISTINCT(clan_tag), clan_name FROM clans WHERE clan_tag = $1 OR clan_name LIKE $2 AND guild_id = $3"
                    fetch = await ctx.db.fetchrow(query, correct_tag(argument), argument, ctx.guild.id)
                else:
                    query = "SELECT DISTINCT(clan_tag), clan_name FROM clans WHERE clan_tag = $1 OR clan_name LIKE $2"
                    fetch = await ctx.db.fetchrow(query, correct_tag(argument), argument)

                if fetch:
                    clan = fetch
                else:
                    query = """
                            WITH cte AS (
                                SELECT DISTINCT player_tag, player_name FROM players WHERE user_id = $1 OR $2 = True
                            )
                            WITH cte2 AS (
                                SELECT DISTINCT player_tag, player_name FROM players INNER JOIN clans ON clans.clan_tag = players.clan_tag WHERE clans.guild_id = $3
                            )
                            SELECT *
                            FROM cte
                            FULL JOIN cte2 ON cte.player_tag = cte2.player_tag 
                            WHERE cte.player_tag = $4 
                            OR cte.player_name LIKE $5
                            """
                    fetch = await ctx.db.fetchrow(
                        query,
                        ctx.author.id,
                        await ctx.bot.is_owner(ctx.author),
                        ctx.guild.id,
                        correct_tag(argument),
                        argument
                    )
                    if fetch:
                        player = fetch
                    else:
                        raise commands.BadArgument(
                            "I tried to parse your argument as a channel, server, clan name, clan tag, player name "
                            "or tag and couldn't find a match! \n\n"
                            "A couple of security features to note: \n"
                            "1. Clan stats can only be found when the clan has been claimed to this server.\n"
                            "2. Player stats can only be found when the player's current clan is claimed to this server, "
                            "or you have claimed the player.\n\nPlease try again.")

        fetch = await ctx.db.fetchrow("SELECT activity_sync FROM guilds WHERE guild_id = $1", ctx.guild.id)
        if not fetch['activity_sync']:
            await ctx.send("Loading clan activity values. This will take a minute. Please be patient.")
            query = """
                    WITH g_clans AS (
                        SELECT distinct clan_tag FROM clans WHERE guild_id = $1
                    ),
                    cte AS (
                        SELECT player_tag,
                               donationevents.clan_tag,
                               date_trunc('HOUR', "time") AS "timer",
                               COUNT(*) AS "counter"
                        FROM donationevents
                        INNER JOIN g_clans ON g_clans.clan_tag = donationevents.clan_tag
                        GROUP BY timer, player_tag, donationevents.clan_tag
                    ),
                    cte2 AS (
                        SELECT player_tag,
                               trophyevents.clan_tag,
                               date_trunc('HOUR', "time") AS "timer",
                               COUNT(*) AS "counter"
                        FROM trophyevents
                        INNER JOIN g_clans ON g_clans.clan_tag = trophyevents.clan_tag
                        WHERE trophyevents.league_id = 29000022
                        AND trophyevents.trophy_change > 0
                        GROUP BY timer, player_tag, trophyevents.clan_tag
                    )
                    INSERT INTO activity_query (player_tag, clan_tag, hour_time, counter, hour_digit)
                    SELECT cte.player_tag,
                           cte.clan_tag,
                           cte.timer,
                           COALESCE(cte.counter, 0) + COALESCE(cte2.counter, 0) as "num_events",
                           date_part('hour', cte.timer) as "hour"
                    FROM cte
                    FULL JOIN cte2
                    ON cte.player_tag = cte2.player_tag
                    AND cte.clan_tag = cte2.clan_tag
                    AND cte.timer = cte2.timer
                    GROUP BY cte.player_tag, cte.clan_tag, cte.timer, "num_events", "hour"
                    ON CONFLICT DO NOTHING
                    """
            s = time.perf_counter()
            guild_id = ctx.guild.id
            ctx.bot.locked_guilds.add(guild_id)
            await ctx.db.execute(query, guild_id)
            ctx.bot.locked_guilds.remove(guild_id)
            await ctx.db.execute("UPDATE guilds SET activity_sync = TRUE WHERE guild_id = $1", ctx.guild.id)
            log.info(f"ACTIVITY INSERT QUERY for Guild ID {guild_id} took {(time.perf_counter() - s)*1000}ms")

        if channel or guild:
            query = """
                    WITH clan_tags AS (
                        SELECT DISTINCT clan_tag, clan_name 
                        FROM clans 
                        WHERE channel_id = $1 OR guild_id = $1
                    ),
                    cte1 AS (
                        SELECT COUNT(DISTINCT player_tag) as "num_players", 
                               DATE(activity_query.hour_time) as "date", 
                               clan_name
                        FROM activity_query 
                        INNER JOIN clan_tags
                        ON clan_tags.clan_tag = activity_query.clan_tag
                        GROUP BY date, clan_name
                    ),
                    cte2 AS (
                        SELECT cast(SUM(counter) as decimal) / MIN(num_players) AS num_events, 
                               hour_time,
                               cte1.clan_name 
                        FROM activity_query 
                        JOIN cte1 
                        ON cte1.date = date(hour_time) 
                        GROUP BY hour_time, cte1.clan_name
                    )
                    SELECT date_part('HOUR', hour_time) as "hour_digit", AVG(num_events),  MIN(hour_time), cte2.clan_name 
                    FROM cte2 
                    GROUP BY hour_digit, cte2.clan_name
                    ORDER BY cte2.clan_name, hour_digit
                    """
        if channel:
            return channel, await ctx.db.fetch(query, channel.id)
        if guild:
            return guild, await ctx.db.fetch(query, guild.id)

        if player:
            query = """
                    WITH valid_times AS (
                        SELECT generate_series(min(hour_time), max(hour_time), '1 hour'::interval) as "time"
                        FROM activity_query 
                        WHERE player_tag = $1
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                    ),
                    actual_times AS (
                        SELECT hour_time as "time", counter
                        FROM activity_query
                        WHERE player_tag = $1
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                    )
                    SELECT date_part('HOUR', valid_times."time") AS "hour", AVG(COALESCE(actual_times.counter, 0)), min(valid_times."time")
                    FROM valid_times
                    LEFT JOIN actual_times ON actual_times.time = valid_times.time
                    GROUP BY "hour"
                    ORDER BY "hour"
                    """
            return player['player_name'], await ctx.db.fetch(query, player['player_tag'], str(time_ or 365))

        if clan:
            query = """
                    WITH cte1 AS (
                        SELECT COUNT(DISTINCT player_tag) as "num_players", 
                               DATE(activity_query.hour_time) as "date" 
                        FROM activity_query 
                        WHERE clan_tag = $1 
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP by date
                    ),
                    cte2 AS (
                        SELECT cast(SUM(counter) as decimal) / MIN(num_players) AS num_events, 
                               hour_time 
                        FROM activity_query 
                        JOIN cte1 
                        ON cte1.date = date(hour_time) 
                        WHERE clan_tag = $1 
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP BY hour_time
                    )
                    SELECT date_part('HOUR', hour_time) as "hour_digit", AVG(num_events), MIN(hour_time) 
                    FROM cte2 
                    GROUP BY hour_digit
                    """
            return clan['clan_name'], await ctx.db.fetch(query, clan['clan_tag'], str(time_ or 365))
