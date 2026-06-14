"""
Download royalty-free background music into assets/music/.

There is no clean free "music API" the way Pexels serves video, so this reads a
list of direct .mp3 URLs you provide in config/music_sources.txt (one per line)
and downloads any that aren't already present. media.py then picks one at random
per video and mixes it quietly under the voiceover.

Where to get royalty-free / CC0 tracks and their direct URLs:
  - Pixabay Music   https://pixabay.com/music/   (Pixabay license, no attribution)
  - YouTube Audio Library  (in YouTube Studio — download, then host or add locally)
  - Free Music Archive  https://freemusicarchive.org/  (check each track's license)
  - Incompetech (Kevin MacLeod)  https://incompetech.com/  (CC-BY — needs credit)

On Pixabay: open a track, click Download, then copy the resulting .mp3 link into
config/music_sources.txt. Or just download the files manually straight into
assets/music/ and skip this script entirely.

Usage:  python3 scripts/fetch_music.py
"""

import os
import sys

import requests

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from config import settings  # noqa: E402

SOURCES_FILE = os.path.join(settings.BASE_DIR, "config", "music_sources.txt")


def _safe_name(url, idx):
    base = url.split("?")[0].rstrip("/").split("/")[-1]
    if not base.lower().endswith(".mp3"):
        base = f"track_{idx}.mp3"
    # avoid path traversal / weird chars
    return os.path.basename(base) or f"track_{idx}.mp3"


def fetch():
    os.makedirs(settings.MUSIC_DIR, exist_ok=True)

    if not os.path.exists(SOURCES_FILE):
        print(f"No {SOURCES_FILE} found.")
        print("Create it with one direct .mp3 URL per line (see this file's docstring),")
        print(f"or just drop .mp3 files straight into {settings.MUSIC_DIR}.")
        return

    with open(SOURCES_FILE) as fh:
        urls = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]

    if not urls:
        print(f"{SOURCES_FILE} is empty — add some .mp3 URLs.")
        return

    downloaded = 0
    for idx, url in enumerate(urls, 1):
        dest = os.path.join(settings.MUSIC_DIR, _safe_name(url, idx))
        if os.path.exists(dest):
            print(f"  = exists, skip: {os.path.basename(dest)}")
            continue
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if "audio" not in ctype and not url.lower().endswith(".mp3"):
                    print(f"  ! not audio ({ctype}); skipping {url}", file=sys.stderr)
                    continue
                with open(dest, "wb") as out:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        out.write(chunk)
            print(f"  + downloaded: {os.path.basename(dest)}")
            downloaded += 1
        except requests.RequestException as e:
            print(f"  ! failed {url}: {e}", file=sys.stderr)

    have = len([f for f in os.listdir(settings.MUSIC_DIR) if f.lower().endswith(".mp3")])
    print(f"\nDone. {downloaded} new track(s). {have} total in {settings.MUSIC_DIR}.")


if __name__ == "__main__":
    fetch()
