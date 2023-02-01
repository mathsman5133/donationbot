import asyncio
import datetime
import coc
import discord
import aiohttp
import traceback
import creds
import sqlite3
import sys
import itertools
import logging
import json

import asyncpg
import sentry_sdk

from coc.ext import discordlinks
from discord.ext import commands

from botlog import setup_logging, add_hooks
from cogs.utils import context
from cogs.utils.error_handler import error_handler, discord_event_error

sentry_sdk.init(creds.SENTRY_KEY)
initial_extensions = [
    'cogs.admin',
    'cogs.aliases',
    'cogs.auto_claim',
    'cogs.botutils',
    'cogs.stats',
    'cogs.deprecated',
    'cogs.info',
    'cogs.reset_season',
    'cogs.activity',
    'cogs.remove',
    'cogs.add',
    'cogs.edit'
]
beta = "beta" in sys.argv

if creds.live and not beta:
    initial_extensions.extend(
        (
            'cogs.background_management',
            'cogs.boards',
        )
    )
    command_prefix = None
    key_names = 'test'
elif beta:
    command_prefix = '//'
    key_names = 'test'
    creds.bot_token = creds.beta_bot_token
else:
    command_prefix = '//'
    key_names = 'windows'


description = "A simple discord bot to track donations of clan families in clash of clans."
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.guild_reactions = True
intents.members = True
intents.emojis = True


log = logging.getLogger()


async def get_pref(bot, message):
    if command_prefix:
        return command_prefix

    if not message.guild:
        # message is a DM
        return "+"

    prefix = bot.prefixes.get(message.guild.id, "+")

    return commands.when_mentioned_or(prefix)(bot, message)


async def setup_db():
    def _encode_jsonb(value):
        return json.dumps(value)

    def _decode_jsonb(value):
        return json.loads(value)

    async def init(con):
        await con.set_type_codec('jsonb', schema='pg_catalog', encoder=_encode_jsonb, decoder=_decode_jsonb, format='text')
    return await asyncpg.create_pool(creds.postgres, init=init)


class DonationBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(command_prefix=get_pref, case_insensitive=True,
                         description=description, pm_help=None, help_attrs=dict(hidden=True),
                         intents=intents, chunk_guilds_at_startup=False, allowed_mentions=discord.AllowedMentions.none())

        self.prefixes = dict()

        self.colour = discord.Colour.blurple()

        self.client_id = creds.client_id
        self.dbl_token = creds.dbl_token
        self.owner_ids = {230214242618441728, 251150854571163648}  # maths, tuba
        self.locked_guilds = set()
        self.session = aiohttp.ClientSession()

        add_hooks(self)
        self.before_invoke(self.before_command_invoke)
        self.after_invoke(self.after_command_invoke)

        self.uptime = datetime.datetime.utcnow()

        self.sqlite = sqlite3.connect("errors.sqlite")

        self.fake_clan_guilds = {}

    async def setup_hook(self):
        setup_logging(bot)

        coc_client = coc.EventsClient(
            key_names=key_names,
            throttle_limit=30,
            key_count=1,
            key_scopes=creds.scopes,
            throttler=coc.BatchThrottler,
        )

        await coc_client.login(creds.email, creds.password)
        self.coc = coc_client
        self.pool = await setup_db()

        self.links = await discordlinks.login(creds.links_username, creds.links_password)

        for e in initial_extensions:
            try:
                await self.load_extension(e)  # load cogs
            except Exception:
                traceback.print_exc()

    @property
    def donationboard(self):
        return self.get_cog('DonationBoard')

    @property
    def seasonconfig(self):
        return self.get_cog('SeasonConfig')

    @property
    def utils(self):
        return self.get_cog('Utils')

    @property
    def background(self):
        return self.get_cog('BackgroundManagement')

    async def before_command_invoke(self, ctx):
        if hasattr(ctx, 'before_invoke'):
            await ctx.before_invoke(ctx)

    async def after_command_invoke(self, ctx):
        if hasattr(ctx, 'after_invoke'):
            await ctx.after_invoke(ctx)

    async def on_message(self, message):
        if message.author.bot:
            return  # ignore bot messages

        await self.process_commands(message)

    async def process_commands(self, message):
        # we have a couple attributes to add to context, lets add them now (easy db connection etc.)
        ctx = await self.get_context(message, cls=context.Context)

        if ctx.guild is None:
            invite = getattr(self, "invite", discord.utils.oauth_url(self.user.id))
            return await ctx.send(f"Please invite me to a server to run commands: {invite}")

        if ctx.command is None:
            if self.user in message.mentions and message.channel.permissions_for(ctx.me).send_messages:
                await ctx.send(f"My prefix for this guild is {self.prefixes.get(message.guild.id, '+')}")

            return  # if there's no command invoked return

        async with ctx.acquire():
            await self.invoke(ctx)

    async def on_ready(self):
        await self.change_presence(activity=discord.Game('+help for commands'))
        await self.init_prefixes()
        self.error_webhooks = itertools.cycle(n for n in await self.get_channel(625160612791451661).webhooks())
        self.fake_clan_guilds = {row['guild_id'] for row in await self.pool.fetch("SELECT DISTINCT guild_id FROM clans WHERE fake_clan=True")}

    async def on_resumed(self):
        await self.change_presence(activity=discord.Game('+help for commands'))

    async def get_clans(self, guild_id, in_event=False):
        if in_event:
            query = "SELECT DISTINCT clan_tag FROM clans WHERE guild_id = $1 AND in_event = $2"
            fetch = await self.pool.fetch(query, guild_id, in_event)
        else:
            query = "SELECT DISTINCT clan_tag FROM clans WHERE guild_id = $1"
            fetch = await self.pool.fetch(query, guild_id)
        return await self.coc.get_clans(n[0].strip() for n in fetch).flatten()

    async def on_command_error(self, context, exception):
        try:
            return await error_handler(context, exception)
        except Exception as exc:
            log.exception('exception when logging command error', exc_info=exc)

    async def on_error(self, event_method, *args, **kwargs):
        return await discord_event_error(self, event_method, *args, **kwargs)

    async def init_prefixes(self):
        query = "SELECT guild_id, prefix FROM guilds"
        fetch = await self.pool.fetch(query)
        self.prefixes = {n["guild_id"]: n["prefix"] for n in fetch}

    async def query_member_by_id_batch(self, guild, user_ids, only_guild=True):
        results = []
        to_fetch = []

        for user in user_ids:
            result = guild.get_member(user) or (self.get_user(user) if not only_guild else None)
            if result:
                results.append(result)
            else:
                to_fetch.append(user)

        log.info("Query Members Checkpoint 1, results: %s, fetch: %s", len(results), len(to_fetch))
        if len(to_fetch) == 0:
            return results

        ws = self._get_websocket(shard_id=guild.shard_id)
        if len(to_fetch) == 1 or ws.is_ratelimited():
            # If we're being rate limited on the WS, then fall back to using the HTTP API
            # So we don't have to wait ~60 seconds for the query to finish
            for user_id in to_fetch:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException:
                    pass
                else:
                    results.append(member)
                    to_fetch.remove(user_id)
                    guild._add_member(member)

        elif len(to_fetch) <= 100:
            # If we're not being rate limited then we can use the websocket to actually query
            try:
                members = await guild.query_members(limit=100, user_ids=to_fetch, cache=True)
            except asyncio.TimeoutError:
                pass
            else:
                for member in members:
                    results.append(member)
                    if member:
                        to_fetch.remove(member.id)

        else:
            for index in range(0, len(to_fetch), 100):
                to_resolve = to_fetch[index:index + 100]
                try:
                    members = await guild.query_members(limit=100, user_ids=to_resolve, cache=True)
                except asyncio.TimeoutError:
                    continue
                else:
                    for member in members:
                        results.append(member)
                        if member:
                            to_fetch.remove(member.id)

        log.info("Query Members Checkpoint 2, results: %s, fetch: %s", len(results), len(to_fetch))
        if not only_guild and to_fetch:
            for user_id in to_fetch:
                try:
                    user = await self.fetch_user(user_id)
                except discord.HTTPException:
                    pass
                else:
                    results.append(user)
                    to_fetch.remove(user_id)

        log.info("Query Members Checkpoint 3, results: %s, fetch: %s", len(results), len(to_fetch))
        return results


if __name__ == '__main__':
    try:
        bot = DonationBot()
        bot.run(creds.bot_token)  # run bot

    except Exception:
        traceback.print_exc()
