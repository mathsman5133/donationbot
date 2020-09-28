import matplotlib.pyplot as plt
import discord
import io


class MPLTable:
    def __init__(self, table_name, columns, start=1):
        self.table_name = table_name
        self.columns = columns
        self.start = start

        self.rows = []

    def add_row(self, data):
        self.rows.append(*[str(n) for n in data])

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def render(self):
        plt.figure(linewidth=2,
                   edgecolor='steelblue',
                   facecolor='skyblue',
                   tight_layout={'pad': 1},
                   # figsize=(5,3)
                   )
        row_headers = [str(i) + ". " + x.pop(0) for i, x in enumerate(self.rows, start=self.start)]
        table = plt.table(
            cellText=self.rows,
            rowLabels=row_headers,
            rowLoc='right',
            colLabels=self.columns,
            loc='center'
        )
        table.scale(1, 2)

        # Hide axes
        ax = plt.gca()
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        # Hide axes border
        plt.box(on=None)
        # Add title
        plt.suptitle(self.table_name)
        # Add footer
        # plt.figtext(0.95, 0.05, datetime, horizontalalignment='right', size=6, weight='light')

        b = io.BytesIO()
        plt.savefig(b, format='png')
        b.seek(0)
        plt.close()
        return discord.File(b, f'board.png')


class DonationBoardTable(MPLTable):
    def __init__(self, board_name, start):
        columns = ("Name", "Cups", "Gain", "Last On")
        super().__init__(board_name, columns, start)


class TrophyBoardTable(MPLTable):
    def __init__(self, board_name, start):
        columns = ("Name", "Dons", "Rec", "Ratio", "Last On", )
        super().__init__(board_name, columns, start)
