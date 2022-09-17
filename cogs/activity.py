import datetime
import io
import itertools
import typing

import discord
import numpy as np
import seaborn as sns

from matplotlib import pyplot as plt
from matplotlib import dates as mdates
from discord.ext import commands, tasks

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

    @commands.group()
    async def activity(self, ctx):
        """[Group] Get a graph showing the approximate activity/online times for a clan or member."""
        if ctx.invoked_subcommand is not None:
            return

        await ctx.send_help(ctx.command)

    @activity.group(name='bar', invoke_without_command=True)
    async def activity_bar(self, ctx, *, argument: ActivityBarConverter = None):
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
        query = """SELECT COALESCE((SELECT timezone_offset FROM user_config WHERE user_id = $1), 0) as timezone_offset,
                          COALESCE((SELECT dark_mode FROM user_config WHERE user_id = $1), False) as dark_mode"""
        fetch = await ctx.db.fetchrow(query, ctx.author.id)
        timezone_offset = int(fetch['timezone_offset'])
        if fetch['dark_mode']:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        if not argument:
            return await ctx.send(f"Not enough history. Please try again later.")

        data: typing.List[typing.Tuple[str, typing.List]] = argument

        existing_graph_data = self.get_bar_graph(ctx.channel.id, ctx.author.id)

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

        self.add_bar_graph(ctx.channel.id, ctx.author.id, **data_to_add)

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await ctx.send(file=discord.File(b, f'activitygraph.png'))
        plt.close()

    @activity_bar.command(name='clear')
    async def activity_bar_clear(self, ctx):
        """Clear your activity bar graph of previous results.

        **Format**
        :information_source: `+activity bar clear`

        **Example**
        :information_source: `+activity bar clear`
        """
        try:
            del self.graphs[("bar", ctx.channel.id, ctx.author.id)]
        except KeyError:
            pass
        await ctx.send(":ok_hand: Graph has been reset.")

    @activity.group(name="line", invoke_without_command=True)
    async def activity_line(self, ctx, *, argument: ActivityLineConverter = None):
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
        query = """SELECT COALESCE((SELECT dark_mode FROM user_config WHERE user_id = $1), False) as dark_mode"""
        fetch = await ctx.db.fetchrow(query, ctx.author.id)
        if fetch['dark_mode']:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        if not argument:
            return await ctx.send(f"Not enough history. Please try again later.")

        data: typing.List[typing.Tuple[str, typing.Dict]] = argument

        existing = self.get_line_graph(ctx.channel.id, ctx.author.id)
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

        self.add_line_graph(ctx.channel.id, ctx.author.id, data)

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await ctx.send(file=discord.File(b, f'activitygraph.png'))
        plt.close()

    @activity_line.command(name='clear')
    async def activity_line_clear(self, ctx):
        """Clear your activity line graph of previous results.

        **Format**
        :information_source: `+activity line clear`

        **Example**
        :information_source: `+activity line clear`
        """
        try:
            del self.graphs[("line", ctx.channel.id, ctx.author.id)]
        except KeyError:
            pass
        await ctx.send(":ok_hand: Graph has been reset.")

    @activity.before_invoke
    async def before_activity(self, ctx):
        await ctx.trigger_typing()


async def setup(bot):
    await bot.add_cog(Activity(bot))
