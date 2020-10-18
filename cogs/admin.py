from discord.ext import commands
import asyncio
import traceback
import discord
import inspect
import textwrap
import importlib
from contextlib import redirect_stdout
import io
import itertools
import os
import re
import sys
import copy
import time
import subprocess
from typing import Union, Optional

from cogs.utils.formatters import TabularData
from cogs.utils.converters import GlobalChannel
import asyncio
import io


class HTMLImages:
    def __init__(self, players, title=None, image=None):
        self.players = players

        self.title = title or "Donation Leaderboard"
        self.image = image or "https://cdn.discordapp.com/attachments/641594147374891029/767306860306759680/dc0f83c3eba7fad4cbe8de3799708e93.jpg"

        self.html = ""

    def add_style(self):
        self.html += """
<!DOCTYPE html>
<html>
<head>
<style>
img {
  position: fixed;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  z-index:-1;
  opacity:0.9;
}
table {
  font-family: Lato, Helvetica, Arial, sans-serif;
  border-collapse: seperate;
  border-spacing: 0 12px;
  width: 100%;
  padding-bottom: 30px;
  padding-left: 30px;
  padding-right: 30px
}

td, th {
  text-align: left;
  font-size: 40px;
  padding: 10px;
  box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.19);
}

th {
  border: 1px solid #404040;
  background-color: rgba(185, 147, 108, 0.6);

}


tr:nth-child(even) {
  background-color: rgba(166, 179, 196, 0.8);
}
tr:nth-child(odd) {
  background-color: rgba(196, 186, 133, 0.8);
}

header {
  background:-webkit-gradient(linear,left bottom,left top,color-stop(20%,rgb(196, 183, 166)),color-stop(80%,rgb(220, 207, 186)));
  font-size: 60px;
  margin-left: auto;
  margin-right: auto;
  text-align: center;
  font-style: bold;
  font-weight: 200;
  letter-spacing: 1.5px;
  opacity: 1;
}
</style>
        """

    def add_body(self):
        self.html += "<body>"

    def add_title(self):
        self.html += f"<header>{self.title}</header>"

    def add_image(self):
        self.html += f'<img src="{self.image}" alt="Test"></img>'

    def add_table(self):
        to_add = "<table>"

        headers = ("#", "Player Name", "Dons", "Rec", "Ratio", "Trophies", "Gain", "Last On")
        to_add += "<tr>" + "".join(f"<th>{column}</th>" for column in headers) + "</tr>"

        for player in self.players:
            to_add += "<tr>" + "".join(f"<td>{cell}</td>" for cell in player) + "</tr>"

        to_add += "</table>"
        self.html += to_add

    def end_html(self):
        self.html += "</body></html>"

    def parse_players(self):
        self.players = [(i, p['player_name'], p['donations'], p['received'], round(p['donations'] / p['received'], 2),
                         p['trophies'], p['gain'], p['last_online']) for i, p in enumerate(self.players)]

    async def make(self):
        self.add_style()
        self.add_body()
        self.add_title()
        self.add_image()
        self.add_table()
        self.end_html()

        proc = await asyncio.create_subprocess_shell(
            'wkhtmltoimage - -', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=self.html.encode('utf-8'))
        b = io.BytesIO(stdout)
        b.seek(0)
        return b


# to expose to the eval command
import datetime
from collections import Counter


class PerformanceMocker:
    """A mock object that can also be used in await expressions."""

    def __init__(self):
        self.loop = asyncio.get_event_loop()

    def permissions_for(self, obj):
        # Lie and say we don't have permissions to embed
        # This makes it so pagination sessions just abruptly end on __init__
        # Most checks based on permission have a bypass for the owner anyway
        # So this lie will not affect the actual command invocation.
        perms = discord.Permissions.all()
        perms.administrator = False
        perms.embed_links = False
        perms.add_reactions = False
        return perms

    def __getattr__(self, attr):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __repr__(self):
        return '<PerformanceMocker>'

    def __await__(self):
        future = self.loop.create_future()
        future.set_result(self)
        return future.__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return self

    def __len__(self):
        return 0

    def __bool__(self):
        return False



