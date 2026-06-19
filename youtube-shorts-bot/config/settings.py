"""
Copy this file to config/settings.py and fill in your values.
config/settings.py is gitignored so your keys never get committed.
"""

import os

# --- Claude API (for rewriting facts into engaging scripts) ---
# Get a key at https://console.anthropic.com — or run `ant auth login`.
# Leaving this as None makes the SDK read ANTHROPIC_API_KEY from the env.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"  # balanced speed/intelligence; supports adaptive thinking

# --- Stock media (Pexels — free tier, 200 req/hr) ---
# Get a key at https://www.pexels.com/api/
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# --- Content policy ---
# The bot only produces positive, factual content. These constrain generation.
TONE = "uplifting, warm, and encouraging"
TOPICS = [
    "science wonders",
    "acts of kindness",
    "nature facts",
    "human achievements",
    "history's bright moments",
    "health and wellbeing",
]

# --- Video format (YouTube Shorts: vertical 9:16, <= 60s) ---
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
MAX_DURATION_SECONDS = 30   # hard cap — videos are trimmed to this length
TARGET_DURATION_SECONDS = 25  # aim point for narration length (20-30s sweet spot)
FPS = 30

# --- Background music (optional) ---
# Drop royalty-free .mp3 files into assets/music/. One is picked at random and
# mixed quietly under the voiceover. No files there -> no music (voice only).
ENABLE_MUSIC = True
MUSIC_VOLUME = 0.12  # 0.0-1.0, kept low so narration stays clear
MUSIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "music")

# --- Visual style ---
CLIPS_PER_VIDEO = 4        # number of different stock clips to rotate through
SHOW_TITLE_CARD = True     # 2.5s title card at the start
KEN_BURNS = True           # slow zoom on each clip for motion

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# --- YouTube upload ---
# Always uploads as PRIVATE so you review before making public. Set False to skip upload entirely.
ENABLE_UPLOAD = True
UPLOAD_PRIVACY = "private"  # "private" | "unlisted" | "public" — keep "private" for human review
YOUTUBE_CLIENT_SECRETS = os.path.join(BASE_DIR, "config", "client_secrets.json")
YOUTUBE_TOKEN_FILE = os.path.join(BASE_DIR, "config", "youtube_token.json")
