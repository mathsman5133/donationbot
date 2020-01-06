import asyncio
import discord
import inspect
import textwrap

from datetime import datetime

from discord.ext.commands import Paginator as CommandPaginator

from cogs.utils.emoji_lookup import misc
from cogs.utils.formatters import CLYTable, get_render_type, events_time, readable_time


class CannotPaginate(Exception):
    pass


class Pages:
    """Implements a paginator that queries the user for the
    pagination interface.

    Pages are 1-index based, not 0-index based.

    If the user does not reply within 2 minutes then the pagination
    interface exits automatically.

    Parameters
    ------------
    ctx: Context
        The context of the command.
    entries: List[str]
        A list of entries to paginate.
    per_page: int
        How many entries show up per page.
    show_entry_count: bool
        Whether to show an entry count in the footer.

    Attributes
    -----------
    embed: discord.Embed
        The embed object that is being used to send pagination info.
        Feel free to modify this externally. Only the description,
        footer fields, and colour are internally modified.
    permissions: discord.Permissions
        Our permissions for the channel.
    """
    def __init__(self, ctx, *, entries, per_page=12, show_entry_count=True):
        self.bot = ctx.bot
        self.entries = entries
        self.message = ctx.message
        self.channel = ctx.channel
        self.author = ctx.author
        self.per_page = per_page
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        self.embed = discord.Embed(colour=discord.Colour.blurple())
        self.paginating = len(entries) > per_page
        self.show_entry_count = show_entry_count
        self.reaction_emojis = [
            ('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
            ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
            ('\N{INPUT SYMBOL FOR NUMBERS}', self.numbered_page ),
            ('\N{WHITE QUESTION MARK ORNAMENT}', self.show_help),
        ]

        if ctx.guild is not None:
            self.permissions = self.channel.permissions_for(ctx.guild.me)
        else:
            self.permissions = self.channel.permissions_for(ctx.bot.user)

        if not self.permissions.embed_links:
            raise CannotPaginate('Bot does not have embed links permission.')

        if not self.permissions.send_messages:
            raise CannotPaginate('Bot cannot send messages.')

        if self.paginating:
            # verify we can actually use the pagination session
            if not self.permissions.add_reactions:
                raise CannotPaginate('Bot does not have add reactions permission.')

            if not self.permissions.read_message_history:
                raise CannotPaginate('Bot does not have Read Message History permission.')

    def get_page(self, page):
        base = (page - 1) * self.per_page
        return self.entries[base:base + self.per_page]

    async def get_content(self, entries, page, *, first=False):
        return None

    async def get_embed(self, entries, page, *, first=False):
        self.prepare_embed(entries, page, first=first)
        return self.embed

    def prepare_embed(self, entries, page, *, first=False):
        p = []
        for index, entry in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            p.append(f'{entry}')

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

        if self.paginating and first:
            p.append('')
            p.append('Confused? React with \N{INFORMATION SOURCE} for more info.')

        self.embed.description = '\n'.join(p)

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = self.get_page(page)
        content = await self.get_content(entries, page, first=first)
        embed = await self.get_embed(entries, page, first=first)

        if not self.paginating:
            return await self.channel.send(content=content, embed=embed)

        if not first:
            await self.message.edit(content=content, embed=embed)
            return

        self.message = await self.channel.send(content=content, embed=embed)
        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            await self.message.add_reaction(reaction)

    async def checked_show_page(self, page):
        if page != 0 and page <= self.maximum_pages:
            await self.show_page(page)

    async def first_page(self):
        """goes to the first page"""
        await self.show_page(1)

    async def last_page(self):
        """goes to the last page"""
        await self.show_page(self.maximum_pages)

    async def next_page(self):
        """goes to the next page"""
        await self.checked_show_page(self.current_page + 1)

    async def previous_page(self):
        """goes to the previous page"""
        await self.checked_show_page(self.current_page - 1)

    async def show_current_page(self):
        if self.paginating:
            await self.show_page(self.current_page)

    async def numbered_page(self):
        """lets you type a page number to go to"""
        to_delete = []
        to_delete.append(await self.channel.send('What page do you want to go to?'))

        def message_check(m):
            return m.author == self.author and \
                   self.channel == m.channel and \
                   m.content.isdigit()

        try:
            msg = await self.bot.wait_for('message', check=message_check, timeout=30.0)
        except asyncio.TimeoutError:
            to_delete.append(await self.channel.send('Took too long.'))
            await asyncio.sleep(5)
        else:
            page = int(msg.content)
            to_delete.append(msg)
            if page != 0 and page <= self.maximum_pages:
                await self.show_page(page)
            else:
                to_delete.append(await self.channel.send(f'Invalid page given. ({page}/{self.maximum_pages})'))
                await asyncio.sleep(5)

        try:
            await self.channel.delete_messages(to_delete)
        except Exception:
            pass

    async def show_help(self):
        """shows this message"""
        messages = ['Welcome to the interactive paginator!\n']
        messages.append('This interactively allows you to see pages of text by navigating with '
                        'reactions. They are as follows:\n')

        for (emoji, func) in self.reaction_emojis:
            messages.append(f'{emoji} {func.__doc__}')

        embed = self.embed.copy() if self.embed else discord.Embed(colour=self.bot.colour)
        embed.clear_fields()
        embed.description = '\n'.join(messages)
        embed.set_footer(text=f'We were on page {self.current_page} before this message.')
        await self.message.edit(content=None, embed=embed)

        async def go_back_to_current_page():
            await asyncio.sleep(60.0)
            await self.show_current_page()

        self.bot.loop.create_task(go_back_to_current_page())

    async def stop_pages(self):
        """stops the interactive pagination session"""
        await self.message.delete()
        self.paginating = False

    def react_check(self, reaction, user):
        if user is None or user.id != self.author.id:
            return False

        if reaction.message.id != self.message.id:
            return False

        for (emoji, func) in self.reaction_emojis:
            if reaction.emoji == emoji:
                self.match = func
                return True
        return False

    async def callback(self):
        pass

    async def paginate(self):
        """Actually paginate the entries and run the interactive loop if necessary."""
        first_page = self.show_page(1, first=True)
        if not self.paginating:
            await first_page
        else:
            # allow us to react to reactions right away if we're paginating
            self.bot.loop.create_task(first_page)

        while self.paginating:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', check=self.react_check, timeout=120.0)
            except asyncio.TimeoutError:
                self.paginating = False
                try:
                    await self.message.clear_reactions()
                except:
                    pass
                finally:
                    break

            try:
                await self.message.remove_reaction(reaction, user)
            except:
                pass # can't remove it so don't bother doing so

            await self.match()

        await self.callback()
        return

class FieldPages(Pages):
    """Similar to Pages except entries should be a list of
    tuples having (key, value) to show as embed fields instead.
    """

    def prepare_embed(self, entries, page, *, first=False):
        self.embed.clear_fields()
        self.embed.description = discord.Embed.Empty

        for key, value in entries:
            self.embed.add_field(name=key, value=value, inline=False)

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)


