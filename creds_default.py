# required to launch the bot
email = 'name@email.com'  # from https://developer.clashofclans.com/#/
password = 'password'  # from https://developer.clashofclans.com/#/
bot_token = 'BOT_TOKEN'  # from https://discordapp.com/developers/applications/
postgres = 'postgresql://user:password@host:5432/databasename'
live = False  # whether the bot should load settings as production mode. This will change the key name for COCAPI, and bot prefix.


# optional
dbl_token = 'DBL_TOKEN'  # from https://top.gg/api
client_id = 123456789  # your bot's user/client ID


# optional detailed error handling via discord webhooks.
error_hook_id = 123456789  # for error logs
error_hook_token = 'WEBHOOK_TOKEN'  # token for error webhook
join_log_hook_id = 123456789
join_log_hook_token = 'JOIN_LOG_WEBHOOK_TOKEN'
feedback_hook_id = 123456789
feedback_hook_token = 'FEEDBACK_WEBHOOK_TOKEN'
log_hook_id = 123456789
log_hook_token = 'LOGGING_WEBHOOK_TOKEN'
command_hook_id = 123456789
command_hook_token = 'COMMAND_WEBHOOK_TOKEN'
