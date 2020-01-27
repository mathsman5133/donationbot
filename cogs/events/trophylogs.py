import asyncio
import asyncpg
import discord
import logging
import math
import time

from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimTrophyEvent
from cogs.utils.formatters import format_trophy_log_message

log = logging.getLogger(__name__)

EVENTS_TABLE_TYPE = 'trophy'


class TrophyLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._batch_data = []
        self._batch_lock = asyncio.Lock(loop=bot.loop)
        self.report_task.add_exception_type(asyncpg.PostgresConnectionError)
        self.report_task.start()

        self._tasks = {}
        asyncio.ensure_future(self.sync_temp_event_tasks())

    def cog_unload(self):
        self.report_task.cancel()
        for k, v in self._tasks:
            v.cancel()

    @tasks.loop(seconds=60.0)
    async def report_task(self):
        log.debug('Starting bulk report loop for trophies.')
        start = time.perf_counter()
        async with self._batch_lock:
            await self.bulk_report()
        log.debug('Time taken: %s ms', (time.perf_counter() - start)*1000)

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

    async def add_temp_events(self, channel_id, fmt):
        query = """INSERT INTO tempevents (channel_id, fmt, type) VALUES ($1, $2, $3)"""
        await self.bot.pool.execute(query, channel_id, fmt, EVENTS_TABLE_TYPE)
        log.debug(f'Added a message for channel id {channel_id} to tempevents db')

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

    async def bulk_report(self):
        query = """SELECT DISTINCT clans.channel_id 
                   FROM clans 
                        INNER JOIN trophyevents 
                        ON clans.clan_tag = trophyevents.clan_tag 
                   WHERE trophyevents.reported=False
                """
        fetch = await self.bot.pool.fetch(query)

        query = """SELECT trophyevents.clan_tag, 
                          trophyevents.trophy_change,
                          trophyevents.league_id, 
                          trophyevents.player_name, 
                          trophyevents.time
                    FROM trophyevents 
                        INNER JOIN clans 
                        ON clans.clan_tag = trophyevents.clan_tag 
                    WHERE clans.channel_id = $1 
                    AND trophyevents.reported=False
                    ORDER BY trophyevents.clan_tag, 
                             time DESC;
                """

        for n in fetch:
            config = await self.bot.utils.log_config(n[0], EVENTS_TABLE_TYPE)
            if not config:
                continue
            if not config.toggle:
                continue

            events = await self.bot.pool.fetch(query, n[0])

            messages = []
            for x in events:
                slim_event = SlimTrophyEvent(x['trophy_change'], x['league_id'], x['player_name'], x['clan_tag'])
                clan_name = await self.bot.utils.get_clan_name(config.guild_id, slim_event.clan_tag)
                messages.append(format_trophy_log_message(slim_event, clan_name))

            group_batch = []
            for i in range(math.ceil(len(messages) / 20)):
                group_batch.append(messages[i*20:(i+1)*20])

            for x in group_batch:
                if config.seconds > 0:
                    await self.add_temp_events(config.channel_id, '\n'.join(x))
                else:
                    log.debug(f'Dispatching a log to channel '
                              f'{config.channel} (ID {config.channel_id})')
                    asyncio.ensure_future(self.bot.utils.channel_log(config.channel_id, EVENTS_TABLE_TYPE,
                                                                     '\n'.join(x), embed=False))

        query = """UPDATE trophyevents
                        SET reported=True
                   WHERE reported=False
                """
        removed = await self.bot.pool.execute(query)
        log.debug('Removed events from the database. Status Code %s', removed)


def setup(bot):
    bot.add_cog(TrophyLogs(bot))
