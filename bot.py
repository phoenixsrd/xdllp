import asyncio
import logging
import os
import re
import tempfile
import time
from urllib.parse import urlparse

import requests
import yt_dlp
from dotenv import load_dotenv
from telethon import TelegramClient, events

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xdllp")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_IDS = {
    int(x)
    for x in os.environ.get("ALLOWED_IDS", "").replace(" ", "").split(",")
    if x
}

URL_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter|fxtwitter|fixupx|vxtwitter)\.com/(\w+)/status/(\d+)"
)
MAX_SIZE = 2000 * 1024 * 1024
DEADLINE = 600
CACHE_LIMIT = 200
MAX_LINKS_PER_MESSAGE = 5
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "3"))
HEADERS = {"User-Agent": "Mozilla/5.0"}
FORMAT = "best[protocol^=http][ext=mp4]/best[protocol^=http]/best"

SEM = asyncio.Semaphore(MAX_PARALLEL)
CACHE = {}


class TooBig(Exception):
    pass


def trusted(url):
    host = urlparse(url).hostname or ""
    return host == "twimg.com" or host.endswith(".twimg.com")


def pick_video(media):
    for v in media.get("videos") or []:
        if v.get("url"):
            return v["url"]
    for m in media.get("all") or []:
        if m.get("type") in ("video", "gif") and m.get("url"):
            return m["url"]
    return None


def build_caption(tweet, post_url):
    author = tweet.get("author") or {}
    head = f"{author.get('name', '')} (@{author.get('screen_name', '')})".strip()
    body = (tweet.get("text") or "").strip()
    return f"{head}\n{post_url}\n\n{body}"[:1024]


def from_fx(user, tweet_id, post_url):
    try:
        r = requests.get(
            f"https://api.fxtwitter.com/{user}/status/{tweet_id}",
            headers=HEADERS,
            timeout=20,
        )
        if r.status_code != 200:
            log.warning("fxtwitter status %s", r.status_code)
            return None
        tweet = r.json().get("tweet") or {}
    except Exception:
        log.exception("fxtwitter falhou")
        return None

    source = tweet
    url = pick_video(source.get("media") or {})
    if not url:
        source = tweet.get("quote") or {}
        url = pick_video(source.get("media") or {})
    if not url:
        return None
    return url, build_caption(source, post_url)


def from_ytdlp(post_url):
    opts = {
        "format": FORMAT,
        "noplaylist": True,
        "quiet": True,
        "socket_timeout": 20,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(post_url, download=False)
            if info.get("entries"):
                info = next(e for e in info["entries"] if e)
            return info.get("url")
    except Exception:
        log.exception("yt-dlp falhou")
        return None


def resolve(user, tweet_id, post_url):
    found = from_fx(user, tweet_id, post_url)
    if found and trusted(found[0]):
        return found
    url = from_ytdlp(post_url)
    if url and trusted(url):
        return url, post_url
    return None


def download(url, path):
    start = time.monotonic()
    size = 0
    with requests.get(url, headers=HEADERS, stream=True, timeout=(10, 30)) as r:
        r.raise_for_status()
        if int(r.headers.get("Content-Length", 0)) > MAX_SIZE:
            raise TooBig()
        with open(path, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                size += len(chunk)
                if size > MAX_SIZE or time.monotonic() - start > DEADLINE:
                    raise TooBig()
                f.write(chunk)


def make_progress(status):
    state = {"t": 0.0, "p": -1}

    async def progress(sent, total):
        p = int(sent * 100 / total) if total else 0
        now = time.monotonic()
        if p == state["p"] or now - state["t"] < 3:
            return
        state["p"] = p
        state["t"] = now
        try:
            await status.edit(f"Enviando... {p}%")
        except Exception:
            pass

    return progress


def remember(tweet_id, media, caption):
    CACHE[tweet_id] = (media, caption)
    while len(CACHE) > CACHE_LIMIT:
        CACHE.pop(next(iter(CACHE)))


def allowed(event):
    return not ALLOWED_IDS or event.sender_id in ALLOWED_IDS


async def work(event, status, user, tweet_id, post_url):
    cached = CACHE.get(tweet_id)
    if cached:
        try:
            await event.client.send_file(
                event.chat_id, cached[0], caption=cached[1], reply_to=event.id
            )
            await status.delete()
            return
        except Exception:
            log.exception("reenvio do cache falhou")
            CACHE.pop(tweet_id, None)

    found = await asyncio.to_thread(resolve, user, tweet_id, post_url)
    if not found:
        await status.edit("Não achei vídeo nesse post.")
        return
    video_url, caption = found

    await status.edit("Baixando...")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"{tweet_id}.mp4")
        try:
            await asyncio.to_thread(download, video_url, path)
        except TooBig:
            await status.edit("Vídeo maior que 2 GB ou download lento demais.")
            return
        except Exception:
            log.exception("download falhou")
            await status.edit("Falha ao baixar o vídeo.")
            return

        await status.edit("Enviando... 0%")
        try:
            sent = await event.client.send_file(
                event.chat_id,
                path,
                caption=caption,
                reply_to=event.id,
                supports_streaming=True,
                progress_callback=make_progress(status),
            )
        except Exception:
            log.exception("envio falhou")
            await status.edit("Falha ao enviar o vídeo.")
            return

    remember(tweet_id, sent.media, caption)
    await status.delete()


async def process(event, user, tweet_id):
    post_url = f"https://x.com/{user}/status/{tweet_id}"
    status = await event.reply("Na fila...")
    async with SEM:
        await status.edit("Verificando...")
        await work(event, status, user, tweet_id, post_url)


async def on_start(event):
    if allowed(event):
        await event.reply("Envie um ou mais links de posts do X com vídeo.")


async def on_message(event):
    if not allowed(event):
        return
    text = event.raw_text or ""
    if text.startswith("/"):
        return

    jobs = {tid: user for user, tid in URL_RE.findall(text)}
    if not jobs:
        if event.is_private:
            await event.reply("Envie um link válido de post do X.")
        return

    await asyncio.gather(
        *(
            process(event, user, tid)
            for tid, user in list(jobs.items())[:MAX_LINKS_PER_MESSAGE]
        )
    )


async def main():
    client = TelegramClient(os.path.join(BASE_DIR, "bot_session"), API_ID, API_HASH)
    client.add_event_handler(on_start, events.NewMessage(pattern=r"^/(start|help)"))
    client.add_event_handler(on_message, events.NewMessage(incoming=True))
    await client.start(bot_token=BOT_TOKEN)
    log.info("Bot online")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())