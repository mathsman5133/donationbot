import sys
import coc as coc_pck
import asyncpg
import creds
import asyncio
from cogs.utils.db import Table

loop = asyncio.get_event_loop()
coc = coc_pck.login(creds.email, creds.password, client=coc_pck.Client, key_names='aws', throttle_limit=30, key_count=3)
pool = loop.run_until_complete(Table.create_pool(creds.postgres, command_timeout=60))


class COCCache(coc_pck.Cache):
    async def get(self, cache_type, key):
        return

    async def set(self, cache_type, key, value):
        return

    async def pop(self, cache_type, key):
        return

    async def items(self, cache_type):
        return dict()

    async def keys(self, cache_type):
        return list()

    async def values(self, cache_type):
        return list()


async def insert_final(con, data, season_id):
    query = """UPDATE players SET end_friend_in_need    = x.friend_in_need, 
                                  end_sharing_is_caring = x.sharing_is_caring,
                                  end_attacks           = x.attacks,
                                  end_defenses          = x.defenses,
                                  end_best_trophies     = x.best_trophies,
                                  final_update          = True

                FROM(
                    SELECT x.player_tag, 
                           x.friend_in_need, 
                           x.sharing_is_caring,
                           x.attacks,
                           x.defenses,
                           x.best_trophies

                    FROM jsonb_to_recordset($1::jsonb)
                    AS x(
                        player_tag TEXT, 
                        friend_in_need INTEGER, 
                        sharing_is_caring INTEGER,
                        attacks INTEGER,
                        defenses INTEGER,
                        best_trophies INTEGER
                        )
                    )
            AS x
            WHERE players.player_tag = x.player_tag
            AND players.season_id=$2
            """
    await con.execute(query, data, season_id - 1)


async def new_season_pull(number, season_id):
    query = "SELECT DISTINCT player_tag FROM players WHERE season_id = $1 AND start_update = False LIMIT $2;"
    fetch = await pool.fetch(query, season_id, number)

    query = """UPDATE players SET start_friend_in_need = x.friend_in_need, 
                                  start_sharing_is_caring = x.sharing_is_caring,
                                  start_attacks = x.attacks,
                                  start_defenses = x.defenses,
                                  start_trophies = x.trophies,
                                  start_best_trophies = x.best_trophies,
                                  start_update = True

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
    counter = 0
    data = []
    async for player in coc.get_players((n[0] for n in fetch)):
        if counter == 100:
            # This is basically to ensure we don't have 10k records in memory at any one time.
            # Safety net incase something fails, too.
            await pool.execute(query, data, season_id)
            await insert_final(pool, data, season_id)
            data.clear()
            counter = 0

        data.append({
            'player_tag': player.tag,
            'friend_in_need': player.achievements_dict['Friend in Need'].value,
            'sharing_is_caring': player.achievements_dict['Sharing is caring'].value,
            'attacks': player.achievements_dict['Conqueror'].value,
            'defenses': player.achievements_dict['Unbreakable'].value,
            'trophies': player.trophies,
            'best_trophies': player.best_trophies
        })
        counter += 1

# for _ in range(5):
#     try:
#         loop.run_until_complete(coc.get_clan('12345'))
#     except: pass
loop.run_until_complete(new_season_pull(int(sys.argv[0]), int(sys.argv[1])))
