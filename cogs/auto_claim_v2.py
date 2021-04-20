import asyncio
import logging

import discord

from discord.ext import commands
from fuzzywuzzy import process

from cogs.utils.emoji_lookup import misc


log = logging.getLogger()

TICK = misc['greentick']
CROSS = misc['redtick']
SLASH = misc['greytick']


class AutoClaim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running_commands = {}

    async def get_or_fetch_member(self, guild, member_id):
        member = guild.get_member(member_id)
        if member is not None:
            return member

        shard = self.bot.get_shard(guild.shard_id)
        if shard.is_ws_ratelimited():
            try:
                member = await guild.fetch_member(member_id)
            except discord.HTTPException:
                return None
            else:
                return member

        members = await guild.query_members(limit=1, user_ids=[member_id], cache=True)
        if not members:
            return None
        return members[0]

    async def run_autoclaim_task(self, channel, me, author_id):
        try:
            await channel.guild.chunk(cache=True)
        except Exception as exc:
            log.exception("Failed to chunk members for guild %s", channel.guild.id, exc_info=exc)
            return await channel.send(
                "I'm sorry, but something went wrong and I couldn't find any members in this channel. "
                "Please try again later."
            )
        else:
            members = channel.members
            display_names = [member.display_name for member in members]
            lookup = {member.display_name: member for member in members}

        query = """SELECT DISTINCT player_name, player_tag, user_id
                   FROM players 
                   INNER JOIN clans 
                   ON clans.clan_tag = players.clan_tag 
                   OR players.fake_clan_tag = clans.clan_tag
                   WHERE clans.channel_id = $1
                   AND players.season_id =$2
                   """
        fetch = await self.bot.pool.fetch(query, channel.id, await self.bot.seasonconfig.get_season_id())
        links = {tag: user_id for tag, user_id in await self.bot.links.get_links(*(row['player_tag'] for row in fetch))}

        can_delete_messages = channel.permissions_for(me).manage_messages

        def check(message):
            return message.channel == channel and message.author.id == author_id

        batch_to_send = ""

        for row in fetch:
            tag, name = row['player_tag'], row['player_name']

            link = links.get(tag)
            if link:
                user = await self.get_or_fetch_member(channel.guild, link)
                fmt = f"{TICK} {name} ({tag}) has already been linked to {user.mention}.\n"
                if len(batch_to_send) + len(fmt) > 2000:
                    await channel.send(batch_to_send)
                    batch_to_send = fmt
                else:
                    batch_to_send += fmt

                continue

            else:
                if batch_to_send:
                    await channel.send(batch_to_send)

            match = process.extractOne(name, display_names)
            if match:
                member = lookup[match[0]]
                msg = await channel.send(
                    f"I want to link {name} ({tag}) to {member.mention} ({match[1]}% match). "
                    f"\nIf this is correct, type `yes` or `y`. "
                    f"\nIf not, mention the member you want to add them to, i.e. <@{self.bot.user.id}>."
                    f"\nType `skip` or `s` to skip.",
                )
            else:
                msg = await channel.send(
                    f"I didn't find a matching member for {name} ({tag}).\n"
                    f"Please @mention the person you wish to add to this player, or type `s` or `skip` to skip."
                )

            try:
                response = await self.bot.wait_for('message', timeout=60.0, check=check)
            except asyncio.TimeoutError:
                await channel.send(f"{CROSS} I'm sorry, you took too long. Please try again later.")
                del self.running_commands[channel.id]
                return

            content = response.clean_content.strip()

            if match and content in ("yes", "y") or "yes" in content:
                await self.bot.links.add_link(tag, member.id)
                await msg.edit(f"{TICK} {name} ({tag}) has been linked to {member.mention}.")

            elif content in ("skip", "s") or "skip" in content:
                await msg.edit(f"{SLASH} Skipping {name} ({tag}).")

            elif response.mentions:
                member = response.mentions[0]
                await self.bot.links.add_link(tag, member.id)
                await msg.edit(f"{TICK} {name} ({tag}) has been linked to {member.mention}.")

            else:
                await msg.edit(f"{SLASH} Invalid response, skipping {name} ({tag}).")

            if can_delete_messages:
                try:
                    await response.delete()
                except discord.Forbidden:
                    can_delete_messages = False
                except:
                    pass

        await channel.send(f"{TICK} Thank you, autoclaim has finished.")

    @commands.group(invoke_without_command=True)
    async def autoclaim(self, ctx):
        pass

    @autoclaim.command()
    async def start(self, ctx):
        try:
            self.running_commands[ctx.channel.id]
        except KeyError:
            task = asyncio.create_task(self.run_autoclaim_task(ctx.channel, ctx.me, ctx.author.id))
            await ctx.send(
                "Welcome to AutoClaim. "
                "I will walk you through an interactive linking of all the players in the clans added to this channel."
                "\nPlease wait while I get started."
            )
            await ctx.trigger_typing()
            self.running_commands[ctx.channel.id] = task
            await task
        else:
            return await ctx.send(f"{CROSS} There is already an active autoclaim command runnning.")

    @autoclaim.command()
    async def cancel(self, ctx):
        try:
            task = self.running_commands[ctx.channel.id]
        except KeyError:
            return await ctx.send(f"{CROSS} There is no active autoclaim command to cancel.")
        else:
            task.cancel()
            return await ctx.send(f"{TICK} Autoclaim command cancelled. Thank you.")


def setup(bot):
    bot.add_cog(AutoClaim(bot))
