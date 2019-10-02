from discord.ext import commands


async def check_guild_permissions(ctx, perms, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        raise commands.CheckFailure('You must be in a guild to run this command!')

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
    return any(r.id == 605349824472154134 for
               r in ctx.bot.get_guild(594276321937326091).get_member(ctx.author.id).roles) \
           or ctx.author.id == ctx.bot.owner_id


def is_patron():
    return commands.check(is_patron_pred)


async def before_invoke(ctx):
    config_type = getattr(ctx, 'config_type', None)
    if not config_type:
        return

    invalidate = getattr(ctx, 'invalidate', False)

    if config_type == 'donationboard':
        ctx.config = await ctx.bot.utils.get_board_config(ctx.guild.id, 'donation', invalidate)

    elif config_type == 'trophyboard':
        ctx.config = await ctx.bot.utils.get_board_config(ctx.guild.id, 'trophy', invalidate)

    elif config_type == 'event':
        if invalidate:
            ctx.bot.utils.event_config.invalidate(ctx.bot.utils, ctx.guild.id)

        ctx.config = await ctx.bot.utils.event_config(ctx.guild.id)

    elif config_type == 'donationlog':
        channel = getattr(ctx, 'custom_channel', ctx.channel)
        if invalidate:
            ctx.bot.utils.log_config.invalidate(ctx.bot.utils, channel.id, 'donation')
        ctx.config = await ctx.bot.utils.log_config(channel.id, 'donation')

    elif config_type == 'trophylog':
        channel = getattr(ctx, 'custom_channel', ctx.channel)
        if invalidate:
            ctx.bot.utils.log_config.invalidate(ctx.bot.utils, channel.id, 'trophy')
        ctx.config = await ctx.bot.utils.log_config(channel.id, 'trophy')

async def after_invoke(ctx):
    if not getattr(ctx, 'invalidate', False):
        return
    config_type = getattr(ctx, 'config_type', None)
    if not config_type:
        return

    if not getattr(ctx, 'config', None):
        return

    if config_type in ['donationboard', 'trophyboard']:
        ctx.bot.utils.board_config.invalidate(ctx.bot.utils, ctx.config.channel_id)
    if config_type == 'donationlog':
        ctx.bot.utils.log_config.invalidate(ctx.bot.utils, ctx.config.channel_id, 'donation')
    elif config_type == 'trophylog':
        ctx.bot.utils.log_config.invalidate(ctx.bot.utils, ctx.config.channel_id, 'trophy')
    elif config_type == 'event':
        ctx.bot.utils.event_config.invalidate(ctx.bot.utils, ctx.guild.id)
    return ctx


def requires_config(config_type, invalidate=False):
    async def pred(ctx):
        ctx.before_invoke = before_invoke
        ctx.after_invoke = after_invoke
        ctx.config_type = config_type
        ctx.invalidate = invalidate
        return True
    return commands.check(pred)


