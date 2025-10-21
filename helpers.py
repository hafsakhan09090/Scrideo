import os
import subprocess
import logging
import shlex

logger = logging.getLogger(__name__)

# Color mapping for captions (BGR format for ASS with alpha channel)
COLOR_MAP = {
    'white': '00FFFFFF',
    'yellow': '0000FFFF',
    'cyan': '00FFFF00',
    'lime': '0000FF00',
    'orange': '0000A5FF',
    'red': '000000FF',
    'pink': '00CBC0FF',
    'purple': '00F020A0',
    'light-blue': '00E6D8AD',
    'light-green': '0090EE90'
}

# Background color mapping for captions (AABBGGRR format for ASS)
BG_COLOR_MAP = {
    'none': '00FFFFFF',          # Fully transparent - will use BorderStyle=1
    'black': '00000000',         # Black opaque
    'dark-gray': '00333333',     # Dark gray opaque
    'semi-transparent': '80000000',  # Black with 50% transparency
    'dark-blue': '004D1A00',     # Dark blue opaque
    'dark-red': '0000004D',      # Dark red opaque
    'dark-green': '00004D00',    # Dark green opaque
    'dark-purple': '004D0033',   # Dark purple opaque
    'navy': '00800000',          # Navy blue opaque
    'charcoal': '004F4536'       # Charcoal opaque
}

# Font mapping for common fonts
FONT_MAP = {
    'arial': 'Arial',
    'helvetica': 'Helvetica',
    'times-new-roman': 'Times New Roman',
    'courier-new': 'Courier New',
    'verdana': 'Verdana',
    'georgia': 'Georgia',
    'impact': 'Impact',
    'comic-sans': 'Comic Sans MS',
    'trebuchet': 'Trebuchet MS',
    'arial-black': 'Arial Black',
    'palatino': 'Palatino Linotype'
}

# -------------------------- SRT to ASS Conversion --------------------------

def get_ass_alignment(position, text_alignment):
    """Get the correct ASS alignment number based on position and text alignment
    
    ASS Alignment grid:
    7 8 9  (top row: left, center, right)
    4 5 6  (middle row: left, center, right)
    1 2 3  (bottom row: left, center, right)
    """
    # For corner positions, the position determines alignment regardless of text_alignment setting
    if position in ['bottom-left', 'top-left']:
        return 1 if position == 'bottom-left' else 7  # Left-aligned
    elif position in ['bottom-right', 'top-right']:
        return 3 if position == 'bottom-right' else 9  # Right-aligned
    else:
        # For center positions (top, bottom, middle), use text_alignment
        if position == 'top':
            base = 7  # Top row
        elif position == 'middle':
            base = 4  # Middle row
        else:  # bottom
            base = 1  # Bottom row
        
        # Add alignment offset
        if text_alignment == 'left':
            return base
        elif text_alignment == 'right':
            return base + 2
        else:  # center
            return base + 1

def calculate_margins(position, ass_alignment):
    """Calculate margins based on caption position and alignment
    
    MarginL/R control horizontal positioning
    MarginV controls vertical positioning
    """
    # Vertical margin based on position
    if 'top' in position:
        margin_v = '30'    # Top positions need more space from edge
    elif 'middle' in position:
        margin_v = '0'     # Middle is centered
    else:  # bottom
        margin_v = '30'    # Bottom positions need space from edge
    
    # Horizontal margins based on alignment (1-3 bottom, 4-6 middle, 7-9 top)
    alignment_mod = ass_alignment % 3
    
    if alignment_mod == 1:  # Left-aligned (1, 4, 7)
        margin_l = '30'
        margin_r = '10'
    elif alignment_mod == 0:  # Right-aligned (3, 6, 9)
        margin_l = '10'
        margin_r = '30'
    else:  # Center-aligned (2, 5, 8)
        margin_l = '10'
        margin_r = '10'
    
    return margin_l, margin_r, margin_v

