from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import cgi, json, mimetypes, os, re, subprocess, tempfile, uuid, sys
import shutil

ROOT = Path(__file__).parent
PUBLIC = ROOT / 'public'
OUTPUTS = ROOT / 'outputs'
OUTPUTS.mkdir(exist_ok=True)
VENV_BIN = ROOT / '.venv' / ('Scripts' if os.name == 'nt' else 'bin')
if VENV_BIN.exists():
    os.environ['PATH'] = str(VENV_BIN) + os.pathsep + os.environ.get('PATH', '')
if os.name == 'nt':
    miktex_bin = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'MiKTeX' / 'miktex' / 'bin' / 'x64'
    if miktex_bin.exists():
        os.environ['PATH'] = str(miktex_bin) + os.pathsep + os.environ.get('PATH', '')
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ.setdefault('IMAGEIO_FFMPEG_EXE', ffmpeg_exe)
    os.environ['PATH'] = str(Path(ffmpeg_exe).parent) + os.pathsep + os.environ.get('PATH', '')
except Exception:
    pass

def extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(data))
        return '\n'.join(page.extract_text() or '' for page in reader.pages)
    except Exception:
        return ''

def analyze(filename, text, diagram_choice='auto'):
    lower = text.lower()
    diagram_words = ['figure', 'diagram', 'graph', 'chart', 'рисунк', 'диаграм', 'график', 'схем', 'фигура']
    detected_diagrams = any(w in lower for w in diagram_words) or bool(re.search(r'\b(fig\.?|figure)\s*\d+', lower))
    has_diagrams = detected_diagrams if diagram_choice == 'auto' else diagram_choice == 'yes'
    equations = len(re.findall(r'([A-Za-z]\s*[=≈≤≥]|\\frac|∫|∑|π|²|³)', text))
    sections = [s.strip() for s in re.split(r'\n{2,}|(?=^#{1,3}\s)', text, flags=re.M) if s.strip()]
    title = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
    if sections and len(sections[0]) < 120:
        title = re.sub(r'^#+\s*', '', sections[0].splitlines()[0]).strip() or title
    return {'filename': filename, 'title': title, 'characters': len(text), 'words': len(text.split()),
            'pages': max(1, text.count('\f') + 1), 'sections': min(max(len(sections), 1), 12),
            'has_diagrams': has_diagrams, 'detected_diagrams': detected_diagrams, 'diagram_choice': diagram_choice, 'equations': equations, 'text': text[:24000]}

def prompts(analysis):
    title = analysis['title']
    context = analysis['text'][:10000]
    manual = analysis.get('diagram_choice') == 'manual'
    base = f'''LECTURE TITLE: {title}\nSOURCE LANGUAGE: Bulgarian or English (preserve the source language)\nDIAGRAMS: {"MANUAL UPLOADS PROVIDED" if manual else "NONE"}\nIMPORTANT: The block between BEGIN and END is a VERBATIM COPY of the lecture. Treat it as the source of truth. Do not summarize, rewrite, correct, simplify, reorder, or silently drop any formula, symbol, subscript, superscript, sign, unit, or definition.\nMATH RULE: For every formula, first preserve the original expression exactly in source_formula, then provide an equivalent LaTeX form in latex_formula. Never guess an unclear symbol; mark it as [UNCLEAR] for review.\n\nBEGIN VERBATIM LECTURE TEXT\n{context}\nEND VERBATIM LECTURE TEXT'''
    schema = '''Return ONLY valid JSON with this shape:\n{"title":"...","language":"bg","coverage_map":[{"lecture_section":"...","covered_in_scenes":[1,2],"notes":"..."}],"scenes":[{"id":1,"duration":8,"narration":"...","visual_goal":"...","source_formula":"...","latex_formula":"...","diagram_instruction":"...","manim_code":"...","on_screen_text":"..."}]}\nRules: cover the ENTIRE lecture, not just its main idea. First map every section, definition, theorem, derivation, formula, worked example, diagram reference, and conclusion to one or more scenes in coverage_map. Create as many scenes as needed; do not force a short scene count or omit details to fit a target duration. Every important formula must be narrated and shown. Make the first scene an intriguing question or visual hook; give every scene one clear idea, one visual reveal, and a reason to keep watching; alternate calm explanation with satisfying motion; use visual metaphors, transformations, zooms, and geometric intuition instead of walls of text; keep on-screen text short. Use Manim Community Edition and make code executable as a standalone scene. Narration must be natural Bulgarian when the source is Bulgarian. Copy formulas exactly into source_formula, then convert them equivalently into latex_formula. Use latex_formula in on_screen_text and Manim MathTex/Tex; escape backslashes correctly for JSON. The app will pass the model response directly to the renderer. If manual diagrams are provided, write a concrete diagram_instruction naming the asset, labels, relationships, camera movement, and animation. Do not invent missing lecture content.'''
    chat = f'''You are an expert math educator, Bulgarian scriptwriter, and Manim director. Turn the lecture below into a rigorous, visually clear explainer in a modern 3Blue1Brown-inspired style (original visuals, not a copy). {schema}\n\n{base}'''
    gemini = f'''Act as a multimodal science animator and Bulgarian TTS script editor. Analyze the lecture and produce a complete scene plan and executable Manim code. Prefer visual intuition, precise symbols, and short narration beats. {schema}\n\n{base}'''
    return {'chatgpt': chat, 'gemini': gemini}

