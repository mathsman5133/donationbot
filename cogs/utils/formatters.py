from datetime import datetime
from discord.utils import _string_width, escape_markdown

from cogs.utils.paginator import Pages


def readable_time(delta_seconds):
    hours, remainder = divmod(int(delta_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days:
        fmt = '{d}d {h}h {m}m {s}s ago'
    elif hours:
        fmt = '{h}h {m}m {s}s ago'
    else:
        fmt = '{m}m {s}s ago'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


class TabularData:
    def __init__(self):
        self._widths = []
        self._columns = []
        self._rows = []

    def set_columns(self, columns):
        self._columns = columns
        self._widths = [_string_width(c) + 2 for c in columns]

    def add_row(self, row):
        rows = [str(r) for r in row]
        self._rows.append(rows)
        for index, element in enumerate(rows):
            width = len(element) + 2
            if width > self._widths[index]:
                self._widths[index] = width

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def clear_rows(self):
        self._rows = []

    def render(self):
        """Renders a table in rST format.
        Example:
        +-------+-----+
        | Name  | Age |
        +-------+-----+
        | Alice | 24  |
        |  Bob  | 19  |
        +-------+-----+
        """

        sep = '+'.join('-' * w for w in self._widths)
        sep = f'+{sep}+'

        to_draw = [sep]

        def get_entry(d):
            elem = '|'.join(f'{e:^{self._widths[i]}}' for i, e in enumerate(d))
            return f'|{elem}|'

        to_draw.append(get_entry(self._columns))
        to_draw.append(sep)

        for row in self._rows:
            to_draw.append(get_entry(row))

        to_draw.append(sep)
        return '\n'.join(to_draw)


class TablePaginator(Pages):
    def __init__(self, ctx, data, title='', page_count=1, rows_per_table=20, mobile=False):
        super().__init__(ctx, entries=[i for i in range(page_count)], per_page=1)
        self.table = TabularData()
        self.data = data
        self.mobile = mobile
        self.entries = [None for _ in range(page_count)]
        self.rows_per_table = rows_per_table
        self.title = escape_markdown(title)
        self.message = None

    async def get_page(self, page):
        entry = self.entries[page - 1]
        print(self.entries)
        if entry:
            print('ok')
            return entry

        if not self.message:
            self.message = await self.channel.send('Loading...')
        else:
            await self.message.edit(content='Loading...', embed=None)

        entry = await self.prepare_entry(page)
        self.entries[page - 1] = entry
        print(entry)
        return self.entries[page - 1]

    async def prepare_entry(self, page):
        print(page)
        self.table.clear_rows()
        print(page)
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        print(data)
        for n in data:
            self.table.add_row(n)
        print(self.table.render())

        return f'{self.title}```\n{self.table.render()}\n```'

    async def get_content(self, entries, page, *, first=False):
        if self.mobile:
            return None
        if first and self.paginating:
            return f'{entries}\nConfused? React with \N{INFORMATION SOURCE} for more info.'

        return entries

    async def get_embed(self, entries, page, *, first=False):
        if not self.mobile:
            return None

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

        self.embed.description = entries
        if self.paginating and first:
            self.embed.description += 'Confused? React with \N{INFORMATION SOURCE} for more info.'
        return self.embed

    async def show_page(self, page, *, first=False):
        print(page, first)
        self.current_page = page
        entries = await self.get_page(page)
        print(entries)
        content = await self.get_content(entries, page, first=first)
        print(content)
        embed = await self.get_embed(entries, page, first=first)
        print(embed)
        print('got')
        if not self.paginating:
            return await self.channel.send(content=content, embed=embed)

        await self.message.edit(content=content, embed=embed)

        if not first:
            return

        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            await self.message.add_reaction(reaction)


class DonationsPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table)
        self.table.set_columns(['IGN', 'Don', "Rec'd", 'Tag', 'Claimed By'])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[0]: n for n in data}

        tags = [n[0] for n in data]
        async for player in self.bot.coc.get_players(tags):
            player_data = data_by_tag[player.tag]
            name = str(self.bot.get_user(player_data[3]))
            if len(name) > 20:
                name = name[:20] + '..'
            self.table.add_row([player.name, player_data[1], player_data[2], player.tag, name])

        return f'{self.title}\n```\n{self.table.render()}\n```'


class EventsPaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table)
        self.table.set_columns(['IGN', 'Don', "Rec'd", 'Time', 'Clan'])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[0]: n for n in data}
        time = datetime.utcnow()

        tags = (n[0] for n in data)
        async for player in self.bot.coc.get_players(tags):
            player_data = data_by_tag[player.tag]

            delta = time - player_data[3]
            if not player.clan:
                clan_name = 'None'
            else:
                clan_name = player.clan.name

            self.table.add_row([player.name,
                                player_data[1],
                                player_data[2],
                                readable_time(delta.total_seconds()),
                                clan_name
                                ]
                                )
        return f'{self.title}```\n{self.table.render()}\n```'


class MobilePaginator(TablePaginator):
    def __init__(self, ctx, data, title, page_count=1, rows_per_table=20):
        super().__init__(ctx, data, title=title, page_count=page_count,
                         rows_per_table=rows_per_table, mobile=True)
        self.embed.title = title
        self.table.set_columns(['IGN', 'Don', "Rec'd"])

    async def prepare_entry(self, page):
        self.table.clear_rows()
        base = (page - 1) * self.rows_per_table
        data = self.data[base:base + self.rows_per_table]
        data_by_tag = {n[0]: n for n in data}

        tags = (n[0] for n in data)
        async for player in self.bot.coc.get_players(tags):
            player_data = data_by_tag[player.tag]
            self.table.add_row([player.name, player_data[1], player_data[2]])  # IGN, don, rec

        return f'```\n{self.table.render()}\n```'
