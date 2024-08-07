import asyncio
import io
import itertools
import logging
import time
import os
import shutil

from pathlib import Path

from datetime import datetime, timedelta

import aiohttp
import httpx
import coc
import discord

from discord.ext import tasks
from prometheus_async.aio.web import start_http_server
from prometheus_client import Histogram, Counter

import creds

from botlog import setup_logging

from cogs.utils.db_objects import BoardConfig


REFRESH_EMOJI = discord.PartialEmoji(name="refresh", id=694395354841350254, animated=False)
LEFT_EMOJI = discord.PartialEmoji(name="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)    # [:arrow_left:]
RIGHT_EMOJI = discord.PartialEmoji(name="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)   # [:arrow_right:]
PERCENTAGE_EMOJI = discord.PartialEmoji(name="percent", id=694463772135260169, animated=False)
GAIN_EMOJI = discord.PartialEmoji(name="gain", id=696280508933472256, animated=False)
LAST_ONLINE_EMOJI = discord.PartialEmoji(name="lastonline", id=696292732599271434, animated=False)
HISTORICAL_EMOJI = discord.PartialEmoji(name="historical", id=694812540290465832, animated=False)

emojis = {
    "donation": (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI, PERCENTAGE_EMOJI, LAST_ONLINE_EMOJI, HISTORICAL_EMOJI),
    "trophy": (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI, GAIN_EMOJI, LAST_ONLINE_EMOJI, HISTORICAL_EMOJI),
    "legend": (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI),
    "war": (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI),
}
backgrounds = {
    "donation": "assets/wall-background_.png",
    "trophy": "assets/SummerWardenBackground.png",
    "legend": "assets/BattleGrassBackground.png",
    "war": "https://cdn.discordapp.com/attachments/594286547449282587/824491008099876885/BG-coc_BALLOON.jpg",
}
titles = {
    "donation": "Donation Leaderboard",
    "trophy": "Trophy Leaderboard",
    "legend": "Legend Leaderboard",
    "war": "War Leaderboard",
}
default_sort_by = {
    "donation": "donations",
    "trophy": "trophies",
    "legend": "finishing",
    "war": "stars",
}


BOARD_PLACEHOLDER = """
This is a Placeholder message for your {board} board.

Please don't delete this message, otherwise the board will be deleted.
This message should be replaced shortly by your {board} board.

If a board doesn't appear, please make sure you have `+add clan #clantag #dt-boards` properly, by using `+info`.
"""

GLOBAL_BOARDS_CHANNEL_ID = 663683345108172830

log = logging.getLogger(__name__)

counter = Counter("donbot_boards_processed", "The number of boards processed.")
render_histo = Histogram("donbot_boards_render_latency_seconds", "Latency of board processing.", buckets=(0.01, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0))
overall_histo = Histogram("donbot_boards_overall_latency_seconds", "Latency of board processing.", buckets=(0.01, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0))

class HTMLImages:
    def __init__(self, players, title=None, image=None, sort_by=None, footer=None, offset=None, board_type='donation', fonts=None, session=None, coc_client=None):
        self.players = players
        self.session = session
        self.coc_client = coc_client

        self.emoji_data = {}

        self.offset = offset or 1
        self.title = title or titles.get(board_type, backgrounds['donation'])
        self.image = image

        self.footer = footer
        self.fonts = fonts or "symbola, Helvetica, Verdana,courier,arial,symbola"
        self.board_type = board_type

        self.html = ""
        if board_type == "donation":
            self.columns = ["#", None, "Player Name", "Dons", "Rec", "Ratio", "Last On"]
        elif board_type == "legend":
            self.columns = ["#", None, "Player Name", "Initial", "Gain", "Loss", "Final"]
        elif board_type == "war":
            self.columns = ["#", None, "Player Name", "Stars", "Dest %", "3 ⭐", "2 ⭐", "Missed"]
        else:
            self.columns = ["#", None, "Player Name", "Cups", "Gain", "Last On"]

        if sort_by and board_type == "donation":
            sort_columns = ("#", "Clan", "Player Name", "donations", "received", "ratio", "last_online ASC, player_name")
            self.selected_index = [sort_columns.index('donations' if sort_by == 'donation' else sort_by)]
        elif sort_by and board_type == "legend":
            sort_columns = ("#", "Clan", "Player Name", "starting", "gain", "loss", "finishing")
            self.selected_index = [sort_columns.index(sort_by)]
        elif sort_by and board_type == "war":
            sort_columns = ("#", "Clan", "Player Name", "stars", "destruction", "3_star", "2_star", "1_star", "0_star", "missed")
            self.selected_index = [sort_columns.index(sort_by)]
        elif sort_by:
            sort_columns = ("#", "Clan", "Player Name", "trophies", "gain", "last_online ASC, player_name")
            self.selected_index = [sort_columns.index(sort_by.replace('donations', 'trophies'))]
        else:
            self.selected_index = []

        if len({p['clan_tag'] for p in players}) > 1:
            # re-assign the sorted column index
            # self.selected_index = [col + 1 for col in self.selected_index]
            self.show_clan = True
            self.columns.pop(1)
            self.columns.insert(1, '<img id="icon_cls" src="badge.png">')
        else:
            self.show_clan = False

    async def load_or_save_custom_emoji(self, emoji_or_clan_id: str, clan_tag: str = None):
        emoji_or_clan_id = emoji_or_clan_id.replace("#", "")
        if emoji_or_clan_id in self.emoji_data:
            return emoji_or_clan_id
        else:
            path = Path(f'assets/board_icons/{emoji_or_clan_id}.png')
            if path.is_file():
                with open(path, "rb") as fp:
                    self.emoji_data[emoji_or_clan_id] = fp.read()
                return emoji_or_clan_id

            else:
                if clan_tag:
                    clan = await self.coc_client.get_clan(clan_tag)
                    if clan:
                        b = await clan.badge.save(path)
                        return b and (await self.load_or_save_custom_emoji(emoji_or_clan_id, clan_tag)) or False
                else:
                    resp = await self.session.get(f"{discord.Asset.BASE}/emojis/{emoji_or_clan_id}.png")
                    if resp.status_code == 200:
                        data = resp.read()
                        with open(f'assets/board_icons/{emoji_or_clan_id}.png', 'wb') as f:
                            f.write(data)

                        self.emoji_data[emoji_or_clan_id] = data
                        return emoji_or_clan_id

    def get_readable(self, delta):
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if delta.days:
            return f"{days}d {hours}h"
        else:
            return f"{hours}h {minutes}m"

    def add_style(self):
        if len(self.players) >= 30:
            body = """
body {
width: 2500px;
}
"""
            width = "width: 50%;"
        else:
            body = """
body {
width: 1200px;
background: linear-gradient(rgba(255,255,255,.2), rgba(255,255,255,.2)), url(""" + (self.image or 'background.png') + """) no-repeat;
background-size: cover;
}
"""
            width = "width: 100%;"
        self.html += """
<!DOCTYPE html>
<meta charset="UTF-8">
<html>
<head>
<style>
""" + body + """
#icon_cls {
    position: relative;
    height: 64px;
    width: 64px;
    align:center;
}
#icon_clsii {
    position: relative;
    height: 40px;
    width: 40px;
    align:center;
}
table {
  border-collapse: seperate;
  border-spacing: 0 12px;
""" + width + """
  padding-left: 30px;
  padding-right: 30px;
  float: left
}

td, th {
  text-align: center;
  letter-spacing: 1px;
  font-size: 42px;
  padding: 7px;
  box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.19);
}

th {
  border: 1px solid #404040;
  background-color: rgba(185, 147, 108, 0.6);
}
.selected {
  background-color: rgba(170,204,238,0.8);
}
.footer {
  float: left;
  text-align: left;
  font-size: 40px;
  font-style: bold;
  padding: 2px;
  top: 0;
  margin-top:0;
  margin-bottom:0;
}

tr:nth-child(even) {
  background-color: rgba(166, 179, 196, 0.8);
}
tr:nth-child(odd) {
  background-color: rgba(196, 186, 133, 0.8);
}

header {
  background:-webkit-gradient(linear,left bottom,left top,color-stop(20%,rgb(196, 183, 166)),color-stop(80%,rgb(220, 207, 186)));
  font-size: 70px;
  margin-left: auto;
  margin-right: auto;
  text-align: center;
  font-style: bold;
  font-weight: 200;
  letter-spacing: 1.5px;
  opacity: 1;
}

.title{
font-weight: bold;
}
</style>
        """

    def add_body(self):
        self.html += '<body>'

    def add_title(self):
        self.html += f"<header><strong>{self.title}</strong></header>"

    def add_table(self, players):
        to_add = "<table>"

        to_add += "<tr>" + "".join(
            f"<th{' class=selected' if i in self.selected_index else ''}>{column}</th>"
            for i, column in enumerate(self.columns) if column
        ) + "</tr>"

        for player in players:
            to_add += "<tr>" + "".join(
                f"<td{' class=selected' if i in self.selected_index else ''}>{cell}</td>"
                for i, cell in enumerate(player) if cell != ''
            ) + "</tr>"

        to_add += "</table>"
        self.html += to_add

    def add_footer(self):
        if self.footer:
            self.html += f'<h6 class="footer">{self.footer}</h6>'

    def end_html(self):
        self.html += "</body></html>"

    async def get_img_src(self, player):
        emoji = player['emoji']
        if emoji and emoji.isdigit():
            uri = await self.load_or_save_custom_emoji(player['emoji'], None)
        elif emoji:
            return emoji
        elif player['clan_tag']:
            uri = await self.load_or_save_custom_emoji(player['clan_tag'], player['clan_tag'])
        else:
            return ''

        return uri and f'<img id="icon_clsii" src="{uri}.png">' or ''

    async def parse_players(self):
        if self.board_type == 'donation':
            self.players = [
                (
                    str(i) + ".",
                    self.show_clan and await self.get_img_src(p) or '',
                    p['player_name'],
                    p['donations'],
                    p['received'],
                    round(p['donations'] / (p['received'] or 1), 2),
                    self.get_readable(p['last_online']),
                 )
                for i, p in enumerate(self.players, start=self.offset)
            ]
        elif self.board_type == 'legend':
            self.players = [
                (
                    str(i) + ".",
                    self.show_clan and await self.get_img_src(p) or '',
                    p['player_name'],
                    p['starting'],
                    f"{p['gain']} <sup>({p['attacks']})</sup>", f"{p['loss']} <sup>({p['defenses']})</sup>",
                    p['finishing'],
                )
                for i, p in enumerate(self.players, start=self.offset)
            ]
        elif self.board_type == "war":
            players = []
            for player_tag, rows in itertools.groupby(sorted(self.players, key=lambda r: r['player_tag']), key=lambda r: r['player_tag']):
                rows = list(rows)
                by_star = {r['stars']: r for r in rows}

                players.append(
                    (
                        self.show_clan and await self.get_img_src(rows[0]) or '',
                        rows[0]['player_name'],
                        sum(r['stars'] * r['star_count'] for r in rows if r['stars'] >= 0),
                        sum(r['destruction_count'] for r in rows),
                        by_star.get(3, {}).get('star_count', 0),
                        by_star.get(2, {}).get('star_count', 0),
                        # by_star.get(1, {}).get('stars', 0),
                        # by_star.get(0, {}).get('stars', 0),
                        by_star.get(-1, {}).get('star_count', 0),
                    )
                )

            self.players = [(str(index) + ".", *player) for index, player in enumerate(sorted(players, key=lambda r: (r[2], r[3]), reverse=True), start=self.offset)]

        else:
            self.players = [
                (
                    str(i) + ".",
                    self.show_clan and await self.get_img_src(p) or '',
                    p['player_name'],
                    p['trophies'],
                    p['gain'],
                    self.get_readable(p['last_online'])
                )
                for i, p in enumerate(self.players, start=self.offset)
            ]

    async def make(self):
        s = time.perf_counter()
        await self.parse_players()
        self.add_style()
        self.add_body()
        self.add_title()
        if len(self.players) >= 30:
            self.add_table(self.players[:int(len(self.players)/2)])
            self.add_table(self.players[int(len(self.players)/2):])
        else:
            self.add_table(self.players)

        if not self.board_type == 'legend':
            self.add_footer()
        self.end_html()

        files = [
            ('file', ("index.html", io.BytesIO(self.html.encode("utf-8")))),
            ('file', ("badge.png", open("assets/reddit badge.png", "rb"))),
            *[('file', (k + ".png", io.BytesIO(v))) for k, v in self.emoji_data.items()]
        ]
        if not self.image:
            files.append(('file', ("background.png", open(backgrounds.get(self.board_type, backgrounds["donation"]), "rb"))))

        data = {'optimizeForSpeed': 'true', 'skipNetworkIdleEvent': 'true'}

        res = await self.session.post("http://localhost:3000/forms/chromium/screenshot/html", files=files, data=data)
        return io.BytesIO(res.read())


class SyncBoards:
    def __init__(self, bot, start_loop=False, pool=None, session=None, coc_client=None, fake_clan_guilds=None):
        self.bot = bot
        self.pool = pool or bot.pool
        self.coc_client = coc_client or bot.coc

        self.aiohttp_session = aiohttp.ClientSession()
        self.session = httpx.AsyncClient()

        self.season_id = 17

        self.last_updated_channels = {}
        self.season_meta = {}

        self.webhooks = None
        self.fake_clan_guilds = fake_clan_guilds or set()

        self.throttler = coc.BasicThrottler(1)

        self.reset_season_id.add_exception_type(Exception)
        self.reset_season_id.start()

        self.start_loops = start_loop
        if start_loop:
            for task in (self.update_board_loops, self.flush_saved_board_icons):
                task.add_exception_type(Exception)
                task.start()

        self.legend_board_reset.add_exception_type(Exception)
        self.legend_board_reset.start()

    async def on_init(self):
        self.webhooks = itertools.cycle(
            discord.Webhook.partial(
                payload['id'], payload['token'], session=self.aiohttp_session
            ) for payload in await self.bot.http.guild_webhooks(691779140059267084)
        )

        await self.set_season_id()

    async def close(self):
        if not self.session.is_closed:
            await self.session.aclose()

    async def set_season_id(self):
        fetch = await self.pool.fetchrow("SELECT id FROM seasons WHERE start < now() ORDER BY start DESC;")
        self.season_id = fetch['id']

    async def get_season_meta(self, season_id):
        try:
            return self.season_meta[season_id]
        except KeyError:
            fetch = await self.pool.fetchrow("SELECT start, finish FROM seasons WHERE id = $1", season_id)
            season_start, season_finish = fetch[0].strftime('%d-%b-%Y'), fetch[1].strftime('%d-%b-%Y')
            self.season_meta[season_id] = (season_start, season_finish)
            return (season_start, season_finish)

    @tasks.loop(seconds=5.0)
    async def reset_season_id(self):
        next_season = coc.utils.get_season_end()
        await asyncio.sleep((datetime.utcnow() - next_season).total_seconds() + 1)  # allow some buffer
        await self.set_season_id()

    @tasks.loop(seconds=5.0)
    async def update_board_loops(self):
        log.info("starting loop to update boards")
        if not self.webhooks:
            log.info("no webhooks, skipping")
            return

        try:
            fetch = await self.pool.fetch("UPDATE boards SET need_to_update=False WHERE need_to_update=True AND toggle=True RETURNING *")
            self.fake_clan_guilds = {row['guild_id'] for row in await self.pool.fetch("SELECT DISTINCT guild_id FROM clans WHERE fake_clan=True")}
            log.info("updating %s boards", len(fetch))
        except Exception as exc:
            log.exception("failed to fetch boards that need to be updated...", exc_info=exc)

        current_tasks = []
        for n in fetch:
            config = BoardConfig(bot=self.bot, record=n)
            current_tasks.append(asyncio.create_task(self.run_board(config)))

        res = await asyncio.gather(*current_tasks)

    async def run_board(self, config):
        try:
            async with self.throttler:
                log.info("updating board for channel: %s, title: %s", config.channel_id, config.title)
                await self.update_board(config)
        except:
            log.exception("board error.... CHANNEL ID: %s", config.channel_id)

    async def set_new_message(self, config):
        try:
            params = discord.http.handle_message_parameters(content=BOARD_PLACEHOLDER.format(board=config.type))
            message = await self.bot.http.send_message(config.channel_id, params=params)
        except (discord.Forbidden, discord.NotFound):
            await self.pool.execute("UPDATE boards SET toggle = FALSE WHERE channel_id = $1", config.channel_id)
            return

        try:
            for emoji in emojis[config.type]:
                await self.bot.http.add_reaction(message['channel_id'], message['id'], emoji._as_reaction())
        except:
            log.info('failed to add reactions for message_id %s', message['id'])

        fetch = await self.pool.fetchrow("UPDATE boards SET message_id = $1 WHERE channel_id = $2 AND type = $3 RETURNING *", int(message['id']), config.channel_id, config.type)
        if fetch:
            return BoardConfig(record=fetch, bot=self.bot)

    @staticmethod
    def get_next_per_page(page_no, config_per_page):
        if config_per_page == 0:
            lookup = {
                1: 15,
                2: 15,
                3: 20,
                4: 25,
                5: 25
            }
            if page_no > 5:
                return 50
            return lookup[page_no]

        return config_per_page

    async def update_board(self, config, update_global=False, divert_to=None):
        if config.channel_id == GLOBAL_BOARDS_CHANNEL_ID and not update_global:
            return
        if not config.message_id and not divert_to:
            config = await self.set_new_message(config)
            if not config:
                return

        start = time.perf_counter()

        season_id = config.season_id or self.season_id
        if season_id < 0:
            # default season id is null, which means historical will make it go negative, so just take it from current id.
            season_id = self.season_id + season_id

        offset = 0
        for i in range(1, config.page):
            offset += self.get_next_per_page(i, config.per_page)

        # fake_clan_in_server = config.guild_id in self.fake_clan_guilds
        # join = "(clans.clan_tag = players.clan_tag OR " \
        #        "(players.fake_clan_tag IS NOT NULL AND clans.clan_tag = players.fake_clan_tag))" \
        #     if fake_clan_in_server else "clans.clan_tag = players.clan_tag"

        if config.channel_id == GLOBAL_BOARDS_CHANNEL_ID:
            query = f"""SELECT DISTINCT player_name,
                                        players.clan_tag,
                                        clans.emoji,
                                        donations,
                                        received,
                                        trophies,
                                        now() - last_updated AS "last_online",
                                        CASE WHEN received = 0 THEN cast(donations as decimal)
                                             ELSE cast(donations as decimal) / received
                                        END ratio,
                                        trophies - start_trophies AS "gain"
                       FROM players
                       INNER JOIN clans
                       ON clans.clan_tag = players.clan_tag
                       WHERE season_id = $1
                       ORDER BY {'donations' if config.sort_by == 'donation' else config.sort_by} DESC
                       NULLS LAST
                       LIMIT $2
                       OFFSET $3
                    """
            fetch = await self.pool.fetch(
                query,
                season_id,
                self.get_next_per_page(config.page, config.per_page),
                offset
            )
        elif config.type == "legend":
            query = f"""
                        WITH cte AS (
                            SELECT DISTINCT player_tag, player_name 
                            FROM players 
                            INNER JOIN clans 
                            ON clans.clan_tag = players.clan_tag
                            WHERE clans.channel_id = $1
                            AND season_id = $5
                        ),
                        cte2 AS (
                            SELECT emoji, clan_tag FROM clans WHERE channel_id=$1
                        )
                        SELECT DISTINCT cte.player_name, legend_days.clan_tag, cte2.emoji, starting, gain, loss, finishing, legend_days.attacks, legend_days.defenses
                        FROM legend_days 
                        INNER JOIN cte
                        ON cte.player_tag = legend_days.player_tag
                        INNER JOIN cte2 
                        ON legend_days.clan_tag = cte2.clan_tag
                        WHERE day = $2
                        ORDER BY {config.sort_by} DESC
                        NULLS LAST
                        LIMIT $3
                        OFFSET $4
                    """
            fetch = await self.pool.fetch(
                query,
                config.channel_id,
                self.legend_day,
                self.get_next_per_page(config.page, config.per_page),
                offset,
                season_id,
            )
        elif config.type == "war":
            query = f"""
                    WITH cte AS (
                            SELECT DISTINCT player_tag, player_name 
                            FROM players 
                            INNER JOIN clans 
                            ON clans.clan_tag = players.clan_tag
                            WHERE clans.channel_id = $1
                            AND players.season_id = $2
                    ),
                    cte2 AS (
                        SELECT emoji, clan_tag FROM clans WHERE channel_id=$1
                    )
                    SELECT COUNT(*) as star_count, SUM(destruction) as destruction_count, cte.player_tag, cte.player_name, stars, cte2.emoji, war_attacks.clan_tag
                    FROM war_attacks 
                    INNER JOIN cte 
                    ON cte.player_tag = war_attacks.player_tag 
                    INNER JOIN seasons 
                    ON start < load_time 
                    AND load_time < finish
                    LEFT JOIN cte2
                    ON cte2.clan_tag = war_attacks.clan_tag
                    WHERE seasons.id = $2
                    GROUP BY cte.player_tag, cte.player_name, stars, cte2.emoji, war_attacks.clan_tag
                    UNION ALL
                    SELECT SUM(attacks_missed) as star_count, 0 as destruction_count, cte.player_tag, cte.player_name, -1 as stars, cte2.emoji, war_missed_attacks.clan_tag
                    FROM war_missed_attacks
                    INNER JOIN cte 
                    ON cte.player_tag = war_missed_attacks.player_tag
                    INNER JOIN seasons 
                    ON start < load_time 
                    AND load_time < finish
                    LEFT JOIN cte2 
                    ON cte2.clan_tag = war_missed_attacks.clan_tag
                    WHERE seasons.id = $2
                    GROUP BY cte.player_tag, cte.player_name, cte2.emoji, war_missed_attacks.clan_tag
                    ORDER BY star_count DESC, destruction_count DESC
                    LIMIT $3
                    OFFSET $4
            """
            fetch = await self.pool.fetch(
                query,
                config.channel_id,
                season_id,
                self.get_next_per_page(config.page, config.per_page),
                offset
            )
        else:
            query = f"""SELECT DISTINCT player_name,
                                        players.clan_tag,
                                        players.fake_clan_tag,
                                        clans.emoji,
                                        donations,
                                        received,
                                        trophies,
                                        now() - last_updated AS "last_online",
                                        CASE WHEN received = 0 THEN cast(donations as decimal)
                                             ELSE cast(donations as decimal) / received
                                        END ratio,
                                        trophies - start_trophies AS "gain"
                       FROM players
                       INNER JOIN clans
                       ON clans.clan_tag = players.clan_tag
                       WHERE clans.channel_id = $1
                       AND season_id = $2
                       ORDER BY {'donations' if config.sort_by == 'donation' else config.sort_by} DESC
                       NULLS LAST
                       LIMIT $3
                       OFFSET $4
                    """
            fetch = await self.pool.fetch(
                query,
                config.channel_id,
                season_id,
                self.get_next_per_page(config.page, config.per_page),
                offset
            )

        if not fetch:
            return  # nothing to do/add

        season_start, season_finish = await self.get_season_meta(season_id)

        s1 = time.perf_counter()
        table = self.table = HTMLImages(
            players=fetch,
            title=config.title,
            image=config.icon_url,
            sort_by=config.sort_by,
            footer=f"Season: {season_start} - {season_finish}.",
            offset=offset + 1,
            board_type=config.type,
            session=self.session,
            coc_client=self.coc_client,
        )
        render = await table.make()
        s2 = (time.perf_counter() - s1)*1000
        overall = (time.perf_counter() - start)*1000

        perf_log = f"Perf: {overall}ms\n" \
                   f"Build Image Perf: {s2}ms\n" \
                   f"Channel: {config.channel_id}\n" \
                   f"Guild: {config.guild_id}"
        if divert_to:
            log.info('diverting board to %s channel_id', divert_to)
            try:
                params = discord.http.handle_message_parameters(file=discord.File(render, f'{config.type}board.png'))
                await self.bot.http.send_message(channel_id=divert_to, params=params)
            except Exception as e:
                log.info('failed to send legend log to channel %s: %s', config.channel_id, e)
            return

        log.info(perf_log)

        counter.inc()
        render_histo.observe(s2/1000)

        logged_board_message = await next(self.webhooks).send(
            perf_log, file=discord.File(render, f'{config.type}board.png'), wait=True
        )
        embed = discord.Embed(timestamp=discord.utils.utcnow())
        embed.set_image(url=logged_board_message.attachments[0].url)
        embed.set_footer(text="Last Updated", icon_url="https://cdn.discordapp.com/avatars/427301910291415051/8fd702a4bbec20941c72bc651279c05c.webp?size=1024")

        try:
            params = discord.http.handle_message_parameters(
                content=None,
                embed=embed,
            )
            await self.bot.http.edit_message(config.channel_id, config.message_id, params=params)
        except discord.NotFound:
            await self.set_new_message(config)
        except discord.HTTPException:
            await self.pool.execute("UPDATE boards SET toggle = FALSE WHERE channel_id = $1", config.channel_id)

            params = discord.http.handle_message_parameters(
                content="Please enable `Embed Links` permission for me to update your board.",
            )
            await self.bot.http.edit_message(
                config.channel_id,
                config.message_id,
                params=params
            )
        except:
            log.exception('trying to send board for %s', config.channel_id)

        overall_histo.observe(time.perf_counter() - start)

    @tasks.loop(hours=1.0)
    async def flush_saved_board_icons(self):
        try:
            shutil.rmtree('assets/board_icons')
            os.makedirs('assets/board_icons')
        except:
            log.exception('failed to flush saved board icons')

    @tasks.loop(seconds=5.0)
    async def legend_board_reset(self):
        log.info('running legend trophies')
        now = datetime.utcnow()
        if now.hour >= 5:
            tomorrow = (now + timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
        else:
            tomorrow = now.replace(hour=5, minute=0, second=0, microsecond=0)

        try:
            self.legend_day = tomorrow - timedelta(days=1)
            seconds = (tomorrow - now).total_seconds()
            log.info("Legend board resetter sleeping for %s seconds", seconds)
            await asyncio.sleep(seconds)
            if not self.start_loops:
                return

            fetch = await self.pool.fetch("SELECT * FROM boards WHERE toggle=True AND type='legend' AND divert_to_channel_id is not null")
            log.info("Legend board archiving for %s boards", len(fetch))
            for row in fetch:
                try:
                    config = BoardConfig(record=row, bot=self.bot)
                    # we just want to fool the update function to show all the players.
                    config.page = 1
                    config.per_page = 200
                    config.sort_by = 'finishing'

                    await self.update_board(config, divert_to=row['divert_to_channel_id'] or config.channel_id)

                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    continue

            query = """INSERT INTO legend_days (player_tag, day, starting, gain, loss, finishing) 
                       SELECT player_tag, $1, trophies, 0, 0, trophies
                       FROM players
                       WHERE season_id = $2
                       AND league_id = 29000022
                       ON CONFLICT (player_tag, day)
                       DO NOTHING;
                    """
            try:
                await self.pool.execute(query, tomorrow, self.season_id)
            except:
                log.exception('resetting legend players trophies')

        except:
            log.exception('resetting legend boards')


async def main():
    from bot import setup_db

    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.guild_reactions = True
    intents.members = True
    intents.emojis = True

    stateless_bot = discord.Client(intents=intents)

    # async with stateless_bot:

    await start_http_server(port=8001)

    client = coc.Client(key_names="donbot_syncer")
    await client.login(creds.email, creds.password)

    pool = await setup_db()

    stateless_bot.session = aiohttp.ClientSession()
    setup_logging(stateless_bot)
    await stateless_bot.login(creds.bot_token)

    sb = SyncBoards(stateless_bot, start_loop=True, coc_client=client, pool=pool)
    await sb.on_init()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
    asyncio.get_event_loop().run_forever()
