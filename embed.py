"""
Genera versiones standalone de los HTMLs con TODAS las imágenes
y el CSS embebidos (base64 data URIs). Salida: ./shareable/
"""
import os
import re
import base64
import io
import shutil
from pathlib import Path
from urllib.parse import unquote
from PIL import Image, ImageOps

ROOT = Path(__file__).parent
OUT = ROOT / "shareable"

# Image optimization params
MAX_LONG_SIDE = 1500   # downsize images larger than this
JPG_QUALITY = 80
LOGO_MAX = 96          # logo is small in UI, keep small

# Cache image -> data URI to avoid re-encoding duplicates
_data_uri_cache = {}

def file_to_data_uri(abs_path: Path) -> str | None:
    if not abs_path.exists():
        print(f"  MISSING: {abs_path}")
        return None
    key = str(abs_path.resolve())
    if key in _data_uri_cache:
        return _data_uri_cache[key]

    ext = abs_path.suffix.lower()
    raw = abs_path.read_bytes()

    if ext in {'.jpg', '.jpeg', '.png'}:
        try:
            img = Image.open(io.BytesIO(raw))
            img = ImageOps.exif_transpose(img)
            has_alpha = (img.mode in ('RGBA', 'LA') or 'transparency' in img.info)
            is_logo = 'monogram' in abs_path.name.lower()
            max_side = LOGO_MAX if is_logo else MAX_LONG_SIDE
            if max(img.size) > max_side:
                img.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            if has_alpha:
                img.save(buf, 'PNG', optimize=True)
                mime = 'image/png'
            else:
                img = img.convert('RGB')
                img.save(buf, 'JPEG', quality=JPG_QUALITY, optimize=True, progressive=True)
                mime = 'image/jpeg'
            encoded = base64.b64encode(buf.getvalue()).decode('ascii')
            data_uri = f"data:{mime};base64,{encoded}"
            kb = len(buf.getvalue()) // 1024
            print(f"  {abs_path.name}: {img.size} -> {kb} KB")
            _data_uri_cache[key] = data_uri
            return data_uri
        except Exception as e:
            print(f"  ERROR optimizing {abs_path}: {e}")
            # fallback raw
            mime = 'image/png' if ext == '.png' else 'image/jpeg'
            encoded = base64.b64encode(raw).decode('ascii')
            return f"data:{mime};base64,{encoded}"
    else:
        print(f"  skip non-image: {abs_path}")
        return None

def resolve_path(href: str, html_path: Path) -> Path:
    """Resolve a relative URL (may be url-encoded) against the HTML file's directory."""
    href = unquote(href)
    # remove leading ./
    return (html_path.parent / href).resolve()

def replace_image_refs(html: str, html_path: Path) -> str:
    # 1. url('path') or url("path") inside style attributes/CSS
    def url_repl(m):
        prefix = m.group(1)  # url(
        quote = m.group(2)   # ' or " or empty
        path = m.group(3)
        suffix = m.group(4)  # closing quote and )
        if path.startswith('data:'):
            return m.group(0)
        # Skip external URLs
        if path.startswith('http'):
            return m.group(0)
        abs_path = resolve_path(path, html_path)
        data_uri = file_to_data_uri(abs_path)
        if data_uri is None:
            return m.group(0)
        return f"{prefix}{quote}{data_uri}{suffix}"

    html = re.sub(
        r"(url\()(['\"]?)([^)'\"]+)(\2\))",
        url_repl,
        html
    )

    # 2. <img src="...">
    def src_repl(m):
        before = m.group(1)
        quote = m.group(2)
        path = m.group(3)
        after = m.group(4)
        if path.startswith('data:'):
            return m.group(0)
        if path.startswith('http'):
            return m.group(0)
        abs_path = resolve_path(path, html_path)
        data_uri = file_to_data_uri(abs_path)
        if data_uri is None:
            return m.group(0)
        return f"{before}{quote}{data_uri}{quote}{after}"

    html = re.sub(
        r"(<img\b[^>]*?\bsrc=)(['\"])([^'\"]+)(['\"])",
        src_repl,
        html
    )
    return html

def inline_css(html: str, html_path: Path) -> str:
    """Find <link rel="stylesheet" href="..."> and replace with inline <style>...</style>."""
    def repl(m):
        href = m.group(1)
        if href.startswith('http'):
            return m.group(0)
        css_path = (html_path.parent / unquote(href)).resolve()
        if not css_path.exists():
            return m.group(0)
        css = css_path.read_text(encoding='utf-8')
        # Process url() inside CSS using same logic with css_path as base
        css = re.sub(
            r"(url\()(['\"]?)([^)'\"]+)(\2\))",
            lambda mm: rewrite_css_url(mm, css_path),
            css
        )
        print(f"  inlined CSS: {css_path.name} ({len(css)//1024} KB)")
        return f"<style>\n{css}\n</style>"
    return re.sub(
        r"<link\s+rel=['\"]stylesheet['\"]\s+href=['\"]([^'\"]+)['\"][^>]*>",
        repl,
        html
    )

def rewrite_css_url(m, css_path: Path) -> str:
    prefix = m.group(1)
    quote = m.group(2)
    path = m.group(3)
    suffix = m.group(4)
    if path.startswith('data:') or path.startswith('http'):
        return m.group(0)
    abs_path = (css_path.parent / unquote(path)).resolve()
    data_uri = file_to_data_uri(abs_path)
    if data_uri is None:
        return m.group(0)
    return f"{prefix}{quote}{data_uri}{suffix}"

def process_html(src: Path, dest: Path):
    print(f"\n=== {src.relative_to(ROOT)} ===")
    html = src.read_text(encoding='utf-8')
    html = inline_css(html, src)
    html = replace_image_refs(html, src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding='utf-8')
    print(f"  -> {dest.relative_to(ROOT)} ({len(html)//1024} KB)")

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    # Main page
    process_html(
        ROOT / "index.html",
        OUT / "index.html"
    )
    # Sub pages
    for name in ["islas-del-canal", "yoo4", "havanna"]:
        process_html(
            ROOT / "proyectos" / f"{name}.html",
            OUT / "proyectos" / f"{name}.html"
        )

    # Update cross-links from sub-pages: "../moroff-estudio (7).html" -> "../index.html"
    for sub in (OUT / "proyectos").glob("*.html"):
        content = sub.read_text(encoding='utf-8')
        content = content.replace("../moroff-estudio (7).html", "../index.html")
        content = content.replace("moroff-estudio%20(7).html", "index.html")
        sub.write_text(content, encoding='utf-8')

    # Also update main: project cards link to proyectos/*.html (already relative, fine)
    print("\n[OK] Done. Open shareable/index.html")

if __name__ == "__main__":
    main()
