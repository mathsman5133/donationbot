import typing

import discord

from discord.ext import commands

from cogs.utils.checks import requires_config
from cogs.utils.converters import PlayerConverter


class Aliases(commands.Cog, command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot

    def get_aliases(self, full_name):
        return None

    @commands.command()
    @requires_config('event')
    async def claim(self, ctx, user: typing.Optional[discord.Member] = None, *,
                    player: PlayerConverter):
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
    async def multi_claim(self, ctx, user: discord.Member,
                          players: commands.Greedy[PlayerConverter]):
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
    async def unclaim(self, ctx, *, player: PlayerConverter):
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


def setup(bot):
    bot.add_cog(Aliases(bot))
