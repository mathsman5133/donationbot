import datetime
import logging
from dateutil import relativedelta

from discord.ext import commands, tasks

log = logging.getLogger(__name__)


class SeasonConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.season_id = 0

    @staticmethod
    def next_last_monday():
        now = datetime.datetime.utcnow()
        day = now + relativedelta.relativedelta(month=now.month,
                                                weekday=relativedelta.MO(-1),
                                                day=31,
                                                hour=(-now.hour + 6),
                                                minutes=-now.minute,
                                                seconds=-now.second
                                                )
        return day

    @tasks.loop(time=datetime.time(hour=6, tzinfo=datetime.timezone.utc))
    async def start_new_season(self):
        log.debug('Starting season reset loop.')
        now = datetime.datetime.utcnow()
        next_monday = self.next_last_monday()

        if now.day != next_monday.day:
            return

        log.critical('New season starting - via loop.')
        await self.new_season()

    async def new_season(self):
        query = "INSERT INTO seasons (start, finish) VALUES ($1, $2)"
        await self.bot.pool.execute(query, datetime.datetime.utcnow(), self.next_last_monday())

        self.season_id = await self.get_season_id(refresh=True)

        query = """INSERT INTO players (
                            player_tag,
                            donations,
                            received,
                            user_id,
                            season_id
                            )
                    SELECT player_tag,
                           0,
                           0,
                           user_id,
                           season_id + 1
                    FROM players
                    WHERE season_id = $1
                """
        await self.bot.pool.execute(query, self.season_id - 1)

    async def get_season_id(self, refresh: bool = False):
        if self.season_id and not refresh:
            return self.season_id

        query = "SELECT id FROM seasons WHERE start < CURRENT_TIMESTAMP ORDER BY start DESC;"
        fetch = await self.bot.pool.fetchrow(query)
        if not fetch:
            return

        self.season_id = fetch[0]
        return self.season_id

    async def new_season_pull(self):
        query = "SELECT DISTINCT player_tag FROM players WHERE season_id = $1 AND start_update = False"
        fetch = await self.bot.pool.fetch(query, await self.get_season_id())

        query = """UPDATE players SET start_friend_in_need = x.friend_in_need, 
                                      start_sharing_is_caring = x.sharing_is_caring,
                                      start_attacks = x.start_attacks,
                                      start_defenses = x.start_defenses,
                                      start_best_trophies = x.start_best_trophies
                                       
                    FROM(
                        SELECT x.player_tag, 
                               x.friend_in_need, 
                               x.sharing_is_caring,
                               x.start_attacks,
                               x.start_defenses,
                               x.start_best_trophies
                               
                        FROM jsonb_to_recordset($1::jsonb)
                        AS x(
                            player_tag TEXT, 
                            friend_in_need INTEGER, 
                            sharing_is_caring INTEGER,
                            start_attacks INTEGER,
                            start_defenses INTEGER,
                            start_best_trophies INTEGER
                            )
                        )
                AS x
                WHERE players.player_tag = x.player_tag
                AND players.season_id=$2
                """
        season_id = await self.get_season_id()

        counter = 0
        data = []
        async for player in self.bot.coc.get_players((n[0] for n in fetch)):
            if counter == 100:
                # This is basically to ensure we don't have 10k records in memory at any one time.
                # Safety net incase something fails, too.
                await self.bot.pool.execute(query, data, season_id)
                await self.insert_final(self.bot.pool, data, season_id)
                data.clear()
                counter = 0

            data.append({
                'player_tag': player.tag,
                'friend_in_need': player.achievements_dict['Friend in Need'].value,
                'sharing_is_caring': player.achievements_dict['Sharing is caring'].value,
                'attacks': player.attack_wins,
                'defenses': player.defense_wins,
                'best_trophies': player.best_trophies
            })
            counter += 1

    @staticmethod
    async def insert_final(con, data, season_id):
        query = """UPDATE players SET end_friend_in_need    = x.friend_in_need, 
                                      end_sharing_is_caring = x.sharing_is_caring,
                                      end_attacks           = x.attacks,
                                      end_defenses          = x.defenses,
                                      end_best_trophies     = x.best_trophies,
                                      final_update          = True

                    FROM(
                        SELECT x.player_tag, 
                               x.friend_in_need, 
                               x.sharing_is_caring,
                               x.attacks,
                               x.defenses,
                               x.best_trophies
                               
                        FROM jsonb_to_recordset($1::jsonb)
                        AS x(
                            player_tag TEXT, 
                            friend_in_need INTEGER, 
                            sharing_is_caring INTEGER,
                            attacks INTEGER,
                            defenses INTEGER,
                            best_trophies INTEGER
                            )
                        )
                AS x
                WHERE players.player_tag = x.player_tag
                AND players.season_id=$2
                """
        await con.execute(query, data, season_id - 1)

    @commands.command()
    @commands.is_owner()
    async def resetseason(self, ctx):
        prompt = await ctx.prompt('Are you sure?')
        if not prompt:
            return

        season_id = await self.get_season_id(refresh=True)
        if not season_id:
            return await ctx.send('Something strange happened...')

        prompt = await ctx.prompt(f'Current season found: ID {season_id}.\n'
                                  f'Would you like to create a new one anyway?')

        if not prompt:
            return

        await self.new_season()
        await self.get_season_id(refresh=True)
        await ctx.confirm()

    @commands.command()
    @commands.is_owner()
    async def startingdump(self, ctx):
        await self.new_season_pull()
        await ctx.confirm()

    async def event_management(self):
        pass  # todo: management for start and end of events


def setup(bot):
    bot.add_cog(SeasonConfig(bot))
