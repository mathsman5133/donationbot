import asyncio
import asyncpg
import discord
import itertools
import logging
import math
import time

from collections import namedtuple

from datetime import datetime
from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimDonationEvent
from cogs.utils.formatters import format_donation_log_message, format_donation_log_message_test, get_line_chunks

log = logging.getLogger(__name__)

EVENTS_TABLE_TYPE = 'donation'
SlimDonationEvent2 = namedtuple("SlimDonationEvent", "donations received name tag clan_tag")
TEST_CHANNEL_IDS = [595598923993710592, 594280479881035776, 680216594307350652, 671799417136873504]


def get_received_combos(clan_events):
    valid_events = [n for n in clan_events if n.received]
    combos = {}
    for n in valid_events:
        for x in valid_events:
            if n == x:
                continue
            combos[n.received + x.received] = (n, x)

            for y in valid_events:
                if y == x or y == n:
                    continue

                combos[x.received + n.received + y.received] = (n, x, y)

    return combos


async def get_matches_for_detailed_log(clan_events):
    clan_events = [
        SlimDonationEvent2(
            x['donations'], x['received'], x['player_name'], x['player_tag'], x['clan_tag']
        ) for x in clan_events
    ]

    responses = {
        "exact": [],
        "combo": [],
        "unknown": []
    }

    donation_matches = [x for x in clan_events if
                        x.donations and x.donations in set(n.received for n in clan_events if n.tag != x.tag)]

    for match in donation_matches:
        corresponding_received = [x for x in clan_events if x.received == match.donations and x.tag != match.tag]

        if not corresponding_received:
            continue  # not sure why this would happen
        if len(corresponding_received) > 1:
            continue
            # e.g. 1 player donates 20 and 2 players receive 20, we don't know who the donator gave troops to
        if match not in clan_events:
            continue  # not sure why, have to look into this
        if corresponding_received[0] not in clan_events:
            continue  # same issue

        responses["exact"].append(format_donation_log_message_test(match))
        clan_events.remove(match)

        responses["exact"].append(format_donation_log_message_test(corresponding_received[0]))
        clan_events.remove(corresponding_received[0])

    possible_received_combos = get_received_combos(clan_events)

    matches = [n for n in clan_events if n.donations in possible_received_combos.keys()]

    for event in matches:
        received_combos = possible_received_combos.get(event.donations)
        if not all(x in clan_events for x in received_combos):
            continue

        if not received_combos:
            continue

        for x in (event, *received_combos):
            responses["combo"].append(format_donation_log_message_test(x))
            clan_events.remove(x)

    for event in clan_events:
        responses["unknown"].append(format_donation_log_message_test(event))
        clan_events.remove(event)

    return responses


def get_events_fmt(events):
    messages = []

    if events["exact"]:
        messages.append("**Exact donation/received matches**")
        messages.extend(events["exact"])
    if events["combo"]:
        messages.append("\n**Matched donations with a combo of received troops**")
        messages.extend(events["combo"])
    if events["unknown"]:
        messages.append("\n**Unknown donation/received matches**")
        messages.extend(events["unknown"])

    return messages


async def get_detailed_log(bot, all_clan_events, raw_events: bool = False):
    embeds = []
    for (tag, clan_events) in itertools.groupby(all_clan_events, key=lambda x: x['clan_tag']):
        events = await get_matches_for_detailed_log(list(clan_events))
        if raw_events:
            embeds.append((tag, events))
            continue

        clan = await bot.coc.get_clan(tag, update_cache=True, cache=True)
        messages = get_events_fmt(events)

        hex_ = bytes.hex(str.encode(clan.tag))[:20]

        for lines in get_line_chunks(messages):
            e = discord.Embed(
                colour=int(int(''.join(filter(lambda x: x.isdigit(), hex_))) ** 0.3),
                description="\n".join(lines)
            )
            e.set_author(name=f"{clan.name} ({clan.tag})", icon_url=clan.badge.url)
            e.set_footer(text="Reported").timestamp = datetime.utcnow()
            embeds.append(e)

    return embeds


async def get_basic_log(bot, guild_id, events):
    all_events = [SlimDonationEvent(x['donations'], x['received'], x['player_name'], x['clan_tag']) for x in sorted(events, key=lambda x: x['clan_tag'])]

    messages = []
    for x in all_events:
        clan_name = await bot.utils.get_clan_name(guild_id, x.clan_tag)
        messages.append(format_donation_log_message(x, clan_name))

    group_batch = []
    for i in range(math.ceil(len(messages) / 20)):
        group_batch.append(messages[i * 20:(i + 1) * 20])

    return group_batch


class DonationLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._batch_data = []
        self.report_task.add_exception_type(asyncpg.PostgresConnectionError)
        self.report_task.start()

        self._tasks = {}
        asyncio.ensure_future(self.sync_temp_event_tasks())

        self._clans_updated = set()

    def cog_unload(self):
        self.report_task.cancel()
        self.bot.coc.remove_events(
            self.on_clan_member_donation,
            self.on_clan_member_received
        )
        for k, v in self._tasks:
            v.cancel()

    @tasks.loop(seconds=60.0)
    async def report_task(self):
        log.debug('Starting bulk report loop for donations.')
        start = time.perf_counter()
        try:
            await self.bulk_report()
        except:
            pass
        log.debug('Time taken: %s ms', (time.perf_counter() - start)*1000)

    async def sync_temp_event_tasks(self):
        query = """SELECT channel_id 
                   FROM logs 
                   WHERE toggle = True 
                   AND interval > make_interval()
                   AND type = $1
                """
        fetch = await self.bot.pool.fetch(query, EVENTS_TABLE_TYPE)
        for n in fetch:
            if not n[0] == 594280479881035776:
                continue
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

                await asyncio.sleep(config.seconds)
                config = await self.bot.utils.log_config(channel_id, EVENTS_TABLE_TYPE)

                if config.detailed:
                    query = "DELETE FROM detailedtempevents WHERE channel_id = $1 RETURNING clan_tag, exact, combo, unknown"
                    fetch = await self.bot.pool.fetch(query, channel_id)

                    if not fetch:
                        continue

                    embeds = []

                    for clan_tag, events in itertools.groupby(sorted(fetch, key=lambda x: x['clan_tag'])):
                        events = list(events)

                        events_fmt = {
                            "exact": [n['exact'].split('\n') for n in events],
                            "combo": [n['combo'].split('\n') for n in events],
                            "unknown": [n['unknown'].split('\n') for n in events]
                        }
                        messages = get_events_fmt(events_fmt)

                        clan = await self.bot.coc.get_clan(clan_tag, cache=True)

                        hex_ = bytes.hex(str.encode(clan.tag))[:20]

                        for lines in get_line_chunks(messages):
                            e = discord.Embed(
                                colour=int(int(''.join(filter(lambda x: x.isdigit(), hex_))) ** 0.3),
                                description="\n".join(lines)
                            )
                            e.set_author(name=f"{clan.name} ({clan.tag})", icon_url=clan.badge.url)
                            e.set_footer(text="Reported").timestamp = datetime.utcnow()
                            embeds.append(e)

                    for n in embeds:
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel, embed=n))
                        
                else:
                    query = "DELETE FROM tempevents WHERE channel_id = $1 AND type = $2 RETURNING fmt"
                    fetch = await self.bot.pool.fetch(query, channel_id, EVENTS_TABLE_TYPE)

                    for n in fetch:
                        asyncio.ensure_future(self.bot.utils.channel_log(channel_id, EVENTS_TABLE_TYPE,
                                                                         n[0], embed=False))

        except asyncio.CancelledError:
            raise
        except (OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            log.exception(f'Exception encountered while running task for {channel_id}')
            self._tasks[channel_id].cancel()
            self._tasks[channel_id] = self.bot.loop.create_task(self.create_temp_event_task(channel_id))

    async def bulk_report(self):
        query = """SELECT donationevents.clan_tag,
                          donations,
                          received,
                          player_name,
                          player_tag,
                          time,
                          clans.channel_id
                    FROM donationevents
                    INNER JOIN clans 
                    ON donationevents.clan_tag = clans.clan_tag
                    INNER JOIN logs
                    ON clans.channel_id = logs.channel_id
                    WHERE donationevents.reported = FALSE
                    AND logs.type = 'donation'
                    ORDER BY time DESC
                """
        fetch = await self.bot.pool.fetch(query)

        query = "UPDATE donationevents SET reported = TRUE WHERE reported = FALSE RETURNING clan_tag"
        removed = await self.bot.pool.fetch(query)
        log.debug('Removed donationevents from the database. Status Code %s', len(removed))
        self.bot.donationboard.tags_to_update.update(set(n['clan_tag'] for n in removed))

        sorted_fetch = sorted(fetch, key=lambda n: n['channel_id'])

        for channel_id, events in itertools.groupby(sorted_fetch, key=lambda n: n['channel_id']):
            config = await self.bot.utils.log_config(channel_id, 'donation')

            if not config:
                continue
            if not config.toggle:
                continue
            if not config.channel:
                continue

            events = list(events)
            log.debug(f"running {channel_id}")

            if config.detailed:
                if config.seconds > 0 and channel_id == 594280479881035776:
                    responses = await get_detiled_log(self.bot, events, raw_events=True)
                    # in this case, responses will be in
                    # [(clan_tag, {"exact": [str], "combo": [str], "unknown": [str]})] form.

                    for clan_tag, items in responses:
                        await self.add_detailed_temp_events(channel_id, clan_tag, items)
                    continue

                embeds = await get_detiled_log(self.bot, events)
                for x in embeds:
                    log.debug(f'Dispatching a log to channel {config.channel} (ID {config.channel_id}), {x}')
                    asyncio.ensure_future(self.bot.utils.safe_send(config.channel, embed=x))

            else:
                messages = await get_basic_log(self.bot, config.guild_id, events)
                if config.seconds > 0 and channel_id == 594280479881035776:
                    for n in messages:
                        await self.add_temp_events(channel_id, "\n".join(n))

                for x in messages:
                    log.debug(f'Dispatching a detailed log to channel {config.channel} (ID {config.channel_id}), {x}')
                    asyncio.ensure_future(self.bot.utils.safe_send(config.channel, '\n'.join(x)))

    async def add_temp_events(self, channel_id, fmt):
        query = """INSERT INTO tempevents (channel_id, fmt, type) VALUES ($1, $2, $3)"""
        await self.bot.pool.execute(query, channel_id, fmt, EVENTS_TABLE_TYPE)
        log.debug(f'Added a message for channel id {channel_id} to tempevents db')

    async def add_detailed_temp_events(self, channel_id, clan_tag, events):
        query = "INSERT INTO detailedtempevents (channel_id, clan_tag, exact, combo, unknown) VALUES ($1, $2, $3, $4, $5)"
        await self.bot.pool.execute(
            query, 
            channel_id, 
            clan_tag, 
            "\n".join(events["exact"]), 
            "\n".join(events["combo"]), 
            "\n".join(events["unknown"])
        )
        log.debug(f'Added detailed temp events for channel id {channel_id} clan tag {clan_tag} to detailedtempevents db\n{events}')


def setup(bot):
    bot.add_cog(DonationLogs(bot))
