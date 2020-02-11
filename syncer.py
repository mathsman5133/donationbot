import asyncio
import datetime
import logging

from discord.ext import tasks

import creds

from cogs.utils.db import Table

log = logging.getLogger(__name__)
SEASON_ID = 8

loop = asyncio.get_event_loop()
pool = loop.run_until_complete(Table.create_pool(creds.postgres))

donationlog_batch_lock = asyncio.Lock(loop=loop)
donationlog_batch_data = []

trophylog_batch_lock = asyncio.Lock(loop=loop)
trophylog_batch_data = []

last_updated_batch_lock = asyncio.Lock(loop=loop)
last_updated_data = {}


@tasks.loop(seconds=60.0)
async def batch_insert_loop():
    log.debug('Starting batch insert loop for donationlogs.')
    async with donationlog_batch_lock:
        await bulk_insert()


async def bulk_insert():
    query = """INSERT INTO donationevents (player_tag, player_name, clan_tag, 
                                             donations, received, time, season_id)
                    SELECT x.player_tag, x.player_name, x.clan_tag, 
                           x.donations, x.received, x.time, x.season_id
                       FROM jsonb_to_recordset($1::jsonb) 
                    AS x(player_tag TEXT, player_name TEXT, clan_tag TEXT, 
                         donations INTEGER, received INTEGER, time TIMESTAMP, season_id INTEGER
                         )
            """

    if donationlog_batch_data:
        await pool.execute(query, donationlog_batch_data)
        total = len(donationlog_batch_data)
        if total > 1:
            log.debug('Registered %s donation events to the database.', total)
        donationlog_batch_data.clear()


async def on_clan_member_donation(old_donations, new_donations, player, clan):
    log.debug(f'Received on_clan_member_donation event for player {player} of clan {clan}')
    if old_donations > new_donations:
        donations = new_donations
    else:
        donations = new_donations - old_donations

    async with donationlog_batch_lock:
        donationlog_batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan.tag,
            'donations': donations,
            'received': 0,
            'time': datetime.datetime.utcnow().isoformat(),
            'season_id': SEASON_ID
        })


async def on_clan_member_received(old_received, new_received, player, clan):
    log.debug(f'Received on_clan_member_received event for player {player} of clan {clan}')
    if old_received > new_received:
        received = new_received
    else:
        received = new_received - old_received

    async with donationlog_batch_lock:
        donationlog_batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan.tag,
            'donations': 0,
            'received': received,
            'time': datetime.datetime.utcnow().isoformat(),
            'season_id': SEASON_ID
        })


@tasks.loop(seconds=60.0)
async def trophylog_batch_insert_loop():
    log.debug('Starting batch insert loop.')
    async with trophylog_batch_lock:
        await trophylog_bulk_insert()

async def trophylog_bulk_insert():
    query = """INSERT INTO trophyevents (player_tag, player_name, clan_tag, 
                                             trophy_change, league_id, time, season_id)
                    SELECT x.player_tag, x.player_name, x.clan_tag, 
                           x.trophy_change, x.league_id, x.time, x.season_id
                       FROM jsonb_to_recordset($1::jsonb) 
                    AS x(player_tag TEXT, player_name TEXT, clan_tag TEXT, 
                         trophy_change INTEGER, league_id INTEGER, time TIMESTAMP, season_id INTEGER
                         )
            """

    if trophylog_batch_data:
        await pool.execute(query, trophylog_batch_data)
        total = len(trophylog_batch_data)
        if total > 1:
            log.debug('Registered %s trophy events to the database.', total)
        trophylog_batch_data.clear()


async def on_clan_member_trophies_change(old_trophies, new_trophies, player, clan):
    log.debug(f'Received on_clan_member_trophy_change event for player {player} of clan {clan}')
    change = new_trophies - old_trophies

    async with trophylog_batch_lock:
        trophylog_batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan.tag,
            'trophy_change': change,
            'league_id': player.league.id,
            'time': datetime.datetime.utcnow().isoformat(),
            'season_id': SEASON_ID
        })

