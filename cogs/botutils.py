import discord

from discord.ext import commands

from cogs.utils.cache import cache
from cogs.utils.db_objects import DatabaseClan, LogConfig


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @cache()
    async def donation_log_config(self, channel_id):
        query = """SELECT guild_id, channel_id, donlog_interval, donlog_toggle 
                   FROM clans WHERE channel_id=$1
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id)
        if not fetch:
            return None

        return LogConfig(bot=self.bot,
                         guild_id=fetch['guild_id'],
                         channel_id=fetch['channel_id'],
                         interval=fetch['donevents_interval'],
                         toggle=fetch['donevents_toggle']
                         )

    @cache()
    async def trophy_log_config(self, channel_id):
        query = """SELECT guild_id, channel_id, trophylog_interval, trophylog_toggle 
                       FROM clans WHERE channel_id=$1
                    """
        fetch = await self.bot.pool.fetchrow(query, channel_id)
        if not fetch:
            return None

        return LogConfig(bot=self.bot,
                         guild_id=fetch['guild_id'],
                         channel_id=fetch['channel_id'],
                         interval=fetch['donevents_interval'],
                         toggle=fetch['donevents_toggle']
                         )

    @cache()
    async def get_channel_config(self, channel_id):
        query = """SELECT id, guild_id, clan_tag, clan_name, 
                              channel_id, log_interval, log_toggle 
                        FROM clans WHERE channel_id=$1
                    """
        fetch = await self.bot.pool.fetchrow(query, channel_id)

        if not fetch:
            return None

        return DatabaseClan(bot=self.bot, record=fetch)

    def invalidate_channel_configs(self, channel_id):
        self.get_channel_config.invalidate(self, channel_id)
        task = self.bot.donationlogs._tasks.pop(channel_id, None)
        if task:
            task.cancel()

    @cache()
    async def get_clan_name(self, guild_id, tag):
        query = "SELECT clan_name FROM clans WHERE clan_tag=$1 AND guild_id=$2"
        fetch = await self.bot.pool.fetchrow(query, tag, guild_id)
        if not fetch:
            return 'Unknown'
        return fetch[0]

    @cache()
    async def get_message(self, channel, message_id):
        try:
            o = discord.Object(id=message_id + 1)
            # don't wanna use get_message due to poor rate limit (1/1s) vs (50/1s)
            msg = await channel.history(limit=1, before=o).next()

            if msg.id != message_id:
                return None

            return msg
        except Exception:
            return None

