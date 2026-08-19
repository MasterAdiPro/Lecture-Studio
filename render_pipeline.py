import asyncio, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).parent
VENV_BIN = ROOT / '.venv' / ('Scripts' if os.name == 'nt' else 'bin')
if VENV_BIN.exists():
    os.environ['PATH'] = str(VENV_BIN) + os.pathsep + os.environ.get('PATH', '')
if os.name == 'nt':
    miktex_bin = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'MiKTeX' / 'miktex' / 'bin' / 'x64'
    if miktex_bin.exists():
        os.environ['PATH'] = str(miktex_bin) + os.pathsep + os.environ.get('PATH', '')

async def make_voice(text, out, voice):
    import edge_tts
    await edge_tts.Communicate(text or ' ', voice).save(str(out))

def clean_display(value):
    value = str(value or '')
    value = re.sub(r'\\text\{([^{}]*)\}', r'\1', value)
    value = value.replace('\\;', ' ').replace('\\,', ' ').replace('\\!', '')
    return value.replace('\\n', ' ').strip()

def formula_to_text(value):
    value = str(value or '')
    matrix = re.search(r'\\begin\{(?:p|b)?matrix\}(.*?)\\end\{(?:p|b)?matrix\}', value, re.S)
    if matrix:
        rows = matrix.group(1).replace('\\\\', ';').replace('&', '  ')
        return '[ ' + rows.strip() + ' ]'
    value = re.sub(r'\\text\{([^{}]*)\}', r'\1', value)
    value = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', r'(\1)/(\2)', value)
    replacements = {'\\deg':'deg ', '\\pi':'π', '\\theta':'θ', '\\alpha':'α', '\\beta':'β', '\\le':'≤', '\\ge':'≥', '\\cdot':'·', '\\infty':'∞'}
    for source, target in replacements.items(): value = value.replace(source, target)
    value = value.replace('\\;', ' ').replace('\\,', ' ').replace('\\!', '').replace('\\ ', ' ')
    value = re.sub(r'\\[a-zA-Z]+', '', value)
    return value.replace('{', '(').replace('}', ')').strip()

def short_lines(value, limit=52, max_lines=2):
    words = clean_display(value).split()
    lines, line = [], ''
    for word in words:
        if line and len(line) + len(word) + 1 > limit:
            lines.append(line); line = word
        else:
            line = (line + ' ' + word).strip()
    if line: lines.append(line)
    return lines[:max_lines] or ['']

