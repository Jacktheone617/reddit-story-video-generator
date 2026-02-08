"""
Reddit-Style Header Generation Module
Creates the post header that looks like a real Reddit post
"""

import os
from typing import List

# MoviePy imports
try:
    from moviepy import TextClip, ImageClip
    MOVIEPY_VERSION = 2
except ImportError:
    from moviepy.editor import TextClip, ImageClip
    MOVIEPY_VERSION = 1


def rounded_rectangle_clip(size: tuple, radius: int, color: tuple, duration: float):
    """Create a rounded rectangle clip using PIL"""
    from PIL import Image, ImageDraw
    import numpy as np
    
    width, height = size
    
    # Create image with transparency
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle
    draw.rounded_rectangle(
        [(0, 0), (width, height)],
        radius=radius,
        fill=color + (255,)  # Add alpha channel
    )
    
    # Convert to numpy array for MoviePy
    img_array = np.array(img)
    
    # Create ImageClip from the array
    clip = ImageClip(img_array).with_duration(duration)
    
    return clip


def create_reddit_header(title: str, author: str = "u/BrokenStories",
                         subreddit: str = "r/AskReddit",
                         duration: float = 4.5,
                         logo_path: str = "logo/Redit logo.png",
                         video_width: int = 720,
                         video_height: int = 1280):
    """
    Create Reddit-style post header that looks like a real Reddit post - MATCHES REFERENCE STYLE
    
    Args:
        title: Post title text
        author: Reddit username (e.g., "u/BrokenStories")
        subreddit: Subreddit name (e.g., "r/AskReddit")
        duration: How long to display the header (seconds)
        logo_path: Path to Reddit logo image
        video_width: Width of the video
        video_height: Height of the video
    
    Returns:
        List of clip objects that make up the header
    """
    
    clips = []
    
    # -------------------------------------------------- LOGO SIZE (defined early for box calculation)
    logo_size = 160  # Change this to adjust logo size
    # --------------------------------------------------
    
    # Calculate title height to adjust box size dynamically
    temp_title_clip = TextClip(
        text=title[:100] + "..." if len(title) > 100 else title,
        font="fonts/Montserrat-Black.ttf",
        font_size=38,
        color="black",
        size=(video_width - 110, None),  # Proper constraint for measurement
        method="caption"
    )
    title_height = temp_title_clip.size[1] if temp_title_clip.size[1] else 80
    
    # ====== BACKGROUND BOX (NARROWER, ADJUSTED TO CONTENT) ======
    # Calculate box height based on content
    # Logo section + title height + engagement (40px) + extra padding
    box_height = logo_size + title_height + 40 + 40  # Added extra padding for multi-line titles
    box_width = video_width - 60  # Narrower to match reference
    
    header_bg = rounded_rectangle_clip(
        size=(box_width, box_height),
        radius=50,                 
        color=(255, 255, 255),  # White background
        duration=duration
    ).with_position(('center', 20))

    clips.append(header_bg)
    
    # ====== REDDIT LOGO ======
    if os.path.exists(logo_path):
        logo = ImageClip(logo_path)
        logo = logo.resized((logo_size, logo_size))
        logo = logo.with_position((40, 30)).with_duration(duration)
        clips.append(logo)
        logo_x_end = 40 + logo_size + 15  # Logo X + size + 15px padding
        print(f"✓ Loaded Reddit logo ({logo_size}x{logo_size}, positioned at 40,30)")
    else:
        print(f"⚠️  Logo not found at {logo_path}, skipping logo")
        logo_x_end = 50
    
    # ====== "Reddit Tales" TEXT (PARALLEL TO LOGO - CENTERED VERTICALLY) ======
    # -------------------------------------------------- CHANNEL NAME WIDTH
    channel_name_width_setting = 250  # Width for channel name (increase if name gets cut off)
    # --------------------------------------------------
    
    channel_name_text = "Reddit Tales"
    channel_name = TextClip(
        text=channel_name_text,
        font="fonts/Montserrat-Black.ttf",
        font_size=38,
        color="black",
        size=(channel_name_width_setting, None)  # Width ensures full name displays
    ).with_position((logo_x_end, 55)).with_duration(duration)
    clips.append(channel_name)
    
    # Calculate actual width of the channel name text
    channel_name_width = channel_name.size[0]  # Get actual rendered width
    
    # ====== VERIFIED BADGE (RIGHT OF THE NAME - MORE SPACE) ======
    verified_path = "logo/verified.png"
    if os.path.exists(verified_path):
        verified = ImageClip(verified_path)
        verified = verified.resized((28, 28))
        verified = verified.with_position((logo_x_end + channel_name_width + 10, 58)).with_duration(duration)
        clips.append(verified)
        print(f"✓ Loaded verified badge image at x={logo_x_end + channel_name_width + 10}")
    else:
        print(f"⚠️  Verified badge not found at {verified_path}")
    
    # ====== EMOJI REACTIONS ROW (BELOW NAME AND BADGE) ======
    # -------------------------------------------------- EMOJI SIZE
    emoji_height = 50  # Change this to adjust emoji strip height
    # --------------------------------------------------
    
    emoji_images_path = "logo/emijeys.png"
    if os.path.exists(emoji_images_path):
        emoji_strip = ImageClip(emoji_images_path)
        emoji_strip = emoji_strip.resized(height=emoji_height)
        emoji_strip = emoji_strip.with_position((logo_x_end, 95)).with_duration(duration)
        clips.append(emoji_strip)
        print(f"✓ Loaded emoji reactions image (height={emoji_height})")
    else:
        print(f"⚠️  Emoji reactions image not found at {emoji_images_path}")
    
    # ====== POST TITLE (CENTERED AND FITS WITHIN BOX) ======
    # Truncate title if too long
    display_title = title[:100] + "..." if len(title) > 100 else title
    
    # -------------------------------------------------- TITLE POSITION & PADDING
    title_gap_from_emojis = 10  # Gap between emoji row and title (increase for more space)
    title_y = 30 + logo_size + title_gap_from_emojis  # Logo Y + Logo size + gap
    # --------------------------------------------------
    engagement_y = title_y + title_height + 10
    # Calculate proper text width to fit in box (box_width - padding on both sides)
    text_width = box_width - 80  # Leave more padding (40px each side)
    
    # Calculate center position for the box
    box_left_edge = (video_width - box_width) // 2
    
    # -------------------------------------------------- TEXT HEIGHT (prevents bottom cutoff)
    text_height = title_height + 20  # Add extra height so letters don't get cut off
    # --------------------------------------------------
    
    title_clip = TextClip(
        text=display_title,
        font="fonts/Montserrat-Black.ttf",
        font_size=38,  # Bold title
        color="black",
        size=(text_width, text_height),  # BOTH width and height set (fixes cutoff!)
        method="caption"
    ).with_position((box_left_edge + 40, title_y)).with_duration(duration)  # Centered with padding
    clips.append(title_clip)
    
    # ====== ENGAGEMENT METRICS ======
    # Position at bottom of box with padding
    engagement_y = title_y + title_height + 10  # Below title with 10px gap (increased from 5px)
    
    hearts_path = "logo/harts&coments.png"
    share_path = "logo/share.png"
    
    # -------------------------------------------------- HEARTS & COMMENTS POSITION
    hearts_x = box_left_edge + 40  # Align with title (centered in box)
    hearts_height = 28  # Height of hearts & comments image
    # --------------------------------------------------
    
    # Load hearts & comments image
    if os.path.exists(hearts_path):
        hearts = ImageClip(hearts_path)
        hearts = hearts.resized(height=hearts_height)
        hearts = hearts.with_position((hearts_x, engagement_y)).with_duration(duration)
        clips.append(hearts)
        print(f"✓ Loaded hearts & comments image")
    else:
        print(f"⚠️  Hearts & comments image not found at {hearts_path}")
    
    # -------------------------------------------------- SHARE BUTTON POSITION
    share_offset = 100  # Distance from right edge (smaller = more right)
    share_height = 28   # Height of share button image
    # --------------------------------------------------
    
    # Load share button
    if os.path.exists(share_path):
        share = ImageClip(share_path)
        share = share.resized(height=share_height)
        # Calculate right position
        share_x = (video_width // 2) + (box_width // 2) - share_offset
        share = share.with_position((share_x, engagement_y)).with_duration(duration)
        clips.append(share)
        print(f"✓ Loaded share button image at x={share_x}")
    else:
        print(f"⚠️  Share button not found at {share_path}")
    
    return clips