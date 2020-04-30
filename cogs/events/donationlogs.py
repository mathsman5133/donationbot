import asyncio
import asyncpg
import discord
import itertools
import logging
import math
import time

from collections import namedtuple
from datetime import datetime

import coc

from discord.ext import commands, tasks

from cogs.utils.donationtrophylogs import SlimDonationEvent, SlimDonationEvent2, get_events_fmt
from cogs.utils.formatters import LineWrapper

log = logging.getLogger(__name__)

EVENTS_TABLE_TYPE = 'donation'


class DonationLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._batch_data = []

        self._tasks = {}
        asyncio.ensure_future(self.sync_temp_event_tasks())

        self._clans_updated = set()

    def cog_unload(self):
        for k, v in self._tasks:
            v.cancel()

    async def sync_temp_event_tasks(self):
        query = """SELECT channel_id 
                   FROM logs 
                   WHERE toggle = True 
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
            task = self._tasks.pop(n)
            task.cancel()

        log.info(f'Successfully synced {len(fetch)} channel tasks.')

    async def create_temp_event_task(self, channel_id):
        try:
            while not self.bot.is_closed():
                config = await self.bot.utils.log_config(channel_id, EVENTS_TABLE_TYPE)
                if not config:
                    log.critical(f'Requested a task creation for channel id {channel_id}'
                                 ' but config was not found.')
                    return

                await asyncio.sleep(config.seconds)
                config = await self.bot.utils.log_config(channel_id, EVENTS_TABLE_TYPE)

                if config.detailed:
                    query = "DELETE FROM detailedtempevents WHERE channel_id = $1 RETURNING clan_tag, exact, combo, unknown"
                    fetch = await self.bot.pool.fetch(query, channel_id)

                    if not fetch:
                        continue

                    embeds = []

                    for clan_tag, events in itertools.groupby(sorted(fetch, key=lambda x: x['clan_tag']), key=lambda x: x['clan_tag']):
                        events = list(events)

                        events_fmt = {
                            "exact": [],
                            "combo": [],
                            "unknown": []
                        }
                        for n in events:
                            events_fmt["exact"].extend(n['exact'].split('\n'))
                            events_fmt["combo"].extend(n['combo'].split('\n'))
                            events_fmt["unknown"].extend(n['unknown'].split('\n'))

                        p = LineWrapper()
                        p.add_lines(get_events_fmt(events_fmt))

                        try:
                            clan = await self.bot.coc.get_clan(clan_tag, cache=True)
                        except coc.NotFound:
                            log.exception(f'{clan_tag} not found')
                            continue

                        hex_ = bytes.hex(str.encode(clan.tag))[:20]

                        for page in p.pages:
                            e = discord.Embed(
                                colour=int(int(''.join(filter(lambda x: x.isdigit(), hex_))) ** 0.3),
                                description=page
                            )
                            e.set_author(name=f"{clan.name} ({clan.tag})", icon_url=clan.badge.url)
                            e.set_footer(text="Reported").timestamp = datetime.utcnow()
                            embeds.append(e)

                    for n in embeds:
                        await self.bot.background.log_message_send(
                            None, config.channel_id, config.guild_id, 'donationlog'
                        )
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel, embed=n))
                        
                else:
                    query = "DELETE FROM tempevents WHERE channel_id = $1 AND type = $2 RETURNING fmt"
                    fetch = await self.bot.pool.fetch(query, channel_id, EVENTS_TABLE_TYPE)
                    p = LineWrapper()

                    for n in fetch:
                        p.add_lines(n[0].split("\n"))
                    for page in p.pages:
                        await self.bot.background.log_message_send(
                            None, config.channel_id, config.guild_id, 'donationlog'
                        )
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel, page))

        except asyncio.CancelledError:
            raise
        except:
            log.exception(f'Exception encountered while running task for {channel_id}')
            self._tasks[channel_id].cancel()
            self._tasks[channel_id] = self.bot.loop.create_task(self.create_temp_event_task(channel_id))


def setup(bot):
    bot.add_cog(DonationLogs(bot))
