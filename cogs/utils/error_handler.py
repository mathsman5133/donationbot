import datetime
import discord
import textwrap
import traceback


from cogs.utils import formatters, paginator
from discord.ext import commands


async def error_handler(ctx, error):
    if isinstance(error, commands.CheckFailure):
        # TODO are there any other checks that might end up here?
        await ctx.send('\N{WARNING SIGN} You must have '
                       '`manage_server` permission to run this command.')
        return
    if isinstance(error, (commands.BadArgument, commands.BadUnionArgument, commands.MissingRequiredArgument)):
        return await ctx.send(f'Oops! That didn\'t look right... '
                              f'please see how to use the command with `+help {ctx.command.qualified_name}`')
        return await ctx.send(str(error))
    if not isinstance(error, commands.CommandError):
        return
    if isinstance(error, commands.CommandOnCooldown):
        if await ctx.bot.is_owner(ctx.author):
            return await ctx.reinvoke()
        time = formatters.readable_time(error.retry_after)
        return await ctx.send(f'You\'re on cooldown. Please try again in: {time}')

    ctx.command.reset_cooldown(ctx)

    if not isinstance(error, commands.CommandInvokeError):
        return

    if isinstance(error, (discord.Forbidden, discord.NotFound, paginator.CannotPaginate)):
        return

    error = getattr(error, 'original', error)

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
    await ctx.bot.error_webhook.send(embed=e)
    try:
        await ctx.send('Uh oh! Something broke. This error has been reported; '
                       'the owner is working on it. Please join the support server: '
                       'https://discord.gg/ePt8y4V to stay updated!')
    except discord.Forbidden:
        pass


async def discord_event_error(self, event_method, *args, **kwargs):
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


async def clash_event_error(self, event_name, exception, *args, **kwargs):
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
        await self.bot.error_webhook.send(embed=e)
    except:
        pass

