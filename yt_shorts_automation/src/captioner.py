"""
Caption generation module for yt_shorts_automation.

Generates styled ASS (Advanced SubStation Alpha) subtitle files from
transcript segments, then the dashboard burns them into the video
with ffmpeg's subtitles filter.

The ASS styling approach is adapted from:
  https://github.com/mutonby/openshorts
  File: subtitles.py
  (Their license: Custom/Other — used here for algorithmic inspiration only;
   the ASS format spec is an open standard.)

The dashboard calls:
  build_ass(segments, start, end, ass_path, ccfg) → writes .ass file
"""

import os
from typing import Dict, List


# ---------------------------------------------------------------------------
# ASS format helpers
# ---------------------------------------------------------------------------

def _ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp format: H:MM:SS.cc (centiseconds)."""
    total_cs = max(0, int(round(seconds * 100)))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_or_ass: str) -> str:
    """Normalize a color value to ASS format (&HAABBGGRR).

    Accepts:
      - ASS format: &H00FFFFFF  (already correct)
      - Hex format: #FFFFFF or FFFFFF
    """
    val = hex_or_ass.strip()
    if val.startswith("&H"):
        return val  # Already ASS format
    # Convert hex (#RRGGBB) to ASS (&H00BBGGRR)
    val = val.lstrip("#")
    if len(val) == 6:
        r, g, b = val[0:2], val[2:4], val[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"  # default white


def _build_ass_header(
    width: int = 1080,
    height: int = 1920,
    font: str = "Arial",
    font_size: int = 48,
    primary_color: str = "&H00FFFFFF",
    secondary_color: str = "&H000000FF",
    outline_color: str = "&H00000000",
    outline_width: int = 3,
    shadow: int = 1,
    position: str = "bottom",
) -> str:
    """Generate the ASS file header with script info and style definition.

    Styled for mobile-first vertical video (YouTube Shorts / TikTok):
      - Large bold font
      - White text with black outline for readability
      - Positioned at bottom-center (or center based on config)
    """
    primary = _ass_color(primary_color)
    secondary = _ass_color(secondary_color)
    outline = _ass_color(outline_color)

    # ASS alignment values:
    # 1=bottom-left, 2=bottom-center, 3=bottom-right
    # 4=mid-left, 5=mid-center, 6=mid-right
    # 7=top-left, 8=top-center, 9=top-right
    alignment_map = {
        "bottom": 2,
        "center": 5,
        "top": 8,
    }
    alignment = alignment_map.get(position, 2)

    # MarginV pushes text up from the edge
    margin_v = 80 if position == "bottom" else (40 if position == "top" else 20)

    header = f"""[Script Info]
