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
import logging
from typing import Union, Optional
import shlex

from cogs.utils.formatters import TabularData
from cogs.utils.converters import GlobalChannel
import asyncio
import io

log = logging.getLogger(__name__)


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

    @commands.command(hidden=True)
    async def eval(self, ctx, *, body: str):
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

    async def execute_sql(self, ctx, query: str):
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
            return f'```py\n{traceback.format_exc()}\n```', None
        else:
            return results, dt

    @commands.command(hidden=True)
    async def sql(self, ctx, *, query: str):
        """Run some SQL."""
        results, timer = await self.execute_sql(ctx, query)
        if not timer:
            return await self.safe_send(ctx, results)

        rows = len(results)
        if rows == 0:
            return await ctx.send(f'`{timer:.2f}ms: {results}`')

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```\n*Returned {rows} rows in {timer:.2f}ms*'
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
    async def sqlcsv(self, ctx, *, query: str):
        results, timer = await self.execute_sql(ctx, query)
        if not timer:
            return await self.safe_send(ctx, results)

        rows = len(results)
        if rows == 0:
            return await ctx.send(f'`{timer:.2f}ms: {results}`')

        csv = ""
        for i, row in enumerate(results):
            if i == 0:
                # headers
                csv += ''.join(f"{col}," for col in row.keys())
                csv += '\n'

            csv += ''.join(f"{r}," for r in row.values())
            csv += '\n'

        fmt = f'Returned {rows} rows in {timer:.2f}ms*'
        return await ctx.send(fmt, file=discord.File(filename="sql-query-results.csv", fp=io.BytesIO(csv.encode("utf-8"))))


def setup(bot):
    bot.add_cog(Admin(bot))