class EmbedPages(Pages):
    """Class for paginating a list of embed objects."""
    def prepare_embed(self, entries, page, *, first=False):
        self.embed = entries[0]

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

class TextPages(Pages):
    """Uses a commands.Paginator internally to paginate some text."""

    def __init__(self, ctx, text, *, prefix='```', suffix='```', max_size=2000):
        paginator = CommandPaginator(prefix=prefix, suffix=suffix, max_size=max_size - 200)
        for line in text.split('\n'):
            paginator.add_line(line)

        super().__init__(ctx, entries=paginator.pages, per_page=1, show_entry_count=False)

    def get_page(self, page):
        return self.entries[page - 1]

    async def get_embed(self, entries, page, *, first=False):
        return None

    async def get_content(self, entry, page, *, first=False):
        if self.maximum_pages > 1:
            return f'{entry}\nPage {page}/{self.maximum_pages}'
        return entry


class MessagePaginator(Pages):
    def __init__(self, ctx, *, entries, per_page=12, show_entry_count=True, title=None):
        """A paginator for paging regular message rather than embeds."""
        super().__init__(ctx, entries=entries, per_page=per_page, show_entry_count=show_entry_count)
        self.embed = None
        self.title = title

    async def get_embed(self, entries, page, *, first=False):
        return None

    async def get_content(self, entries, page, *, first=False):
        p = []
        if self.title:
            p.append(self.title)

        for index, entry in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            p.append(f'{entry}')

        if self.paginating and first:
            p.append('')
            p.append('Confused? React with \N{INFORMATION SOURCE} for more info.')

        return '\n'.join(p)



class TablePaginator(Pages):
    def __init__(self, ctx, data, title=None, page_count=1, rows_per_table=20):
        super().__init__(ctx, entries=[i for i in range(page_count)], per_page=1)
        self.table = CLYTable()
        self.data = [(i, v) for (i, v) in enumerate(data)]
        self.entries = [None for _ in range(page_count)]
        self.rows_per_table = rows_per_table
        self.title = title
        self.message = None
        self.ctx = ctx
        if getattr(ctx, 'config', None):
            self.icon_url = ctx.config.icon_url or ctx.guild.icon_url
            self.title = ctx.config.title or title
        else:
            self.icon_url = ctx.guild.icon_url

    async def get_page(self, page):
        entry = self.entries[page - 1]
        if entry:
            return entry

        if not self.message:
            self.message = await self.channel.send('Loading...')
        else:
            await self.message.edit(content='Loading...', embed=None)

        entry = await self.prepare_entry(page)
        self.entries[page - 1] = entry
        return self.entries[page - 1]

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        for n in data:
            self.table.add_row(n)

        render = get_render_type(self.ctx.config, self.table)
        return render()

    async def get_embed(self, entries, page, *, first=False):
        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

        self.embed.description = entries

        self.embed.set_author(
            name=textwrap.shorten(self.title, width=240, placeholder='...'),
            icon_url=self.icon_url
        )

        return self.embed

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = await self.get_page(page)
        embed = await self.get_embed(entries, page, first=first)

        if not self.paginating:
            print('not paginating')
            return await self.message.edit(content=None, embed=embed)

        await self.message.edit(content=None, embed=embed)

        if not first:
            return

        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            await self.message.add_reaction(reaction)