Title: YT Shorts Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},{secondary},{outline},&H80000000,1,0,0,0,100,100,0,0,1,{outline_width},{shadow},{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header


# ---------------------------------------------------------------------------
# Main caption builder
# ---------------------------------------------------------------------------

def build_ass(
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
    ass_path: str,
    caption_config: Dict,
    hook_line: str = "",
) -> str:
    """Generate an ASS subtitle file for the clipped time range.

    Args:
        segments: Full transcript [{start, end, text, words?}, ...] in original video time.
        clip_start: Start time of the clip in the original video.
        clip_end: End time of the clip in the original video.
        ass_path: Where to write the .ass file.
        caption_config: Dict from config.yaml['captions'] with font, size, colors, etc.
        hook_line: Optional text for an opening hook overlay.
    """
    clip_segments = [
        s for s in segments
        if s["start"] < clip_end and s["end"] > clip_start
    ]

    is_karaoke = caption_config.get("style") == "word_karaoke"

    if is_karaoke:
        font_size = caption_config.get("font_size", 110)
        outline_width = caption_config.get("outline_width", 8)
        shadow = caption_config.get("shadow", 8)
        primary_color = caption_config.get("highlight_color", "&H0000FFFF")
        secondary_color = caption_config.get("primary_color", "&H00FFFFFF")
    else:
        font_size = caption_config.get("font_size", 48)
        outline_width = caption_config.get("outline_width", 3)
        shadow = caption_config.get("shadow", 1)
        primary_color = caption_config.get("primary_color", "&H00FFFFFF")
        secondary_color = "&H000000FF"

    header = _build_ass_header(
        font=caption_config.get("font", "Arial"),
        font_size=font_size,
        primary_color=primary_color,
        secondary_color=secondary_color,
        outline_color=caption_config.get("outline_color", "&H00000000"),
        outline_width=outline_width,
        shadow=shadow,
        position=caption_config.get("position", "bottom"),
    )

    lines = []

    # Optional hook overlay
    if caption_config.get("hook_overlay", {}).get("enabled") and hook_line:
        hook_end = min(2.0, clip_end - clip_start)
        hook_text = _wrap_text(hook_line, max_chars=35).replace("\n", "\\N")
        # Layer 1, {\b1} bold, {\an8} top-center alignment, explicitly set color to secondary_color (usually white) so it's not yellow
        hook_ass = f"{{\\c{_ass_color(secondary_color)}\\b1\\an8}}{hook_text}"
        lines.append(f"Dialogue: 1,{_ass_timestamp(0)},{_ass_timestamp(hook_end)},Default,,0,0,0,,{hook_ass}")

    for seg in clip_segments:
        seg_start = max(0, seg["start"] - clip_start)
        seg_end = min(clip_end - clip_start, seg["end"] - clip_start)

        if seg_end <= seg_start:
            continue

        if is_karaoke and "words" in seg and seg["words"]:
            shifted_words = []
            for w in seg["words"]:
                ws = max(0, w["start"] - clip_start)
                we = min(clip_end - clip_start, w["end"] - clip_start)
                if we > ws:
                    shifted_words.append({"start": ws, "end": we, "word": w["word"]})
            
            if shifted_words:
                chunks = _group_words_karaoke(shifted_words, max_chars=35, max_words=4)
                
                pos_tag = ""
                if is_karaoke and "vertical_position" in caption_config:
                    vpos = caption_config["vertical_position"]
                    y = int(1920 * vpos)
                    pos_tag = f"{{\\an5\\pos(540,{y})}}"
                    
                for chunk in chunks:
                    chunk_start = chunk[0]["start"]
                    chunk_end = chunk[-1]["end"]
                    
                    text_parts = []
                    for i, w in enumerate(chunk):
                        dur_cs = max(1, int((w["end"] - w["start"]) * 100))
                        text_parts.append(f"{{\\k{dur_cs}}}{w['word']}")
                    
                    ass_text = pos_tag + " ".join(text_parts)
                    start_ts = _ass_timestamp(chunk_start)
                    end_ts = _ass_timestamp(chunk_end)
                    lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{ass_text}")
                continue

        # Fallback to static line-by-line rendering
        text = seg["text"].strip()
        if not text:
            continue

        text = _wrap_text(text, max_chars=35)
        text = text.replace("\n", "\\N")

        start_ts = _ass_timestamp(seg_start)
        end_ts = _ass_timestamp(seg_end)
        lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    os.makedirs(os.path.dirname(ass_path) or ".", exist_ok=True)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(lines))
        f.write("\n")

    print(f"[captioner] wrote {len(lines)} subtitle lines to {ass_path}", flush=True)
    return ass_path


def _wrap_text(text: str, max_chars: int = 35) -> str:
    """Word-wrap text to fit vertical video width."""
    words = text.split()
    if not words:
        return text

    lines = []
    current_line = words[0]

    for word in words[1:]:
        if len(current_line) + 1 + len(word) <= max_chars:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return "\n".join(lines)


def _group_words_karaoke(words: List[Dict], max_chars: int = 35, max_words: int = 4) -> List[List[Dict]]:
    """Group words into small chunks for karaoke rendering."""
    chunks = []
    current_chunk = []
    current_len = 0
    for w in words:
        word_len = len(w["word"])
        if current_chunk and (current_len + 1 + word_len > max_chars or len(current_chunk) >= max_words):
            chunks.append(current_chunk)
            current_chunk = []
            current_len = 0
        current_chunk.append(w)
        current_len += word_len + (1 if current_chunk else 0)
    if current_chunk:
        chunks.append(current_chunk)
    return chunks