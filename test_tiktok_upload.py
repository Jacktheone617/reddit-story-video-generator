"""Tests for TikTok upload integration (tiktok_upload.py + main_webscraper._try_tiktok_upload).

All heavy external dependencies are mocked via sys.modules so tests run without
installing Pillow, MoviePy, edge_tts, language_tool_python, etc.
"""

import sqlite3
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Mock heavy third-party modules BEFORE importing our project code
# ---------------------------------------------------------------------------
_MODULES_TO_MOCK = [
    "PIL", "PIL.Image",
    "requests", "bs4",
    "gtts", "pydub",
    "moviepy", "moviepy.editor",
    "edge_tts",
    "language_tool_python",
    "spellchecker",
    "header", "subtitles", "youtube_uploader",
    # The tiktok-uploader library package
    "tiktok_uploader", "tiktok_uploader.upload",
]

for mod_name in _MODULES_TO_MOCK:
    fake = types.ModuleType(mod_name)
    # Add attributes that importing code expects via `from X import Y`
    if mod_name == "PIL.Image":
        fake.ANTIALIAS = fake.LANCZOS = 1
        fake.open = MagicMock()
    elif mod_name == "tiktok_uploader.upload":
        fake.upload_video = MagicMock()
    elif mod_name == "spellchecker":
        fake.SpellChecker = MagicMock
    elif mod_name == "header":
        fake.create_reddit_header = MagicMock()
    elif mod_name == "subtitles":
        fake.create_dynamic_text_clips = MagicMock()
    elif mod_name == "youtube_uploader":
        fake.YouTubeUploader = MagicMock
    elif mod_name == "bs4":
        fake.BeautifulSoup = MagicMock()
    elif mod_name == "gtts":
        fake.gTTS = MagicMock()
    elif mod_name == "pydub":
        fake.AudioSegment = MagicMock()
    elif mod_name == "edge_tts":
        fake.Communicate = MagicMock()
    elif mod_name == "language_tool_python":
        fake.LanguageTool = MagicMock
    elif mod_name == "moviepy":
        for attr in ("VideoFileClip", "CompositeVideoClip", "TextClip",
                      "AudioFileClip", "ImageClip"):
            setattr(fake, attr, MagicMock())
    elif mod_name == "moviepy.editor":
        for attr in ("VideoFileClip", "CompositeVideoClip", "TextClip",
                      "AudioFileClip", "ImageClip"):
            setattr(fake, attr, MagicMock())
    sys.modules[mod_name] = fake

# Wire PIL.Image as an attribute of PIL so `PIL.Image` resolves correctly
sys.modules["PIL"].Image = sys.modules["PIL.Image"]
# Wire tiktok_uploader.upload as submodule
sys.modules["tiktok_uploader"].upload = sys.modules["tiktok_uploader.upload"]

# Now import the local modules (tiktok_upload.py and main_webscraper.py)
from tiktok_upload import TikTokVideoUploader  # noqa: E402
import tiktok_upload as _local_tiktok_mod  # noqa: E402
import main_webscraper  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# Tests for TikTokVideoUploader class
# ═══════════════════════════════════════════════════════════════════════════════

