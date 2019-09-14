import discord

from discord.ext import commands
from typing import Union

from cogs.utils.cache import cache
from cogs.utils.db_objects import LogConfig, BoardConfig


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @cache()
    async def log_config(self, channel_id, log_type) -> Union[LogConfig, None]:
        query = """SELECT guild_id, 
                          channel_id, 
                          interval, 
                          toggle 
                   FROM logs 
                   WHERE channel_id=$1 
                   AND type=$2
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id, log_type)
        if not fetch:
            return None

        return LogConfig(bot=self.bot, record=fetch)

    def invalidate_channel_configs(self, channel_id):
        self.log_config.invalidate(self, channel_id)
        # todo: fix
        task = self.bot.donationlogs._tasks.pop(channel_id, None)
        if task:
            task.cancel()

    @cache()
    async def board_config(self, channel_id) -> Union[BoardConfig, None]:
        query = """SELECT guild_id, 
                          channel_id,
                          icon_url,
                          title,
                          render,
                          toggle,
                          type,
                          in_event
                   FROM boards 
                   WHERE channel_id = $1
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id)

        if not fetch:
            return None

        return BoardConfig(bot=self.bot, record=fetch)

    @cache()
    async def get_clan_name(self, guild_id, tag) -> str:
        query = "SELECT clan_name FROM clans WHERE clan_tag=$1 AND guild_id=$2"
        fetch = await self.bot.pool.fetchrow(query, tag, guild_id)
        if not fetch:
            return 'Unknown'
        return fetch[0]

    @cache()
    async def get_message(self, channel, message_id) -> Union[discord.Message, None]:
        try:
            o = discord.Object(id=message_id + 1)
            # don't wanna use get_message due to poor rate limit (1/1s) vs (50/1s)
            msg = await channel.history(limit=1, before=o).next()

            if msg.id != message_id:
                return None

            return msg
        except Exception:
            return None

    async def update_clan_tags(self):
        query = "SELECT DISTINCT clan_tag FROM clans"
        fetch = await self.bot.pool.fetch(query)
        self.bot.coc._clan_updates = [n[0] for n in fetch]



