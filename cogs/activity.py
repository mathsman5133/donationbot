import datetime
import io
import itertools
import typing

import discord
import numpy

from matplotlib import pyplot as plt
from discord.ext import commands, tasks

from cogs.utils.converters import ActivityBarConverter


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.graphs = {}
        self.clean_graph_cache.start()

    def cog_unload(self):
        self.clean_graph_cache.cancel()

    def add_bar_graph(self, channel_id, author_id, **data):
        key = (channel_id, author_id)
        self.graphs[key] = (data, datetime.datetime.now())

    def get_bar_graph(self, channel_id, author_id):
        try:
            data = self.graphs[(channel_id, author_id)]
            return data[0]
        except KeyError:
            return {}

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

    @activity.group(name='bar', invoke_without_command=True)
    async def activity_bar(self, ctx, *, data: ActivityBarConverter):
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

        data: typing.List[typing.Tuple[str, typing.List]] = data

        if not data:
            return await ctx.send(f"Not enough history. Please try again later.")

        days = int((datetime.datetime.now() - data[0][1][2]).total_seconds() / (60 * 60 * 24))
        existing_graph_data = self.get_bar_graph(ctx.channel.id, ctx.author.id)

        data_to_add = {}  # name: {hour: events}

        def get_hour_plus_offset(hour):
            if 0 <= hour + timezone_offset <= 23:
                return hour + timezone_offset
            if hour + timezone_offset > 23:
                return hour + timezone_offset - 24
            return hour + timezone_offset + 24

        for key, fetch in data:
            dict_ = {n[0]: n[1] for n in fetch}
            data_to_add[key + f" ({days + 1}d)"] = {
                get_hour_plus_offset(hour): dict_.get(hour, 0) for hour in range(24)
            }

        data_to_add = {**existing_graph_data, **data_to_add}

        def get_width_offset(index):
            width = 0.8 / len(data_to_add)
            return width, width * index

        y_pos = numpy.arange(24)
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
            del self.graphs[(ctx.channel.id, ctx.author.id)]
        except KeyError:
            pass
        await ctx.send(":ok_hand: Graph has been reset.")


def setup(bot):
    bot.add_cog(Activity(bot))
