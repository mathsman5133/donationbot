import discord

from collections import namedtuple
from datetime import datetime, timedelta

from cogs.utils.formatters import readable_time



class DatabaseBoard:
    __slots__ = ('bot', 'guild_id', 'channel_id', 'icon_url', 'title', 'render', 'toggle', 'type')

    def __init__(self, *, guild_id, board_type, bot, record=None):
        self.guild_id = guild_id
        self.type = board_type
        self.bot = bot

        if record:
            get = record.get
            self.channel_id = get('channel_id')
            self.icon_url = get('icon_url')
            self.title = get('title')
            self.render = get('render')
            self.toggle = get('type')
        else:
            self.channel_id = None
            self.render = 1
            self.toggle = False

    @property
    def board_channel(self):
        return self.bot.get_channel(self.channel_id)


class DatabaseGuild:
    __slots__ = ('bot', 'guild_id', 'id', 'updates_toggle', 'auto_claim', 'donationboard_title',
                 'icon_url', 'donationboard_render')

    def __init__(self, *, guild_id, bot, record=None):
        self.guild_id = guild_id
        self.bot = bot

        if record:
            get = record.get
            self.id = get('id')
            self.updates_toggle = get('updates_toggle')
            self.auto_claim = get('auto_claim')
            self.donationboard_title = get('donationboard_title')
            self.icon_url = get('icon_url')
            self.donationboard_render = get('donationboard_render')

            self.donationboard_id = get('donationboard_id')
            self.trophyboard_id = get('trophyboard_id')
            self.attackboard_id = get('attackboard_id')
        else:
            self.updates_channel_id = None
            self.updates_toggle = False
            self.auto_claim = False

    @property
    def donationboard(self):
        return self.bot.get_channel(self.donationboard_id)

    @property
    def trophyboard(self):
        return self.bot.get_channel(self.trophyboard_id)

    @property
    def attackboard(self):
        return self.bot.get_channel(self.attackboard_id)

    async def updates_messages(self):
        query = "SELECT id, message_id, guild_id, channel_id FROM messages WHERE guild_id = $1"
        fetch = await self.bot.pool.fetch(query, self.guild_id)
        return [DatabaseMessage(bot=self.bot, record=n) for n in fetch]


class DatabasePlayer:
    def __init__(self, *, bot, player_tag=None, record=None):
        self.bot = bot

        if record:
            get = record.get
            self.id = get('id')
            self.player_tag = get('player_tag')
            self.donations = get('donations')
            self.received = get('received')
            self.user_id = get('user_id')
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
            get = record.get
            self.id = get('id')
            self.guild_id = get('guild_id')
            self.clan_tag = get('clan_tag')
            self.clan_name = get('clan_name')
            self.channel_id = get('channel_id')
            self.log_interval = get('log_interval')
            self.log_toggle = get('log_toggle')
        else:
            self.guild_id = None
            self.clan_tag = clan_tag

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)

    @property
    def interval_seconds(self):
        return self.log_interval.total_seconds()

    async def full_clan(self):
        return await self.bot.coc.get_clan(self.clan_tag)


class DonationEvent:
    __slots__ = ('bot', 'id', 'player_tag', 'player_name', 'clan_tag', 'donations', 'received', 'time')

    def __init__(self, *, bot, record=None):
        self.bot = bot

        if record:
            get = record.get
            self.id = get('id')
            self.player_tag = get('player_tag')
            self.player_name = get('player_name')
            self.clan_tag = get('clan_tag')
            self.donations = get('donations')
            self.received = get('received')
            self.time = get('time')

        else:
            self.time = None

    @property
    def readable_time(self):
        return readable_time((datetime.utcnow() - self.time).total_seconds())

    @property
    def delta_since(self):
        return datetime.utcnow() - self.time


class TrophyEvent:
    __slots__ = ('bot', 'id', 'player_tag', 'player_name', 'clan_tag', 'trophy_change', 'received', 'time')

    def __init__(self, *, bot, record=None):
        self.bot = bot

        if record:
            get = record.get
            self.id = get('id')
            self.player_tag = get('player_tag')
            self.player_name = get('player_name')
            self.clan_tag = get('clan_tag')
            self.trophy_change = get('trophy_change')
            self.received = get('received')
            self.time = get('time')
        else:
            self.time = None

    @property
    def readable_time(self):
        return readable_time((datetime.utcnow() - self.time).total_seconds())

    @property
    def delta_since(self):
        return datetime.utcnow() - self.time


class LogConfig:
    __slots__ = ('bot', 'guild_id', 'channel_id', 'interval', 'toggle')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.channel_id: int = record['channel_id']
        self.interval: timedelta = record['interval']
        self.toggle: bool = record['toggle']

    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self.channel_id)

    @property
    def seconds(self) -> float:
        return self.interval.total_seconds()


class BoardConfig:
    __slots__ = ('bot', 'guild_id', 'channel_id', 'icon_url', 'title',
                 'render', 'toggle', 'board_type', 'in_event')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.channel_id: int = record['channel_id']
        self.icon_url: str = record['icon_url']
        self.title: str = record['title']
        self.render: int = record['render']
        self.toggle: bool = record['toggle']
        self.board_type: str = record['board_type']
        self.in_event: bool = record['in_event']

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)

    async def messages(self):
        query = """SELECT guild_id, 
                          message_id, 
                          channel_id 
                   FROM messages 
                   WHERE guild_id = $1
                """
        fetch = await self.bot.pool.fetch(query, self.guild_id)
        return [DatabaseMessage(bot=self.bot, record=n) for n in fetch]


class DatabaseMessage:
    __slots__ = ('bot', 'guild_id', 'message_id', 'channel_id')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.message_id: int = record['message_id']
        self.channel_id: int = record['channel_id']

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self):
        return self.bot.get_channel(self.channel_id)

    async def get_message(self):
        return await self.bot.utils.get_message(self.channel, self.message_id)


SlimDonationEvent = namedtuple('SlimDonationEvent', 'donations received name clan_tag')
SlimTrophyEvent = namedtuple('SlimTrophyEvent', 'trophies name clan_tag')