class Handler(BaseHTTPRequestHandler):
    def _send(self, status=200, content_type='application/json'):
        self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Access-Control-Allow-Origin','*'); self.end_headers()
    def do_GET(self):
        if self.path.startswith('/api/job/'):
            job_id = self.path.split('/')[-1]
            status = ROOT / 'work' / 'jobs' / job_id / 'status.json'
            self._send(200 if status.exists() else 404); self.wfile.write(status.read_bytes() if status.exists() else b'{}'); return
        if self.path.startswith('/outputs/'):
            file = OUTPUTS / Path(self.path[len('/outputs/'):]).name
            if file.exists(): self._send(200, mimetypes.guess_type(str(file))[0] or 'application/octet-stream'); self.wfile.write(file.read_bytes()); return
            self._send(404); self.wfile.write(b'Not found'); return
        if self.path == '/api/status':
            checks = {'Manim': bool(shutil.which('manim')), 'Bulgarian TTS': bool(shutil.which('edge-tts') or shutil.which('tts')), 'FFmpeg': bool(shutil.which('ffmpeg') or os.environ.get('IMAGEIO_FFMPEG_EXE'))}
            self._send(); self.wfile.write(json.dumps(checks).encode()); return
        file = PUBLIC / ('index.html' if self.path in ('/', '') else self.path.lstrip('/'))
        if file.exists() and file.is_file():
            self._send(200, mimetypes.guess_type(str(file))[0] or 'text/plain'); self.wfile.write(file.read_bytes()); return
        self._send(404); self.wfile.write(b'Not found')
    def do_POST(self):
        if self.path == '/api/analyze':
            ctype, pdict = cgi.parse_header(self.headers.get('content-type',''))
            filename, text = 'lecture.txt', ''
            diagram_files = []
            if ctype == 'multipart/form-data':
                pdict['boundary'] = pdict['boundary'].encode(); form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST','CONTENT_TYPE':self.headers['content-type']})
                item = form['file']; filename = item.filename or filename; data = item.file.read()
                if 'diagrams' in form:
                    diagram_items = form['diagrams'] if isinstance(form['diagrams'], list) else [form['diagrams']]
                    diagram_files = [x.filename for x in diagram_items if x.filename]
                text = extract_pdf(data) if filename.lower().endswith('.pdf') else data.decode('utf-8', errors='ignore')
            else:
                n = int(self.headers.get('content-length','0')); payload = json.loads(self.rfile.read(n) or '{}'); filename = payload.get('filename', filename); text = payload.get('text','')
            diagram_choice = payload.get('diagram_choice', 'auto') if ctype != 'multipart/form-data' else 'auto'
            if ctype == 'multipart/form-data' and 'diagram_choice' in form: diagram_choice = form['diagram_choice'].value
            result = analyze(filename, text, diagram_choice); result['diagram_files'] = diagram_files; result['prompts'] = prompts(result); self._send(); self.wfile.write(json.dumps(result, ensure_ascii=False).encode()); return
        if self.path == '/api/render':
            n = int(self.headers.get('content-length','0')); payload = json.loads(self.rfile.read(n) or '{}')
            job_id = str(uuid.uuid4())[:8]; job_dir = ROOT / 'work' / 'jobs' / job_id; job_dir.mkdir(parents=True, exist_ok=True)
            job = {'id': job_id, 'response': json.loads(payload.get('model_response', '{}')), 'language': payload.get('language','bg'), 'target_minutes': payload.get('target_minutes', 0)}
            (job_dir / 'job.json').write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8'); (job_dir / 'status.json').write_text(json.dumps({'status':'queued','message':'Render queued'}), encoding='utf-8')
            subprocess.Popen([sys.executable, str(ROOT / 'render_pipeline.py'), str(job_dir / 'job.json')], cwd=ROOT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._send(202); self.wfile.write(json.dumps({'id':job_id,'status':'queued'}, ensure_ascii=False).encode()); return
        self._send(404); self.wfile.write(b'Not found')

if __name__ == '__main__':
    print('Lecture Studio running at http://localhost:8765')
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()

