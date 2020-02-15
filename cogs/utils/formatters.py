from discord.utils import _string_width
from cogs.utils.emoji_lookup import emojis, misc, number_emojis

def get_render_type(config, table):
    if getattr(config, 'type', None) == 'donation':
        if config.render == 1:
            render = table.donationboard_1
        else:
            render = table.donationboard_2
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
        fmt = '{d}d {h}h {m}m {s}s'
    elif hours:
        fmt = '{h}h {m}m {s}s'
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
    trophies = player.trophies
    abs_trophies = abs(trophies)

    if 0 < abs_trophies <= 100:
        number = number_emojis[abs_trophies]
    else:
        number = abs_trophies

    emoji = (misc['trophygreen'], misc['trophygain']) if trophies > 0 else (misc['trophyred'], misc['trophyloss'])

    return f"{emoji[0]} {player.name} {emoji[1]} {number} {emojis[player.league_id]} ({clan_name})"


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
        fmt = f"{misc['number']}`⠀{'Cups':\u00A0>4.4}⠀` ` {'Gain':\u00A0>5.5} ` `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀` ` {str(v[2]):\u00A0>5.5} ` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def trophyboard_2(self):
        fmt = f"{misc['number']}` {'Gain':\u00A0>5.5}⠀` ` {'Name':\u00A0<18.18}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>5.5}⠀` ` {str(v[2]):\u00A0<18.18}⠀`\n"
        return fmt

    def trophyboard_attacks(self):
        fmt = f"{misc['number']}⠀⠀{misc['attack']}⠀{misc['trophygold']}⠀ `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀` ` {str(v[2]):\u00A0>4.4} ` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def trophyboard_defenses(self):
        fmt = f"{misc['number']} ⠀⠀{misc['defense']} ⠀{misc['trophygold']}   `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀` ` {str(v[2]):\u00A0>4.4} ` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def trophyboard_gain(self):
        fmt = f"{misc['number']}    {misc['trophygreen']}⠀{misc['trophygold']}  `⠀{'Name':\u00A0<10.10}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0>4.4}⠀` ` {str(v[2]):\u00A0>4.4} ` `⠀{str(v[3]):\u00A0<10.10}⠀`\n"
        return fmt

    def events_list(self):
        fmt = f"{misc['number']}` {'Starts In':\u00A0^9}⠀` ` {'Name':\u00A0<15.15}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}`⠀{str(v[1]):\u00A0^9}⠀` ` {str(v[2]):\u00A0<15.15}⠀`\n"
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

    def last_online(self):
        fmt = f"{misc['number']}⠀`⠀{'Name':\u00A0>13.13}⠀` `⠀{'Last Online':\u00A0>11.11}⠀`\n"
        for v in self._rows:
            index = int(v[0]) + 1
            index = number_emojis[index] if index <= 100 else misc['idle']
            fmt += f"{index}⠀`⠀{str(v[1]):\u00A0>13.13}⠀`  `⠀{str(v[2]):\u00A0>11.11}⠀`\n"
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
