import coc
import discord
import datetime
from dateutil import relativedelta

from discord.ext import commands


class SeasonSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.season_id = 0

    async def get_season_id(self):
        if not self.season_id:
            query = "SELECT id FROM seasons WHERE start < CURRENT_TIMESTAMP ORDER BY start LIMIT 1;"
            fetch = await self.bot.pool.fetchrow(query)
            self.season_id = fetch[0]
        return self.season_id

    @staticmethod
    def next_last_monday():
        return datetime.datetime.utcnow() + \
               relativedelta.relativedelta(day=31, weekday=relativedelta.MO(-1))




def setup(bot):
    bot.add_cog(SeasonSettings(bot))
