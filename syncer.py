import asyncio
import datetime
import logging
import time

import coc

from discord.ext import tasks

import creds

from cogs.utils.db import Table

logging.basicConfig(level=logging.INFO)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
SEASON_ID = 9


class CustomCache(coc.Cache):
    @property
    def clan_config(self):
        return coc.CacheConfig(2000, None)  # max_size, time to live


loop = asyncio.get_event_loop()
pool = loop.run_until_complete(Table.create_pool(creds.postgres))
coc_client = coc.login(creds.email, creds.password, client=coc.EventsClient, key_names="test", throttle_limit=30, key_count=3, cache=CustomCache)

board_batch_lock = asyncio.Lock(loop=loop)
board_batch_data = {}

donationlog_batch_lock = asyncio.Lock(loop=loop)
donationlog_batch_data = []

trophylog_batch_lock = asyncio.Lock(loop=loop)
trophylog_batch_data = []

last_updated_batch_lock = asyncio.Lock(loop=loop)
last_updated_data = {}


@tasks.loop(seconds=60.0)
async def batch_insert_loop():
    log.info('Starting batch insert loop for donationlogs.')
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
            log.info('Registered %s donation events to the database.', total)
        donationlog_batch_data.clear()

        
@tasks.loop(seconds=60.0)
async def board_insert_loop():
    async with board_batch_lock:
        await bulk_board_insert()
        
async def bulk_board_insert():
    query = """UPDATE players SET donations = public.get_don_rec_max(x.old_dons, x.new_dons, COALESCE(players.donations, 0)), 
                                  received  = public.get_don_rec_max(x.old_rec, x.new_rec, COALESCE(players.received, 0)), 
                                  trophies  = x.trophies,
                                  clan_tag  = x.clan_tag,
                                  player_name = x.player_name
                    FROM(
                        SELECT x.player_tag, x.old_dons, x.new_dons, x.old_rec, x.new_rec, x.trophies, x.clan_tag, x.player_name
                            FROM jsonb_to_recordset($1::jsonb)
                        AS x(player_tag TEXT, 
                             old_dons INTEGER, 
                             new_dons INTEGER,
                             old_rec INTEGER, 
                             new_rec INTEGER,
                             trophies INTEGER,
                             clan_tag TEXT,
                             player_name TEXT)
                        )
                AS x
                WHERE players.player_tag = x.player_tag
                AND players.season_id=$2
            """

    query2 = """UPDATE eventplayers SET donations = public.get_don_rec_max(x.old_dons, x.new_dons, eventplayers.donations), 
                                        received  = public.get_don_rec_max(x.old_rec, x.new_rec, eventplayers.received),
                                        trophies  = x.trophies   
                    FROM(
                        SELECT x.player_tag, x.old_dons, x.new_dons, x.old_rec, x.new_rec, x.trophies
                        FROM jsonb_to_recordset($1::jsonb)
                        AS x(player_tag TEXT, 
                             old_dons INTEGER, 
                             new_dons INTEGER,
                             old_rec INTEGER,
                             new_rec INTEGER, 
                             trophies INTEGER,
                             clan_tag TEXT,
                             player_name TEXT)
                        )
                AS x
                WHERE eventplayers.player_tag = x.player_tag
                AND eventplayers.live = true                    
            """
    if board_batch_data:
        response = await pool.execute(query, list(board_batch_data.values()), SEASON_ID)
        log.info(f'Registered donations/received to the database. Status Code {response}.')
        response = await pool.execute(query2, list(board_batch_data.values()))
        log.info(f'Registered donations/received to the events database. Status Code {response}.')
        board_batch_data.clear()


