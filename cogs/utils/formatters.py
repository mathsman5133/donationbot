from disnake.utils import _string_width
from disnake.ext import commands
from cogs.utils.emoji_lookup import emojis, misc, number_emojis


def big_number_fmt(value):
    value = int(value)
    if value < 10_000:
        return '{:,}'.format(value)

    if value // 1_000_000_000:
        return f'{round(value / 1_000_000_000, 3)}'.replace('.0', '') + 'bil'
    if value // 1_000_000 > 0:
        return f'{round(value / 1_000_000, 3)}'.replace('.0', '') + 'mil'
    elif value // 1_000 > 0:
        return f'{round(value / 1_000, 3)}'.replace('.0', '') + 'k'
    else:
        return f'{value}'


def get_render_type(config, table):
    if getattr(config, 'type', None) == 'donation':
        if config.render == 1:
            render = table.donationboard_1
        else:
            render = table.donationboard_2
    elif getattr(config, 'type', None) == 'last_online':
        render = table.last_online_board
    else:
        if config.render == 1:
            render = table.trophyboard_1
        elif config.render == 2:
            render = table.trophyboard_2
        elif config.render == 3:
            render = table.trophyboard_attacks
        elif config.render == 4:
            render = table.trophyboard_defenses
        else:
            render = table.trophyboard_gain
    return render


def clean_name(name):
    if len(name) > 15:
        name = name[:15] + '..'
    return name


def readable_time(delta_seconds):
    if delta_seconds < 0:
        ago = True
        delta_seconds = - delta_seconds
    else:
        ago = False

    hours, remainder = divmod(int(delta_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days:
        fmt = '{d}d {h}h {m}m'
    elif hours:
        fmt = '{h}h {m}m'
    else:
        fmt = '{m}m {s}s'

    fmt = fmt.format(d=days, h=hours, m=minutes, s=seconds)
    if ago:
        return f'{fmt} ago'
    return fmt


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

    def last_online_board(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Name':\u00A0>12.12}⠀` `⠀{'Last Online':\u00A0>11.11}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[4]):\u00A0>12.12}⠀` `⠀{v[3]:\u00A0>11.11}⠀`\n"
        return fmt

    def donationboard_1(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Dons':\u00A0>6.6}⠀` `⠀{'Rec':\u00A0>5.5}⠀` `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>6.6}⠀` `⠀{str(v[3]):\u00A0>5.5}⠀` `⠀{str(v[4]):\u00A0<10.10}⠀`\n"
        return fmt

    def donationboard_2(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀⠀{'Dons':\u00A0>6.6}⠀` `⠀{'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>6.6}⠀` `⠀{str(v[3]):\u00A0<15.15}⠀`\n"
        return fmt

    def trophyboard_1(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Cups':\u00A0>4.4}⠀` ` {'Gain':\u00A0>5.5} ` `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>4.4}⠀` ` {str(v[3]):\u00A0>5.5} ` `⠀{str(v[4]):\u00A0<10.10}⠀`\n"
        return fmt

    def trophyboard_2(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}` {'Gain':\u00A0>5.5}⠀` ` {'Name':\u00A0<18.18}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>5.5}⠀` ` {str(v[3]):\u00A0<18.18}⠀`\n"
        return fmt

    def trophyboard_attacks(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}⠀⠀{misc['attack']}⠀ `⠀{'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>4.4}⠀` `⠀{str(v[3]):\u00A0<15.15}⠀`\n"
        return fmt

    def trophyboard_defenses(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}⠀⠀{misc['defense']} ⠀`⠀{'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>4.4}⠀` `⠀{str(v[3]):\u00A0<15.15}⠀`\n"
        return fmt

    def trophyboard_gain(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}⠀⠀{misc['trophygreen']}⠀ `⠀{'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>4.4}⠀` `⠀{str(v[3]):\u00A0<15.15}⠀`\n"
        return fmt

    def events_list(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}` {'Starts In':\u00A0^9}⠀` ` {'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0^9}⠀` ` {str(v[3]):\u00A0<15.15}⠀`\n"
        return fmt

    def donation_log_command(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Don/Rec':\u00A0>7.7}⠀`  `⠀{'Name':\u00A0<12.12}⠀`  `⠀{'Age':\u00A0<5.5}⠀`\n"
        for v in self._rows:
            fmt += f"{v[0]}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>7.7}⠀`  `⠀{str(v[3]):\u00A0<12.12}⠀`  `⠀{str(v[4]):\u00A0<5.5}⠀`\n"
        return fmt

    def trophy_log_command(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Gain':\u00A0>4.4}⠀`  `⠀{'Name':\u00A0<14.14}⠀`  `⠀{'Age':\u00A0<5.5}⠀`\n"
        for v in self._rows:
            fmt += f"{v[0]}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>3.3}⠀`  `⠀{str(v[3]):\u00A0<14.14}⠀`  `⠀{str(v[4]):\u00A0<5.5}⠀`\n"
        return fmt

    def last_online(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Last On':\u00A0>9.9}⠀` `⠀{'Name':\u00A0>15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>9.9}⠀` `⠀{str(v[3]):\u00A0>15.15}⠀`\n"
        return fmt

    def achievement(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Achievement':\u00A0>11.11}⠀` `⠀{'Name':\u00A0>13.13}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{big_number_fmt(v[2]):\u00A0>11.11}⠀` `⠀{str(v[3]):\u00A0>13.13}⠀`\n"
        return fmt

    def accounts(self):
        show = any(v[1] for v in self._rows)
        fmt = f"{misc['number']}{emojis[17] if show else ''}`⠀{'Player IGN':\u00A0>11.11}⠀` `⠀{'Discord/Tag':\u00A0>13.13}⠀`\n"
        for v in self._rows:
            index = int(v[0])
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}{v[1] or '⠀⠀' if show else ''}`⠀{str(v[2]):\u00A0>11.11}⠀` `⠀{str(v[3]):\u00A0>13.13}⠀`\n"
        return fmt


def get_line_chunks(lines, chunk_size=13, max_size=1950):
    if not lines:
        return

    chars = 0
    idx_start = 0
    for idx, line in enumerate(lines):
        chars += len(line) + 1  # Need to count the eventual \n
        if chars > max_size:
            yield lines[idx_start:idx]
            chars = len(line) + 1
            idx_start = idx
        if idx == len(lines) - 1:
            yield lines[idx_start:]


class LineWrapper(commands.Paginator):
    def __init__(self, max_size=2000):
        super().__init__('', '', max_size=max_size)
    def add_lines(self, lines, empty=False):
        for line in lines:
            self.add_line(line)
