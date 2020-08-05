import asyncio
import creds
import discord
import logging
import logging.handlers
import math
import sqlite3


def setup_logging(bot, test_syncer=False):
    if test_syncer:
        db = sqlite3.connect("errors.sqlite")
        db.execute("create table if not exists errors (script text, level integer, message text, time timestamp, module text);")
        db.commit()

    # logging.getLogger('discord').setLevel(logging.INFO)
    # logging.getLogger('discord.http').setLevel(logging.WARNING)
    # logging.getLogger('discord.state').setLevel(logging.WARNING)
    # logging.getLogger('websockets.protocol').setLevel(logging.WARNING)
    # logging.getLogger('coc').setLevel(logging.INFO)
    # logging.getLogger('coc.http').setLevel(logging.WARNING)

    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    dt_fmt = '%d-%m-%Y %H:%M:%S'
    fmt = logging.Formatter('[{asctime}] [{levelname:<7}] {name}: {message}', dt_fmt, style='{')
    if creds.live:
        handler = logging.FileHandler(filename='donationtracker.log', encoding='utf-8', mode='w')
        handler.setLevel(logging.INFO)
        handler.setFormatter(fmt)
        log.addHandler(handler)

    stream_handler.setFormatter(fmt)
    log.addHandler(stream_handler)

    error_webhook = discord.Webhook.partial(
        id=creds.log_hook_id,
        token=creds.log_hook_token,
        adapter=discord.AsyncWebhookAdapter(session=bot.session)
                                            )
    requests_hook = discord.Webhook.partial(
        id=creds.log_hook_id,
        token=creds.log_hook_token,
        adapter=discord.RequestsWebhookAdapter()
    )

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # add handler to the logger
    handler = logging.handlers.SysLogHandler('/dev/log')

    # add syslog format to the handler
    formatter = logging.Formatter(
        'Python: { "loggerName":"%(name)s", "timestamp":"%(asctime)s", "pathName":"%(pathname)s", "logRecordCreationTime":"%(created)f", "functionName":"%(funcName)s", "levelNo":"%(levelno)s", "lineNo":"%(lineno)d", "time":"%(msecs)d", "levelName":"%(levelname)s", "message":"%(message)s"}')

    handler.formatter = formatter
    logger.addHandler(handler)

    logger.info("Test Log")

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
                    asyncio.ensure_future(error_webhook.send(f'```\n{n}\n```'))
                except:
                    pass

        def emit(self, record):
            self.handle(record)

    discord_hndlr = DiscordHandler()
    discord_hndlr.setLevel(logging.DEBUG)
    log.addHandler(discord_hndlr)


def add_hooks(bot):
    bot.error_webhook = discord.Webhook.partial(id=creds.error_hook_id,
                                                token=creds.error_hook_token,
                                                adapter=discord.AsyncWebhookAdapter(
                                                    session=bot.session)
                                                )
    bot.join_log_webhook = discord.Webhook.partial(id=creds.join_log_hook_id,
                                                   token=creds.join_log_hook_token,
                                                   adapter=discord.AsyncWebhookAdapter(
                                                        session=bot.session)
                                                   )
    bot.feedback_webhook = discord.Webhook.partial(id=creds.feedback_hook_id,
                                                   token=creds.feedback_hook_token,
                                                   adapter=discord.AsyncWebhookAdapter(
                                                        session=bot.session)
                                                   )
    bot.command_webhook = discord.Webhook.partial(id=creds.command_hook_id,
                                                  token=creds.command_hook_token,
                                                  adapter=discord.AsyncWebhookAdapter(
                                                      session=bot.session
                                                  )
                                                  )
    return bot


