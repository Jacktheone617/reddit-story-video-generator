# Reddit Story Video Generator

Automatically scrapes Reddit stories, generates TikTok/YouTube Shorts-style videos with TTS narration and subtitles, then uploads them to TikTok and YouTube.

No Reddit API credentials needed — uses web scraping via Reddit's public JSON endpoints.

## How It Works

1. Scrapes top stories from a subreddit (default: `r/AmItheAsshole`)
2. Runs spell/grammar checking on the text
3. Generates TTS audio using Microsoft Edge Neural voices (Jenny)
4. Overlays audio + word-by-word subtitles + Reddit-style header onto random gameplay footage
5. Uploads the finished video to TikTok and/or YouTube
6. Tracks processed posts in a SQLite database to avoid duplicates
7. Waits 3 minutes between each video to avoid rate limits

## Video Output

- **Resolution:** 720x1280 (9:16 portrait)
- **FPS:** 24
- **Codec:** H.264 + AAC with faststart flag
- **Subtitles:** One-word-at-a-time, frame-safe, synced to Edge TTS WordBoundary events
- **Header:** Reddit-style card with subreddit, author, verified badge, and emoji reactions

## Project Structure

```
main_webscraper.py       # Main script — scrapes Reddit, generates videos, uploads
header.py                # Reddit-style header card generation (PIL)
subtitles.py             # Word-by-word caption/subtitle module
tiktok_upload.py         # TikTok uploader (cookie-based via tiktok-uploader library)
youtube_uploader.py      # YouTube uploader (OAuth via Google API)
run_daily.bat            # Batch file for Windows Task Scheduler
test_tiktok_upload.py    # Unit tests for TikTok upload integration
processed_posts.db       # SQLite database tracking processed/uploaded posts
gameplay_videos/         # Folder of .mp4 gameplay clips (you provide these)
output_videos/           # Generated videos are saved here
logo/Redit logo.png      # Reddit logo used in the header overlay
```

## Setup

### 1. Install Dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements_webscraper.txt
```

### 2. Add Gameplay Videos

Create a `gameplay_videos/` folder and add `.mp4` gameplay clips (Minecraft parkour, Subway Surfers, etc.). The script picks a random clip for each video.

### 3. TikTok Upload (Optional)

1. Install Playwright browsers: `playwright install`
2. Log into TikTok in Chrome
3. Export cookies using a "Get cookies.txt" browser extension
4. Extract only the TikTok cookies into `tiktok_cookies.txt` in the project root

The critical cookie is `sessionid` — without it, authentication will fail.

### 4. YouTube Upload (Optional)

1. Create a Google Cloud project with the YouTube Data API v3 enabled
2. Download OAuth credentials as `client_secret.json` in the project root
3. On first run, a browser window opens for Google OAuth — after that, `token.json` is cached

### 5. Scheduled Daily Runs

The project is configured to run automatically via Windows Task Scheduler. A scheduled task named `RedditVideoGenerator` runs `run_daily.bat` every day at **2:00 AM**.

To set this up manually:

```bash
schtasks /create /tn "RedditVideoGenerator" /tr "path\to\run_daily.bat" /sc daily /st 02:00 /f
```

Your PC must be on and logged in for the task to run (set to "Interactive only" mode). To run while logged out, open Task Scheduler > find "RedditVideoGenerator" > Properties > select "Run whether user is logged on or not".

## Configuration

Key settings in `main_webscraper.py` `main()` function:

| Setting | Default | Description |
|---------|---------|-------------|
| `subreddit` | `"AmItheAsshole"` | Subreddit to scrape stories from |
| `num_videos` | `4` | Number of videos to generate per run |
| `min_score` | `50` | Minimum post score to consider |
| `sort` | `"hot"` | Reddit sort order (`hot`, `top`, `new`) |
| `voice_type` | `"tiktok"` | TTS voice (`tiktok` = Edge TTS Jenny Neural) |

## Running

```bash
# Activate venv
venv\Scripts\activate

# Generate videos
python main_webscraper.py

# Run tests
python -m pytest test_tiktok_upload.py -v
```

## Dependencies

- **Web scraping:** requests, beautifulsoup4
- **TTS:** edge-tts (primary), gtts (fallback)
- **Audio:** pydub
- **Video:** moviepy, Pillow, numpy, imageio, imageio-ffmpeg
- **Spell/grammar:** language_tool_python, pyspellchecker
- **YouTube upload:** google-api-python-client, google-auth-oauthlib
- **TikTok upload:** tiktok-uploader, playwright
- **Database:** sqlite3 (built-in)