def convert_srt_to_ass(srt_path, ass_path, caption_settings=None):
    """Convert SRT to ASS format with custom styling and positioning"""
    try:
        if caption_settings is None:
            caption_settings = {
                'size': '20', 
                'color': 'white', 
                'bgColor': 'none', 
                'font': 'arial',
                'position': 'bottom',
                'alignment': 'center'
            }
        
        font_size = caption_settings.get('size', '20')
        color_name = caption_settings.get('color', 'white')
        bg_color_name = caption_settings.get('bgColor', 'none')
        font_family = FONT_MAP.get(caption_settings.get('font', 'arial'), 'Arial')
        font_style = caption_settings.get('fontStyle', 'normal')
        position = caption_settings.get('position', 'bottom')
        text_alignment = caption_settings.get('alignment', 'center')
        
        color_hex = COLOR_MAP.get(color_name, '00FFFFFF')
        bg_color_hex = BG_COLOR_MAP.get(bg_color_name, '00FFFFFF')
        
        # Determine font styling
        bold = -1 if 'bold' in font_style else 0
        italic = -1 if 'italic' in font_style else 0
        
        # Determine BorderStyle based on background
        has_background = bg_color_name != 'none'
        
        if has_background:
            border_style = '4'  # Background box
            outline = '3'  # Padding/margin around text
            shadow = '0'
        else:
            border_style = '1'
            outline = '2'  # Text outline
            shadow = '0'
        
        # Get ASS alignment code based on position and text alignment
        ass_alignment = get_ass_alignment(position, text_alignment)
        
        # Calculate margins based on position and alignment
        margin_l, margin_r, margin_v = calculate_margins(position, ass_alignment)
        
        # ASS header with style definition
        ass_content = """[Script Info]
Title: Scrideo Subtitles
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},&H{color},&H{color},&H00000000,&H{bgcolor},{bold},{italic},0,0,100,100,0,0,{borderstyle},{outline},{shadow},{alignment},{marginl},{marginr},{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""".format(
            fontname=font_family,
            fontsize=font_size,
            color=color_hex,
            bgcolor=bg_color_hex,
            bold=bold,
            italic=italic,
            borderstyle=border_style,
            outline=outline,
            shadow=shadow,
            alignment=ass_alignment,
            marginl=margin_l,
            marginr=margin_r,
            marginv=margin_v
        )
        
        # Read SRT file
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_lines = f.readlines()
        
        i = 0
        while i < len(srt_lines):
            line = srt_lines[i].strip()
            
            # Look for timestamp line
            if '-->' in line:
                time_parts = line.split(' --> ')
                if len(time_parts) == 2:
                    start_time = convert_time_srt_to_ass(time_parts[0].strip())
                    end_time = convert_time_srt_to_ass(time_parts[1].strip())
                    
                    # Get text (next lines until empty line)
                    i += 1
                    text_lines = []
                    while i < len(srt_lines) and srt_lines[i].strip():
                        text_lines.append(srt_lines[i].strip())
                        i += 1
                    
                    text = '\\N'.join(text_lines)
                    
                    # Do NOT add alignment tags - the Style already handles alignment
                    # The ass_alignment in the style is sufficient
                    
                    # Create ASS line
                    ass_line = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
                    ass_content += ass_line
            
            i += 1
        
        # Write ASS file
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        logger.info(f"ASS file generated: {ass_path} with position={position}, alignment={text_alignment}")
        logger.debug(f"ASS styling: Alignment={ass_alignment}, Margins L/R/V={margin_l}/{margin_r}/{margin_v}")
        
        return True
        
    except Exception as e:
        logger.error(f"SRT to ASS conversion failed: {e}")
        raise

def convert_time_srt_to_ass(time_str):
    """Convert SRT timestamp to ASS format"""
    # SRT: HH:MM:SS,mmm
    # ASS: H:MM:SS.cc
    parts = time_str.replace(',', '.').split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"

# -------------------------- SRT Generation --------------------------

