"""
Tests for the scraper: duplicate prevention and update detection/merging.

Run with: python test_scraper.py
"""

import os
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from main_webscraper import DynamicTextVideoGenerator


# ── Fake Reddit JSON responses ──────────────────────────────────────────────

def make_post(post_id, title, body, author="testuser", score=100,
              num_comments=50, subreddit="AmItheAsshole", nsfw=False):
    """Helper: build a fake Reddit post in the JSON API format."""
    return {
        "data": {
            "id": post_id,
            "title": title,
            "selftext": body,
            "author": author,
            "score": score,
            "num_comments": num_comments,
            "subreddit": subreddit,
            "over_18": nsfw,
            "created_utc": 1700000000,
        }
    }


ORIGINAL_STORY = make_post(
    "abc123",
    "AITA for telling my sister she can't bring her kids to my wedding",
    " ".join(["word"] * 100),  # 100 words — passes the 80-350 filter
    author="throwaway_wedding",
)

UPDATE_POST = make_post(
    "def456",
    "Update: AITA for telling my sister she can't bring her kids to my wedding",
    "So after my last post things got worse. " + " ".join(["update_word"] * 50),
    author="throwaway_wedding",
)
UPDATE_POST["data"]["created_utc"] = 1700100000

UNRELATED_POST = make_post(
    "ghi789",
    "AITA for not tipping at a restaurant",
    " ".join(["unrelated"] * 100),
    author="throwaway_wedding",
)

SECOND_STORY = make_post(
    "jkl012",
    "AITA for refusing to lend my car to my roommate",
    " ".join(["story"] * 100),
    author="another_user",
)

UPDATE_IN_FEED = make_post(
    "upd001",
    "Update: AITA for refusing to pay for my friend's dinner",
    " ".join(["update_text"] * 100),
    author="someone_else",
)


