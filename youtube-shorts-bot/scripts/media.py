"""
Media assembly:
  - voiceover via gTTS (free text-to-speech)
  - vertical background from Pexels stock video (falls back to a gradient)
  - burned-in captions
  - composited into a 9:16 MP4 sized for YouTube Shorts

Targets moviepy 2.x (TextClip renders via Pillow — no ImageMagick needed).
Requires ffmpeg on PATH (moviepy wraps it). Install: apt install ffmpeg / brew install ffmpeg
"""

import os
import sys
import tempfile

import requests

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from config import settings  # noqa: E402

from gtts import gTTS  # noqa: E402
from moviepy import (  # noqa: E402  (moviepy 2.x: import from package root, not moviepy.editor)
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)


# A TextClip in moviepy 2.x requires an explicit font file path. Pick the first
# that exists; allow an override via settings.CAPTION_FONT.
_FONT_CANDIDATES = [
    getattr(settings, "CAPTION_FONT", None),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Ubuntu (apt install fonts-dejavu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",     # macOS
    "/System/Library/Fonts/Helvetica.ttc",
]


def _resolve_font():
    for path in _FONT_CANDIDATES:
        if path and os.path.exists(path):
            return path
    raise RuntimeError(
        "No caption font found. Install one (Ubuntu: `sudo apt install fonts-dejavu`) "
        "or set CAPTION_FONT in config/settings.py to a .ttf path."
    )


def synthesize_voiceover(narration, out_path):
    """Render narration to an MP3 using gTTS."""
    gTTS(text=narration, lang="en", slow=False).save(out_path)
    return out_path


def fetch_background_video(search_terms, duration, out_path):
    """
    Download a vertical stock clip from Pexels matching one of the search terms.
    Returns the path, or None to signal the caller to use a gradient fallback.
    """
    if not settings.PEXELS_API_KEY:
        print("[media] no PEXELS_API_KEY set — using gradient background")
        return None

    for term in search_terms:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={"query": term, "orientation": "portrait", "per_page": 5},
                timeout=20,
            )
            r.raise_for_status()
            videos = r.json().get("videos", [])
            for video in videos:
                files = sorted(
                    (f for f in video["video_files"] if f.get("height", 0) >= 1280),
                    key=lambda f: f.get("height", 0),
                )
                if not files:
                    continue
                link = files[0]["link"]
                with requests.get(link, stream=True, timeout=60) as dl:
                    dl.raise_for_status()
                    with open(out_path, "wb") as fh:
                        for chunk in dl.iter_content(chunk_size=1 << 16):
                            fh.write(chunk)
                print(f"[media] background: '{term}' -> {os.path.basename(out_path)}")
                return out_path
        except requests.RequestException as e:
            print(f"  ! pexels '{term}' failed: {e}", file=sys.stderr)
    return None


def _background_clip(search_terms, duration, workdir):
    """A 9:16 background clip of the given duration: stock video, looped, or gradient."""
    size = (settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT)
    raw = fetch_background_video(search_terms, duration, os.path.join(workdir, "bg.mp4"))
    if raw:
        clip = VideoFileClip(raw).without_audio()
        # crop/scale to fill 9:16 (moviepy 2.x: resized / cropped / subclipped)
        clip = clip.resized(height=settings.VIDEO_HEIGHT)
        if clip.w < settings.VIDEO_WIDTH:
            clip = clip.resized(width=settings.VIDEO_WIDTH)
        clip = clip.cropped(
            x_center=clip.w / 2, y_center=clip.h / 2,
            width=settings.VIDEO_WIDTH, height=settings.VIDEO_HEIGHT,
        )
        # loop to cover the full duration
        if clip.duration < duration:
            n = int(duration / clip.duration) + 1
            clip = concatenate_videoclips([clip] * n)
        return clip.subclipped(0, duration)

    # fallback: solid dark teal background (calm, readable)
    return ColorClip(size=size, color=(18, 46, 56), duration=duration)


def _caption_clips(captions, duration):
    """Evenly time captions across the video, centered, with a readable stroke."""
    if not captions:
        return []
    font = _resolve_font()
    each = duration / len(captions)
    clips = []
    for i, line in enumerate(captions):
        txt = TextClip(
            font=font,
            text=line,
            font_size=80,
            color="white",
            stroke_color="black",
            stroke_width=3,
            method="caption",
            size=(int(settings.VIDEO_WIDTH * 0.85), None),
            text_align="center",
        )
        txt = (
            txt.with_start(i * each)
            .with_duration(each)
            .with_position(("center", "center"))
        )
        clips.append(txt)
    return clips


def assemble(script, out_path):
    """Build the final MP4 from a script dict. Returns out_path."""
    with tempfile.TemporaryDirectory() as workdir:
        # 1. voiceover defines the video length. Clamp duration to the audio so
        #    ffmpeg never reads an audio frame past the clip's end, and to MAX.
        vo_path = synthesize_voiceover(script["narration"], os.path.join(workdir, "vo.mp3"))
        voice = AudioFileClip(vo_path)
        # shave a small epsilon so the timeline ends just inside the audio
        # (avoids ffmpeg reading one frame past the clip end at the boundary).
        duration = min(voice.duration - 0.05, settings.MAX_DURATION_SECONDS)
        voice = voice.subclipped(0, duration)

        # 2. background + captions
        background = _background_clip(script["search_terms"], duration, workdir)
        captions = _caption_clips(script["captions"], duration)

        # 3. composite (moviepy 2.x: with_audio / with_duration)
        video = CompositeVideoClip([background, *captions], size=(settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT))
        video = video.with_audio(voice).with_duration(duration)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        video.write_videofile(
            out_path,
            fps=settings.FPS,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="medium",
            logger=None,
        )
        voice.close()
        video.close()
    print(f"[media] wrote {out_path}")
    return out_path
