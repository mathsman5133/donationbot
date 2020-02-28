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


async def get_detiled_log(bot, all_clan_events):
    embeds = []
    for (tag, clan_events) in itertools.groupby(all_clan_events, key=lambda x: x['clan_tag']):
        clan_events = [SlimDonationEvent2(x['donations'], x['received'], x['player_name'], x['player_tag'], x['clan_tag']) for x in clan_events]
        clan = await bot.coc.get_clan(clan_events[0].clan_tag, cache=True, update_cache=False)

        messages = []

        donation_matches = [x for x in clan_events if x.donations and x.donations in set(n.received for n in clan_events if n.tag != x.tag)]

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

            if not messages:
                messages.append("**Exact donation/received matches**")

            messages.append(format_donation_log_message_test(match))
            clan_events.remove(match)

            messages.append(format_donation_log_message_test(corresponding_received[0]))
            clan_events.remove(corresponding_received[0])

        possible_received_combos = get_received_combos(clan_events)

        matches = [n for n in clan_events if n.donations in possible_received_combos.keys()]

        for event in matches:
            if "\n**Matched donations with a combo of received troops**" not in messages:
                messages.append("\n**Matched donations with a combo of received troops**")

            received_combos = possible_received_combos.get(event.donations)
            if not all(x in clan_events for x in received_combos):
                continue

            if not received_combos:
                continue

            for x in (event, *received_combos):
                messages.append(format_donation_log_message_test(x))
                clan_events.remove(x)

        for event in clan_events:
            if "\n**Unknown donation/received matches**" not in messages:
                messages.append("\n**Unknown donation/received matches**")
            messages.append(format_donation_log_message_test(event))
            clan_events.remove(event)

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
        return
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

                await asyncio.sleep(config.seconds)
                config = await self.bot.utils.log_config(channel_id, EVENTS_TABLE_TYPE)

                query = """SELECT * 
                           FROM donationevents 
                           INNER JOIN clans 
                           ON donationevents.clan_tag = clans.clan_tag 
                           INNER JOIN logs 
                           ON clans.channel_id = logs.channel_id 
                           WHERE donationevents.time > now() - logs.interval 
                           AND clans.channel_id = $1
                           AND logs.toggle = TRUE
                        """

                fetch = await self.bot.pool.fetch(query, channel_id)

                if config.detailed:
                    embeds = await get_detiled_log(self.bot, fetch)
                    for x in embeds:
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel, embed=x))
                else:
                    messages = await get_basic_log(self.bot, config.guild_id, fetch)
                    for x in messages:
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel, "\n".join(x)))

                if fetch:
                    log.debug(f'Dispatching {len(fetch)} logs after sleeping for {config.seconds} '
                              f'sec to channel {config.channel} ({config.channel_id})')

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
                    AND logs.interval = make_interval()
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
            if config.seconds > 0:
                continue

            events = list(events)
            log.debug(f"running {channel_id}")

            if config.detailed:
                embeds = await get_detiled_log(self.bot, events)
                for x in embeds:
                    log.debug(f'Dispatching a log to channel {config.channel} (ID {config.channel_id}), {x}')
                    asyncio.ensure_future(self.bot.utils.safe_send(config.channel, embed=x))

            else:
                messages = await get_basic_log(self.bot, config.guild_id, events)
                for x in messages:
                    log.debug(f'Dispatching a detailed log to channel {config.channel} (ID {config.channel_id}), {x}')
                    asyncio.ensure_future(self.bot.utils.safe_send(config.channel, '\n'.join(x)))

    async def on_clan_member_donation(self, old_donations, new_donations, player, clan):
        log.debug(f'Received on_clan_member_donation event for player {player} of clan {clan}')
        if old_donations > new_donations:
            donations = new_donations
        else:
            donations = new_donations - old_donations

        self._batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan.tag,
            'donations': donations,
            'received': 0,
            'time': datetime.utcnow().isoformat(),
            'season_id': await self.bot.seasonconfig.get_season_id()
        })

    async def on_clan_member_received(self, old_received, new_received, player, clan):
        log.debug(f'Received on_clan_member_received event for player {player} of clan {clan}')
        if old_received > new_received:
            received = new_received
        else:
            received = new_received - old_received

        self._batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan.tag,
            'donations': 0,
            'received': received,
            'time': datetime.utcnow().isoformat(),
            'season_id': await self.bot.seasonconfig.get_season_id()
        })


def setup(bot):
    bot.add_cog(DonationLogs(bot))
