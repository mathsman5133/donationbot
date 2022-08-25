from datetime import datetime
import logging
import asyncio
from dateutil import relativedelta
import calendar
import pytz
import discord
import time

from cogs.utils.db_objects import BoardConfig

from discord.ext import commands, tasks

log = logging.getLogger(__name__)

REFRESH_EMOJI = discord.PartialEmoji(name="refresh", id=694395354841350254, animated=False)
LEFT_EMOJI = discord.PartialEmoji(name="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)    # [:arrow_left:]
RIGHT_EMOJI = discord.PartialEmoji(name="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)   # [:arrow_right:]
PERCENTAGE_EMOJI = discord.PartialEmoji(name="percent", id=694463772135260169, animated=False)
GAIN_EMOJI = discord.PartialEmoji(name="gain", id=696280508933472256, animated=False)
LAST_ONLINE_EMOJI = discord.PartialEmoji(name="lastonline", id=696292732599271434, animated=False)
HISTORICAL_EMOJI = discord.PartialEmoji(name="historical", id=694812540290465832, animated=False)


class SeasonConfig(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.season_id = 0
        #self.start_new_season.start()

    @staticmethod
    def next_last_monday():
        now = datetime.utcnow()
        day = now + relativedelta.relativedelta(month=now.month + 1,
                                                weekday=relativedelta.MO(-1))
        day.replace(hour=6, minute=0, second=0, microsecond=0)
        return day

    async def _new_season(self):
        log.critical('New season starting - via loop.')
        await self.new_season()

    async def new_season(self):
        query = "INSERT INTO seasons (start, finish) VALUES (now(), $1)"
        await self.bot.pool.execute(query, self.next_last_monday())

        self.season_id = await self.get_season_id(refresh=True)

        query = """INSERT INTO players (
                            player_tag,
                            donations,
                            received,
                            user_id,
                            season_id,
                            player_name,
                            start_trophies
                            )
                    SELECT player_tag,
                           0,
                           0,
                           user_id,
                           season_id + 1,
                           player_name,
                           trophies
                    FROM players
                    WHERE season_id = $1
                """
        await self.bot.pool.execute(query, self.season_id - 1)
        query = "UPDATE players SET start_trophies = 5000 WHERE start_trophies > 5000 AND season_id = $1"
        await self.bot.pool.execute(query, self.season_id)

    async def get_season_id(self, refresh: bool = False):
        if self.season_id and not refresh:
            return self.season_id

        query = "SELECT id FROM seasons WHERE start < now() ORDER BY start DESC;"
        fetch = await self.bot.pool.fetchrow(query)
        if not fetch:
            return

        self.season_id = fetch[0]
        return self.season_id

    async def reset_boards(self):
        s = time.perf_counter()
        query = "SELECT * FROM boards WHERE boards.toggle=True"
        query2 = "UPDATE boards SET message_id = $1 WHERE message_id = $2"
        fetch = await self.bot.pool.fetch(query)
        counter = 0
        for row in fetch:
            counter += 1
            channel = self.bot.get_channel(row['channel_id'])
            message_id = row['message_id']
            type = row['type']
            if not channel or not message_id:
                continue
            message = await self.bot.utils.get_message(channel, message_id)

            if not message:
                return

            if 'Placeholder' in message.content:
                continue

            config = BoardConfig(record=row, bot=self.bot)
            try:
                await self.bot.donationboard.new_donationboard_updater(config, reset=True)
            except discord.HTTPException:
                pass

            try:
                await message.clear_reactions()
            except (discord.Forbidden, discord.HTTPException):
                pass

            try:
                new_msg = await channel.send("Placeholder for the next season's board. Please don't delete me!")
            except (discord.Forbidden, discord.HTTPException):
                continue

            if type == "donation":
                reactions = (
                    REFRESH_EMOJI,
                    LEFT_EMOJI,
                    RIGHT_EMOJI,
                    PERCENTAGE_EMOJI,
                    LAST_ONLINE_EMOJI,
                    HISTORICAL_EMOJI,
                )
            elif type == "trophy":
                reactions = (
                    REFRESH_EMOJI,
                    LEFT_EMOJI,
                    RIGHT_EMOJI,
                    GAIN_EMOJI,
                    LAST_ONLINE_EMOJI,
                    HISTORICAL_EMOJI
                )
            else:
                reactions = ()
            try:
                for r in reactions:
                    await new_msg.add_reaction(r)
            except (discord.Forbidden, discord.HTTPException):
                pass

            await self.bot.pool.execute(query2, new_msg.id, message_id)
            if counter == 50:
                log.info(f'counter:{counter}')

        log.critical(f"boards reset loop took {(time.perf_counter() - s)*1000}ms.")

    async def new_season_pull(self):
        s = time.perf_counter()
        season_id = await self.get_season_id()
        query = "SELECT DISTINCT player_tag FROM players WHERE season_id = $1 AND start_update = False;"
        fetch = await self.bot.pool.fetch(query, season_id)

        tasks_ = []
        for i in range(int(len(fetch) / 100)):
            task = asyncio.ensure_future(self.get_and_do_updates((n[0] for n in fetch[i:i+100]), season_id))
            tasks_.append(task)

        await asyncio.gather(*tasks_)
        log.critical(f"new season pull done, took {(time.perf_counter() - s)*1000}ms")

    async def get_and_do_updates(self, player_tags, season_id):
        s = time.perf_counter()
        query = """UPDATE players SET start_friend_in_need = x.friend_in_need, 
                                      start_sharing_is_caring = x.sharing_is_caring,
                                      start_attacks = x.attacks,
                                      start_defenses = x.defenses,
                                      start_trophies = x.trophies,
                                      start_best_trophies = x.best_trophies,
                                      start_update = True,
                                      ignore = TRUE

                    FROM(
                        SELECT x.player_tag, 
                               x.friend_in_need, 
                               x.sharing_is_caring,
                               x.attacks,
                               x.defenses,
                               x.trophies,
                               x.best_trophies

                        FROM jsonb_to_recordset($1::jsonb)
                        AS x(
                            player_tag TEXT, 
                            friend_in_need INTEGER, 
                            sharing_is_caring INTEGER,
                            attacks INTEGER,
                            defenses INTEGER,
                            trophies INTEGER,
                            best_trophies INTEGER
                            )
                        )
                AS x
                WHERE players.player_tag = x.player_tag
                AND players.season_id=$2
                """
        query2 = """UPDATE players SET end_friend_in_need = x.friend_in_need, 
                                      end_sharing_is_caring = x.sharing_is_caring,
                                      end_attacks = x.attacks,
                                      end_defenses = x.defenses,
                                      end_best_trophies = x.best_trophies,
                                      final_update = True,
                                      ignore = TRUE

                    FROM(
                        SELECT x.player_tag, 
                               x.friend_in_need, 
                               x.sharing_is_caring,
                               x.attacks,
                               x.defenses,
                               x.trophies,
                               x.best_trophies

                        FROM jsonb_to_recordset($1::jsonb)
                        AS x(
                            player_tag TEXT, 
                            friend_in_need INTEGER, 
                            sharing_is_caring INTEGER,
                            attacks INTEGER,
                            defenses INTEGER,
                            trophies INTEGER,
                            best_trophies INTEGER
                            )
                        )
                AS x
                WHERE players.player_tag = x.player_tag
                AND players.season_id=$2"""

        data = []
        async for player in self.bot.coc.get_players(player_tags):
            data.append({
                'player_tag': player.tag,
                'friend_in_need': player.get_achievement('Friend in Need').value,
                'sharing_is_caring': player.get_achievement('Sharing is caring').value,
                'attacks': player.attack_wins,
                'defenses': player.defense_wins,
                'trophies': player.trophies,
                'best_trophies': player.best_trophies
            })

        q = await self.bot.pool.execute(query, data, season_id)
        q2 = await self.bot.pool.execute(query2, data, season_id - 1)
        log.info(f"Done update players: {q}, {q2}, {(time.perf_counter() - s)*1000}ms")

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

        await self._new_season()
        await self.get_season_id(refresh=True)
        await ctx.confirm()

    @commands.command()
    @commands.is_owner()
    async def startingdump(self, ctx, number: int = 1000):
        await self.new_season_pull(number)
        await ctx.confirm()

    async def event_management(self):
        pass  # todo: management for start and end of events


async def setup(bot):
    await bot.add_cog(SeasonConfig(bot))
