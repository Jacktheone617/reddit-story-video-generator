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
from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip, AudioFileClip
import edge_tts
import asyncio

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
        self.video_width = 720   # Reduced for faster processing
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
    
    def scrape_reddit_stories(self, subreddit_name: str, limit: int = 5, allow_reprocess: bool = False) -> List[Dict]:
        """Scrape stories from Reddit"""
        print(f"Scraping r/{subreddit_name}...")
        
        subreddit = self.reddit.subreddit(subreddit_name)
        stories = []
        
        for submission in subreddit.hot(limit=limit * 10):
            # Skip processed posts unless reprocessing is explicitly allowed you can set allow_reprocess to change this behavior
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
        
        print(f"✓ Found {len(stories)} suitable stories")
        return stories
    
    def clean_text_for_speech(self, text: str) -> str:
        """Clean text for TTS"""
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'&gt;', '', text)
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def generate_audio(self, text: str, output_path: str, voice_type: str = "tiktok") -> float:
        """Generate TTS audio with different voice options"""
        
        if voice_type == "tiktok":
            # Use Microsoft Edge TTS - sounds like TikTok voices
            return self.generate_edge_tts_audio(text, output_path)
        else:
            # Fallback to Google TTS
            return self.generate_gtts_audio(text, output_path)
    
    def generate_gtts_audio(self, text: str, output_path: str) -> float:
        """Generate Google TTS audio (original method)"""
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(output_path)
        
        audio = AudioSegment.from_file(output_path)
        duration = len(audio) / 1000.0
        print(f"✓ Generated Google TTS audio: {duration:.1f}s")
        return duration
    
    def generate_edge_tts_audio(self, text: str, output_path: str) -> float:
        """Generate Microsoft Edge TTS audio (TikTok-like voice)"""
        try:
            asyncio.run(self._generate_edge_tts_async(text, output_path))

            audio = AudioSegment.from_file(output_path)
            duration = len(audio) / 1000.0
            print(f"✓ Generated TikTok-style audio: {duration:.1f}s")
            return duration
            
        except Exception as e:
            print(f"⚠️  Edge TTS failed, falling back to Google TTS: {e}")
            return self.generate_gtts_audio(text, output_path)
    
    async def _generate_edge_tts_async(self, text: str, output_path: str):
        """Async function to generate Edge TTS"""
        # Other voices you can try:
        # - "en-US-JennyNeural" - Young female voice (very TikTok-like)
        # - "en-US-AriaNeural" - Natural female voice  
        # - "en-US-GuyNeural" - Male voice
        # - "en-US-JaneNeural" - Cheerful female voice
        
        voice = "en-US-JennyNeural"  # This sounds most like TikTok
        
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    
    def select_random_gameplay(self, gameplay_folder: str) -> str:
        """Select random gameplay video"""
        if not os.path.exists(gameplay_folder):
            raise FileNotFoundError(f"Gameplay folder not found: {gameplay_folder}")
            
        video_files = [f for f in os.listdir(gameplay_folder) 
                      if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        
        if not video_files:
            raise FileNotFoundError("No gameplay videos found")
        
        selected = os.path.join(gameplay_folder, random.choice(video_files))
        print(f"✓ Selected: {os.path.basename(selected)}")
        return selected
    
    def estimate_word_timings(self, text: str, duration: float) -> List[Dict]:
        """Estimate precise timing for each word based on Edge TTS characteristics"""
        words = text.split()
        total_words = len(words)
        
        if total_words == 0:
            return []
        
        # Edge TTS (Jenny Neural) typically speaks at ~2.0-2.5 words per second
        # But we need to account for natural speech patterns this isnt perfect
        base_rate = 2.2  # words per second for Edge TTS
        
        word_timings = []
        current_time = 0
        
        for i, word in enumerate(words):
            # Adjust timing based on word characteristics
            word_length_factor = max(0.4, len(word) / 6.0)  # Longer words take more time
            
            # Add pauses for punctuation
            punctuation_pause = 0
            if word.endswith(('.', '!', '?')):
                punctuation_pause = 0.3  # Longer pause for sentence endings
            elif word.endswith((',', ';', ':')):
                punctuation_pause = 0.15  # Medium pause for commas
            
            # Calculate word duration (minimum 0.3 seconds per word)
            base_duration = max(0.3, word_length_factor / base_rate)
            word_duration = base_duration + punctuation_pause
            
            # Add slight randomness for natural speech (±10%)
            import random
            variation = random.uniform(0.9, 1.1)
            word_duration *= variation
            
            word_timings.append({
                'word': word,
                'start': current_time,
                'end': current_time + word_duration,
                'index': i
            })
            
            current_time += word_duration
        
        # Scale all timings to match actual audio duration
        if current_time > 0:
            scale_factor = duration / current_time
            for timing in word_timings:
                timing['start'] *= scale_factor
                timing['end'] *= scale_factor
        
        #Print first few timings so we see usally just top of post like AITA etc
        print(f"Audio duration: {duration:.1f}s, Estimated total: {current_time:.1f}s")
        print(f"Scale factor: {scale_factor:.2f}")
        for i in range(min(5, len(word_timings))):
            t = word_timings[i]
            print(f"  '{t['word']}': {t['start']:.1f}-{t['end']:.1f}s")
        
        return word_timings
    
    def create_word_segments(self, text: str, duration: float) -> List[Dict]:
        """Create segments for individual word display"""
        word_timings = self.estimate_word_timings(text, duration)
        words = text.split()
        
        if not word_timings:
            return []
        
        segments = []
        
        # Create a segment for each individual word
        for word_idx, timing in enumerate(word_timings):
            if word_idx < len(words):
                segments.append({
                    'word': words[word_idx],
                    'start': timing['start'],
                    'end': timing['end'],
                    'word_index': word_idx
                })
        
        return segments
    
    def create_dynamic_text_clips(self, text: str, duration: float) -> List[TextClip]:
        """Create simple one-word-at-a-time text clips with better timing"""
        print("Creating one-word-at-a-time text display...")
        
        segments = self.create_word_segments(text, duration)
        text_clips = []
        
        for i, segment in enumerate(segments):
            # Make words appear slightly longer for better readability
            word_duration = segment['end'] - segment['start']
            extended_duration = max(word_duration, 0.4)  # Minimum 0.4 seconds per word
            
            # Create a single yellow word clip
            word_clip = TextClip(
                segment['word'],
                fontsize=54,  # Large, readable text
                color='yellow',
                font='Comic-Sans-MS-Bold',
                stroke_color='black',
                stroke_width=4
            ).set_position(('center', self.video_height - 300)).set_start(segment['start']).set_duration(extended_duration)
            
            text_clips.append(word_clip)
            
            # Debug: Print timing for first few words
            if i < 5:
                print(f"  Word '{segment['word']}': {segment['start']:.1f}-{segment['start'] + extended_duration:.1f}s")
        
        print(f"✓ Created {len(text_clips)} individual word clips")
        return text_clips
    
    def create_progress_bar(self, current_word_index: int, total_words: int, duration: float) -> TextClip:
        """Create a simple progress indicator"""
        progress = int((current_word_index / total_words) * 20) if total_words > 0 else 0
        progress_bar = "█" * progress + "░" * (20 - progress)
        progress_text = f"{progress_bar} {current_word_index}/{total_words}"
        
        return TextClip(
            progress_text,
            fontsize=24,
            color='cyan',
            font='Arial-Bold'
        ).set_position(('center', 50)).set_duration(duration)
    
    def create_dynamic_video(self, gameplay_path: str, audio_path: str, text: str, 
                           output_path: str, part_number: int = None) -> str:
        """Create video with dynamic text highlighting"""
        print(f"Creating DYNAMIC video: {os.path.basename(output_path)}")
        
        # Load gameplay video
        gameplay = VideoFileClip(gameplay_path)
        
        # Get audio duration
        audio = AudioSegment.from_file(audio_path)
        audio_duration = len(audio) / 1000.0
        
        # Resize gameplay to TikTok format
        gameplay = gameplay.resize((self.video_width, self.video_height))
        
        # Loop gameplay if needed
        if gameplay.duration < audio_duration:
            loops = int(audio_duration / gameplay.duration) + 1
            gameplay = gameplay.loop(n=loops)
        
        # Trim to audio length
        gameplay = gameplay.subclip(0, audio_duration)
        
        # Create title overlay
        title = text.split('.')[0][:40] + "..." if len(text.split('.')[0]) > 40 else text.split('.')[0]
        if part_number:
            title = f"Part {part_number}: {title}"
        
        title_clip = TextClip(
            title,
            fontsize=36,
            color='yellow',
            font='Comic-Sans-MS-Bold',
            stroke_color='black',
            stroke_width=3,
            size=(self.video_width - 60, None),
            method='caption'
        ).set_position(('center', 100)).set_duration(10)  # Title disappears after 10 seconds
        
        # Create dynamic text clips with real-time highlighting
        dynamic_text_clips = self.create_dynamic_text_clips(text, audio_duration)
        
        # Load and add audio
        audio_clip = AudioFileClip(audio_path)
        gameplay = gameplay.set_audio(audio_clip)
        
        # Composite everything
        all_clips = [gameplay, title_clip] + dynamic_text_clips
        final_video = CompositeVideoClip(all_clips)
        
        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            preset='fast',
            threads=multiprocessing.cpu_count(),
            verbose=False,
            logger=None,
            temp_audiofile='temp-audio.m4a',
            remove_temp=True
        )
        
        # Clean up resources
        gameplay.close()
        title_clip.close()
        audio_clip.close()
        for clip in dynamic_text_clips:
            clip.close()
        final_video.close()
        
        print(f"✓ DYNAMIC video created: {output_path}")
        return output_path
    
    def generate_videos_from_story(self, story: Dict, gameplay_folder: str, 
                                 output_folder: str) -> List[str]:
        """Generate dynamic video(s) from a Reddit story"""
        print(f"\nProcessing: {story['title'][:50]}...")
        
        # Prepare text
        full_text = f"{story['title']}. {story['content']}"
        clean_text = self.clean_text_for_speech(full_text)
        
        # Limit text length for optimal processing
        words = clean_text.split()
        if len(words) > 250:  # ~100 seconds max
            clean_text = ' '.join(words[:250]) + "..."
        
        print(f"Text length: {len(clean_text)} characters, {len(clean_text.split())} words")
        
        # File names
        video_filename = f"{story['id']}_dynamic.mp4"
        audio_filename = f"temp_audio_{story['id']}.mp3"
        
        video_path = os.path.join(output_folder, video_filename)
        audio_path = os.path.join(output_folder, audio_filename)
        
        try:
            # Generate TikTok-style audio
            self.generate_audio(clean_text, audio_path, voice_type="tiktok")
            
            # Select gameplay
            gameplay_path = self.select_random_gameplay(gameplay_folder)
            
            # Create dynamic video
            final_video = self.create_dynamic_video(
                gameplay_path, audio_path, clean_text, video_path
            )
            
            # Mark as processed
            self.mark_post_processed(story['id'], story['title'], 1)
            
            return [final_video]
            
        except Exception as e:
            print(f"✗ Error creating video: {e}")
            return []
        finally:
            # Clean up temp audio
            if os.path.exists(audio_path):
                os.remove(audio_path)

