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

        log.error(f"Interaction error, author {interaction.user}, channel {interaction.channel_id}", exc_info=error)

        message = "Sorry, something went wrong. Please join the support " \
                  "server for more help: https://discord.gg/ePt8y4V"
        if not await interaction.original_response():
            await interaction.response.send_message(message, ephemeral=True)
            return
        else:
            await interaction.followup.send(message, ephemeral=True)
