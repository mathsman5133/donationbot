import discord
from discord.ext import commands
import coc
from .donations import PlayerConverter, ClanConverter, TabularData


class GuildConfiguration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @commands.command()
    async def log(self, ctx, channel: discord.TextChannel=None, toggle: bool=True):
        """Setup a log channel for the bot.

        Logs can include:
            - Accounts claimed with `auto_claim`
            - Result of trying to auto-claim an account on clan or guild join

        Parameters
        -----------
        channel : discord.TextChannel"""
        if not channel:
            channel = ctx.channel

        query = "UPDATE guilds SET log_channel_id = $1, log_toggle = $2 WHERE guild_id = $3"
        await ctx.db.execute(query, channel.id, toggle, ctx.guild.id)
        await ctx.confirm()

    @commands.command()
    async def updates(self, ctx, channel: discord.TextChannel=None, toggle: bool=True):
        if not channel:
            channel = ctx.channel
        query = "UPDATE guilds SET updates_channel_id = $1, updates_toggle = $2 WHERE guild_id = $3"
        await ctx.db.execute(query, channel.id, toggle, ctx.guild.id)

        query = "DELETE FROM messages WHERE guild_id = $1"
        await ctx.db.execute(query, ctx.guild.id)

        msg = await channel.send('Placeholder')
        msg2 = await channel.send('Placeholder')
        query = "UPDATE guilds SET updates_message_id = $1 WHERE guild_id = $2"
        await ctx.db.execute(query, msg.id, ctx.guild.id)

        query = "INSERT INTO messages (message_id, guild_id) VALUES ($1, $2)"
        await ctx.db.execute(query, msg2.id, ctx.guild.id)
        await ctx.confirm()

    @commands.command(aliases=['aclan'])
    async def add_clan(self, ctx, clan_tag: str):
        query = "SELECT * FROM guilds WHERE clan_tag = $1 AND guild_id = $2"
        fetch = await ctx.db.fetch(query, clan_tag, ctx.guild.id)
        if fetch:
            raise commands.BadArgument('This clan has already been linked to the server.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag)
        except coc.NotFound:
            raise commands.BadArgument(f'Clan not found with `{clan_tag}` tag.')

        query = "INSERT INTO guilds (clan_tag, guild_id, clan_name) VALUES ($1, $2, $3)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, clan.name)

        query = "INSERT INTO players (player_tag, donations, received) " \
                "VALUES ($1, $2, $3) ON CONFLICT (player_tag) DO NOTHING"
        for member in clan._members:
            await ctx.db.execute(query, member.tag, member.donations, member.received)

        await ctx.confirm()
        await ctx.send('Clan and all members have been added to the database (if not already added)')
        await self.bot.get_cog('Updates').update_clan_tags()

    @commands.command(aliases=['rclan'])
    async def remove_clan(self, ctx, clan_tag: str):
        query = "DELETE FROM guilds WHERE clan_tag = $1 AND guild_id = $2"
        await ctx.db.execute(query, clan_tag, ctx.guild.id)
        await ctx.confirm()

    @commands.command(aliases=['aplayer'])
    async def add_player(self, ctx, *, player_tag: PlayerConverter):
        query = "INSERT INTO players (player_tag, donations, received) " \
                "VALUES ($1, $2, $3, $4) ON CONFLICT (tag) DO NOTHING"
        try:
            player = await ctx.bot.coc.get_player(player_tag)
        except coc.NotFound:
            raise commands.BadArgument('Player tag not found')

        await ctx.db.execute(query, player.tag, player.donations, player.received)
        await ctx.confirm()

    @commands.command()
    async def claim(self, ctx, *, player: PlayerConverter):
        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)
        if fetch:
            if fetch[0]:
                user = self.bot.get_user(fetch[0])
                raise commands.BadArgument(f'Player {player.name} '
                                           f'({player.tag}) has already been claimed by {str(user)}')
        if not fetch:
            query = "INSERT INTO players (player_tag, donations, received) VALUES ($1, $2, $3)"
            await ctx.db.execute(query, player.tag, player.donations, player.received)
            return

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
        await ctx.db.execute(query, ctx.author.id, player.tag)
        await ctx.confirm()

    @commands.command()
    async def unclaim(self, ctx, *, player: PlayerConverter):
        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)
        if fetch:
            if fetch[0] != ctx.author.id:
                raise commands.BadArgument(f'Player {player.name} '
                                           f'({player.tag}) has been claimed by {str(user)}. '
                                           f'Please contact them to unclaim it.')

        query = "UPDATE players SET user_id = NULL WHERE player_tag = $1"
        await ctx.db.execute(query, player.tag)
        await ctx.confirm()

    @commands.command()
    async def auto_claim(self, ctx, *, clan: ClanConverter=None):
        failed_players = []

        if not clan:
            clan = await ctx.get_clans()
        else:
            clan = [clan]

        prompt = await ctx.prompt('Would you like to be asked to confirm before the bot claims matching accounts? '
                                  'Else you can un-claim and reclaim if there is an incorrect claim.')
        if prompt is None:
            return

        match_player = self.bot.get_cog('Updates').match_player

        for c in clan:
            for member in c.members:
                query = "SELECT * FROM players WHERE player_tag = $1 AND user_id IS NOT NULL;"
                fetch = await ctx.db.fetchrow(query, member.tag)
                if fetch:
                    continue

                results = await match_player(member, ctx.guild, prompt, ctx)
                if not results:
                    await self.bot.log_info(c, f'[auto-claim]: No members found for {member.name} ({member.tag})',
                                            colour=discord.Colour.red())
                    failed_players.append(member)
                    continue
                    # no members found in guild with that player name
                if isinstance(results, discord.abc.User):
                    await self.bot.log_info(c, f'[auto-claim]: {member.name} ({member.tag}) '
                                               f'has been claimed to {str(results)} ({results.id})',
                                            colour=discord.Colour.green())
                    continue

                table = TabularData()
                table.set_columns(['Option', 'user#disrim', 'UserID'])
                table.add_rows([i + 1, str(n), n.id] for i, n in enumerate(results))
                result = await ctx.prompt(f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                          f'Corresponding members found:\n'
                                          f'```\n{table.render()}\n```', additional_options=len(results))
                if isinstance(result, int):
                    query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
                    await self.bot.pool.execute(query, results[result].id, member.tag)
                if result is None or result is False:
                    await self.bot.log_info(c, f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                               f'Corresponding members found, none claimed:\n'
                                               f'```\n{table.render()}\n```',
                                            colour=discord.Colour.gold())
                    failed_players.append(member)
                    continue

                await self.bot.log_info(c, f'[auto-claim]: {member.name} ({member.tag}) '
                                           f'has been claimed to {str(results[result])} ({results[result].id})',
                                        colour=discord.Colour.green())
        prompt = await ctx.prompt("Would you like to go through a list of players who weren't claimed and "
                                  "claim them now?\nI will walk you through it...")
        if not prompt:
            await ctx.confirm()
            return
        for fail in failed_players:
            m = await ctx.send(f'Player: {fail.name} ({fail.tag}), Clan: {fail.clan.name} ({fail.clan.tag}).'
                               f'\nPlease send either a UserID, user#discrim combo, '
                               f'or mention of the person you wish to claim this account to.')

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            msg = await self.bot.wait_for('message', check=check)
            try:
                member = await commands.MemberConverter().convert(ctx, msg.content)
            except commands.BadArgument:
                await ctx.send('Discord user not found. Moving on to next clan member. Please claim them manually.')
                continue
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
            await self.bot.pool.execute(query, member.id, fail.tag)
            await self.bot.log_info(fail.clan, f'[auto-claim]: {fail.name} ({fail.tag}) '
                                               f'has been claimed to {str(member)} ({member.id})',
                                    colour=discord.Colour.green())
            try:
                await m.delete()
                await msg.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.group(name='toggle', hidden=True)
    async def _toggle(self, ctx):
        pass

    @_toggle.command()
    async def mentions(self, ctx, toggle: bool=True):
        pass

    @_toggle.command()
    async def required(self, ctx, toggle: bool=True):
        pass

    @_toggle.command()
    async def nonmembers(self, ctx, toggle: bool=False):
        pass

    @_toggle.command()
    async def persist(self, ctx, toggle: bool=True):
        pass


def setup(bot):
    bot.add_cog(GuildConfiguration(bot))
