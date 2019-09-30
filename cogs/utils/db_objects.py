import discord

from collections import namedtuple
from datetime import datetime, timedelta

from cogs.utils.formatters import readable_time


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


class LogConfig:
    __slots__ = ('bot', 'guild_id', 'channel_id', 'interval', 'toggle', 'type')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.channel_id: int = record['channel_id']
        self.interval: timedelta = record['interval']
        self.toggle: bool = record['toggle']
        self.type: str = record['type']

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
                 'render', 'toggle', 'type', 'in_event')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.channel_id: int = record['channel_id']
        self.icon_url: str = record['icon_url']
        self.title: str = record['title']
        self.render: int = record['render']
        self.toggle: bool = record['toggle']
        self.type: str = record['type']
        self.in_event: bool = record['in_event']

    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self.channel_id)

    async def messages(self) -> list:
        query = """SELECT guild_id, 
                          message_id, 
                          channel_id 
                   FROM messages 
                   WHERE channel_id = $1
                   ORDER BY message_id DESC
                """
        fetch = await self.bot.pool.fetch(query, self.channel_id)
        return [DatabaseMessage(bot=self.bot, record=n) for n in fetch]


class DatabaseMessage:
    __slots__ = ('bot', 'guild_id', 'message_id', 'channel_id')

    def __init__(self, *, bot, record):
        self.bot = bot

        self.guild_id: int = record['guild_id']
        self.message_id: int = record['message_id']
        self.channel_id: int = record['channel_id']

    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self.channel_id)

    async def get_message(self) -> discord.Message:
        return await self.bot.utils.get_message(self.channel, self.message_id)


SlimDonationEvent = namedtuple('SlimDonationEvent', 'donations received name clan_tag')
SlimTrophyEvent = namedtuple('SlimTrophyEvent', 'trophies name clan_tag')
SlimEventConfig = namedtuple('SlimEventConfig', 'id start finish event_name channel_id')
SlimDummyBoardConfig = namedtuple('SlimDummyBoardConfig', 'type render title icon_url')
SlimDummyLogConfig = namedtuple('SlimDummyLogConfig', 'type title icon_url')