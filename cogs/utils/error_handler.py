from cogs.utils import formatters
from discord.ext import commands


async def error_handler(ctx, error):
    if isinstance(error, commands.CheckFailure):
        # TODO are there any other checks that might end up here?
        await ctx.send('\N{WARNING SIGN} You must have '
                       '`manage_server` permission to run this command.')
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send(str(error))
        return
    if not isinstance(error, commands.CommandError):
        return
    if isinstance(error, commands.CommandOnCooldown):
        if await ctx.bot.is_owner(ctx.author):
            return await ctx.reinvoke()
        time = formatters.readable_time(error.retry_after)
        return await ctx.send(f'You\'re on cooldown. Please try again in: {time}')
    else:
        ctx.command.reset_cooldown(ctx)
        return await ctx.send(str(error))
