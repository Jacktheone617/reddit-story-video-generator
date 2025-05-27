# simple_test.py
# Test all imports to see which ones are working

print("Testing imports...")
print("-" * 40)

try:
    import praw
    print("✓ praw - OK")
except Exception as e:
    print(f"✗ praw - ERROR: {e}")

try:
    import requests
    print("✓ requests - OK")
except Exception as e:
    print(f"✗ requests - ERROR: {e}")

try:
    from gtts import gTTS
    print("✓ gtts - OK")
except Exception as e:
    print(f"✗ gtts - ERROR: {e}")

try:
    from pydub import AudioSegment
    print("✓ pydub - OK")
except Exception as e:
    print(f"✗ pydub - ERROR: {e}")

try:
    import sqlite3
    print("✓ sqlite3 - OK")
except Exception as e:
    print(f"✗ sqlite3 - ERROR: {e}")

try:
    import numpy
    print("✓ numpy - OK")
except Exception as e:
    print(f"✗ numpy - ERROR: {e}")

try:
    import imageio
    print("✓ imageio - OK")
except Exception as e:
    print(f"✗ imageio - ERROR: {e}")

try:
    from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip
    print("✓ moviepy - OK")
except Exception as e:
    print(f"✗ moviepy - ERROR: {e}")

print("-" * 40)
print("Import test completed!")

# Test basic functionality
print("\nTesting basic functionality...")
try:
    # Test gTTS
    tts = gTTS(text="Hello world", lang='en')
    print("✓ gTTS can create TTS object")
except Exception as e:
    print(f"✗ gTTS test failed: {e}")

try:
    # Test SQLite
    conn = sqlite3.connect(':memory:')
    conn.close()
    print("✓ SQLite database connection works")
except Exception as e:
    print(f"✗ SQLite test failed: {e}")

print("\nAll tests completed!")