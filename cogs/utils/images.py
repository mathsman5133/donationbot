import copy
import io
import logging
import math
import time

from PIL import ImageFont, Image, ImageDraw

log = logging.getLogger(__name__)

BACKGROUND = Image.open(f"assets/dark_backdrop.jpg").resize((3000, 4500))

SUPERCELL_FONT_FP = "assets/Supercell-Magic_5.ttf"
SUPERCELL_FONT_SIZE = 40
SUPERCELL_FONT = ImageFont.truetype(SUPERCELL_FONT_FP, SUPERCELL_FONT_SIZE)

REGULAR_FONT_FP = "assets/Roboto-Black.ttf"
REGULAR_FONT_SIZE = 200
REGULAR_FONT = ImageFont.truetype(REGULAR_FONT_FP, REGULAR_FONT_SIZE)

IMAGE_WIDTH = 3000

MINIMUM_COLUMN_HEIGHT = 318
LEFT_COLUMN_WIDTH = 20
NUMBER_LEFT_COLUMN_WIDTH = 40
NAME_LEFT_COLUMN_WIDTH = 170
DONATIONS_LEFT_COLUMN_WIDTH = 620
RECEIVED_LEFT_COLUMN_WIDTH = 820
RATIO_LEFT_COLUNM_WIDTH = 1020
LAST_ONLINE_LEFT_COLUMN_WIDTH = 1220

HEADER_RECTANGLE_RGB = (40, 40, 70)
RECTANGLE_RGB = (60,80,100)
NUMBER_RGB = (200, 200, 255)
NAME_RGB = (255, 255, 255)
DONATIONS_RGB = (100, 255, 100)
RECEIVED_RGB = (255, 100, 100)
RATIO_RGB = (100, 100, 255)
LAST_ONLINE_RGB = (200, 200, 200)


def get_readable(delta):
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if delta.days:
        return f"{days}d {hours}h"
    else:
        return f"{hours}h {minutes}m"


class DonationBoardImage:
    def __init__(self, title):
        self.title = title or "Donation Board"
        self.height = MINIMUM_COLUMN_HEIGHT
        self.width = 0
        self.max_width = IMAGE_WIDTH / 2 - 40
        self.image = copy.deepcopy(BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    def special_text(self, position, text, rgb, font_fp, font_size, max_width, centre_align=False):
        font = ImageFont.truetype(font_fp, font_size)
        text_width, text_height = self.draw.textsize(text, font)
        while text_width > max_width:
            font_size -= 1
            font = ImageFont.truetype(font_fp, font_size)
            text_width, text_height = self.draw.textsize(text, font)

        if centre_align:
            position = (int((IMAGE_WIDTH - text_width) / 2), position[1])

        self.draw.text(position, text, rgb, font)

    def add_headers(self, add_double_column=False):
        if add_double_column:
            self.special_text((IMAGE_WIDTH / 4.5, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=2200, centre_align=True)
        else:
            self.special_text((40, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=2200, centre_align=True)

        self.draw.rectangle(((LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT), ((IMAGE_WIDTH / 2) - 40, MINIMUM_COLUMN_HEIGHT + 60)), fill=HEADER_RECTANGLE_RGB)
        self.draw.text((NUMBER_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "#", NUMBER_RGB, font=SUPERCELL_FONT)
        self.draw.text((NAME_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Name", NAME_RGB, font=SUPERCELL_FONT)
        self.draw.text((DONATIONS_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Dons", DONATIONS_RGB, font=SUPERCELL_FONT)
        self.draw.text((RECEIVED_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Rec", RECEIVED_RGB, font=SUPERCELL_FONT)
        self.draw.text((RATIO_LEFT_COLUNM_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Ratio", RATIO_RGB, font=SUPERCELL_FONT)
        self.draw.text((LAST_ONLINE_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Last On", LAST_ONLINE_RGB, font=SUPERCELL_FONT)

        if add_double_column:
            halfway = IMAGE_WIDTH / 2 + 40
            self.draw.rectangle(((IMAGE_WIDTH + LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT), ((IMAGE_WIDTH / 2) + 40, MINIMUM_COLUMN_HEIGHT + 60)), fill=HEADER_RECTANGLE_RGB)
            self.draw.text((halfway + NUMBER_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "#", NUMBER_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + NAME_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Name", NAME_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + DONATIONS_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Dons", DONATIONS_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + RECEIVED_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Rec", RECEIVED_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + RATIO_LEFT_COLUNM_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Ratio", RATIO_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + LAST_ONLINE_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 15), "Last On", LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_player(self, player):
        self.height += 82
        position = ((self.width or LEFT_COLUMN_WIDTH, self.height), (self.max_width, self.height + 60))

        self.draw.rectangle(position, fill=RECTANGLE_RGB)
        self.draw.text((self.width + NUMBER_LEFT_COLUMN_WIDTH, self.height + 15), f"{player.index}.", NUMBER_RGB, font=SUPERCELL_FONT)
        self.special_text((self.width + NAME_LEFT_COLUMN_WIDTH, self.height + 15), player.name, NAME_RGB, SUPERCELL_FONT_FP, SUPERCELL_FONT_SIZE, 400)
        self.draw.text((self.width + DONATIONS_LEFT_COLUMN_WIDTH, self.height + 15), str(player.donations), DONATIONS_RGB, font=SUPERCELL_FONT)
        self.draw.text((self.width + RECEIVED_LEFT_COLUMN_WIDTH, self.height + 15), str(player.received), RECEIVED_RGB, font=SUPERCELL_FONT)
        self.draw.text((self.width + RATIO_LEFT_COLUNM_WIDTH, self.height + 15), f"{round(player.donations / (player.received or 1), 2)}", RATIO_RGB, font=SUPERCELL_FONT)
        self.draw.text((self.width + LAST_ONLINE_LEFT_COLUMN_WIDTH, self.height + 15), get_readable(player.last_online), LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_players(self, players):
        double_column = len(players) > 25
        self.add_headers(add_double_column=double_column)

        if double_column:
            for p in players[:25]:
                self.add_player(p)

            self.width = IMAGE_WIDTH / 2 + 40
            self.max_width = IMAGE_WIDTH
            self.height = MINIMUM_COLUMN_HEIGHT

            for p in players[25:50]:
                self.add_player(p)

            self.image = self.image.crop((0, 0, IMAGE_WIDTH, self.height + 80))

        else:
            for player in players:
                self.add_player(player)

            self.image = self.image.crop((0, 0, IMAGE_WIDTH / 2 - 20, self.height + 80))

    def render(self):
        self.image = self.image.resize((int(self.image.size[0] / 4), int(self.image.size[1] / 4)))
        buffer = io.BytesIO()
        self.image.save(buffer, format="png")
        buffer.seek(0)
        return buffer



