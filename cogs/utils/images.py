import copy
import io
import logging
import re
import math
import time
import creds

from PIL import ImageFont, Image, ImageDraw, UnidentifiedImageError

log = logging.getLogger(__name__)

CJK_REGEX = re.compile(r"[\u4e00-\u9FFF\u3040-\u30ff\uac00-\ud7a3]")  # chinese, japanese, korean unicode ranges

if creds.live:
    absolute_path = "/home/mathsman/donationbot/"
else:
    absolute_path = ""
BACKGROUND = Image.open(f"{absolute_path}assets/clash_cliffs.png")
TROPHYBOARD_BACKGROUND = Image.open(f"{absolute_path}assets/snowyfield.png")

CJK_FRIENDLY_FONT_FP = absolute_path + "assets/NotoSansCJK-Bold.ttc"
SUPERCELL_FONT_FP = absolute_path + "assets/DejaVuSans-Bold.ttf"
SUPERCELL_FONT_SIZE = 70
SUPERCELL_FONT = ImageFont.truetype(SUPERCELL_FONT_FP, SUPERCELL_FONT_SIZE)

REGULAR_FONT_FP = absolute_path + "assets/Roboto-Black.ttf"
REGULAR_FONT_SIZE = 140
REGULAR_FONT = ImageFont.truetype(REGULAR_FONT_FP, REGULAR_FONT_SIZE)

SEASON_FONT = ImageFont.truetype(REGULAR_FONT_FP, 60)

IMAGE_WIDTH = 4000

MINIMUM_COLUMN_HEIGHT = 200
LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 55  # 20
COLUMN_RIGHT_BOUND = IMAGE_WIDTH - IMAGE_WIDTH / 55
NUMBER_LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 35  # 40
NAME_LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 8.5  # 220
DONATIONS_LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 2.72  # 720
RECEIVED_LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 1.945
RATIO_LEFT_COLUNM_WIDTH = IMAGE_WIDTH / 1.51
LAST_ONLINE_LEFT_COLUMN_WIDTH = IMAGE_WIDTH / 1.23

HEADER_RECTANGLE_RGB = (40, 40, 70)
RECTANGLE_RGB = (60,80,100)
NUMBER_RGB = (200, 200, 255)
NAME_RGB = (255, 255, 255)
DONATIONS_RGB = (100, 255, 100)
RECEIVED_RGB = (255, 100, 100)
RATIO_RGB = (150, 220, 225)
LAST_ONLINE_RGB = (200, 200, 200)

T_TROPHIES_LEFT_COLUMN_WIDTH = 840
T_GAIN_LEFT_COLUMN_WIDTH = 1120
T_LAST_ONLINE_LEFT_COLUMN_WIDTH = 1420

T_HEADER_RECTANGLE_RGB = (61, 66, 71)
T_RECTANGLE_RGB = (74, 89, 82)
T_NUMBER_RGB = (209, 227, 212)
T_NAME_RGB = (232, 250, 235)
T_TROPHIES_RGB = (224, 230, 69)
T_GAIN_RGB = (33, 174, 181)
T_LAST_ONLINE_RGB = (194, 84, 34)

def get_width(original_size, is_double=False, left=True):
    if not is_double:
        return original_size
    if left:
        return (original_size / IMAGE_WIDTH) * (IMAGE_WIDTH / 2) - IMAGE_WIDTH / 55
    return (original_size / IMAGE_WIDTH) * (IMAGE_WIDTH / 2) + IMAGE_WIDTH / 2 + IMAGE_WIDTH / 55

def get_readable(delta):
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    if delta.days:
        return f"{days}d {hours}h"
    else:
        return f"{hours}h {minutes}m"


