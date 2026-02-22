"""
Download ~40 mountain biking videos from Pexels.

Uses Playwright to browse the search page (bypasses Cloudflare),
then yt-dlp.exe to download each video.

No API key needed — runs fully from the command line.

Usage:
    python download_biking_ytdlp.py
"""

import os
import re
import time
import subprocess
import asyncio

# ── CONFIG ──────────────────────────────────────────────────────────────────
OUTPUT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gameplay_videos")
YTDLP_EXE   = os.path.join(OUTPUT_DIR, "yt-dlp.exe")
TARGET_COUNT = 40

SEARCH_QUERIES = [
    "mountain biking pov",
    "downhill mountain biking",
    "mountain bike trail",
    "cycling adventure",
    "mtb ride",
]
# ────────────────────────────────────────────────────────────────────────────


async def scrape_pexels_urls(queries: list[str], target: int) -> list[str]:
    """
    Use Playwright (headless Chromium) to browse Pexels search pages
    and collect individual video page URLs.
    """
    from playwright.async_api import async_playwright

    seen: set[str] = set()
    urls: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        for query in queries:
            if len(urls) >= target * 2:
                break

            encoded = query.replace(" ", "%20")
            search_url = f"https://www.pexels.com/search/videos/{encoded}/"
            print(f"\n  Browsing: {search_url}")

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2500)   # let JS render videos

                # Scroll down a few times to trigger lazy loading
                for _ in range(4):
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1200)

                html = await page.content()
            except Exception as e:
                print(f"    Failed to load page: {e}")
                continue

            # Extract /video/{slug}-{id}/ hrefs
            found = re.findall(r'href="(/video/[a-z0-9][a-z0-9\-]+-\d+/)"', html)
            added = 0
            for path in found:
                full = "https://www.pexels.com" + path
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
                    added += 1

            print(f"    Found {added} new URLs (total: {len(urls)})")

        await browser.close()

    return urls


def download_video(url: str, index: int, total: int) -> bool:
    """Download one Pexels video page URL using yt-dlp.exe."""
    out_template = os.path.join(OUTPUT_DIR, "biking_%(id)s.%(ext)s")
    cmd = [
        YTDLP_EXE,
        url,
        "-o", out_template,
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--extractor-args", "generic:impersonate",
        "--no-playlist",
        "--quiet",
        "--progress",
        "--no-warnings",
    ]
    print(f"\n[{index}/{total}] {url}")
    try:
        result = subprocess.run(cmd, timeout=180)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  Timed out, skipping")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def already_downloaded_count() -> int:
    files = [f for f in os.listdir(OUTPUT_DIR)
             if f.lower().endswith((".mp4", ".webm", ".mkv", ".mov"))]
    return len(files)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(YTDLP_EXE):
        print(f"ERROR: yt-dlp.exe not found at:\n  {YTDLP_EXE}")
        return

    existing = already_downloaded_count()
    if existing >= TARGET_COUNT:
        print(f"Already have {existing} videos in {OUTPUT_DIR} — nothing to do.")
        return

    still_needed = TARGET_COUNT - existing
    print(f"Already downloaded: {existing}  |  Still need: {still_needed}")
    print(f"Collecting Pexels mountain biking video URLs via Playwright...")

    # Scrape URLs
    urls = asyncio.run(scrape_pexels_urls(SEARCH_QUERIES, still_needed))

    if not urls:
        print("\nNo URLs found. Check your internet connection or try again later.")
        return

    urls_to_get = urls[:still_needed]
    print(f"\nDownloading {len(urls_to_get)} videos -> {OUTPUT_DIR}\n")

    downloaded = 0
    for i, url in enumerate(urls_to_get, 1):
        ok = download_video(url, i, len(urls_to_get))
        if ok:
            downloaded += 1
        time.sleep(0.5)

    total = already_downloaded_count()
    print(f"\n{'='*50}")
    print(f"Done!  Downloaded this run: {downloaded}/{len(urls_to_get)}")
    print(f"Total biking videos in folder: {total}")
    print(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
