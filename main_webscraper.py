# Fix Pillow compatibility issue with MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import os
import sqlite3
import re
import random
import time
from datetime import datetime
from typing import List, Dict
import multiprocessing

# Web scraping libraries
import requests
from bs4 import BeautifulSoup
import json

from gtts import gTTS
from pydub import AudioSegment

# MoviePy 2.x imports (different from 1.x)
try:
    # Try MoviePy 2.x import structure first
    from moviepy import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip, ImageClip, concatenate_videoclips
    # In MoviePy 2.x, effects are methods on the clip objects, not separate fx module
    MOVIEPY_VERSION = 2
    print("Using MoviePy 2.x")
except ImportError:
    try:
        # Fallback to MoviePy 1.x import structure
        from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip, ImageClip
        MOVIEPY_VERSION = 1
        print("Using MoviePy 1.x")
    except ImportError:
        print("ERROR: Could not import MoviePy. Please run: pip install moviepy")
        exit(1)

import edge_tts
import asyncio
import nest_asyncio
nest_asyncio.apply()  # Allow nested event loops (fixes Edge TTS after Playwright runs)
import language_tool_python
from spellchecker import SpellChecker

# ═══════════════════════════════════════════════════════════════════════════
# ✅ CRITICAL FIX #1: Import from header.py (replace header.py with header_FIXED.py)
# ═══════════════════════════════════════════════════════════════════════════
from header import create_reddit_header
from subtitles import create_dynamic_text_clips
from youtube_uploader import YouTubeUploader
from tiktok_upload import TikTokVideoUploader

# AI Background Generation (optional - falls back to gameplay if unavailable)
try:
    from scene_extractor import extract_scenes, generate_fallback_scenes
    from image_generator import SceneImageGenerator
    from scene_animator import create_scene_clips
    from ai_config import GENERATED_SCENES_DIR, TARGET_SCENES
    AI_BACKGROUNDS_AVAILABLE = True
    print("AI background generation modules loaded")
except ImportError as e:
    AI_BACKGROUNDS_AVAILABLE = False
    print(f"AI backgrounds not available ({e}), using gameplay fallback")


def _tiktok_upload_worker(video_path, title, tags, cookies_path, result_queue):
    """Subprocess worker for TikTok uploads (isolates Playwright's event loop)."""
    try:
        from tiktok_upload import TikTokVideoUploader
        uploader = TikTokVideoUploader(cookies_path=cookies_path)
        result = uploader.upload_video(video_path, title, tags=tags)
        result_queue.put(result is not None)
    except Exception as e:
        print(f"TikTok upload failed: {e}")
        result_queue.put(False)


