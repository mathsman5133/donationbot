import asyncio
import logging
import sys
import time

import coc

import creds
from cogs.utils.db import Table

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

loop = asyncio.get_event_loop()
client = coc.login(creds.email, creds.password, key_names='test2', key_count=6, throttle_limit=30)
pool = loop.run_until_complete(Table.create_pool(creds.postgres))

SEASON_ID = 11

for _ in range(10):
    try:
        loop.run_until_complete(client.get_clan('abc123'))
    except:
        pass

async def new_season_pull():
    s = time.perf_counter()
    query = "SELECT DISTINCT player_tag FROM players WHERE season_id = $1 AND start_update = False;"
    fetch = await pool.fetch(query, SEASON_ID)

    tasks_ = []
    for i in range(int(len(fetch) / 100)):
        task = asyncio.ensure_future(get_and_do_updates((n[0] for n in fetch[i:i+100]), SEASON_ID))
        tasks_.append(task)

    await asyncio.gather(*tasks_)
    log.critical(f"new season pull done, took {(time.perf_counter() - s)*1000}ms")

async def get_and_do_updates(player_tags, season_id):
    s = time.perf_counter()
    query = """UPDATE players SET start_friend_in_need = x.friend_in_need, 
                                  start_sharing_is_caring = x.sharing_is_caring,
                                  start_attacks = x.attacks,
                                  start_defenses = x.defenses,
                                  start_trophies = x.trophies,
                                  start_best_trophies = x.best_trophies,
                                  start_update = True,
                                  ignore = TRUE

                FROM(
                    SELECT x.player_tag, 
                           x.friend_in_need, 
                           x.sharing_is_caring,
                           x.attacks,
                           x.defenses,
                           x.trophies,
                           x.best_trophies

                    FROM jsonb_to_recordset($1::jsonb)
                    AS x(
                        player_tag TEXT, 
                        friend_in_need INTEGER, 
                        sharing_is_caring INTEGER,
                        attacks INTEGER,
                        defenses INTEGER,
                        trophies INTEGER,
                        best_trophies INTEGER
                        )
                    )
            AS x
            WHERE players.player_tag = x.player_tag
            AND players.season_id=$2
            """
    query2 = """UPDATE players SET end_friend_in_need = x.friend_in_need, 
                                  end_sharing_is_caring = x.sharing_is_caring,
                                  end_attacks = x.attacks,
                                  end_defenses = x.defenses,
                                  end_best_trophies = x.best_trophies,
                                  final_update = True,
                                  ignore = TRUE

                FROM(
                    SELECT x.player_tag, 
                           x.friend_in_need, 
                           x.sharing_is_caring,
                           x.attacks,
                           x.defenses,
                           x.trophies,
                           x.best_trophies

                    FROM jsonb_to_recordset($1::jsonb)
                    AS x(
                        player_tag TEXT, 
                        friend_in_need INTEGER, 
                        sharing_is_caring INTEGER,
                        attacks INTEGER,
                        defenses INTEGER,
                        trophies INTEGER,
                        best_trophies INTEGER
                        )
                    )
            AS x
            WHERE players.player_tag = x.player_tag
            AND players.season_id=$2"""

    data = []
    async for player in client.get_players(player_tags, cache=False, update_cache=False):
        data.append({
            'player_tag': player.tag,
            'friend_in_need': player.achievements_dict['Friend in Need'].value,
            'sharing_is_caring': player.achievements_dict['Sharing is caring'].value,
            'attacks': player.attack_wins,
            'defenses': player.defense_wins,
            'trophies': player.trophies,
            'best_trophies': player.best_trophies
        })

    q = await pool.execute(query, data, season_id)
    q2 = await pool.execute(query2, data, season_id - 1)
    log.info(f"Done update players: {q}, {q2}, {(time.perf_counter() - s)*1000}ms")


loop.run_until_complete(new_season_pull())
