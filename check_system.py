"""Check the local tools required by Lecture Studio."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).parent

def find_tool(name, extra=None):
    try:
        if Path(name).exists():
            return str(Path(name))
    except OSError:
        return None
    found = shutil.which(name)
    if found:
        return found
    for path in extra or []:
        if Path(path).exists():
            return str(Path(path))
    return None

def version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        line = (result.stdout or result.stderr).splitlines()
        return line[0].strip() if line else 'installed'
    except Exception as exc:
        return f'found, version unavailable ({exc.__class__.__name__})'

def main():
    venv = ROOT / '.venv' / ('Scripts' if os.name == 'nt' else 'bin')
    miktex = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'MiKTeX' / 'miktex' / 'bin' / 'x64'
    checks = [
        ('Python', [sys.executable], True),
        ('Manim', [str(venv / 'manim.exe'), str(venv / 'manim')], True),
        ('Bulgarian TTS', [str(venv / 'edge-tts.exe'), str(venv / 'edge-tts'), 'tts'], True),
        ('FFmpeg', ['ffmpeg'], True),
        ('MiKTeX / pdflatex', [str(miktex / 'pdflatex.exe'), 'pdflatex'], False),
    ]
    ok = True
    print('Lecture Studio system check\n')
    for label, candidates, required in checks:
        tool = next((find_tool(c) for c in candidates if find_tool(c)), None)
        if label == 'FFmpeg' and not tool:
            try:
                import imageio_ffmpeg
                tool = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
        if label == 'Python':
            tool = sys.executable
        if tool:
            print(f'[OK]   {label}: {tool}')
            if label in ('Python', 'Manim', 'Bulgarian TTS', 'MiKTeX / pdflatex'):
                print(f'       {version([tool, "--version"])}')
        else:
            note = ' (required)' if required else ' (recommended for math formulas)'
            print(f'[MISS] {label}{note}')
            ok = ok and not required
    for package in ('pypdf', 'imageio_ffmpeg'):
        installed = importlib.util.find_spec(package) is not None
        print(f'[{'OK' if installed else 'MISS'}]   Python package: {package}')
        ok = ok and installed
    print('\nResult:', 'READY' if ok else 'NOT READY')
    print('Note: Bulgarian TTS uses edge-tts voices bg-BG-KalinaNeural or bg-BG-BorislavNeural.')
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main())