class TestTikTokVideoUploader(unittest.TestCase):
    """Tests for the TikTokVideoUploader class."""

    def _get_mock_upload(self):
        """Return the mocked upload_video function used by tiktok_upload.py."""
        return _local_tiktok_mod.upload_video

    def setUp(self):
        self._get_mock_upload().reset_mock()
        self._get_mock_upload().side_effect = None

    def test_upload_builds_description(self):
        mock_upload = self._get_mock_upload()
        uploader = TikTokVideoUploader()
        uploader.upload_video("vid.mp4", "My Title", tags=["Tag1", "Tag2"])
        mock_upload.assert_called_once()
        description = mock_upload.call_args.kwargs["description"]
        self.assertEqual(description, "My Title #Tag1 #Tag2")

    def test_upload_uses_default_tags(self):
        mock_upload = self._get_mock_upload()
        uploader = TikTokVideoUploader()
        uploader.upload_video("vid.mp4", "Title")
        description = mock_upload.call_args.kwargs["description"]
        self.assertIn("#Reddit", description)
        self.assertIn("#RedditStories", description)
        self.assertIn("#AskReddit", description)

    def test_upload_truncates_long_description(self):
        mock_upload = self._get_mock_upload()
        uploader = TikTokVideoUploader()
        long_title = "A" * 2300
        uploader.upload_video("vid.mp4", long_title, tags=["T"])
        description = mock_upload.call_args.kwargs["description"]
        self.assertLessEqual(len(description), 2200)

    def test_upload_returns_success(self):
        uploader = TikTokVideoUploader()
        result = uploader.upload_video("vid.mp4", "Title")
        self.assertEqual(result, {"success": True})

    def test_upload_returns_none_on_failure(self):
        self._get_mock_upload().side_effect = RuntimeError("browser crashed")
        uploader = TikTokVideoUploader()
        result = uploader.upload_video("vid.mp4", "Title")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests for _try_tiktok_upload (on DynamicTextVideoGenerator)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTryTikTokUpload(unittest.TestCase):
    """Tests for DynamicTextVideoGenerator._try_tiktok_upload."""

    def _make_generator(self):
        """Create a minimal DynamicTextVideoGenerator with in-memory DB."""
        gen = object.__new__(main_webscraper.DynamicTextVideoGenerator)
        gen.conn = sqlite3.connect(":memory:")
        gen.conn.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                video_path TEXT,
                platform TEXT DEFAULT 'youtube',
                video_id TEXT,
                privacy TEXT DEFAULT 'private',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        gen.conn.commit()
        return gen

    def _story(self, **overrides):
        base = {"id": "abc123", "title": "Test Story Title", "subreddit": "AskReddit"}
        base.update(overrides)
        return base

    @patch("main_webscraper.os.path.exists", return_value=False)
    def test_skip_when_no_cookies(self, mock_exists):
        gen = self._make_generator()
        gen._try_tiktok_upload("vid.mp4", self._story())
        rows = gen.conn.execute("SELECT * FROM uploaded_videos").fetchall()
        self.assertEqual(len(rows), 0)

    @patch("main_webscraper.TikTokVideoUploader")
    @patch("main_webscraper.os.path.exists", return_value=True)
    def test_calls_uploader_when_cookies_exist(self, _exists, mock_cls):
        mock_instance = MagicMock()
        mock_instance.upload_video.return_value = {"success": True}
        mock_cls.return_value = mock_instance

        gen = self._make_generator()
        gen._try_tiktok_upload("vid.mp4", self._story())
        mock_instance.upload_video.assert_called_once()

    @patch("main_webscraper.TikTokVideoUploader")
    @patch("main_webscraper.os.path.exists", return_value=True)
    def test_records_in_database(self, _exists, mock_cls):
        mock_instance = MagicMock()
        mock_instance.upload_video.return_value = {"success": True}
        mock_cls.return_value = mock_instance

        gen = self._make_generator()
        story = self._story(id="post999")
        gen._try_tiktok_upload("vid.mp4", story)

        rows = gen.conn.execute("SELECT post_id, platform FROM uploaded_videos").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "post999")
        self.assertEqual(rows[0][1], "tiktok")

    @patch("main_webscraper.TikTokVideoUploader")
    @patch("main_webscraper.os.path.exists", return_value=True)
    def test_no_db_record_on_failure(self, _exists, mock_cls):
        mock_instance = MagicMock()
        mock_instance.upload_video.return_value = None
        mock_cls.return_value = mock_instance

        gen = self._make_generator()
        gen._try_tiktok_upload("vid.mp4", self._story())

        rows = gen.conn.execute("SELECT * FROM uploaded_videos").fetchall()
        self.assertEqual(len(rows), 0)

    @patch("main_webscraper.TikTokVideoUploader")
    @patch("main_webscraper.os.path.exists", return_value=True)
    def test_exception_doesnt_crash(self, _exists, mock_cls):
        mock_cls.side_effect = RuntimeError("boom")

        gen = self._make_generator()
        # Should not raise
        gen._try_tiktok_upload("vid.mp4", self._story())

        rows = gen.conn.execute("SELECT * FROM uploaded_videos").fetchall()
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
