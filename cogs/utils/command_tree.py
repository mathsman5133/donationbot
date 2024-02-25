import logging

from discord import app_commands, Interaction

from cogs.utils import formatters

log = logging.getLogger()


class CustomCommandTree(app_commands.CommandTree):
    async def on_error(
        self,
        interaction: Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            time = formatters.readable_time(error.retry_after)
            await interaction.response.send_message(f"You're on cooldown. Please try again in: {time}.", ephemeral=True)

        log.error("Interaction author: %s, error: %s", interaction.user.name, str(error))
