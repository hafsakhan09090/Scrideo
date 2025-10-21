import os
import subprocess
import logging
import shlex
import uuid
import threading
import tempfile
import shutil
import time
from datetime import datetime, timedelta
import whisper
import gc
import psutil
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from helpers import generate_srt, overlay_subtitles, check_ffmpeg_installation
import yt_dlp
import hashlib
import jwt
import json

app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CORS
CORS(app, origins=["http://localhost:5000", "https://scrideo.app"])

# Storage
TEMP_STORAGE_LIMIT = 200 * 1024 * 1024  # 200MB
TEMP_BASE_DIR = tempfile.mkdtemp(prefix='scrideo_')
UPLOAD_FOLDER = os.path.join(TEMP_BASE_DIR, 'Uploads')
PROCESSED_FOLDER = os.path.join(TEMP_BASE_DIR, 'processed')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Job and user management
job_status = {}
file_timestamps = {}
download_timestamps = {}
processing_lock = threading.Lock()
users = {}  # In-memory user storage {username: {password_hash, history: [job_ids], favorites: set([job_ids])}}
user_jobs = {}  # In-memory job storage per user {job_id: {status, filename, download_url, transcription, date, time, duration}}

# Whisper model
whisper_model = None
model_load_lock = threading.Lock()

# JWT Secret
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key')  # Use environment variable in production

@app.route("/")
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    """Health check"""
    if check_ffmpeg_installation():
        return jsonify({"status": "ok", "ffmpeg": "available"})
    return jsonify({"status": "error", "error": "FFmpeg not found"}), 500

def get_directory_size(directory):
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except Exception as e:
        logger.error(f"Error calculating directory size: {e}")
    return total_size

def cleanup_old_files():
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=6)
    files_to_remove = []
    
    with processing_lock:
        for job_id, timestamp in list(file_timestamps.items()):
            if timestamp < cutoff_time:
                status = job_status.get(job_id, {}).get('status')
                if status in ['completed', 'failed']:
                    files_to_remove.append(job_id)
    
    for job_id in files_to_remove:
        try:
            cleanup_job_files(job_id)
        except Exception as e:
            logger.error(f"Error cleaning up job {job_id}: {e}")

def cleanup_job_files(job_id):
    with processing_lock:
        job_status.pop(job_id, None)
        file_timestamps.pop(job_id, None)
        download_timestamps.pop(job_id, None)
    
    for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.startswith(job_id):
                    filepath = os.path.join(folder, filename)
                    try:
                        os.remove(filepath)
                    except Exception as e:
                        logger.error(f"Failed to remove {filepath}: {e}")

def periodic_cleanup():
    while True:
        time.sleep(7200)  # 2 hours
        current_usage = get_directory_size(TEMP_BASE_DIR)
        if current_usage / TEMP_STORAGE_LIMIT > 0.8:
            cleanup_old_files()

cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
cleanup_thread.start()

