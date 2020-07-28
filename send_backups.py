import os

import discord

from creds import backups_url

webhook = discord.Webhook.from_url(backups_url, adapter=discord.RequestsWebhookAdapter())

for fp in os.listdir("/home/mathsman/backups2"):
    try:
        webhook.send(file=discord.File(fp))
    except Exception as e:
        print(e)