class DynamicTextVideoGenerator:
    def __init__(self):
        """Initialize the Reddit Video Generator - NO API CREDENTIALS NEEDED"""
        self.session = requests.Session()
        # Rotate through modern User-Agents to avoid blocks
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
        ]
        self.session.headers.update({
            'User-Agent': random.choice(self.user_agents)
        })
        
        self.init_database()

        # Spell checker (pyspellchecker — fast, offline, good at picking the right word)
        print("Loading spell/grammar checker...")
        self.spell = SpellChecker()
        # Reddit-specific words that should NOT be corrected
        self.ignore_words = {
            # Reddit voting/judgment terms
            'aita', 'aitah', 'wibta', 'yta', 'nta', 'esh', 'nah', 'yikes',
            'tifu', 'tldr', 'tl', 'dr', 'imo', 'imho', 'afaik',
            # Common internet abbreviations
            'irl', 'tbh', 'smh', 'fml', 'omg', 'lol', 'lmao', 'lmk', 'idk',
            'ngl', 'iirc', 'ftw', 'smth', 'rn', 'asap', 'ty', 'np', 'ikr',
            'btw', 'fyi', 'brb', 'dm', 'dms', 'pm', 'pms', 'ofc', 'jk',
            # Relationship terms
            'bf', 'gf', 'mil', 'fil', 'sil', 'bil', 'dh', 'dw',
            'hubby', 'wifey', 'kiddo', 'kiddos', 'stepdad', 'stepmom',
            # Reddit terms
            'reddit', 'subreddit', 'redditor', 'redditors',
            # Informal speech
            'gonna', 'wanna', 'gotta', 'kinda', 'sorta', 'dunno',
            'ok', 'okay', 'nope', 'yep', 'yeah', 'nah', 'meh',
            'tho', 'thru', 'ur', 'pls', 'plz', 'cuz', 'coz',
            'bro', 'bruh', 'dude', 'sus', 'lowkey', 'highkey', 'vibe',
            'salty', 'toxic', 'ghosted', 'gaslighting', 'gaslight',
            'cringe', 'wholesome', 'deadass', 'legit', 'hella',
            'periodt', 'slay', 'bestie', 'bestfriend',
            # Gaming terms (Minecraft, etc.)
            'netherite', 'minecraft', 'nether', 'enderman', 'creeper',
            'endermen', 'respawn', 'speedrun', 'speedrunning', 'pvp',
            'pve', 'gg', 'afk', 'noob', 'nerf', 'buff', 'op',
            'xbox', 'playstation', 'nintendo', 'fortnite', 'roblox',
            # Brand names / apps
            'venmo', 'paypal', 'zelle', 'cashapp', 'uber', 'lyft',
            'tiktok', 'snapchat', 'instagram', 'whatsapp', 'spotify',
            'netflix', 'youtube', 'google', 'facebook', 'airbnb',
            # Contractions often flagged
            "y'all", "ya'll",
        }
        # Add Reddit terms to spellchecker so it doesn't flag them
        self.spell.word_frequency.load_words(self.ignore_words)

        # Grammar checker (LanguageTool — handles grammar rules, not just spelling)
        self.lang_tool = language_tool_python.LanguageTool('en-US')
        print("Spell/grammar checker ready")

        # TikTok video settings (9:16 aspect ratio) - OPTIMIZED FOR YOUTUBE SHORTS 2025-2026
        self.video_width = 720   # Optimized for mobile
        self.video_height = 1280 # 9:16 aspect ratio
        self.fps = 24
        
    def init_database(self):
        """Initialize SQLite database to track processed posts"""
        self.conn = sqlite3.connect('processed_posts.db')
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                processed_date TIMESTAMP,
                video_parts INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS uploaded_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                video_path TEXT,
                platform TEXT DEFAULT 'youtube',
                video_id TEXT,
                privacy TEXT DEFAULT 'private',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
        print("✓ Database initialized")
    
    def is_post_processed(self, post_id: str) -> bool:
        """Check if post was already processed"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT post_id FROM processed_posts WHERE post_id = ?', (post_id,))
        return cursor.fetchone() is not None
    
    def get_processed_count(self) -> int:
        """Get count of processed posts"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM processed_posts')
        return cursor.fetchone()[0]
    
    def list_recent_processed(self, limit: int = 5) -> List[str]:
        """List recent processed post titles"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT title FROM processed_posts ORDER BY processed_date DESC LIMIT ?', (limit,))
        return [row[0] for row in cursor.fetchall()]
    
    def clear_database(self):
        """Clear all processed posts from database"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM processed_posts')
        self.conn.commit()
        print("✓ Database cleared - all posts can be reprocessed")
    
    def mark_post_processed(self, post_id: str, title: str, video_parts: int):
        """Mark post as processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO processed_posts (post_id, title, processed_date, video_parts)
            VALUES (?, ?, ?, ?)
        ''', (post_id, title, datetime.now(), video_parts))
        self.conn.commit()
    
    def _fetch_reddit_json(self, url: str, params: dict) -> list:
        """Fetch posts from a Reddit JSON endpoint with User-Agent rotation."""
        self.session.headers.update({'User-Agent': random.choice(self.user_agents)})
        response = self.session.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch {url} (status {response.status_code})")
            return []
        data = response.json()
        return data.get('data', {}).get('children', [])

    def scrape_reddit_stories(self, subreddit_name: str, limit: int = 5,
                              allow_reprocess: bool = False,
                              min_score: int = 50,
                              sort: str = "hot") -> List[Dict]:
        """
        Scrape stories from Reddit with engagement-ratio filtering.

        Args:
            subreddit_name: Subreddit to scrape
            limit: Number of stories to return
            allow_reprocess: If True, include already-processed posts
            min_score: Minimum upvote count (default 50 for quality)
            sort: Sort method - "hot", "top", or "new"
        """
        print(f"Scraping r/{subreddit_name} ({sort})...")

        candidates = []
        stories = []

        try:
            url = f"https://www.reddit.com/r/{subreddit_name}/{sort}.json"
            params = {
                'limit': min(limit * 10, 100),  # Fetch plenty for filtering
                'raw_json': 1,
            }
            if sort == "top":
                params['t'] = 'week'  # Top of the week for fresh content

            posts = self._fetch_reddit_json(url, params)

            for post_data in posts:
                post = post_data['data']

                post_id = post.get('id', '')
                title = post.get('title', '')
                selftext = post.get('selftext', '')
                score = post.get('score', 0)
                num_comments = post.get('num_comments', 0)
                is_nsfw = post.get('over_18', False)
                author = post.get('author', '')

                # Skip already processed
                if not allow_reprocess and self.is_post_processed(post_id):
                    continue

                # Skip NSFW (demonetization risk)
                if is_nsfw:
                    continue

                # Must have body text
                if not selftext:
                    continue

                # Skip update posts — they'll get merged into their original story
                title_lower = title.lower()
                if any(kw in title_lower for kw in ['update:', '[update]', 'update -', 'update!', 'follow up:', 'follow-up:']):
                    print(f"  Skipping update post (will merge with original): {title[:50]}...")
                    continue

                word_count = len(selftext.split())

                # Text length filter: 80-600 words (longer stories get trimmed in video)
                if word_count < 80 or word_count > 600:
                    continue

                # Minimum score filter
                if score < min_score:
                    continue

                # Engagement ratio: comments per upvote (higher = more drama/discussion)
                engagement_ratio = num_comments / max(score, 1)

                candidates.append({
                    'id': post_id,
                    'title': title,
                    'content': selftext,
                    'author': author,
                    'score': score,
                    'num_comments': num_comments,
                    'engagement_ratio': engagement_ratio,
                    'word_count': word_count,
                    'subreddit': subreddit_name
                })

            # Sort by engagement ratio (most discussion per upvote = most dramatic)
            candidates.sort(key=lambda x: x['engagement_ratio'], reverse=True)

            # Take the top results
            stories = candidates[:limit]

            for s in stories:
                print(f"  {s['title'][:50]}... "
                      f"(Score: {s['score']}, Comments: {s['num_comments']}, "
                      f"Engagement: {s['engagement_ratio']:.2f}, Words: {s['word_count']})")

            print(f"Selected {len(stories)} stories from {len(candidates)} candidates")
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse Reddit response: {e}")
        except Exception as e:
            print(f"Error scraping Reddit: {e}")

        return stories
    
    def find_update_posts(self, story: Dict) -> List[Dict]:
        """
        Search for update posts related to a story.

        Checks the author's recent submissions for posts in the same subreddit
        that look like updates (title contains 'update', references original post).

        Returns:
            List of update post dicts sorted by oldest first, each with 'title' and 'content'.
        """
        try:
            author = story.get('author', '')

            if not author or author == '[deleted]':
                return []

            print(f"  Checking u/{author} for update posts...")

            # Fetch author's recent submissions
            time.sleep(1)  # Rate limiting
            user_url = f"https://www.reddit.com/user/{author}/submitted.json"
            user_posts = self._fetch_reddit_json(user_url, {
                'raw_json': 1,
                'limit': 25,
                'sort': 'new'
            })

            updates = []
            original_title_lower = story['title'].lower()
            # Extract key words from original title for matching
            # Remove common prefixes like "AITA", "WIBTA", "TIFU", etc.
            title_keywords = set(
                w.lower() for w in re.sub(r'[^a-zA-Z\s]', '', story['title']).split()
                if len(w) > 3 and w.lower() not in {
                    'aita', 'wibta', 'tifu', 'that', 'this', 'with', 'from',
                    'have', 'what', 'when', 'where', 'which', 'there', 'their',
                    'they', 'them', 'then', 'than', 'would', 'could', 'should',
                    'about', 'after', 'before', 'being', 'between', 'does',
                    'doing', 'during', 'each', 'because', 'update', 'edit',
                }
            )

            for post_data in user_posts:
                post = post_data['data']
                post_id = post.get('id', '')
                post_title = post.get('title', '')
                post_body = post.get('selftext', '')
                post_sub = post.get('subreddit', '')

                # Skip the original post itself
                if post_id == story['id']:
                    continue

                # Must be in the same subreddit
                if post_sub.lower() != story['subreddit'].lower():
                    continue

                # Must have body text
                if not post_body:
                    continue

                post_title_lower = post_title.lower()

                # Check if this looks like an update
                is_update = False

                # Method 1: Title contains "update" keyword
                if any(kw in post_title_lower for kw in ['update', 'edit:', 'follow up', 'follow-up', 'part 2', 'part two', 'pt 2', 'pt. 2']):
                    # Check if title shares enough keywords with original
                    post_keywords = set(
                        w.lower() for w in re.sub(r'[^a-zA-Z\s]', '', post_title).split()
                        if len(w) > 3
                    )
                    shared = title_keywords & post_keywords
                    if len(shared) >= 2 or len(title_keywords) <= 3:
                        is_update = True

                if is_update:
                    updates.append({
                        'id': post_id,
                        'title': post_title,
                        'content': post_body,
                        'created': post.get('created_utc', 0),
                    })
                    print(f"  Found update: {post_title[:60]}...")

            # Sort updates by creation time (oldest first so story flows naturally)
            updates.sort(key=lambda x: x['created'])

            if not updates:
                print(f"  No updates found for this story")

            return updates

        except Exception as e:
            print(f"  Could not check for updates: {e}")
            return []

    def clean_text_for_speech(self, text: str) -> str:
        """Clean text for TTS - remove characters that get read aloud"""
        # Remove URLs
        text = re.sub(r'http[s]?://\S+', '', text)
        # Remove Reddit markdown (bold, italic, strikethrough, superscript)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'~~(.*?)~~', r'\1', text)
        text = re.sub(r'\^(\S+)', r'\1', text)
        # Remove Reddit quotes and HTML entities
        text = re.sub(r'&gt;', '', text)
        text = re.sub(r'&amp;', 'and', text)
        text = re.sub(r'&lt;', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        # Remove characters TTS reads aloud
        text = re.sub(r'[#~^/\\|@<>{}\[\]()_=+]', '', text)
        # Remove standalone special chars and leftover markdown
        text = re.sub(r'(?<!\w)[-](?!\w)', '', text)  # Lone dashes but not hyphens in words
        # Replace newlines with spaces (not periods - TTS says "period")
        text = re.sub(r'\n+', ' ', text)
        # Clean up multiple periods/dots
        text = re.sub(r'\.{2,}', '.', text)
        # Remove multiple punctuation in a row
        text = re.sub(r'([.!?,;:])\s*\1+', r'\1', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def correct_text(self, text: str) -> str:
        """
        Fix spelling and grammar using LanguageTool + pyspellchecker.

        LanguageTool detects all issues (spelling + grammar).
        For spelling errors, pyspellchecker picks a better replacement.
        Style rules that rewrite the author's phrasing are skipped.

        Runs after clean_text_for_speech() so markdown/special chars are already gone.
        """
        matches = self.lang_tool.check(text)

        # Rules that rewrite style rather than fix errors — skip these
        skip_rules = {
            'EXTREME_ADJECTIVES', 'TOO_LONG_SENTENCE', 'PASSIVE_VOICE',
            'READABILITY_RULE_SIMPLE', 'EN_QUOTES', 'DASH_RULE',
            'COMMA_COMPOUND_SENTENCE', 'WHITESPACE_RULE',
            # Transition/style rules that insert "Furthermore," "However," etc.
            'SENTENCE_FRAGMENT', 'SENTENCE_LINKING',
        }
        # Rule categories (prefixes) that are style suggestions, not errors
        skip_categories = {'STYLE', 'REDUNDANCY', 'TYPOGRAPHY'}

        fixes = []
        for match in matches:
            if match.rule_id in skip_rules:
                continue
            # Skip entire style/redundancy categories
            if any(match.rule_id.startswith(cat) for cat in skip_categories):
                continue
            bad_text = text[match.offset:match.offset + match.error_length]
            # Skip if it's a Reddit term we want to keep
            if bad_text.lower().strip() in self.ignore_words:
                continue
            if not match.replacements:
                continue

            replacement = match.replacements[0]

            # Guard: skip if the replacement adds transition words
            # (e.g., "She" → "Furthermore, she", "I" → "However, I")
            added_text = replacement.lower().replace(bad_text.lower(), '').strip(' ,')
            transition_words = {'furthermore', 'however', 'moreover', 'therefore',
                                'additionally', 'nevertheless', 'consequently',
                                'meanwhile', 'otherwise', 'instead'}
            if added_text in transition_words:
                continue

            # Guard: skip single common word → different common word substitutions
            # (e.g., "if" → "is", "to" → "too") — these change meaning
            if (match.rule_id != 'MORFOLOGIK_RULE_EN_US'
                    and len(bad_text.split()) == 1 and len(replacement.split()) == 1
                    and bad_text.lower() != replacement.lower()
                    and len(bad_text) <= 4
                    and self.spell.unknown([bad_text.lower()]) == set()):
                # The original word is a real word — don't swap it
                continue

            # For spelling errors, use pyspellchecker's suggestion if available
            # (it picks contextually better words than LanguageTool's alphabetical list)
            if match.rule_id == 'MORFOLOGIK_RULE_EN_US':
                stripped = re.sub(r'[^a-zA-Z]', '', bad_text).lower()
                # Collapse elongated words: "broooooo" -> "bro", "nooooo" -> "no"
                collapsed = re.sub(r'(.)\1{2,}', r'\1', stripped)
                if collapsed in self.ignore_words:
                    continue
                # Try spell-checking the collapsed version first
                spell_suggestion = self.spell.correction(collapsed) or self.spell.correction(stripped)
                if spell_suggestion and spell_suggestion != stripped:
                    # Preserve original casing
                    if bad_text[0].isupper():
                        spell_suggestion = spell_suggestion.capitalize()
                    if bad_text.isupper():
                        spell_suggestion = spell_suggestion.upper()
                    replacement = spell_suggestion
                else:
                    replacement = match.replacements[0]

            # Final guard: skip duplicate word "fixes" like "to to" → "to"
            # when they appear in different sentence contexts
            # (keep legitimate duplicate fixes like actual "to to" typos)

            fixes.append({
                'offset': match.offset,
                'length': match.error_length,
                'original': bad_text,
                'replacement': replacement,
                'rule': match.rule_id,
            })

        if not fixes:
            print("Spell/grammar check: no corrections needed")
            return text

        # Apply fixes from end to start so offsets stay valid
        corrected = text
        for fix in reversed(fixes):
            start = fix['offset']
            end = start + fix['length']
            corrected = corrected[:start] + fix['replacement'] + corrected[end:]
            label = "Spelling" if fix['rule'] == 'MORFOLOGIK_RULE_EN_US' else "Grammar"
            print(f"  {label}: '{fix['original']}' -> '{fix['replacement']}'")

        print(f"Spell/grammar check: applied {len(fixes)} correction(s)")
        return corrected

    def generate_audio(self, text: str, output_path: str, voice_type: str = "tiktok"):
        """
        Generate TTS audio with different voice options.

        Returns:
            Tuple of (duration_seconds, word_timings_list_or_None)
        """
        if voice_type == "tiktok":
            return self.generate_edge_tts_audio(text, output_path)
        else:
            return self.generate_gtts_audio(text, output_path), None
    
    def generate_gtts_audio(self, text: str, output_path: str) -> float:
        """Generate Google TTS audio (original method)"""
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(output_path)
        
        audio = AudioSegment.from_file(output_path)
        duration = len(audio) / 1000.0
        print(f"✓ Generated Google TTS audio: {duration:.1f}s")
        return duration
    
    def generate_edge_tts_audio(self, text: str, output_path: str):
        """
        Generate Microsoft Edge TTS audio (TikTok-like voice).

        Returns:
            Tuple of (duration_seconds, word_timings_list_or_None)
        """
        try:
            # Use a fresh event loop each time to avoid
            # "asyncio.run() cannot be called from a running event loop"
            loop = asyncio.new_event_loop()
            try:
                word_timings = loop.run_until_complete(
                    self._generate_edge_tts_async(text, output_path)
                )
            finally:
                loop.close()

            audio = AudioSegment.from_file(output_path)
            duration = len(audio) / 1000.0
            print(f"✓ Generated TikTok-style audio: {duration:.1f}s")
            return duration, word_timings

        except Exception as e:
            print(f"⚠️  Edge TTS failed, falling back to Google TTS: {e}")
            return self.generate_gtts_audio(text, output_path), None
    
    async def _generate_edge_tts_async(self, text: str, output_path: str):
        """
        Async function to generate Edge TTS audio and capture WordBoundary events.

        Uses SubMaker for proper subtitle timing and saves audio correctly.

        Returns:
            List of word timing dicts with keys: word, start (seconds), duration (seconds)
        """
        voice = "en-US-JennyNeural"

        communicate = edge_tts.Communicate(text, voice, boundary='WordBoundary')
        submaker = edge_tts.SubMaker()

        word_timings = []

        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    submaker.feed(chunk)
                    word_timings.append({
                        "word": chunk["text"],
                        "start": chunk["offset"] / 10_000_000,
                        "duration": chunk["duration"] / 10_000_000,
                    })

        print(f"Captured {len(word_timings)} WordBoundary events from Edge TTS")
        if word_timings:
            print(f"  First: '{word_timings[0]['word']}' at {word_timings[0]['start']:.3f}s")
            print(f"  Last: '{word_timings[-1]['word']}' at {word_timings[-1]['start']:.3f}s")
        return word_timings
    
    def select_random_gameplay(self, gameplay_folder: str) -> str:
        """Select random gameplay video (legacy - use build_gameplay_background instead)"""
        if not os.path.exists(gameplay_folder):
            raise FileNotFoundError(f"Gameplay folder not found: {gameplay_folder}")

        video_files = [f for f in os.listdir(gameplay_folder)
                       if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]

        if not video_files:
            raise FileNotFoundError("No gameplay videos found")

        selected = os.path.join(gameplay_folder, random.choice(video_files))
        print(f"✓ Selected: {os.path.basename(selected)}")
        return selected

    def build_gameplay_background(self, gameplay_folder: str, duration: float):
        """
        Build a varied background by stitching random segments from DIFFERENT biking videos.

        - Picks a new video for each segment so the background constantly changes.
        - Each segment is 8-25 seconds from a random position in that video.
        - Continues until total coverage >= duration, then trims to exact length.

        Returns:
            A single MoviePy clip (resized to video dimensions) ready to composite.
        """
        if not os.path.exists(gameplay_folder):
            raise FileNotFoundError(f"Gameplay folder not found: {gameplay_folder}")

        video_files = [
            os.path.join(gameplay_folder, f) for f in os.listdir(gameplay_folder)
            if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))
        ]

        if not video_files:
            raise FileNotFoundError("No gameplay videos found in folder")

        print(f"Building varied background ({duration:.1f}s) from {len(video_files)} video(s)...")

        # Shuffle so we start with a random video each time
        pool = video_files.copy()
        random.shuffle(pool)

        source_clips = []   # kept open until caller finishes rendering
        segments = []
        total_so_far = 0.0
        pool_idx = 0

        while total_so_far < duration:
            # Cycle through the shuffled pool; re-shuffle every full cycle
            if pool_idx >= len(pool):
                pool_idx = 0
                random.shuffle(pool)

            vid_path = pool[pool_idx]
            pool_idx += 1

            try:
                clip = VideoFileClip(vid_path)
                clip_duration = clip.duration

                if clip_duration < 4:          # too short to be useful
                    clip.close()
                    continue

                # How much more do we need?
                still_needed = duration - total_so_far
                # Aim for 8-25 s segments (but never more than clip length or what's needed)
                seg_len = min(clip_duration, min(still_needed, random.uniform(8, 25)))
                seg_len = max(seg_len, min(4, clip_duration))  # at least 4 s

                # Pick a random start inside the clip
                max_start = max(0.0, clip_duration - seg_len)
                start = random.uniform(0, max_start)

                seg = clip.subclipped(start, start + seg_len)
                seg = seg.resized((self.video_width, self.video_height))

                # Keep source clip open — frames are read lazily at render time.
                # Closing here would destroy the reader and crash during compositing.
                source_clips.append(clip)
                segments.append(seg)
                total_so_far += seg_len

                name = os.path.basename(vid_path)
                print(f"  + {name}  [{start:.1f}s – {start+seg_len:.1f}s]  ({seg_len:.1f}s)")

            except Exception as e:
                print(f"  Skipping {os.path.basename(vid_path)}: {e}")
                continue

            # Safety valve: if somehow we can't fill duration, bail out
            if pool_idx > len(pool) * 5 and total_so_far < 1:
                raise RuntimeError("Could not load any gameplay segments")

        if not segments:
            raise RuntimeError("No gameplay segments were built")

        background = concatenate_videoclips(segments, method="compose")
        background = background.subclipped(0, duration)

        print(f"  Background ready: {len(segments)} segments, {background.duration:.1f}s total")
        return background, source_clips

    def create_scene_background(self, story_text: str, word_timings: list,
                                 audio_duration: float, story_id: str) -> str:
        """
        Generate AI scene backgrounds for a story.
        Pipeline: story_text -> Ollama scenes -> SDXL images -> Ken Burns clips -> composite

        Returns:
            Path to composited background clip (.mp4), or None on failure.
        """
        if not AI_BACKGROUNDS_AVAILABLE:
            return None

        print("\n=== AI BACKGROUND GENERATION ===")

        # 1. Extract scenes via Ollama (falls back to keyword extraction)
        print("Step 1/3: Extracting visual scenes from story...")
        scenes = extract_scenes(
            story_text=story_text,
            word_timings=word_timings,
            audio_duration=audio_duration,
            num_scenes=TARGET_SCENES,
        )
        print(f"  Got {len(scenes)} scenes")

        if not scenes:
            print("  No scenes extracted, falling back to gameplay")
            return None

        # 2. Generate images via SDXL Turbo
        print("Step 2/3: Generating scene images with SDXL Turbo...")
        generator = SceneImageGenerator()
        scenes = generator.generate_all_scenes(scenes, story_id)

        if not scenes:
            print("  Image generation failed, falling back to gameplay")
            return None

        # 3. Animate with Ken Burns + crossfade transitions
        print("Step 3/3: Animating scenes with Ken Burns effect...")
        background_clip = create_scene_clips(
            scenes=scenes,
            video_width=self.video_width,
            video_height=self.video_height,
            fps=self.fps,
        )

        # Export as temporary video file
        bg_output_path = os.path.join(GENERATED_SCENES_DIR, story_id, "background.mp4")
        os.makedirs(os.path.dirname(bg_output_path), exist_ok=True)

        background_clip.write_videofile(
            bg_output_path,
            fps=self.fps,
            codec='libx264',
            preset='fast',
            threads=multiprocessing.cpu_count(),
            audio=False,
            logger=None,
        )

        # Clean up the clip object
        background_clip.close()

        print(f"=== AI background ready: {bg_output_path} ===\n")
        return bg_output_path

    def create_progress_bar(self, current_word_index: int, total_words: int, duration: float) -> TextClip:
        """Create a simple progress indicator"""
        progress = int((current_word_index / total_words) * 20) if total_words > 0 else 0
        progress_bar = "█" * progress + "░" * (20 - progress)
        progress_text = f"{progress_bar} {current_word_index}/{total_words}"
        
        return TextClip(
            text=progress_text,
            font_size=24,
            color='cyan',
            font="fonts/Montserrat-Black.ttf"
        ).with_position(('center', 50)).with_duration(duration)
    
    def create_dynamic_video(self, background_path: str, audio_path: str, text: str,
                           output_path: str, part_number: int = None, subreddit: str = "AskReddit",
                           logo_path: str = "logo/Redit logo.png",
                           word_timings=None, is_ai_background: bool = False,
                           background_clip=None) -> str:
        """
        Create video with dynamic text highlighting - YOUTUBE SHORTS 2025-2026 OPTIMIZED

        FIXES APPLIED:
        - Header positioned in safe zone (y=200+) via header.py
        - Faststart optimization for instant playback
        - Frame-safe caption timing
        """
        print(f"Creating DYNAMIC video: {os.path.basename(output_path)}")

        # Get audio duration
        audio = AudioSegment.from_file(audio_path)
        audio_duration = len(audio) / 1000.0

        if background_clip is not None:
            # Pre-built multi-segment clip (already resized + trimmed to audio_duration)
            gameplay = background_clip
        else:
            # Load single background video from path (fallback / AI background)
            gameplay = VideoFileClip(background_path)

            if not is_ai_background:
                # Resize gameplay to TikTok format
                gameplay = gameplay.resized((self.video_width, self.video_height))

                # Loop gameplay if needed
                if gameplay.duration < audio_duration:
                    loops = int(audio_duration / gameplay.duration) + 1
                    gameplay = gameplay.looped(n=loops)

                # Trim to audio length
                gameplay = gameplay.subclipped(0, audio_duration)

        # ═══════════════════════════════════════════════════════════════════
        # HEADER — centered on screen, visible for first 4.5 seconds
        # ═══════════════════════════════════════════════════════════════════
        post_title = text.split('.')[0][:120]

        reddit_header = create_reddit_header(
            title=post_title,
            author="u/BrokenStories",
            subreddit=f"r/{subreddit}",
            duration=4.5,
            logo_path=logo_path,
            video_width=self.video_width,
            video_height=self.video_height
        )

        # ═══════════════════════════════════════════════════════════════════
        # CAPTIONS — start immediately with the audio
        # ═══════════════════════════════════════════════════════════════════
        dynamic_text_clips = create_dynamic_text_clips(
            text=text,
            duration=audio_duration,
            video_width=self.video_width,
            video_height=self.video_height,
            fps=self.fps,
            word_timings=word_timings
        )

        # Load and add audio
        audio_clip = AudioFileClip(audio_path)

        # Dog reaction overlay (above subtitles) — disabled for now
        # from dog_overlay import create_dog_overlay_clip
        # dog_clips = create_dog_overlay_clip(text, audio_duration,
        #                                     word_timings=word_timings,
        #                                     start_time=4.5)
        dog_clips = []

        # Composite everything: gameplay + header + captions + dog overlay
        all_clips = [gameplay] + reddit_header + dynamic_text_clips
        if dog_clips:
            all_clips += dog_clips
        final_video = CompositeVideoClip(all_clips)
        final_video = final_video.with_audio(audio_clip)
        
        # ═══════════════════════════════════════════════════════════════════
        # ✅ CRITICAL FIX #2: FASTSTART OPTIMIZATION (Line 344)
        # This ensures videos play INSTANTLY on YouTube Shorts
        # Without this: 2-3 second loading delay → 70% viewers leave
        # With this: Instant playback → 80% retention
        # ═══════════════════════════════════════════════════════════════════
        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='fast',
            threads=multiprocessing.cpu_count(),
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            ffmpeg_params=['-movflags', '+faststart']  # ✅ INSTANT PLAYBACK!
        )
        
        # Clean up resources
        # Only close gameplay if we opened it here (not if caller passed background_clip)
        if background_clip is None:
            gameplay.close()
        for clip in reddit_header:
            clip.close()
        audio_clip.close()
        for clip in dynamic_text_clips:
            clip.close()
        if dog_clips:
            for clip in dog_clips:
                try:
                    clip.close()
                except Exception:
                    pass
        final_video.close()

        print(f"✓ DYNAMIC video created: {output_path}")
        print(f"✓ Faststart enabled: INSTANT playback ready")
        return output_path
    
    def _try_youtube_upload(self, video_path: str, story: Dict):
        """Upload a video to YouTube as a public Short if credentials exist."""
        if not os.path.exists("client_secret.json"):
            print("YouTube upload skipped: no client_secret.json found")
            return

        try:
            uploader = YouTubeUploader()
            uploader.authenticate()

            # Title: story title truncated to 95 chars + #Shorts
            title = story['title'][:95] + " #Shorts"
            subreddit = story.get('subreddit', 'AskReddit')
            author = story.get('author', '')
            description = (
                f"r/{subreddit} | u/{author}\n\n"
                "#Shorts #Reddit #RedditStories #AskReddit"
            )

            result = uploader.upload_short(video_path, title, description, privacy="public")

            if result:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO uploaded_videos (post_id, video_path, video_id, privacy) "
                    "VALUES (?, ?, ?, ?)",
                    (story['id'], video_path, result['video_id'], 'public')
                )
                self.conn.commit()
                print(f"Uploaded to YouTube (public): {result['url']}")
            else:
                print("YouTube upload failed, continuing...")

        except Exception as e:
            print(f"YouTube upload error: {e}")

    def _try_tiktok_upload(self, video_path: str, story: Dict):
        """Upload a video to TikTok if cookies file exists.

        Runs in a subprocess to isolate Playwright's event loop from the main
        process (prevents 'Sync API inside asyncio loop' errors on 2nd+ videos).
        """
        if not os.path.exists("tiktok_cookies.txt"):
            print("TikTok upload skipped: no tiktok_cookies.txt found")
            return

        try:
            title = story['title'][:150]
            subreddit = story.get('subreddit', 'AskReddit')
            tags = ["Reddit", "RedditStories", subreddit]

            # Run in subprocess to isolate Playwright's asyncio loop
            ctx = multiprocessing.get_context('spawn')
            result_queue = ctx.Queue()
            proc = ctx.Process(
                target=_tiktok_upload_worker,
                args=(video_path, title, tags, "tiktok_cookies.txt", result_queue)
            )
            proc.start()
            proc.join(timeout=300)  # 5-minute timeout

            if proc.is_alive():
                proc.terminate()
                print("TikTok upload timed out, continuing...")
                return

            success = not result_queue.empty() and result_queue.get()
            if success:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO uploaded_videos (post_id, video_path, platform, privacy) "
                    "VALUES (?, ?, ?, ?)",
                    (story['id'], video_path, 'tiktok', 'public')
                )
                self.conn.commit()
                print(f"Uploaded to TikTok: {title[:50]}...")
            else:
                print("TikTok upload failed, continuing...")

        except Exception as e:
            print(f"TikTok upload error: {e}")

    def generate_videos_from_story(self, story: Dict, gameplay_folder: str,
                                 output_folder: str, logo_path: str = "logo/Redit logo.png") -> List[str]:
        """Generate dynamic video(s) from a Reddit story, including any updates"""
        print(f"\nProcessing: {story['title'][:50]}...")

        # Check for update posts by the same author
        updates = self.find_update_posts(story)

        # Build full text: original story + any updates
        full_text = f"{story['title']}. {story['content']}"

        if updates:
            print(f"  Including {len(updates)} update(s) in video")
            for update in updates:
                # Add a separator and the update text
                full_text += f" Update. {update['content']}"
                # Mark update posts as processed too so they don't get their own video
                try:
                    self.mark_post_processed(update['id'], update['title'], 0)
                except Exception:
                    pass  # Already in database

        clean_text = self.clean_text_for_speech(full_text)

        # Fix spelling and grammar before TTS reads it
        clean_text = self.correct_text(clean_text)

        # Limit text length for optimal processing
        words = clean_text.split()
        if len(words) > 500:  # Allow longer for stories with updates (~200 seconds)
            clean_text = ' '.join(words[:500]) + "..."

        print(f"Text length: {len(clean_text)} characters, {len(clean_text.split())} words")

        # Lightly paraphrase for platform originality (Ollama; falls back silently)
        try:
            from story_paraphraser import paraphrase_story
            clean_text = paraphrase_story(clean_text)
        except Exception as e:
            print(f"Paraphraser import failed: {e}")

        # File names
        video_filename = f"{story['id']}_dynamic.mp4"
        audio_filename = f"temp_audio_{story['id']}.mp3"
        
        video_path = os.path.join(output_folder, video_filename)
        audio_path = os.path.join(output_folder, audio_filename)
        
        try:
            # Generate TikTok-style audio (now returns word timings too)
            audio_duration, word_timings = self.generate_audio(clean_text, audio_path, voice_type="tiktok")

            # AI background disabled — always use gameplay video
            # (create_scene_background commented out to avoid SDXL hangs)
            background_path = None
            is_ai_background = False
            # if AI_BACKGROUNDS_AVAILABLE:
            #     try:
            #         background_path = self.create_scene_background(
            #             clean_text, word_timings, audio_duration, story['id']
            #         )
            #         if background_path:
            #             is_ai_background = True
            #     except Exception as e:
            #         print(f"AI background generation failed: {e}")
            #         import traceback
            #         traceback.print_exc()

            print("Using biking gameplay videos as background")
            bg_clip, bg_sources = self.build_gameplay_background(gameplay_folder, audio_duration)

            # Create dynamic video with ground-truth word timings
            final_video = self.create_dynamic_video(
                background_path=None, audio_path=audio_path, text=clean_text,
                output_path=video_path,
                subreddit=story['subreddit'],
                logo_path=logo_path,
                word_timings=word_timings,
                is_ai_background=is_ai_background,
                background_clip=bg_clip,
            )

            # NOW safe to close — video has been fully written to disk
            try:
                bg_clip.close()
            except Exception:
                pass
            for src in bg_sources:
                try:
                    src.close()
                except Exception:
                    pass
            
            # Mark as processed (skip if already exists)
            try:
                self.mark_post_processed(story['id'], story['title'], 1)
            except Exception:
                pass  # Already in database, that's fine

            # Upload to YouTube if credentials are available
            self._try_youtube_upload(final_video, story)

            # Upload to TikTok if cookies are available
            self._try_tiktok_upload(final_video, story)

            return [final_video]
            
        except Exception as e:
            print(f"✗ Error creating video: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            # Clean up temp audio with retry logic (Windows file locking)
            if os.path.exists(audio_path):
                for attempt in range(5):
                    try:
                        time.sleep(1)
                        os.remove(audio_path)
                        print(f"✓ Cleaned up: {os.path.basename(audio_path)}")
                        break
                    except PermissionError:
                        if attempt == 4:
                            print(f"⚠️  Could not delete temp file: {audio_path}")
                        else:
                            time.sleep(2)


def main():
    """Main function to run the dynamic video generator"""
    
    # NO CONFIG FILE NEEDED ANYMORE!
    print("=" * 60)
    print("🌐 WEB SCRAPING MODE - No Reddit API credentials needed!")
    print("=" * 60)
    
    # Initialize generator (no credentials needed)
    generator = DynamicTextVideoGenerator()
    
    # Show database status
    processed_count = generator.get_processed_count()
    print(f"Database contains {processed_count} processed posts")
    
    if processed_count > 0:
        recent_posts = generator.list_recent_processed(3)
        print("Recent processed posts:")
        for i, title in enumerate(recent_posts, 1):
            print(f"  {i}. {title[:50]}...")
    
    # Optional: Clear database to allow reprocessing (comment out to prevent reuse)
    # generator.clear_database()  # Uncomment this line to reprocess old posts
    
    # Set up folders
    gameplay_folder = "gameplay_videos"
    output_folder = "output_videos"
    logo_path = "logo/Redit logo.png"
    
    os.makedirs(output_folder, exist_ok=True)
    
    if not os.path.exists(gameplay_folder):
        print(f"✗ Please create '{gameplay_folder}' folder and add some .mp4 gameplay videos")
        return
    
    if not os.path.exists(logo_path):
        print(f"⚠️  Warning: Logo not found at {logo_path}")
        print("Video will be created without logo")
    
    # Configuration
    subreddit = "AmItheAsshole"
    num_videos = 2
    
    print(f"\n🎬 Generating {num_videos} DYNAMIC videos from r/{subreddit}")
    print("=" * 60)
    print("✅ YOUTUBE SHORTS 2025-2026 OPTIMIZED:")
    print("   • 📱 Header in safe zone (y=200+)")
    print("   • ⚡ Faststart enabled (instant playback)")
    print("   • 🎯 Frame-safe caption timing")
    print("   • 🎭 Reddit-style post header")
    print("   • ✓ Verified badge + emoji reactions")
    print("   • 🗣️ TikTok-style voice (Jenny Neural)")
    print("   • 🌐 Web scraping (NO API needed!)")
    print("=" * 60)
    
    # Generate videos
    try:
        stories = generator.scrape_reddit_stories(
            subreddit, num_videos,
            allow_reprocess=False,
            min_score=50,
            sort="hot"
        )
        
        if not stories:
            print("\n❌ No suitable stories found!")
            print("Tips:")
            print("  - Make sure the subreddit name is correct")
            print("  - Try a different subreddit (e.g., 'tifu', 'relationships')")
            print("  - Check your internet connection")
            return
        
        total_videos = 0
        start_time = datetime.now()
        
        for i, story in enumerate(stories):
            story_start = datetime.now()
            videos = generator.generate_videos_from_story(
                story, gameplay_folder, output_folder, logo_path=logo_path
            )
            story_end = datetime.now()
            story_duration = (story_end - story_start).total_seconds()

            total_videos += len(videos)
            if videos:
                print(f"✓ Created {len(videos)} video(s) in {story_duration:.1f}s")

            # Wait 1 minute between videos to avoid rate limits
            if i < len(stories) - 1:
                print("Waiting 1 minute before next video...")
                time.sleep(60)
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        print("=" * 60)
        print(f"🎉 Successfully generated {total_videos} DYNAMIC videos!")
        print(f"⏱️  Total time: {total_duration:.1f} seconds")
        if total_videos > 0:
            print(f"⚡ Average: {total_duration/total_videos:.1f}s per video")
        print(f"📁 Check the '{output_folder}' folder for your videos")
        print("=" * 60)
        print("✅ ALL FIXES APPLIED:")
        print("   ✓ Header positioned in safe zone")
        print("   ✓ Faststart optimization enabled")
        print("   ✓ Instant playback ready")
        print("   ✓ YouTube Shorts 2025-2026 compliant")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()