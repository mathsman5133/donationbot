import math

from cogs.utils import formatters
from cogs.utils.checks import requires_config
from datetime import datetime
from collections import namedtuple
from discord.ext import commands

DummyRender = namedtuple('DummyRender', 'render type icon_url')


class Event(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='eventstats', invoke_without_command=True)
    async def eventstats(self, ctx):
        """[Group] Provide statistics for the current (or most recent) event for this server.

        **Parameters**

        """
        if ctx.invoked_subcommand is not

    @eventstats.command(name='attacks')
    @requires_config('event')
    async def attacks(self, ctx):
        """Get attack wins for all clans.

           By default, you shouldn't need to call these sub-commands as the bot will
           parse your argument and direct it to the correct sub-command automatically.

           **Example**
           :white_check_mark: `+trophies attacks`
        """
        if not ctx.config:
            in_event = False
        else:
            in_event = ctx.config.start < datetime.utcnow() < ctx.config.finish
        if in_event:
            query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                        FROM eventplayers 
                        WHERE event_id = $1
                        ORDER BY attacks DESC
                    """
            fetch = await ctx.db.fetch(query, ctx.config.id)

            title = f"Attack wins for {ctx.config.event_name}"
        else:
            tags = []
            clans = await ctx.get_clans()
            for n in clans:
                tags.extend(x.tag for x in n.itermembers)
            query = """SELECT player_tag, end_attacks - start_attacks as attacks, trophies 
                        FROM players
                        WHERE player_tag=ANY($1::TEXT[])
                        AND season_id=$2
                        ORDER BY attacks DESC
                    """
            fetch = await ctx.db.fetch(query, tags, await self.bot.seasonconfig.get_season_id() - 1)

            if not fetch:
                return await ctx.send(f"No players claimed for clans "
                                      f"`{', '.join(f'{c.name} ({c.tag})' for c in clans)}`"
                                      )

            title = f"Attack wins for {', '.join(f'{c.name}' for c in clans)}"

        page_count = math.ceil(len(fetch) / 20)

        ctx.config = DummyRender(3, None, None)
        p = formatters.TrophyPaginator(ctx, data=fetch, title=title, page_count=page_count)

        await p.paginate()

def setup(bot):
    bot.add_cog(Event(bot))
