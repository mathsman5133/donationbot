import asyncio
import io

import httpx
import requests
from time import perf_counter

async def test_img():
    with open("index.html", "rb") as fp:
        html_data = fp.read().decode("utf-8")

    with open("donationbot/assets/wall-background_.png", "rb") as fp:
        img_data = fp.read()

    with open("donationbot/assets/reddit badge.png", "rb") as fp:
        badge_data = fp.read()

    # r = requests.post("http://localhost:3000/forms/chromium/screenshot/html", files={'index.html': html_data, 'background.png': img_data, 'badge.png': badge_data}, data={'quality': 50, 'format': 'jpeg', 'optimizeForSpeed': 'true', 'skipNetworkIdleEvent': 'true'})
    # print('request took %sms', (perf_counter() - s) * 1000, )

    # with open("test.jpeg", "wb") as fp:
    #     fp.write(r.content)

    # with aiohttp.MultipartWriter("form-data") as mp:
    #     part = mp.append("jpeg")
    #     part.set_content_disposition('form-data', name="format")
    #
    #     part = mp.append("true")
    #     part.set_content_disposition('form-data', name="optimizeForSpeed")
    #
    #     part = mp.append(html_data)
    #     part.set_content_disposition('form-data', name="index.html")
    data = {'quality': '50', 'format': 'jpeg', 'optimizeForSpeed': 'true', 'skipNetworkIdleEvent': 'true'}
    f = io.BytesIO(html_data.encode("utf-8"))
    print(f)
    f.seek(0)
    files2 = {
        "index.html": io.BytesIO(html_data.encode("utf-8")),
        # "index.html": open("assets/index.html", "rb"),
        # "index.html": html_data.encode("utf-8")
        # "background.png": open("assets/wall-background_.png", "rb"),
        # "badge.png": open("assets/reddit badge.png", "rb"),
    }
    files3 = [
        ('file', ('index.html', io.BytesIO(html_data.encode("utf-8")))),
        ('file', ('background.png', open("donationbot/assets/wall-background_.png", "rb"))),
        ('file', ('badge.png', io.BytesIO(badge_data))),
    ]
    async with httpx.AsyncClient() as client:
        for _ in range(5):
            start = perf_counter()
            resp = await client.post("http://localhost:3000/forms/chromium/screenshot/html", files=files3, data=data)
            print(f'request took {(perf_counter() - start) * 1000}ms')

    with open("test2.jpeg", "wb") as fp:
        fp.write(resp.read())

asyncio.run(test_img())
