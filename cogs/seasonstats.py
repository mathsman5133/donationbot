from datetime import datetime
import discord
import math
import traceback
import typing

from discord.ext import commands

from cogs.donations import ClanConverter
from cogs.boards import MockPlayer
from cogs.utils.emoji_lookup import number_emojis
from cogs.utils.paginator import SeasonStatsPaginator
from cogs.utils.formatters import TabularData, readable_time, CLYTable, get_render_type
from cogs.utils.cache import cache, Strategy

mock = MockPlayer('Unknown', 'Unknown')


class Season(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.season_stats_guild_entries = {}
        self.season_stats_user_entries = {}

    @cache(strategy=Strategy.lru)
    async def build_season_clan_misc_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Overview for {ctx.guild.name}')

        query = """SELECT COUNT(*), 
                          MIN(time),
                          SUM(donations),
                          SUM(received)
                   FROM donationevents 
                   WHERE clan_tag=ANY($1::TEXT[])
                   AND season_id=$2
                """
        count = await ctx.db.fetchrow(query, clan_tags, season_id)

        fmt = f'{count[0]} events\n{count[2]} donations\n{count[3]} received'
        e.add_field(name='Total Stats',
                    value=fmt,
                    inline=False)
        e.set_footer(text='First event tracked').timestamp = count[1] or datetime.utcnow()

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE guild_id=$1
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, ctx.guild.id)
        value = '\n'.join(f'{number_emojis[i+1]}: {command} ({uses} uses)'
                          for i, (command, uses) in enumerate(fetch)) or 'No Commands.'
        e.add_field(name='Top Commands',
                    value=value)
        return e

    @cache(strategy=Strategy.lru)
    async def build_season_clan_event_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Event Stats for {ctx.guild.name}')
        query = """SELECT clans.clan_name,
                          COUNT(*) AS "uses"
                   FROM donationevents
                   INNER JOIN clans
                        ON donationevents.clan_tag=clans.clan_tag
                   WHERE donationevents.clan_tag=ANY($1::TEXT[])
                   AND season_id=$2
                   GROUP BY clans.clan_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch)) or 'No Clans'
        e.add_field(name='Top Clan Events',
                    value=value,
                    inline=False
                    )

        query = """SELECT clans.clan_name,
                          SUM(donations) AS "donations"
                   FROM donationevents
                   INNER JOIN clans
                        ON donationevents.clan_tag=clans.clan_tag
                   WHERE donationevents.clan_tag=ANY($1::TEXT[])
                   AND donationevents.season_id=$2
                   GROUP BY clans.clan_name
                   ORDER BY "donations" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({don} donations)'
                          for (i, (name, don)) in enumerate(fetch)) or 'No Clans'
        e.add_field(name='Top Clan Donations',
                    value=value,
                    inline=False
                    )

        query = """SELECT clans.clan_name,
                          SUM(received) AS "received"
                   FROM donationevents
                   INNER JOIN clans
                        ON donationevents.clan_tag=clans.clan_tag
                   WHERE donationevents.clan_tag=ANY($1::TEXT[])
                   AND donationevents.season_id=$2
                   GROUP BY clans.clan_name
                   ORDER BY "received" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({rec} received)'
                          for (i, (name, rec)) in enumerate(fetch)) or 'No Clans'
        e.add_field(name='Top Clan Received',
                    value=value,
                    inline=False
                    )

        query = """SELECT player_name,
                          COUNT(*) AS "uses"
                   FROM donationevents
                   WHERE clan_tag=ANY($1::TEXT[])
                   AND season_id=$2
                   AND player_name IS NOT NULL
                   GROUP BY player_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                   """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top Player Events',
                    value=value,
                    inline=False
                    )
        e.set_footer(text='Page 2/3').timestamp = datetime.utcnow()
        return e

    @cache(strategy=Strategy.lru)
    async def build_season_clan_player_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Player Stats for {ctx.guild.name}')
        query = """SELECT player_name,
                          COUNT(*) AS "uses"
                   FROM donationevents
                   WHERE clan_tag=ANY($1::TEXT[])
                   AND season_id=$2
                   AND player_name IS NOT NULL
                   GROUP BY player_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top 5 Players - By Events',
                    value=value,
                    inline=False
                    )

        query = """SELECT donationevents.player_name,
                          SUM(DISTINCT players.donations) as "donations"
                   FROM players
                   INNER JOIN donationevents 
                        ON donationevents.player_tag=players.player_tag
                        AND donationevents.season_id=players.season_id
                   WHERE donationevents.clan_tag=ANY($1::TEXT[])
                   AND donationevents.season_id=$2
                   AND donationevents.player_name IS NOT NULL
                   GROUP BY donationevents.player_name
                   ORDER BY "donations" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({don} donations)'
                          for (i, (name, don)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top 5 Players - By Donations',
                    value=value,
                    inline=False
                    )

        query = """SELECT donationevents.player_name,
                          SUM(DISTINCT players.received) as "received"
                   FROM players
                   INNER JOIN donationevents 
                        ON donationevents.player_tag=players.player_tag
                        AND donationevents.season_id=players.season_id
                   WHERE donationevents.clan_tag=ANY($1::TEXT[])
                   AND donationevents.season_id=$2
                   AND donationevents.player_name IS NOT NULL
                   GROUP BY donationevents.player_name
                   ORDER BY "received" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({rec} received)'
                          for (i, (name, rec)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top 5 Players - By Received',
                    value=value,
                    inline=False
                    )
        e.set_footer(text='Page 3/3').timestamp = datetime.utcnow()
        return e

    @cache(strategy=Strategy.lru)
    async def build_season_user_misc_stats(self, ctx, user, season_id):
        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Overview for {user}')

        query = """SELECT COUNT(*), 
                          MIN(donationevents.time),
                          SUM(players.donations),
                          SUM(players.received)
                   FROM donationevents
                   INNER JOIN players
                        ON donationevents.player_tag=players.player_tag
                        AND donationevents.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND donationevents.season_id=$2
                """
        count = await ctx.db.fetchrow(query, user.id, season_id)

        fmt = f'{count[0]} events\n{count[2]} donations\n{count[3]} received'
        e.add_field(name='Total Stats',
                    value=fmt,
                    inline=False)
        e.set_footer(text='First event tracked').timestamp = count[1] or datetime.utcnow()

        query = """SELECT command,
                          COUNT(*) as "uses"
                   FROM commands
                   WHERE author_id=$1
                   GROUP BY command
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, ctx.guild.id)
        value = '\n'.join(f'{number_emojis[i+1]}: {command} ({uses} uses)'
                          for i, (command, uses) in enumerate(fetch)) or 'No Commands.'
        e.add_field(name='Top Commands',
                    value=value)
        return e

    @cache(strategy=Strategy.lru)
    async def build_season_user_player_stats(self, ctx, user, season_id):
        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Player Stats for {user}')
        query = """SELECT donationevents.player_name,
                          COUNT(*) AS "uses"
                   FROM donationevents
                   INNER JOIN players
                        ON players.player_tag=donationevents.player_tag
                        AND players.season_id=donationevents.season_id
                   WHERE players.user_id=$1
                   AND donationevents.season_id=$2
                   AND player_name IS NOT NULL
                   GROUP BY player_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, user.id, season_id)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch)) or 'No Players.'
        e.add_field(name='Top 5 Players - By Events',
                    value=value,
                    inline=False
                    )

        query = """SELECT donationevents.player_name,
                          SUM(DISTINCT players.donations) as "donations"
                   FROM players
                   INNER JOIN donationevents 
                        ON donationevents.player_tag=players.player_tag
                        AND donationevents.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND donationevents.season_id=$2
                   AND donationevents.player_name IS NOT NULL
                   GROUP BY donationevents.player_name
                   ORDER BY "donations" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, user.id, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({don} donations)'
                          for (i, (name, don)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top 5 Players - By Donations',
                    value=value,
                    inline=False
                    )

        query = """SELECT donationevents.player_name,
                          SUM(DISTINCT players.received) as "received"
                   FROM players
                   INNER JOIN donationevents 
                        ON donationevents.player_tag=players.player_tag
                        AND donationevents.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND donationevents.season_id=$2
                   AND donationevents.player_name IS NOT NULL
                   GROUP BY donationevents.player_name
                   ORDER BY "received" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, user.id, season_id)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({rec} received)'
                          for (i, (name, rec)) in enumerate(fetch)) or 'No Players'
        e.add_field(name='Top 5 Players - By Received',
                    value=value,
                    inline=False
                    )
        e.set_footer(text='Page 2/2').timestamp = datetime.utcnow()
        return e

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
    async def season(self, ctx):
        """[Group] command to manage historical stats for seasons past."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @season.command(name='info')
    async def season_info(self, ctx):
        """Get Season IDs and start/finish times and info."""
        query = "SELECT id, start, finish FROM seasons ORDER BY id DESC"
        fetch = await ctx.db.fetch(query)
        table = TabularData()
        table.set_columns(['ID', 'Start', 'Finish'])
        for n in fetch:
            table.add_row([n[0], n[1].strftime('%d-%b-%Y'), n[2].strftime('%d-%b-%Y')])

        e = discord.Embed(colour=self.bot.colour,
                          description=f'```\n{table.render()}\n```',
                          title='Season Info',
                          timestamp=datetime.utcnow()
                          )
        e.add_field(name='Current Season',
                    value=readable_time((fetch[0][2] - datetime.utcnow()).total_seconds())[:-4] + ' left',
                    inline=False)
        await ctx.send(embed=e)

    @season.command(name='donationboard')
    async def season_donationboard(self, ctx, season: typing.Optional[int] = None):
        """Get a historical donationboard for the given season.

        This command will return a pagination of the top 100 players for the guild, in that season.

        Parameters
        --------------------

            • Season ID: integer - optional. Defaults to the previous season.

        Examples
        ----------------------

        • `+season donationboard 1` - donationboard for season 1
        """
        embeds = await self.get_board_fmt(ctx.guild.id, season or (await self.bot.seasonconfig.get_season_id()) - 1,
                                          'donation')
        p = SeasonStatsPaginator(ctx, entries=embeds)
        await p.paginate()

    @season.group(name='stats')
    async def season_stats(self, ctx, season: typing.Optional[int] = None,
                           *, arg: typing.Union[discord.Member, ClanConverter] = None):
        """Get Overall Season Stats for past seasons.

        This command will give you total clan donations, top players by events, donations etc. and more.

        Parameters
        --------------------

            • Season ID: integer - optional. Defaults to the previous season.
            • Discord user or clan name/tag/`all` - either a mention, user ID, clan tag,
                clan name or `all` for all clans in server.

        Examples
        ----------------------

        • `+season stats 1 all` - season stats for season 1 for all clans in guild.
        • `+season stats #CLAN_TAG` - season stats for previous season for that clan tag.
        • `+season stats 4 @user` - season stats for season 4 for @user.
        """
        if not arg:
            arg = await ctx.get_clans()
        if not season:
            season = (await self.bot.seasonconfig.get_season_id()) - 1

        if isinstance(arg, list):
            await ctx.invoke(self.season_stats_guild, clan=arg, season=season)
        if isinstance(arg, discord.Member):
            await ctx.invoke(self.season_stats_user, user=arg, season=season)

    @season_stats.command(name='user')
    async def season_stats_user(self, ctx, season: typing.Optional[int] = None,
                                *, user: discord.Member = None):
        """Get Overall Season Stats for a User.

        Parameters
        -----------------------
            • Season ID: integer - optional. Defaults to the previous season.
            • Discord user - either a mention, user ID, or user#discrim combo. Defaults to you.

        Examples
        ----------------------

        • `+season stats user 1 @user` - season stats for season 1 for @user.
        • `+season stats` - season stats for previous season for you.
        • `+season stats user @user` - season stats for previous season for @user.
        """
        user = user or ctx.author
        season = season or await self.bot.seasonconfig.get_season_id() - 1

        query = "SELECT player_tag FROM players WHERE user_id=$1"
        fetch = await ctx.db.fetchrow(query, user.id)
        if not fetch:
            return await ctx.send(f'{user} doesn\'t have any claimed accounts.')

        entries = [
            await self.build_season_user_misc_stats(ctx, user, season),
            await self.build_season_user_player_stats(ctx, user, season)
        ]

        p = SeasonStatsPaginator(ctx, entries=entries)
        await p.paginate()

    @season_stats.command(name='guild', aliases=['server'])
    async def season_stats_guild(self, ctx, season: typing.Optional[int] = None,
                                 *, clan: ClanConverter):
        """Get Overall Season Stats for past seasons for a guild.

        Parameters
        --------------------

            • Season ID: integer - optional. Defaults to the previous season.
            • Clan name/tag/`all` - either a clan tag, clan name or `all` for all clans in server.

        Examples
        ----------------------

        • `+season stats guild 1 all` - season stats for season 1 for all clans in guild.
        • `+season stats guild #CLAN_TAG` - season stats for previous season for that clan tag.
        • `+season stats 4 Clan Name` - season stats for season 4 for `Clan Name` clan.
        """
        if not clan:
            return await ctx.send('No claimed clans.')

        season = season or await self.bot.seasonconfig.get_season_id() - 1

        entries = [
            await self.build_season_clan_misc_stats(ctx, clan, season),
            await self.build_season_clan_event_stats(ctx, clan, season),
            await self.build_season_clan_player_stats(ctx, clan, season)
        ]

        p = SeasonStatsPaginator(ctx, entries=entries)
        await p.paginate()

    @season_stats.command(name='attacks')
    async def season_stats_attacks(self, ctx, season: typing.Optional[int] = None):
        """Get attack wins for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+season stats attacks`
        """
        season = season or await self.bot.seasonconfig.get_season_id() - 1
        query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                        FROM players 
                        WHERE season_id = $1 AND guild_id = $2
                        ORDER BY attacks DESC
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, season, ctx.guild.id)
        table = CLYTable()
        table.title = f"Attack wins for Season {season}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['attacks'], player.trophies, player.name])
        render = table.trophyboard_attacks()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.gold(), description=fmt)
        await ctx.send(embed=e)

    @season_stats.command(name='defenses', aliases=['defense', 'defences', 'defence'])
    async def season_stats_defenses(self, ctx, season: typing.Optional[int] = None):
        """Get defense wins for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+season stats defenses`
        """
        season = season or await self.bot.seasonconfig.get_season_id() - 1
        query = """SELECT player_tag, end_defenses - start_defenses as defenses, trophies 
                        FROM players 
                        WHERE season_id = $1 AND guild_id = $2
                        ORDER BY defenses DESC
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, season, ctx.guild.id)
        defenses = {}
        for row in fetch:
            defenses[row['player_tag']] = row['defenses']
        table = CLYTable()
        table.title = f"Defense wins for Season {season}"
        index = 0
        async for player in self.bot.coc.get_players((n[0] for n in fetch)):
            table.add_row([index, defenses[player.tag], player.trophies, player.name])
        render = table.trophyboard_defenses()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.dark_red(), description=fmt)
        await ctx.send(embed=e)

    @season_stats.command(name='gains', aliases=['trophies'])
    async def season_stats_gains(self, ctx, season: typing.Optional[int] = None):
        """Get trophy gains for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+season stats gains`
        """
        season = season or await self.bot.seasonconfig.get_season_id() - 1
        query = """SELECT player_tag, trophies - start_trophies as gain, trophies 
                            FROM players 
                            WHERE season_id = $1 AND guild_id = $2
                            ORDER BY gain DESC
                            LIMIT 15
                        """
        fetch = await ctx.db.fetch(query, season, ctx.guild.id)
        table = CLYTable()
        table.title = f"Trophy Gains for Season {season}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['gains'], player.trophies, player.name])
        render = table.trophyboard_gain()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.green(), description=fmt)
        await ctx.send(embed=e)

    @season_stats.command(name='donors', aliases=['donations', 'donates', 'donation'])
    async def season_stats_donors(self, ctx, season: typing.Optional[int] = None):
        """Get donations for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+season stats donations`
        """
        # TODO Since this is straight donations, might change sql to use donationevents (just want consistent numbers)
        season = season or await self.bot.seasonconfig.get_season_id() - 1
        query = """SELECT player_tag,  
                        (end_friend_in_need + end_sharing_is_caring) - (start_friend_in_need + start_sharing_is_caring) as donations
                        FROM players
                        WHERE season_id = $1 AND guild_id = $2
                        ORDER BY gain DESC
                        LIMIT 15
                    """
        fetch = await ctx.db.fetch(query, season, ctx.guild.id)
        table = CLYTable()
        table.title = f"Donations for Season {season}"
        index = 0
        for row in fetch:
            player = await self.bot.coc.get_player(row['player_tag'])
            table.add_row([index, row['donations'], player.name])
        render = table.donationboard_2()
        fmt = render()

        e = discord.Embed(colour=discord.Colour.green(), description=fmt)
        await ctx.send(embed=e)

def setup(bot):
    bot.add_cog(Season(bot))
