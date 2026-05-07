"""
Simple asset minifier for CSS and JS used in local development.

This script performs lightweight minification (strip comments and blank lines)
and writes minified copies to `web/static/dist/js` and `web/static/dist/css`.

Run:
  python tools/minify_assets.py

It does not require external dependencies and is safe to run locally.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'web', 'static')
DIST = os.path.join(STATIC, 'dist')

JS_SRC = os.path.join(STATIC, 'js')
CSS_SRC = os.path.join(STATIC, 'css')
JS_DIST = os.path.join(DIST, 'js')
CSS_DIST = os.path.join(DIST, 'css')

os.makedirs(JS_DIST, exist_ok=True)
os.makedirs(CSS_DIST, exist_ok=True)

def minify_js(src_path, dst_path):
    with open(src_path, 'r', encoding='utf-8') as f:
        text = f.read()
    # Remove /* */ comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    # Remove // comments
    text = re.sub(r'//.*', '', text)
    # Collapse multiple blank lines
    lines = [l.rstrip() for l in text.splitlines()]
    lines = [l for l in lines if l.strip()]
    out = '\n'.join(lines)
    with open(dst_path, 'w', encoding='utf-8') as f:
        f.write(out)

def minify_css(src_path, dst_path):
    with open(src_path, 'r', encoding='utf-8') as f:
        text = f.read()
    # Remove /* */ comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    # Remove whitespace around symbols
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s*([{};:,])\s*', r'\1', text)
    text = text.strip()
    with open(dst_path, 'w', encoding='utf-8') as f:
        f.write(text)

def process_folder(src_dir, dst_dir, minify_fn, ext):
    if not os.path.isdir(src_dir):
        return []
    processed = []
    for fname in os.listdir(src_dir):
        if not fname.endswith(ext):
            continue
        src = os.path.join(src_dir, fname)
        name = os.path.splitext(fname)[0]
        dst_fname = f"{name}.min{ext}"
        dst = os.path.join(dst_dir, dst_fname)
        try:
            minify_fn(src, dst)
            processed.append((src, dst))
            print(f"Minified {src} -> {dst}")
        except Exception as e:
            print(f"Failed to minify {src}: {e}")
    return processed

def main():
    js = process_folder(JS_SRC, JS_DIST, minify_js, '.js')
    css = process_folder(CSS_SRC, CSS_DIST, minify_css, '.css')
    print('\nSummary:')
    print(f'JS files minified: {len(js)}')
    print(f'CSS files minified: {len(css)}')

if __name__ == '__main__':
    main()
