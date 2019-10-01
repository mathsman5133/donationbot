from datetime import datetime
import discord
import math
import traceback
import typing

from discord.ext import commands

from cogs.donations import ClanConverter
from cogs.boards import MockPlayer
from cogs.utils.emoji_lookup import number_emojis
from cogs.utils.error_handler import error_handler
from cogs.utils.paginator import SeasonStatsPaginator
from cogs.utils.formatters import TabularData, readable_time, CLYTable
from cogs.utils.cache import cache
from cogs.utils.db_objects import DatabasePlayer


class Season(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.season_stats_guild_entries = {}
        self.season_stats_user_entries = {}

    @cache()
    async def build_season_clan_misc_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Overview for {ctx.guild.name}')

        query = """SELECT COUNT(*), 
                          MIN(time),
                          SUM(donations),
                          SUM(received)
                   FROM events 
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

    @cache()
    async def build_season_clan_event_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Event Stats for {ctx.guild.name}')
        query = """SELECT clans.clan_name,
                          COUNT(*) AS "uses"
                   FROM events
                   INNER JOIN clans
                        ON events.clan_tag=clans.clan_tag
                   WHERE events.clan_tag=ANY($1::TEXT[])
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
                   FROM events
                   INNER JOIN clans
                        ON events.clan_tag=clans.clan_tag
                   WHERE events.clan_tag=ANY($1::TEXT[])
                   AND events.season_id=$2
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
                   FROM events
                   INNER JOIN clans
                        ON events.clan_tag=clans.clan_tag
                   WHERE events.clan_tag=ANY($1::TEXT[])
                   AND events.season_id=$2
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
                   FROM events
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

    @cache()
    async def build_season_clan_player_stats(self, ctx, clans, season_id):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Player Stats for {ctx.guild.name}')
        query = """SELECT player_name,
                          COUNT(*) AS "uses"
                   FROM events
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

        query = """SELECT events.player_name,
                          SUM(DISTINCT players.donations) as "donations"
                   FROM players
                   INNER JOIN events 
                        ON events.player_tag=players.player_tag
                        AND events.season_id=players.season_id
                   WHERE events.clan_tag=ANY($1::TEXT[])
                   AND events.season_id=$2
                   AND events.player_name IS NOT NULL
                   GROUP BY events.player_name
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

        query = """SELECT events.player_name,
                          SUM(DISTINCT players.received) as "received"
                   FROM players
                   INNER JOIN events 
                        ON events.player_tag=players.player_tag
                        AND events.season_id=players.season_id
                   WHERE events.clan_tag=ANY($1::TEXT[])
                   AND events.season_id=$2
                   AND events.player_name IS NOT NULL
                   GROUP BY events.player_name
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

    @cache()
    async def build_season_user_misc_stats(self, ctx, user, season_id):
        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Overview for {user}')

        query = """SELECT COUNT(*), 
                          MIN(events.time),
                          SUM(players.donations),
                          SUM(players.received)
                   FROM events
                   INNER JOIN players
                        ON events.player_tag=players.player_tag
                        AND events.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND events.season_id=$2
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

    @cache()
    async def build_season_user_player_stats(self, ctx, user, season_id):
        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Player Stats for {user}')
        query = """SELECT events.player_name,
                          COUNT(*) AS "uses"
                   FROM events
                   INNER JOIN players
                        ON players.player_tag=events.player_tag
                        AND players.season_id=events.season_id
                   WHERE players.user_id=$1
                   AND events.season_id=$2
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

        query = """SELECT events.player_name,
                          SUM(DISTINCT players.donations) as "donations"
                   FROM players
                   INNER JOIN events 
                        ON events.player_tag=players.player_tag
                        AND events.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND events.season_id=$2
                   AND events.player_name IS NOT NULL
                   GROUP BY events.player_name
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

        query = """SELECT events.player_name,
                          SUM(DISTINCT players.received) as "received"
                   FROM players
                   INNER JOIN events 
                        ON events.player_tag=players.player_tag
                        AND events.season_id=players.season_id
                   WHERE players.user_id=$1
                   AND events.season_id=$2
                   AND events.player_name IS NOT NULL
                   GROUP BY events.player_name
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

    @cache()
    async def get_donationboard(self, guild_id, season_id):
        query = "SELECT DISTINCT clan_tag FROM clans WHERE guild_id=$1"
        fetch = await self.bot.pool.fetch(query, guild_id)
        clans = await self.bot.coc.get_clans((n[0] for n in fetch)).flatten()
        guild_config = await self.bot.donationboard.get_guild_config(guild_id)

        players = []
        for n in clans:
            players.extend(p for p in n.itermembers)

        query = """SELECT player_tag, donations, received
                    FROM players 
                    WHERE player_tag=ANY($1::TEXT[])
                    AND season_id=$2
                    ORDER BY donations DESC
                    LIMIT 100;
                """
        fetch = await self.bot.pool.fetch(query, [n.tag for n in players], season_id)
        if not fetch:
            e = discord.Embed(colour=self.bot.colour,
                              title='No Donations Found')
            return [e]
        db_players = [DatabasePlayer(bot=self.bot, record=n) for n in fetch]
        players = {n.tag: n for n in players if n.tag in set(x.player_tag for x in db_players)}

        message_count = math.ceil(len(db_players) / 20)

        embeds = []
        for i in range(message_count):
            player_data = db_players[i * 20:(i + 1) * 20]
            table = CLYTable()

            for x, y in enumerate(player_data):
                index = i * 20 + x
                if guild_config.donationboard_render == 2:
                    table.add_row([index,
                                   y.donations,
                                   players.get(y.player_tag, MockPlayer()).name])
                else:
                    table.add_row([index,
                                   y.donations,
                                   y.received,
                                   players.get(y.player_tag, MockPlayer()).name
                                   ]
                                  )

            fmt = table.render_option_2() if \
                guild_config.donationboard_render == 2 else table.render_option_1()
            e = discord.Embed(colour=self.bot.colour,
                              description=fmt,
                              timestamp=datetime.utcnow())
            e.set_author(name=guild_config.donationboard_title or 'DonationBoard',
                         icon_url=guild_config.icon_url or 'https://cdn.discordapp.com/'
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
                    value=readable_time((fetch[0][2] - fetch[0][1]).total_seconds()) + ' left',
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
        return await ctx.send('This command is not available at the moment. Sorry!')

        query = "SELECT COUNT(*) FROM events WHERE clan_tag=ANY($1::TEXT[]) AND"
        embeds = await self.get_donationboard(ctx.guild.id, season
                                              or (await self.bot.seasonconfig.get_season_id()) - 1)
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
        return await ctx.send('This command is not available at the moment. Sorry!')

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
        season = season or await self.bot.seasonconfig.get_season_id()

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

        season = season or await self.bot.seasonconfig.get_season_id()

        entries = [
            await self.build_season_clan_misc_stats(ctx, clan, season),
            await self.build_season_clan_event_stats(ctx, clan, season),
            await self.build_season_clan_player_stats(ctx, clan, season)
        ]

        p = SeasonStatsPaginator(ctx, entries=entries)
        await p.paginate()


def setup(bot):
    bot.add_cog(Season(bot))
