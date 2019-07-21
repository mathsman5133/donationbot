from datetime import datetime

from cogs.utils.formatters import readable_time


class DatabaseGuild:
    __slots__ = ('bot', 'guild_id', 'id', 'updates_channel_id', 'updates_header_id', 'updates_toggle',
                 'log_channel_id', 'log_toggle', 'ign', 'don', 'rec', 'tag', 'claimed_by', 'clan',
                 'auto_claim', 'donationboard_title', 'icon_url', 'donationboard_render', 'log_interval')

    def __init__(self, *, guild_id, bot, record=None):
        self.guild_id = guild_id
        self.bot = bot

        if record:
            self.id = record['id']
            self.updates_channel_id = record['updates_channel_id']
            self.updates_toggle = record['updates_toggle']
            self.log_channel_id = record['log_channel_id']
            self.log_toggle = record['log_toggle']
            self.ign = record['updates_ign']
            self.don = record['updates_don']
            self.rec = record['updates_rec']
            self.tag = record['updates_tag']
            self.claimed_by = record['updates_claimed_by']
            self.clan = record['updates_clan']  # record['updates_clan']
            self.auto_claim = record['auto_claim']
            self.donationboard_title = record['donationboard_title']
            self.icon_url = record['icon_url']
            self.donationboard_render = record['donationboard_render']
            self.log_interval = record['log_interval']
        else:
            self.updates_channel_id = None
            self.log_channel_id = None
            self.updates_toggle = False
            self.log_toggle = False
            self.auto_claim = False

    @property
    def donationboard(self):
        return self.bot.get_channel(self.updates_channel_id)

    @property
    def log_channel(self):
        guild = self.bot.get_guild(self.guild_id)
        return guild and guild.get_channel(self.log_channel_id)

    async def updates_messages(self):
        query = "SELECT * FROM messages WHERE guild_id = $1"
        fetch = await self.bot.pool.fetch(query, self.guild_id)
        return [DatabaseMessage(bot=self.bot, record=n) for n in fetch]


class DatabasePlayer:
    def __init__(self, *, bot, player_tag=None, record=None):
        self.bot = bot

        if record:
            self.id = record['id']
            self.player_tag = record['player_tag']
            self.donations = record['donations']
            self.received = record['received']
            self.user_id = record['user_id']
        else:
            self.user_id = None
            self.player_tag = player_tag

    @property
    def owner(self):
        return self.bot.get_user(self.user_id)

    async def full_player(self):
        return await self.bot.coc.get_player(self.player_tag)


class DatabaseClan:
    def __init__(self, *, bot, clan_tag=None, record=None):
        self.bot = bot

        if record:
            self.id = record['id']
            self.guild_id = record['guild_id']
            self.clan_tag = record['clan_tag']
            self.clan_name = record['clan_name']
        else:
            self.guild_id = None
            self.clan_tag = clan_tag

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    async def full_clan(self):
        return await self.bot.coc.get_clan(self.clan_tag)


class DatabaseMessage:
    def __init__(self, *, bot, record=None):
        self.bot = bot

        if record:
            self.id = record['id']
            self.guild_id = record['guild_id']
            self.message_id = record['message_id']
            self.channel_id = record['channel_id']

        else:
            self.guild_id = None
            self.channel_id = None
            self.message_id = None

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)

    async def get_message(self):
        return await self.bot.donationboard.get_message(self.channel, self.message_id)


class DatabaseEvent:
    def __init__(self, *, bot, record=None):
        self.bot = bot

        if record:
            self.id = record['id']
            self.player_tag = record['player_tag']
            self.player_name = record['player_name']
            self.clan_tag = record['clan_tag']
            self.donations = record['donations']
            self.received = record['received']
            self.time = record['time']

        else:
            self.time = None

    @property
    def readable_time(self):
        return readable_time((datetime.utcnow() - self.time).total_seconds())

    @property
    def delta_since(self):
        return datetime.utcnow() - self.time

