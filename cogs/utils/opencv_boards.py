import matplotlib.pyplot as plt
import matplotlib.image as mimage
import matplotlib.tight_layout as mtight
import matplotlib.transforms as mtransforms
import numpy as np
import discord
import io
import logging
import time
import colorsys
import statistics
import math
from PIL import Image

from cogs.utils.formatters import readable_time

log = logging.getLogger()
PER_GRAPH = 25

def get_readable(delta):
    hours, remainder = divmod(int(delta), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if days:
        return f"{days}d {hours}h"
    else:
        return f"{hours}h {minutes}m"

class MPLTable:
    def __init__(self, table_name, columns, start=1):
        self.table_name = table_name
        self.columns = columns
        self.start = start

        self.rows = []
        self.colours = []
        self.column_widths = [0.3, ]

    def add_row(self, data):
        data = list(data)
        data[-1] = data[-1].total_seconds()
        self.rows.append([str(n) for n in data])

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    @staticmethod
    def get_colour(percentage, reverse=False):
        if reverse:
            return colorsys.hsv_to_rgb(1 / 3 - percentage * 1 / 3, 1, 1)
        else:
            return colorsys.hsv_to_rgb(percentage * 1 / 3, 1, 1)

    def populate_colours(self):
        colours = []
        for i, values in enumerate(zip(*self.rows)):
            try:
                values = [float(x) if x and not x == 'None' else 0.0 for x in values]
            except ValueError:
                colours.append([(1, 1, 1) for _ in range(len(values))])
                continue

            mean = statistics.mean(values)
            sdev = statistics.stdev(values)

            markers = [
                (0.0, min(0, *values)),
                (0.25, statistics.median_low(values)),
                (0.5, statistics.median(values)),
                (0.75, statistics.median_high(values)),
                (1.0, max(v for v in values if v < mean + sdev))
            ]
            percentages = []

            for index, (percentage, lower_range) in enumerate(markers):
                try:
                    upper_range = markers[i + 1][1]
                except IndexError:
                    continue

                to_use = [v for v in values if lower_range < v < upper_range]
                if not to_use:
                    continue

                min_val, max_val = min(to_use), max(to_use)

                percentages.extend([percentage + (val - min_val) / (max_val - min_val) / 4 for val in to_use])

            print(percentages)

            # dev = statistics.stdev(values)
            # mean = statistics.mean(values)
            # outliers = [v for v in values if not mean - dev < v < mean + dev]
            # good_vals = [v for v in values if mean - dev < v < mean + dev]
            #
            # divided = statistics.quantiles(good_vals, n=len(good_vals), method="exclusive")
            # combined = sorted(list(zip(sorted(good_vals), divided)), key=lambda t: good_vals.index(t[0]))
            #
            # min_val, max_val = min(0, min(a for v, a in combined)), max(a for v, a in combined)
            # percentages = [(adjusted - min_val) / (max_val - min_val) for val, adjusted in combined]
            #
            # percentages = [0] * len([v for v in outliers if v < mean]) + percentages + [1] * len([v for v in outliers if v > mean])
            percentages = [0] * (len(values) - len(percentages)) + percentages

            if i == len(self.rows[0]) - 1:
                last_online = True
            else:
                last_online = False

            colours.append([self.get_colour(percent, reverse=last_online) for percent in percentages])

        print(colours, [len(x) for x in colours])
        self.colours = list(zip(*colours))

    def adjust_time(self):
        for row in self.rows:
            row[-1] = get_readable(float(row[-1]))

    def render(self):
        s = time.perf_counter()
        self.populate_colours()
        self.adjust_time()
        log.info(f"{(time.perf_counter() - s)*1000}ms to populate colours")

        bytes_array = []

        for i in range(int(math.ceil(len(self.rows) / PER_GRAPH))):
            s = time.perf_counter()
            fig = plt.figure(linewidth=2,
                       edgecolor='steelblue',
                       facecolor='skyblue',
                       #tight_layout={'pad': 1},
                       figsize=(6, 5)
                       )
            ax = fig.gca()

            log.info(f"{(time.perf_counter() - s) * 1000}ms t create figure")
            row_headers = [str(i) + ". " for i in range(PER_GRAPH*i + 1, (i+1)*PER_GRAPH + 1)]
            rcolors = plt.cm.BuPu(np.full(PER_GRAPH, 0.1))
            ccolors = plt.cm.BuPu(np.full(PER_GRAPH, 0.1))

            s = time.perf_counter()
            rows = self.rows[i*PER_GRAPH:(i+1)*PER_GRAPH]
            colours = self.colours[i*PER_GRAPH:(i+1)*PER_GRAPH]
            table = ax.table(
                cellText=rows,
                rowLabels=row_headers,
                rowLoc='right',
                rowColours=rcolors,
                colColours=ccolors,
                colLabels=self.columns,
                loc='center left',
                cellColours=colours,
                # bbox=[0, 6, 0, 8]
                # colWidths=self.column_widths
            )
            log.info(f"{(time.perf_counter() - s)*1000}ms t create table")

            table.auto_set_column_width(col=list(range(len(self.columns))))

            table.set_fontsize(10)
            # table.scale(1.5, 1.5)
            #table.scale(0.8, 2)
            # Hide axes
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
            # Hide axes border
            ax.set_frame_on(False)
            # Add title
            # if i == 0:
            #     plt.suptitle(self.table_name)
            # Add footer
            # plt.figtext(0.95, 0.05, datetime, horizontalalignment='right', size=6, weight='light')

            b = io.BytesIO()


            s = time.perf_counter()
            #fig.set_tight_layout(True)

            renderer = fig.canvas.get_renderer(cleared=True)
            log.info(f"{(time.perf_counter() - s)*1000}ms to get renderer figure")

            s = time.perf_counter()
            # kwargs = mtight.get_tight_layout_figure(fig, fig.axes, mtight.get_subplotspec_list(fig.axes), renderer, **fig._tight_parameters)
            # log.info(f"{(time.perf_counter() - s)*1000}ms to get adjust tight figure")
            # s = time.perf_counter()
            # if kwargs:
            #     fig.subplots_adjust(**kwargs)
            log.info(f"{(time.perf_counter() - s)*1000}ms to get actually tight figure")

            s = time.perf_counter()
            fig.patch.draw(renderer)
            log.info(f"{(time.perf_counter() - s)*1000}ms to get draw figure")

            s = time.perf_counter()
            # mimage._draw_list_compositing_images(
            #     renderer, fig, fig.get_children(), fig.suppressComposite)
            table.draw(renderer)
            # fig.canvas.figure.draw(renderer)
            log.info(f"{(time.perf_counter() - s)*1000}ms to draw figure")
            s = time.perf_counter()
            pil_kwargs = {}
            pil_kwargs.setdefault("format", "png")
            pil_kwargs.setdefault("dpi", (fig.dpi, fig.dpi))
            rgba = renderer.buffer_rgba()
            log.info(f"{(time.perf_counter() - s)*1000}ms to buffer figure")

            s = time.perf_counter()
            pil_shape = (rgba.shape[1], rgba.shape[0])
            image = Image.frombuffer(
                "RGBA", pil_shape, rgba, "raw", "RGBA", 0, 1)

            log.info(f"{(time.perf_counter() - s)*1000}ms to load from buffer figure")

            s = time.perf_counter()
            image.save(b, **pil_kwargs)
            log.info(f"{(time.perf_counter() - s)*1000}ms to save figure")

            # fig.canvas.print_png(b,
            #             #bbox='tight',
            #             #edgecolor=fig.get_edgecolor(),
            #             #facecolor=fig.get_facecolor(),
            #             #dpi=150,
            #             format="png"
            #             )
            b.seek(0)
            plt.clf()
            bytes_array.append(b)

        print(bytes_array)
        return bytes_array

    def convert_to_many_images(self):
        s = time.perf_counter()
        bytes_array = self.render()

        if len(self.rows) < 20:
            return [bytes_array]

        to_return = []
        image = Image.frombytes('RGBA', (128, 128), bytes_array, 'raw')
        for i in range(int(math.ceil(len(self.rows) / 20))):
            new = image.crop((40, i*20, 40, (i+1)*20))
            b = io.BytesIO()
            new.save(b, format="png")
            b.seek(0)
            to_return.append(b)

        log.info(f"{(time.perf_counter() - s) * 1000}ms to process image")

        return to_return


class DonationBoardTable(MPLTable):
    def __init__(self, board_name):
        columns = ("Name", "Donations", "Received", "Ratio", "Trophies", "Gain", "Last On", )
        super().__init__(board_name, columns)


class TrophyBoardTable(MPLTable):
    def __init__(self, board_name, start):
        columns = ("Name", "Cups", "Gain", "Last On")
        super().__init__(board_name, columns, start)
