import asyncio
import creds
import disnake
import logging
import logging.handlers
import math
import itertools
import sys

# from google.cloud import logging as glogging
# from oauth2client.service_account import ServiceAccountCredentials

def setup_logging(bot, test_syncer=False):
    # google_log_client = glogging.Client(project='donationbot')
    # google_log_client.setup_logging()

    # bot.message_log = google_log_client.logger('messages')
    #
    # bot.command_log = google_log_client.logger('commands')
    # bot.guild_log = google_log_client.logger('guilds')
    # bot.clan_log = google_log_client.logger('clans')
    # bot.google_logger = google_log_client.logger('syncer')
    # bot.board_log = google_log_client.logger('boards')

    logging.getLogger('disnake').setLevel(logging.INFO)
    logging.getLogger('disnake.http').setLevel(logging.WARNING)
    logging.getLogger('disnake.state').setLevel(logging.WARNING)
    logging.getLogger('websockets.protocol').setLevel(logging.WARNING)
    logging.getLogger('coc').setLevel(logging.INFO)
    logging.getLogger('coc.events').setLevel(logging.INFO)
    logging.getLogger('coc.http').setLevel(logging.INFO)

    log = logging.getLogger()
    log.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    dt_fmt = '%H:%M:%S'
    fmt = logging.Formatter('[{asctime}]: {message}', dt_fmt, style='{')
    # if creds.live:
    #     handler = logging.FileHandler(filename='donationtracker.log', encoding='utf-8', mode='w')
    #     handler.setLevel(logging.INFO)
    #     handler.setFormatter(fmt)
    #     log.addHandler(handler)

    stream_handler.setFormatter(fmt)
    log.addHandler(stream_handler)

    bot.error_webhooks = itertools.cycle(
        [disnake.Webhook.partial(id=creds.log_hook_id, token=creds.log_hook_token, session=bot.session)]
    )
    # add handler to the logger
    # handler = logging.handlers.SysLogHandler('/dev/log')
    #
    # # add syslog format to the handler
    # formatter = logging.Formatter(
    #     'Python: { "loggerName":"%(name)s", "timestamp":"%(asctime)s", "pathName":"%(pathname)s", "logRecordCreationTime":"%(created)f", "functionName":"%(funcName)s", "levelNo":"%(levelno)s", "lineNo":"%(lineno)d", "time":"%(msecs)d", "levelName":"%(levelname)s", "message":"%(message)s"}')
    #
    # handler.formatter = formatter
    # logger.addHandler(handler)
    #
    # logger.info("Test Log")
    #
    # class COCPYFilter(logging.Filter):
    #     def filter(self, record: logging.LogRecord) -> int:
    #         return record.msg == "API HTTP Request"
    #
    # logger = logging.getLogger("coc.http")
    # logger.addFilter(COCPYFilter())
    # logger.setLevel(logging.DEBUG)
    # formatter = logging.Formatter('coc.py API: { "loggerName":"%(name)s", "timestamp":"%(asctime)s", "pathName":"%(pathname)s", "method": "%(method)s", "url": "%(url)s", "status": "%(status)s", "perf_counter": "%(perf_counter)s"}')
    # handler = logging.handlers.SysLogHandler('/dev/log')
    # handler.formatter = formatter
    # logger.addHandler(handler)

    class DiscordHandler(logging.NullHandler):
        def handle(self, record):
            if not creds.live:
                return
            if record.levelno < 20:
                return

            to_send = fmt.format(record)

            messages = []
            for i in range(math.ceil(len(to_send) / 1950)):
                messages.append(to_send[i*1950:(i+1)*1950])

            for n in messages:
                try:
                    asyncio.ensure_future(next(bot.error_webhooks).send(f'```\n{n}\n```'))
                except:
                    pass

        def emit(self, record):
            self.handle(record)

    discord_hndlr = DiscordHandler()
    discord_hndlr.setLevel(logging.INFO)
    # log.addHandler(discord_hndlr)


def add_hooks(bot):
    bot.error_webhook = disnake.Webhook.partial(id=creds.error_hook_id, token=creds.error_hook_token, session=bot.session)
    bot.join_log_webhook = disnake.Webhook.partial(id=creds.join_log_hook_id, token=creds.join_log_hook_token, session=bot.session)
    bot.feedback_webhook = disnake.Webhook.partial(id=creds.feedback_hook_id, token=creds.feedback_hook_token, session=bot.session)
    bot.command_webhook = disnake.Webhook.partial(id=creds.command_hook_id, token=creds.command_hook_token, session=bot.session)

    return bot


