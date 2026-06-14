"""
YouTube upload — HUMAN-IN-THE-LOOP by design.

The video is uploaded as PRIVATE (configurable). It is NEVER auto-published.
You review it in YouTube Studio and click "Publish" yourself. This is the
safest pattern for avoiding policy strikes from automated publishing.

First run opens a browser for OAuth consent; the token is cached afterward.
"""

import os
import sys

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from config import settings  # noqa: E402

from google.auth.transport.requests import Request  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaFileUpload  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials():
    creds = None
    if os.path.exists(settings.YOUTUBE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(settings.YOUTUBE_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(settings.YOUTUBE_CLIENT_SECRETS):
                raise FileNotFoundError(
                    f"Missing {settings.YOUTUBE_CLIENT_SECRETS}. Download an OAuth "
                    "client secret (Desktop app) from Google Cloud Console and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(settings.YOUTUBE_CLIENT_SECRETS, SCOPES)
            # Headless-friendly: bind to a FIXED port and DON'T try to open a browser
            # (EC2 has none). The auth URL is printed; open it in a browser that can
            # reach this port. On EC2, set up an SSH tunnel from your laptop first:
            #     ssh -i KEY -L 8765:localhost:8765 ubuntu@<EC2_IP>
            # then open the printed URL in your laptop browser. The OAuth redirect to
            # http://localhost:8765/ tunnels back to this server and completes the flow.
            print(
                "\n[upload] Open the URL below in a browser that can reach localhost:8765.\n"
                "         (Headless EC2? First run on your laptop:\n"
                "            ssh -i KEY -L 8765:localhost:8765 ubuntu@<EC2_IP>\n"
                "          then open the URL in your laptop's browser.)\n"
            )
            creds = flow.run_local_server(port=8765, open_browser=False)
        with open(settings.YOUTUBE_TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())
    return creds


def _build_description(script):
    """Assemble the YouTube description, including source and any music credit."""
    parts = [script["description"]]
    if script.get("source_url"):
        parts.append(f"Source: {script['source_url']}")
    if script.get("music_credit"):
        parts.append(f"Music: {script['music_credit']}")
    return "\n\n".join(parts)


def upload(video_path, script):
    """Upload as PRIVATE and return the watch URL. You publish manually after review."""
    youtube = build("youtube", "v3", credentials=_get_credentials())

    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": _build_description(script),
            "tags": ["shorts", "positivity", "facts"],
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": settings.UPLOAD_PRIVACY,  # "private" — you review before publishing
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print("[upload] uploading...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")

    video_id = response["id"]
    url = f"https://youtube.com/watch?v={video_id}"
    print(f"[upload] done ({settings.UPLOAD_PRIVACY}): {url}")
    print("[upload] REVIEW it in YouTube Studio, then publish manually.")
    return url
