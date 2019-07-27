import discord
from discord.ext import commands
import coc
from .donations import PlayerConverter, ClanConverter
import math
from .utils import paginator, checks, formatters, fuzzy
import typing


class GuildConfiguration(commands.Cog):
    """All commands related to setting up the server for the first time, and managing configurations."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)

        if isinstance(error, commands.CheckFailure):
            await ctx.send('\N{WARNING SIGN} You must have `manage_server` permission to run this command.')
        if not isinstance(error, commands.CommandError):
            return
        if isinstance(error, commands.CommandOnCooldown):
            if ctx.author.id == self.bot.owner_id:
                return await ctx.reinvoke()
            time = formatters.readable_time(error.retry_after)
            return await ctx.send(f'You\'re on cooldown. Please try again in: {time}')
        else:
            await ctx.command.reset_cooldown(ctx)

    async def match_player(self, player, guild: discord.Guild, prompt=False, ctx=None,
                           score_cutoff=20, claim=True):
        matches = fuzzy.extract_matches(player.name, [n.name for n in guild.members],
                                        score_cutoff=score_cutoff, scorer=fuzzy.partial_ratio,
                                        limit=9)
        if len(matches) == 0:
            return None
        if len(matches) == 1:
            user = guild.get_member_named(matches[0][0])
            if prompt:
                m = await ctx.prompt(f'[auto-claim]: {player.name} ({player.tag}) '
                                     f'to be claimed to {str(user)} ({user.id}). '
                                     f'If already claimed, this will do nothing.')
                if m is True and claim is True:
                    query = "UPDATE players SET user_id = $1 " \
                            "WHERE player_tag = $2 AND user_id IS NULL"
                    await self.bot.pool.execute(query, user.id, player.tag)
                else:
                    return False
            return user
        return [guild.get_member_named(n[0]) for n in matches]

    async def match_member(self, member, clan, claim):
        matches = fuzzy.extract_matches(member.name, [n.name for n in clan.members],
                                        score_cutoff=60)
        if len(matches) == 0:
            return None
        for i, n in enumerate(matches):
            query = "SELECT user_id FROM players WHERE player_tag = $1"
            m = clan.get_member(name=n[0])
            fetch = await self.bot.pool.fetchrow(query, m.tag)
            if fetch is None:
                continue
            del matches[i]

        if len(matches) == 1 and claim is True:
            player = clan.get_member(name=matches[0][0])
            query = "UPDATE players SET user_id = $1 WHERE player_tag = $2 AND user_id IS NULL"
            await self.bot.pool.execute(query, member.id, player.tag)
            return player
        elif len(matches) == 1:
            return True

        return [clan.get_member(name=n) for n in matches]

    @commands.command(aliases=['aclan'])
    @checks.manage_guild()
    async def add_clan(self, ctx, clan_tag: str):
        """Link a clan to your server.
        This will add all accounts in clan to the database, if not already present.

        Parameters
        ----------------
        Pass in any of the following:

            • A clan tag

        Example
        -----------
        • `+add_clan #CLAN_TAG`
        • `+aclan #CLAN_TAG`

        Aliases
        -----------
        • `+add_clan` (primary)
        • `+aclan`

        Required Permissions
        ------------------------------
        • `manage_server` permissions
        """
        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "SELECT * FROM clans WHERE clan_tag = $1 AND guild_id = $2"
        fetch = await ctx.db.fetch(query, clan_tag, ctx.guild.id)
        if fetch:
            raise commands.BadArgument('This clan has already been linked to the server.')

        try:
            clan = await ctx.bot.coc.get_clan(clan_tag)
        except coc.NotFound:
            raise commands.BadArgument(f'Clan not found with `{clan_tag}` tag.')

        query = "INSERT INTO clans (clan_tag, guild_id, clan_name) VALUES ($1, $2, $3)"
        await ctx.db.execute(query, clan.tag, ctx.guild.id, clan.name)

        query = "INSERT INTO players (player_tag, donations, received) " \
                "VALUES ($1, $2, $3) ON CONFLICT (player_tag) DO NOTHING"
        for member in clan.itermembers:
            await ctx.db.execute(query, member.tag, member.donations, member.received)

        await ctx.confirm()
        await ctx.send('Clan and all members have been added to the database (if not already added)')
        await self.bot.donationboard.update_clan_tags()

    @commands.command(aliases=['rclan'])
    @checks.manage_guild()
    async def remove_clan(self, ctx, clan_tag: str):
        """Unlink a clan from your server.

        Parameters
        -----------------
        Pass in any of the following:

            • A clan tag

        Example
        -------------
        • `+remove_clan #CLAN_TAG`
        • `+rclan #CLAN_TAG`

        Aliases
        ------------
        • `+remove_clan` (primary)
        • `+rclan`

        Required Permissions
        ----------------------------
        • `manage_server` permissions
        """
        clan_tag = coc.utils.correct_tag(clan_tag)
        query = "DELETE FROM clans WHERE clan_tag = $1 AND guild_id = $2"
        await ctx.db.execute(query, clan_tag, ctx.guild.id)
        await ctx.confirm()
        await self.bot.donationboard.update_clan_tags()

    @commands.command(aliases=['aplayer'])
    async def add_player(self, ctx, *, player: PlayerConverter):
        """Manually add a clash account to the database. This does not claim the account.

        Parameters
        -----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in clan claimed in server)

        Example
        ------------
        • `+add_player #PLAYER_TAG`
        • `+aplayer my account name`

        Aliases
        -------------
        • `+add_player` (primary)
        • `+aplayer`
        """
        query = "INSERT INTO players (player_tag, donations, received) " \
                "VALUES ($1, $2, $3) ON CONFLICT (player_tag) DO NOTHING"
        await ctx.db.execute(query, player.tag, player.donations, player.received)
        await ctx.confirm()

    @commands.command()
    async def claim(self, ctx, user: typing.Optional[discord.Member] = None, *,
                    player: PlayerConverter):
        """Link a clash account to your discord account

        Parameters
        ------------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in clan claimed in server)

        Example
        -------------
        • `+claim #PLAYER_TAG`
        • `+claim my account name
        """
        if not user:
            user = ctx.author

        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)

        if not fetch:
            query = "INSERT INTO players (player_tag, donations, received, user_id) " \
                    "VALUES ($1, $2, $3, $4)"
            await ctx.db.execute(query, player.tag, player.donations, player.received, user.id)
            return await ctx.confirm()

        if fetch[0]:
            user = self.bot.get_user(fetch[0])
            raise commands.BadArgument(f'Player {player.name} '
                                       f'({player.tag}) has already been claimed by {str(user)}')

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
        await ctx.db.execute(query, user.id, player.tag)
        await ctx.confirm()

    @commands.command()
    async def unclaim(self, ctx, *, player: PlayerConverter):
        """Unlink a clash account from your discord account

        Parameters
        ----------------
        Pass in any of the following:

            • A player tag
            • A player name (must be in clan claimed in server)

        Example
        -------------
        • `+unclaim #PLAYER_TAG`
        • `+unclaim my account name
        """
        if ctx.channel.permissions_for(ctx.author).manage_guild \
                or await self.bot.is_owner(ctx.author):
            query = "UPDATE players SET user_id = NULL WHERE player_tag = $1"
            await ctx.db.execute(query, player.tag)
            return await ctx.confirm()

        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)
        if not fetch:
            query = "UPDATE players SET user_id = NULL WHERE player_tag = $1"
            await ctx.db.execute(query, player.tag)
            return await ctx.confirm()

        if fetch[0] != ctx.author.id:
            return await ctx.send(f'Player has been claimed by '
                                  f'{self.bot.get_user(fetch[0]) or "unknown"}.\n'
                                  f'Please contact them, or someone '
                                  f'with `manage_guild` permissions to unclaim it.')

        query = "UPDATE players SET user_id = NULL WHERE player_tag = $1"
        await ctx.db.execute(query, player.tag)
        await ctx.confirm()

    @commands.command()
    @commands.cooldown(1, 43200, commands.BucketType.guild)
    async def refresh(self, ctx, *, clans: ClanConverter = None):
        """Manually refresh all players in the database with current donations and received.

        Note: it will only update their donations if the
              amount recorded in-game is more than in the database.
              Ie. if they have left and re-joined it won't update them, usually.

        Cool-downs
        ----------------
        You can only call this command once every **12 hours** due to the
        amount of resources it requires to run, and to prevent future abuse.

        Parameters
        --------------------
        Pass in any one of the following:
            • clan tag
            • clan name (if claimed)
            • `all`, `server`, `guild` for all clans in guild
            • None: all clans in guild

        Example
        ---------------
        `+refresh all`
        `+refresh`
        `+refresh #CLAN_TAG`
        """
        if not clans:
            clans = await ctx.get_clans()
        query = """UPDATE players 
                        SET donations=$1, received=$2
                    WHERE player_tag=$3
                    AND donations<$1
                    AND received<$2
                """
        for clan in clans:
            for member in clan.members:
                await ctx.db.execute(query, member.donations, member.received, member.tag)
        await ctx.confirm()

    @commands.command()
    @commands.is_owner()
    async def reset_cooldown(self, ctx):
        await self.refresh.reset_cooldown(ctx)
        await ctx.confirm()

    @commands.command()
    async def accounts(self, ctx, *, clans: ClanConverter = None):
        """Get accounts and claims for all accounts in clans in a server.

        Parameters
        ------------------
        Pass in any one of the following:
            • clan tag
            • clan name (if claimed)
            • `all`, `server`, `guild` for all clans in guild
            • None: all clans in guild

        Example
        ------------
        • `+accounts #CLAN_TAG`
        • `+accounts guild`
        """
        if not clans:
            clans = await ctx.get_clans()

        players = []
        for n in clans:
            players.extend(x for x in n.members)

        final = []

        query = "SELECT user_id FROM players WHERE player_tag = $1"
        for n in players:
            fetch = await ctx.db.fetchrow(query, n.tag)
            if not fetch:
                final.append([n.name, n.tag, 'None'])
                continue
            name = str(ctx.guild.get_member(fetch[0]))

            if len(name) > 20:
                name = name[:20] + '..'
            final.append([n.name, n.tag, name])

        table = formatters.TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)

        messages = math.ceil(len(final) / 20)
        entries = []

        for i in range(int(messages)):

            results = final[i*20:(i+1)*20]

            table = formatters.TabularData()
            table.set_columns(['IGN', 'Tag', "Claimed By"])
            table.add_rows(results)

            entries.append(f'```\n{table.render()}\n```')

        p = paginator.Pages(ctx, entries=entries, per_page=1)
        p.embed.colour = self.bot.colour
        p.embed.title = f"Accounts for {', '.join(f'{c.name}' for c in clans)}"

        await p.paginate()

    @commands.command()
    async def get_claims(self, ctx, *, player: typing.Union[PlayerConverter, discord.Member]=None):
        """Get accounts and claims for a player or discord user.

        Parameters
        ------------------
        Pass in any one of the following:
            • discord @mention
            • discord user#discrim combo
            • discord user id
            • player tag
            • player name (must be in clan claimed in server)

        Example
        --------------
        • `+get_claims @my_friend`
        • `+get_claims my_friend#1208
        • `+gclaims #PLAYER_TAG`
        • `+gc player name`

        Aliases
        -------------
        • `+get_claims` (primary)
        • `+gclaims`
        • `+gc`
        """
        if not player:
            player = ctx.author

        if isinstance(player, discord.Member):
            query = "SELECT player_tag FROM players WHERE user_id = $1"
            fetch = await ctx.db.fetch(query, player.id)
            if not fetch:
                return await ctx.send(f'{str(player)} has no claimed accounts.')
            player = await ctx.coc.get_players(n[0] for n in fetch).flatten()
        else:
            player = [player]

        query = "SELECT user_id FROM players WHERE player_tag = $1"

        final = []
        for n in player:
            fetch = await ctx.db.fetch(query, n.tag)
            if not fetch:
                final.append([n.name, n.tag, 'None'])
                continue

            name = str(ctx.guild.get_member(fetch[0]))

            if len(name) > 20:
                name = name[:20] + '..'
            final.append([n.name, n.tag, name])

        table = formatters.TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)
        await ctx.send(f'```\n{table.render()}\n```')

    @commands.command()
    @checks.manage_guild()
    async def auto_claim(self, ctx, *, clan: ClanConverter = None):
        """Automatically claim all accounts in server, through an interactive process.

        It will go through all players in claimed clans in server, matching them to discord users where possible.
        The interactive process is easy to use, and will try to guide you through as easily as possible

        Parameters
        -----------------
        Pass in any of the following:

            • A clan tag
            • A clan name (must be claimed clan)
            • `all`, `server`, `guild` will get all clans claimed in the server
            • None passed will get all clans claimed in the server

        Example
        -------------
        • `+auto_claim #CLAN_TAG`
        • `+auto_claim my clan name`
        • `+aclaim all`
        • `+aclaim`

        Aliases
        --------------
        • `+auto_claim` (primary)
        • `+aclaim`

        Required Permissions
        ------------------------------
        • `manage_server` permissions
        """
        failed_players = []

        if not clan:
            clan = await ctx.get_clans()
        else:
            clan = [clan]

        prompt = await ctx.prompt('Would you like to be asked to confirm before the bot claims matching accounts? '
                                  'Else you can un-claim and reclaim if there is an incorrect claim.')
        if prompt is None:
            return

        match_player = self.match_player

        for c in clan:
            for member in c.members:
                query = "SELECT * FROM players WHERE player_tag = $1 AND user_id IS NOT NULL;"
                fetch = await ctx.db.fetchrow(query, member.tag)
                if fetch:
                    continue

                results = await match_player(member, ctx.guild, prompt, ctx)
                if not results:
                    await self.bot.log_info(ctx.guild.id, f'[auto-claim]: No members found for {member.name} ({member.tag})',
                                            colour=discord.Colour.red())
                    failed_players.append(member)
                    continue
                    # no members found in guild with that player name
                if isinstance(results, discord.abc.User):
                    await self.bot.log_info(ctx.guild.id, f'[auto-claim]: {member.name} ({member.tag}) '
                                            f'has been claimed to {str(results)} ({results.id})',
                                            colour=discord.Colour.green())
                    continue

                table = formatters.TabularData()
                table.set_columns(['Option', 'user#disrim', 'UserID'])
                table.add_rows([i + 1, str(n), n.id] for i, n in enumerate(results))
                result = await ctx.prompt(f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                          f'Corresponding members found:\n'
                                          f'```\n{table.render()}\n```', additional_options=len(results))
                if isinstance(result, int):
                    query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
                    await self.bot.pool.execute(query, results[result].id, member.tag)
                if result is None or result is False:
                    await self.bot.log_info(ctx.guild.id, f'[auto-claim]: For player {member.name} ({member.tag})\n'
                                               f'Corresponding members found, none claimed:\n'
                                               f'```\n{table.render()}\n```',
                                            colour=discord.Colour.gold())
                    failed_players.append(member)
                    continue

                await self.bot.log_info(ctx.guild.id, f'[auto-claim]: {member.name} ({member.tag}) '
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
            await self.bot.log_info(ctx.guild.id, f'[auto-claim]: {fail.name} ({fail.tag}) '
                                               f'has been claimed to {str(member)} ({member.id})',
                                    colour=discord.Colour.green())
            try:
                await m.delete()
                await msg.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        prompt = await ctx.prompt('Would you like to have the bot to search for players to claim when '
                                  'someone joins the clan/server? I will let you know what I find '
                                  'and you must confirm/deny if you want them claimed.')
        if prompt is True:
            query = "UPDATE guilds SET auto_claim = True WHERE guild_id = $1;"
            await ctx.db.execute(query, ctx.guild.id)

        await ctx.send('All done. Thanks!')
        await ctx.confirm()

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
