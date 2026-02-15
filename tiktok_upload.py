"""
TikTok uploader using the tiktok-uploader package (browser automation via Playwright).

Setup (one-time):
1. pip install tiktok-uploader playwright
2. playwright install
3. Log into TikTok in Chrome
4. Export cookies with a "Get cookies.txt" browser extension
5. Save as tiktok_cookies.txt in the project root
"""

from tiktok_uploader.upload import upload_video


class TikTokVideoUploader:
    """Handles cookie-based authentication and video uploads to TikTok."""

    def __init__(self, cookies_path="tiktok_cookies.txt"):
        self.cookies_path = cookies_path

    def upload_video(self, video_path, title, tags=None):
        """
        Upload a video to TikTok.

        Args:
            video_path: Path to the .mp4 file.
            title: Video title/caption.
            tags: Optional list of hashtag strings (without #).

        Returns:
            Dict with success=True on success, None on failure.
        """
        try:
            # Build description: title + hashtags
            default_tags = ["Reddit", "RedditStories", "AskReddit"]
            all_tags = tags or default_tags
            hashtags = " ".join(f"#{t}" for t in all_tags)
            description = f"{title} {hashtags}"

            # TikTok caption limit is 2200 characters
            if len(description) > 2200:
                description = description[:2200]

            upload_video(
                filename=video_path,
                description=description,
                cookies=self.cookies_path,
            )

            print(f"TikTok upload complete: {title[:50]}...")
            return {"success": True}

        except Exception as e:
            print(f"TikTok upload failed: {e}")
            return None
