from datetime import datetime
import discord
import traceback

from discord.ext import commands

from cogs.donations import ArgConverter, PlayerConverter, ClanConverter
from cogs.utils.emoji_lookup import number_emojis
from cogs.utils.paginator import SeasonStatsPaginator


class Season(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))
        traceback.print_exc()

    async def build_season_clan_misc_stats(self, ctx, clans):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Overview for {ctx.guild.name}')

        query = """SELECT COUNT(*), 
                          MIN(time),
                          SUM(donations),
                          SUM(received)
                   FROM events 
                   WHERE clan_tag=ANY($1::TEXT[])
                """
        count = await ctx.db.fetchrow(query, clan_tags)

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
                          for i, (command, uses) in enumerate(fetch))
        e.add_field(name='Top Commands',
                    value=value)
        return e

    async def build_season_clan_event_stats(self, ctx, clans):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Event Stats for {ctx.guild.name}')
        query = """SELECT clans.clan_name,
                          COUNT(*) AS "uses"
                   FROM events
                   INNER JOIN clans
                        ON events.clan_tag=clans.clan_tag
                   WHERE events.clan_tag=ANY($1::TEXT[])
                   GROUP BY clans.clan_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch))
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
                   GROUP BY clans.clan_name
                   ORDER BY "donations" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({don} donations)'
                          for (i, (name, don)) in enumerate(fetch))
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
                   GROUP BY clans.clan_name
                   ORDER BY "received" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({rec} received)'
                          for (i, (name, rec)) in enumerate(fetch))
        e.add_field(name='Top Clan Received',
                    value=value,
                    inline=False
                    )

        query = """SELECT player_name,
                          COUNT(*) AS "uses"
                   FROM events
                   WHERE clan_tag=ANY($1::TEXT[])
                   GROUP BY player_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                   """
        fetch = await ctx.db.fetch(query, clan_tags)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch))
        e.add_field(name='Top Player Events',
                    value=value,
                    inline=False
                    )
        return e

    async def build_season_clan_player_stats(self, ctx, clans):
        clan_tags = [n.tag for n in clans]

        e = discord.Embed(colour=self.bot.colour,
                          title=f'Season Player Stats for {ctx.guild.name}')
        query = """SELECT player_name,
                          COUNT(*) AS "uses"
                   FROM events
                   WHERE clan_tag=ANY($1::TEXT[])
                   GROUP BY player_name
                   ORDER BY "uses" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)

        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({events} events)'
                          for (i, (name, events)) in enumerate(fetch))
        e.add_field(name='Top 5 Players - By Events',
                    value=value,
                    inline=False
                    )

        query = """SELECT player_name,
                          SUM(donations) AS "donations"
                   FROM events
                   WHERE clan_tag=ANY($1::TEXT[])
                   GROUP BY player_name
                   ORDER BY "donations" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({don} donations)'
                          for (i, (name, don)) in enumerate(fetch))
        e.add_field(name='Top 5 Players - By Donations',
                    value=value,
                    inline=False
                    )

        query = """SELECT player_name,
                          SUM(received) AS "received"
                   FROM events
                   WHERE clan_tag=ANY($1::TEXT[])
                   GROUP BY player_name
                   ORDER BY "received" DESC
                   LIMIT 5;
                """
        fetch = await ctx.db.fetch(query, clan_tags)
        value = '\n'.join(f'{number_emojis[i + 1]}: {name} ({rec} received)'
                          for (i, (name, rec)) in enumerate(fetch))
        e.add_field(name='Top 5 Players - By Received',
                    value=value,
                    inline=False
                    )
        return e

    @commands.group(invoke_without_subcommand=True)
    async def season(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.show_help(ctx.command)

    @season.group(name='stats')
    async def season_stats(self, ctx, *, arg: ArgConverter = None):
        if not arg:
            arg = await ctx.get_clans()
        await ctx.invoke(self.season_stats_clan, clan=arg)

    @season_stats.command(name='player')
    async def season_stats_player(self, ctx, *, player: PlayerConverter):
        pass

    @season_stats.command(name='user')
    async def season_stats_user(self, ctx, *, user: discord.Member = None):
        user = user or ctx.author

    @season_stats.command(name='clan')
    async def season_stats_clan(self, ctx, *, clan: ClanConverter):
        entries = [
            await self.build_season_clan_misc_stats(ctx, clans=clan),
            await self.build_season_clan_event_stats(ctx, clans=clan),
            await self.build_season_clan_player_stats(ctx, clans=clan)
        ]
        p = SeasonStatsPaginator(ctx, entries=entries)
        await p.paginate()


def setup(bot):
    bot.add_cog(Season(bot))
