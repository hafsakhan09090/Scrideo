# Scrideo 

**Scrideo** is a powerful web application that uses OpenAI's Whisper API to generate highly accurate transcripts from YouTube videos or local media files. 
This project was developed to tackle the "digital sound barrier," making video content more accessible for everyone.

Scrideo provides a simple, clean, and powerful solution. It offers two methods for transcription to ensure reliability:

1.  **YouTube URL:** Paste a link to a YouTube video.
2.  **Local File Upload:** Upload your own audio or video file directly from your computer.

---

### Key Features
* **High-Accuracy Transcription:** Powered by OpenAI's `whisper-1` model.
* **Dual Input Methods:** Supports both YouTube URLs and local file uploads.
* **Simple & Modern UI:** A clean, intuitive, and responsive user interface.
* **Secure:** Built with security in mind, ensuring API keys are kept safe and private.

---

## Tech Stack 

* **Frontend:** HTML, Tailwind CSS, JavaScript
* **Backend:** Python with the Flask framework
* **Core AI:** OpenAI Whisper API
* **YouTube Downloader:** `yt-dlp`
* **Key Libraries:** `requests`, `python-dotenv`

---

## Local Setup & Installation ⚙️

To run this project on your local machine, follow these steps.

### 1. Prerequisites
* Python 3.7+ installed on your system.
* An OpenAI API key.

### 2. Clone the Repository
```bash
git clone [https://github.com/your-username/Scrideo.git](https://github.com/your-username/Scrideo.git)
cd Scrideo
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

Create a new file in the root of the project folder named exactly .env.

Open the .env file and add the following line, replacing the placeholder with your actual OpenAI API key:
OPENAI_API_KEY="sk-YourSecretApiKeyGoesHere"

NOTE: The .gitignore file is already configured to keep this file private, so it will not be uploaded.

To run the application :
python app.py
