import datetime
import discord

from discord.ext import commands
from typing import Union

from cogs.utils.cache import cache, Strategy
from cogs.utils.db_objects import LogConfig, BoardConfig, SlimEventConfig


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @cache(strategy=Strategy.lru)
    async def log_config(self, channel_id: int, log_type: str) -> Union[LogConfig, None]:
        query = """SELECT guild_id, 
                          channel_id, 
                          interval, 
                          toggle,
                          type 
                   FROM logs 
                   WHERE channel_id=$1 
                   AND type=$2
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id, log_type)
        if not fetch:
            return None

        return LogConfig(bot=self.bot, record=fetch)

    @cache(strategy=Strategy.lru)
    async def board_config(self, channel_id: int) -> Union[BoardConfig, None]:
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
    async def get_board_channel(self, guild_id: int, board_type: str) -> Union[int, None]:
        query = "SELECT channel_id FROM boards WHERE guild_id = $1 AND type = $2 AND toggle = True;"
        fetch = await self.bot.pool.fetchrow(query, guild_id, board_type)
        if fetch:
            return fetch['channel_id']

    async def get_board_config(self, guild_id: int, board_type: str, invalidate=False):
        if invalidate:
            await self.get_board_channel.invalidate(self, guild_id, board_type)

        channel_id = await self.get_board_channel(guild_id, board_type)
        if not channel_id:
            return
        channel_id = int(channel_id)

        if invalidate:
            self.board_config.invalidate(self, channel_id)

        return await self.board_config(channel_id)

    @cache(strategy=Strategy.lru)
    async def event_config(self, guild_id: int) -> Union[SlimEventConfig, None]:
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          channel_id
                   FROM events
                   WHERE guild_id = $1
                   ORDER BY start DESC;
                """
        fetch = await self.bot.pool.fetchrow(query, guild_id)

        if not fetch:
            return None

        return SlimEventConfig(fetch['id'], fetch['start'],
                               fetch['finish'], fetch['event_name'], fetch['channel_id'])

    @cache()
    async def get_clan_name(self, guild_id: int, tag: str) -> str:
        query = "SELECT clan_name FROM clans WHERE clan_tag=$1 AND guild_id=$2"
        fetch = await self.bot.pool.fetchrow(query, tag, guild_id)
        if not fetch:
            return 'Unknown'
        return fetch[0]

    @cache(strategy=Strategy.lru)
    async def get_message(self, channel: discord.TextChannel, message_id: int) -> Union[discord.Message, None]:
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

    async def channel_log(self, channel_id, log_type, message, colour=None, embed=True):
        config = await self.log_config(channel_id, log_type)
        if not config.channel or not config.toggle:
            return

        if embed:
            e = discord.Embed(colour=colour or self.bot.colour,
                              description=message,
                              timestamp=datetime.datetime.utcnow())
            c = None
        else:
            e = None
            c = message

        try:
            await config.channel.send(content=c, embed=e)
        except (discord.Forbidden, discord.HTTPException):
            return


def setup(bot):
    bot.add_cog(Utils(bot))
