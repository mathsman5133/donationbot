from .eventstats import EventStats
from .seasonstats import SeasonStats
from .stats import Stats


def setup(bot):
    bot.add_cog(EventStats(bot))
    bot.add_cog(SeasonStats(bot))
    bot.add_cog(Stats(bot))