class TestDuplicatePrevention(unittest.TestCase):
    """Stories already in the database should be skipped."""

    def setUp(self):
        # Use an in-memory database so tests don't touch the real one
        self.gen = DynamicTextVideoGenerator.__new__(DynamicTextVideoGenerator)
        self.gen.conn = sqlite3.connect(":memory:")
        self.gen.session = MagicMock()
        self.gen.user_agents = ["TestAgent/1.0"]
        cursor = self.gen.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                processed_date TIMESTAMP,
                video_parts INTEGER
            )
        ''')
        self.gen.conn.commit()

    def tearDown(self):
        self.gen.conn.close()

    def test_new_post_is_not_processed(self):
        """A brand new post should not be flagged as processed."""
        self.assertFalse(self.gen.is_post_processed("abc123"))

    def test_marked_post_is_processed(self):
        """After marking a post, it should be flagged as processed."""
        self.gen.mark_post_processed("abc123", "Test title", 1)
        self.assertTrue(self.gen.is_post_processed("abc123"))

    def test_scraper_skips_processed_posts(self):
        """scrape_reddit_stories with allow_reprocess=False should skip DB posts."""
        # Mark the original story as already processed
        self.gen.mark_post_processed("abc123", "Already done", 1)

        # Mock the JSON endpoint to return the already-processed post + a new one
        with patch.object(self.gen, '_fetch_reddit_json', return_value=[ORIGINAL_STORY, SECOND_STORY]):
            stories = self.gen.scrape_reddit_stories("AmItheAsshole", limit=5,
                                                     allow_reprocess=False, min_score=1)

        ids = [s['id'] for s in stories]
        self.assertNotIn("abc123", ids, "Processed post should be skipped")
        self.assertIn("jkl012", ids, "New post should be included")

    def test_scraper_includes_processed_when_allowed(self):
        """scrape_reddit_stories with allow_reprocess=True should include DB posts."""
        self.gen.mark_post_processed("abc123", "Already done", 1)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[ORIGINAL_STORY, SECOND_STORY]):
            stories = self.gen.scrape_reddit_stories("AmItheAsshole", limit=5,
                                                     allow_reprocess=True, min_score=1)

        ids = [s['id'] for s in stories]
        self.assertIn("abc123", ids, "Processed post should be included when allow_reprocess=True")

    def test_scraper_skips_update_posts_in_feed(self):
        """Posts with 'Update:' in the title should be skipped during scraping."""
        with patch.object(self.gen, '_fetch_reddit_json', return_value=[UPDATE_IN_FEED, SECOND_STORY]):
            stories = self.gen.scrape_reddit_stories("AmItheAsshole", limit=5,
                                                     allow_reprocess=False, min_score=1)

        ids = [s['id'] for s in stories]
        self.assertNotIn("upd001", ids, "Update posts should be skipped in the main feed")
        self.assertIn("jkl012", ids, "Normal posts should still be included")


class TestUpdateDetection(unittest.TestCase):
    """Update posts by the same author should be found and merged."""

    def setUp(self):
        self.gen = DynamicTextVideoGenerator.__new__(DynamicTextVideoGenerator)
        self.gen.conn = sqlite3.connect(":memory:")
        self.gen.session = MagicMock()
        self.gen.user_agents = ["TestAgent/1.0"]
        cursor = self.gen.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                processed_date TIMESTAMP,
                video_parts INTEGER
            )
        ''')
        self.gen.conn.commit()

    def tearDown(self):
        self.gen.conn.close()

    def test_finds_update_by_same_author(self):
        """Should find an update post by the same author in the same subreddit."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister she can\'t bring her kids to my wedding',
            'content': 'Original story text here.',
            'author': 'throwaway_wedding',
            'subreddit': 'AmItheAsshole',
        }

        # Mock: author's submissions include the original, an update, and an unrelated post
        with patch.object(self.gen, '_fetch_reddit_json', return_value=[
            ORIGINAL_STORY, UPDATE_POST, UNRELATED_POST
        ]):
            updates = self.gen.find_update_posts(story)

        self.assertEqual(len(updates), 1, "Should find exactly 1 update")
        self.assertEqual(updates[0]['id'], "def456")
        self.assertIn("update_word", updates[0]['content'])

    def test_ignores_unrelated_posts(self):
        """Posts by the same author that aren't updates should not be matched."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister she can\'t bring her kids to my wedding',
            'content': 'Original story text.',
            'author': 'throwaway_wedding',
            'subreddit': 'AmItheAsshole',
        }

        # Mock: only unrelated posts (no "update" in title)
        with patch.object(self.gen, '_fetch_reddit_json', return_value=[
            ORIGINAL_STORY, UNRELATED_POST
        ]):
            updates = self.gen.find_update_posts(story)

        self.assertEqual(len(updates), 0, "Unrelated posts should not match as updates")

    def test_skips_deleted_author(self):
        """Should return no updates if author is [deleted]."""
        story = {
            'id': 'abc123',
            'title': 'Some story',
            'content': 'Text.',
            'author': '[deleted]',
            'subreddit': 'AmItheAsshole',
        }

        updates = self.gen.find_update_posts(story)
        self.assertEqual(len(updates), 0, "Deleted author should return no updates")

    def test_skips_empty_author(self):
        """Should return no updates if author is empty."""
        story = {
            'id': 'abc123',
            'title': 'Some story',
            'content': 'Text.',
            'author': '',
            'subreddit': 'AmItheAsshole',
        }

        updates = self.gen.find_update_posts(story)
        self.assertEqual(len(updates), 0, "Empty author should return no updates")

    def test_ignores_updates_from_different_subreddit(self):
        """Update posts in a different subreddit should not be matched."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister she can\'t bring her kids to my wedding',
            'content': 'Text.',
            'author': 'throwaway_wedding',
            'subreddit': 'AmItheAsshole',
        }

        # Create an update that's in a different subreddit
        wrong_sub_update = make_post(
            "wrong_sub",
            "Update: AITA for telling my sister she can't bring her kids to my wedding",
            "Update text here.",
            author="throwaway_wedding",
            subreddit="relationship_advice",
        )

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[wrong_sub_update]):
            updates = self.gen.find_update_posts(story)

        self.assertEqual(len(updates), 0, "Updates from a different subreddit should be ignored")

    def test_updates_sorted_oldest_first(self):
        """Multiple updates should be returned in chronological order."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister she can\'t bring her kids to my wedding',
            'content': 'Text.',
            'author': 'throwaway_wedding',
            'subreddit': 'AmItheAsshole',
        }

        update1 = make_post(
            "upd1",
            "Update: AITA for telling my sister she can't bring her kids to my wedding",
            "First update.",
            author="throwaway_wedding",
        )
        update1["data"]["created_utc"] = 1700200000  # Later

        update2 = make_post(
            "upd2",
            "Update 2: AITA for telling my sister she can't bring kids to my wedding",
            "Second update.",
            author="throwaway_wedding",
        )
        update2["data"]["created_utc"] = 1700300000  # Even later

        # Return them in reverse order to test sorting
        with patch.object(self.gen, '_fetch_reddit_json', return_value=[
            ORIGINAL_STORY, update2, update1
        ]):
            updates = self.gen.find_update_posts(story)

        self.assertEqual(len(updates), 2, "Should find 2 updates")
        self.assertEqual(updates[0]['id'], "upd1", "Older update should come first")
        self.assertEqual(updates[1]['id'], "upd2", "Newer update should come second")


