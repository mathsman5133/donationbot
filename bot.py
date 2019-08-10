import asyncio
import datetime
import coc
import discord
import aiohttp
import traceback
import creds
import textwrap

from discord.ext import commands
from cogs.utils import context
from cogs.utils.db import Table
from cogs.utils.paginator import CannotPaginate
from cogs.utils.emoji_lookup import misc
from cogs.utils.cache import cache

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

coc_client = coc.login(creds.email, creds.password, client=coc.EventsClient,
                       key_names='test', throttle_limit=40)

initial_extensions = (
    'cogs.guildsetup',
    'cogs.donations',
    'cogs.events',
    'cogs.donationboard',
    'cogs.admin',
    'cogs.info',
    'cogs.seasonstats',
    'cogs.reset_season'
)
description = "A simple discord bot to track donations of clan families in clash of clans."


class DonationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or('+'), case_insensitive=True,
                         description=description, pm_help=None, help_attrs=dict(hidden=True),
                         fetch_offline_members=True)

        self.colour = discord.Colour.blurple()
        self.coc = coc_client
        self.client_id = creds.client_id
        self.owner_id = 230214242618441728
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.error_webhook = discord.Webhook.partial(id=creds.error_hook_id,
                                                     token=creds.error_hook_token,
                                                     adapter=discord.AsyncWebhookAdapter(
                                                         session=self.session)
                                                     )
        self.join_log_webhook = discord.Webhook.partial(id=creds.join_log_hook_id,
                                                        token=creds.join_log_hook_token,
                                                        adapter=discord.AsyncWebhookAdapter(
                                                            session=self.session)
                                                        )
        self.feedback_webhook = discord.Webhook.partial(id=creds.feedback_hook_id,
                                                        token=creds.feedback_hook_token,
                                                        adapter=discord.AsyncWebhookAdapter(
                                                            session=self.session)
                                                        )

        self.uptime = datetime.datetime.utcnow()
        self.prefixes = {}
        coc_client.add_events(self.on_event_error)

        for e in initial_extensions:
            try:
                self.load_extension(e)  # load cogs
            except Exception:
                traceback.print_exc()

    @property
    def donationboard(self):
        return self.get_cog('DonationBoard')

    @property
    def events(self):
        return self.get_cog('Events')

    @property
    def seasonconfig(self):
        return self.get_cog('SeasonConfig')

    async def on_message(self, message):
        if message.author.bot:
            return  # ignore bot messages

        await self.process_commands(message)

    async def process_commands(self, message):
        # we have a couple attributes to add to context, lets add them now (easy db connection etc.)
        ctx = await self.get_context(message, cls=context.Context)

        if ctx.command is None:
            return  # if there's no command invoked return

        async with ctx.acquire():
            await self.invoke(ctx)

    async def on_error(self, event_method, *args, **kwargs):
        e = discord.Embed(title='Discord Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event_method)
        e.description = f'```py\n{traceback.format_exc()}\n```'
        e.timestamp = datetime.datetime.utcnow()

        args_str = ['```py']
        for index, arg in enumerate(args):
            args_str.append(f'[{index}]: {arg!r}')
        args_str.append('```')
        e.add_field(name='Args', value='\n'.join(args_str), inline=False)

        try:
            await self.error_webhook.send(embed=e)
        except:
            pass

    async def on_command_error(self, ctx, error):
        if not isinstance(error, commands.CommandInvokeError):
            return

        error = error.original
        if isinstance(error, (discord.Forbidden, discord.NotFound, CannotPaginate)):
            return

        e = discord.Embed(title='Command Error', colour=0xcc3366)
        e.add_field(name='Name', value=ctx.command.qualified_name)
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)
        e.add_field(name='Content', value=textwrap.shorten(ctx.message.content, width=512))

        exc = ''.join(
            traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        e.description = f'```py\n{exc}\n```'
        e.timestamp = datetime.datetime.utcnow()
        await self.error_webhook.send(embed=e)
        try:
            await ctx.send('Uh oh! Something broke. This error has been reported; '
                           'the owner is working on it. Please join the support server: '
                           'https://discord.gg/ePt8y4V to stay updated!')
        except discord.Forbidden:
            pass

    async def on_event_error(self, event_name, *args, **kwargs):
        e = discord.Embed(title='COC Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event_name)
        e.description = f'```py\n{traceback.format_exc()}\n```'
        e.timestamp = datetime.datetime.utcnow()

        args_str = ['```py']
        for index, arg in enumerate(args):
            args_str.append(f'[{index}]: {arg!r}')
        args_str.append('```')
        e.add_field(name='Args', value='\n'.join(args_str), inline=False)

        try:
            await self.error_webhook.send(embed=e)
        except:
            pass

    async def on_ready(self):
        cog = self.get_cog('DonationBoard')
        await cog.update_clan_tags()
        await self.change_presence(activity=discord.Game('+help for commands'))

    async def log_info(self, channel_id, message, colour=None, prompt=False):
        channel = self.get_channel(channel_id)
        if not channel:
            return

        e = discord.Embed(colour=colour or self.colour,
                          description=message,
                          timestamp=datetime.datetime.utcnow())
        try:
            msg = await channel.send(embed=e)
        except (discord.Forbidden, discord.HTTPException):
            return
        if prompt:
            for n in (misc['greentick'], misc['redtick']):
                try:
                    await msg.add_reaction(n)
                except (discord.Forbidden, discord.HTTPException):
                    return msg.id
        return msg.id

    async def channel_log(self, channel_id, message, colour=None, embed=True):
        channel_config = await self.events.get_channel_config(channel_id)
        if not channel_config.channel or not channel_config.log_toggle:
            return

        if embed:
            e = discord.Embed(colour=colour or self.colour,
                              description=message,
                              timestamp=datetime.datetime.utcnow())
            c = None
        else:
            e = None
            c = message

        try:
            await channel_config.channel.send(content=c, embed=e)
        except (discord.Forbidden, discord.HTTPException):
            return

    @cache()
    async def get_guilds(self, clan_tag):
        query = "SELECT guild_id FROM clans WHERE clan_tag = $1"
        fetch = await self.pool.fetch(query, clan_tag)
        return [self.get_guild(n[0]) for n in fetch if self.get_guild(n[0])]

    @cache()
    async def get_clans(self, guild_id):
        query = "SELECT clan_tag FROM clans WHERE guild_id = $1"
        fetch = await self.pool.fetch(query, guild_id)
        return await self.coc.get_clans(n[0].strip() for n in fetch).flatten()

    async def get_channel_config(self, channel_id):
        return await self.events.get_channel_config(channel_id)

    async def get_guild_config(self, guild_id):
        return await self.donationboard.get_guild_config(guild_id)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    try:
        # configure the database connection
        pool = loop.run_until_complete(Table.create_pool(creds.postgres, command_timeout=60))

        bot = DonationBot()
        bot.pool = pool  # add db as attribute
        bot.run(creds.bot_token)  # run bot

    except Exception:
        traceback.print_exc()
