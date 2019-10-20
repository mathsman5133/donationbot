from cogs.utils.category import Category

from .eventstats import EventStats
from .seasonstats import SeasonStats
from .stats import Stats

description = """
The main stats command for all donation, trophy, attacks and defense statistics.

This command does nothing by itself, however - check out the subcommands!

If your server is currently in an event (+info event), this will automatically divert your command to
`+eventstats...`, otherwise it will automatically call `+seasonstats....`.
"""


def setup(bot):
    stats_category = Category(
        bot=bot,
        name='Stats',
        description=description
    )

    stats_category.add_cogs(
        EventStats,
        SeasonStats,
        Stats
    )