class Admin(commands.Cog):
    """Admin-only commands that make the bot dynamic."""

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await self.bot.loop.run_in_executor(None, process.communicate)

        return [output.decode() for output in result]

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def get_syntax_error(self, e):
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

    async def safe_send(self, ctx, fmt):
        if len(fmt) > 8000:
            fp = io.BytesIO(fmt.encode('utf-8'))
            return await ctx.send('Too many results...', file=discord.File(fp, 'results.txt'))

        if len(fmt) < 2000:
            await ctx.send(fmt)
        else:
            coll = ""
            for line in fmt.splitlines(keepends=True):
                if len(coll) + len(line) > 2000:
                    # if collecting is going to be too long, send  what you have so far
                    await ctx.send(coll)
                    coll = ""
                coll += line
            await ctx.send(coll)

    @commands.command(hidden=True)
    async def loadapi(self, ctx, num: int = 20):
        tasks = []
        async def run(item, *args, **kwargs):
            for _ in range(num):
                try:
                    await item(*args, **kwargs)
                except:
                    continue

        client = self.bot.coc
        for call in (
            client.get_clan,
            client.get_members,
            client.get_warlog,
            client.get_clan_war,
            client.get_league_group,
            client.get_current_war,
        ):
            tasks.append(asyncio.ensure_future(run(call, "#G88CYQP")))
        
        for call in (
            client.search_locations,
            client.search_leagues,
            client.get_clan_labels,
            client.get_player_labels,
            client.get_location_clans,
            client.get_location_players,
            client.get_location_clans_versus,
            client.get_location_players_versus,
        ):
            tasks.append(asyncio.ensure_future(run(call)))

        tasks.append(asyncio.ensure_future(run(client.get_player, "#JY9J2Y99")))
        tasks.append(asyncio.ensure_future(run(client.get_clan, "Reddit")))
        await asyncio.gather(*tasks)
        await ctx.send('\N{OK HAND SIGN}')

    @commands.command(hidden=True)
    async def load(self, ctx, *, module):
        """Loads a module."""
        try:
            self.bot.load_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.command(hidden=True)
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.group(name='reload', hidden=True, invoke_without_command=True)
    async def _reload(self, ctx, *, module):
        """Reloads a module."""
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    _GIT_PULL_REGEX = re.compile(r'\s*(?P<filename>.+?)\s*\|\s*[0-9]+\s*[+-]+')

    def find_modules_from_git(self, output):
        files = self._GIT_PULL_REGEX.findall(output)
        ret = []
        for file in files:
            root, ext = os.path.splitext(file)
            if ext != '.py':
                continue

            if root.startswith('cogs/'):
                # A submodule is a directory inside the main cog directory for
                # my purposes
                ret.append((root.count('/') - 1, root.replace('/', '.')))

        # For reload order, the submodules should be reloaded first
        ret.sort(reverse=True)
        return ret

    def reload_or_load_extension(self, module):
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            self.bot.load_extension(module)

    @_reload.command(name='all', hidden=True)
    async def _reload_all(self, ctx):
        """Reloads all modules, while pulling from git."""

        async with ctx.typing():
            stdout, stderr = await self.run_process('git pull')

        # progress and stuff is redirected to stderr in git pull
        # however, things like "fast forward" and files
        # along with the text "already up-to-date" are in stdout

        if stdout.startswith('Already up-to-date.'):
            return await ctx.send(stdout)

        modules = self.find_modules_from_git(stdout)
        mods_text = '\n'.join(f'{index}. `{module}`' for index, (_, module) in enumerate(modules, start=1))
        prompt_text = f'This will update the following modules, are you sure?\n{mods_text}'
        confirm = await ctx.prompt(prompt_text, reacquire=False)
        if not confirm:
            return await ctx.send('Aborting.')

        statuses = []
        for is_submodule, module in modules:
            if is_submodule:
                try:
                    actual_module = sys.modules[module]
                except KeyError:
                    statuses.append((ctx.tick(None), module))
                else:
                    try:
                        importlib.reload(actual_module)
                    except Exception as e:
                        statuses.append((ctx.tick(False), module))
                    else:
                        statuses.append((ctx.tick(True), module))
            else:
                try:
                    self.reload_or_load_extension(module)
                except commands.ExtensionError:
                    statuses.append((ctx.tick(False), module))
                else:
                    statuses.append((ctx.tick(True), module))

        await ctx.send('\n'.join(f'{status}: `{module}`' for status, module in statuses))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def commandstats(self, ctx, limit=20):
        """Shows command stats.
        Use a negative number for bottom instead of top.
        This is only for the current session.
        """
        counter = self.bot.command_stats
        width = len(max(counter, key=len))
        total = sum(counter.values())

        if limit > 0:
            common = counter.most_common(limit)
        else:
            common = counter.most_common()[limit:]

        output = '\n'.join(f'{k:<{width}}: {c}' for k, c in common)

        await ctx.send(f'```\n{output}\n```')

    @commands.command(pass_context=True, hidden=True, name='eval')
    async def _eval(self, ctx, *, body: str):
        """Evaluates a code"""

        env = {
            'bot': self.bot,
            'coc': self.bot.coc,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            return await self.safe_send(ctx, fmt)
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await self.safe_send(ctx, f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await self.safe_send(ctx, f'```py\n{value}{ret}\n```')

    @commands.command(pass_context=True, hidden=True)
    async def repl(self, ctx):
        """Launches an interactive REPL session."""
        variables = {
            'ctx': ctx,
            'bot': self.bot,
            'message': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author,
            '_': None,
        }

        if ctx.channel.id in self.sessions:
            await ctx.send('Already running a REPL session in this channel. Exit it with `quit`.')
            return

        self.sessions.add(ctx.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        def check(m):
            return m.author.id == ctx.author.id and \
                   m.channel.id == ctx.channel.id and \
                   m.content.startswith('`')

        while True:
            try:
                response = await self.bot.wait_for('message', check=check, timeout=10.0 * 60.0)
            except asyncio.TimeoutError:
                await ctx.send('Exiting REPL session.')
                self.sessions.remove(ctx.channel.id)
                break

            cleaned = self.cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self.sessions.remove(ctx.channel.id)
                return

            executor = exec
            if cleaned.count('\n') == 0:
                # single statement, potentially 'eval'
                try:
                    code = compile(cleaned, '<repl session>', 'eval')
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is exec:
                try:
                    code = compile(cleaned, '<repl session>', 'exec')
                except SyntaxError as e:
                    await ctx.send(self.get_syntax_error(e))
                    continue

            variables['message'] = response

            fmt = None
            stdout = io.StringIO()

            try:
                with redirect_stdout(stdout):
                    result = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception as e:
                value = stdout.getvalue()
                fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f'```py\n{value}{result}\n```'
                    variables['_'] = result
                elif value:
                    fmt = f'```py\n{value}\n```'

            try:
                if fmt is not None:
                    if len(fmt) > 2000:
                        await ctx.send('Content too big to be printed.')
                    else:
                        await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send(f'Unexpected error: `{e}`')

    @commands.command(hidden=True)
    async def sql(self, ctx, *, query: str):
        """Run some SQL."""
        # the imports are here because I imagine some people would want to use
        # this cog as a base for their other cog, and since this one is kinda
        # odd and unnecessary for most people, I will make it easy to remove
        # for those people.
        query = self.cleanup_code(query)

        is_multistatement = query.count(';') > 1
        if is_multistatement:
            # fetch does not support multiple statements
            strategy = ctx.db.execute
        else:
            strategy = ctx.db.fetch

        try:
            start = time.perf_counter()
            results = await strategy(query)
            dt = (time.perf_counter() - start) * 1000.0
        except Exception:
            return await ctx.send(f'```py\n{traceback.format_exc()}\n```')

        rows = len(results)
        if is_multistatement or rows == 0:
            return await ctx.send(f'`{dt:.2f}ms: {results}`')

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```\n*Returned {rows} rows in {dt:.2f}ms*'
        return await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    async def sqlite(self, ctx, *, query: str):
        """Run some SQLite."""
        # the imports are here because I imagine some people would want to use
        # this cog as a base for their other cog, and since this one is kinda
        # odd and unnecessary for most people, I will make it easy to remove
        # for those people.
        query = self.cleanup_code(query)

        try:
            start = time.perf_counter()
            cursor = self.bot.sqlite.execute(query)
            results = cursor.fetchall()
            dt = (time.perf_counter() - start) * 1000.0
        except Exception:
            return await ctx.send(f'```py\n{traceback.format_exc()}\n```')

        rows = len(results)
        if rows == 0:
            return await ctx.send(f'`{dt:.2f}ms: {results}`')

        headers = [f"header {i}" for i in range(len(results[0]))]
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```\n*Returned {rows} rows in {dt:.2f}ms*'
        return await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    async def sql_table(self, ctx, *, table_name: str):
        """Runs a query describing the table schema."""
        query = """SELECT column_name, data_type, column_default, is_nullable
                   FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE table_name = $1
                """

        results = await ctx.db.fetch(query, table_name)

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```'
        return await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sql_tables(self, ctx):
        query = """SELECT table_name
                   FROM information_schema.tables
                   WHERE table_schema='public'
                   AND table_type='BASE TABLE';
                """
        results = await ctx.db.fetch(query)

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```'
        return await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sql_constraints(self, ctx, *, table: str):
        query = """SELECT conname
                   FROM pg_constraint
                   WHERE conrelid =
                            (SELECT oid
                             FROM pg_class
                             WHERE relname LIKE $1
                             );
                """
        results = await ctx.db.fetch(query, table)

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```'
        await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    async def sql_indexes(self, ctx, *, table: str):
        query = """SELECT tablename, indexname FROM pg_indexes WHERE tablename = $1;"""
        results = await ctx.db.fetch(query, table)

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```'
        await self.safe_send(ctx, fmt)

    @commands.command(hidden=True)
    async def sudo(self, ctx, channel: Optional[GlobalChannel], who: discord.User, *, command: str):
        """Run a command as another user optionally in another channel."""
        msg = copy.copy(ctx.message)
        channel = channel or ctx.channel
        msg.channel = channel
        msg.author = channel.guild.get_member(who.id) or who
        msg.content = ctx.prefix + command
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        new_ctx._db = ctx._db
        await self.bot.invoke(new_ctx)

    @commands.command(hidden=True)
    async def do(self, ctx, times: int, *, command):
        """Repeats a command a specified number of times."""
        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        new_ctx._db = ctx._db

        for i in range(times):
            await new_ctx.reinvoke()

    @commands.command(hidden=True)
    async def sh(self, ctx, *, command):
        """Runs a shell command."""
        from cogs.utils.paginator import TextPages

        async with ctx.typing():
            stdout, stderr = await self.run_process(command)

        if stderr:
            text = f'stdout:\n{stdout}\nstderr:\n{stderr}'
        else:
            text = stdout

        try:
            pages = TextPages(ctx, text)
            await pages.paginate()
        except Exception as e:
            await ctx.send(str(e))

    @commands.command(hidden=True)
    async def perf(self, ctx, *, command):
        """Checks the timing of a command, attempting to suppress HTTP and DB calls."""

        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + command

        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        new_ctx._db = PerformanceMocker()

        # Intercepts the Messageable interface a bit
        new_ctx._state = PerformanceMocker()
        new_ctx.channel = PerformanceMocker()

        if new_ctx.command is None:
            return await ctx.send('No command found')

        start = time.perf_counter()
        try:
            await new_ctx.command.invoke(new_ctx)
        except commands.CommandError:
            end = time.perf_counter()
            success = False
            try:
                await self.safe_send(ctx, f'```py\n{traceback.format_exc()}\n```')
            except discord.HTTPException:
                pass
        else:
            end = time.perf_counter()
            success = True

        await ctx.send(f'Status: {ctx.tick(success)} Time: {(end - start) * 1000:.2f}ms')

    @commands.command()
    async def rb(self, ctx):
        query = """
        SELECT DISTINCT player_name,
                                        donations,
                                        received,
                                        trophies,
                                        now() - last_updated AS "last_online",
                                        donations / NULLIF(received, 0) AS "ratio",
                                        trophies - start_trophies AS "gain"
                       FROM players
                       INNER JOIN clans
                       ON clans.clan_tag = players.clan_tag
                       WHERE clans.channel_id = (SELECT channel_id FROM clans OFFSET random() LIMIT 1)
                       AND season_id = 16
                       ORDER BY donations DESC
                       NULLS LAST
                       LIMIT 20
                       
                       """
        f = await ctx.db.fetch(query)
        players = [(i, p['player_name'], p['donations'], p['received'], round(p['donations'] / p['received'], 2), p['trophies'], p['gain'], p['last_online']) for i, p in enumerate(f)]

        im = await HTMLImages(players=players).make()
        await ctx.send(file=discord.File(im, filename="donationboard.png"))

def setup(bot):
    bot.add_cog(Admin(bot))