async def on_clan_member_donation(old_donations, new_donations, player, clan):
    log.info(f'Received on_clan_member_donation event for player {player} of clan {clan}')
    if old_donations > new_donations:
        donations = new_donations
    else:
        donations = new_donations - old_donations

    async with donationlog_batch_lock:
        donationlog_batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan and clan.tag,
            'donations': donations,
            'received': 0,
            'time': datetime.datetime.utcnow().isoformat(),
            'season_id': SEASON_ID
        })

    async with board_batch_lock:
        try:
            board_batch_data[player.tag]['old_dons'] = old_donations
            board_batch_data[player.tag]['new_dons'] = new_donations
        except KeyError:
            board_batch_data[player.tag] = {
                'player_tag': player.tag,
                'old_dons': old_donations,
                'new_dons': new_donations,
                'old_rec': player.received,
                'new_rec': player.received,
                'trophies': player.trophies,
                'clan_tag': player.clan and player.clan.tag,
                'player_name': player.name
            }
    await update(player.tag)

async def on_clan_member_received(old_received, new_received, player, clan):
    log.info(f'Received on_clan_member_received event for player {player} of clan {clan}')
    await update(player.tag)
    if old_received > new_received:
        received = new_received
    else:
        received = new_received - old_received

    async with donationlog_batch_lock:
        donationlog_batch_data.append({
            'player_tag': player.tag,
            'player_name': player.name,
            'clan_tag': clan and clan.tag,
            'donations': 0,
            'received': received,
            'time': datetime.datetime.utcnow().isoformat(),
            'season_id': SEASON_ID
        })

    async with board_batch_lock:
        try:
            board_batch_data[player.tag]['old_rec'] = old_received
            board_batch_data[player.tag]['new_rec'] = new_received
        except KeyError:
            board_batch_data[player.tag] = {
                'player_tag': player.tag,
                'old_dons': player.donations,
                'new_dons': player.donations,
                'old_rec': old_received,
                'new_rec': new_received,
                'trophies': player.trophies,
                'clan_tag': player.clan and player.clan.tag,
                'player_name': player.name
            }


@tasks.loop(seconds=60.0)
async def trophylog_batch_insert_loop():
    log.info('Starting batch insert loop.')
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
            log.info('Registered %s trophy events to the database.', total)
        trophylog_batch_data.clear()


async def on_clan_member_trophies_change(old_trophies, new_trophies, player, clan):
    log.info(f'Received on_clan_member_trophy_change event for player {player} of clan {clan}')
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

    async with board_batch_lock:
        try:
            board_batch_data[player.tag]['trophies'] = new_trophies
        except KeyError:
            board_batch_data[player.tag] = {
                'player_tag': player.tag,
                'old_dons': player.donations,
                'new_dons': player.donations,
                'old_rec': player.received,
                'new_rec': player.received,
                'trophies': new_trophies,
                'clan_tag': player.clan and player.clan.tag,
                'player_name': player.name
            }

    if player.league and player.league.id == 29000022 and new_trophies > old_trophies:
        await update(player.tag)

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

#
# async def on_clan_member_league_change(old_league, new_league, player, clan):
#     if old_league.id > new_league.id:
#         return  # they dropped a league
#     if new_league.id == 29000000:
#         return  # unranked - probably start of season.
#
#     query = """SELECT channel_id
#                FROM events
#                INNER JOIN eventplayers
#                ON eventplayers.event_id = events.id
#                WHERE start_best_trophies < $1
#                AND player_tag = $2
#             """
#     fetch = await self.bot.pool.fetch(query, player.trophies, player.tag)
#     if not fetch:
#         return
#
#     msg = f"Breaking new heights! {player} just got promoted to {new_league} league!"
#
#     for record in fetch:
#         await self.safe_send(self.bot.get_channel(record['channel_id']), msg)


@tasks.loop(minutes=1.0)
async def last_updated_loop():
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
    async with last_updated_batch_lock:
        await pool.execute(
            query, list(last_updated_data.values()), SEASON_ID
        )
        last_updated_data.clear()


async def update(player_tag):
    async with last_updated_batch_lock:
        last_updated_data[player_tag] = {
            'player_tag': player_tag,
            'last_updated': datetime.datetime.utcnow().isoformat()
        }
#
async def on_clan_member_name_change(_, __, player, ___):
    await update(player.tag)
#
# async def on_clan_member_donation(self, _, __, player, ___):
#     await self.update(player.tag)