class DonationBoardImage:
    def __init__(self, title, icon, season_start, season_finish):
        self.title = title or "Donation Board"
        self.icon = icon
        self.season_start, self.season_finish = season_start, season_finish
        self.height = MINIMUM_COLUMN_HEIGHT
        self.width = 0
        self.max_width = IMAGE_WIDTH / 2 - 40
        self.image = copy.deepcopy(BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    def special_text(self, position, text, rgb, font_fp, font_size, max_width, centre_align=False, offset=0):
        if CJK_REGEX.search(text):
            font_fp = CJK_FRIENDLY_FONT_FP

        font = ImageFont.truetype(font_fp, font_size)

        text_width, text_height = self.draw.textsize(text, font)

        need_to_offset = False
        while text_width > max_width - offset:
            font_size -= 1
            font = ImageFont.truetype(font_fp, font_size)
            text_width, text_height = self.draw.textsize(text, font)
            need_to_offset = True

        if need_to_offset and centre_align:
            position = (int((max_width - text_width + offset) / 2), position[1])
        elif centre_align:
            position = (int((max_width - text_width) / 2), position[1])
        elif offset:
            position = (position[0] + offset, position[1])

        self.draw.text(position, text, rgb, font)

    def add_headers(self, add_double_column=False):
        if add_double_column:
            self.special_text((IMAGE_WIDTH / 4.5, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=IMAGE_WIDTH - 40, centre_align=True, offset=180 if self.icon else 0)
        else:
            self.special_text((40, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=int(IMAGE_WIDTH / 2) - 40, centre_align=True, offset=180 if self.icon else 0)

        if self.icon:
            self.image.paste(self.icon, (10, 10))
        adc = add_double_column

        self.draw.rectangle(((get_width(LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT), (get_width(COLUMN_RIGHT_BOUND, adc), MINIMUM_COLUMN_HEIGHT + 100)), fill=HEADER_RECTANGLE_RGB)
        self.draw.text((get_width(NUMBER_LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "#", NUMBER_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(NAME_LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "Name", NAME_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(DONATIONS_LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "Dons", DONATIONS_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(RECEIVED_LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "Rec", RECEIVED_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(RATIO_LEFT_COLUNM_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "Ratio", RATIO_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(LAST_ONLINE_LEFT_COLUMN_WIDTH, adc), MINIMUM_COLUMN_HEIGHT + 2), "Last On", LAST_ONLINE_RGB, font=SUPERCELL_FONT)

        if add_double_column:
            self.draw.rectangle(((get_width(LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT), (COLUMN_RIGHT_BOUND, MINIMUM_COLUMN_HEIGHT + 60)), fill=HEADER_RECTANGLE_RGB)
            self.draw.text((get_width(NUMBER_LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "#", NUMBER_RGB, font=SUPERCELL_FONT)
            self.draw.text((get_width(NAME_LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "Name", NAME_RGB, font=SUPERCELL_FONT)
            self.draw.text((get_width(DONATIONS_LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "Dons", DONATIONS_RGB, font=SUPERCELL_FONT)
            self.draw.text((get_width(RECEIVED_LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "Rec", RECEIVED_RGB, font=SUPERCELL_FONT)
            self.draw.text((get_width(RATIO_LEFT_COLUNM_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "Ratio", RATIO_RGB, font=SUPERCELL_FONT)
            self.draw.text((get_width(LAST_ONLINE_LEFT_COLUMN_WIDTH, True, True), MINIMUM_COLUMN_HEIGHT + 2), "Last On", LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_player(self, player, double=False, left=True):
        position = ((get_width(LEFT_COLUMN_WIDTH, double, left), self.height), (get_width(COLUMN_RIGHT_BOUND, double, left), self.height + 80))

        self.draw.rectangle(position, fill=RECTANGLE_RGB)
        self.draw.text((get_width(NUMBER_LEFT_COLUMN_WIDTH, double, left), self.height + 2), f"{player.index}.", NUMBER_RGB, font=SUPERCELL_FONT)
        self.special_text((get_width(NAME_LEFT_COLUMN_WIDTH, double, left), self.height + 2), str(player.name), NAME_RGB, SUPERCELL_FONT_FP, SUPERCELL_FONT_SIZE, 450)
        self.draw.text((get_width(DONATIONS_LEFT_COLUMN_WIDTH, double, left), self.height + 2), str(player.donations), DONATIONS_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(RECEIVED_LEFT_COLUMN_WIDTH, double, left), self.height + 2), str(player.received), RECEIVED_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(RATIO_LEFT_COLUNM_WIDTH, double, left), self.height + 2), f"{round((player.donations or 0) / (player.received or 1), 2)}", RATIO_RGB, font=SUPERCELL_FONT)
        self.draw.text((get_width(LAST_ONLINE_LEFT_COLUMN_WIDTH, double, left), self.height + 2), get_readable(player.last_online), LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_players(self, players):
        double_column = len(players) > 25
        self.add_headers(add_double_column=double_column)

        if double_column:
            no_players = len(players)

            for p in players[:int(no_players / 2)]:
                self.height += int(IMAGE_HEIGHT / no_players / 2)
                self.add_player(p, True, True)

            self.width = IMAGE_WIDTH / 2 + 40
            self.max_width = IMAGE_WIDTH
            self.height = MINIMUM_COLUMN_HEIGHT

            for p in players[int(no_players / 2):]:
                self.height += int(IMAGE_HEIGHT / no_players / 2)
                self.add_player(p, True, False)

        else:
            for player in players:
                self.height += int(IMAGE_HEIGHT / len(players))
                self.add_player(player, False, False)

        self.draw.text((40, self.height + 90), f"Season: {self.season_start} - {self.season_finish}.", NAME_RGB, font=SEASON_FONT)

        # if double_column:
        #     self.image = self.image.crop((0, 0, IMAGE_WIDTH, self.height + 160))
        # else:
        #     self.image = self.image.crop((0, 0, IMAGE_WIDTH / 2 - 20, self.height + 160))


    def render(self):
        self.image = self.image.resize((int(self.image.size[0] / 4), int(self.image.size[1] / 4)))
        buffer = io.BytesIO()
        self.image.save(buffer, format="png")
        buffer.seek(0)
        return buffer


class TrophyBoardImage:
    def __init__(self, title, icon, season_start, season_finish):
        self.title = title or "Trophy Board"
        self.icon = icon
        self.season_start, self.season_finish = season_start, season_finish
        self.height = MINIMUM_COLUMN_HEIGHT
        self.width = 0
        self.max_width = IMAGE_WIDTH / 2 - 40
        self.image = copy.deepcopy(TROPHYBOARD_BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)

    def special_text(self, position, text, rgb, font_fp, font_size, max_width, centre_align=False, offset=0):
        if CJK_REGEX.search(text):
            font_fp = CJK_FRIENDLY_FONT_FP

        font = ImageFont.truetype(font_fp, font_size)

        text_width, text_height = self.draw.textsize(text, font)

        need_to_offset = False
        while text_width > max_width - offset:
            font_size -= 1
            font = ImageFont.truetype(font_fp, font_size)
            text_width, text_height = self.draw.textsize(text, font)
            need_to_offset = True

        if need_to_offset and centre_align:
            position = (int((max_width - text_width + offset) / 2), position[1])
        elif centre_align:
            position = (int((max_width - text_width) / 2), position[1])
        elif offset:
            position = (position[0] + offset, position[1])

        self.draw.text(position, text, rgb, font)

    def add_headers(self, add_double_column=False):
        if add_double_column:
            self.special_text((IMAGE_WIDTH / 4.5, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=IMAGE_WIDTH - 40, centre_align=True, offset=180 if self.icon else 0)
        else:
            self.special_text((40, 20), self.title, (255, 255, 255), REGULAR_FONT_FP, REGULAR_FONT_SIZE, max_width=int(IMAGE_WIDTH / 2) - 40, centre_align=True, offset=180 if self.icon else 0)

        if self.icon:
            self.image.paste(self.icon, (10, 10))

        self.draw.rectangle(((LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT), ((IMAGE_WIDTH / 2) - 40, MINIMUM_COLUMN_HEIGHT + 100)), fill=T_HEADER_RECTANGLE_RGB)
        self.draw.text((NUMBER_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "#", T_NUMBER_RGB, font=SUPERCELL_FONT)
        self.draw.text((NAME_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Name", T_NAME_RGB, font=SUPERCELL_FONT)
        self.draw.text((T_TROPHIES_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Cups", T_TROPHIES_RGB, font=SUPERCELL_FONT)
        self.draw.text((T_GAIN_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Gain", T_GAIN_RGB, font=SUPERCELL_FONT)
        self.draw.text((T_LAST_ONLINE_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Last On", T_LAST_ONLINE_RGB, font=SUPERCELL_FONT)

        if add_double_column:
            halfway = IMAGE_WIDTH / 2 + 40
            self.draw.rectangle(((IMAGE_WIDTH + LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT), ((IMAGE_WIDTH / 2) + 40, MINIMUM_COLUMN_HEIGHT + 60)), fill=T_HEADER_RECTANGLE_RGB)
            self.draw.text((halfway + NUMBER_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "#", T_NUMBER_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + NAME_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Name", T_NAME_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + T_TROPHIES_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Cups", T_TROPHIES_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + T_GAIN_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Gain", T_GAIN_RGB, font=SUPERCELL_FONT)
            self.draw.text((halfway + T_LAST_ONLINE_LEFT_COLUMN_WIDTH, MINIMUM_COLUMN_HEIGHT + 2), "Last On", T_LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_player(self, player):
        self.height += 100
        position = ((self.width or LEFT_COLUMN_WIDTH, self.height), (self.max_width, self.height + 80))

        self.draw.rectangle(position, fill=T_RECTANGLE_RGB)
        self.draw.text((self.width + NUMBER_LEFT_COLUMN_WIDTH, self.height + 2), f"{player.index}.", T_NUMBER_RGB, font=SUPERCELL_FONT)
        self.special_text((self.width + NAME_LEFT_COLUMN_WIDTH, self.height + 2), str(player.name), T_NAME_RGB, SUPERCELL_FONT_FP, SUPERCELL_FONT_SIZE, 450)
        self.draw.text((self.width + T_TROPHIES_LEFT_COLUMN_WIDTH, self.height + 2), str(player.trophies), T_TROPHIES_RGB, font=SUPERCELL_FONT)
        self.draw.text((self.width + T_GAIN_LEFT_COLUMN_WIDTH, self.height + 2), str(player.gain), T_GAIN_RGB, font=SUPERCELL_FONT)
        self.draw.text((self.width + T_LAST_ONLINE_LEFT_COLUMN_WIDTH, self.height + 2), get_readable(player.last_online), T_LAST_ONLINE_RGB, font=SUPERCELL_FONT)

    def add_players(self, players):
        double_column = len(players) > 25
        self.add_headers(add_double_column=double_column)

        if double_column:
            no_players = len(players)

            for p in players[:int(no_players / 2)]:
                self.add_player(p)

            self.width = IMAGE_WIDTH / 2 + 40
            self.max_width = IMAGE_WIDTH
            self.height = MINIMUM_COLUMN_HEIGHT

            for p in players[int(no_players / 2):]:
                self.add_player(p)

        else:
            for player in players:
                self.add_player(player)

        self.draw.text((40, self.height + 90), f"Season: {self.season_start} - {self.season_finish}.", NAME_RGB, font=SEASON_FONT)

        if double_column:
            self.image = self.image.crop((0, 0, IMAGE_WIDTH, self.height + 120))
        else:
            self.image = self.image.crop((0, 0, IMAGE_WIDTH / 2 - 20, self.height + 160))


    def render(self):
        self.image = self.image.resize((int(self.image.size[0] / 4), int(self.image.size[1] / 4)))
        buffer = io.BytesIO()
        self.image.save(buffer, format="png")
        buffer.seek(0)
        return buffer


