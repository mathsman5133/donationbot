import asyncio
import io
import itertools
import logging
import time

from datetime import datetime

import aiohttp
import discord

from discord.ext import tasks

import creds

from cogs.utils.db import Table
from cogs.utils.db_objects import BoardConfig


REFRESH_EMOJI = discord.PartialEmoji(name="refresh", id=694395354841350254, animated=False)
LEFT_EMOJI = discord.PartialEmoji(name="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)    # [:arrow_left:]
RIGHT_EMOJI = discord.PartialEmoji(name="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f", id=None, animated=False)   # [:arrow_right:]
PERCENTAGE_EMOJI = discord.PartialEmoji(name="percent", id=694463772135260169, animated=False)
GAIN_EMOJI = discord.PartialEmoji(name="gain", id=696280508933472256, animated=False)
LAST_ONLINE_EMOJI = discord.PartialEmoji(name="lastonline", id=696292732599271434, animated=False)
HISTORICAL_EMOJI = discord.PartialEmoji(name="historical", id=694812540290465832, animated=False)

GLOBAL_BOARDS_CHANNEL_ID = 663683345108172830

log = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
pool = loop.run_until_complete(Table.create_pool(creds.postgres))

logging.basicConfig(level=logging.INFO)


class HTMLImages:
    def __init__(self, players, title=None, image=None, sort_by=None, footer=None, offset=None, donationboard=None):
        self.players = players

        self.donationboard = donationboard
        self.offset = offset or 1
        self.title = title or "Donation Leaderboard" if donationboard else "Trophy Leaderboard"
        self.image = image or "https://cdn.discordapp.com/attachments/641594147374891029/767306860306759680/dc0f83c3eba7fad4cbe8de3799708e93.jpg" if donationboard else "https://cdn.discordapp.com/attachments/681438398455742536/768649037250560060/clash_cliffs2-min.png"
        self.footer = footer

        self.html = ""
        if donationboard:
            self.columns = ("#", "Player Name", "Dons", "Rec", "Ratio", "Last On")
        else:
            self.columns = ("#", "Player Name", "Cups", "Gain", "Last On")

        if sort_by and donationboard:
            sort_columns = ("#", "Player Name", "donations", "received", "ratio", "last_online ASC, player_name")
            self.selected_index = [1, sort_columns.index('donations' if sort_by == 'donation' else sort_by)]
        elif sort_by:
            sort_columns = ("#", "Player Name", "trophies", "gain", "last_online ASC, player_name")
            self.selected_index = [1, sort_columns.index(sort_by.replace('donations', 'trophies'))]
        else:
            self.selected_index = []

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
}
"""
            width = "width: 100%;"

        self.html += """
