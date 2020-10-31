import datetime
import typing

import discord

from discord.ext import commands

from cogs.utils.checks import requires_config, manage_guild
from cogs.utils.converters import PlayerConverter, ClanChannelComboConverter


class Aliases(commands.Cog, name='\u200bAliases'):
    def __init__(self, bot):
        self.bot = bot

    def get_aliases(self, full_name):
        return None

    @commands.command()
    @requires_config('event')
    async def claim(self, ctx, user: typing.Optional[discord.Member] = None, *, player: str):
        """Link a clash account to your discord account

        **Parameters**
        :key: Discord user (optional - defaults to yourself)
        :key: A player tag OR name

        **Format**
        :information_source: `+claim @MENTION #PLAYERTAG`
        :information_source: `+claim @MENTION PLAYER NAME`
        :information_source: `+claim #PLAYERTAG`

        **Example**
        :white_check_mark: `+claim @mathsman #P0LYJC8C`
        :white_check_mark: `+claim @mathsman mathsman5133`
        :white_check_mark: `+claim #P0LYJC8C`
        """
        cmd = self.bot.get_command('add discord')
        if not await cmd.can_run(ctx):
            return

        await ctx.invoke(cmd, user=user, player=player)

    @commands.command(name='multiclaim')
    @requires_config('event')
    async def multi_claim(self, ctx, user: discord.Member, *players: str):
        """Helper command to link many clash accounts to a user's discord.

        Note: unlike `+claim`, a discord mention **is not optional** - mention yourself if you want.

        **Parameters**
        :key: A discord user (mention etc.)
        :key: Player tags OR names

        **Format**
        :information_source: `+multiclaim @MENTION #PLAYER_TAG #PLAYER_TAG2 #PLAYER_TAG3`
        :information_source: `+multiclaim @MENTION PLAYERNAME PLAYERNAME2 PLAYERNAME3`

        **Example**
        :white_check_mark: `+multiclaim @mathsman #P0LYJC8C #C0LLJC8 #P0CC8JY`
        :white_check_mark: `+multiclaim @mathsman mathsman raptor217 johnny36`
        """
        cmd = self.bot.get_command('add multidiscord')
        if not await cmd.can_run(ctx):
            return

        await ctx.invoke(cmd, user=user, players=players)

    @commands.command()
    async def unclaim(self, ctx, *, player: str):
        """Unlink a clash account from your discord account.

        If you have not claimed the account, you must have `Manage Server` permissions.

        **Parameters**
        :key: Player name OR tag.

        **Format**
        :information_source: `+unclaim #PLAYER_TAG`
        :information_source: `+unclaim PLAYER NAME`

        **Example**
        :white_check_mark: `+unclaim #P0LYJC8C`
        :white_check_mark: `+unclaim mathsman`
        """
        cmd = self.bot.get_command('remove discord')
        if await cmd.can_run(ctx):
            await ctx.invoke(cmd, player=player)

    @commands.command()
    @manage_guild()
    @requires_config('event')
    async def donationlog(self, ctx, *, body: ClanChannelComboConverter):
        """A quick and easy way to add a clan and a donationlog, in 1 command.

        Note: As a security feature, the clan must have the letters `dt` added
        at the end of the clan's description.

        This is a security feature of the bot to ensure you have proper (co)ownership of the clan.
        `dt` should be removed once the command has been sucessfully run.

        If you are not a patron, this server must have less than 4 unique clans added.

        **Parameters**
        :key: A discord channel (#mention). If you don't have this, it will use the channel you're in.
        :key: A clan tag

        **Format**
        :information_source: `+donationlog #CLAN_TAG`
        :information_source: `+donationlog #CHANNEL #CLAN_TAG`

        **Example**
        :white_check_mark: `+donationlog #my-donation-log #P0LYJC8C`
        :white_check_mark: `+donationlog #P0LYJC8C`

        **Required Permissions**
        :warning: Manage Server"""
        channel, clan = body
        if not clan:
            await ctx.send_help(ctx.command)
            return await ctx.send("I couldn't detect a clan from your message. Please try again.")

        await self.do_log_add(ctx, channel or ctx.channel, clan, "donation")

    @commands.command()
    @manage_guild()
    @requires_config('event')
    async def trophylog(self, ctx, *, body: ClanChannelComboConverter):
        """A quick and easy way to add a clan and a trophylog, in 1 command.

        Note: As a security feature, the clan must have the letters `dt` added
        at the end of the clan's description.

        This is a security feature of the bot to ensure you have proper (co)ownership of the clan.
        `dt` should be removed once the command has been sucessfully run.

        If you are not a patron, this server must have less than 4 unique clans added.

        **Parameters**
        :key: A discord channel (#mention). If you don't have this, it will use the channel you're in.
        :key: A clan tag

        **Format**
        :information_source: `+trophylog #CLAN_TAG`
        :information_source: `+trophylog #CHANNEL #CLAN_TAG`

        **Example**
        :white_check_mark: `+trophylog #my-trophy-log #P0LYJC8C`
        :white_check_mark: `+trophylog #P0LYJC8C`

        **Required Permissions**
        :warning: Manage Server"""
        channel, clan = body
        if not clan:
            await ctx.send_help(ctx.command)
            return await ctx.send("I couldn't detect a clan from your message. Please try again.")

        await self.do_log_add(ctx, channel or ctx.channel, clan, "trophy")

    async def do_log_add(self, ctx, channel, clan, type_):
        channel = channel or ctx.channel

        if not clan:
            return await ctx.send_help(ctx.command)

        board_config = await self.bot.utils.board_config(channel.id)
        if board_config:
            return await ctx.send('You can\'t have the same channel for a board and log!')
        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        in_event = ctx.config and ctx.config.start < datetime.datetime.utcnow()

        query = """INSERT INTO clans (
                       clan_tag, 
                       guild_id, 
                       channel_id, 
                       clan_name, 
                       in_event
                    )
                    VALUES ($1, $2, $3, $4, $5) 
                    ON CONFLICT (clan_tag, channel_id) 
                    DO NOTHING;
                """
        await ctx.db.execute(query, clan.tag, ctx.guild.id, channel.id, clan.name, in_event)

        season_id = await self.bot.seasonconfig.get_season_id()
        query = """INSERT INTO players (
                                                player_tag, 
                                                donations, 
                                                received, 
                                                trophies, 
                                                start_trophies, 
                                                season_id,
                                                start_update,
                                                clan_tag,
                                                player_name
                                                ) 
                            VALUES ($1,$2,$3,$4,$4,$5,True, $6, $7) 
                            ON CONFLICT (player_tag, season_id) 
                            DO UPDATE SET clan_tag = $6
                        """
        async with ctx.db.transaction():
            for member in clan.members:
                await ctx.db.execute(query, member.tag, member.donations, member.received, member.trophies, season_id,
                                     clan.tag, member.name)

        self.bot.dispatch('clan_claim', ctx, clan)

        query = """INSERT INTO logs (
                       guild_id,
                       channel_id,
                       toggle,
                       type
                    )
                    VALUES ($1, $2, True, $3) 
                    ON CONFLICT (channel_id, type)
                    DO UPDATE SET toggle = True;
                """
        await ctx.db.execute(query, ctx.guild.id, channel.id, type_)

        return await ctx.send(f'{channel.mention} has been added as a {type_}log channel for {clan} ({clan.tag})')

    @commands.command(aliases=["trophyevents"], hidden=True)
    async def donationevents(self, ctx):
        await ctx.send(
            f"These commands have been removed as this data is no longer saved. "
            f"Please join the support server for more questions: {self.bot.support_invite}"
        )


def setup(bot):
    bot.add_cog(Aliases(bot))
