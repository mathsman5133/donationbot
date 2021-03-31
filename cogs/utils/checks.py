import discord
from discord.ext import commands

PATRON_PERK_ROLES = [605349824472154134, 683559116731318423]
HELPER_ROLE = 705550299699478609


class NoConfigFailure(commands.CheckFailure):
    pass


async def helper_check(bot, user):
    try:
        support_member = await bot.get_guild(594276321937326091).fetch_member(user.id)
    except discord.NotFound:
        return False
    else:
        if any(r.id == HELPER_ROLE for r in support_member.roles):
            return True
        else:
            return False


async def check_guild_permissions(ctx, perms, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        raise commands.CheckFailure('You must be in a guild to run this command!')
    if ctx.guild.id == 594276321937326091:
        # custom message for the support server
        raise commands.CheckFailure("You should run this command in your server! Get the invite link with `+invite`.")
    if await helper_check(ctx.bot, ctx.author):
        return True

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def manage_guild():
    async def pred(ctx):
        perms = await check_guild_permissions(ctx, {'manage_guild': True})
        if not perms:
            raise commands.CheckFailure('You must have `Manage Server` permissions to use this command!')
        return True
    return commands.check(pred)


def is_patron_pred(ctx):
    if ctx.author.id in ctx.bot.owner_ids:
        return True

    guild = ctx.bot.get_guild(594276321937326091)
    if not guild:
        return False

    member = guild.get_member(ctx.author.id)
    if not member:
        return False

    return any(r.id in PATRON_PERK_ROLES for r in member.roles)

def is_patron():
    return commands.check(is_patron_pred)


async def before_invoke(ctx):
    config_type = getattr(ctx, 'config_type', None)
    if not config_type:
        return

    # invalidate = getattr(ctx, 'invalidate', False)
    error = getattr(ctx, 'error_without_config', False)
    channel = getattr(ctx, 'custom_channel', ctx.channel)

    if config_type in ['donationboard', 'trophyboard', 'lastonlineboard']:
        ctx.config = await ctx.bot.utils.board_config(channel.id)

    elif config_type == 'event':
        ctx.config = await ctx.bot.utils.event_config(ctx.guild.id)

    elif config_type == 'donationlog':
        ctx.config = await ctx.bot.utils.log_config(channel.id, 'donation')

    elif config_type == 'trophylog':
        ctx.config = await ctx.bot.utils.log_config(channel.id, 'trophy')

    elif config_type == 'legendlog':
        ctx.config = await ctx.bot.utils.log_config(channel.id, 'legend')

    if error and not ctx.config:
        raise NoConfigFailure(f'Please create a {config_type} with `+help add {config_type}`')


async def after_invoke(ctx):
    if not getattr(ctx, 'invalidate', False):
        return
    config_type = getattr(ctx, 'config_type', None)
    if not config_type:
        return

    if not getattr(ctx, 'config', None):
        return
    return ctx


def requires_config(config_type, error=False):
    async def pred(ctx):
        ctx.before_invoke = before_invoke
        ctx.after_invoke = after_invoke
        ctx.config_type = config_type
        ctx.error_without_config = error
        return True
    return commands.check(pred)