<!DOCTYPE html>
<html>
<head>
<style>
""" + body + """
img {
  position: fixed;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  z-index:-1;
  opacity:0.9;
}
table {
  font-family: Helvetica, Verdana,courier,arial,helvetica;
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
  background-color: #ace;
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
</style>
        """

    def add_body(self):
        self.html += '<body>'

    def add_title(self):
        self.html += f"<header>{self.title}</header>"

    def add_image(self):
        self.html += f'<img src="{self.image}" alt="Test"></img>'

    def add_table(self, players):
        to_add = "<table>"

        to_add += "<tr>" + "".join(
            f"<th{' class=selected' if i in self.selected_index else ''}>{column}</th>"
            for i, column in enumerate(self.columns)
        ) + "</tr>"

        for player in players:
            to_add += "<tr>" + "".join(
                f"<td{' class=selected' if i in self.selected_index else ''}>{cell}</td>"
                for i, cell in enumerate(player)
            ) + "</tr>"

        to_add += "</table>"
        self.html += to_add

    def add_footer(self):
        if self.footer:
            self.html += f'<h6 class="footer">{self.footer}</h6>'

    def end_html(self):
        self.html += "</body></html>"

    def parse_players(self):
        if self.donationboard:
            self.players = [(str(i) + ".", p['player_name'], p['donations'], p['received'], round(p['donations'] / (p['received'] or 1), 2),
                            self.get_readable(p['last_online'])) for i, p in enumerate(self.players, start=self.offset)]
        else:
            self.players = [
                (str(i) + ".", p['player_name'], p['trophies'], p['gain'], self.get_readable(p['last_online']))
                for i, p in enumerate(self.players, start=self.offset)
            ]

    async def make(self):
        s = time.perf_counter()
        self.parse_players()
        self.add_style()
        self.add_body()
        self.add_title()
        self.add_image()
        if len(self.players) >= 30:
            self.add_table(self.players[:int(len(self.players)/2)])
            self.add_table(self.players[int(len(self.players)/2):])
        else:
            self.add_table(self.players)

        self.add_footer()
        self.end_html()
        log.debug((time.perf_counter() - s)*1000)

        s = time.perf_counter()
        proc = await asyncio.create_subprocess_shell(
            "wkhtmltoimage - -", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        log.debug((time.perf_counter() - s)*1000)
        s = time.perf_counter()
        stdout, stderr = await proc.communicate(input=self.html.encode('utf-8'))
        log.debug((time.perf_counter() - s)*1000)
        b = io.BytesIO(stdout)
        b.seek(0)
        return b


class SyncBoards:
    def __init__(self, bot):
        self.bot = bot

        self.season_id = 16

        self.last_updated_channels = {}
        self.season_meta = {}

        self.webhooks = None
        self.session = aiohttp.ClientSession()
        bot.loop.create_task(self.on_init())
        self.update_board_loops.start()

    async def on_init(self):
        self.webhooks = [
            discord.Webhook.partial(
                payload['id'], payload['token'], adapter=discord.AsyncWebhookAdapter(session=self.session)
            ) for payload in await self.bot.http.guild_webhooks(691779140059267084)
        ]
        self.webhooks = itertools.cycle(self.webhooks)

    async def get_season_meta(self, season_id):
        try:
            return self.season_meta[season_id]
        except KeyError:
            fetch = await pool.fetchrow("SELECT start, finish FROM seasons WHERE id = $1", season_id)
            season_start, season_finish = fetch[0].strftime('%d-%b-%Y'), fetch[1].strftime('%d-%b-%Y')
            self.season_meta[season_id] = (season_start, season_finish)
            return (season_start, season_finish)

    @tasks.loop(seconds=5.0)
    async def update_board_loops(self):
        if not self.webhooks:
            return

        fetch = await pool.fetch("UPDATE boards SET need_to_update=False WHERE need_to_update=True AND toggle=True RETURNING *")

        for n in fetch:
            try:
                config = BoardConfig(bot=self.bot, record=n)
                await self.update_board(config)
                self.last_updated_channels[n['channel_id']] = datetime.utcnow()
            except:
                log.exception(f"old board failed...\nChannel ID: {n['channel_id']}")

    async def set_new_message(self, config):
        try:
            message = await self.bot.http.send_message(config.channel_id, content="Placeholder.... do not delete me!")
        except (discord.Forbidden, discord.NotFound):
            await pool.execute("UPDATE boards SET toggle = FALSE WHERE channel_id = $1", config.channel_id)
            return

        for emoji in (REFRESH_EMOJI, LEFT_EMOJI, RIGHT_EMOJI, PERCENTAGE_EMOJI if config.type == 'donation' else GAIN_EMOJI, LAST_ONLINE_EMOJI, HISTORICAL_EMOJI):
            await self.bot.http.add_reaction(message['channel_id'], message['message_id'], str(emoji))

        await pool.execute("UPDATE boards SET message_id = $1 WHERE channel_id = $2 AND type = $3", int(message['message_id']), config.channel_id, config.type)

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

    async def update_board(self, config, update_global=False):
        if config.channel_id == GLOBAL_BOARDS_CHANNEL_ID and not update_global:
            return

        donationboard = config.type == 'donation'
        start = time.perf_counter()

        season_id = config.season_id or self.season_id
        offset = 0
        for i in range(1, config.page):
            offset += self.get_next_per_page(i, config.per_page)

        if config.channel_id == GLOBAL_BOARDS_CHANNEL_ID:
            query = f"""SELECT DISTINCT player_name,
                                        donations,
                                        received,
                                        trophies,
                                        now() - last_updated AS "last_online",
                                        donations / NULLIF(received, 0) AS "ratio",
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
            fetch = await pool.fetch(
                query,
                season_id,
                self.get_next_per_page(config.page, config.per_page),
                offset
            )
        else:
            query = f"""SELECT DISTINCT player_name,
                                        donations,
                                        received,
                                        trophies,
                                        now() - last_updated AS "last_online",
                                        donations / NULLIF(received, 0) AS "ratio",
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
            fetch = await pool.fetch(
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
        table = HTMLImages(
            players=fetch,
            title=config.title,
            image=config.icon_url,
            sort_by=config.sort_by,
            footer=f"Season: {season_start} - {season_finish}.",
            offset=offset,
            donationboard=donationboard
        )
        render = await table.make()
        s2 = time.perf_counter() - s1

        perf_log = f"Perf: {(time.perf_counter() - start) * 1000}ms\n" \
                   f"Build Image Perf: {s2 * 1000}ms\n" \
                   f"Channel: {config.channel_id}\n" \
                   f"Guild: {config.guild_id}"

        log.info(perf_log)
        logged_board_message = await next(self.webhooks).send(
            perf_log, file=discord.File(render, f'{config.type}board.png'), wait=True
        )

        try:
            await self.bot.http.edit_message(config.channel_id, config.message_id, content=logged_board_message.attachments[0].url, embed=None)
        except discord.NotFound:
            await self.set_new_message(config)


stateless_bot = discord.Client()
loop.run_until_complete(stateless_bot.login(creds.bot_token))
SyncBoards(stateless_bot)
loop.run_forever()
