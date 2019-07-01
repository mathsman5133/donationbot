import discord
from discord.ext import commands
import coc
from .donations import PlayerConverter, ClanConverter, TabularData
import math
from .utils import paginator
import typing
from .utils import checks


class GuildConfiguration(commands.Cog):
    """All commands related to setting up the server for the first time, and managing configurations."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_command_error(self, ctx, error):
        await ctx.send(str(error))

    @staticmethod
    async def updates_fields_settings(ctx, *, default=False, ign=False,
                                      don=False, rec=False, tag=False, claimed_by=False):
        if default is True:
            ign = True
            don = True
            rec = True
            tag = False
            claimed_by = False

        query = "UPDATE guilds SET updates_ign = $1, updates_don = $2, updates_rec = $3, " \
                "updates_tag = $4, updates_claimed_by = $5 WHERE guild_id = $6"
        await ctx.db.execute(query, ign, don, rec, tag, claimed_by, ctx.guild.id)

    @commands.command()
    @checks.manage_guild()
    async def log(self, ctx, channel: discord.TextChannel=None, toggle: bool=True):
        """Designate a channel for logs.

        Parameters
        ----------------
        Pass in any of the following:

            • A discord channel: #channel or a channel id. This defaults to the channel you are in.
            • Toggle: `True` or `False`: the toggle option. This defaults to `True`.

        Example
        -----------
        • `+log #CHANNEL True`
        • `+log CHANNEL_ID False`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        if not channel:
            channel = ctx.channel
        if not (channel.permissions_for(ctx.me).send_messages or channel.permissions_for(ctx.me).read_messages):
            return await ctx.send('I need permission to send and read messages here!')

        query = "UPDATE guilds SET log_channel_id = $1, log_toggle = $2 WHERE guild_id = $3"
        await ctx.db.execute(query, channel.id, toggle, ctx.guild.id)
        await ctx.confirm()

    @commands.group(invoke_without_command=True)
    @checks.manage_guild()
    async def updates(self, ctx, *, name='donationboard'):
        """Creates a donationboard channel for donation updates.

        Parameters
        ----------------
        Pass in any of the following:

            • A name for the channel. Defaults to `donationboard`

        Example
        -----------
        • `+updates`
        • `+updates my cool donationboard name`

        Required Perimssions
        ----------------------------
        • `manage_server` permissions

        Bot Required Permissions
        --------------------------------
        • `manage_channels` permissions
        """
        cog = self.bot.get_cog('Updates')
        cog._guild_config_cache[ctx.guild.id] = None
        guild_config = await cog.get_guild_config(ctx.guild.id)
        if guild_config.updates_channel is not None:
            return await ctx.send(f'This server already has a donationboard ({guild_config.updates_channel.mention})')

        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.manage_channels:
            return await ctx.send('I need manage channels permission to create the donationboard!')

        overwrites = {
            ctx.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True,
                                                embed_links=True, manage_messages=True),
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False,
                                                                read_message_history=True)
        }
        reason = f'{str(ctx.author)} created a donationboard channel.'

        try:
            channel = await ctx.guild.create_text_channel(name=name, overwrites=overwrites, reason=reason)
        except discord.Forbidden:
            return await ctx.send('I do not have permissions to create the donationboard channel.')
        except discord.HTTPException:
            return await ctx.send('Creating the channel failed. Try checking the name?')

        header = await channel.send('Placeholder')

        query = "UPDATE guilds SET updates_channel_id = $1, updates_toggle = $2, " \
                "updates_message_id = $3 WHERE guild_id = $4"
        await ctx.db.execute(query, channel.id, True, header.id, ctx.guild.id)

        msg = await channel.send('Placeholder')

        query = "INSERT INTO messages (message_id, guild_id) VALUES ($1, $2)"
        await ctx.db.execute(query, msg.id, ctx.guild.id)
        cog._guild_config_cache[ctx.guild.id] = None
        await ctx.send(f'Donationboard channel created: {channel.mention}')

        prompt = await ctx.prompt('Would you like to set custom fields for the message? The default is '
                                  'IGN, donations and received, in that order. This combination is mobile friendly, '
                                  'but once you start adding fields the formatting does not work on mobile.')
        if not prompt:
            await ctx.send('All done. Thanks!')
            await self.updates_fields_settings(ctx, default=True)
            return await ctx.confirm()

        ign = await ctx.prompt('Would you like an IGN (In-game name) column?')
        if ign is None:
            await self.updates_fields_settings(ctx, default=True)
            return await ctx.confirm()

        don = await ctx.prompt('Would you like a donations column?')
        if don is None:
            await self.updates_fields_settings(ctx, ign=ign, don=True, rec=True)
            return await ctx.confirm()

        rec = await ctx.prompt('Would you like a received column?')
        if rec is None:
            await self.updates_fields_settings(ctx, ign=ign, don=don, rec=True)
            return await ctx.confirm()

        tag = await ctx.prompt('Would you like a player tag column?')
        if tag is None:
            await self.updates_fields_settings(ctx, ign=ign, don=don, rec=rec)
            return await ctx.confirm()

        claimed_by = await ctx.prompt('Would you like a claimed_by column?')
        if claimed_by is None:
            await self.updates_fields_settings(ctx, ign=ign, don=don, rec=rec, tag=tag)
            return await ctx.confirm()

        await self.updates_fields_settings(ctx, ign=ign, don=don, rec=rec, tag=tag, claimed_by=claimed_by)
        await ctx.send('All done. Thanks!')
        return await ctx.confirm()

    @updates.command(name='info')
    async def donationboard_info(self, ctx):
        """Gives you info about the donationboard.
        """
        cog = self.bot.get_cog('Updates')
        guild_config = await cog.get_guild_config(ctx.guild.id)

        channel = guild_config.updates_channel
        data = []

        if channel is None:
            data.append('Channel: #deleted-channel')
        else:
            data.append(f'Channel: {channel.mention}')

        query = "SELECT clan_name, clan_tag FROM clans WHERE guild_id = $1;"
        fetch = await ctx.db.fetch(query, ctx.guild.id)

        data.append(f"Clans: {', '.join(f'{n[0]} ({n[1]})' for n in fetch)}")

        message = await cog.get_message(channel=guild_config.updates_channel, message_id=guild_config.updates_header_id)
        timestamp = message.embeds[0].timestamp
        if timestamp:
            data.append(f"Last Updated: {timestamp:%Y-%m-%d %H:%M:%S%z}")

        columns = []
        if guild_config.ign:
            columns.append("IGN")
        if guild_config.tag:
            columns.append("Tag")
        if guild_config.don:
            columns.append("Donations")
        if guild_config.rec:
            columns.append("Received")
        if guild_config.claimed_by:
            columns.append("Claimed By")
        data.append(f"Columns: {', '.join(columns)}")

        await ctx.send('\n'.join(data))

    @commands.command(aliases=['aclan'])
    @checks.manage_guild()
    async def add_clan(self, ctx, clan_tag: str):
        """Link a clan to your server. This will add all accounts in clan to the database, if not already present.

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

        Required Perimssions
        ------------------------------
        • `manage_server` permissions
        """
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
        for member in clan._members:
            await ctx.db.execute(query, member.tag, member.donations, member.received)

        await ctx.confirm()
        await ctx.send('Clan and all members have been added to the database (if not already added)')
        await self.bot.get_cog('Updates').update_clan_tags()

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

        Required Perimssions
        ----------------------------
        • `manage_server` permissions
        """
        query = "DELETE FROM clans WHERE clan_tag = $1 AND guild_id = $2"
        await ctx.db.execute(query, clan_tag, ctx.guild.id)
        await ctx.confirm()

    @commands.command(aliases=['aplayer'])
    async def add_player(self, ctx, *, player_tag: PlayerConverter):
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
                "VALUES ($1, $2, $3, $4) ON CONFLICT (tag) DO NOTHING"
        try:
            player = await ctx.bot.coc.get_player(player_tag)
        except coc.NotFound:
            raise commands.BadArgument('Player tag not found')

        await ctx.db.execute(query, player.tag, player.donations, player.received)
        await ctx.confirm()

    @commands.command()
    async def claim(self, ctx, *, player: PlayerConverter):
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
        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)
        if fetch:
            user = self.bot.get_user(fetch[0])
            raise commands.BadArgument(f'Player {player.name} '
                                       f'({player.tag}) has already been claimed by {str(user)}')
        if not fetch:
            query = "INSERT INTO players (player_tag, donations, received, user_id) VALUES ($1, $2, $3, $4)"
            await ctx.db.execute(query, player.tag, player.donations, player.received, ctx.author.id)
            return await ctx.confirm()

        query = "UPDATE players SET user_id = $1 WHERE player_tag = $2"
        await ctx.db.execute(query, ctx.author.id, player.tag)
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
        query = "SELECT user_id FROM players WHERE player_tag = $1"
        fetch = await ctx.db.fetchrow(query, player.tag)
        if fetch:
            if fetch[0] != ctx.author.id:
                return await ctx.send(f'Player {player.name} '
                                      f"({player.tag}) has been claimed by "
                                      f"{str(ctx.guild.get_member(fetch[0]) or 'Member not in guild.')}. "
                                      f'Please contact them to un-claim it.')

        query = "UPDATE players SET user_id = NULL WHERE player_tag = $1"
        await ctx.db.execute(query, player.tag)
        await ctx.confirm()

    @commands.command()
    async def accounts(self, ctx, *, clans: ClanConverter=None):
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

        table = TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)

        messages = math.ceil(len(final) / 20)
        entries = []

        for i in range(int(messages)):

            results = final[i*20:(i+1)*20]

            table = TabularData()
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

        table = TabularData()
        table.set_columns(['IGN', 'Tag', 'Claimed By'])
        table.add_rows(final)
        await ctx.send(f'```\n{table.render()}\n```')

    @commands.command()
    @checks.manage_guild()
    async def auto_claim(self, ctx, *, clan: ClanConverter=None):
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

        Required Perimssions
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
