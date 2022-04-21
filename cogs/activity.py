import datetime
import io
import itertools
import typing

import coc
import disnake
import numpy as np
import seaborn as sns

from matplotlib import pyplot as plt
from matplotlib import dates as mdates
from disnake.ext import commands, tasks

from cogs.utils.converters import ActivityBarConverter, ActivityLineConverter


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.graphs = {}
        self.bot_wide_line = None

        self.clean_graph_cache.start()
        self.load_bot_wide_data.start()

    def cog_unload(self):
        self.clean_graph_cache.cancel()
        self.load_bot_wide_data.cancel()

    def add_bar_graph(self, channel_id, author_id, **data):
        key = ("bar", channel_id, author_id)
        self.graphs[key] = (data, datetime.datetime.now())

    def get_bar_graph(self, channel_id, author_id):
        try:
            data = self.graphs[("bar", channel_id, author_id)]
            return data[0]
        except KeyError:
            return {}

    def add_line_graph(self, channel_id, author, data):
        key = ("line", channel_id, author)
        self.graphs[key] = (data, datetime.datetime.utcnow())

    def get_line_graph(self, channel_id, author_id):
        try:
            data = self.graphs[("line", channel_id, author_id)]
            return data[0]
        except KeyError:
            return []

    @tasks.loop(hours=24.0)
    async def load_bot_wide_data(self):
        await self.bot.wait_until_ready()
        query = """WITH cte AS (
                            SELECT cast(SUM(counter) as decimal) / COUNT(distinct player_tag) AS counter, 
                                   date_trunc('day', hour_time) AS "date" 
                            FROM activity_query 
                            WHERE hour_time < TIMESTAMP 'today'
                            GROUP BY date 
                        ),
                        cte2 AS (
                            SELECT stddev(counter) AS stdev, 
                                   avg(counter) as avg, 
                                   date_trunc('week', date) as week 
                            FROM cte 
                            GROUP BY week
                        )
                        SELECT cte.date, counter, stdev 
                        FROM cte 
                        INNER JOIN cte2 
                        ON date_trunc('week', cte.date) = cte2.week 
                        WHERE counter BETWEEN avg - stdev AND avg + stdev 
                        ORDER BY date
                """
        fetch = await self.bot.pool.fetch(query)
        self.bot_wide_line = ("Bot Average", fetch)

    @tasks.loop(minutes=1)
    async def clean_graph_cache(self):
        time = datetime.datetime.now()
        to_clear = [k for (k, (v, t)) in self.graphs.items() if time > t + datetime.timedelta(hours=1)]
        for key in to_clear:
            try:
                del self.graphs[key]
            except KeyError:
                pass

    async def clan_to_tag(self, clan, guild_id, author, conn):
        if not await self.bot.is_owner(author):
            query = "SELECT DISTINCT(clan_tag), clan_name FROM clans WHERE clan_tag = $1 OR clan_name LIKE $2 AND guild_id = $3"
            return await conn.fetchrow(query, coc.utils.correct_tag(clan), clan, guild_id)
        else:
            query = "SELECT DISTINCT(clan_tag), clan_name FROM clans WHERE clan_tag = $1 OR clan_name LIKE $2"
            return await conn.fetchrow(query, coc.utils.correct_tag(clan), clan)

    async def player_to_tag(self, player, guild_id, author, conn):
        fake_clan_in_server = guild_id in self.bot.fake_clan_guilds
        join = "(clans.clan_tag = players.clan_tag OR " \
               "(players.fake_clan_tag IS NOT NULL AND clans.clan_tag = players.fake_clan_tag))" \
            if fake_clan_in_server else "clans.clan_tag = players.clan_tag"

        query = f"""
                        WITH cte AS (
                            SELECT player_tag, player_name FROM players WHERE ($2 = True OR user_id = $1) AND player_name is not null AND season_id = $6
                        ),
                        cte2 AS (
                            SELECT DISTINCT player_tag, 
                                            player_name 
                            FROM players 
                            INNER JOIN clans 
                            ON {join}
                            WHERE clans.guild_id = $3
                            AND players.season_id = $6
                        )
                        SELECT player_tag, player_name FROM cte
                        WHERE player_tag = $4 
                        OR player_name LIKE $5
                        UNION 
                        SELECT player_tag, player_name FROM cte2
                        WHERE player_tag = $4 
                        OR player_name LIKE $5
                        """
        fetch = await conn.fetchrow(
            query,
            author.id,
            await self.bot.is_owner(author),
            guild_id,
            coc.utils.correct_tag(player),
            player,
            await self.bot.seasonconfig.get_season_id(),
        )
        return fetch

    async def convert_activity_bar(self, player, clan, author, channel, guild, days, conn):
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
            player = await self.player_to_tag(player, guild.id, author, conn)
            fetch = await conn.fetch(query, player['player_tag'], str(days or 365))
            if not fetch:
                return None

            return [(player['player_name'], fetch)]

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
            fetch = await conn.fetch(query, clan['clan_tag'], str(days or 365))
            clan = await self.clan_to_tag(clan, guild.id, author, conn)
            if not fetch:
                return None

            return [(clan['clan_name'], fetch)]

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
                               clan_tags.clan_name
                        FROM activity_query 
                        INNER JOIN clan_tags ON activity_query.clan_tag = clan_tags.clan_tag
                        WHERE activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP by clan_tags.clan_name, date
                    ),
                    cte2 AS (
                        SELECT cast(SUM(counter) as decimal) / MIN(num_players) AS num_events, 
                               hour_time,
                               clan_tags.clan_name
                        FROM activity_query 
                        JOIN cte1 
                        ON cte1.date = date(hour_time) 
                        INNER JOIN clan_tags ON clan_tags.clan_tag = activity_query.clan_tag
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP by clan_tags.clan_name, hour_time
                    )
                    SELECT date_part('HOUR', hour_time) as "hour_digit", AVG(num_events), MIN(hour_time), clan_name
                    FROM cte2 
                    GROUP BY clan_name, hour_digit
                    ORDER BY clan_name, hour_digit
                    """

            fetch = await conn.fetch(query, channel and channel.id or guild.id, str(days or 365))
            if not fetch:
                return None

            to_return = []
            for clan_name, records in itertools.groupby(fetch, key=lambda r: r['clan_name']):
                to_return.append((clan_name, list(records)))

            return to_return

        else:
            query = """
                    WITH player_tags AS (
                        SELECT DISTINCT player_tag, player_name FROM players WHERE user_id = $1 AND player_name IS NOT null AND season_id = $3
                    ),
                    valid_times AS (
                        SELECT generate_series(min(hour_time), max(hour_time), '1 hour'::interval) as "time", player_tags.player_name
                        FROM activity_query 
                        INNER JOIN player_tags 
                        ON activity_query.player_tag = player_tags.player_tag
                        WHERE activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP BY player_tags.player_name
                    ),
                    actual_times AS (
                        SELECT hour_time as "time", counter, player_tags.player_name
                        FROM activity_query 
                        INNER JOIN player_tags 
                        ON activity_query.player_tag = player_tags.player_tag
                        AND activity_query.hour_time > now() - ($2 ||' days')::interval
                        GROUP BY player_tags.player_name, time, counter
                    )
                    SELECT date_part('HOUR', valid_times."time") AS "hour", AVG(COALESCE(actual_times.counter, 0)), min(valid_times."time"), valid_times.player_name
                    FROM valid_times
                    LEFT JOIN actual_times ON actual_times.time = valid_times.time AND actual_times.player_name = valid_times.player_name
                    GROUP BY valid_times.player_name, "hour"
                    ORDER BY valid_times.player_name, "hour"
                    """
            fetch = await conn.fetch(query, author.id, str(days or 365), await self.bot.seasonconfig.get_season_id())
            if not fetch:
                return None

            to_return = []
            for player_tag, records in itertools.groupby(fetch, key=lambda r: r['player_name']):
                to_return.append((player_tag, list(records)))

            return to_return

    async def convert_activity_line(self, player, clan, author, channel, guild, conn):
        if player:
            query = """WITH cte AS (
                            SELECT SUM(counter) AS counter, 
                                   date_trunc('day', hour_time) AS date 
                            FROM activity_query 
                            WHERE player_tag = $1 
                            AND hour_time < TIMESTAMP 'today'
                            GROUP BY date 
                            ORDER BY date
                        ),
                        cte2 AS (
                            SELECT stddev(counter) AS stdev, 
                                   avg(counter) as avg, 
                                   date_trunc('week', date) as week 
                            FROM cte 
                            GROUP BY week
                        )
                        SELECT cte.date, counter, stdev 
                        FROM cte 
                        INNER JOIN cte2 
                        ON date_trunc('week', cte.date) = cte2.week 
                        WHERE counter BETWEEN avg - stdev AND avg + stdev 
                        ORDER BY date
                    """
            player = await self.player_to_tag(player, guild.id, author, conn)
            fetch = await conn.fetch(query, player['player_tag'])
            if not fetch:
                return None
            return [(player['player_name'], fetch)]

        if clan:
            query = """WITH cte AS (
                            SELECT cast(SUM(counter) as decimal) / COUNT(distinct player_tag) AS counter, 
                                   date_trunc('day', hour_time) AS "date" 
                            FROM activity_query 
                            WHERE clan_tag = $1 
                            AND hour_time < TIMESTAMP 'today'
                            GROUP BY date 
                            ORDER BY date
                        ),
                        cte2 AS (
                            SELECT stddev(counter) AS stdev, 
                                   avg(counter) as avg, 
                                   date_trunc('week', date) as week 
                            FROM cte 
                            GROUP BY week
                        )
                        SELECT cte.date, counter, stdev 
                        FROM cte 
                        INNER JOIN cte2 
                        ON date_trunc('week', cte.date) = cte2.week 
                        WHERE counter BETWEEN avg - stdev AND avg + stdev 
                        ORDER BY date
                    """
            clan = await self.clan_to_tag(clan, guild.id, author, conn)
            fetch = await conn.fetch(query, clan['clan_tag'])
            if not fetch:
                return None
            return [(clan['clan_name'], fetch)]

        if channel or guild:
            query = """
                    WITH clan_tags AS (
                        SELECT DISTINCT clan_tag, clan_name 
                        FROM clans 
                        WHERE channel_id = $1 OR guild_id = $1
                    ),
                    cte AS (
                        SELECT cast(SUM(counter) as decimal) / COUNT(DISTINCT player_tag) AS counter, 
                               date_trunc('day', hour_time) AS date,
                               clan_tags.clan_name
                        FROM activity_query 
                        INNER JOIN clan_tags
                        ON clan_tags.clan_tag = activity_query.clan_tag
                        AND hour_time < TIMESTAMP 'today'
                        GROUP BY date, clan_tags.clan_name 
                        ORDER BY date
                    ),
                    cte2 AS (
                        SELECT stddev(counter) AS stdev, 
                               avg(counter) as avg, 
                               date_trunc('week', date) as week,
                               clan_name
                        FROM cte 
                        GROUP BY week, clan_name
                    )
                    SELECT cte.date, min(counter) as counter, min(stdev) as stdev, cte.clan_name 
                    FROM cte 
                    INNER JOIN cte2 
                    ON date_trunc('week', cte.date) = cte2.week 
                    WHERE counter BETWEEN avg - stdev AND avg + stdev 
                    GROUP BY cte.clan_name, cte.date
                    ORDER BY cte.clan_name, cte.date
                    """

            fetch = await conn.fetch(query, channel and channel.id or guild.id)
            if not fetch:
                return None

            to_return = []
            for clan_name, records in itertools.groupby(fetch, key=lambda r: r['clan_name']):
                to_return.append((clan_name, list(records)))

            return to_return

        else:
            query = """
                    WITH player_tags AS (
                        SELECT DISTINCT player_tag, player_name FROM players WHERE user_id = $1 AND player_name IS NOT null
                    ),
                    cte AS (
                        SELECT SUM(counter) AS counter, 
                               date_trunc('day', hour_time) AS date,
                               player_tags.player_name
                        FROM activity_query 
                        INNER JOIN player_tags
                        ON player_tags.player_tag = activity_query.player_tag
                        AND hour_time < TIMESTAMP 'today'
                        GROUP BY date, player_tags.player_name 
                        ORDER BY date
                    ),
                    cte2 AS (
                        SELECT stddev(counter) AS stdev, 
                               avg(counter) as avg, 
                               date_trunc('week', date) as week,
                               player_name
                        FROM cte 
                        GROUP BY week, player_name
                    )
                    SELECT cte.date, min(counter) as counter, min(stdev) as stdev, cte.player_name 
                    FROM cte 
                    INNER JOIN cte2 
                    ON date_trunc('week', cte.date) = cte2.week 
                    WHERE counter BETWEEN avg - stdev AND avg + stdev 
                    GROUP BY cte.player_name, cte.date
                    ORDER BY cte.player_name, cte.date
                    """
            fetch = await conn.fetch(query, author.id)
            if not fetch:
                return None

            to_return = []
            for player_tag, records in itertools.groupby(fetch, key=lambda r: r['player_name']):
                to_return.append((player_tag, list(records)))

            return to_return

    async def check_can_run_activity(self, guild_id, conn):
        fetch = await conn.fetchrow("SELECT activity_sync FROM guilds WHERE guild_id = $1", guild_id)
        if not (fetch and fetch['activity_sync']):
            await conn.execute(
                "INSERT INTO guilds (guild_id, activity_sync) VALUES ($1, TRUE) "
                "ON CONFLICT (guild_id) DO UPDATE SET activity_sync = TRUE",
                guild_id
            )
            return False
        return True

    @commands.slash_command(description="Get a graph showing the approximate activity/online times for a clan or member.")
    async def activity(self, intr: disnake.ApplicationCommandInteraction):
        """[Group] Get a graph showing the approximate activity/online times for a clan or member."""
        # await intr.response.defer()
        # if ctx.invoked_subcommand is not None:
        #     return
        #
        # await ctx.send_help(ctx.command)

    @activity.sub_command(name="bar", description="Get a graph showing the approximate activity/online times for a clan.")
    async def activity_bar(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        days: int = commands.Param(default=None, description="Data range - in days - how long you wish to find data for."),
        new_graph: bool = commands.Param(default=False, description="Whether to clear previous results and generate a new graph.")
    ):
        """Get a graph showing the approximate activity/online times for a clan.

        This command will return a graph that is generated from approximate activity readers
        based on donations and trophy gains of legends players.

        This command will remember your previous graph, and the next command you run will automatically compare
        the previous graph(s) with this one. If you wish to reset the graph, use `+activity bar clear`.

        **Parameters**
        :key: Clan name or tag, player name or tag. The player or clan you wish to find activity for.
        :key: Data range - in days - how long you wish to find data for. By default, this will be as long as the bot has.

        **Format**
        :information_source: `+activity bar #CLANTAG`
        :information_source: `+activity bar Clan Name DAYSd`
        :information_source: `+activity bar #PLAYERTAG DAYSd`
        :information_source: `+activity bar Player Name`

        **Example**
        :white_check_mark: `+activity bar #P0LYJC8C 13d`
        :white_check_mark: `+activity bar Rock Throwers`
        :white_check_mark: `+activity bar #PL80J2YL`
        :white_check_mark: `+activity bar Mathsman 30d`
        """
        if not await self.check_can_run_activity(intr.guild_id, intr.db):
            await intr.edit_original_message(content="""
                This is the first time this command has been run in this server.
                I will only start recording your activity from now.
                Please wait a few days for me to gather reliable data.""")

        if new_graph:
            try:
                del self.graphs[("bar", intr.channel_id, intr.author.id)]
            except KeyError:
                pass

        query = """SELECT COALESCE((SELECT timezone_offset FROM user_config WHERE user_id = $1), 0) as timezone_offset,
                          COALESCE((SELECT dark_mode FROM user_config WHERE user_id = $1), False) as dark_mode"""
        fetch = await intr.db.fetchrow(query, intr.author.id)
        timezone_offset = int(fetch['timezone_offset'])
        if fetch['dark_mode']:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        argument = await self.convert_activity_bar(player, clan, intr.author, intr.channel, intr.guild, days, intr.db)
        if not argument:
            return await intr.send(f"I couldn't find that player/clan, or there wasn't enough history. Please try again later.")

        data: typing.List[typing.Tuple[str, typing.List]] = argument

        existing_graph_data = self.get_bar_graph(intr.channel.id, intr.author.id)

        data_to_add = {}  # name: {hour: events}

        def get_hour_plus_offset(hour):
            if 0 <= hour + timezone_offset <= 23:
                return hour + timezone_offset
            if hour + timezone_offset > 23:
                return hour + timezone_offset - 24
            return hour + timezone_offset + 24

        for key, fetch in data:
            days = int((datetime.datetime.now() - min([n['min'] for n in fetch])).total_seconds() / (60 * 60 * 24))
            dict_ = {n[0]: n[1] for n in fetch}
            data_to_add[key + f" ({days + 1}d)"] = {
                get_hour_plus_offset(hour): dict_.get(hour, 0) for hour in range(24)
            }

        data_to_add = {**existing_graph_data, **data_to_add}

        def get_width_offset(index):
            width = 0.8 / len(data_to_add)
            return width, width * index

        y_pos = np.arange(24)
        graphs = []

        for i, (name, data) in enumerate(data_to_add.items()):
            data = dict(sorted(data.items()))
            width, offset = get_width_offset(i)
            graphs.append((
                plt.bar([n + offset for n in y_pos], list(data.values()), width, align='center'), name
            ))

        plt.xticks(y_pos, list(range(24)))
        plt.xlabel(f"Time (hr) - UTC{'+' + str(timezone_offset) if timezone_offset > 0 else timezone_offset}")
        plt.ylabel("Activity (average events)")
        plt.title(f"Activity Graph - Time Period: {days + 1}d")
        plt.legend(tuple(n[0] for n in graphs), tuple(n[1] for n in graphs))

        self.add_bar_graph(intr.channel.id, intr.author.id, **data_to_add)

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await intr.edit_original_message(file=disnake.File(b, f'activitygraph.png'))
        plt.close()

    @activity.sub_command(name="line", description="Get a graph showing the change in activity for a clan or player over time.")
    async def activity_line(
        self,
        intr: disnake.ApplicationCommandInteraction,
        player: str = commands.Param(default=None, description="Player #tag or name."),
        clan: str = commands.Param(default=None, description="Clan #tag or name."),
        new_graph: bool = commands.Param(default=False,
                                         description="Whether to clear previous results and generate a new graph.")

    ):
        """Get a graph showing the change in activity for a clan or player over time.

        This command will return a graph that is generated from approximate activity readers
        based on donations, received, exp level change and other measures used to calculate last online.

        This command will remember your previous graph, and the next command you run will automatically compare
        the previous graph(s) with this one. If you wish to reset the graph, use `+activity line clear`.

        **Parameters**
        :key: Clan name or tag, player name or tag. The player or clan you wish to find activity for.

        **Format**
        :information_source: `+activity line #CLANTAG`
        :information_source: `+activity line Clan Name`
        :information_source: `+activity line #PLAYERTAG`
        :information_source: `+activity line Player Name`

        **Example**
        :white_check_mark: `+activity line #P0LYJC8C`
        :white_check_mark: `+activity line Rock Throwers`
        :white_check_mark: `+activity line #PL80J2YL`
        :white_check_mark: `+activity line Mathsman`
        """
        if not await self.check_can_run_activity(intr.guild_id, intr.db):
            await intr.edit_original_message(content="""
                This is the first time this command has been run in this server.
                I will only start recording your activity from now.
                Please wait a few days for me to gather reliable data.""")

        if new_graph:
            try:
                del self.graphs[("line", intr.channel_id, intr.author.id)]
            except KeyError:
                pass

        query = """SELECT COALESCE((SELECT dark_mode FROM user_config WHERE user_id = $1), False) as dark_mode"""
        fetch = await intr.db.fetchrow(query, intr.author.id)
        if fetch['dark_mode']:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        argument = await self.convert_activity_line(player, clan, intr.author, intr.channel, intr.guild, intr.db)
        if not argument:
            return await intr.send(f"I couldn't find that player/clan, or there wasn't enough history. Please try again later.")

        data: typing.List[typing.Tuple[str, typing.Dict]] = argument

        existing = self.get_line_graph(intr.channel_id, intr.author.id)
        data = [*existing, *data]
        if self.bot_wide_line:
            data.insert(0, self.bot_wide_line)

        colours = sns.color_palette("hls", len(data))

        fig, ax = plt.subplots()
        min_date = None
        max_date = None

        for i, entry in enumerate(data):
            name, record = entry
            means = []
            stdev = []
            dates = []
            for item in record:
                means.append(item['counter'])
                stdev.append(item['stdev'])
                dates.append(item['date'])

            meanst = np.array(means, dtype=np.float64)
            sdt = np.array(stdev, dtype=np.float64)
            ax.plot(dates, means, label=name, color=colours[i])

            if name != "Bot Average":
                ax.fill_between(dates, [max(0, n) for n in meanst - sdt], meanst + sdt, alpha=0.3, facecolor=colours[i])
                if not min_date or dates[0] < min_date:
                    min_date = dates[0]
                if not max_date or dates[-1] > max_date:
                    max_date = dates[-1]

            locator = mdates.AutoDateLocator(minticks=3, maxticks=10)
            formatter = mdates.ConciseDateFormatter(locator)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(formatter)

            ax.legend()

        ax.grid(True)
        ax.set_ylabel("Activity")
        ax.set_title("Activity Change Over Time")
        ax.set_xlim(min_date, max_date)

        data = [(n, v) for n, v in data if n != "Bot Average"]

        self.add_line_graph(intr.channel_id, intr.author.id, data)

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await intr.edit_original_message(file=disnake.File(b, f'activitygraph.png'))
        plt.close()


def setup(bot):
    bot.add_cog(Activity(bot))
