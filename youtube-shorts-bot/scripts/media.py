"""
Media assembly:
  - voiceover via gTTS (free Google text-to-speech)
  - dynamic visuals: several rotating vertical stock clips with a slow Ken Burns
    zoom, an optional title card, and time-synced English subtitles
  - optional royalty-free background music mixed quietly under the voice
  - composited into a 9:16 MP4 sized for YouTube Shorts

Targets moviepy 2.x (TextClip renders via Pillow — no ImageMagick needed).
Requires ffmpeg on PATH (moviepy wraps it). Install: apt install ffmpeg / brew install ffmpeg
"""

import glob
import os
import random
import sys
import tempfile

import requests

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from config import settings  # noqa: E402

from gtts import gTTS  # noqa: E402
from moviepy import (  # noqa: E402  (moviepy 2.x: import from package root)
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.audio.fx import AudioFadeOut, AudioLoop, MultiplyVolume  # noqa: E402
from moviepy.video.fx import Resize  # noqa: E402


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    getattr(settings, "CAPTION_FONT", None),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Ubuntu
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


# ---------------------------------------------------------------------------
# Voiceover
# ---------------------------------------------------------------------------
def synthesize_voiceover(narration, out_path):
    """Render narration to MP3 using gTTS (free Google text-to-speech)."""
    gTTS(text=narration, lang="en", slow=False).save(out_path)
    print("[media] voiceover: gTTS")
    return out_path


# ---------------------------------------------------------------------------
# Stock footage
# ---------------------------------------------------------------------------
def _download_pexels_clip(term, out_path):
    """Download one portrait stock clip for a term. Returns path or None."""
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": settings.PEXELS_API_KEY},
            params={"query": term, "orientation": "portrait", "per_page": 8},
            timeout=20,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        random.shuffle(videos)
        for video in videos:
            files = sorted(
                (f for f in video["video_files"] if f.get("height", 0) >= 1280),
                key=lambda f: f.get("height", 0),
            )
            if not files:
                continue
            with requests.get(files[0]["link"], stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with open(out_path, "wb") as fh:
                    for chunk in dl.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
            return out_path
    except requests.RequestException as e:
        print(f"  ! pexels '{term}' failed: {e}", file=sys.stderr)
    return None


def _fit_vertical(clip):
    """Scale + center-crop a clip to fill the 9:16 frame."""
    clip = clip.with_effects([Resize(height=settings.VIDEO_HEIGHT)])
    if clip.w < settings.VIDEO_WIDTH:
        clip = clip.with_effects([Resize(width=settings.VIDEO_WIDTH)])
    return clip.cropped(
        x_center=clip.w / 2, y_center=clip.h / 2,
        width=settings.VIDEO_WIDTH, height=settings.VIDEO_HEIGHT,
    )


def _ken_burns(clip):
    """Slow zoom from 1.0x to ~1.08x over the clip for gentle motion."""
    if not getattr(settings, "KEN_BURNS", False):
        return clip
    dur = clip.duration
    zoomed = clip.with_effects([Resize(lambda t: 1.0 + 0.08 * (t / dur))])
    # re-crop back to frame after zoom so edges don't show
    return zoomed.cropped(
        x_center=zoomed.w / 2, y_center=zoomed.h / 2,
        width=settings.VIDEO_WIDTH, height=settings.VIDEO_HEIGHT,
    )


def _background(search_terms, duration, workdir):
    """
    Build a dynamic background: several different stock clips back-to-back, each
    with a slow zoom. Falls back to a single looped clip, then a solid color.
    """
    size = (settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT)
    if not settings.PEXELS_API_KEY:
        print("[media] no PEXELS_API_KEY — using solid background")
        return ColorClip(size=size, color=(18, 46, 56), duration=duration)

    n_clips = max(1, getattr(settings, "CLIPS_PER_VIDEO", 3))
    # cycle through the search terms to get visual variety
    terms = (search_terms * n_clips)[:n_clips]
    per = duration / n_clips

    segments = []
    for i, term in enumerate(terms):
        path = _download_pexels_clip(term, os.path.join(workdir, f"bg{i}.mp4"))
        if not path:
            continue
        try:
            clip = VideoFileClip(path).without_audio()
        except Exception as e:
            print(f"  ! could not open clip for '{term}': {e}", file=sys.stderr)
            continue
        clip = _fit_vertical(clip)
        # loop/trim this segment to exactly `per` seconds
        if clip.duration < per:
            reps = int(per / clip.duration) + 1
            clip = concatenate_videoclips([clip] * reps)
        clip = clip.subclipped(0, per)
        clip = _ken_burns(clip)
        segments.append(clip)
        print(f"[media] clip {i + 1}/{n_clips}: '{term}'")

    if not segments:
        return ColorClip(size=size, color=(18, 46, 56), duration=duration)

    bg = concatenate_videoclips(segments)
    # ensure exact length
    if bg.duration < duration:
        bg = concatenate_videoclips([bg, bg]).subclipped(0, duration)
    return bg.subclipped(0, duration)


# ---------------------------------------------------------------------------
# Subtitles
# ---------------------------------------------------------------------------
def _chunk_narration(narration, max_words=3):
    """Split narration into short subtitle phrases (<= max_words each)."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", narration.strip())
    phrases = []
    for sentence in sentences:
        words = sentence.split()
        for i in range(0, len(words), max_words):
            phrase = " ".join(words[i : i + max_words]).strip()
            if phrase:
                phrases.append(phrase)
    return phrases


def _caption_clips(narration, duration, font):
    """English subtitles derived from narration, time-synced to the voiceover."""
    phrases = _chunk_narration(narration)
    if not phrases:
        return []
    total_words = sum(len(p.split()) for p in phrases)
    clips = []
    t = 0.0
    for phrase in phrases:
        share = len(phrase.split()) / total_words
        seg = max(0.8, share * duration)
        txt = TextClip(
            font=font,
            text=phrase,
            font_size=58,
            color="white",
            stroke_color="black",
            stroke_width=3,
            method="caption",
            size=(int(settings.VIDEO_WIDTH * 0.80), None),
            text_align="center",
        )
        txt = (
            txt.with_start(t)
            .with_duration(seg)
            .with_position(("center", int(settings.VIDEO_HEIGHT * 0.6)))
        )
        clips.append(txt)
        t += seg
        if t >= duration:
            break
    return clips


def _title_card(title, font):
    """A short opening title card overlay (first ~2.5s) for a stronger hook."""
    if not getattr(settings, "SHOW_TITLE_CARD", False) or not title:
        return []
    card = TextClip(
        font=font,
        text=title,
        font_size=62,
        color="white",
        stroke_color="black",
        stroke_width=3,
        method="caption",
        size=(int(settings.VIDEO_WIDTH * 0.80), None),
        text_align="center",
    )
    card = (
        card.with_start(0)
        .with_duration(2.5)
        .with_position(("center", int(settings.VIDEO_HEIGHT * 0.28)))
    )
    return [card]


# ---------------------------------------------------------------------------
# Music
# ---------------------------------------------------------------------------
def _mix_music(voice, duration):
    """
    Mix a random royalty-free track from assets/music under the voiceover.
    Returns (audio_clip, track_basename_or_None) so the caller can record a credit.
    """
    if not getattr(settings, "ENABLE_MUSIC", False):
        return voice, None
    tracks = glob.glob(os.path.join(settings.MUSIC_DIR, "*.mp3"))
    if not tracks:
        return voice, None  # no music available — voice only
    track = random.choice(tracks)
    try:
        music = AudioFileClip(track).with_effects([
            AudioLoop(duration=duration),
            MultiplyVolume(settings.MUSIC_VOLUME),
            AudioFadeOut(1.0),  # gentle fade in the last second
        ])
        print(f"[media] music: {os.path.basename(track)} @ {settings.MUSIC_VOLUME}")
        return CompositeAudioClip([music, voice]), os.path.basename(track)
    except Exception as e:
        print(f"  ! music mix failed ({e}); voice only", file=sys.stderr)
        return voice, None


def _music_credit(track_basename):
    """
    Look up an attribution string for a track from config/music_credits.json.
    Returns the credit text, or None if the track needs no attribution (e.g. Pixabay/CC0).
    """
    if not track_basename:
        return None
    credits_file = os.path.join(settings.BASE_DIR, "config", "music_credits.json")
    if not os.path.exists(credits_file):
        return None
    import json

    try:
        with open(credits_file) as fh:
            credits = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"  ! could not read music_credits.json ({e})", file=sys.stderr)
        return None
    return credits.get(track_basename) or None


# ---------------------------------------------------------------------------
# Assemble
# ---------------------------------------------------------------------------
def assemble(script, out_path):
    """Build the final MP4 from a script dict. Returns out_path."""
    font = _resolve_font()
    with tempfile.TemporaryDirectory() as workdir:
        # 1. voiceover defines the length
        vo_path = synthesize_voiceover(script["narration"], os.path.join(workdir, "vo.mp3"))
        voice = AudioFileClip(vo_path)
        duration = min(voice.duration - 0.05, settings.MAX_DURATION_SECONDS)
        voice = voice.subclipped(0, duration)

        # 2. visuals
        background = _background(script["search_terms"], duration, workdir)
        overlays = _title_card(script.get("title", ""), font) + _caption_clips(
            script["narration"], duration, font
        )

        # 3. audio (voice + optional music). Record any required credit on the
        #    script dict so the uploader can append it to the description.
        final_audio, track = _mix_music(voice, duration)
        credit = _music_credit(track)
        if credit:
            script["music_credit"] = credit
            print(f"[media] music credit: {credit}")

        # 4. composite
        video = CompositeVideoClip(
            [background, *overlays], size=(settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT)
        )
        video = video.with_audio(final_audio).with_duration(duration)

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
