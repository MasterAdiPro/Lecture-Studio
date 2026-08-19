# Lecture Studio

Local MVP for turning math/science lectures into a structured Bulgarian explainer-video workflow.

## Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Or double-click `run.bat`.

## Check your system

Before rendering, run the checker from the project folder:

```powershell
.\.venv\Scripts\python.exe check_system.py
```

It checks Python, Manim, Bulgarian TTS, FFmpeg, MiKTeX/pdfLaTeX, `pypdf`, and `imageio-ffmpeg`.

Required setup:

1. Create the environment if needed: `python -m venv .venv`
2. Install the Python tools: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
3. Install MiKTeX for mathematical formula rendering. Enable “Install missing packages on-the-fly”.
4. Start the app with `.\.venv\Scripts\python.exe app.py`.

Manim, Bulgarian `edge-tts`, and FFmpeg are included in `requirements.txt`. The app uses `bg-BG-KalinaNeural` by default and `bg-BG-BorislavNeural` is also available.

Open http://localhost:8765.

The project-local `.venv` contains Manim, `edge-tts`, and an FFmpeg binary from `imageio-ffmpeg`. Bulgarian voices available through the TTS fallback are `bg-BG-KalinaNeural` and `bg-BG-BorislavNeural`. The app accepts PDF, TXT, and Markdown. PDF text extraction uses `pypdf` when available. The UI creates model-specific prompts for ChatGPT and Gemini, requiring a strict JSON scene response containing narration, on-screen text, and executable Manim code. `/api/render` is the integration seam for a production worker that runs Bulgarian TTS, Manim, and FFmpeg.

