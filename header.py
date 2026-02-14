"""
Reddit-Style Header Generation Module - PROFESSIONAL GRADE
YouTube Shorts 2025-2026 Optimized with Advanced Safe Zones

Modern solid styling with:
  - Soft drop shadow for depth
  - Dynamic font sizing (no hard truncation)
  - Accent bar for visual distinction
  - Off-white background with subtle border
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


def rounded_rectangle_clip(size: tuple, radius: int, color: tuple, duration: float,
                           border_color: tuple = None, border_width: int = 0,
                           accent_color: tuple = None, accent_height: int = 0):
    """
    Create a rounded rectangle clip using PIL with optional border and accent bar.

    Args:
        size: (width, height)
        radius: Corner radius
        color: RGB tuple for fill
        duration: Clip duration in seconds
        border_color: Optional RGB tuple for a subtle border
        border_width: Border thickness in pixels
        accent_color: Optional RGB tuple for top accent bar
        accent_height: Height of accent bar in pixels
    """
    from PIL import Image, ImageDraw
    import numpy as np

    width, height = size

    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw border as a filled rounded rect first
    if border_color and border_width > 0:
        draw.rounded_rectangle(
            [(0, 0), (width - 1, height - 1)],
            radius=radius,
            fill=border_color + (255,)
        )

    # Draw main fill on top (inset by border width) — fully opaque
    inset = border_width
    draw.rounded_rectangle(
        [(inset, inset), (width - 1 - inset, height - 1 - inset)],
        radius=max(0, radius - inset),
        fill=color + (255,)
    )

    # Draw accent bar at the top (drawn directly on the fill)
    if accent_color and accent_height > 0:
        draw.rectangle(
            [(inset, inset), (width - 1 - inset, inset + accent_height)],
            fill=accent_color + (255,)
        )

    img_array = np.array(img)
    clip = ImageClip(img_array).with_duration(duration)
    return clip


def create_shadow_clip(size: tuple, radius: int, duration: float,
                       shadow_color: tuple = (0, 0, 0, 50),
                       blur_radius: int = 12, offset: tuple = (4, 6)):
    """
    Create a soft drop shadow clip.

    Args:
        size: (width, height) of the element casting the shadow
        radius: Corner radius matching the element
        duration: Clip duration
        shadow_color: RGBA tuple for shadow
        blur_radius: Gaussian blur radius
        offset: (x_offset, y_offset) for directional shadow
    """
    from PIL import Image, ImageDraw, ImageFilter
    import numpy as np

    # Create a larger canvas to accommodate the blur spread
    pad = blur_radius * 3
    canvas_w = size[0] + pad * 2
    canvas_h = size[1] + pad * 2

    img = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw the shadow shape centered in the padded canvas
    draw.rounded_rectangle(
        [(pad, pad), (pad + size[0], pad + size[1])],
        radius=radius,
        fill=shadow_color
    )

    # Apply gaussian blur for soft edges
    img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    img_array = np.array(img)
    clip = ImageClip(img_array).with_duration(duration)
    return clip, pad, offset


def wrap_text(text: str, font_path: str, font_size: int, max_width: int) -> str:
    """Wrap text at word boundaries so no word gets split across lines."""
    from PIL import ImageFont
    font = ImageFont.truetype(font_path, font_size)
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def create_reddit_header(title: str, author: str = "u/BrokenStories",
                         subreddit: str = "r/AskReddit",
                         duration: float = 4.5,
                         logo_path: str = "logo/Redit logo.png",
                         video_width: int = 720,
                         video_height: int = 1280):
    """
    Create Reddit-style post header with modern solid styling.

    Features:
      - Asymmetrical safe zones for YouTube Shorts 2025-2026
      - Soft drop shadow for depth
      - Dynamic font sizing (reduces font instead of truncating)
      - Off-white background with subtle border and accent bar
      - Strict relative positioning (drift-proof)
    """

    clips = []

    # === LAYOUT CONSTANTS ===
    LEFT_MARGIN = 30
    RIGHT_UI_BUFFER = 130 if video_width <= 720 else 190
    LOGO_SIZE = 160
    BOX_RADIUS = 24

    box_width = video_width - LEFT_MARGIN - RIGHT_UI_BUFFER
    box_left_edge = LEFT_MARGIN

    # Title spans the full box width with padding on each side
    title_padding = 40  # Gap between title and box edges
    title_width = box_width - (title_padding * 2)

    # === DYNAMIC FONT SIZING ===
    # Uses wrap_text() to guarantee whole words stay together
    MAX_TITLE_HEIGHT = 100
    display_title = title
    title_font_size = 38
    font_path = "fonts/Montserrat-Black.ttf"
    # Account for margin (20px each side) when wrapping
    wrap_width = title_width - 40

    for fs in range(38, 22, -2):
        wrapped = wrap_text(display_title, font_path, fs, wrap_width)
        title_clip = TextClip(
            text=wrapped,
            font=font_path,
            font_size=fs,
            color="#1a1a1b",
            method="label",
            margin=(20, 20)
        )
        if title_clip.size[1] and title_clip.size[1] <= MAX_TITLE_HEIGHT:
            title_font_size = fs
            break

    # Last resort: truncate if still too tall at smallest font
    if title_clip.size[1] and title_clip.size[1] > MAX_TITLE_HEIGHT:
        display_title = title[:90] + "..."
        wrapped = wrap_text(display_title, font_path, 24, wrap_width)
        title_clip = TextClip(
            text=wrapped,
            font=font_path,
            font_size=24,
            color="#1a1a1b",
            method="label",
            margin=(20, 20)
        )
        title_font_size = 24

    title_height = title_clip.size[1] if title_clip.size[1] else 60

    # === BOX DIMENSIONS ===
    emoji_height = 50
    right_side_height = 40 + emoji_height + 10 + title_height
    content_height = max(LOGO_SIZE, right_side_height)
    engagement_row_height = 40
    box_height = content_height + 20 + engagement_row_height + 20

    # === VERTICALLY CENTER THE HEADER ===
    box_top = (video_height - box_height) // 2

    # All Y positions are relative to box_top
    logo_x = box_left_edge
    logo_y = box_top

    # === DROP SHADOW ===
    shadow_clip, shadow_pad, shadow_offset = create_shadow_clip(
        size=(box_width, box_height),
        radius=BOX_RADIUS,
        duration=duration,
        shadow_color=(0, 0, 0, 50),
        blur_radius=12,
        offset=(4, 6)
    )
    shadow_x = box_left_edge - shadow_pad + shadow_offset[0]
    shadow_y = box_top - shadow_pad + shadow_offset[1]
    shadow_clip = shadow_clip.with_position((shadow_x, shadow_y))
    clips.append(shadow_clip)

    # === BACKGROUND BOX ===
    header_bg = rounded_rectangle_clip(
        size=(box_width, box_height),
        radius=BOX_RADIUS,
        color=(254, 255, 255),  # #FEFFFF
        duration=duration,
        border_color=(255, 69, 0),  # Reddit orange border
        border_width=3,
        accent_color=(255, 69, 0),
        accent_height=4
    ).with_position((box_left_edge, box_top))
    clips.append(header_bg)

    # === REDDIT LOGO ===
    if os.path.exists(logo_path):
        logo = ImageClip(logo_path)
        logo = logo.resized((LOGO_SIZE, LOGO_SIZE))
        logo = logo.with_position((logo_x, logo_y)).with_duration(duration)
        clips.append(logo)
        print(f"Logo: {LOGO_SIZE}x{LOGO_SIZE} at ({logo_x}, {logo_y})")
    else:
        print(f"Logo not found: {logo_path}")

    # === EMOJI REACTIONS — just right of logo ===
    emoji_x = logo_x + LOGO_SIZE - 22
    emoji_y = logo_y + LOGO_SIZE - emoji_height - 32

    emoji_path = "logo/emijeys.png"
    if os.path.exists(emoji_path):
        emoji_strip = ImageClip(emoji_path)
        emoji_strip = emoji_strip.resized(height=emoji_height)
        emoji_strip = emoji_strip.with_position((emoji_x, emoji_y)).with_duration(duration)
        clips.append(emoji_strip)

    # === CHANNEL NAME + VERIFIED — just above the emojis ===
    channel_name_y = emoji_y - 42
    channel_name = TextClip(
        text="Reddit Tales",
        font="fonts/Montserrat-Black.ttf",
        font_size=24,
        color="#1a1a1b",
        size=(250, None),
        margin=(5, 5)
    )
    channel_name_x = emoji_x - 45
    channel_name = channel_name.with_position((channel_name_x, channel_name_y)).with_duration(duration)
    clips.append(channel_name)

    channel_name_width_actual = channel_name.size[0]

    verified_path = "logo/verified.png"
    if os.path.exists(verified_path):
        verified = ImageClip(verified_path)
        verified = verified.resized((22, 22))
        verified_x = channel_name_x + channel_name_width_actual - 15
        verified_y = channel_name_y + 4
        verified = verified.with_position((verified_x, verified_y)).with_duration(duration)
        clips.append(verified)

    # === POST TITLE — centered in box, BELOW the emojis ===
    title_y = emoji_y + emoji_height + 2
    title_x = box_left_edge + title_padding - 10
    title_clip = title_clip.with_position((title_x, title_y)).with_duration(duration)

    # === ENGAGEMENT METRICS — below the logo/content area ===
    engagement_y = box_top + content_height + 20

    hearts_path = "logo/harts&coments.png"
    hearts_x = box_left_edge + 40
    hearts_height = 28

    if os.path.exists(hearts_path):
        hearts = ImageClip(hearts_path)
        hearts = hearts.resized(height=hearts_height)
        hearts = hearts.with_position((hearts_x, engagement_y)).with_duration(duration)
        clips.append(hearts)

    share_path = "logo/share.png"
    share_offset = 100
    share_height = 28

    if os.path.exists(share_path):
        share = ImageClip(share_path)
        share = share.resized(height=share_height)
        share_x = box_left_edge + box_width - share_offset
        share = share.with_position((share_x, engagement_y)).with_duration(duration)
        clips.append(share)

    # === TITLE ON TOP — appended last so it renders above everything else ===
    clips.append(title_clip)

    # === SUMMARY ===
    print(f"Header: {box_width}x{box_height}px | Font: {title_font_size}px | "
          f"Shadow: on | Accent: on | Clips: {len(clips)}")

    return clips
