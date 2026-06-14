"""
Content generation — the HYBRID approach:
  1. Pull a raw fact from a TRUSTED source (Wikipedia / Numbers API).
  2. Use Claude to verify it's positive + factual and rewrite it into a
     punchy ~45-second short-form script with an on-screen caption track.

Claude is instructed NOT to invent facts — only to rephrase the sourced fact.
This keeps factual reliability high while making the script engaging.
"""

import json
import random
import sys

import requests

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from config import settings  # noqa: E402

import anthropic  # noqa: E402


# ---------------------------------------------------------------------------
# Step 1: fetch a raw fact from a trusted source
# ---------------------------------------------------------------------------
_UA = {"User-Agent": "positivity-shorts-bot/1.0 (educational shorts)"}

# Subjects we skip — keeps the channel positive and broadly relatable.
_SKIP_KEYWORDS = (
    "death", "killed", "war", "massacre", "murder", "disaster", "suicide",
    "shooting", "attack", "genocide", "porn", "rape", "abuse",
)


def fetch_raw_fact():
    """Return (title, fact_text, source_url) from a trusted, popular English source."""
    fetchers = [_wikipedia_most_read, _wikipedia_featured_article, _wikipedia_random]
    for fetch in fetchers:
        try:
            result = fetch()
            if result and result[1]:
                return result
        except requests.RequestException as e:
            print(f"  ! source failed ({fetch.__name__}): {e}", file=sys.stderr)
    raise RuntimeError("All fact sources failed — check your network connection.")


def _is_relatable(title, extract):
    """Filter out thin, non-English-relevant, or negative subjects."""
    if len(extract) < 120:
        return False
    blob = (title + " " + extract).lower()
    return not any(bad in blob for bad in _SKIP_KEYWORDS)


def _summary_for(title):
    """Fetch the plain-English summary for a Wikipedia page title."""
    r = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}",
        headers=_UA, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return (
        data.get("title", title),
        data.get("extract", "").strip(),
        data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    )


def _wikipedia_most_read():
    """Yesterday's most-read English Wikipedia articles — popular, engaging topics."""
    # Use a recent fixed-ish date; the feed needs YYYY/MM/DD.
    import datetime
    day = datetime.date.today() - datetime.timedelta(days=2)
    r = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/feed/featured/{day:%Y/%m/%d}",
        headers=_UA, timeout=15,
    )
    r.raise_for_status()
    articles = r.json().get("mostread", {}).get("articles", [])
    random.shuffle(articles)
    for art in articles[:20]:
        title = art.get("title", "")
        extract = art.get("extract", "").strip()
        url = art.get("content_urls", {}).get("desktop", {}).get("page", "")
        if _is_relatable(title.replace("_", " "), extract):
            return title.replace("_", " "), extract, url
    return None


def _wikipedia_featured_article():
    """Today's featured article — curated, high-quality English content."""
    import datetime
    day = datetime.date.today() - datetime.timedelta(days=1)
    r = requests.get(
        f"https://en.wikipedia.org/api/rest_v1/feed/featured/{day:%Y/%m/%d}",
        headers=_UA, timeout=15,
    )
    r.raise_for_status()
    tfa = r.json().get("tfa", {})
    title = tfa.get("title", "").replace("_", " ")
    extract = tfa.get("extract", "").strip()
    url = tfa.get("content_urls", {}).get("desktop", {}).get("page", "")
    if _is_relatable(title, extract):
        return title, extract, url
    return None


def _wikipedia_random():
    """Last-resort fallback: a random article that passes the relatability filter."""
    for _ in range(8):
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/random/summary",
            headers=_UA, timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        title = data.get("title", "")
        extract = data.get("extract", "").strip()
        url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        if _is_relatable(title, extract):
            return title, extract, url
    return None


