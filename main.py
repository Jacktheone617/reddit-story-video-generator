# Fix Pillow compatibility issue with MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import os
import sqlite3
import re
import random
from datetime import datetime
from typing import List, Dict
import multiprocessing

import praw
from gtts import gTTS
from pydub import AudioSegment

# MoviePy 2.x imports (different from 1.x)
try:
    from moviepy import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip, ImageClip
    MOVIEPY_VERSION = 2
    print("Using MoviePy 2.x")
except ImportError:
    try:
        from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip, ImageClip
        MOVIEPY_VERSION = 1
        print("Using MoviePy 1.x")
    except ImportError:
        print("ERROR: Could not import MoviePy. Please run: pip install moviepy")
        exit(1)

import edge_tts
import asyncio

from header import create_reddit_header
from subtitles import create_dynamic_text_clips


class DynamicTextVideoGenerator:
    def __init__(self, reddit_client_id: str, reddit_client_secret: str, reddit_user_agent: str):
        """Initialize the Reddit Video Generator"""
        self.reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent=reddit_user_agent
        )

        self.init_database()

        # TikTok video settings (9:16 aspect ratio) - OPTIMIZED
        self.video_width = 720
        self.video_height = 1280
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
        self.conn.commit()
        print("Database initialized")

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
        print("Database cleared - all posts can be reprocessed")

    def mark_post_processed(self, post_id: str, title: str, video_parts: int):
        """Mark post as processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO processed_posts (post_id, title, processed_date, video_parts)
            VALUES (?, ?, ?, ?)
        ''', (post_id, title, datetime.now(), video_parts))
        self.conn.commit()

    def scrape_reddit_stories(self, subreddit_name: str, limit: int = 5, allow_reprocess: bool = False) -> List[Dict]:
        """Scrape stories from Reddit using PRAW API"""
        print(f"Scraping r/{subreddit_name}...")

        subreddit = self.reddit.subreddit(subreddit_name)
        stories = []

        for submission in subreddit.hot(limit=limit * 10):
            if not allow_reprocess and self.is_post_processed(submission.id):
                print(f"Skipping already processed: {submission.title[:30]}...")
                continue

            if (submission.selftext and
                len(submission.selftext) > 100 and
                len(submission.selftext) < 2000 and
                submission.score > 5):

                stories.append({
                    'id': submission.id,
                    'title': submission.title,
                    'content': submission.selftext,
                    'score': submission.score,
                    'subreddit': subreddit_name
                })

                print(f"Found story: {submission.title[:50]}... (Score: {submission.score})")

                if len(stories) >= limit:
                    break

        print(f"Found {len(stories)} suitable stories")
        return stories

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
        print(f"Generated Google TTS audio: {duration:.1f}s")
        return duration

    def generate_edge_tts_audio(self, text: str, output_path: str):
        """
        Generate Microsoft Edge TTS audio (TikTok-like voice).

        Returns:
            Tuple of (duration_seconds, word_timings_list_or_None)
        """
        try:
            word_timings = asyncio.run(self._generate_edge_tts_async(text, output_path))

            audio = AudioSegment.from_file(output_path)
            duration = len(audio) / 1000.0
            print(f"Generated TikTok-style audio: {duration:.1f}s")
            return duration, word_timings

        except Exception as e:
            print(f"Edge TTS failed, falling back to Google TTS: {e}")
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
        """Select random gameplay video"""
        if not os.path.exists(gameplay_folder):
            raise FileNotFoundError(f"Gameplay folder not found: {gameplay_folder}")

        video_files = [f for f in os.listdir(gameplay_folder)
                      if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm'))]

        if not video_files:
            raise FileNotFoundError("No gameplay videos found")

        selected = os.path.join(gameplay_folder, random.choice(video_files))
        print(f"Selected: {os.path.basename(selected)}")
        return selected

    def create_dynamic_video(self, gameplay_path: str, audio_path: str, text: str,
                           output_path: str, part_number: int = None,
                           subreddit: str = "AskReddit",
                           logo_path: str = "logo/Redit logo.png",
                           word_timings=None) -> str:
        """Create video with dynamic text highlighting - YouTube Shorts optimized"""
        print(f"Creating DYNAMIC video: {os.path.basename(output_path)}")

        # Load gameplay video
        gameplay = VideoFileClip(gameplay_path)

        # Get audio duration
        audio = AudioSegment.from_file(audio_path)
        audio_duration = len(audio) / 1000.0

        # Resize gameplay to TikTok format
        if MOVIEPY_VERSION == 2:
            gameplay = gameplay.resized((self.video_width, self.video_height))
        else:
            gameplay = gameplay.resize((self.video_width, self.video_height))

        # Loop gameplay if needed
        if gameplay.duration < audio_duration:
            loops = int(audio_duration / gameplay.duration) + 1
            if MOVIEPY_VERSION == 2:
                gameplay = gameplay.looped(n=loops)
            else:
                gameplay = gameplay.loop(n=loops)

        # Trim to audio length
        if MOVIEPY_VERSION == 2:
            gameplay = gameplay.subclipped(0, audio_duration)
        else:
            gameplay = gameplay.subclip(0, audio_duration)

        # Reddit-style header
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

        # Frame-safe word-by-word captions with ground-truth timings
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
        if MOVIEPY_VERSION == 2:
            gameplay = gameplay.with_audio(audio_clip)
        else:
            gameplay = gameplay.set_audio(audio_clip)

        # Composite everything
        all_clips = [gameplay] + reddit_header + dynamic_text_clips
        final_video = CompositeVideoClip(all_clips)

        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='fast',
            threads=multiprocessing.cpu_count(),
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            ffmpeg_params=['-movflags', '+faststart']
        )

        # Clean up resources
        gameplay.close()
        for clip in reddit_header:
            clip.close()
        audio_clip.close()
        for clip in dynamic_text_clips:
            clip.close()
        final_video.close()

        print(f"DYNAMIC video created: {output_path}")
        return output_path

    def generate_videos_from_story(self, story: Dict, gameplay_folder: str,
                                 output_folder: str, logo_path: str = "logo/Redit logo.png") -> List[str]:
        """Generate dynamic video(s) from a Reddit story"""
        print(f"\nProcessing: {story['title'][:50]}...")

        # Prepare text
        full_text = f"{story['title']}. {story['content']}"
        clean_text = self.clean_text_for_speech(full_text)

        # Limit text length for optimal processing
        words = clean_text.split()
        if len(words) > 250:
            clean_text = ' '.join(words[:250]) + "..."

        print(f"Text length: {len(clean_text)} characters, {len(clean_text.split())} words")

        # File names
        video_filename = f"{story['id']}_dynamic.mp4"
        audio_filename = f"temp_audio_{story['id']}.mp3"

        video_path = os.path.join(output_folder, video_filename)
        audio_path = os.path.join(output_folder, audio_filename)

        try:
            # Generate TikTok-style audio (now returns word timings too)
            audio_duration, word_timings = self.generate_audio(clean_text, audio_path, voice_type="tiktok")

            # Select gameplay
            gameplay_path = self.select_random_gameplay(gameplay_folder)

            # Create dynamic video with ground-truth word timings
            final_video = self.create_dynamic_video(
                gameplay_path, audio_path, clean_text, video_path,
                subreddit=story['subreddit'],
                logo_path=logo_path,
                word_timings=word_timings
            )

            # Mark as processed
            try:
                self.mark_post_processed(story['id'], story['title'], 1)
            except Exception:
                pass  # Already in database

            return [final_video]

        except Exception as e:
            print(f"Error creating video: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            # Clean up temp audio with retry logic (Windows file locking issue)
            if os.path.exists(audio_path):
                import time
                for attempt in range(3):
                    try:
                        time.sleep(0.5)
                        os.remove(audio_path)
                        break
                    except PermissionError:
                        if attempt == 2:
                            print(f"Could not delete temp audio file: {audio_path}")
                        else:
                            time.sleep(1)


def main():
    """Main function to run the dynamic video generator"""

    try:
        from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    except ImportError:
        print("Please create config.py with your Reddit API credentials")
        return

    # Initialize generator
    generator = DynamicTextVideoGenerator(
        REDDIT_CLIENT_ID,
        REDDIT_CLIENT_SECRET,
        REDDIT_USER_AGENT
    )

    # Show database status
    processed_count = generator.get_processed_count()
    print(f"Database contains {processed_count} processed posts")

    if processed_count > 0:
        recent_posts = generator.list_recent_processed(3)
        print("Recent processed posts:")
        for i, title in enumerate(recent_posts, 1):
            print(f"  {i}. {title[:50]}...")

    # Set up folders
    gameplay_folder = "gameplay_videos"
    output_folder = "output_videos"
    logo_path = "logo/Redit logo.png"

    os.makedirs(output_folder, exist_ok=True)

    if not os.path.exists(gameplay_folder):
        print(f"Please create '{gameplay_folder}' folder and add some .mp4 gameplay videos")
        return

    # Configuration
    subreddit = "AmItheAsshole"
    num_videos = 2

    print(f"\nGenerating {num_videos} DYNAMIC videos from r/{subreddit}")
    print("=" * 60)

    # Generate videos
    try:
        stories = generator.scrape_reddit_stories(subreddit, num_videos, allow_reprocess=False)

        if not stories:
            print("No suitable stories found")
            return

        total_videos = 0
        start_time = datetime.now()

        for story in stories:
            story_start = datetime.now()
            videos = generator.generate_videos_from_story(
                story, gameplay_folder, output_folder, logo_path=logo_path
            )
            story_end = datetime.now()
            story_duration = (story_end - story_start).total_seconds()

            total_videos += len(videos)
            if videos:
                print(f"Created {len(videos)} video(s) in {story_duration:.1f}s")

        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()

        print("=" * 60)
        print(f"Successfully generated {total_videos} DYNAMIC videos!")
        print(f"Total time: {total_duration:.1f} seconds")
        if total_videos > 0:
            print(f"Average: {total_duration/total_videos:.1f}s per video")
        print(f"Check the '{output_folder}' folder for your videos")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
