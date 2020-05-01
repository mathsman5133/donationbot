import datetime
import discord
import logging

from discord.ext import commands
from typing import Union, List

from cogs.utils.cache import cache, Strategy
from cogs.utils.db_objects import LogConfig, BoardConfig, SlimEventConfig


log = logging.getLogger(__name__)


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @cache()
    async def log_config(self, channel_id: int, log_type: str) -> Union[LogConfig, None]:
        query = """SELECT guild_id, 
                          channel_id, 
                          "interval", 
                          toggle,
                          type,
                          detailed 
                   FROM logs 
                   WHERE channel_id=$1 
                   AND type=$2
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id, log_type)
        if not fetch:
            return None

        return LogConfig(bot=self.bot, record=fetch)

    @cache()
    async def board_config(self, message_id: int) -> Union[BoardConfig, None]:
        query = """SELECT guild_id, 
                          channel_id,
                          icon_url,
                          title,
                          render,
                          sort_by,
                          toggle,
                          type,
                          in_event,
                          message_id,
                          per_page
                   FROM boards
                   WHERE message_id = $1
                """
        fetch = await self.bot.pool.fetchrow(query, message_id)

        if not fetch:
            return None

        return BoardConfig(bot=self.bot, record=fetch)

    @cache()
    async def get_board_channels(self, guild_id: int, board_type: str) -> Union[List[int], None]:
        query = "SELECT message_id FROM boards WHERE guild_id = $1 AND type = $2 AND toggle = True;"
        fetch = await self.bot.pool.fetch(query, guild_id, board_type)
        return [n["message_id"] for n in fetch]

    async def board_config_from_channel(self, channel_id: int, board_type: str) -> Union[BoardConfig, None]:
        query = """SELECT guild_id, 
                          channel_id,
                          icon_url,
                          title,
                          render,
                          sort_by,
                          toggle,
                          type,
                          in_event,
                          message_id,
                          per_page
                   FROM boards
                   WHERE channel_id = $1
                   AND type = $2
                """
        fetch = await self.bot.pool.fetchrow(query, channel_id, board_type)

        if not fetch:
            return None

        return BoardConfig(bot=self.bot, record=fetch)

    async def get_board_configs(self, guild_id: int, board_type: str, invalidate=False) -> List[BoardConfig]:
        if invalidate:
            self.get_board_channels.invalidate(self, guild_id, board_type)

        message_ids = await self.get_board_channels(guild_id, board_type)

        if not message_ids:
            return list()

        message_ids = [int(n) for n in message_ids]

        configs = list()

        for n in message_ids:
            if invalidate:
                self.board_config.invalidate(self, n)

            configs.append(await self.board_config(n))

        return configs

    @cache()
    async def event_config(self, guild_id: int) -> Union[SlimEventConfig, None]:
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          channel_id,
                          guild_id
                   FROM events
                   WHERE guild_id = $1
                   AND CURRENT_TIMESTAMP < finish
                   ORDER BY start DESC;
                """
        fetch = await self.bot.pool.fetchrow(query, guild_id)

        if not fetch:
            return None

        return SlimEventConfig(fetch['id'], fetch['start'],
                               fetch['finish'], fetch['event_name'],
                               fetch['channel_id'], fetch['guild_id'])

    @cache()
    async def get_clan_name(self, guild_id: int, tag: str) -> str:
        query = "SELECT clan_name FROM clans WHERE clan_tag=$1 AND guild_id=$2"
        fetch = await self.bot.pool.fetchrow(query, tag, guild_id)
        if not fetch:
            return 'Unknown'
        return fetch[0]

    @cache()
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

    async def safe_send(self, channel_id, content=None, embed=None):
        channel = self.bot.get_channel(channel_id)
        try:
            return await channel.send(content, embed=embed)
        except (discord.Forbidden, discord.NotFound, AttributeError):
            await self.bot.pool.execute("UPDATE logs SET toggle = FALSE WHERE channel_id = $1", channel_id)
            self.log_config.invalidate(channel_id, 'donation')
            self.log_config.invalidate(channel_id, 'trophy')
            return
        except:
            log.exception(f"{channel} failed to send {content} {embed}")

    async def channel_log(self, channel_id, log_type, message=None, embed_to_send=None, colour=None, embed=True):
        config = await self.log_config(channel_id, log_type)
        if not config.channel or not config.toggle:
            return

        if embed_to_send:
            e = embed_to_send
            c = None
        elif embed:
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

    async def event_config_id(self, event_id: int) -> Union[None, SlimEventConfig]:
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          channel_id,
                          guild_id
                   FROM events
                   WHERE id = $1
                """
        fetch = await self.bot.pool.fetchrow(query, event_id)

        if not fetch:
            return None

        return SlimEventConfig(fetch['id'], fetch['start'],
                               fetch['finish'], fetch['event_name'],
                               fetch['channel_id'], fetch['guild_id'])


def setup(bot):
    bot.add_cog(Utils(bot))
