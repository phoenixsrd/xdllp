import asyncio
import os
import re
import tempfile

import requests
import yt_dlp
from telethon import TelegramClient, events

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env():
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_IDS = {
    int(x)
    for x in os.environ.get("ALLOWED_IDS", "").replace(" ", "").split(",")
    if x
}

client = TelegramClient(os.path.join(BASE_DIR, "bot_session"), API_ID, API_HASH)

URL_RE = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/(\w+)/status/(\d+)")
MAX_SIZE = 2000 * 1024 * 1024
HEADERS = {"User-Agent": "Mozilla/5.0"}
FORMAT = "best[protocol^=http][ext=mp4]/best[protocol^=http]/best"


def pick_video(media):
    for v in media.get("videos") or []:
        if v.get("url"):
            return v["url"]
    for m in media.get("all") or []:
        if m.get("type") in ("video", "gif") and m.get("url"):
            return m["url"]
    return None


def from_fx(user, tweet_id):
    try:
        r = requests.get(
            f"https://api.fxtwitter.com/{user}/status/{tweet_id}",
            headers=HEADERS,
            timeout=20,
        )
        print("fxtwitter:", r.status_code, flush=True)
        if r.status_code != 200:
            return None
        tweet = r.json().get("tweet") or {}
    except Exception as e:
        print("fxtwitter erro:", e, flush=True)
        return None

    url = pick_video(tweet.get("media") or {})
    if url:
        return url
    quote = tweet.get("quote") or {}
    return pick_video(quote.get("media") or {})


def from_ytdlp(post_url):
    opts = {
        "format": FORMAT,
        "noplaylist": True,
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(post_url, download=False)
            if info.get("entries"):
                info = next(e for e in info["entries"] if e)
            return info.get("url")
    except Exception as e:
        print("yt-dlp erro:", e, flush=True)
        return None


def remote_size(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return int(r.headers.get("Content-Length", 0))
    except Exception:
        return 0


def download(url, path):
    size = 0
    with requests.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    return False
                f.write(chunk)
    return True


def allowed(event):
    return not ALLOWED_IDS or event.sender_id in ALLOWED_IDS


@client.on(events.NewMessage(pattern=r"^/(start|help)"))
async def start(event):
    if not allowed(event):
        return
    await event.reply("Envie o link de um post do X com vídeo.")


@client.on(events.NewMessage(incoming=True))
async def handle(event):
    if not allowed(event):
        return

    text = event.raw_text or ""
    if text.startswith("/"):
        return

    match = URL_RE.search(text)
    if not match:
        await event.reply("Envie um link válido de post do X.")
        return

    user, tweet_id = match.groups()
    post_url = match.group(0)
    status = await event.reply("Verificando...")

    video_url = await asyncio.to_thread(from_fx, user, tweet_id)
    if not video_url:
        video_url = await asyncio.to_thread(from_ytdlp, post_url)

    if not video_url:
        await status.edit("Não achei vídeo nesse post.")
        return

    if await asyncio.to_thread(remote_size, video_url) > MAX_SIZE:
        await status.edit("Vídeo maior que 2 GB, não dá para enviar.")
        return

    await status.edit("Baixando...")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"{tweet_id}.mp4")
        try:
            ok = await asyncio.to_thread(download, video_url, path)
        except Exception as e:
            print("download erro:", e, flush=True)
            await status.edit("Falha ao baixar o vídeo.")
            return

        if not ok:
            await status.edit("Vídeo maior que 2 GB, não dá para enviar.")
            return

        await status.edit("Enviando... 0%")
        last = {"p": -1}

        async def progress(sent, total):
            p = int(sent * 100 / total)
            if p - last["p"] >= 10:
                last["p"] = p
                print(f"upload {p}%", flush=True)
                try:
                    await status.edit(f"Enviando... {p}%")
                except Exception:
                    pass

        try:
            await client.send_file(
                event.chat_id,
                path,
                reply_to=event.id,
                supports_streaming=True,
                progress_callback=progress,
            )
        except Exception as e:
            print("envio erro:", repr(e), flush=True)
            await status.edit("Falha ao enviar o vídeo.")
            return

    await status.delete()


client.start(bot_token=BOT_TOKEN)
print("Bot online", flush=True)
client.run_until_disconnected()