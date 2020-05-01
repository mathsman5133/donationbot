import asyncio
import datetime
import discord
import logging
import textwrap
import itertools
import time

import coc
import pytz

from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimEventConfig
from cogs.utils.formatters import readable_time, LineWrapper
from cogs.utils.emoji_lookup import misc
from cogs.utils.donationtrophylogs import get_events_fmt

log = logging.getLogger(__name__)


def seconds_until_5am():
    now = datetime.datetime.now(pytz.utc)

    if now.hour < 4:
        five_am = now.replace(hour=4, minute=0, second=0, microsecond=0)
    else:
        tomorrow = now + datetime.timedelta(days=1)
        five_am = tomorrow.replace(hour=4, minute=0, second=0, microsecond=0)

    return (five_am - now).total_seconds()


class BackgroundManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.next_event_starts.start()
        self.daily_history_updater.start()
        asyncio.ensure_future(self.sync_temp_event_tasks())
        #self.sync_activity_stats.start()
        self._log_tasks = {}
        # self.event_player_updater.start()

    def cog_unload(self):
        self.next_event_starts.cancel()
        self.daily_history_updater.cancel()
        for k, v in self._log_tasks:
            v.cancel()
        #self.sync_activity_stats.cancel()
        # self.event_player_updater.cancel()

    async def bot_check(self, ctx):
        if ctx.guild.id in ctx.bot.locked_guilds:
            await ctx.send(
                "Your server is locked. Please be patient while your activity data is synced. "
                "If you believe this has been issued in error, "
                "please join the support server: https://discord.gg/ePt8y4V"
            )
            return False
        return True

    async def log_message_send(self, message_id, channel_id, guild_id, type_):
        # type can be: command, donationboard, trophyboard, donationlog, trophylog
        query = "INSERT INTO message_sends (message_id, channel_id, guild_id, type) VALUES ($1, $2, $3, $4)"
        await self.bot.pool.execute(query, message_id, channel_id, guild_id, type_)

    @tasks.loop()
    async def sync_activity_stats(self):
        await asyncio.sleep(seconds_until_5am())
        query = """INSERT INTO activity_query (
                       player_tag, 
                       clan_tag, 
                       hour_time, 
                       counter, 
                       hour_digit
                    ) 
                    SELECT player_tag, clan_tag, timer, num_events, hour 
                    FROM get_activity_to_sync()
                    ON CONFLICT DO NOTHING
                """
        await self.bot.pool.execute(query)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def forceguild(self, ctx, guild_id: int):
        self.bot.dispatch('guild_join', self.bot.get_guild(guild_id))

    @tasks.loop()
    async def daily_history_updater(self):
        await asyncio.sleep(seconds_until_5am())
        query = """INSERT INTO players_history (
                                    player_tag, 
                                    donations, 
                                    received, 
                                    user_id, 
                                    friend_in_need, 
                                    sharing_is_caring, 
                                    trophies, 
                                    best_trophies, 
                                    last_updated, 
                                    league_id, 
                                    versus_trophies, 
                                    clan_tag, 
                                    level, 
                                    player_name, 
                                    attacks, 
                                    defenses, 
                                    versus_attacks, 
                                    exp_level, 
                                    games_champion, 
                                    well_seasoned
                                )             
                   SELECT player_tag,
                          donations,
                          received,
                          user_id,
                          end_friend_in_need,
                          end_sharing_is_caring,
                          trophies,
                          end_best_trophies,
                          last_updated,
                          league_id,
                          versus_trophies,
                          clan_tag,
                          level,
                          player_name,
                          attacks,
                          defenses,
                          versus_attacks,
                          exp_level,
                          games_champion,
                          well_seasoned
                   FROM players
                   WHERE players.season_id = $1
        """
        await self.bot.pool.execute(query, await self.bot.seasonconfig.get_season_id())

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
            await self.bot.donationboard.update_board(config.channel_id, config.type)
            await self.new_event_message(event, event.guild_id, config.channel_id, 'donation')

        trophyboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'trophy')
        for config in trophyboard_configs:
            await self.bot.donationboard.update_board(config.channel_id, config.type)
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
            await self.bot.donationboard.update_board(config.channel_id, config.type)
            await self.remove_event_msg(event.id, config.channel, 'donation')

        trophyboard_configs = await self.bot.utils.get_board_configs(event.guild_id, 'trophy')
        for config in trophyboard_configs:
            await self.bot.donationboard.update_board(config.channel_id, config.type)
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
        await self.log_message_send(ctx.message.id, ctx.channel.id, ctx.guild.id, 'command')
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
        await self.bot.background.sync_temp_event_tasks()

    @commands.Cog.listener()
    async def on_clan_unclaim(self, ctx, clan):
        e = discord.Embed(colour=discord.Colour.dark_blue(), title='Clan Unclaimed')
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.utils.update_clan_tags()
        await self.bot.background.sync_temp_event_tasks()

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

    async def sync_temp_event_tasks(self):
        query = """SELECT channel_id, type 
                   FROM logs 
                   WHERE toggle = True 
                   AND "interval" > make_interval()
                """
        fetch = await self.bot.pool.fetch(query)
        for n in fetch:
            channel_id, type_ = n[0], n[1]
            key = (channel_id, type_)
            log.debug(f'Syncing task for Channel ID {key}')
            task = self._log_tasks.get(key)
            if not task:
                log.debug(f'Task has not been created. Creating it. Channel ID: {key}')
                self._log_tasks[key] = self.bot.loop.create_task(self.create_temp_event_task(channel_id, type_))
                continue
            elif task.done():
                log.info(task.get_stack())
                log.info(f'Task has already been completed, recreating it. Channel ID: {key}')
                self._log_tasks[key] = self.bot.loop.create_task(self.create_temp_event_task(channel_id, type_))
                continue
            else:
                log.debug(f'Task has already been sucessfully registered for Channel ID {channel_id}')

        to_cancel = [n for n in self._log_tasks.keys() if n not in set((n[0], n[1]) for n in fetch)]
        for n in to_cancel:
            log.debug(f'Channel events have been removed from DB. Destroying task. Channel ID: {n}')
            task = self._log_tasks.pop(n)
            task.cancel()

        log.info(f'Successfully synced {len(fetch)} channel tasks.')

    async def create_temp_event_task(self, channel_id, type_):
        try:
            while not self.bot.is_closed():
                config = await self.bot.utils.log_config(channel_id, type_)
                if not config:
                    log.critical(
                        f'Requested a task creation for channel id {channel_id} type={type_} but config was not found.'
                    )
                    return

                await asyncio.sleep(config.seconds)
                config = await self.bot.utils.log_config(channel_id, type_)

                if type_ == "donation" and config.detailed:
                    query = "DELETE FROM detailedtempevents WHERE channel_id = $1 RETURNING clan_tag, exact, combo, unknown"
                    fetch = await self.bot.pool.fetch(query, channel_id)

                    if not fetch:
                        continue

                    embeds = []

                    for clan_tag, events in itertools.groupby(sorted(fetch, key=lambda x: x['clan_tag']),
                                                              key=lambda x: x['clan_tag']):
                        events = list(events)

                        events_fmt = {
                            "exact": [],
                            "combo": [],
                            "unknown": []
                        }
                        for n in events:
                            events_fmt["exact"].extend(n['exact'].split('\n'))
                            events_fmt["combo"].extend(n['combo'].split('\n'))
                            events_fmt["unknown"].extend(n['unknown'].split('\n'))

                        p = LineWrapper()
                        p.add_lines(get_events_fmt(events_fmt))

                        try:
                            clan = await self.bot.coc.get_clan(clan_tag, cache=True)
                        except coc.NotFound:
                            log.exception(f'{clan_tag} not found')
                            continue

                        hex_ = bytes.hex(str.encode(clan.tag))[:20]

                        for page in p.pages:
                            e = discord.Embed(
                                colour=int(int(''.join(filter(lambda x: x.isdigit(), hex_))) ** 0.3),
                                description=page
                            )
                            e.set_author(name=f"{clan.name} ({clan.tag})", icon_url=clan.badge.url)
                            e.set_footer(text="Reported").timestamp = datetime.datetime.utcnow()
                            embeds.append(e)

                    for n in embeds:
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel_id, embed=n))

                else:
                    query = "DELETE FROM tempevents WHERE channel_id = $1 AND type = $2 RETURNING fmt"
                    fetch = await self.bot.pool.fetch(query, channel_id, type_)
                    p = LineWrapper()

                    for n in fetch:
                        p.add_lines(n[0].split("\n"))
                    for page in p.pages:
                        asyncio.ensure_future(self.bot.utils.safe_send(config.channel_id, page))

        except asyncio.CancelledError:
            raise
        except:
            log.exception(f'Exception encountered while running task for {channel_id} {type_}')
            self._log_tasks[(channel_id, type_)].cancel()
            self._log_tasks[(channel_id, type_)] = self.bot.loop.create_task(self.create_temp_event_task(channel_id, type_))


def setup(bot):
    bot.add_cog(BackgroundManagement(bot))
