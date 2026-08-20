## 📖 Overview

**GapGPT Voice Transcriber** is a Python desktop application that records audio from your microphone, transcribes it using OpenAI-compatible Whisper models, and optionally sends the transcript to an LLM to produce cleaner, more articulated text.

It features a modern dark-themed GUI, session management, and seamless integration with the [GapGPT API](https://gapgpt.app).

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎙️ **Real-time Recording** | Capture audio from your microphone with configurable sample rate and channels |
| 📝 **Speech-to-Text** | Transcribe audio using Whisper models via the GapGPT API |
| 🤖 **AI Articulation** | Optional LLM-powered refinement for grammatically correct, well-formatted text |
| 💾 **Session Management** | Save, review, copy, and delete transcript sessions |
| 🎨 **Modern UI** | Catppuccin-inspired dark theme with custom-styled buttons and inputs |
| ⚙️ **Configurable** | Adjust API keys, models, audio settings, and articulation toggle directly in-app |
| 📄 **Export** | Transcripts saved as `.txt` files with timestamps |
| 🛑 **Cancel Anytime** | Cancel recording or transcription mid-process |

---

## 📂 Project Structure
```

voicer/ ├── gapgpt_transcriber.py # Main application (~1100 lines) ├── run_voice_converter.bat # Windows launcher script ├── .env # Configuration & API keys ├── README_EN.md # English documentation ├── README_FA.md # مستندات فارسی ├── recordings/ # Raw .wav audio files ├── transcripts/ # Saved .txt transcript files └── venv/ # Python virtual environment

````javascript

---

## 🛠️ Prerequisites

- **Python 3.8+**
- **Windows** (launcher script is `.bat`; the app itself is cross-platform)
- A microphone
- An API key from [GapGPT](https://gapgpt.app)

---

## 📦 Installation

### 1. Set up the virtual environment

```bash
python -m venv venv
venv\Scripts\activate
````

### 2. Install dependencies

```bash
pip install numpy requests sounddevice python-dotenv
```

---

## ⚙️ Configuration

### API Key Setup

Create or edit the `.env` file in the project root:

```env
GAPGPT_API_KEY="your-api-key-here"
GAPGPT_BASE_URL="https://api.gapgpt.app/v1"
GAPGPT_TRANSCRIPTION_MODEL="gapgpt/whisper-1"
GAPGPT_ARTICULATION_MODEL="gapgpt-qwen-3.6"
ENABLE_ARTICULATION="true"
AUDIO_SAMPLE_RATE="16000"
AUDIO_CHANNELS="1"
```

> __Security Note:__ Never commit your `.env` file with a real API key to a public repository.

### Configuration Options

| Setting | Default | Description | |---|---|---| | `GAPGPT_API_KEY` | *(required)* | Your GapGPT API authentication key | | `GAPGPT_BASE_URL` | `https://api.gapgpt.app/v1` | API endpoint base URL | | `GAPGPT_TRANSCRIPTION_MODEL` | `gapgpt/whisper-1` | Whisper model for speech-to-text | | `GAPGPT_ARTICULATION_MODEL` | `gapgpt-qwen-3.6` | LLM for text refinement | | `ENABLE_ARTICULATION` | `true` | Run LLM refinement after transcription | | `AUDIO_SAMPLE_RATE` | `16000` | Microphone sample rate in Hz | | `AUDIO_CHANNELS` | `1` | Audio channels (1 = mono, 2 = stereo) |

> 💡 All settings can also be modified directly through the app's __Settings__ panel.

---

## 🚀 Usage

### Launch the App (Windows)

Double-click `run_voice_converter.bat` or run:

```bash
.\run_voice_converter.bat
```

### Manual Launch

```bash
venv\Scripts\activate.bat
python gapgpt_transcriber.py
```

### Step-by-Step Guide

1. __Set your API key__ — Enter it in the Settings panel or `.env` file
2. __Click "Start Recording"__ — Speak into your microphone
3. __Click "Stop"__ — Transcription begins automatically
4. __Optional:__ Toggle "Enable Articulation" for LLM-powered refinement
5. __Review transcripts__ — They appear in the lower panel
6. __Copy or delete__ individual transcripts using the buttons on each card
7. __"Clear All"__ — Remove all saved transcripts at once

---

## 🔌 API Endpoints Used

The app communicates with the GapGPT API (OpenAI-compatible):

| Endpoint | Method | Purpose | |---|---|---| | `/audio/transcriptions` | `POST` | Transcribe audio file to text | | `/chat/completions` | `POST` | Send text to LLM for refinement |

### Request Example — Transcription

```bash
POST https://api.gapgpt.app/v1/audio/transcriptions
Headers:
  Authorization: Bearer <API_KEY>
  Content-Type: multipart/form-data

Body:
  model: "gapgpt/whisper-1"
  file: recording_20250101_120000.wav
  language: "fa"
```

### Request Example — Articulation

```bash
POST https://api.gapgpt.app/v1/chat/completions
Headers:
  Authorization: Bearer <API_KEY>
  Content-Type: application/json

Body:
{
  "model": "gapgpt-qwen-3.6",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant. Your task is to refine transcribed speech text. Produce grammatically correct, well-formatted text while preserving the original meaning. Keep it concise and natural."
    },
    {
      "role": "user",
      "content": "<raw_transcript_text>"
    }
  ]
}
```

---

## 🖥️ UI Components

```javascript
┌─────────────────────────────────────────────────┐
│           GapGPT Voice Transcriber               │
├─────────────────────────────────────────────────┤
│ [Settings ▼]  ← Collapsible settings panel      │
├─────────────────────────────────────────────────┤
│ [Start Recording] [Stop] [Cancel] [Export]      │
│ [Enable Articulation ☑]   [Clear All]           │
│                                                  │
│ Status: Transcription complete                  │
│ Last File: recordings/recording_20250101_1200.wav│
├─────────────────────────────────────────────────┤
│                 Transcripts                      │
│ ┌─────────────────────────────────────────────┐ │
│ │ 2025-01-01 12:00:30              [Copy] [×] │ │
│ │ "Hello, this is a test transcription..."    │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ 2025-01-01 12:05:15              [Copy] [×] │ │
│ │ "Articulated/refined version of the text..." │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## 🔧 Technical Details

### Recording Pipeline

```javascript
Microphone → sounddevice → numpy arrays → queue → wav file → API
```

1. Audio is captured via `sounddevice.InputStream` at the configured sample rate
2. Each audio chunk is pushed into a thread-safe `queue.Queue`
3. The main thread drains the queue and accumulates chunks in a list
4. On stop, chunks are concatenated and saved as a `.wav` file
5. The `.wav` file is uploaded to the transcription API

### Transcription & Articulation Flow

```javascript
Stop Recording → Save WAV → Transcribe (Whisper) → [Articulate (LLM)?] → Save & Display
```

- __Transcription__ runs synchronously — blocks until the API responds
- __Articulation__ runs in a separate thread — doesn't block the UI
- Both phases can be cancelled mid-process

### File Naming Convention

| Type | Pattern | Example | |---|---|---| | Audio recordings | `recording_YYYYMMDD_HHMMSS.wav` | `recording_20250101_120000.wav` | | Transcripts | `transcript_YYYYMMDD_HHMMSS.txt` | `transcript_20250101_120000.txt` |

---

## 🎨 Color Scheme

The app uses a __Catppuccin Mocha__ inspired dark theme:

| Color | Hex | Usage | |---|---|---| | Background | `#1e1e2e` | Main window background | | Surface | `#313244` | Panels and cards | | Surface Light | `#45475a` | Input fields | | Primary | `#89b4fa` | Buttons, accents | | Secondary | `#a6e3a1` | Success states | | Danger | `#f38ba8` | Error / delete actions |

---

## 🐛 Troubleshooting

| Issue | Solution | |---|---| | `"Failed to start recording"` | Check that your microphone is connected and not in use by another app | | `"No audio captured"` | Try lowering the `AUDIO_SAMPLE_RATE` or checking microphone permissions | | `"Missing API Key"` | Enter your API key in the Settings panel or `.env` file | | __Silent API errors__ | Check the `error_var` display at the bottom of the app | | Transcription works but articulation doesn't | Verify `ENABLE_ARTICULATION=true` and that the articulation model name is correct |

---

## 📝 Notes

- The app is designed primarily for __Windows__ but the Python code is cross-platform
- Transcripts are stored as plain `.txt` files for easy portability
- The articulation step requires an active internet connection (LLM API call)
- API keys are stored in `.env` — never share this file publicly

---

## 📄 License

This project is licensed under the __MIT License__. See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- __[GapGPT](https://gapgpt.app)__ — AI API platform powering transcription and articulation
- __[Whisper](https://github.com/openai/whisper)__ — OpenAI's speech recognition model
- __Catppuccin__ — Color palette inspiration

---

*Built with ❤️ using Python, tkinter, and the GapGPT API* '''