@tasks.loop(hours=1)
async def event_player_updater():
    query = "SELECT DISTINCT player_tag FROM eventplayers WHERE live = True;"
    fetch = await pool.fetch(query)

    query = """UPDATE eventplayers
               SET donations             = x.end_fin + x.end_sic - eventplayers.start_friend_in_need - eventplayers.start_sharing_is_caring,
                   trophies              = x.trophies,
                   end_friend_in_need    = x.end_fin,
                   end_sharing_is_caring = x.end_sic,
                   end_attacks           = x.end_attacks,
                   end_defenses          = x.end_defenses,
                   end_best_trophies     = x.end_best_trophies
               FROM (
                   SELECT x.player_tag,
                          x.trophies,
                          x.end_fin,
                          x.end_sic,
                          x.end_attacks,
                          x.end_defenses,
                          x.end_best_trophies
                   FROM jsonb_to_recordset($1::jsonb)
                   AS x (
                       player_tag TEXT,
                       trophies INTEGER,
                       end_fin INTEGER,
                       end_sic INTEGER,
                       end_attacks INTEGER,
                       end_defenses INTEGER,
                       end_best_trophies INTEGER
                       )
                    )
               AS x
               WHERE eventplayers.player_tag = x.player_tag
               AND eventplayers.live = True
            """

    to_insert = []

    log.info(f'Starting loop for event updates. {len(fetch)} players to update!')
    start = time.perf_counter()
    async for player in coc_client.get_players((n[0] for n in fetch), update_cache=False):
        to_insert.append(
            {
                'player_tag': player.tag,
                'trophies': player.trophies,
                'end_fin': player.achievements_dict['Friend in Need'].value,
                'end_sic': player.achievements_dict['Sharing is caring'].value,
                'end_attacks': player.attack_wins,
                'end_defenses': player.defense_wins,
                'end_best_trophies': player.best_trophies
            }
        )
        await asyncio.sleep(0.01)
    await pool.execute(query, to_insert)
    log.info(f'Loop for event updates finished. Took {(time.perf_counter() - start)*1000}ms')


async def on_clan_member_league_change(self, old_league, new_league, player, clan):
    if old_league.id > new_league.id:
        return  # they dropped a league
    if new_league.id == 29000000:
        return  # unranked - probably start of season.

    query = """SELECT channel_id 
               FROM events
               INNER JOIN eventplayers 
               ON eventplayers.event_id = events.id
               WHERE start_best_trophies < $1 
               AND player_tag = $2
            """
    fetch = await self.bot.pool.fetch(query, player.trophies, player.tag)
    if not fetch:
        return

    msg = f"Breaking new heights! {player} just got promoted to {new_league} league!"

    for record in fetch:
        await self.safe_send(self.bot.get_channel(record['channel_id']), msg)


@tasks.loop(minutes=1.0)
async def loop():
    await update_db()

async def update_db():
    query = """UPDATE players 
               SET last_updated = x.last_updated
               FROM(
                   SELECT x.last_updated, x.player_tag
                   FROM jsonb_to_recordset($1::jsonb)
                   AS x(
                       player_tag TEXT,
                       last_updated TIMESTAMP
                   )
               )
               AS x
               WHERE players.player_tag = x.player_tag
               AND players.season_id = $2
            """
    async with :
        await self.bot.pool.execute(
            query, list(self.last_updated.values()), await self.bot.seasonconfig.get_season_id()
        )
        self.last_updated.clear()

async def update(self, player_tag):
    async with self.batch_lock:
        self.last_updated[player_tag] = {
            'player_tag': player_tag,
            'last_updated': datetime.utcnow().isoformat()
        }

async def on_clan_member_name_change(self, _, __, player, ___):
    await self.update(player.tag)

async def on_clan_member_donation(self, _, __, player, ___):
    await self.update(player.tag)

async def on_clan_member_versus_trophies_change(self, _, __, player, ___):
    await self.update(player.tag)

async def on_clan_member_level_change(self, _, __, player, ___):
    await self.update(player.tag)

async def on_clan_member_trophies_change(self, _, __, player, ___):
    pass  # could be a defense - doesn't mean online

async def on_clan_member_received(self, _, __, player, ___):
    pass  # don't have to be online to receive donations