def load_whisper_model():
    global whisper_model
    with model_load_lock:
        if whisper_model is not None:
            return whisper_model
        try:
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            model_name = "tiny" if available_gb < 1.0 else "base"
            logger.info(f"Loading Whisper model: {model_name}")
            whisper_model = whisper.load_model(model_name)
            logger.info(f"Successfully loaded Whisper model: {model_name}")
            return whisper_model
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            try:
                logger.info("Falling back to tiny model")
                whisper_model = whisper.load_model("tiny")
                return whisper_model
            except Exception as fallback_error:
                logger.error(f"Failed to load fallback model: {fallback_error}")
                raise

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_token(token):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return decoded['username']
    except:
        return None

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    password_confirm = data.get('password_confirm')
    
    if not username or not password or not password_confirm:
        return jsonify({'error': 'Username and both passwords required'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if password != password_confirm:
        return jsonify({'error': 'Passwords do not match'}), 400
    
    with processing_lock:
        if username in users:
            return jsonify({'error': 'Username already exists'}), 400
        
        users[username] = {
            'password_hash': hash_password(password),
            'history': [],
            'favorites': set()
        }
        token = jwt.encode({'username': username}, SECRET_KEY, algorithm='HS256')
        return jsonify({'token': token}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    with processing_lock:
        user = users.get(username)
        if not user or user['password_hash'] != hash_password(password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        token = jwt.encode({'username': username}, SECRET_KEY, algorithm='HS256')
        return jsonify({'token': token}), 200

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
            if job_info:  # Only include jobs that exist in user_jobs
                job_info['job_id'] = job_id
                job_info['favorited'] = job_id in favorites
                history.append(job_info)
        
        # Sort history by date and time (newest first)
        history.sort(key=lambda x: (x.get('date', ''), x.get('time', '')), reverse=True)
        
        return jsonify({
            'username': username,
            'job_count': len(job_ids),
            'favorite_count': len(favorites),
            'history': history
        }), 200

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
        
        # Remove from user's history
        if job_id in user['history']:
            user['history'].remove(job_id)
        
        # Remove from favorites if present
        if 'favorites' in user and job_id in user['favorites']:
            user['favorites'].discard(job_id)
        
        # Remove from job_status and user_jobs
        if job_id in job_status:
            del job_status[job_id]
        if job_id in user_jobs:
            del user_jobs[job_id]
        
        # Clean up timestamps
        if job_id in file_timestamps:
            del file_timestamps[job_id]
        if job_id in download_timestamps:
            del download_timestamps[job_id]
    
    # Clean up files (outside the lock to avoid blocking)
    cleanup_job_files(job_id)
    
    logger.info(f"Deleted history item {job_id} for user {username}")
    return jsonify({'message': 'History item deleted successfully'}), 200

def cleanup_job_files(job_id):
    """Clean up all files associated with a job"""
    try:
        # Clean up uploaded files
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if filename.startswith(job_id):
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    try:
                        os.remove(filepath)
                        logger.info(f"Deleted uploaded file: {filepath}")
                    except Exception as e:
                        logger.error(f"Failed to remove uploaded file {filepath}: {e}")
        
        # Clean up processed files
        if os.path.exists(PROCESSED_FOLDER):
            for filename in os.listdir(PROCESSED_FOLDER):
                if filename.startswith(job_id):
                    filepath = os.path.join(PROCESSED_FOLDER, filename)
                    try:
                        os.remove(filepath)
                        logger.info(f"Deleted processed file: {filepath}")
                    except Exception as e:
                        logger.error(f"Failed to remove processed file {filepath}: {e}")
        
        # Clean up any temporary subtitle files
        temp_files = [
            os.path.join(PROCESSED_FOLDER, f"{job_id}_captions.srt"),
            os.path.join(PROCESSED_FOLDER, f"{job_id}_captions.ass"),
            os.path.join(UPLOAD_FOLDER, f"{job_id}_youtube_video.mp4"),
            os.path.join(UPLOAD_FOLDER, f"{job_id}_youtube_fallback.mp4")
        ]
        
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Deleted temp file: {temp_file}")
                except Exception as e:
                    logger.error(f"Failed to remove temp file {temp_file}: {e}")
                    
    except Exception as e:
        logger.error(f"Error during file cleanup for job {job_id}: {e}")
        
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
        
        # Check if job exists in user's history
        if job_id not in user.get('history', []):
            return jsonify({'error': 'Job not found in user history'}), 404
        
        # Ensure favorites set exists
        if 'favorites' not in user:
            user['favorites'] = set()
        
        # Toggle favorite status
        if job_id in user['favorites']:
            user['favorites'].discard(job_id)
            favorited = False
        else:
            user['favorites'].add(job_id)
            favorited = True
        
        logger.info(f"{'Added' if favorited else 'Removed'} favorite {job_id} for user {username}")
        return jsonify({'favorited': favorited}), 200

def process_video_task(job_id, filepath, filename, is_youtube=False, token=None, caption_settings=None):
    try:
        logger.info(f"Starting processing for job {job_id}")
        start_time = datetime.now()
        
        with processing_lock:
            job_status[job_id] = {'status': 'transcribing', 'filename': filename}

        model = load_whisper_model()
        logger.info(f"Starting transcription")
        result = model.transcribe(filepath, language="en", task="transcribe", verbose=False, word_timestamps=True)
        if not result or 'segments' not in result or not result['segments']:
            raise Exception("No speech detected")

        with processing_lock:
            job_status[job_id] = {'status': 'generating_captions', 'filename': filename}
        
        srt_path = os.path.join(PROCESSED_FOLDER, f"{job_id}_captions.srt")
        
        if is_youtube:
            output_video_filename = f"{job_id}_with_subtitles.mp4"
        else:
            name, ext = os.path.splitext(filename)
            output_video_filename = f"{job_id}_with_subtitles{ext}"
            
        output_video_path = os.path.join(PROCESSED_FOLDER, output_video_filename)

        generate_srt(result["segments"], srt_path)
        
        transcription_text = "\n".join([seg['text'].strip() for seg in result["segments"] if seg['text'].strip()])
        
        # Calculate video duration
        video_duration = result.get('segments', [])[-1].get('end', 0) if result.get('segments') else 0
        
        with processing_lock:
            job_status[job_id] = {'status': 'embedding_subtitles', 'filename': filename}
        
        # Pass caption_settings to overlay_subtitles
        overlay_subtitles(filepath, srt_path, output_video_path, caption_settings=caption_settings)
        
        if os.path.exists(output_video_path):
            logger.info(f"Processing completed for job {job_id}")
            end_time = datetime.now()
            with processing_lock:
                job_info = {
                    'status': 'completed',
                    'filename': filename,
                    'download_url': f"/download/{output_video_filename}",
                    'transcription': transcription_text,
                    'date': start_time.strftime('%Y-%m-%d'),
                    'time': start_time.strftime('%H:%M:%S'),
                    'duration': f"{int(video_duration // 60)}:{int(video_duration % 60):02d}"
                }
                job_status[job_id] = job_info
                user_jobs[job_id] = job_info
                if token:
                    username = verify_token(token)
                    if username and username in users:
                        users[username]['history'].append(job_id)
            if os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists(srt_path):
                os.remove(srt_path)
        else:
            raise Exception("Output video not created")
            
        gc.collect()
        
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

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    video = request.files['video']
    if video.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    # Check file extension for video files only
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp'}
    file_ext = os.path.splitext(video.filename.lower())[1]
    if file_ext not in allowed_extensions:
        return jsonify({'error': 'Only video files are allowed. Supported formats: MP4, AVI, MOV, MKV, WEBM, FLV, WMV, M4V, 3GP'}), 400

    if request.content_length and request.content_length > 100 * 1024 * 1024:
        return jsonify({'error': 'File too large (100MB max)'}), 400

    current_storage = get_directory_size(TEMP_BASE_DIR)
    estimated_size = request.content_length or 0
    if current_storage + estimated_size > TEMP_STORAGE_LIMIT:
        cleanup_old_files()
        if get_directory_size(TEMP_BASE_DIR) + estimated_size > TEMP_STORAGE_LIMIT:
            return jsonify({'error': 'Server storage full'}), 507

    job_id = str(uuid.uuid4())
    filename = f"{job_id}_{video.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        video.save(filepath)
        if not os.path.exists(filepath):
            raise FileNotFoundError("Failed to save uploaded file")
        with processing_lock:
            file_timestamps[job_id] = datetime.now()
            job_status[job_id] = {'status': 'uploaded', 'filename': video.filename}
        
        # Extract caption settings
        caption_settings = None
        if 'captionSettings' in request.form:
            try:
                caption_settings = json.loads(request.form.get('captionSettings', '{}'))
            except Exception as e:
                logger.warning(f"Could not parse caption settings: {e}")
                caption_settings = None
        
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        thread = threading.Thread(
            target=process_video_task, 
            args=(job_id, filepath, video.filename, False, token, caption_settings), 
            daemon=True
        )
        thread.start()

        logger.info(f"Upload successful for job {job_id}")
        return jsonify({'job_id': job_id}), 202
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    with processing_lock:
        if job_id not in job_status:
            return jsonify({'error': 'Job not found or expired'}), 404
        
        status_info = job_status[job_id].copy()
        logger.debug(f"Status check for job {job_id}: {status_info.get('status', 'unknown')}")
        return jsonify(status_info)

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    path = os.path.join(PROCESSED_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found or expired'}), 404
    
    job_id = filename.split('_')[0]
    with processing_lock:
        download_timestamps[job_id] = datetime.now()
    
    original_name = job_status.get(job_id, {}).get('filename', 'video')
    name, ext = os.path.splitext(original_name)
    download_name = f"Scrideo-{name}{ext}"
    
    logger.info(f"File downloaded: {filename} -> {download_name}")
    
    response = send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True, download_name=download_name)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

def download_youtube_video(youtube_url, job_id):
    try:
        temp_video = os.path.join(UPLOAD_FOLDER, f"{job_id}_youtube_video.mp4")
        
        ydl_opts = {
            'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': temp_video,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'http_chunk_size': 10485760,
            'extractaudio': False,
            'noplaylist': True,
        }
        
        logger.info(f"Downloading YouTube video: {youtube_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get('title', 'youtube_video')
            
        if not os.path.exists(temp_video):
            raise Exception("Downloaded file not found")
            
        logger.info(f"YouTube download completed: {title}")
        return temp_video, f"{title}.mp4"
        
    except Exception as e:
        logger.error(f"YouTube download failed: {e}")
        
        try:
            logger.info("Trying fallback download method...")
            temp_video_fallback = os.path.join(UPLOAD_FOLDER, f"{job_id}_youtube_fallback.mp4")
            
            ydl_opts_fallback = {
                'format': 'best',
                'outtmpl': temp_video_fallback,
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                title = info.get('title', 'youtube_video')
                
            if os.path.exists(temp_video_fallback):
                logger.info(f"Fallback download successful: {title}")
                return temp_video_fallback, f"{title}.mp4"
            else:
                raise Exception("Fallback download also failed")
                
        except Exception as fallback_error:
            logger.error(f"Fallback download also failed: {fallback_error}")
            raise Exception(f"Failed to download YouTube video: {str(e)}")
        
@app.route('/transcribe', methods=['POST'])
def transcribe_video_url():
    data = request.get_json()
    youtube_url = data.get('url')
    caption_settings = data.get('captionSettings', None)
    
    if not youtube_url:
        return jsonify({"error": "YouTube URL required"}), 400
    
    current_storage = get_directory_size(TEMP_BASE_DIR)
    if current_storage > TEMP_STORAGE_LIMIT * 0.9:
        cleanup_old_files()
        if get_directory_size(TEMP_BASE_DIR) > TEMP_STORAGE_LIMIT * 0.9:
            return jsonify({"error": "Server storage full"}), 507

    job_id = str(uuid.uuid4())
    
    try:
        with processing_lock:
            job_status[job_id] = {'status': 'downloading', 'filename': 'YouTube Video'}
            file_timestamps[job_id] = datetime.now()
        
        video_path, filename = download_youtube_video(youtube_url, job_id)
        
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        thread = threading.Thread(
            target=process_video_task, 
            args=(job_id, video_path, filename, True, token, caption_settings), 
            daemon=True
        )
        thread.start()

        logger.info(f"YouTube processing started for job {job_id}")
        return jsonify({'job_id': job_id}), 202
        
    except Exception as e:
        logger.error(f"YouTube processing failed: {e}")
        with processing_lock:
            job_status[job_id] = {
                'status': 'failed',
                'filename': 'YouTube Video',
                'error': str(e)
            }
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

@app.route('/storage_info', methods=['GET'])
def storage_info():
    current_usage = get_directory_size(TEMP_BASE_DIR)
    with processing_lock:
        active_jobs = len(job_status)
        downloaded_jobs = len(download_timestamps)
    
    return jsonify({
        'current_usage_mb': round(current_usage / 1024 / 1024, 2),
        'limit_mb': 200,
        'usage_percentage': round((current_usage / TEMP_STORAGE_LIMIT) * 100, 2),
        'active_jobs': active_jobs,
        'downloaded_jobs': downloaded_jobs
    })

@app.route('/system_info', methods=['GET'])
def system_info():
    memory = psutil.virtual_memory()
    
    return jsonify({
        'whisper_models': ["tiny", "base"],
        'current_model': 'adaptive (tiny/base based on memory)',
        'temp_storage_mb': 200,
        'memory_total_gb': round(memory.total / (1024**3), 1),
        'memory_available_gb': round(memory.available / (1024**3), 1),
        'memory_used_gb': round(memory.used / (1024**3), 1),
        'features': [
            'Video file processing only (no audio files)',
            'YouTube video processing',
            'Forced English subtitles',
            'Word-level timestamps',
            'Embedded subtitles in video',
            'Status polling',
            'Download tracking',
            'Adaptive model selection',
            'User authentication with history and profile',
            'Caption customization (size, color, position, alignment)',
            'History search functionality',
            'Date, time, and duration tracking',
            'Browser notifications for completion',
            'Favorite videos',
            'Delete history items',
            'Advanced filtering and search'
        ]
    })

# Cleanup on shutdown
import atexit

def cleanup_on_exit():
    try:
        shutil.rmtree(TEMP_BASE_DIR)
        logger.info(f"Cleaned up temporary directory: {TEMP_BASE_DIR}")
    except:
        pass

atexit.register(cleanup_on_exit)
if __name__ == '__main__':
    if not check_ffmpeg_installation():
        logger.error("FFmpeg not found. Exiting.")
        exit(1)
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')  # KEEP THIS - it's perfect!
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Temporary storage directory: {TEMP_BASE_DIR}")
    logger.info(f"Storage limit: 200MB")
    
    print("🚀 Starting Scrideo Server...")
    print(f"🌐 Access at: http://{host}:{port}")
    print("Press Ctrl+C to stop the server")
    
    app.run(host=host, port=port, debug=debug) 