class TestUpdateMerging(unittest.TestCase):
    """Updates should be combined into the video text and marked processed."""

    def setUp(self):
        self.gen = DynamicTextVideoGenerator.__new__(DynamicTextVideoGenerator)
        self.gen.conn = sqlite3.connect(":memory:")
        self.gen.session = MagicMock()
        self.gen.user_agents = ["TestAgent/1.0"]
        self.gen.video_width = 720
        self.gen.video_height = 1280
        self.gen.fps = 24
        cursor = self.gen.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                processed_date TIMESTAMP,
                video_parts INTEGER
            )
        ''')
        self.gen.conn.commit()

    def tearDown(self):
        self.gen.conn.close()

    def test_update_text_merged_into_story(self):
        """The update content should be appended to the story text."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister no',
            'content': 'Original story content here.',
            'author': 'testuser',
            'subreddit': 'AmItheAsshole',
        }

        fake_updates = [{
            'id': 'upd1',
            'title': 'Update: AITA for telling my sister no',
            'content': 'Here is what happened next.',
            'created': 1700100000,
        }]

        with patch.object(self.gen, 'find_update_posts', return_value=fake_updates), \
             patch.object(self.gen, 'correct_text', side_effect=lambda t: t), \
             patch.object(self.gen, 'generate_audio') as mock_audio, \
             patch.object(self.gen, 'select_random_gameplay', return_value="fake.mp4"), \
             patch.object(self.gen, 'create_dynamic_video', return_value="output.mp4"):

            mock_audio.return_value = (10.0, [])

            self.gen.generate_videos_from_story(story, "gameplay_videos", "output_videos")

            # Check that generate_audio was called with text containing both parts
            called_text = mock_audio.call_args[0][0]
            self.assertIn("Original story content", called_text,
                          "Original story text should be in the audio")
            self.assertIn("happened next", called_text,
                          "Update text should be in the audio")

    def test_update_posts_marked_as_processed(self):
        """Update post IDs should be saved to the database so they aren't reused."""
        story = {
            'id': 'abc123',
            'title': 'AITA for telling my sister no',
            'content': 'Original story.',
            'author': 'testuser',
            'subreddit': 'AmItheAsshole',
        }

        fake_updates = [{
            'id': 'upd1',
            'title': 'Update: AITA',
            'content': 'Update text.',
            'created': 1700100000,
        }]

        with patch.object(self.gen, 'find_update_posts', return_value=fake_updates), \
             patch.object(self.gen, 'correct_text', side_effect=lambda t: t), \
             patch.object(self.gen, 'generate_audio', return_value=(5.0, [])), \
             patch.object(self.gen, 'select_random_gameplay', return_value="fake.mp4"), \
             patch.object(self.gen, 'create_dynamic_video', return_value="output.mp4"):

            self.gen.generate_videos_from_story(story, "gameplay_videos", "output_videos")

        # The update post should now be in the database
        self.assertTrue(self.gen.is_post_processed("upd1"),
                        "Update post should be marked as processed in the database")

    def test_no_updates_still_works(self):
        """Stories with no updates should process normally."""
        story = {
            'id': 'abc123',
            'title': 'AITA for something',
            'content': 'Just a normal story with no updates at all.',
            'author': 'testuser',
            'subreddit': 'AmItheAsshole',
        }

        with patch.object(self.gen, 'find_update_posts', return_value=[]), \
             patch.object(self.gen, 'correct_text', side_effect=lambda t: t), \
             patch.object(self.gen, 'generate_audio') as mock_audio, \
             patch.object(self.gen, 'select_random_gameplay', return_value="fake.mp4"), \
             patch.object(self.gen, 'create_dynamic_video', return_value="output.mp4"):

            mock_audio.return_value = (5.0, [])
            videos = self.gen.generate_videos_from_story(story, "gameplay_videos", "output_videos")

            self.assertEqual(len(videos), 1, "Should still produce a video with no updates")
            # Text should NOT contain "Update."
            called_text = mock_audio.call_args[0][0]
            self.assertNotIn("Update.", called_text,
                             "No 'Update.' separator when there are no updates")


class TestNSFWAndFilters(unittest.TestCase):
    """Basic filter checks: NSFW, word count, score."""

    def setUp(self):
        self.gen = DynamicTextVideoGenerator.__new__(DynamicTextVideoGenerator)
        self.gen.conn = sqlite3.connect(":memory:")
        self.gen.session = MagicMock()
        self.gen.user_agents = ["TestAgent/1.0"]
        cursor = self.gen.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                processed_date TIMESTAMP,
                video_parts INTEGER
            )
        ''')
        self.gen.conn.commit()

    def tearDown(self):
        self.gen.conn.close()

    def test_nsfw_posts_skipped(self):
        """NSFW posts should be filtered out."""
        nsfw_post = make_post("nsfw1", "NSFW story", " ".join(["word"] * 100),
                              nsfw=True, score=200)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[nsfw_post]):
            stories = self.gen.scrape_reddit_stories("test", limit=5, min_score=1)

        self.assertEqual(len(stories), 0, "NSFW posts should be skipped")

    def test_short_posts_skipped(self):
        """Posts with fewer than 80 words should be filtered out."""
        short_post = make_post("short1", "Short story", " ".join(["word"] * 30),
                               score=200)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[short_post]):
            stories = self.gen.scrape_reddit_stories("test", limit=5, min_score=1)

        self.assertEqual(len(stories), 0, "Posts under 80 words should be skipped")

    def test_long_posts_skipped(self):
        """Posts with more than 350 words should be filtered out."""
        long_post = make_post("long1", "Long story", " ".join(["word"] * 400),
                              score=200)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[long_post]):
            stories = self.gen.scrape_reddit_stories("test", limit=5, min_score=1)

        self.assertEqual(len(stories), 0, "Posts over 350 words should be skipped")

    def test_low_score_posts_skipped(self):
        """Posts below min_score should be filtered out."""
        low_score = make_post("low1", "Low score story", " ".join(["word"] * 100),
                              score=5)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[low_score]):
            stories = self.gen.scrape_reddit_stories("test", limit=5, min_score=50)

        self.assertEqual(len(stories), 0, "Low score posts should be skipped")

    def test_posts_without_body_skipped(self):
        """Posts with no selftext should be filtered out."""
        no_body = make_post("nobody1", "No body", "", score=200)

        with patch.object(self.gen, '_fetch_reddit_json', return_value=[no_body]):
            stories = self.gen.scrape_reddit_stories("test", limit=5, min_score=1)

        self.assertEqual(len(stories), 0, "Posts with no body should be skipped")


