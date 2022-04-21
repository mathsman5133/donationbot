import os

import disnake

from creds import backups_url

webhook = disnake.SyncWebhook.from_url(backups_url)

for fp in os.listdir("/home/mathsman/backups2"):
    try:
        webhook.send(file=disnake.File("/home/mathsman/backups2/" + fp))
    except Exception as e:
        print(e)
