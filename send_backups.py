import os

import discord

from creds import backups_url

webhook = discord.Webhook.from_url(backups_url, adapter=discord.RequestsWebhookAdapter())

for fp in os.listdir("/home/mathsman/donationbot/backups"):
    webhook.send(file=discord.File(fp))
