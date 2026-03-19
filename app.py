import os
import subprocess
import logging
import uuid
import threading
import tempfile
import shutil
import time
from datetime import datetime, timedelta
import gc
import psutil
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp
import hashlib
import jwt
import json

# AI imports
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

app = Flask(__name__)

# Hugging Face specific paths
BASE_DIR = "/app"
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Storage
TEMP_STORAGE_LIMIT = 500 * 1024 * 1024  # 500MB
job_status = {}
users = {}
user_jobs = {}
processing_lock = threading.Lock()

# JWT Secret
SECRET_KEY = os.environ.get('SECRET_KEY', 'scrideo-hf-secret-2024')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Whisper model
whisper_model = None
if WHISPER_AVAILABLE:
    try:
        print("🚀 Loading Whisper model...")
        whisper_model = whisper.load_model("base")
        print("✅ Whisper model loaded successfully!")
    except Exception as e:
        print(f"❌ Whisper loading failed: {e}")
        WHISPER_AVAILABLE = False

CORS(app)

# Helper functions
def get_directory_size(directory):
    total = 0
    try:
        for entry in os.scandir(directory):
            if entry.is_file():
                total += entry.stat().st_size
    except:
        pass
    return total

def cleanup_old_files():
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=2)
    
    with processing_lock:
        jobs_to_remove = []
        for job_id, job_info in list(job_status.items()):
            if job_info.get('status') in ['completed', 'failed']:
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove[5:]:  # Keep last 5 jobs
            cleanup_job_files(job_id)

def cleanup_job_files(job_id):
    with processing_lock:
        job_status.pop(job_id, None)
        user_jobs.pop(job_id, None)
    
    for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
        for filename in os.listdir(folder):
            if filename.startswith(job_id):
                try:
                    os.remove(os.path.join(folder, filename))
                except:
                    pass

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_srt(segments, srt_path):
    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for seg in segments:
                text = seg['text'].strip()
                if not text:
                    continue
                f.write(f"{idx}\n")
                f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
                f.write(f"{text}\n\n")
                idx += 1
        return True
    except Exception as e:
        logger.error(f"SRT generation failed: {e}")
        raise

# Replace the overlay_subtitles function in app.py (around line 150) with this:

