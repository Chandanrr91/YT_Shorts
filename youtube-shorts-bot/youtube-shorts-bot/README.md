# Positivity Shorts Bot

Automates creating short, **positive and factual** YouTube Shorts.

**Pipeline:** trusted fact source → Claude rewrites it into a script (no invented
facts) → vertical video with voiceover + captions → uploaded **private** for you
to review and publish.

```
content.py   sourced fact + Claude rewrite (hybrid, factual)
media.py     gTTS voiceover + Pexels stock background + burned-in captions → 9:16 MP4
upload.py    uploads as PRIVATE — you publish manually (human-in-the-loop)
main.py      runs all three
```

## Setup

```bash
# 1. System dependency — ffmpeg (video assembly)
brew install ffmpeg

# 2. Python deps (a virtualenv is recommended)
cd ~/youtube-shorts-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure — copy the template and add your keys
cp config/settings.example.py config/settings.py   # already done for you
export ANTHROPIC_API_KEY="sk-ant-..."               # required (script writing)
export PEXELS_API_KEY="..."                          # optional (stock video; gradient used if absent)
```

### YouTube upload (optional)

1. In [Google Cloud Console](https://console.cloud.google.com): create a project,
   enable **YouTube Data API v3**, create an **OAuth client ID (Desktop app)**.
2. Download the JSON and save it to `config/client_secrets.json`.
3. First upload opens a browser for consent; the token is cached afterward.

To skip upload entirely, set `ENABLE_UPLOAD = False` in `config/settings.py`
or run with `--no-upload`.

## Usage

```bash
python3 main.py --dry-run     # generate + print the script only (no video, no API video cost)
python3 main.py --no-upload   # generate + build the MP4, skip upload
python3 main.py               # full pipeline: build + upload as PRIVATE
```

Test one stage at a time:

```bash
python3 scripts/content.py    # prints a vetted script dict
```

## Safety / responsibility notes

- **Factual integrity:** Claude is instructed to *only rephrase* a sourced fact,
  never invent one, and to reject anything not positive/safe. Sources
  (Wikipedia, Numbers API) are citable; the source URL is saved and added to the
  video description.
- **Human-in-the-loop publishing:** videos upload as `private`. Review every one
  in YouTube Studio before making it public — this is your check against errors
  and your safeguard against automated-publishing policy issues.
- **YouTube policy:** automated/repetitive content is subject to YouTube's spam
  and "inauthentic content" policies. Keep volume reasonable and add genuine
  value; review before publishing.
- **Stock media licensing:** Pexels clips are free to use; keep within their
  [license](https://www.pexels.com/license/).
