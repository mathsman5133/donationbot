import creds

from cogs.utils.category import Category

from .donationlogs import DonationLogs
from .trophylog import TrophyLogs
from .events import Events

description = "Get donation and trophy events for a player, user, clan or server."

if creds.live:
    cogs = [
        Events,
        DonationLogs,
        TrophyLogs
    ]
else:
    cogs = [Events]


def setup(bot):
    stats_category = Category(
        bot=bot,
        name='Events',
        description=description,
        fp='events'
    )

    stats_category.add_cogs(cogs)
