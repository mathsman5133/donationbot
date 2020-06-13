# Donation Tracker

Donation Tracker is the ultimate tool for managing donations and activity across your Clash of Clans clan or family.

As this is an educational repo, throughout this README I will attempt to explain *how* things work, as well as issues
I may have faced, *why* I do something how I do it, referring to applicable sections of the code where relevant.

Due to the dynamic nature of an open-source repository, any code-links I share will be hardcoded and may become stale as the bot progresses.


# 
### Interacting with the Clash of Clans API.

Very early on I realised that there was an obvious hole in how my bot was going to function. 
The clash of clans API is a basic JSON RESTful API and, while being functional, had many flaws and inconsistencies 
to just use the raw API.

I decided to develop [coc.py](https://github.com/mathsman5133/coc.py), a fully functional asynchronous wrapper for the API. 
Being asynchronous was important to me. In a bot-style environment where a constant connection is established and many tasks
can be completed at once, no asynchronous interaction with the clash API would've led to blocking: code that blocks the entire event loop, 
meaning that the bot cannot process other events, such as messages, during the time that the blocking code is running.

Another issue I faced is that this bot resolves around the idea of "events": someone does something in the game,
and the bot responds accordingly. The API provides no such functionality, and while a webhook or websocket connection would 
be nice, we have to work with what we have got.

Thus the idea of "events" in [coc.py](https://github.com/mathsman5133/coc.py) was born. The way these work is through constantly
polling the API, while caching recent results, to find a "difference" in the data. When the client detects a change, it dispatches 
an event, for example `on_clan_member_donation` - an event fired when someone's donations change. While being less than perfect, 
this new solution meant a *lot* of the background API processing was abstracted away behind the wrapper.

# 


1. Donation and Trophy Leaderboards:

    These are live-updating leaderboards that report you
    
    
     
I would prefer if you didn't run an instance of the bot, just invite the bot to your server.

Bot Invite: https://discordapp.com/oauth2/authorize?client_id=427301910291415051&scope=bot&permissions=388176
Support Server: https://discord.gg/ePt8y4V   