class SeasonStatsPaginator(Pages):
    def __init__(self, ctx, entries):
        super().__init__(ctx, entries=entries, per_page=1)

    async def get_embed(self, entries, page, *, first=False):
        return self.entries[page - 1]


class BoardPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table)

    def create_row(self, player, data):
        player_data = data[player.tag]

        if self.ctx.config.type == 'donation':
            if self.ctx.config.render == 1:
                row = [player_data[0], player_data[1]['donations'], player_data[1]['received'], player.name]
            else:
                row = [player_data[0], player_data[1]['donations'], player.name]
        else:
            if self.ctx.config.render == 1:
                row = [player_data[0], player_data[1]['trophies'], player_data[1][2], player.name]
            else:
                row = [player_data[0], player_data[1]['trophies'], player.name]

        self.table.add_row(row)

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        render = get_render_type(self.ctx.config, self.table)
        return render()


class TrophyPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table)

    def create_row(self, player, data):
        player_data = data[player.tag]
        row = [player_data[0], player_data[1][1], player_data[1][2], player.name]
        self.table.add_row(row)

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        render = get_render_type(self.ctx.config, self.table)
        return render()


class LogsPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table)

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        for player_data in data:
            if self.ctx.config.type == 'donation':
                player_data = player_data[1]
                time = events_time((datetime.utcnow() - player_data[3]).total_seconds())
                row = [
                    misc['donated'] if player_data[1] else misc['received'],
                    player_data[1] if player_data[1] else player_data[2],
                    player_data[4],
                    time
                    ]
            else:
                player_data = player_data[1]
                time = events_time((datetime.utcnow() - player_data[3]).total_seconds())
                row = [
                    misc['trophygreen'] if player_data[1] > 0 else misc['trophyred'],
                    player_data[1],
                    player_data[4],
                    time
                ]
            self.table.add_row(row)

        if self.ctx.config.type == 'donation':
            return f"{self.table.donation_log_command()}\nKey: {misc['donated']} - Donated," \
                   f" {misc['received']} - Received"
        else:
            return f"{self.table.trophy_log_command()}\nKey: {misc['trophygreen']} - Trophies Gained," \
                   f" {misc['trophyred']} - Trophies Lost"


class StatsAttacksPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20, key=''):
        super().__init__(
            ctx, data, title=title, page_count=page_count, rows_per_table=rows_per_table
        )
        self.key = key

    def create_row(self, player, data):
        player_data = data[player.tag]
        self.table.add_row([player_data[0], player_data[1]['attacks'], player_data[1]['trophies'], player.name])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        return self.table.trophyboard_attacks() + self.key


class StatsDefensesPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20, key=''):
        super().__init__(
            ctx, data, title=title, page_count=page_count, rows_per_table=rows_per_table
        )
        self.key = key

    def create_row(self, player, data):
        player_data = data[player.tag]
        self.table.add_row([player_data[0], player_data[1]['defenses'], player_data[1]['trophies'], player.name])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        return self.table.trophyboard_defenses() + self.key


class StatsGainsPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20, key=''):
        super().__init__(
            ctx, data, title=title, page_count=page_count, rows_per_table=rows_per_table
        )
        self.key = key

    def create_row(self, player, data):
        player_data = data[player.tag]
        self.table.add_row([player_data[0], player_data[1]['gain'], player_data[1]['trophies'], player.name])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        return self.table.trophyboard_gain() + self.key


class StatsDonorsPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20, key=''):
        super().__init__(
            ctx, data, title=title, page_count=page_count, rows_per_table=rows_per_table
        )
        self.key = key

    def create_row(self, player, data):
        player_data = data[player.tag]
        self.table.add_row([player_data[0], player_data[1]['donations'], player.name])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player, data_by_tag)

        return self.table.donationboard_2() + self.key


class LastOnlinePaginator(TablePaginator):
    def create_row(self, name, player_data):
        since = player_data[1]['since'].total_seconds()
        self.table.add_row([player_data[0], name, readable_time(since)[:-3]])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[1]['player_tag']: n for n in data}

        tags = [n[1]['player_tag'] for n in data]
        async for player in self.bot.coc.get_players(tags):
            self.create_row(player.name, data_by_tag[player.tag])

        return self.table.last_online()
