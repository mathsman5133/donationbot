from datetime import datetime
from discord.utils import _string_width
from cogs.utils.paginator import Pages
from cogs.utils.emoji_lookup import number_emojis, misc


def get_render_type(config, table):
    if config.type == 'donation':
        if config.render == 1:
            render = table.donationboard_1
        else:
            render = table.donationboard_2
    else:
        if config.render == 1:
            render = table.trophyboard_1
        else:
            render = table.donationboard_2

    return render


def clean_name(name):
    if len(name) > 15:
        name = name[:15] + '..'
    return name


def readable_time(delta_seconds):
    hours, remainder = divmod(int(delta_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days:
        fmt = '{d}d {h}h {m}m {s}s'
    elif hours:
        fmt = '{h}h {m}m {s}s'
    else:
        fmt = '{m}m {s}s'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


def events_time(delta_seconds):
    hours, remainder = divmod(int(delta_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days}days"
    if hours > 0:
        return f"{hours}hr"
    if minutes > 0:
        return f"{minutes}min"
    return f"{seconds}sec"


def format_donation_log_message(player, clan_name):
    if player.donations:
        emoji = misc['donated']
        emoji2 = misc['online']
        if player.donations <= 100:
            number = number_emojis[player.donations]
        else:
            number = str(player.donations)
    else:
        emoji = misc['received']
        emoji2 = misc['offline']
        if 0 < player.received <= 100:
            number = number_emojis[player.received]
        else:
            number = str(player.received)
    return f'{emoji2}{player.name} {emoji} {number} ({clan_name})'


def format_trophy_log_message(player, clan_name):
    trophies = player.tropies
    abs_trophies = abs(trophies)

    if 0 < abs_trophies <= 100:
        number = number_emojis[abs_trophies]
    else:
        number = abs_trophies

    emoji = misc['trophies_gained'] if trophies > 0 else misc['trophies_lost']

    return f"{misc['trophies']}{player.name} {emoji} {number} ({clan_name})"


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


class CLYTable:
    def __init__(self):
        self._widths = []
        self._rows = []

    def add_row(self, row):
        rows = [str(r) for r in row]
        self._rows.append(rows)

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def clear_rows(self):
        self._rows = []

    def donationboard_1(self):
        fmt = f"{misc['number']}`⠀{'Dons':\u00A0>6.6}⠀` `⠀{'Rec':\u00A0>5.5}⠀` `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>6.6}⠀` `⠀{str(v[2]):\u00A0>5.5}⠀` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def donationboard_2(self):
        fmt = f"{misc['number']}`⠀{'Dons':\u00A0>6.6}⠀` `⠀{'Name':\u00A0<16.16}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>6.6}⠀` `⠀{str(v[2]):\u00A0<16.16}⠀`\n"
        return fmt

    def trophyboard_1(self):
        fmt = f"{misc['number']}`⠀{'Cups':\u00A0>4.4}⠀` ` {'Gain':\u00A0>4.4} ` `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀` ` {str(v[2]):\u00A0>4.4} ` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def trophyboard_2(self):
        fmt = f"{misc['number']}` {'Gain':\u00A0>4.4} `⠀{'Name':\u00A0<18.18}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀`⠀{str(v[2]):\u00A0<18.18}⠀`\n"
        return fmt

    def events_list(self):
        fmt = f"{misc['number']}` {'Starts In':\u00A0^9} `⠀{'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0^9}⠀`⠀{str(v[2]):\u00A0<15.15}⠀`\n"
        return fmt

    def donation_log_command(self):
        fmt = f"{misc['number']}⠀`⠀{'Don/Rec':\u00A0>7.7}⠀`  `⠀{'Name':\u00A0<12.12}⠀`  `⠀{'Age':\u00A0<5.5}⠀`\n"
        for v in self._rows:
            fmt += f"{v[0]}⠀`⠀{str(v[1]):\u00A0>7.7}⠀`  `⠀{str(v[2]):\u00A0<12.12}⠀`  `⠀{str(v[3]):\u00A0<5.5}⠀`\n"
        return fmt

    def trophy_log_command(self):
        fmt = f"{misc['number']}⠀`⠀{'Gain':\u00A0>4.4}⠀`  `⠀{'Name':\u00A0<14.14}⠀`  `⠀{'Age':\u00A0<5.5}⠀`\n"
        for v in self._rows:
            fmt += f"{v[0]}⠀`⠀{str(v[1]):\u00A0>3.3}⠀`  `⠀{str(v[2]):\u00A0<14.14}⠀`  `⠀{str(v[3]):\u00A0<5.5}⠀`\n"
        return fmt


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

        self.embed.set_author(name=self.title or self.ctx.config.title,
                              icon_url=self.ctx.config.icon_url
                                        or 'https://cdn.discordapp.com/emojis/592028799768592405.png?v=1')

        return self.embed

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = await self.get_page(page)
        embed = await self.get_embed(entries, page, first=first)

        if not self.paginating:
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
                row = [player_data[0], player_data[1]['trophies'], player_data[1]['gained'], player.name]
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
                    misc['trophies_gained'] if player_data[1] > 0 else misc['trophies_lost'],
                    abs(player_data[1]),
                    player_data[4],
                    time
                ]
            self.table.add_row(row)

        if self.ctx.config.type == 'donation':
            return f"{self.table.donation_log_command()}\nKey: {misc['donated']} - Donated," \
                   f" {misc['received']} - Received"
        else:
            return f"{self.table.trophy_log_command()}\nKey: {misc['trophies_gained']} - Trophies Gained," \
                   f" {misc['trophies_lost']} - Trophies Lost"
