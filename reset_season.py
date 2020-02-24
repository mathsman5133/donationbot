import asyncio
import logging
import sys

import coc

import creds
from cogs.utils.db import Table

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

loop = asyncio.get_event_loop()
client = coc.login(creds.email, creds.password, key_names='test', key_count=3, throttle_limit=30)
pool = loop.run_until_complete(Table.create_pool(creds.postgres))

SEASON_ID = 9


async def new_season_pull(number=5000):
    query = "SELECT DISTINCT player_tag FROM players WHERE season_id = $1 AND start_update = False LIMIT $2;"
    fetch = await pool.fetch(query, SEASON_ID, number)

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

    counter = 0
    data = []
    async for player in client.get_players((n[0] for n in fetch), cache=False, update_cache=False):
        if counter == 100:
            # This is basically to ensure we don't have 10k records in memory at any one time.
            # Safety net incase something fails, too.
            q = await pool.execute(query, data, SEASON_ID)
            q2 = await pool.execute(query2, data, SEASON_ID - 1)
            data.clear()
            counter = 0
            log.info(f"Done query: {q}, {q2}")


        data.append({
            'player_tag': player.tag,
            'friend_in_need': player.achievements_dict['Friend in Need'].value,
            'sharing_is_caring': player.achievements_dict['Sharing is caring'].value,
            'attacks': player.attack_wins,
            'defenses': player.defense_wins,
            'trophies': player.trophies,
            'best_trophies': player.best_trophies
        })
        counter += 1


for _ in range(int(sys.argv[1])):
    loop.run_until_complete(new_season_pull(1000))
