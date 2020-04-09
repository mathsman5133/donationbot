import io
import time
import typing
import numpy

import coc
import discord

from collections import Counter

from matplotlib import pyplot as plt
from discord.ext import commands

from cogs.utils.converters import ClanConverter, PlayerConverter
from cogs.utils.formatters import readable_time
from cogs.utils.paginator import LastOnlinePaginator


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.graphs = {}

    def add_graph(self, guild_id, author_id, data):
        key = (guild_id, author_id)
        try:
            self.graphs[key].append(data)
        except (KeyError, AttributeError):  # not sure which one this raises yet
            self.graphs[key] = [data]

    @commands.group()
    @commands.is_owner()
    async def activity(self, ctx, *, arg: typing.Union[discord.Member, ClanConverter, PlayerConverter] = None):
        """[Group] Get a graph showing the approximate activity/online times for a clan or member.

        **Parameters**
        :key: Discord user **OR**
        :key: Clash player tag or name **OR**
        :key: Clash clan tag or name **OR**
        :key: `all` for all clans claimed.

        **Format**
        :information_source: `+activity @MENTION`
        :information_source: `+activity #PLAYER_TAG`
        :information_source: `+activity Player Name`
        :information_source: `+activity #CLAN_TAG`
        :information_source: `+activity Clan Name`
        :information_source: `+activity all`

        **Example**
        :white_check_mark: `+activity @mathsman`
        :white_check_mark: `+activity #JJ6C8PY`
        :white_check_mark: `+activity mathsman`
        :white_check_mark: `+activity #P0LYJC8C`
        :white_check_mark: `+activity Rock Throwers`
        :white_check_mark: `+activity all`
        """
        if ctx.invoked_subcommand is not None:
            return

        if not arg:
            arg = await ctx.get_clans()

        if not arg:
            return await ctx.send('Please claim a clan.')
        # elif isinstance(arg, discord.Member):
        #     await ctx.invoke(self.last_online_user, user=arg)
        # elif isinstance(arg, coc.BasicPlayer):
        #     await ctx.invoke(self.last_online_player, player=arg)
        elif isinstance(arg, list):
            if isinstance(arg[0], coc.BasicClan):
                await ctx.invoke(self.activity_clan, clan=arg)

    @activity.command(name='clan')
    async def activity_clan(self, ctx, *, clan: ClanConverter):
        """Get a graph showing the approximate activity/online times for a clan."

        **Parameters**
        :key: Clan name OR tag

        **Format**
        :information_source: `+activity clan #CLANTAG`
        :information_source: `+activity clan Clan Name`

        **Example**
        :white_check_mark: `+activity clan #P0LYJC8C`
        :white_check_mark: `+activity clan Rock Throwers`
        """
        if not clan:
            return await ctx.send("Please pass in a clan.")

        s = time.perf_counter()
        query = """SELECT date_part('HOUR', "time") as "hour", COUNT(*) as "count" 
                   From trophyevents 
                   WHERE clan_tag = $1
                   AND league_id = 29000022
                   AND trophy_change > 0
                   GROUP BY clan_tag, "hour"
                   ORDER BY "hour"
                """
        query2 = """SELECT date_part('HOUR', "time") as "hour", COUNT(*) as "count" 
                    From donationevents 
                    WHERE clan_tag = $1
                    AND donations > 0
                    GROUP BY clan_tag, "hour"
                    ORDER BY "hour"
                 """
        trophy_events = {n[1]: n[0] for n in await ctx.db.fetch(query, clan[0].tag)}
        donation_events = {n[1]: n[0] for n in await ctx.db.fetch(query2, clan[0].tag)}

        if not (trophy_events or donation_events):
            return await ctx.send(f"Not enough history. Please try again later.")

        events = {hour: value + donation_events[hour] for hour, value in trophy_events.items()}
        f = time.perf_counter()

        existing_graphs = self.graphs.get((ctx.guild.id, ctx.author.id), [])

        s2 = time.perf_counter()
        y_pos = numpy.arange(len(events))
        graph = plt.bar(y_pos, list(events.values()), align='center', alpha=0.5)
        plt.xticks(y_pos, list(events.keys()))
        plt.xlabel("Time (hr)")
        plt.ylabel("Activity (events / 60min)")
        plt.title(f"Activity Graph")
        plt.legend((graph, *[n[0] for n in existing_graphs]), (clan[0], *[n[1] for n in existing_graphs]))

        self.add_graph(ctx.guild.id, ctx.author.id, (graph, str(clan[0])))

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        await ctx.send(f"query: {(f - s)*1000}ms\nplt: {(time.perf_counter() - s2) * 1000}ms", file=discord.File(b, f'activitygraph.png'))
        plt.close()

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
