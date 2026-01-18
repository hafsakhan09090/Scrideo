import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# Text color mapping (AABBGGRR format)
# AA = alpha: 00=opaque
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

# Background color mapping - FIXED WITH PROPER OPACITY
# In ASS format AABBGGRR: AA controls transparency where 00=fully opaque, FF=fully transparent
# We use 00-40 range for visible backgrounds (fully opaque to mostly opaque)
BG_COLOR_MAP = {
    'none': 'FF000000',          # Fully transparent (no background)
    'black': '00000000',         # Black fully opaque (was C0)
    'dark-gray': '00333333',     # Dark gray fully opaque (was C0)
    'semi-transparent': '80000000',  # Black with 50% opacity (was E0)
    'dark-blue': '00800000',     # Dark blue fully opaque (was C0)
    'dark-red': '00000080',      # Dark red fully opaque (was C0)
    'dark-green': '00008000',    # Dark green fully opaque (was C0)
    'dark-purple': '00800080',   # Dark purple fully opaque (was C0)
    'navy': '00800000',          # Navy fully opaque (was C0)
    'charcoal': '00363636'       # Charcoal gray fully opaque (was C0)
}

# Font mapping
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

def get_ass_alignment_and_margins(position, text_alignment):
    """
    ASS Alignment codes (NumPad layout):
    7 8 9  (top-left, top-center, top-right)
    4 5 6  (middle-left, middle-center, middle-right)
    1 2 3  (bottom-left, bottom-center, bottom-right)
    
    Returns: (alignment_code, margin_left, margin_right, margin_vertical)
    """
    
    # Map positions to alignment codes
    position_map = {
        'top-left': (7, '40', '10', '20'),
        'top': (8, '10', '10', '20'),
        'top-right': (9, '10', '40', '20'),
        'middle-left': (4, '40', '10', '0'),
        'middle': (5, '10', '10', '0'),
        'middle-right': (6, '10', '40', '0'),
        'bottom-left': (1, '40', '10', '20'),
        'bottom': (2, '10', '10', '20'),
        'bottom-right': (3, '10', '40', '20'),
    }
    
    # Get base position
    base_position = position_map.get(position, (2, '10', '10', '20'))  # default to bottom-center
    
    # For non-corner positions, apply text alignment
    if position in ['top', 'middle', 'bottom']:
        alignment_base = base_position[0]
        
        if text_alignment == 'left':
            # Shift to left variant: 8→7, 5→4, 2→1
            alignment_code = alignment_base - 1
            margins = ('40', '10', base_position[3])
        elif text_alignment == 'right':
            # Shift to right variant: 8→9, 5→6, 2→3
            alignment_code = alignment_base + 1
            margins = ('10', '40', base_position[3])
        else:  # center
            alignment_code = alignment_base
            margins = ('10', '10', base_position[3])
        
        return alignment_code, margins[0], margins[1], margins[2]
    
    # For corner positions, return as-is
    return base_position

def convert_srt_to_ass(srt_path, ass_path, caption_settings=None):
    """Convert SRT to ASS with proper styling"""
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
        
        # Get colors
        primary_color = COLOR_MAP.get(color_name, '00FFFFFF')
        back_color = BG_COLOR_MAP.get(bg_color_name, 'FF000000')
        
        # Font styling
        bold = -1 if 'bold' in font_style else 0
        italic = -1 if 'italic' in font_style else 0
        
        # Border and shadow settings
        has_background = bg_color_name != 'none'
        
        if has_background:
            border_style = '4'  # Opaque box background
            outline = '2'       # Padding inside box
            shadow = '0'        # No shadow when box background exists
        else:
            border_style = '1'  # Outline + shadow
            outline = '2'       # Outline thickness
            shadow = '1'        # Shadow depth
        
        # Get alignment and margins
        alignment, margin_l, margin_r, margin_v = get_ass_alignment_and_margins(position, text_alignment)
        
        # Build ASS file
        ass_content = f"""[Script Info]
Title: Scrideo Subtitles
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},&H{primary_color},&H{primary_color},&H00000000,&H{back_color},{bold},{italic},0,0,100,100,0,0,{border_style},{outline},{shadow},{alignment},{margin_l},{margin_r},{margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Read and convert SRT
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_lines = f.readlines()
        
        i = 0
        while i < len(srt_lines):
            line = srt_lines[i].strip()
            
            if '-->' in line:
                time_parts = line.split(' --> ')
                if len(time_parts) == 2:
                    start = convert_time_srt_to_ass(time_parts[0].strip())
                    end = convert_time_srt_to_ass(time_parts[1].strip())
                    
                    # Get text
                    i += 1
                    text_lines = []
                    while i < len(srt_lines) and srt_lines[i].strip():
                        text_lines.append(srt_lines[i].strip())
                        i += 1
                    
                    text = '\\N'.join(text_lines)
                    ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
            
            i += 1
        
        # Write ASS file
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        logger.info(f"✅ ASS: pos={position}, align={text_alignment}, color={color_name}, bg={bg_color_name}")
        logger.debug(f"ASS codes: alignment={alignment}, margins={margin_l}/{margin_r}/{margin_v}, BackColour=&H{back_color}")
        
        return True
        
    except Exception as e:
        logger.error(f"ASS conversion failed: {e}")
        raise

def convert_time_srt_to_ass(time_str):
    """SRT timestamp to ASS format"""
    parts = time_str.replace(',', '.').split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"

def format_time(seconds: float) -> str:
    """Seconds to SRT timestamp"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_srt(segments, srt_path):
    """Generate SRT with short chunks"""
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
                        
        logger.info(f"✅ SRT generated")
        return True
        
    except Exception as e:
        logger.error(f"SRT generation failed: {e}")
        raise

def overlay_subtitles(input_path, srt_path, output_path, caption_settings=None):
    """Overlay subtitles via FFmpeg"""
    try:
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
        
        input_path = os.path.abspath(input_path)
        srt_path = os.path.abspath(srt_path)
        output_path = os.path.abspath(output_path)
        ass_path = srt_path.replace('.srt', '.ass')

        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input not found: {input_path}")
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT not found: {srt_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Convert to ASS
        convert_srt_to_ass(srt_path, ass_path, caption_settings)

        # FFmpeg path handling
        if os.name == 'nt':
            input_path_ffmpeg = input_path.replace('\\', '/')
            output_path_ffmpeg = output_path.replace('\\', '/')
            ass_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
        else:
            input_path_ffmpeg = input_path
            output_path_ffmpeg = output_path
            ass_escaped = ass_path.replace(':', '\\:')

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

        logger.info(f"🎬 FFmpeg overlay starting...")
        logger.debug(f"CMD: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        logger.info("✅ FFmpeg complete")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("FFmpeg output empty")
        
        # Cleanup
        try:
            if os.path.exists(ass_path):
                os.remove(ass_path)
        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")
        
        return True

    except subprocess.TimeoutExpired:
        raise Exception("FFmpeg timeout")
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e.stderr}")
    except Exception as e:
        raise Exception(f"Overlay failed: {str(e)}")

def check_ffmpeg_installation():
    """Check FFmpeg availability"""
    try:
        res = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if res.returncode == 0:
            logger.info(f"FFmpeg OK")
            return True
        return False
    except Exception:
        logger.error("FFmpeg not found")
        return False
