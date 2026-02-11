# 🎬 Scrideo – Subtitles, Simplified.

![Flask](https://img.shields.io/badge/Flask-2.3.3-blue?style=flat-square\&logo=flask)
![Whisper](https://img.shields.io/badge/Whisper-OpenAI-green?style=flat-square\&logo=openai)
![FFmpeg](https://img.shields.io/badge/FFmpeg-ASS%20Styling-orange?style=flat-square\&logo=ffmpeg)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-Spaces-yellow?style=flat-square\&logo=huggingface)

> **Automatically generate and embed customizable subtitles into any video.**

Scrideo is a Flask based web application deployed on **Hugging Face Spaces** that uses **OpenAI’s Whisper AI** to automatically transcribe and permanently embed styled subtitles into videos.

Upload a file or paste a YouTube URL — get back a professionally captioned video.

🔗 **Live Demo:** *https://huggingface.co/spaces/hafsakhan09090/scrideo*

---

# 📋 Overview

Scrideo allows users to:

* Upload a video file
* Paste a YouTube URL
* Automatically generate subtitles using Whisper
* Customize styling (font, color, position, outline, shadow, etc.)
* Burn captions directly into the video
* Download the final captioned video

No external subtitle files — captions are permanently embedded.

---

# 📁 Project Structure

```
scrideo/
├── app.py             # Flask backend + Whisper + FFmpeg processing
├── index.html         # Single page frontend (TailwindCSS)
├── requirements.txt   # Python dependencies
└── README.md          # Documentation
```

That’s it. Everything runs from these 4 files.

---

# 💻 Local Development

## Install FFmpeg

**macOS**

```bash
brew install ffmpeg
```

**Ubuntu / Debian**

```bash
sudo apt install ffmpeg
```

---

## Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## Run Application

```bash
python app.py
```

Open:

```
http://localhost:7860
```

---

# 🔧 Core Components

## 🧠 app.py

* Flask server
* JWT authentication
* Whisper transcription
* YouTube downloading (yt-dlp)
* ASS subtitle styling engine
* FFmpeg video processing
* Auto cleanup system

---

## 🎨 index.html

* Responsive single-page UI
* TailwindCSS styling
* Real-time caption preview
* Authentication modal
* Video preview player
* History & favorites management

---

## 📦 requirements.txt

```txt
Flask==2.3.3
flask-cors==4.0.0
yt-dlp==2023.11.16
openai-whisper==20231117
torch==2.0.1
numpy==1.24.3
psutil==5.9.6
PyJWT==2.8.0
gunicorn==21.2.0
```

---

# 🎨 Caption Styling (ASS Format)

Scrideo uses **Advanced SubStation Alpha (ASS)** for professional subtitle styling.

### Available Customization

| Setting    | Options                                                                                                  |
| ---------- | -------------------------------------------------------------------------------------------------------- |
| Font       | Arial, Helvetica, Times, Courier, Verdana, Georgia, Impact, Comic Sans, Trebuchet, Arial Black, Palatino |
| Style      | Normal, Bold, Italic, Bold Italic                                                                        |
| Size       | 12px – 32px                                                                                              |
| Color      | White, Yellow, Cyan, Lime, Orange, Red, Pink, Purple, Light Blue, Light Green                            |
| Background | None, Black, Dark Gray, Semi-transparent, Dark Blue, Dark Red, Dark Green, Dark Purple, Navy, Charcoal   |
| Position   | Bottom, Top, Bottom-Left, Bottom-Right, Top-Left, Top-Right, Middle                                      |
| Alignment  | Left, Center, Right                                                                                      |
| Outline    | None, Thin, Medium, Thick, Extra Thick                                                                   |
| Shadow     | None, Subtle, Medium, Large, Extra Large                                                                 |

✨ **50+ styling combinations**

Preview changes instantly before processing.

---

# 🔌 API Reference

| Endpoint                     | Method | Description              |
| ---------------------------- | ------ | ------------------------ |
| `/`                          | GET    | Serve frontend           |
| `/upload`                    | POST   | Upload video             |
| `/transcribe`                | POST   | Process YouTube URL      |
| `/status/<job_id>`           | GET    | Check job status         |
| `/download/<filename>`       | GET    | Download processed video |
| `/signup`                    | POST   | Create account           |
| `/login`                     | POST   | Login                    |
| `/profile`                   | GET    | Get user history         |
| `/history/<job_id>/favorite` | POST   | Toggle favorite          |
| `/history/<job_id>`          | DELETE | Delete history           |
| `/health`                    | GET    | System health check      |

---

# 🧠 How It Works

1️⃣ User uploads video or provides YouTube URL

2️⃣ Whisper generates transcription with timestamps

3️⃣ Styling settings converted to ASS format

4️⃣ FFmpeg burns subtitles into video frames

5️⃣ User downloads permanently captioned video

Temporary files auto-delete after 2 hours.

---

# ⚡ Performance (Hugging Face)

| Component        | Requirement                     |
| ---------------- | ------------------------------- |
| RAM              | Minimum 8GB                     |
| Storage          | 500MB temp limit                |
| Processing Speed | ~30 sec per 1 min of video      |
| Accuracy         | 95%+ (English)                  |
| GPU              | Auto-detected (fallback to CPU) |

---

# 🐛 Common Issues & Fixes

### ❌ Whisper Not Available

**Cause:** Insufficient RAM
**Fix:** Upgrade to 8GB plan
**Check:** `/health` endpoint → `whisper_available: true`

---

### ❌ FFmpeg Not Found

**Cause:** Missing installation
**Fix:** Ensure Docker image includes FFmpeg
**Verify:**

```bash
ffmpeg -version
```

---

### ❌ Subtitle Colors Incorrect

**Cause:** Wrong ASS opacity format
**Fix:** Format must be `AABBGGRR`

* `00` = fully opaque
* `FF` = transparent

---

### ❌ Job Stuck at 0%

**Cause:** Large/corrupt file
**Fix:**

* Keep videos under 500MB
* Use MP4, MOV, AVI, MKV, WEBM

---

# 📊 Resource Management

Auto cleanup runs every 30 minutes:

* Removes jobs older than 2 hours
* Keeps last 5 completed jobs
* Deletes associated video files
* User history resets on Space restart

---

# 🔐 Authentication

* JWT based authentication
* SHA256 password hashing
* User history stored in memory
* Non persistent storage (resets on restart)

---

# 📱 Browser Support

* Chrome / Edge (latest)
* Firefox (latest)
* Safari (latest)
* Mobile browsers (responsive)
  
---

# 📄 License

MIT License

Free for personal and commercial use.

---

# 👩‍💻 Author

**Hafsa Khan**

GitHub: [https://github.com/hafsakhan09090](https://github.com/hafsakhan09090) 

Email: [hafsakhan09090@gmail.com](mailto:hafsakhan09090@gmail.com)

---

<div align="center">
Built with Flask, Whisper & ❤️  
</div>
