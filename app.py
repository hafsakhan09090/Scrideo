import os
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import openai
from dotenv import load_dotenv
import yt_dlp

load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        raise ValueError("OpenAI API key not found in .env file.")
except Exception as e:
    print(f"Error initializing OpenAI API: {e}")

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/transcribe', methods=['POST'])
def transcribe_video_url():
    data = request.get_json()
    youtube_url = data.get('url')
    if not youtube_url:
        return jsonify({"error": "YouTube URL is required"}), 400

    try:
        transcript = transcribe_from_youtube(url=youtube_url)
        return jsonify({"transcript": transcript})
    except Exception as e:
        print(f"A critical error occurred: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/transcribe_file', methods=['POST'])
def transcribe_video_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        try:
            transcript = transcribe_from_local_file(filepath=filepath)
            return jsonify({"transcript": transcript})
        except Exception as e:
            print(f"A critical error occurred: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

def transcribe_from_youtube(url):
    temp_audio_file = os.path.join(UPLOAD_FOLDER, "temp_yt_audio.m4a")
    try:
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]',
            'outtmpl': temp_audio_file,
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return transcribe_audio_file(temp_audio_file)
    finally:
        if os.path.exists(temp_audio_file):
            os.remove(temp_audio_file)

def transcribe_from_local_file(filepath):
    return transcribe_audio_file(filepath)

def transcribe_audio_file(filepath):
    """A central function to handle the OpenAI Whisper API call."""
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb > 25:
        raise ValueError(f"File ({file_size_mb:.2f} MB) exceeds the 25 MB API limit.")
        
    with open(filepath, "rb") as audio_file:
        print(f"Transcribing {filepath} with OpenAI Whisper...")
        transcript_object = openai.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        print("Transcription complete.")
    return transcript_object.text

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)