# ---------------------------------------------------------------------------
# Step 2: rewrite into a short-form script with Claude
# ---------------------------------------------------------------------------
SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "suitable": {
            "type": "boolean",
            "description": "True only if the fact is positive/neutral, factual, and safe for a general audience.",
        },
        "reason_if_unsuitable": {"type": "string"},
        "title": {"type": "string", "description": "YouTube Shorts title in ENGLISH, <= 70 chars. Curiosity-driven, no clickbait."},
        "narration": {
            "type": "string",
            "description": (
                "Spoken voiceover in ENGLISH, STRICTLY 45-65 words total (this must fit in a "
                "20-30 second video — do not exceed 65 words). MUST open with a 1-sentence HOOK "
                "(a surprising question or statement) in the first 3 seconds. Then deliver the "
                "fact conversationally in 2-3 tight sentences, and end with a warm one-line "
                "takeaway. Plain words, short sentences, no emojis, no markdown — it will be "
                "read aloud by text-to-speech."
            ),
        },
        "search_terms": {
            "type": "array",
            "description": "2-4 concrete, visual ENGLISH search terms for background stock footage (e.g. 'ocean waves aerial', 'city timelapse night').",
            "items": {"type": "string"},
        },
        "description": {"type": "string", "description": "YouTube description in ENGLISH, 1-2 sentences + 3-5 relevant hashtags."},
    },
    "required": [
        "suitable",
        "reason_if_unsuitable",
        "title",
        "narration",
        "search_terms",
        "description",
    ],
    "additionalProperties": False,
}


def _supports_adaptive_thinking(model):
    """Haiku does not support adaptive thinking; Opus 4.6+/Sonnet 4.6/Fable do."""
    m = model.lower()
    if "haiku" in m:
        return False
    return any(tag in m for tag in ("opus-4-6", "opus-4-7", "opus-4-8", "sonnet-4-6", "fable", "mythos"))


def build_script(title, raw_fact, source_url):
    """Use Claude to turn a raw fact into an engaging, English short-form script."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    system = (
        "You are a scriptwriter for short, uplifting, FACTUAL YouTube Shorts aimed at a "
        f"global ENGLISH-speaking audience. The channel's tone is {settings.TONE}. "
        "You turn a sourced fact into a punchy 20-30 second script that hooks viewers "
        "in the first 3 seconds and keeps them watching. CRITICAL RULES:\n"
        "- Write EVERYTHING in clear, natural English.\n"
        "- Do NOT invent, exaggerate, or add any fact not present in the source text. "
        "Only rephrase and frame what you are given.\n"
        "- Make it ENGAGING: open with a hook, use vivid plain language, build a little "
        "curiosity, and land a satisfying takeaway. Avoid dry encyclopedia phrasing.\n"
        "- If the subject is foreign or niche, frame it so an English-speaking viewer "
        "anywhere instantly sees why it's interesting.\n"
        "- If the fact is negative, tragic, controversial, or not safe for a positivity "
        "channel, set suitable=false and explain why."
    )

    kwargs = dict(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Subject: {title}\n\n"
                    f"Sourced fact:\n\"\"\"\n{raw_fact}\n\"\"\"\n"
                    f"Source URL: {source_url}\n\n"
                    "Write the engaging English short-form script as structured output."
                ),
            }
        ],
        output_config={
            "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}
        },
    )

    # Adaptive thinking is only supported on Opus 4.6+/Sonnet 4.6/Fable models —
    # NOT on Haiku. Only send it when the configured model supports it.
    if _supports_adaptive_thinking(settings.CLAUDE_MODEL):
        kwargs["thinking"] = {"type": "adaptive"}

    response = client.messages.create(**kwargs)

    text = next(b.text for b in response.content if b.type == "text")
    script = json.loads(text)
    script["source_url"] = source_url
    script["raw_fact"] = raw_fact
    script["subject"] = title
    return script


def generate():
    """Full content step: returns a vetted script dict, retrying if unsuitable."""
    for attempt in range(1, 6):
        title, raw_fact, source_url = fetch_raw_fact()
        print(f"[content] attempt {attempt}: sourced '{title}' from {source_url}")
        script = build_script(title, raw_fact, source_url)
        if script["suitable"]:
            print(f"[content] script ready: {script['title']!r}")
            return script
        print(f"[content] rejected (not suitable): {script['reason_if_unsuitable']}")
    raise RuntimeError("Could not source a suitable positive fact after 5 attempts.")


if __name__ == "__main__":
    from pprint import pprint

    pprint(generate())
