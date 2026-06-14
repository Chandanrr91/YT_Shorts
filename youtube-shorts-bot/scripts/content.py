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
def fetch_raw_fact():
    """Return (fact_text, source_url) from a trusted, factual source."""
    fetchers = [_wikipedia_featured, _numbers_fact]
    random.shuffle(fetchers)
    for fetch in fetchers:
        try:
            result = fetch()
            if result and result[0]:
                return result
        except requests.RequestException as e:
            print(f"  ! source failed ({fetch.__name__}): {e}", file=sys.stderr)
    raise RuntimeError("All fact sources failed — check your network connection.")


def _wikipedia_featured():
    """Wikipedia's random article summary — real, citable content."""
    r = requests.get(
        "https://en.wikipedia.org/api/rest_v1/page/random/summary",
        headers={"User-Agent": "positivity-shorts-bot/1.0"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    extract = data.get("extract", "").strip()
    url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    if len(extract) < 80:  # too thin to build a script from
        return None
    return extract, url


def _numbers_fact():
    """Numbers API — a factual numeric trivia tidbit."""
    r = requests.get("http://numbersapi.com/random/trivia?json", timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("text", "").strip(), "http://numbersapi.com"


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
        "title": {"type": "string", "description": "YouTube Shorts title, <= 80 chars, no clickbait."},
        "narration": {
            "type": "string",
            "description": "Spoken voiceover, ~90-130 words, warm and factual. No emojis.",
        },
        "captions": {
            "type": "array",
            "description": "On-screen caption lines, in order, each a short phrase (<= 8 words).",
            "items": {"type": "string"},
        },
        "search_terms": {
            "type": "array",
            "description": "2-4 concrete visual search terms for background stock footage.",
            "items": {"type": "string"},
        },
        "description": {"type": "string", "description": "YouTube description, 1-2 sentences + relevant hashtags."},
    },
    "required": [
        "suitable",
        "reason_if_unsuitable",
        "title",
        "narration",
        "captions",
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


def build_script(raw_fact, source_url):
    """Use Claude to turn a raw fact into a structured short-form script."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    system = (
        "You are a scriptwriter for short, uplifting, FACTUAL YouTube Shorts. "
        f"The channel's tone is {settings.TONE}. "
        "You will be given a raw fact from a trusted source. Your job is to rephrase "
        "it into an engaging short-form script. CRITICAL RULES:\n"
        "- Do NOT invent, exaggerate, or add any fact not present in the source text. "
        "Only rephrase what you are given.\n"
        "- If the source fact is negative, tragic, controversial, or not safe for a "
        "general positivity channel, set suitable=false and explain why.\n"
        "- Keep narration spoken-word natural (it will be read by text-to-speech)."
    )

    kwargs = dict(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Source fact:\n\"\"\"\n{raw_fact}\n\"\"\"\n"
                    f"Source URL: {source_url}\n\n"
                    "Write the short-form script as structured output."
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
    return script


def generate():
    """Full content step: returns a vetted script dict, retrying if unsuitable."""
    for attempt in range(1, 6):
        raw_fact, source_url = fetch_raw_fact()
        print(f"[content] attempt {attempt}: sourced fact from {source_url}")
        script = build_script(raw_fact, source_url)
        if script["suitable"]:
            print(f"[content] script ready: {script['title']!r}")
            return script
        print(f"[content] rejected (not suitable): {script['reason_if_unsuitable']}")
    raise RuntimeError("Could not source a suitable positive fact after 5 attempts.")


if __name__ == "__main__":
    from pprint import pprint

    pprint(generate())
