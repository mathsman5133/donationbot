import matplotlib.pyplot as plt
import numpy as np
import discord
import io


class MPLTable:
    def __init__(self, table_name, columns, start=1):
        self.table_name = table_name
        self.columns = columns
        self.start = start

        self.rows = []

    def add_row(self, data):
        self.rows.append([str(n) for n in data])

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def render(self):
        plt.figure(linewidth=2,
                   edgecolor='steelblue',
                   facecolor='skyblue',
                   #tight_layout={'pad': 1},
                   figsize=(5,3)
                   )
        row_headers = [str(i) + ". " for i in range(self.start, len(self.rows) + self.start)]
        rcolors = plt.cm.BuPu(np.full(len(row_headers), 0.1))
        ccolors = plt.cm.BuPu(np.full(len(self.columns), 0.1))

        table = plt.table(
            cellText=self.rows,
            rowLabels=row_headers,
            rowLoc='right',
            rowColours=rcolors,
            colColours=ccolors,
            colLabels=self.columns,
            loc='center'
        )

        table.scale(0.8, 2)

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
        fig = plt.gcf()
        plt.savefig(b,
                    # bbox='tight',
                    edgecolor=fig.get_edgecolor(),
                    facecolor=fig.get_facecolor(),
                    dpi=150
                    )
        b.seek(0)
        plt.close()
        return b


class DonationBoardTable(MPLTable):
    def __init__(self, board_name, start):
        columns = ("Name", "Dons", "Rec", "Ratio", "Last On", )
        super().__init__(board_name, columns, start)


class TrophyBoardTable(MPLTable):
    def __init__(self, board_name, start):
        columns = ("Name", "Cups", "Gain", "Last On")
        super().__init__(board_name, columns, start)
