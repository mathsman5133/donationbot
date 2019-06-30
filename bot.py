import os
import sys
import asyncio
import datetime
import coc
import discord
import aiohttp
import traceback
import creds

from discord.ext import commands
from cogs.utils import context
from cogs.utils.db import Table
import logging

logging.basicConfig(level=logging.INFO)

log = logging.getLogger(__name__)

coc_client = coc.login(creds.email, creds.password, client=coc.EventsClient,
                       key_names='test', throttle_limit=40)

initial_extensions = ['cogs.guildsetup', 'cogs.donations', 'cogs.updatesv2', 'cogs.admin', 'cogs.info']


class DonationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or('+'), case_insensitive=True)
        self.colour = 0x36393E
        self.coc = coc_client
        self.client_id = creds.client_id
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.webhook = discord.Webhook.partial(id=creds.hook_id, token=creds.hook_token,
                                               adapter=discord.AsyncWebhookAdapter(session=self.session))
        self.uptime = datetime.datetime.utcnow()
        self.prefixes = {}
        coc_client.add_events(self.on_event_error)

        for e in initial_extensions:
            try:
                self.load_extension(e)  # load cogs
            except Exception as er:
                exc = ''.join(traceback.format_exception(type(er), er, er.__traceback__, chain=False))
                print(exc)
                print(f'Failed to load extension {e}: {er}.', file=sys.stderr)

    async def on_message(self, message):
        if message.author.bot:
            return  # ignore bot messages

        await self.process_commands(message)

    async def on_command(self, ctx):
        # make bot 'type' so impatient people know we have received the command, if it is a long computation
        await ctx.message.channel.trigger_typing()

    async def process_commands(self, message):
        # we have a couple attributes to add to context, lets add them now (easy db connection etc.)
        ctx = await self.get_context(message, cls=context.Context)

        if ctx.command is None:
            return  # if there's no command invoked return

        async with ctx.acquire():
            await self.invoke(ctx)  # invoke command with our database connection

    async def on_error(self, event_method, *args, **kwargs):
        e = discord.Embed(title='Discord Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event_method)
        e.description = f'```py\n{traceback.format_exc()}\n```'
        e.timestamp = datetime.datetime.utcnow()

        try:
            await self.webhook.send(embed=e)
        except:
            pass

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return

        error = error.original
        if isinstance(error, (discord.Forbidden, discord.NotFound)):
            return

        e = discord.Embed(title='Command Error', colour=0xcc3366)
        e.add_field(name='Name', value=ctx.command.qualified_name)
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        e.description = f'```py\n{exc}\n```'
        e.timestamp = datetime.datetime.utcnow()
        await self.webhook.send(embed=e)

    async def on_event_error(self, event_name, *args, **kwargs):
        e = discord.Embed(title='COC Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event_name)
        e.description = f'```py\n{traceback.format_exc()}\n```'
        e.timestamp = datetime.datetime.utcnow()

        try:
            await self.webhook.send(embed=e)
        except:
            pass

    async def on_ready(self):
        cog = self.get_cog('Updates')
        await cog.update_clan_tags()
        await self.change_presence(activity=discord.Game('+help for commands'))

    async def log_info(self, clan_or_guilds, message, colour):
        if isinstance(clan_or_guilds, coc.BasicClan):
            query = "SELECT guild_id FROM guilds WHERE clan_tag = $1 " \
                    "AND log_toggle = True"
            fetch_guilds = await self.pool.fetch(query, clan_or_guilds.tag)
            guilds = [self.get_guild(n[0]) for n in fetch_guilds if self.get_guild(n[0])]

        if isinstance(clan_or_guilds, discord.Guild):
            guilds = [clan_or_guilds]

        if not guilds:
            return

        query = f"SELECT DISTINCT log_channel_id FROM guilds WHERE guild_id IN ({', '.join(str(n.id) for n in guilds)})"
        fetch = await self.pool.fetch(query)
        channels = [self.get_channel(n[0]) for n in fetch if self.get_channel(n[0])]

        for c in channels:
            e = discord.Embed(colour=colour or self.colour)
            e.description = message
            await c.send(embed=e)

    async def get_guilds(self, clan_tag):
        query = "SELECT guild_id FROM clans WHERE clan_tag = $1"
        fetch = await self.pool.fetch(query, clan_tag)
        return [self.get_guild(n[0]) for n in fetch]

    async def get_clans(self, guild_id):
        query = "SELECT clan_tag FROM clans WHERE guild_id = $1"
        fetch = await self.pool.fetch(query, guild_id)
        return await self.coc.get_clans(n[0] for n in fetch).flatten()

    async def guild_settings(self, guild_id):
        query = "SELECT updates_ign, updates_don, updates_rec, updates_tag, updates_claimed_by FROM guilds " \
                "WHERE guild_id = $1"
        fetch = await self.pool.fetchrow(query, guild_id)
        return fetch[0], fetch[1], fetch[2], fetch[3], fetch[4]


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    try:
        # configure the database connection
        pool = loop.run_until_complete(Table.create_pool(creds.postgres, command_timeout=60))

        bot = DonationBot()
        bot.pool = pool  # add db as attribute
        bot.run(creds.bot_token)  # run bot

    except Exception as e:
        print(traceback.format_exc())