def format_time(seconds: float) -> str:
    """Convert seconds → SRT timestamp (HH:MM:SS,mmm)"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_srt(segments, srt_path):
    """Create SRT with short chunks (max 7 words per line)"""
    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for seg in segments:
                text = seg['text'].strip()
                if not text:
                    continue

                words = text.split()
                max_words = 7
                if len(words) <= max_words:
                    f.write(f"{idx}\n")
                    f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
                    f.write(f"{text}\n\n")
                    idx += 1
                else:
                    total_dur = seg['end'] - seg['start']
                    chunks = [words[i:i + max_words] for i in range(0, len(words), max_words)]
                    chunk_dur = total_dur / len(chunks)
                    for i, chunk in enumerate(chunks):
                        start = seg['start'] + i * chunk_dur
                        end = min(seg['start'] + (i + 1) * chunk_dur, seg['end'])
                        f.write(f"{idx}\n")
                        f.write(f"{format_time(start)} --> {format_time(end)}\n")
                        f.write(f"{' '.join(chunk)}\n\n")
                        idx += 1
        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
            raise Exception("SRT file empty")
        logger.info(f"SRT generated: {srt_path}")
        return True
    except Exception as e:
        logger.error(f"SRT generation failed: {e}")
        raise

# -------------------------- FFmpeg Overlay --------------------------

def overlay_subtitles(input_path, srt_path, output_path, caption_settings=None):
    """Overlay subtitles with customization using ASS format"""
    try:
        # Default caption settings
        if caption_settings is None:
            caption_settings = {
                'size': '20', 
                'color': 'white', 
                'bgColor': 'none', 
                'font': 'arial', 
                'fontStyle': 'normal',
                'position': 'bottom',
                'alignment': 'center'
            }
        
        # Absolute paths
        input_path = os.path.abspath(input_path)
        srt_path = os.path.abspath(srt_path)
        output_path = os.path.abspath(output_path)
        
        # Create ASS file path
        ass_path = srt_path.replace('.srt', '.ass')

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input not found: {input_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT not found: {srt_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Convert SRT to ASS with styling
        convert_srt_to_ass(srt_path, ass_path, caption_settings)

        # Windows-compatible path handling
        if os.name == 'nt':  # Windows
            input_path_ffmpeg = input_path.replace('\\', '/')
            output_path_ffmpeg = output_path.replace('\\', '/')
            ass_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
        else:  # Linux/Mac
            input_path_ffmpeg = input_path
            output_path_ffmpeg = output_path
            ass_escaped = ass_path.replace(':', '\\:')

        # Use ass filter instead of subtitles filter
        subtitles_filter = f"ass='{ass_escaped}'"
        
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path_ffmpeg,
            '-vf', subtitles_filter,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-crf', '23',
            '-preset', 'fast',
            '-movflags', '+faststart',
            output_path_ffmpeg
        ]

        font_family = FONT_MAP.get(caption_settings.get('font', 'arial'), 'Arial')
        font_style = caption_settings.get('fontStyle', 'normal')
        color_name = caption_settings.get('color', 'white')
        bg_color_name = caption_settings.get('bgColor', 'none')
        font_size = caption_settings.get('size', '20')
        position = caption_settings.get('position', 'bottom')
        alignment = caption_settings.get('alignment', 'center')
        
        logger.info(f"Running FFmpeg overlay with caption settings: position={position}, alignment={alignment}")
        logger.debug(f"FFmpeg cmd: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 min
        )
        logger.info("FFmpeg finished")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("FFmpeg produced empty output")
        
        # Clean up ASS file after successful processing
        try:
            if os.path.exists(ass_path):
                os.remove(ass_path)
                logger.info(f"Cleaned up ASS file: {ass_path}")
        except Exception as e:
            logger.warning(f"Could not delete ASS file: {e}")
        
        return True

    except subprocess.TimeoutExpired:
        raise Exception("FFmpeg timed out (5 min)")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e.stderr}")
    except Exception as e:
        raise Exception(f"Overlay failed: {str(e)}")

# -------------------------- FFmpeg Check --------------------------

def check_ffmpeg_installation():
    try:
        res = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if res.returncode == 0:
            logger.info(f"FFmpeg version: {res.stdout.splitlines()[0]}")
            return True
        return False
    except Exception:
        logger.error("FFmpeg not found")
        return False