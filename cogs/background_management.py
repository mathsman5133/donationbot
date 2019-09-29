import asyncio
import discord

from discord.ext import commands, tasks

from cogs.utils.db_objects import SlimEventConfig


class BackgroundManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def forceguild(self, ctx, guild_id: int):
        self.bot.dispatch('guild_join', self.bot.get_guild(guild_id))

    @tasks.loop()
    async def next_event_starts(self):
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          guild_id,
                          start - CURRENT_TIMESTAMP as "until_start"
                   FROM events
                   ORDER BY "until_start" DESC
                   LIMIT 1;
                """
        event = await self.bot.pool.fetchrow(query)
        if not event:
            return await asyncio.sleep(3600)

        slim_config = SlimEventConfig(event['id'], event['start'], event['finish'], event['event_name'])

        if event['until_start'].total_seconds() < 0:
            await self.on_event_start(slim_config, event['guild_id'], event['until_start'])

        await asyncio.sleep(event['until_start'].total_seconds())
        await self.on_event_start(slim_config, event['guild_id'], event['until_start'])

    @tasks.loop()
    async def next_event_starts(self):
        query = """SELECT id,
                          start,
                          finish,
                          event_name,
                          guild_id,
                          finish - CURRENT_TIMESTAMP as "until_finish"
                   FROM events
                   ORDER BY "until_start" DESC
                   LIMIT 1;
                """
        event = await self.bot.pool.fetchrow(query)
        if not event:
            return await asyncio.sleep(3600)

        slim_config = SlimEventConfig(event['id'], event['start'], event['finish'], event['event_name'])

        if event['until_start'].total_seconds() < 0:
            await self.on_event_start(slim_config, event['guild_id'], event['until_finish'])

        await asyncio.sleep(event['until_finish'].total_seconds())
        await self.on_event_start(slim_config, event['guild_id'], event['until_finish'])

    # async def on_event_start(self, event, guild_id, delta_ago):
    #     if in_event:
    #         event_query = """INSERT INTO eventplayers (
    #                                         player_tag,
    #                                         donations,
    #                                         received,
    #                                         trophies,
    #                                         event_id,
    #                                         start_friend_in_need,
    #                                         start_sharing_is_caring,
    #                                         start_attacks,
    #                                         start_defenses,
    #                                         start_best_trophies,
    #                                         start_update
    #                                         )
    #                         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, True)
    #                         ON CONFLICT (player_tag, event_id)
    #                         DO NOTHING
    #                     """
    #         await connection.execute(event_query,
    #                                  player.tag,
    #                                  player.donations,
    #                                  player.received,
    #                                  player.trophies,
    #                                  event_id,
    #                                  player.achievements_dict['Friend in Need'].value,
    #                                  player.achievements_dict['Sharing is caring'].value,
    #                                  player.attack_wins,
    #                                  player.defense_wins,
    #                                  player.best_trophies
    #                                  )
    #         season_id = await self.bot.seasonconfig.get_season_id()
    #         for n in clans:
    #             async for player in n.get_detailed_members:
    #                 await self.insert_player(ctx.db, player, season_id, True, event_id[0])
    #
    # async def on_event_finish(self, event, guild_id, delta_ago):
    #     pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53dda4, title='New Guild')  # green colour
        await self.send_guild_stats(e, guild)
        query = "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING"
        await self.bot.pool.execute(query, guild.id)
        fmt = '**Some handy hints:**\n' \
            f'• My prefix is `+`, or {self.bot.user.mention}\n' \
              '• All commands have super-detailed help commands; please use them!\n' \
              '• Usage: `+help command_name`\n\n' \
              'A few frequently used ones to get started:\n' \
              '• `+help addclan`\n' \
              '• `+help donationboard` and `+help donationboard create`\n' \
              '• `+help log` and `+help log create`\n\n' \
              '• There are lots of how-to\'s and other ' \
              'support on the [support server](https://discord.gg/ePt8y4V) if you get stuck.\n' \
            f'• Please share the bot with your friends! [Bot Invite]({self.bot.invite})\n' \
              '• Please support us on [Patreon](https://www.patreon.com/donationtracker)!\n' \
              '• Have a good day!'
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
