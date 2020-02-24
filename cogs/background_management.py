import asyncio
import datetime
import discord
import logging
import textwrap
import time

from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimEventConfig
from cogs.utils.formatters import readable_time
from cogs.utils.emoji_lookup import misc

log = logging.getLogger(__name__)


class BackgroundManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.next_event_starts.start()

        self.main_syncer.add_exception_type(Exception, BaseException)
        self.main_syncer.start()

        self.insert_new_players.add_exception_type(Exception, BaseException)
        self.insert_new_players.start()

        self.event_player_updater2.start()

    def cog_unload(self):
        self.next_event_starts.cancel()
        self.main_syncer.cancel()
        self.insert_new_players.cancel()
        self.event_player_updater2.cancel()

    @commands.command(hidden=True)
    @commands.is_owner()
    async def forceguild(self, ctx, guild_id: int):
        self.bot.dispatch('guild_join', self.bot.get_guild(guild_id))

    @tasks.loop()
    async def next_event_starts(self):
        await self.bot.wait_until_ready()
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          guild_id,
                          channel_id,
                          start - CURRENT_TIMESTAMP AS "until_start"
                   FROM events
                   WHERE start_report = False
                   ORDER BY "until_start" 
                   LIMIT 1;
                """
        event = await self.bot.pool.fetchrow(query)
        if not event:
            return await asyncio.sleep(3600)

        slim_config = SlimEventConfig(
            event['id'], event['start'], event['finish'], event['event_name'], event['channel_id'], event['guild_id']
        )

        if event['until_start'].total_seconds() < 0:
            await self.on_event_start(slim_config)

        await asyncio.sleep(event['until_start'].total_seconds())
        await self.on_event_start(slim_config)

        query = "UPDATE events SET start_report = True WHERE id = $1"
        await self.bot.pool.execute(query, event['id'])

    @tasks.loop()
    async def next_event_finish(self):
        await self.bot.wait_until_ready()
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          guild_id,
                          channel_id,
                          finish - CURRENT_TIMESTAMP AS "until_finish"
                   FROM events
                   ORDER BY "until_finish"
                   LIMIT 1;
                """
        event = await self.bot.pool.fetchrow(query)
        if not event:
            return await asyncio.sleep(3600)

        slim_config = SlimEventConfig(
            event['id'], event['start'], event['finish'], event['event_name'], event['channel_id'], event['guild_id']
        )
        self.bot.utils.board_config.invalidate(self.bot.utils, slim_config.channel_id)

        if event['until_start'].total_seconds() < 0:
            await self.on_event_finish(slim_config)

        await asyncio.sleep(event['until_finish'].total_seconds())
        await self.on_event_finish(slim_config)

    @tasks.loop(hours=1)
    async def event_player_updater(self):
        query = "SELECT DISTINCT player_tag FROM eventplayers WHERE live = True;"
        fetch = await self.bot.pool.fetch(query)

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
        async for player in self.bot.coc.get_players((n[0] for n in fetch), update_cache=False):
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
        await self.bot.pool.execute(query, to_insert)
        log.info(f'Loop for event updates finished. Took {(time.perf_counter() - start)*1000}ms')

    @commands.Cog.listener()
    async def on_event_register(self):
        self.next_event_starts.restart()
        self.next_event_finish.restart()

    @staticmethod
    async def insert_member(con, player, event_id):
        query = """INSERT INTO eventplayers (
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
                    DO NOTHING;
                """
        await con.execute(query,
                          player.tag,
                          player.trophies,
                          event_id,
                          player.achievements_dict['Friend in Need'].value,
                          player.achievements_dict['Sharing is caring'].value,
                          player.attack_wins,
                          player.defense_wins,
                          player.trophies,
                          player.best_trophies
                          )

    @staticmethod
    async def finalise_member(con, player, event_id):
        query = """UPDATE eventplayers 
                   SET end_friend_in_need = $1,
                       end_sharing_is_caring = $2,
                       end_attacks = $3,
                       end_defenses = $4,
                       end_best_trophies = $5,
                       live = False,
                       final_update = True
                   WHERE player_tag = $6
                   AND event_id = $7
                """
        await con.execute(query,
                          player.achievements_dict['Friend in Need'].value,
                          player.achievements_dict['Sharing is caring'].value,
                          player.attack_wins,
                          player.defense_wins,
                          player.best_trophies,
                          player.tag,
                          event_id
                          )

    @staticmethod
    async def safe_send(channel, msg):
        try:
            return await channel.send(msg)
        except (discord.HTTPException, discord.NotFound, AttributeError):
            log.error(f'Tried to send event info to {channel} but was rejected. Please inform them.')

    async def on_event_start(self, event):
        log.info(f'Starting {event.event_name} ({event.id}) '
                 f'in channel ID {event.channel_id}, for guild {event.guild_id}.')
        channel = self.bot.get_channel(event.channel_id)
        await self.safe_send(channel, ':tada: Event starting! I am adding members to the database...')

        clans = await self.bot.get_clans(event.guild_id, in_event=True)

        for n in clans:
            async for player in n.get_detailed_members():
                await self.insert_member(self.bot.pool, player, event.id)
        await self.safe_send(channel, 'All members have been added... '
                                      'configuring the donation and trophy boards to be in the event!')
        query = "UPDATE boards SET in_event = True WHERE guild_id = $1"
        await self.bot.pool.execute(query, event.guild_id)

        donationboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'donation')
        for config in donationboard_configs:
            await self.bot.donationboard.update_board(config.channel_id)
            await self.new_event_message(event, event.guild_id, config.channel_id, 'donation')

        trophyboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'trophy')
        for config in trophyboard_configs:
            await self.bot.donationboard.update_board(config.channel_id)
            await self.new_event_message(event, event.guild_id, config.channel_id, 'trophy')

        await self.safe_send(channel, f'Boards have been updated. Enjoy your event! '
                                      f'It ends in {readable_time((event.finish - datetime.datetime.utcnow()).total_seconds())}.')
        return True

    async def new_event_message(self, event, guild_id, channel_id, board_type):
        event_channel = self.bot.get_channel(event.channel_id)
        if not event_channel:
            log.error(f'Tried to update {board_type}board for event {event.event_name} '
                      f'({event.id}) but couldn\'t find the channel. '
                      f'Please let them know! Guild ID {guild_id}, Channel ID {channel_id}')
            return

        if board_type == 'donation':
            colour = discord.Colour.gold()
        else:
            colour = discord.Colour.purple()

        e = discord.Embed(colour=colour)

        e.set_author(name='Event in Progress!')

        fmt = f':name_badge:**Name:** {event.event_name}\n' \
            f':id:**ID:** {event.id}\n' \
            f"{misc['green_clock']}**Started (UTC):** {event.start:%Y-%m-%d %H:%M}\n" \
            f":alarm_clock:**Finishes (UTC):** {event.finish:%Y-%m-%d %H:%M}\n" \
            f"{misc['number']}**Updates Channel:**{event_channel.mention}\n\n" \
            f"The board will only show changes (donations, received, trophies etc.) " \
            f"that are made **during** the event times above."
        e.description = fmt

        query = "SELECT DISTINCT clan_tag, clan_name FROM clans " \
                "WHERE guild_id = $1 AND in_event=True ORDER BY clan_name;"
        fetch = await self.bot.pool.fetch(query, guild_id)

        e.add_field(name='Participating Clans',
                    value='\n'.join(f"{misc['online']}{n[1]} ({n[0]})" for n in fetch)
                    )
        board_channel = self.bot.get_channel(channel_id)
        e.set_footer(text='Event Ends').timestamp = event.finish
        try:
            msg = await board_channel.send(embed=e)
        except (AttributeError, discord.NotFound, discord.HTTPException):
            log.error(f'Tried to update {board_type}board for event {event.event_name} '
                      f'({event.id}) but couldn\'t find the channel. '
                      f'Please let them know! Guild ID {guild_id}, Channel ID {channel_id}')
            return

        query = f"UPDATE events SET {board_type}_msg = $1 WHERE id = $2"
        await self.bot.pool.execute(query, msg.id, event.id)

    async def on_event_finish(self, event):
        channel = self.bot.get_channel(event.channel_id)
        await self.safe_send(channel, ':tada: Aaaand thats it! The event has finished. I am crunching the numbers, '
                                      'working out who the champs and chumps are, and will get back to you shortly.')

        query = "SELECT player_tag FROM eventplayers WHERE event_id=$1 AND final_update=False"
        fetch = await self.bot.pool.fetch(query, event.id)

        async for player in self.bot.coc.get_players((n[0] for n in fetch)):
            await self.finalise_member(self.bot.pool, player, event.id)

        await self.safe_send(channel, 'All members have been finalised, updating your boards!')
        query = "UPDATE boards SET in_event = False WHERE guild_id = $1;"
        await self.bot.pool.execute(query, event.guild_id)

        donationboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'donation')
        for config in donationboard_configs:
            await self.bot.donationboard.update_board(config.channel_id)
            await self.remove_event_msg(event.id, config.channel, 'donation')

        trophyboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'trophy')
        for config in trophyboard_configs:
            await self.bot.donationboard.update_board(config.channel_id)
            await self.remove_event_msg(event.id, config.channel, 'trophy')

        # todo: crunch some numbers.
        await self.safe_send(channel, f'Boards have been updated. I will cruch some more numbers and '
                                      f'get back to you later when the owner has fixed this, lol.')

    async def remove_event_msg(self, event_id, channel, board_type):
        query = f"SELECT {board_type}_msg FROM events WHERE id=$1"
        fetch = await self.bot.pool.fetchrow(query, event_id)
        if not fetch:
            return
        msg = await self.bot.utils.get_message(channel, fetch[0])
        if msg:
            return await msg.delete()

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

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53dda4, title='New Guild')  # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING"
        await self.bot.pool.execute(query, guild.id)
        e = self.bot.get_cog('\u200bInfo').welcome_message

        if guild.system_channel:
            try:
                await guild.system_channel.send(embed=e)
                return
            except (discord.Forbidden, discord.HTTPException):
                pass
        for c in guild.channels:
            if not isinstance(c, discord.TextChannel):
                continue
            if c.permissions_for(c.guild.get_member(self.bot.user.id)).send_messages:
                try:
                    await c.send(embed=e)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        e = discord.Embed(colour=0xdd5f53, title='Left Guild')  # red colour
        await self.send_guild_stats(e, guild)
        query = """UPDATE logs 
                   SET toggle = False 
                   WHERE guild_id = $1;
                """
        query2 = """UPDATE boards 
                    SET toggle = False
                    WHERE guild_id = $1;
                """
        await self.bot.pool.execute(query, guild.id)
        await self.bot.pool.execute(query2, guild.id)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        self.bot.command_stats[command] += 1
        message = ctx.message
        if ctx.guild is None:
            guild_id = None
        else:
            guild_id = ctx.guild.id

        query = """INSERT INTO commands (guild_id, channel_id, author_id, used, prefix, command)
                               VALUES ($1, $2, $3, $4, $5, $6)
                """

        e = discord.Embed(title='Command', colour=discord.Colour.green())
        e.add_field(name='Name', value=ctx.command.qualified_name)
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)
        e.add_field(name='Content', value=textwrap.shorten(ctx.message.content, width=512))

        e.timestamp = datetime.datetime.utcnow()
        if not await self.bot.is_owner(ctx.author):
            await self.bot.command_webhook.send(embed=e)

        await self.bot.pool.execute(query, guild_id, ctx.channel.id, ctx.author.id,
                                    message.created_at, ctx.prefix, command
                                    )

    @commands.Cog.listener()
    async def on_clan_claim(self, ctx, clan):
        e = discord.Embed(colour=discord.Colour.blue(), title='Clan Claimed')
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.utils.update_clan_tags()
        # await self.bot.donationlogs.sync_temp_event_tasks()
        # await self.bot.trophylogs.sync_temp_event_tasks()

    @commands.Cog.listener()
    async def on_clan_unclaim(self, ctx, clan):
        e = discord.Embed(colour=discord.Colour.dark_blue(), title='Clan Unclaimed')
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.utils.update_clan_tags()
        # await self.bot.donationlogs.sync_temp_event_tasks()
        # await self.bot.trophylogs.sync_temp_event_tasks()

    async def send_guild_stats(self, e, guild):
        e.add_field(name='Name', value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Owner', value=f'{guild.owner} (ID: {guild.owner.id})')

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count
        online = sum(m.status is discord.Status.online for m in guild.members)
        e.add_field(name='Members', value=str(total))
        e.add_field(name='Bots', value=f'{bots} ({bots / total:.2%})')
        e.add_field(name='Online', value=f'{online} ({online / total:.2%})')

        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)

        if guild.me:
            e.timestamp = guild.me.joined_at

        await self.bot.join_log_webhook.send(embed=e)

    async def send_claim_clan_stats(self, e, clan, guild):
        e.add_field(name='Name', value=clan.name)
        e.add_field(name='Tag', value=clan.tag)

        total = len(clan.members)
        e.add_field(name='Member Count', value=str(total))

        if clan.badge:
            e.set_thumbnail(url=clan.badge.url)

        query = """SELECT clan_tag, clan_name
                   FROM clans WHERE guild_id = $1
                   GROUP BY clan_tag, clan_name
                """
        clan_info = await self.bot.pool.fetch(query, guild.id)
        if clan_info:
            e.add_field(name=f"Clans Claimed: {len(clan_info)}",
                        value='\n'.join(f"{n['clan_name']} ({n['clan_tag']})" for n in clan_info),
                        inline=False)

        e.add_field(name='Guild Name', value=guild.name)
        e.add_field(name='Guild ID', value=guild.id)
        e.add_field(name='Guild Owner', value=f'{guild.owner} (ID: {guild.owner.id})')

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count
        online = sum(m.status is discord.Status.online for m in guild.members)
        e.add_field(name='Guild Members', value=str(total))
        e.add_field(name='Guild Bots', value=f'{bots} ({bots / total:.2%})')
        e.add_field(name='Guild Online', value=f'{online} ({online / total:.2%})')

        if guild.me:
            e.set_footer(text='Bot Added').timestamp = guild.me.joined_at

        await self.bot.join_log_webhook.send(embed=e)

    @tasks.loop(seconds=60.0)
    async def main_syncer(self):
        try:
            await self.sync_clans()
        except Exception as e:
            log.exception(e)

    async def sync_clans(self):
        query = "SELECT DISTINCT(clan_tag) FROM clans"
        fetch = await self.bot.pool.fetch(query)

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
                DO NOTHING
                """

        query = """
            UPDATE players
            SET player_name     = x.player_name,
                clan_tag        = x.clan_tag,
                prev_donations  = x.prev_donations,
                prev_received   = x.prev_received,
                trophies        = x.trophies,
                league_id       = x.league_id,
                versus_trophies = x.versus_trophies,
                exp_level       = x.exp_level
            FROM(
            SELECT x.player_tag,
                   x.player_name,
                   x.clan_tag,
                   x.prev_donations,
                   x.prev_received,
                   x.trophies,
                   x.league_id,
                   x.versus_trophies,
                   x.exp_level
            FROM jsonb_to_recordset($1::jsonb)
            AS x(
                player_tag TEXT,
                player_name TEXT,
                clan_tag TEXT,
                prev_donations INTEGER,
                prev_received INTEGER, 
                trophies INTEGER,
                league_id INTEGER,
                versus_trophies INTEGER,
                exp_level INTEGER
            )
            ) AS x
            WHERE players.player_tag = x.player_tag AND players.season_id = $2
            """

        players = []

        async for clan in self.bot.coc.get_clans((n[0] for n in fetch), cache=False, update_cache=False):
            players.extend(
                {
                    "player_tag": n.tag,
                    "player_name": n.name,
                    "clan_tag": n.clan and n.clan.tag,
                    "prev_donations": n.donations,
                    "prev_received": n.received,
                    "trophies": n.trophies,
                    "league_id": n.league.id,
                    "versus_trophies": n.versus_trophies,
                    "exp_level": n.exp_level
                }
                for n in clan.itermembers
            )

        q = await self.bot.pool.execute(query, players, await self.bot.seasonconfig.get_season_id())
        log.info(q)

    @tasks.loop(seconds=60.0)
    async def insert_new_players(self):
        query = "SELECT player_tag FROM players WHERE fresh_update = TRUE AND season_id = $1"
        fetch = await self.bot.pool.fetch(query, await self.bot.seasonconfig.get_season_id())

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
            donations    = x.fin + x.sic - players.start_friend_in_need - players.start_sharing_is_caring,
            ignore       = TRUE,
            
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
                player_tag TEXT,
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

        async for player in self.bot.coc.get_players((n[0] for n in fetch), cache=False, update_cache=False):
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
                "sic": player.achievements_dict["Sharing is caring"].value
            })
        q = await self.bot.pool.execute(query, players, await self.bot.seasonconfig.get_season_id())
        log.info(q)


    @tasks.loop(hours=1)
    async def event_player_updater2(self):
        query = "SELECT DISTINCT player_tag FROM eventplayers WHERE live = True;"
        fetch = await self.bot.pool.fetch(query)

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
        async for player in self.bot.coc.get_players((n[0] for n in fetch), update_cache=False):
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
        await self.bot.pool.execute(query, to_insert)
        log.info(f'Loop for event updates finished. Took {(time.perf_counter() - start) * 1000}ms')


def setup(bot):
    bot.add_cog(BackgroundManagement(bot))
