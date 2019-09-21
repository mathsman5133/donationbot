import coc
import discord
import re

from datetime import datetime
from discord.ext import commands

tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class PlayerConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if isinstance(argument, coc.BasicPlayer):
            return argument

        tag = coc.utils.correct_tag(argument)
        name = argument.strip()

        if tag_validator.match(argument):
            try:
                return await ctx.coc.get_player(tag)
            except coc.NotFound:
                raise commands.BadArgument('I detected a player tag; and couldn\'t '
                                           'find an account with that tag! '
                                           'If you didn\'t pass in a tag, '
                                           'please drop the owner a message.'
                                           )
        guild_clans = await ctx.get_clans()
        for g in guild_clans:
            if g.name == name or g.tag == tag:
                raise commands.BadArgument(f'You appear to be passing '
                                           f'the clan tag/name for `{str(g)}`')

            member = g.get_member(name=name)
            if member:
                return member

            member_by_tag = g.get_member(tag=tag)
            if member_by_tag:
                return member_by_tag

        raise commands.BadArgument(f"Invalid tag or IGN in "
                                   f"`{','.join(str(n) for n in guild_clans)}` clans.")


class ClanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if argument in ['all', 'guild', 'server'] or not argument:
            return await ctx.get_clans()
        if isinstance(argument, coc.BasicClan):
            return argument

        tag = coc.utils.correct_tag(argument)
        name = argument.strip()

        if tag_validator.match(tag):
            try:
                clan = await ctx.coc.get_clan(argument)
            except coc.NotFound:
                raise commands.BadArgument(f'{tag} is not a valid clan tag.')

            if clan:
                return [clan]

            raise commands.BadArgument(f'{tag} is not a valid clan tag.')

        guild_clans = await ctx.get_clans()
        matches = [n for n in guild_clans if n.name == name or n.tag == tag]

        if not matches:
            raise commands.BadArgument(f'Clan name or tag `{argument}` not found')

        return matches


class DateConverter(commands.Converter):
    """Convert user input into standard format date (YYYY-MM-DD)"""

    async def convert(self, ctx, *, argument):
        error_msg = 'You may think that\'s a date, but I don\'t. Try using the DD-MM-YYYY format.'
        year_options = (f'{datetime.today().year}|{datetime.today().year + 1}|'
                        f'{str(datetime.today().year)[2:]}|{str(datetime.today().year + 1)[2:]}')

        # Check for text based month with day first
        pattern = (r'(?P<Date>\d{1,2})[/.\- ]'
                   r'(?P<Month>Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|Jun(e)?|'
                   r'Jul(y)?|Aug(ust)?|Sep(tember)?|Sept|Oct(ober)?|Nov(ember)?|Dec(ember)?)[/.\- ]'
                   r'(?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')[:3]} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %b %d'
            else:
                fmt = '%Y %b %d'

        # Check for text based month with month first
        pattern = (r'(?P<Month>Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|Jun(e)?|'
                   r'Jul(y)?|Aug(ust)?|Sep(tember)?|Sept|Oct(ober)?|Nov(ember)?|Dec(ember)?)[/.\- ]'
                   r'(?P<Date>\d{1,2})[/.\- ]'
                   r'(?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')[:3]} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %b %d'
            else:
                fmt = '%Y %b %d'

        # Check for YYYY-MM-DD
        pattern = (r'(?P<Year>' + year_options + r')[/.\- ](?P<Month>\d{1,2})[/.\- ](?P<Date>\d{1,2})')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %m %d'
            else:
                fmt = '%Y %m %d'

        # Check for DD-MM-(YY)YY
        pattern = (r'(?P<Date>\d{1,2})[/.\- ](?P<Month>\d{1,2})[/.\- ](?P<Year>' + year_options + ')')
        match = re.match(pattern, argument, re.IGNORECASE)
        if match:
            date_string = f"{match.group('Year')} {match.group('Month')} {match.group('Date')}"
            if len(match.group('Year')) == 2:
                fmt = '%y %m %d'
            else:
                fmt = '%Y %m %d'

        try:
            return datetime.strptime(date_string, fmt)
        except (ValueError, NameError):
            raise commands.BadArgument(error_msg)


class GlobalChannel(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            # Not found... so fall back to ID + global lookup
            try:
                channel_id = int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(f'Could not find a channel by ID {argument!r}.')
            else:
                channel = ctx.bot.get_channel(channel_id)
                if channel is None:
                    raise commands.BadArgument(f'Could not find a channel by ID {argument!r}.')
                return channel


class FetchedUser(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.isdigit():
            raise commands.BadArgument('Not a valid user ID.')
        try:
            return await ctx.bot.fetch_user(argument)
        except discord.NotFound:
            raise commands.BadArgument('User not found.') from None
        except discord.HTTPException:
            raise commands.BadArgument('An error occurred while fetching the user.') from None


class TextChannel(commands.TextChannelConverter):
    async def convert(self, ctx, argument):
        channel = super().convert(ctx, argument)
        ctx.custom_channel = channel