async def on_clan_member_versus_trophies_change(_, __, player, ___):
    await update(player.tag)

async def on_clan_member_level_change(_, __, player, ___):
    await update(player.tag)
#
# async def on_clan_member_trophies_change(self, _, __, player, ___):
#     pass  # could be a defense - doesn't mean online
#
# async def on_clan_member_received(self, _, __, player, ___):
#     await update(player.tag)  # don't have to be online to receive donations


async def on_clan_member_join(member, clan):
    player = await coc_client.get_player(member.tag)
    player_query = """INSERT INTO players (
                                    player_tag, 
                                    donations, 
                                    received, 
                                    trophies, 
                                    start_trophies, 
                                    season_id,
                                    start_friend_in_need,
                                    start_sharing_is_caring,
                                    start_attacks,
                                    start_defenses,
                                    start_best_trophies,
                                    start_update,
                                    clan_tag
                                    ) 
                VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8,$9,$10,True, $11) 
                ON CONFLICT (player_tag, season_id) 
                DO UPDATE SET clan_tag = $11
            """

    response = await pool.execute(
        player_query,
        player.tag,
        player.donations,
        player.received,
        player.trophies,
        SEASON_ID,
        player.achievements_dict['Friend in Need'].value,
        player.achievements_dict['Sharing is caring'].value,
        player.attack_wins,
        player.defense_wins,
        player.best_trophies,
        clan.tag
    )
    log.debug(f'New member {member} joined clan {clan}. Performed a query to insert them into players. '
              f'Status Code: {response}')

    query = """SELECT events.id 
               FROM events 
               INNER JOIN clans 
               ON clans.guild_id = events.guild_id 
               WHERE clans.clan_tag = $1
               AND events.start <= now()
               AND events.finish >= now()
            """
    fetch = await pool.fetch(query, clan.tag)
    if not fetch:
        return

    event_query = """INSERT INTO eventplayers (
                                        player_tag,
                                        trophies,
                                        event_id,
                                        start_friend_in_need,
                                        start_sharing_is_caring,
                                        start_attacks,
                                        start_defenses,
                                        start_trophies,
                                        start_best_trophies,
                                        start_update,
                                        live
                                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, True, True)
                        ON CONFLICT (player_tag, event_id)
                        DO UPDATE 
                        SET live=True
                        WHERE eventplayers.player_tag = $1
                        AND eventplayers.event_id = $2
                    """

    for n in fetch:
        response = await pool.execute(
            event_query,
            player.tag,
            player.trophies,
            n['id'],
            player.achievements_dict['Friend in Need'].value,
            player.achievements_dict['Sharing is caring'].value,
            player.attack_wins,
            player.defense_wins,
            player.trophies,
            player.best_trophies
          )

        log.debug(f'New member {member} joined clan {clan}. '
                  f'Performed a query to insert them into eventplayers. Status Code: {response}')


async def on_clan_member_leave(member, clan):
    query = "UPDATE players SET clan_tag = NULL where player_tag = $1 AND season_id = $2"
    await pool.execute(query, member.tag, SEASON_ID)


@tasks.loop(seconds=60.0)
async def update_clan_tags():
    query = "SELECT DISTINCT(clan_tag) FROM clans"
    fetch = await pool.fetch(query)
    log.info(f"Setting {len(fetch)} tags to update")
    coc_client._clan_updates = [n[0] for n in fetch]

if __name__ == "__main__":
    print("STARTING")
    update_clan_tags.start()
    batch_insert_loop.start()
    trophylog_batch_insert_loop.start()

    event_player_updater.add_exception_type(coc.HTTPException)
    event_player_updater.start()

    last_updated_loop.start()
    board_insert_loop.start()

    coc_client.add_events(
        on_clan_member_donation,
        on_clan_member_received,
        on_clan_member_trophies_change,
        on_clan_member_join,
        on_clan_member_level_change,
        on_clan_member_name_change,
        on_clan_member_versus_trophies_change
    )
    coc_client._clan_retry_interval = 60
    coc_client.start_updates('clan')
    coc_client.run_forever()
