import asyncio
import datetime
import discord
import logging
import textwrap

from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimEventConfig
from cogs.utils.formatters import readable_time
from cogs.utils.emoji_lookup import misc

log = logging.getLogger(__name__)


class BackgroundManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.next_event_starts.start()

    def cog_unload(self):
        self.next_event_starts.cancel()

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

        slim_config = SlimEventConfig(event['id'], event['start'], event['finish'], event['event_name'], event['channel_id'])

        if event['until_start'].total_seconds() < 0:
            await self.on_event_start(slim_config, event['guild_id'])

        await asyncio.sleep(event['until_start'].total_seconds())
        await self.on_event_start(slim_config, event['guild_id'])

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

        slim_config = SlimEventConfig(event['id'], event['start'], event['finish'], event['event_name'], event['channel_id'])

        if event['until_start'].total_seconds() < 0:
            await self.on_event_start(slim_config, event['guild_id'])

        await asyncio.sleep(event['until_finish'].total_seconds())
        await self.on_event_start(slim_config, event['guild_id'])

    @commands.Cog.listener()
    async def on_event_register(self):
        self.next_event_starts.cancel()
        self.next_event_starts.start()

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

    async def on_event_start(self, event, guild_id):
        log.info(f'Starting {event.event_name} ({event.id}) '
                 f'in channel ID {event.channel_id}, for guild {guild_id}.')
        channel = self.bot.get_channel(event.channel_id)
        await self.safe_send(channel, ':tada: Event starting! I am adding members to the database...')

        clans = await self.bot.get_clans(guild_id, in_event=True)

        for n in clans:
            async for player in n.get_detailed_members():
                await self.insert_member(self.bot.pool, player, event.id)
        await self.safe_send(channel, 'All members have been added... '
                                      'configuring the donation and trophy boards to be in the event!')
        query = "UPDATE boards SET in_event = True WHERE guild_id = $1"
        await self.bot.pool.execute(query, guild_id)

        donationboard_config = await self.bot.utils.get_board_config(guild_id, 'donation')
        await self.bot.donationboard.update_board(donationboard_config.channel_id)
        await self.new_event_message(event, guild_id, donationboard_config.channel_id, 'donation')

        trophyboard_config = await self.bot.utils.get_board_config(guild_id, 'trophy')
        await self.bot.donationboard.update_board(trophyboard_config.channel_id)
        await self.new_event_message(event, guild_id, trophyboard_config.channel_id, 'trophy')

        await self.safe_send(channel, f'Boards have been updated. Enjoy your event! '
                                      f'It ends in {readable_time((event.finish - datetime.datetime.utcnow()).total_seconds())}.')
        return True

    async def new_event_message(self, event, guild_id, channel_id, board_type):
        event_channel = self.bot.get_channel(event.channel_id)
        if board_type == 'donation':
            colour = discord.Colour.gold()
        else:
            colour = discord.Colour.purple()

        e = discord.Embed(colour=colour)

        e.set_author(name='Event in Progress!')

        fmt = f':name_badge:**Name:** {event.event_name}\n' \
            f':id:**ID:** {event.id}\n' \
            f"{misc['green_clock']}**Started (UTC):**{event.start:%Y-%m-%d %H:%M:%S%z}\n" \
            f":alarm_clock:**Finishes (UTC):**{event.finish:%Y-%m-%d %H:%M:%S%z}\n" \
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

    async def on_event_finish(self, event, guild_id):
        channel = self.bot.get_channel(event.channel_id)
        await self.safe_send(channel, ':tada: Aaaand thats it! The event has finished. I am crunching the numbers, '
                                      'working out who the champs and chumps are, and will get back to you shortly.')

        clans = await self.bot.get_clans(guild_id, in_event=True)

        for n in clans:
            async for player in n.get_detailed_members:
                await self.finalise_member(self.bot.pool, player, event.id)
        await self.safe_send(channel, 'All members have been finalised, updating your boards!')
        query = "UPDATE boards SET in_event = False WHERE guild_id = $1;"
        await self.bot.pool.execute(query, guild_id)

        donationboard_config = await self.bot.utils.get_board_config(guild_id, 'donation')
        await self.bot.donationboard.update_board(donationboard_config.channel_id)
        await self.remove_event_msg(event.id, donationboard_config.channel, 'donation')

        trophyboard_config = await self.bot.utils.get_board_config(guild_id, 'trophy')
        await self.bot.donationboard.update_board(trophyboard_config.channel_id)
        await self.remove_event_msg(event.id, trophyboard_config.channel, 'trophy')

        # todo: crunch some numbers.
        await self.safe_send(channel, f'Boards have been updated. I will cruch some more numbers and '
                                      f'get back to you later when the owner has fixed this, lol.')

    async def remove_event_msg(self, event_id, channel, board_type):
        query = f"SELECT {board_type}_msg FROM events WHERE id=$1"
        fetch = await self.bot.pool.fetch(query, event_id)
        if not fetch:
            return
        msg = await self.bot.utils.get_message(channel, fetch[0])
        if msg:
            return await msg.delete()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53dda4, title='New Guild')  # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING"
        await self.bot.pool.execute(query, guild.id)
        fmt = self.bot.get_cog('Info').welcome_message
        e = discord.Embed(colour=self.bot.colour,
                          description=fmt)
        e.set_author(name='Hello! I\'m the Donation Tracker!',
                     icon_url=self.bot.user.avatar_url
                     )

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
        query = """WITH t AS (
                        UPDATE logs 
                        SET toggle = False 
                        WHERE guild_id = $1
                        )
                   UPDATE boards 
                   SET toggle = False
                   WHERE guild_id = $1
                """
        await self.bot.pool.execute(query, guild.id)

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
        await self.bot.donationlogs.sync_temp_event_tasks()
        await self.bot.trophylogs.sync_temp_event_tasks()

    @commands.Cog.listener()
    async def on_clan_unclaim(self, ctx, clan):
        e = discord.Embed(colour=discord.Colour.dark_blue(), title='Clan Unclaimed')
        await self.send_claim_clan_stats(e, clan, ctx.guild)
        await self.bot.utils.update_clan_tags()
        await self.bot.donationlogs.sync_temp_event_tasks()
        await self.bot.trophylogs.sync_temp_event_tasks()

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


def setup(bot):
    bot.add_cog(BackgroundManagement(bot))