def main():
    """Main function to run the dynamic video generator"""
    
    try:
        from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
    except ImportError:
        print("✗ Please create config.py with your Reddit API credentials")
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
    
    # Optional: Clear database to allow reprocessing (comment out to prevent reuse)
    # generator.clear_database()  # Uncomment this line to reprocess old posts
    
    # Set up folders
    gameplay_folder = "gameplay_videos"
    output_folder = "output_videos"
    
    os.makedirs(output_folder, exist_ok=True)
    
    if not os.path.exists(gameplay_folder):
        print(f"✗ Please create '{gameplay_folder}' folder and add some .mp4 gameplay videos")
        return
    
    # Configuration
    subreddit = "AmItheAsshole"
    num_videos = 2  # Start with 2 for testing
    
    print(f"Generating {num_videos} DYNAMIC videos from r/{subreddit}")
    print("DYNAMIC TEXT FEATURES:")
    print("   • One word at a time display")
    print("   • Large YELLOW text in center")
    print("   • Title disappears after 10 seconds")
    print("   • TikTok-style voice (Jenny Neural)")
    print("   • Clean, minimal design")
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
                story, gameplay_folder, output_folder
            )
            story_end = datetime.now()
            story_duration = (story_end - story_start).total_seconds()
            
            total_videos += len(videos)
            if videos:
                print(f"✓ Created {len(videos)} video(s) in {story_duration:.1f}s")
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        print("=" * 60)
        print(f"Successfully generated {total_videos} DYNAMIC videos!")
        print(f"Total time: {total_duration:.1f} seconds")
        if total_videos > 0:
            print(f"⚡ Average: {total_duration/total_videos:.1f}s per video")
        print(f"Check the '{output_folder}' folder for your TikTok-ready videos")
        print("Features: Word-by-word highlighting, real-time text updates!")
        
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()