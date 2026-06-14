#!/usr/bin/env python3
"""
Positivity Shorts Bot — end-to-end pipeline.

  1. content.generate()  -> sourced + Claude-rewritten factual script
  2. media.assemble()    -> 9:16 MP4 with voiceover + captions
  3. upload.upload()     -> uploads PRIVATE for your manual review (optional)

Usage:
  python3 main.py              # generate + build + (optionally) upload
  python3 main.py --no-upload  # generate + build only, skip upload
  python3 main.py --dry-run    # generate script only, print it, no video

Run scripts/content.py or scripts/media.py directly to test a single stage.
"""

import argparse
import datetime
import json
import os

from config import settings
from scripts import content, media


def _timestamp():
    # avoids importing datetime.now() into anything cache-sensitive; just for filenames
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def run(do_upload=True, dry_run=False):
    print("=" * 60)
    print("Positivity Shorts Bot")
    print("=" * 60)

    # 1. content
    script = content.generate()

    stamp = _timestamp()
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    script_path = os.path.join(settings.OUTPUT_DIR, f"{stamp}.script.json")
    with open(script_path, "w") as fh:
        json.dump(script, fh, indent=2)
    print(f"[main] saved script -> {script_path}")

    if dry_run:
        print("\n--- DRY RUN: script only ---")
        print(json.dumps(script, indent=2))
        return

    # 2. media (assemble() may add music_credit to the script dict)
    video_path = os.path.join(settings.OUTPUT_DIR, f"{stamp}.mp4")
    media.assemble(script, video_path)

    # re-save so the on-disk record includes anything added during assembly
    with open(script_path, "w") as fh:
        json.dump(script, fh, indent=2)

    # 3. upload (human-in-the-loop: uploaded private, you publish manually)
    if do_upload and settings.ENABLE_UPLOAD:
        from scripts import upload  # imported lazily so video-only runs need no google libs
        upload.upload(video_path, script)
    else:
        print(f"[main] upload skipped. Video ready at: {video_path}")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a positive, factual YouTube Short.")
    parser.add_argument("--no-upload", action="store_true", help="build the video but don't upload")
    parser.add_argument("--dry-run", action="store_true", help="generate the script only, no video")
    args = parser.parse_args()
    run(do_upload=not args.no_upload, dry_run=args.dry_run)
