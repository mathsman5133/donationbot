from datetime import datetime
import discord
import math
import typing

from discord.ext import commands

from cogs.boards import MockPlayer
from cogs.utils.paginator import SeasonStatsPaginator
from cogs.utils.formatters import CLYTable, get_render_type
from cogs.utils.cache import cache, Strategy
from cogs.utils.emoji_lookup import misc

mock = MockPlayer('Unknown', 'Unknown')


class SeasonStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.before_invoke(ctx)

    async def cog_after_invoke(self, ctx):
        after_invoke = getattr(ctx, 'after_invoke', None)
        if after_invoke:
            await after_invoke(ctx)

    @cache(strategy=Strategy.lru)
    async def get_board_fmt(self, guild_id, season_id, board_type):
        board_config = await self.bot.utils.get_board_config(guild_id, board_type)
        clans = await self.bot.get_clans(guild_id)

        players = []
        for n in clans:
            players.extend(p for p in n.itermembers)

        top_players = await self.bot.donationboard.get_top_players(players, board_type, False)

        if not top_players:
            e = discord.Embed(colour=self.bot.colour,
                              title='No Donations Found')
            return [e]

        players = {n.tag: n for n in players if n.tag in set(x['player_tag'] for x in top_players)}

        message_count = math.ceil(len(top_players) / 20)

        embeds = []
        for i in range(message_count):
            player_data = top_players[i*20:(i+1)*20]
            table = CLYTable()

            for x, y in enumerate(player_data):
                index = i*20 + x
                if board_config.render == 2:
                    table.add_row([index,
                                   y[1],
                                   players.get(y['player_tag'], mock).name])
                else:
                    table.add_row([index,
                                   y[1],
                                   y[2],
                                   players.get(y['player_tag'], mock).name])

            render = get_render_type(board_config, table)
            fmt = render()

            e = discord.Embed(colour=self.bot.donationboard.get_colour(board_type, False),
                              description=fmt,
                              timestamp=datetime.utcnow()
                              )
            e.set_author(name=board_config.title,
                         icon_url=board_config.icon_url or 'https://cdn.discordapp.com/'
                                                           'emojis/592028799768592405.png?v=1')
            e.set_footer(text=f'Historical DonationBoard; Season {season_id} - Page {i+1}/{message_count}')
            embeds.append(e)

        return embeds

    @commands.group(invoke_without_subcommand=True)
    async def seasonstats(self, ctx):
        """[Group] command to manage historical stats for seasons past."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @seasonstats.command(name='donationboard')
    async def seasonstats_donationboard(self, ctx, season: typing.Optional[int] = None):
        """Get historical donationoard stats.

        *Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+seasonstats donationboard`
        :white_check_mark: `+seasonstats donationboard 2`
        """
        embeds = await self.get_board_fmt(ctx.guild.id, season or (await self.bot.seasonconfig.get_season_id()) - 1,
                                          'donation')
        p = SeasonStatsPaginator(ctx, entries=embeds)
        await p.paginate()

    @seasonstats.command(name='attacks')
    async def seasonstats_attacks(self, ctx, season: typing.Optional[int] = None):
        """Get attack wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+season stats attacks`
        :white_check_mark: `+season stats attacks 2`
        """
        season = season or await self.bot.seasonconfig.get_season_id() - 1

        clans = await ctx.get_clans()
        query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
               FROM players 
               WHERE player_tag = ANY($1::TEXT[])
               AND season_id = $2
               ORDER BY attacks DESC
               LIMIT 15
            """

        players = []
        for clan in clans:
            players.extend((n.tag for n in clan.itermembers))

        fetch = await ctx.db.execute(query, players, season)

        table = CLYTable()
        title = f"Attack wins for Season {season}"

        attacks = {n['player_tag']: n['attacks'] for n in fetch}
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, attacks[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_attacks()
        fmt += f"**Key:**\n{misc['attack']} - Attacks\n{misc['trophygold']} - Trophies"

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)

    @seasonstats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    async def seasonstats_defenses(self, ctx, season: typing.Optional[int] = None):
        """Get defense wins for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+season stats defenses`
        :white_check_mark: `+season stats defenses 3`
        """
        season = season or await self.bot.seasonconfig.get_season_id() - 1
        clans = await ctx.get_clans()
        query = """SELECT player_tag, end_defenses - start_defenses as defenses, trophies 
                   FROM players 
                   WHERE player_tag = ANY($1::TEXT[])
                   AND season_id = $2
                   ORDER BY defenses DESC
                   LIMIT 15
                """

        players = []
        for clan in clans:
            players.extend((n.tag for n in clan.itermembers))

        fetch = await ctx.db.execute(query, players, season)

        table = CLYTable()
        title = f"Defense wins for Season {season}"

        defenses = {n['player_tag']: n['defenses'] for n in fetch}
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, defenses[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_defenses()
        fmt += f"**Key:**\n{misc['defense']} - Defenses\n{misc['trophygold']} - Trophies"

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)

    @seasonstats.command(name='gains', aliases=['trophies'])
    async def seasonstats_gains(self, ctx, season: typing.Optional[int] = None):
        """Get trophy gains for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+season stats gains`
        :white_check_mark: `+season stats gains 1`
        """

        season = season or await self.bot.seasonconfig.get_season_id() - 1
        clans = await ctx.get_clans()
        query = """SELECT player_tag, trophies - start_trophies as gain, trophies 
                   FROM players 
                   WHERE player_tag = ANY($1::TEXT[])
                   AND season_id = $2
                   ORDER BY gain DESC
                   LIMIT 15
                """

        players = []
        for clan in clans:
            players.extend((n.tag for n in clan.itermembers))

        fetch = await ctx.db.execute(query, players, season)

        table = CLYTable()
        title = f"Trophy Gains for Season {season}"

        gains = {n['player_tag']: n['gain'] for n in fetch}
        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, gains[player.tag], player.trophies, player.name])

        fmt = table.trophyboard_gain()
        fmt += f"**Key:**\n{misc['trophygreen']} - Trophy Gain\n{misc['trophygold']} - Total Trophies"

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)

    @seasonstats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    async def seasonstats_donors(self, ctx, season: typing.Optional[int] = None):
        """Get donations for all clans.

        **Parameters**
        :key: Season ID (optional - defaults to last season)

        **Example**
        :white_check_mark: `+season stats donors`
        :white_check_mark: `+season stats donations 4`
        """

        season = season or await self.bot.seasonconfig.get_season_id() - 1
        clans = await ctx.get_clans()
        query = """SELECT player_tag, (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                   FROM players 
                   WHERE player_tag = ANY($1::TEXT[])
                   AND season_id = $2
                   ORDER BY donations DESC
                   LIMIT 15
                """

        players = []
        for clan in clans:
            players.extend((n.tag for n in clan.itermembers))

        fetch = await ctx.db.execute(query, players, season)

        table = CLYTable()
        title = f"Donations for Season {season}"

        donations = {n['player_tag']: n['donations'] for n in fetch}

        for index, player in enumerate(await self.bot.coc.get_players((n[0] for n in fetch)).flatten()):
            table.add_row([index, donations[player.tag], player.name])

        fmt = table.donationboard_2()

        e = discord.Embed(
            colour=discord.Colour.green(), description=fmt, title=title
        )

        await ctx.send(embed=e)


def setup(bot):
    bot.add_cog(SeasonStats(bot))