class TestSpellGrammar(unittest.TestCase):
    """Spell checking and grammar correction."""

    @classmethod
    def setUpClass(cls):
        """Create a real generator once for all spell tests (LanguageTool takes time to start)."""
        cls.gen = DynamicTextVideoGenerator.__new__(DynamicTextVideoGenerator)
        cls.gen.conn = sqlite3.connect(":memory:")
        cls.gen.session = MagicMock()
        cls.gen.user_agents = ["TestAgent/1.0"]

        from spellchecker import SpellChecker
        import language_tool_python
        cls.gen.spell = SpellChecker()
        cls.gen.ignore_words = {
            'aita', 'wibta', 'yta', 'nta', 'esh', 'nah', 'tifu', 'tldr',
            'bf', 'gf', 'mil', 'hubby', 'gonna', 'wanna', 'kinda', 'tho',
            'thru', 'ur', 'pls', 'cuz', 'coz', 'imo', 'imho', 'ok', 'meh',
        }
        cls.gen.spell.word_frequency.load_words(cls.gen.ignore_words)
        cls.gen.lang_tool = language_tool_python.LanguageTool('en-US')

    @classmethod
    def tearDownClass(cls):
        cls.gen.lang_tool.close()
        cls.gen.conn.close()

    def test_fixes_common_misspellings(self):
        """Common Reddit misspellings should be corrected."""
        text = "I was realy angery becuase of this."
        result = self.gen.correct_text(text)
        self.assertIn("really", result, "Should fix 'realy' -> 'really'")
        self.assertIn("angry", result, "Should fix 'angery' -> 'angry'")
        self.assertIn("because", result, "Should fix 'becuase' -> 'because'")

    def test_preserves_reddit_slang(self):
        """Reddit acronyms and slang should NOT be corrected."""
        text = "AITA for telling my bf NTA when she said ESH. I gonna kinda ignore it tho."
        result = self.gen.correct_text(text)
        result_lower = result.lower()
        self.assertIn("aita", result_lower, "Should preserve AITA")
        self.assertIn("bf", result_lower, "Should preserve bf")
        self.assertIn("nta", result_lower, "Should preserve NTA")
        self.assertIn("esh", result_lower, "Should preserve ESH")
        self.assertIn("gonna", result_lower, "Should preserve gonna")
        self.assertIn("kinda", result_lower, "Should preserve kinda")
        self.assertIn("tho", result_lower, "Should preserve tho")

    def test_fixes_grammar_cant(self):
        """Common grammar issues like 'cant' -> 'can't' should be fixed."""
        text = "She cant come to the party."
        result = self.gen.correct_text(text)
        self.assertIn("can't", result, "Should fix 'cant' -> 'can't'")

    def test_clean_text_unchanged(self):
        """Already correct text should pass through unchanged."""
        text = "This is a perfectly written sentence with no errors."
        result = self.gen.correct_text(text)
        self.assertEqual(text, result, "Clean text should not be modified")

    def test_preserves_capitalization(self):
        """Corrections should preserve the original casing pattern."""
        text = "She was Realy upset about it."
        result = self.gen.correct_text(text)
        # Should be "Really" (capital R preserved)
        self.assertIn("Really", result, "Should preserve capitalization on corrections")

    def test_handles_empty_text(self):
        """Empty string should not crash."""
        result = self.gen.correct_text("")
        self.assertEqual("", result)


if __name__ == "__main__":
    # Run with verbose output
    unittest.main(verbosity=2)
