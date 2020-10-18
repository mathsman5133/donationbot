import asyncio
import io


class HTMLImages:
    def __init__(self, players, title=None, image=None):
        self.players = players

        self.title = title or "Donation Leaderboard"
        self.image = image or "https://cdn.discordapp.com/attachments/641594147374891029/767306860306759680/dc0f83c3eba7fad4cbe8de3799708e93.jpg"

        self.html = ""

    def add_style(self):
        self.html += """
<!DOCTYPE html>
<html>
<head>
<style>
img {
  position: fixed;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  z-index:-1;
  opacity:0.9;
}
table {
  font-family: Lato, Helvetica, Arial, sans-serif;
  border-collapse: seperate;
  border-spacing: 0 12px;
  width: 100%;
  padding-bottom: 30px;
  padding-left: 30px;
  padding-right: 30px
}

td, th {
  text-align: left;
  font-size: 40px;
  padding: 10px;
  box-shadow: 0 4px 8px 0 rgba(0, 0, 0, 0.2), 0 6px 20px 0 rgba(0, 0, 0, 0.19);
}

th {
  border: 1px solid #404040;
  background-color: rgba(185, 147, 108, 0.6);
  
}


tr:nth-child(even) {
  background-color: rgba(166, 179, 196, 0.8);
}
tr:nth-child(odd) {
  background-color: rgba(196, 186, 133, 0.8);
}

header {
  background:-webkit-gradient(linear,left bottom,left top,color-stop(20%,rgb(196, 183, 166)),color-stop(80%,rgb(220, 207, 186)));
  font-size: 60px;
  margin-left: auto;
  margin-right: auto;
  text-align: center;
  font-style: bold;
  font-weight: 200;
  letter-spacing: 1.5px;
  opacity: 1;
}
</style>
        """

    def add_body(self):
        self.html += "<body>"

    def add_title(self):
        self.html += f"<header>{self.title}</header>"

    def add_image(self):
        self.html += f'<img src="{self.image}" alt="Test"></img>'

    def add_table(self):
        to_add = "<table>"

        headers = ("#", "Player Name", "Dons", "Rec", "Ratio", "Trophies", "Gain", "Last On")
        to_add += "<tr>" + "".join(f"<th>{column}</th>" for column in headers) + "</tr>"

        for player in self.players:
            to_add += "<tr>" + "".join(f"<td>{cell}</td>" for cell in player) + "</tr>"

        to_add += "</table>"
        self.html += to_add

    def end_html(self):
        self.html += "</body></html>"

    def parse_players(self):
        self.players = [(i, p['player_name'], p['donations'], p['received'], round(p['donations'] / p['received'], 2), p['trophies'], p['gain'], p['last_online']) for i, p in enumerate(self.players)]

    async def make(self):
        self.add_style()
        self.add_body()
        self.add_title()
        self.add_image()
        self.add_table()
        self.end_html()

        proc = await asyncio.create_subprocess_shell(
            'wkhtmltoimage - -', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate(input=self.html.encode('utf-8'))
        return io.BytesIO(stdout)
