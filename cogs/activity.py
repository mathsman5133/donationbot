import datetime
import io
import time
import typing
import numpy
import itertools

import coc
import discord

from collections import Counter

from matplotlib import pyplot as plt
from discord.ext import commands

from cogs.utils.converters import ClanConverter, PlayerConverter, ActivityBarConverter
from cogs.utils.formatters import readable_time
from cogs.utils.paginator import LastOnlinePaginator
from cogs.utils.checks import is_patron


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.graphs = {}

    def add_bar_graph(self, guild_id, author_id, **data):
        key = (guild_id, author_id)
        self.graphs[key] = data

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
        fetch = await ctx.db.fetchrow("SELECT timezone_offset FROM guilds WHERE guild_id = $1", ctx.guild.id)
        timezone_offset = int(fetch['timezone_offset'])
        key, fetch = data

        if not fetch:
            return await ctx.send(f"Not enough history. Please try again later.")

        days = int((datetime.datetime.now() - fetch[0][2]).total_seconds() / (60 * 60 * 24))
        existing_graph_data = self.graphs.get((ctx.guild.id, ctx.author.id), {})

        data_to_add = {}  # name: {hour: events}

        def get_hour_plus_offset(hour):
            if 0 <= hour + timezone_offset <= 23:
                return hour + timezone_offset
            if hour + timezone_offset > 23:
                return hour + timezone_offset - 24
            return hour + timezone_offset + 24

        if isinstance(key, (discord.TextChannel, discord.Guild)):
            # if it's a guild or channel this supports multiple clans. eg `+activity bar all`
            for clan_name, data in itertools.groupby(fetch, key=lambda x: x[3]):
                dict_ = {n[0]: n[1] for n in data}
                data_to_add[clan_name + f" ({days + 1}d)"] = {get_hour_plus_offset(hour): dict_.get(hour, 0) for hour in range(24)}
        else:
            dict_ = {n[0]: n[1] for n in fetch}
            data_to_add[key + f" ({days + 1}d)"] = {get_hour_plus_offset(hour): dict_.get(hour, 0) for hour in range(24)}

        data_to_add = {**existing_graph_data, **data_to_add}

        def get_width_offset(index):
            width = 0.8 / len(data_to_add)
            return width, width * index

        y_pos = numpy.arange(24)
        graphs = []

        for i, (name, data) in enumerate(data_to_add.items()):
            width, offset = get_width_offset(i)
            graphs.append((
                plt.bar([n + offset for n in y_pos], list(data.values()), width, align='center'), name
            ))

        plt.xticks(y_pos, list(range(24)))
        plt.xlabel(f"Time (hr) - UTC{'+' + str(timezone_offset) if timezone_offset > 0 else timezone_offset}")
        plt.ylabel("Activity (average events)")
        plt.title(f"Activity Graph - Time Period: {days + 1}d")
        plt.legend(tuple(n[0] for n in graphs), tuple(n[1] for n in graphs))

        self.add_bar_graph(ctx.guild.id, ctx.author.id, **data_to_add)

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await ctx.send(file=discord.File(b, f'activitygraph.png'))
        plt.cla()

    @activity_bar.command(name='clear')
    async def activity_bar_clear(self, ctx):
        """Clear your activity bar graph of previous results.

        **Format**
        :information_source: `+activity bar clear`

        **Example**
        :information_source: `+activity bar clear`
        """
        try:
            del self.graphs[(ctx.guild.id, ctx.author.id)]
        except KeyError:
            pass
        await ctx.send(":ok_hand: Graph has been reset.")

    @activity.command(name='player')
    async def activity_player(self, ctx, *, player: PlayerConverter):
        """Get an approximation for the last time a player was online.

        **Parameters**
        :key: Player name OR tag

        **Format**
        :information_source: `+lastonline player #PLAYER_TAG`
        :information_source: `+lastonline player Player Name`

        **Example**
        :white_check_mark: `+lastonline player #P0LYJC8C`
        :white_check_mark: `+lastonline player mathsman`
        """
        query = """WITH cte AS (
                        SELECT date_part('HOUR', "time") as "hour", COUNT(*) as "count", clan_tag 
                        From trophyevents 
                        WHERE player_tag = $1
                        AND league_id = 29000022
                        AND trophy_change > 0
                        GROUP BY clan_tag, "hour"
                    ),
                    cte2 AS (
                        SELECT date_part('HOUR', "time") as "hour", COUNT(*) as "count", clan_tag 
                        From donationevents 
                        WHERE player_tag = $1
                        AND donations > 0
                        GROUP BY clan_tag, "hour"
                    )
                    select cte.count + cte2.count as "count", cte."hour"
                    FROM cte
                    JOIN cte2 ON cte.hour = cte2.hour
                """
        fetch = await ctx.db.fetchrow(query, player.tag)

        if not fetch:
            return await ctx.send("Not enough history. Please try again later.")

        y_pos = [i for i in range(len(fetch))]
        plt.bar(y_pos, [n[0] for n in fetch], align='center', alpha=0.5)
        plt.xticks(y_pos, [str(n[1]) for n in fetch])
        plt.xlabel("Time (hr)")
        plt.ylabel("Activity")
        plt.title(f"Activity graph for {player}")

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await ctx.send(file=discord.File(b, f'activitygraph.png'))
    #
    # @activity.command(name='user')
    # async def last_online_user(self, ctx, *, user: discord.Member = None):
    #     """Get an approximation for the last time a player was online.
    #
    #     **Parameters**
    #     :key: Discord user (optional - defaults to yourself)
    #
    #     **Format**
    #     :information_source: `+lastonline user @MENTION`
    #     :information_source: `+lastonline user`
    #
    #     **Example**
    #     :white_check_mark: `+lastonline user @mathsman`
    #     :white_check_mark: `+lastonline user`
    #     """
    #     user = user or ctx.author
    #     query = """SELECT player_tag,
    #                           last_updated - now() AS "since"
    #                    FROM players
    #                    WHERE user_id = $1
    #                    AND season_id = $2
    #                    ORDER BY since DESC
    #                 """
    #     fetch = await ctx.db.fetch(query, user.id, await self.bot.seasonconfig.get_season_id())
    #     if not fetch:
    #         return await ctx.send(f"{user} doesn't have any claimed accounts.")
    #
    #     page_count = math.ceil(len(fetch) / 20)
    #     title = f'Last Online Estimate for {user}'
    #
    #     p = LastOnlinePaginator(ctx, data=fetch, title=title, page_count=page_count)
    #
    #     await p.paginate()


def setup(bot):
    bot.add_cog(Activity(bot))
