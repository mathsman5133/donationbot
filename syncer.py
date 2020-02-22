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
log.setLevel(logging.DEBUG)
SEASON_ID = 8


loop = asyncio.get_event_loop()
pool = loop.run_until_complete(Table.create_pool(creds.postgres))
coc_client = coc.login(creds.email, creds.password, key_names="test", throttle_limit=30, key_count=3)


@tasks.loop(seconds=60.0)
async def main_syncer():
    query = "SELECT DISTINCT(clan_tag) FROM clans"
    fetch = await pool.fetch(query)

    query = """
            INSERT INTO players (
                player_tag, 
                player_name,
                clan_tag,
                prev_donations, 
                prev_received,
                season_id, 
                trophies,
                league_id
            )
            SELECT x.player_tag, 
                   x.player_name,
                   x.clan_tag,
                   x.donations, 
                   x.received,
                   $2,
                   x.trophies,
                   x.league_id

            FROM jsonb_to_recordset($1::jsonb)
            AS x(
                player_tag TEXT,
                player_name TEXT,
                clan_tag TEXT,
                donations INTEGER,
                received INTEGER, 
                trophies INTEGER,
                league_id INTEGER
            )
            ON CONFLICT (player_tag, season_id)
            DO UPDATE
            SET player_name    = excluded.player_name,
                clan_tag       = excluded.clan_tag,
                prev_donations = excluded.donations,
                prev_received  = excluded.received,
                trophies       = excluded.trophies,
                league_id      = excluded.league_id
            """

    players = []

    async for clan in coc_client.get_clans((n[0] for n in fetch), cache=False, update_cache=False):
        players.extend(
            {
                "player_tag": n.tag,
                "player_name": n.name,
                "clan_tag": n.clan and n.clan.tag,
                "donations": n.donations,
                "received": n.received,
                "trophies": n.trophies,
                "league_id": n.league.id
            }
            for n in clan.itermembers
        )

    await pool.execute(query, players, SEASON_ID)


@tasks.loop(seconds=60.0)
async def insert_new_players():
    query = "SELECT player_tag FROM players WHERE fresh_update = TRUE AND season_id = $1"
    fetch = await pool.fetch(query, SEASON_ID)

    players = []

    query = """
    UPDATE players
    SET player_name  = x.player_name,
        player_tag   = x.player_tag,
        clan_tag     = x.clan_tag,
        trophies     = x.trophies,
        versus_trophies = x.versus_trophies,
        fresh_update = FALSE,
        attacks      = x.attacks  - players.start_attacks,
        defenses     = x.defenses - players.start_defenses,
        versus_attacks = x.versus_attacks,
        donations    = x.fin + x.sic - players.start_friend_in_need - players.start_sharing_is_caring
    
    FROM(
        SELECT x.player_name, 
               x.player_tag,
               x.clan_tag,
               x.trophies,
               x.versus_trophies,
               x.attacks,
               x.defenses,
               x.versus_attacks,
               x.fin,
               x.sic
                              
        FROM jsonb_to_recordset($1::jsonb)
        AS x(
            player_name TEXT, 
            player_tag INTEGER,
            clan_tag TEXT, 
            trophies INTEGER,
            versus_trophies INTEGER,
            attacks INTEGER,
            defenses INTEGER,
            versus_attacks INTEGER,
            fin INTEGER,
            sic INTEGER
        )
    )
    AS x
    WHERE players.player_tag = x.player_tag
    AND players.season_id=$2
    """

    async for player in coc_client.get_players((n[0] for n in fetch), cache=False, update_cache=False):
        players.append({
            "player_name": player.name,
            "player_tag": player.tag,
            "clan_tag": player.clan and player.clan.tag,
            "trophies": player.trophies,
            "versus_trophies": player.versus_trophies,
            "attacks": player.attack_wins,
            "defenses": player.defense_wins,
            "versus_attacks": player.versus_attack_wins,
            "fin": player.achievements_dict["Friend in Need"].value,
            "sic": player.achievements_dict["Sharing is Caring"].value
        })
    await pool.execute(query, players, SEASON_ID)


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
                                    start_update
                                    ) 
                VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8,$9,$10,True) 
                ON CONFLICT (player_tag, season_id) 
                DO NOTHING
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
        player.best_trophies
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


if __name__ == "__main__":
    print("STARTING")
    main_syncer.start()
    event_player_updater.start()
    insert_new_players.start()
    asyncio.get_event_loop().run_forever()