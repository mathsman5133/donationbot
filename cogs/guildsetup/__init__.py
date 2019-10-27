from cogs.utils.category import Category

from .add import Add
from .edit import Edit
from .remove import Remove

description = "Setup and manage the bot's configurations for your server."


def setup(bot):
    stats_category = Category(
        bot=bot,
        name='Server Setup',
        description=description,
        fp='guildsetup'
    )

    stats_category.add_cogs(
        Add,
        Remove,
        Edit
    )
