import datetime
import discord
import textwrap
import traceback
import logging
import io

import coc

from cogs.utils import formatters, paginator, checks

from discord.ext import commands

import creds

log = logging.getLogger()


async def error_handler(ctx, error):
    error = getattr(error, 'original', error)

    if isinstance(error, (commands.MissingPermissions, RuntimeError, discord.Forbidden)):
        log.info('command raised no bot permissions: %s, author: %s, error: %s', ctx.invoked_with, ctx.author.id, error)
        return await ctx.send(str(error) if error else "Please double-check the bot's permissions and try again.")

    if isinstance(error, (checks.NoConfigFailure, paginator.CannotPaginate, commands.CheckFailure)):
        log.info('command raised checks failure: %s, author: %s', ctx.invoked_with, ctx.author.id)
        return await ctx.send(str(error))

    if isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
        if str(error):
            return await ctx.send(str(error))
        else:
            return
    if isinstance(error, commands.MissingRequiredArgument):
        log.info('command missing required argument: %s, author: %s', ctx.invoked_with, ctx.author.id)
        return await ctx.send(f'Oops! That didn\'t look right... '
                              f'please see how to use the command with `+help {ctx.command.qualified_name}`')
    if isinstance(error, commands.CommandOnCooldown):
        if await ctx.bot.is_owner(ctx.author):
            return await ctx.reinvoke()
        time = formatters.readable_time(error.retry_after)
        log.info('command raised cooldown error: %s', ctx.invoked_with)
        return await ctx.send(f'You\'re on cooldown. Please try again in: {time}')
    if isinstance(error, coc.HTTPException):
        log.info('coc api raised %s for command %s', error, ctx.invoked_with)
        return await ctx.send(f"The COC API returned {error.message}. "
                              f"If this persists, please join the support server and let us know!")

    ctx.command.reset_cooldown(ctx)

    if isinstance(error, (discord.Forbidden, discord.NotFound, paginator.CannotPaginate)):
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

    log.exception('unhandled error occured, command: %s, author: %s', ctx.invoked_with, ctx.author.id, exc_info=error)

    if len(exc) > 2000:
        fp = io.BytesIO(exc.encode('utf-8'))
        e.description = "Traceback was too long."
        return await ctx.send(embed=e, file=discord.File(fp, 'traceback.txt'))

    e.description = f'```py\n{exc}\n```'

    e.timestamp = datetime.datetime.utcnow()
    if not creds.live:
        await ctx.send(embed=e)
        return

    await ctx.bot.error_webhook.send(embed=e)
    try:
        await ctx.send('Uh oh! Something broke. This error has been reported; '
                       'the owner is working on it. Please join the support server: '
                       'https://discord.gg/ePt8y4V to stay updated!')
    except discord.Forbidden:
        pass


async def discord_event_error(bot, event_method, *args, **kwargs):
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
        await bot.error_webhook.send(embed=e)
    except:
        pass


async def clash_event_error(bot, event_name, exception, *args, **kwargs):
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
        await bot.error_webhook.send(embed=e)
    except:
        pass