def overlay_subtitles(input_path, srt_path, output_path, caption_settings=None):
    try:
        if caption_settings is None:
            caption_settings = {}
        
        # Get caption settings with defaults
        font_size = caption_settings.get('size', '20')
        font_color = caption_settings.get('color', 'white')
        font_family = caption_settings.get('font', 'Arial')
        bg_color = caption_settings.get('bgColor', 'none')
        position = caption_settings.get('position', 'bottom')
        alignment = caption_settings.get('alignment', 'center')
        outline = caption_settings.get('outlineThickness', 'medium')
        shadow = caption_settings.get('shadowDistance', 'medium')
        font_style = caption_settings.get('fontStyle', 'normal')
        
        # Convert SRT to ASS for better styling control
        ass_path = srt_path.replace('.srt', '.ass')
        
        # Color mapping for ASS (AABBGGRR format where AA=00 is opaque)
        color_map = {
            'white': '00FFFFFF',
            'yellow': '0000FFFF',
            'cyan': '00FFFF00', 
            'lime': '0000FF00',
            'orange': '0000A5FF',
            'red': '000000FF',
            'pink': '00FFC0CB',
            'purple': '00A020F0',
            'light-blue': '00E6D8AD',
            'light-green': '0090EE90'
        }
        
        # Background color mapping - FIXED: 00=fully opaque, FF=fully transparent
        bg_color_map = {
            'none': 'FF000000',              # Fully transparent
            'black': '00000000',             # Black fully opaque
            'dark-gray': '00333333',         # Dark gray fully opaque
            'semi-transparent': '80000000',  # Black 50% opacity
            'dark-blue': '00800000',         # Dark blue fully opaque
            'dark-red': '00000080',          # Dark red fully opaque
            'dark-green': '00008000',        # Dark green fully opaque
            'dark-purple': '00800080',       # Dark purple fully opaque
            'navy': '00800000',              # Navy fully opaque
            'charcoal': '00363636'           # Charcoal fully opaque
        }
        
        # Font mapping
        font_map = {
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
        
        # Position mapping (ASS alignment - numpad layout)
        position_map = {
            'bottom': (2, '10', '10', '20'),
            'top': (8, '10', '10', '20'),
            'bottom-left': (1, '40', '10', '20'), 
            'bottom-right': (3, '10', '40', '20'),
            'top-left': (7, '40', '10', '20'),
            'top-right': (9, '10', '40', '20'),
            'middle': (5, '10', '10', '0')
        }
        
        # Get position settings
        alignment_code, margin_l, margin_r, margin_v = position_map.get(position, (2, '10', '10', '20'))
        
        # Adjust alignment based on text alignment setting
        if position in ['top', 'middle', 'bottom']:
            if alignment == 'left':
                alignment_code -= 1
                margin_l = '40'
                margin_r = '10'
            elif alignment == 'right':
                alignment_code += 1
                margin_l = '10'
                margin_r = '40'
        
        # Get colors
        primary_color = color_map.get(font_color, '00FFFFFF')
        back_color = bg_color_map.get(bg_color, 'FF000000')
        font_name = font_map.get(font_family.lower(), font_family)
        
        # Font style
        bold = -1 if 'bold' in font_style else 0
        italic = -1 if 'italic' in font_style else 0
        
        # Border settings
        has_background = bg_color != 'none'
        
        if has_background:
            border_style = '4'  # Opaque box
            outline_val = '2'   # Padding
            shadow_val = '0'    # No shadow with box
        else:
            border_style = '1'  # Outline + shadow
            outline_val = {'none': '0', 'thin': '1', 'medium': '2', 'thick': '3', 'extra-thick': '4'}.get(outline, '2')
            shadow_val = {'none': '0', 'subtle': '1', 'medium': '2', 'large': '3', 'extra-large': '4'}.get(shadow, '2')
        
        # Create ASS file
        ass_content = f"""[Script Info]
Title: Scrideo Subtitles
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H{primary_color},&H{primary_color},&H00000000,&H{back_color},{bold},{italic},0,0,100,100,0,0,{border_style},{outline_val},{shadow_val},{alignment_code},{margin_l},{margin_r},{margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Convert SRT to ASS
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_lines = f.readlines()
        
        i = 0
        while i < len(srt_lines):
            line = srt_lines[i].strip()
            
            if '-->' in line:
                time_parts = line.split(' --> ')
                if len(time_parts) == 2:
                    # Convert SRT time to ASS time
                    start = time_parts[0].strip().replace(',', '.')
                    end = time_parts[1].strip().replace(',', '.')
                    
                    # Parse times
                    start_parts = start.split(':')
                    end_parts = end.split(':')
                    
                    start_h, start_m = int(start_parts[0]), int(start_parts[1])
                    start_s = float(start_parts[2])
                    end_h, end_m = int(end_parts[0]), int(end_parts[1])
                    end_s = float(end_parts[2])
                    
                    start_ass = f"{start_h}:{start_m:02d}:{start_s:05.2f}"
                    end_ass = f"{end_h}:{end_m:02d}:{end_s:05.2f}"
                    
                    # Get text
                    i += 1
                    text_lines = []
                    while i < len(srt_lines) and srt_lines[i].strip():
                        text_lines.append(srt_lines[i].strip())
                        i += 1
                    
                    text = '\\N'.join(text_lines)
                    ass_content += f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}\n"
            
            i += 1
        
        # Write ASS file
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        logger.info(f"🎨 ASS subtitle created: color={font_color}, bg={bg_color}, BackColour=&H{back_color}")
        
        # Build FFmpeg command using ASS
        if os.name == 'nt':
            ass_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
        else:
            ass_escaped = ass_path.replace(':', '\\:')
        
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-vf', f"ass='{ass_escaped}'",
            '-c:v', 'libx264',
            '-c:a', 'copy',
            '-preset', 'fast',
            output_path
        ]
        
        logger.info(f"🔧 FFmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise Exception(f"FFmpeg failed: {result.stderr}")
        
        if os.path.exists(output_path):
            logger.info("✅ Styled subtitles embedded successfully!")
            # Clean up ASS file
            try:
                os.remove(ass_path)
            except:
                pass
            return True
        else:
            raise Exception("Output file not created")
        
    except Exception as e:
        logger.error(f"Subtitle overlay failed: {e}")
        raise Exception(f"Subtitle overlay failed: {str(e)}")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_token(token):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return decoded['username']
    except:
        return None

def process_video_task(job_id, filepath, filename, is_youtube=False, token=None, caption_settings=None):
    try:
        logger.info(f"Starting processing for job {job_id}")
        
        with processing_lock:
            job_status[job_id] = {'status': 'transcribing', 'filename': filename}

        if not WHISPER_AVAILABLE:
            raise Exception("Whisper not available")
        
        result = whisper_model.transcribe(filepath, word_timestamps=True)
        
        if not result or 'segments' not in result:
            raise Exception("No speech detected")

        with processing_lock:
            job_status[job_id] = {'status': 'generating_captions', 'filename': filename}
        
        srt_path = os.path.join(PROCESSED_FOLDER, f"{job_id}_captions.srt")
        output_filename = f"{job_id}_with_subtitles.mp4"
        output_path = os.path.join(PROCESSED_FOLDER, output_filename)

        generate_srt(result["segments"], srt_path)
        
        transcription_text = " ".join([seg['text'].strip() for seg in result["segments"]])
        video_duration = result['segments'][-1]['end'] if result['segments'] else 0
        
        with processing_lock:
            job_status[job_id] = {'status': 'embedding_subtitles', 'filename': filename}
        
        # FIXED: Pass caption settings to overlay function
        logger.info(f"🎯 Using caption settings: {caption_settings}")
        overlay_subtitles(filepath, srt_path, output_path, caption_settings)
        
        if os.path.exists(output_path):
            end_time = datetime.now()
            with processing_lock:
                job_info = {
                    'status': 'completed',
                    'filename': filename,
                    'download_url': f"/download/{output_filename}",
                    'transcription': transcription_text,
                    'date': end_time.strftime('%Y-%m-%d'),
                    'time': end_time.strftime('%H:%M:%S'),
                    'duration': f"{int(video_duration // 60)}:{int(video_duration % 60):02d}"
                }
                job_status[job_id] = job_info
                user_jobs[job_id] = job_info
                if token:
                    username = verify_token(token)
                    if username and username in users:
                        users[username]['history'].append(job_id)
            
            # Cleanup
            try:
                os.remove(srt_path)
                if filepath != output_path:
                    os.remove(filepath)
            except:
                pass
                
            logger.info(f"Processing completed for job {job_id}")
        else:
            raise Exception("Output video not created")
            
    except Exception as e:
        logger.error(f"Processing failed for job {job_id}: {str(e)}")
        start_time = datetime.now()
        with processing_lock:
            job_info = {
                'status': 'failed',
                'filename': filename,
                'error': str(e),
                'date': start_time.strftime('%Y-%m-%d'),
                'time': start_time.strftime('%H:%M:%S'),
                'duration': 'N/A'
            }
            job_status[job_id] = job_info
            user_jobs[job_id] = job_info
            if token:
                username = verify_token(token)
                if username and username in users:
                    users[username]['history'].append(job_id)

# ========== FIXED LOGIN/SIGNUP ROUTES ==========
@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        
        # Quick validation without heavy processing
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        with processing_lock:
            if username in users:
                return jsonify({'error': 'Username already exists'}), 400
            
            users[username] = {
                'password_hash': password_hash,
                'history': [],
                'favorites': set()
            }
            
            # Fast token generation
            token = jwt.encode({'username': username}, SECRET_KEY, algorithm='HS256')
            
        logger.info(f"✅ User signed up: {username}")
        return jsonify({'token': token}), 201
        
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return jsonify({'error': 'Signup failed'}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        # Fast password hash
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        with processing_lock:
            user = users.get(username)
            if not user or user['password_hash'] != password_hash:
                return jsonify({'error': 'Invalid credentials'}), 401
            
            # Fast token generation
            token = jwt.encode({'username': username}, SECRET_KEY, algorithm='HS256')
            
        logger.info(f"✅ User logged in: {username}")
        return jsonify({'token': token}), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500
# ========== END FIXED LOGIN/SIGNUP ==========

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "platform": "huggingface",
        "whisper_available": WHISPER_AVAILABLE,
        "gpu_available": True,
        "storage_used_mb": round(get_directory_size(BASE_DIR) / 1024 / 1024, 2)
    })

# ========== FIXED UPLOAD ROUTE WITH CAPTION SETTINGS ==========
@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    # Check file extension
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    file_ext = os.path.splitext(video.filename.lower())[1]
    if file_ext not in allowed_extensions:
        return jsonify({'error': 'Only video files are allowed'}), 400

    current_storage = get_directory_size(BASE_DIR)
    if current_storage > TEMP_STORAGE_LIMIT * 0.8:
        cleanup_old_files()

    job_id = str(uuid.uuid4())
    filename = f"{job_id}_{video.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        video.save(filepath)
        
        with processing_lock:
            job_status[job_id] = {'status': 'uploaded', 'filename': video.filename}
        
        # FIXED: Get caption settings from form data
        caption_settings = {}
        if 'captionSettings' in request.form:
            try:
                caption_settings = json.loads(request.form['captionSettings'])
                logger.info(f"🎨 Caption settings received: {caption_settings}")
            except Exception as e:
                logger.warning(f"Could not parse caption settings: {e}")
        
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        thread = threading.Thread(
            target=process_video_task, 
            args=(job_id, filepath, video.filename, False, token, caption_settings), 
            daemon=True
        )
        thread.start()

        return jsonify({'job_id': job_id}), 202
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    with processing_lock:
        if job_id not in job_status:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job_status[job_id])

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    path = os.path.join(PROCESSED_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)

def download_youtube_video(youtube_url, job_id):
    try:
        temp_video = os.path.join(UPLOAD_FOLDER, f"{job_id}_youtube.mp4")
        
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': temp_video,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get('title', 'youtube_video')
            
        return temp_video, f"{title}.mp4"
        
    except Exception as e:
        raise Exception(f"YouTube download failed: {str(e)}")

@app.route('/transcribe', methods=['POST'])
def transcribe_youtube():
    data = request.get_json()
    youtube_url = data.get('url')
    caption_settings = data.get('captionSettings')
    
    if not youtube_url:
        return jsonify({'error': 'YouTube URL required'}), 400
    
    current_storage = get_directory_size(BASE_DIR)
    if current_storage > TEMP_STORAGE_LIMIT * 0.8:
        cleanup_old_files()
    
    job_id = str(uuid.uuid4())
    
    try:
        with processing_lock:
            job_status[job_id] = {'status': 'downloading', 'filename': 'YouTube Video'}
        
        video_path, filename = download_youtube_video(youtube_url, job_id)
        
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        thread = threading.Thread(
            target=process_video_task,
            args=(job_id, video_path, filename, True, token, caption_settings),
            daemon=True
        )
        thread.start()

        return jsonify({'job_id': job_id}), 202
        
    except Exception as e:
        logger.error(f"YouTube processing failed: {e}")
        with processing_lock:
            job_status[job_id] = {'status': 'failed', 'error': str(e)}
        return jsonify({'error': str(e)}), 500

@app.route('/profile', methods=['GET'])
def get_profile():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = verify_token(token)
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with processing_lock:
        user = users.get(username, {})
        job_ids = user.get('history', [])
        favorites = user.get('favorites', set())
        history = []
        
        for job_id in job_ids:
            job_info = user_jobs.get(job_id, {}).copy()
            if job_info:
                job_info['job_id'] = job_id
                job_info['favorited'] = job_id in favorites
                history.append(job_info)
        
        history.sort(key=lambda x: (x.get('date', ''), x.get('time', '')), reverse=True)
        
        return jsonify({
            'username': username,
            'job_count': len(job_ids),
            'favorite_count': len(favorites),
            'history': history
        }), 200

@app.route('/history/<job_id>/favorite', methods=['POST'])
def toggle_favorite(job_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = verify_token(token)
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with processing_lock:
        user = users.get(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if job_id not in user.get('history', []):
            return jsonify({'error': 'Job not found in user history'}), 404
        
        if 'favorites' not in user:
            user['favorites'] = set()
        
        if job_id in user['favorites']:
            user['favorites'].discard(job_id)
            favorited = False
        else:
            user['favorites'].add(job_id)
            favorited = True
        
        return jsonify({'favorited': favorited}), 200

@app.route('/history/<job_id>', methods=['DELETE'])
def delete_history_item(job_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    username = verify_token(token)
    if not username:
        return jsonify({'error': 'Unauthorized'}), 401
    
    with processing_lock:
        user = users.get(username)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if job_id in user['history']:
            user['history'].remove(job_id)
        
        if 'favorites' in user and job_id in user['favorites']:
            user['favorites'].discard(job_id)
        
        if job_id in job_status:
            del job_status[job_id]
        if job_id in user_jobs:
            del user_jobs[job_id]
    
    cleanup_job_files(job_id)
    
    return jsonify({'message': 'History item deleted successfully'}), 200

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# Periodic cleanup
def cleanup_loop():
    while True:
        time.sleep(1800)  # 30 minutes
        cleanup_old_files()

cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    print("🚀 Scrideo Hugging Face Edition Starting...")
    print(f"🔊 Whisper: {'Available' if WHISPER_AVAILABLE else 'Not Available'}")
    print(f"🌐 Server: http://0.0.0.0:{port}")
    print(f"💾 Storage: {TEMP_STORAGE_LIMIT/1024/1024}MB")
    app.run(host='0.0.0.0', port=port, debug=False)