def run(job_file):
    job = json.loads(Path(job_file).read_text(encoding='utf-8'))
    job_dir = Path(job_file).parent
    scenes = job['response'].get('scenes', [])
    status_file = job_dir / 'status.json'
    def status(value, message, **extra):
        status_file.write_text(json.dumps({'status': value, 'message': message, **extra}, ensure_ascii=False), encoding='utf-8')
    try:
        status('running', 'Generating Bulgarian narration…')
        voice = 'bg-BG-KalinaNeural' if job.get('language', 'bg') == 'bg' else 'en-US-AriaNeural'
        audio = []
        for i, scene in enumerate(scenes, 1):
            out = job_dir / f'audio_{i:03d}.mp3'
            asyncio.run(make_voice(scene.get('narration', ''), out, voice))
            audio.append(out)
        status('running', 'Rendering Manim animation…')
        target = float(job.get('target_minutes', 0) or 0) * 60
        raw_total = sum(max(2, float(s.get('duration', 6))) for s in scenes)
        time_scale = target / raw_total if target > 0 else 1
        tex_path = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'MiKTeX' / 'miktex' / 'bin' / 'x64' / 'pdflatex.exe'
        tex_config = f'config.tex_compiler = {str(tex_path)!r}\n' if tex_path.exists() else ''
        code = f'''from manim import *\n{tex_config}\nclass LectureScene(Scene):\n    def construct(self):\n        self.camera.background_color = "#F4F1EB"\n'''
        if not scenes:
            raise ValueError('The response contains no scenes')
        for i, scene in enumerate(scenes, 1):
            visual = str(scene.get('visual_goal', f'Scene {i}'))[:240]
            diagram = str(scene.get('diagram_instruction', ''))[:300]
            visual_lower = (visual + ' ' + diagram).lower()
            onscreen = str(scene.get('on_screen_text', ''))[:220]
            formula = str(scene.get('latex_formula', '')).strip()
            title_source = onscreen or visual
            if '\\begin{' in title_source or '\\deg' in title_source or title_source.startswith('\\'):
                title_source = 'Visualizing the key relationship'
            title_lines = short_lines(title_source, limit=48, max_lines=2)
            title_text = '\\n'.join(title_lines)
            code += f'        # Scene {i}: {visual!r}\n'
            code += f'        title = Text({title_text!r}, font_size=25, line_spacing=0.85, color="#20221F").to_edge(UP, buff=0.35)\n'
            code += '        self.play(FadeIn(title))\n'
            if any(w in visual_lower for w in ['matrix', 'матриц']):
                code += '        matrix = Text("[ 0  1  0  1 ]\\n[ 1  0  1  0 ]\\n[ 0  1  0  1 ]\\n[ 1  0  1  0 ]", font_size=25, line_spacing=0.8, color="#5A72FF"); self.play(FadeIn(matrix))\n'
            elif any(w in visual_lower for w in ['bipartite', 'двуделен', 'двудел', 'two groups', 'две груп']) or ('group' in visual_lower and 'vertex' in visual_lower):
                code += '        left = VGroup(*[Dot(LEFT*2+UP*(j-1), color="#5A72FF") for j in range(3)]); right = VGroup(*[Dot(RIGHT*2+UP*(j-1), color="#FF8F59") for j in range(3)]); edges = VGroup(*[Line(a.get_center(), b.get_center(), color="#AAA69D") for a in left for b in right]); self.play(Create(edges), FadeIn(left), FadeIn(right))\n'
            elif any(w in visual_lower for w in ['path', 'cycle', 'route', 'път', 'цикъл', 'маршрут']):
                code += '        nodes = [Dot(2.2*rotate_vector(UP, k*TAU/6), color="#5A72FF") for k in range(6)]; ring = VGroup(*[Line(nodes[k].get_center(), nodes[(k+1)%6].get_center(), color="#FF8F59") for k in range(6)]); self.play(Create(ring), *[FadeIn(n) for n in nodes])\n'
            elif any(w in visual_lower for w in ['cube', 'куб']):
                code += '        front = Square(2.2, color="#5A72FF").shift(DOWN*0.3); back = front.copy().shift(UP*0.8+RIGHT*0.8); connectors = VGroup(*[Line(front.get_vertices()[k], back.get_vertices()[k], color="#FF8F59") for k in range(4)]); self.play(Create(front), Create(back), Create(connectors))\n'
            elif any(w in visual_lower for w in ['graph', 'parabola', 'function', 'axis', 'график', 'парабол', 'функци', 'ос ']):
                code += '        plane = NumberPlane(x_range=[-6,6,1], y_range=[-3,5,1], background_line_style={"stroke_color": "#C8C3B9", "stroke_opacity": 0.45})\n        curve = plane.plot(lambda x: 0.18*x**2, color="#FF8F59")\n        self.play(Create(plane), Create(curve))\n'
            elif any(w in visual_lower for w in ['circle', 'круг', 'окръж', 'сфера']):
                code += '        shape = Circle(radius=1.6, color="#5A72FF"); self.play(Create(shape))\n'
            elif any(w in visual_lower for w in ['triangle', 'триъгъл', 'геометр']):
                code += '        shape = Polygon(LEFT*2+DOWN, RIGHT*2+DOWN, UP*1.5, color="#FF8F59"); self.play(Create(shape))\n'
            elif diagram:
                code += '        shape = VGroup(Arrow(LEFT*2, RIGHT*2, color="#5A72FF"), Dot(ORIGIN, color="#FF8F59")); self.play(Create(shape))\n'
            if formula:
                if re.search(r'[А-Яа-яЁё]', formula):
                    code += f'        formula = Text({clean_display(formula)!r}, font_size=26, color="#5A72FF").scale_to_fit_width(10.5).to_edge(DOWN, buff=0.55)\n        self.play(Write(formula))\n'
                else:
                    code += f'        formula = Text({formula_to_text(formula)!r}, font_size=26, color="#5A72FF").scale_to_fit_width(10.5).to_edge(DOWN, buff=0.55)\n        self.play(Write(formula))\n'
            elif onscreen:
                code += f'        body = Text({" ".join(short_lines(onscreen, 56, 3))!r}, font_size=21, color="#20221F", line_spacing=0.8).scale_to_fit_width(10.5).to_edge(DOWN, buff=0.55)\n        self.play(FadeIn(body))\n'
            code += f'        self.wait({max(2, float(scene.get("duration", 6)) * time_scale):.2f})\n'
            code += '        self.play(FadeOut(*self.mobjects))\n'
        script = job_dir / 'generated_scene.py'; script.write_text(code, encoding='utf-8')
        subprocess.run([sys.executable, '-m', 'manim', '-qm', '--disable_caching', str(script), 'LectureScene'], cwd=job_dir, check=True)
        video = next((p for p in (job_dir / 'media' / 'videos' / 'generated_scene').rglob('LectureScene.mp4')), None)
        if video is None: raise FileNotFoundError('Manim did not produce a video')
        status('running', 'Combining narration and animation…')
        concat = job_dir / 'audio.txt'; concat.write_text('\n'.join(f"file '{p.as_posix()}'" for p in audio), encoding='utf-8')
        ffmpeg = os.environ.get('IMAGEIO_FFMPEG_EXE', 'ffmpeg')
        audio_all = job_dir / 'narration.mp3'
        subprocess.run([ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-c', 'copy', str(audio_all)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        final = ROOT / 'outputs' / f"lecture_{job['id']}.mp4"
        subprocess.run([ffmpeg, '-y', '-i', str(video), '-i', str(audio_all), '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(final)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        status('complete', 'Video ready', video=f'/outputs/{final.name}')
    except Exception as exc:
        status('error', str(exc))

if __name__ == '__main__': run(sys.argv[1])

