import asyncio
import creds
import discord
import logging


def setup_logging(bot):
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('websockets.protocol').setLevel(logging.WARNING)
    logging.getLogger('coc').setLevel(logging.INFO)
    logging.getLogger('coc.http').setLevel(logging.WARNING)

    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='donationtracker.log', encoding='utf-8', mode='w').setLevel(logging.INFO)
    stream_handler = logging.StreamHandler().setLevel(logging.DEBUG)
    dt_fmt = '%d-%m-%Y %H:%M:%S'
    fmt = logging.Formatter('[{asctime}] [{levelname:<7}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(fmt)
    stream_handler.setFormatter(handler)
    log.addHandler(handler)
    log.addHandler(stream_handler)

    error_webhook = discord.Webhook.partial(
        id=creds.log_hook_id,
        token=creds.log_hook_token,
        adapter=discord.AsyncWebhookAdapter(session=bot.session)
                                            )

    class DiscordHandler(logging.NullHandler):
        def handle(self, record):
            if record.levelno < 30:
                return

            asyncio.ensure_future(error_webhook.send(fmt.format(record)))

    log.addHandler(DiscordHandler())





