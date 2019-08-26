from discord.ext import commands


async def check_guild_permissions(ctx, perms, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def manage_guild():
    async def pred(ctx):
        return await check_guild_permissions(ctx, {'manage_guild': True})
    return commands.check(pred)


def is_patron_pred(ctx):
    return any(r.id == 605349824472154134 for
               r in ctx.bot.get_guild(594276321937326091).get_member(ctx.author.id).roles) \
           or ctx.author.id == ctx.bot.owner_id


def is_patron():
    return commands.check(is_patron_pred)
