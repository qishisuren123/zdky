import asyncio
import os
from pathlib import Path

from twikit import Client

COOKIES_PATH = Path(os.getenv("TWITTER_COOKIES_PATH", "twitter_cookies.local.json")).expanduser()
PROXY = os.getenv("AUTORESEARCH_PROXY_URL")

client = Client("en-US", proxy=PROXY, timeout=30)


async def main():
    if not COOKIES_PATH.exists():
        raise RuntimeError("Set TWITTER_COOKIES_PATH to a local cookie JSON file before running this smoke test.")

    client.load_cookies(str(COOKIES_PATH))
    print("cookies loaded from TWITTER_COOKIES_PATH")

    user = await client.get_user_by_screen_name("OpenAI")
    print(user.id, user.screen_name)


asyncio.run(main())
