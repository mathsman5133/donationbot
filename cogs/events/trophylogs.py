import asyncio
import asyncpg
import discord
import logging

from discord.ext import commands


log = logging.getLogger(__name__)

EVENTS_TABLE_TYPE = 'trophy'


class TrophyLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self._tasks = {}
        asyncio.ensure_future(self.sync_temp_event_tasks())

    def cog_unload(self):
        for k, v in self._tasks:
            v.cancel()

    async def sync_temp_event_tasks(self):
        query = """SELECT channel_id FROM logs 
                   WHERE toggle=True 
                   AND interval > make_interval()
                   AND type = $1
                """
        fetch = await self.bot.pool.fetch(query, EVENTS_TABLE_TYPE)
        for n in fetch:
            channel_id = n[0]
            log.debug(f'Syncing task for Channel ID {channel_id}')
            task = self._tasks.get(channel_id)
            if not task:
                log.debug(f'Task has not been created. Creating it. Channel ID: {channel_id}')
                self._tasks[channel_id] = self.bot.loop.create_task(self.create_temp_event_task(channel_id))
                continue
            elif task.done():
                log.info(task.get_stack())
                log.info(f'Task has already been completed, recreating it. Channel ID: {channel_id}')
                self._tasks[channel_id] = self.bot.loop.create_task(self.create_temp_event_task(channel_id))
                continue
            else:
                log.debug(f'Task has already been sucessfully registered for Channel ID {channel_id}')

        to_cancel = [n for n in self._tasks.keys() if n not in set(n[0] for n in fetch)]
        for n in to_cancel:
            log.debug(f'Channel events have been removed from DB. Destroying task. Channel ID: {n}')
            task = self._tasks.pop(n, None)
            task.cancel()

        log.info(f'Successfully synced {len(fetch)} channel tasks.')

    async def create_temp_event_task(self, channel_id):
        try:
            while not self.bot.is_closed():
                config = await self.bot.utils.log_config(channel_id, EVENTS_TABLE_TYPE)
                if not config:
                    log.warning(f'Channel ID not found in DB or `None` '
                                f'has been cached for Channel ID: {channel_id}')
                    return

                await asyncio.sleep(config.seconds)

                query = "DELETE FROM tempevents WHERE channel_id = $1 AND type = $2 RETURNING fmt"
                fetch = await self.bot.pool.fetch(query, channel_id, EVENTS_TABLE_TYPE)

                for n in fetch:
                    await self.bot.background.log_message_send(
                        None, config.channel_id, config.guild_id, 'trophylog'
                    )

                    asyncio.ensure_future(self.bot.utils.channel_log(channel_id, EVENTS_TABLE_TYPE,
                                                                     n[0], embed=False))

                log.debug(f'Dispatching {len(fetch)} logs after sleeping for {config.seconds} '
                          f'sec to channel {config.channel} ({config.channel_id})')

        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            log.exception(f'Exception encountered while running task for {channel_id}')
            self._tasks[channel_id].cancel()
            self._tasks[channel_id] = self.bot.loop.create_task(self.create_temp_event_task(channel_id))


def setup(bot):
    bot.add_cog(TrophyLogs(bot))
