from discord.ext import commands


def manage_guild():
    async def pred(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        perms = ctx.channel.permissions_for(ctx.author)
        if perms.manage_guild:
            return True
        return False
    return commands.check(pred)
