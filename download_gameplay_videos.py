"""
Download ~40 mountain biking gameplay videos from Pexels.

Requirements:
  pip install requests

Usage:
  1. Get a FREE Pexels API key at https://www.pexels.com/api/
  2. Set PEXELS_API_KEY below (or set env var PEXELS_API_KEY)
  3. Run: python download_gameplay_videos.py
"""

import os
import sys
import time
import requests

# ── CONFIG ──────────────────────────────────────────────────────────────────
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "YOUR_API_KEY_HERE")

SEARCH_QUERIES = [
    "mountain biking pov",
    "mountain bike trail",
    "downhill mountain biking",
    "cycling adventure outdoor",
]

TARGET_COUNT   = 40          # how many videos to download
OUTPUT_DIR     = os.path.join(os.path.dirname(__file__), "gameplay_videos")
MIN_DURATION   = 10          # seconds – skip very short clips
MAX_DURATION   = 120         # seconds – skip very long clips
PREFERRED_RES  = "hd"        # "hd" (1280x720+) or "sd"
# ────────────────────────────────────────────────────────────────────────────


def search_pexels_videos(query: str, per_page: int = 80, page: int = 1) -> list:
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page, "page": page, "size": "medium"}
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("videos", [])


def best_file(video: dict) -> dict | None:
    """Pick the best video file: prefer HD, then SD, biggest resolution first."""
    files = video.get("video_files", [])
    # sort by quality label then by resolution
    quality_order = {"hd": 0, "sd": 1, "uhd": 0}
    files_sorted = sorted(
        files,
        key=lambda f: (quality_order.get(f.get("quality", "sd"), 2),
                       -(f.get("width", 0) * f.get("height", 0)))
    )
    for f in files_sorted:
        if f.get("file_type", "").startswith("video/"):
            return f
    return None


def download_file(url: str, dest: str) -> bool:
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done / total * 100
                        print(f"\r  {pct:5.1f}%  {done//1024//1024} MB / {total//1024//1024} MB", end="")
        print()
        return True
    except Exception as e:
        print(f"\n  ERROR downloading: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return False


def main():
    if PEXELS_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Set your Pexels API key in the script or via env var PEXELS_API_KEY")
        print("Get a FREE key at: https://www.pexels.com/api/")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # collect unique video entries across queries
    seen_ids: set[int] = set()
    candidates: list[dict] = []

    for query in SEARCH_QUERIES:
        if len(candidates) >= TARGET_COUNT * 2:
            break
        print(f"Searching Pexels: '{query}' …")
        try:
            videos = search_pexels_videos(query, per_page=80)
        except Exception as e:
            print(f"  Search failed: {e}")
            continue

        for v in videos:
            vid = v.get("id")
            if vid in seen_ids:
                continue
            duration = v.get("duration", 0)
            if duration < MIN_DURATION or duration > MAX_DURATION:
                continue
            f = best_file(v)
            if f is None:
                continue
            seen_ids.add(vid)
            candidates.append({"id": vid, "duration": duration, "file": f, "url": v.get("url", "")})

        print(f"  Found {len(videos)} results | unique candidates so far: {len(candidates)}")
        time.sleep(0.5)  # be polite to the API

    print(f"\nTotal candidates: {len(candidates)} – will download up to {TARGET_COUNT}\n")

    downloaded = 0
    for i, entry in enumerate(candidates[:TARGET_COUNT]):
        vid_id   = entry["id"]
        file_url = entry["file"]["link"]
        ext      = entry["file"].get("file_type", "video/mp4").split("/")[-1]
        filename = f"biking_{vid_id}.{ext}"
        dest     = os.path.join(OUTPUT_DIR, filename)

        if os.path.exists(dest):
            print(f"[{i+1}/{TARGET_COUNT}] Already exists: {filename}")
            downloaded += 1
            continue

        print(f"[{i+1}/{TARGET_COUNT}] Downloading {filename}  ({entry['duration']}s)  {entry['url']}")
        if download_file(file_url, dest):
            downloaded += 1
        time.sleep(0.3)

    print(f"\nDone. Downloaded {downloaded} videos to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
