"""
Reconstruye la carpeta fotos/ extrayendo las imágenes base64
del shareable/. Recorre TODOS los archivos y de-duplica por hash.

Estrategia: leer los HTMLs originales (proyectos/*.html + index.backup.html)
y para cada url() o src="..." que apunte a un path relativo, buscar
la misma referencia (por posición ordinal) en el shareable equivalente
y extraer el data URI.

Como el shareable es un mapeo 1:1 (mismo orden), asocio cada path
original con el nth data URI del shareable.
"""
import re
import base64
from pathlib import Path

ROOT = Path(__file__).parent
SHAREABLE_INDEX = ROOT / "shareable" / "index ( no subir a github ).html"
INDEX_BACKUP = ROOT / "index.backup.html"

# Also process subpages
SUBS = [
    (ROOT / "proyectos" / "havanna.html",
     ROOT / "shareable" / "proyectos" / "havanna.html"),
    (ROOT / "proyectos" / "islas-del-canal.html",
     ROOT / "shareable" / "proyectos" / "islas-del-canal.html"),
    (ROOT / "proyectos" / "yoo4.html",
     ROOT / "shareable" / "proyectos" / "yoo4.html"),
]

# Patterns used in embed.py — same order they were replaced
URL_RE = re.compile(r"url\((['\"]?)([^)'\"]+)\1\)")
SRC_RE = re.compile(r"<img\b[^>]*?\bsrc=(['\"])([^'\"]+)\1")

DATA_URL_RE = re.compile(r"url\((['\"]?)(data:image/[^;]+;base64,[A-Za-z0-9+/=]+)\1\)")
DATA_SRC_RE = re.compile(r"<img\b[^>]*?\bsrc=(['\"])(data:image/[^;]+;base64,[A-Za-z0-9+/=]+)\1")

def extract_data_uris(html: str):
    """Return list of (kind, data_uri) in file order."""
    hits = []
    for m in DATA_URL_RE.finditer(html):
        hits.append(('url', m.start(), m.group(2)))
    for m in DATA_SRC_RE.finditer(html):
        hits.append(('src', m.start(), m.group(2)))
    hits.sort(key=lambda x: x[1])
    return [(kind, uri) for kind, _, uri in hits]

def extract_original_paths(html: str, base: Path):
    """Return list of (kind, absolute_path_target) in file order."""
    hits = []
    for m in URL_RE.finditer(html):
        path = m.group(2)
        if path.startswith(('data:', 'http', '#', '%23')):
            continue
        hits.append(('url', m.start(), path))
    for m in SRC_RE.finditer(html):
        path = m.group(2)
        if path.startswith(('data:', 'http', '#', '%23')):
            continue
        hits.append(('src', m.start(), path))
    hits.sort(key=lambda x: x[1])
    from urllib.parse import unquote
    return [(kind, (base / unquote(path)).resolve()) for kind, _, path in hits]

def data_uri_to_bytes(uri: str):
    """Return (mime, bytes)."""
    match = re.match(r"data:([^;]+);base64,(.+)", uri)
    if not match:
        return None, None
    mime = match.group(1)
    data = base64.b64decode(match.group(2))
    return mime, data

def process_pair(orig_html_path: Path, shareable_html_path: Path, base_for_orig: Path):
    print(f"\n=== {orig_html_path.name} ===")
    if not orig_html_path.exists():
        print("  ORIGINAL missing, skipping")
        return
    if not shareable_html_path.exists():
        print("  SHAREABLE missing, skipping")
        return

    orig_html = orig_html_path.read_text(encoding='utf-8')
    share_html = shareable_html_path.read_text(encoding='utf-8')

    orig_refs = extract_original_paths(orig_html, base_for_orig)
    share_uris = extract_data_uris(share_html)

    print(f"  original refs: {len(orig_refs)}   shareable uris: {len(share_uris)}")

    if len(orig_refs) != len(share_uris):
        print("  [!] mismatch - will match by index up to min length")

    written = 0
    skipped = 0
    for (kind, target_path), (kind2, uri) in zip(orig_refs, share_uris):
        if target_path.exists():
            skipped += 1
            continue
        mime, data = data_uri_to_bytes(uri)
        if data is None:
            print(f"  [X] bad uri for {target_path.name}")
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        try:
            rel = target_path.relative_to(ROOT)
        except Exception:
            rel = target_path
        print(f"  + {rel}  ({len(data)//1024} KB, {mime})")
        written += 1
    print(f"  wrote {written}, skipped {skipped} (already exist)")

def main():
    # index.backup.html references paths relative to ROOT (based on the grep output)
    process_pair(INDEX_BACKUP, SHAREABLE_INDEX, ROOT)
    # Sub-pages reference paths relative to proyectos/ folder
    for orig, share in SUBS:
        process_pair(orig, share, orig.parent)
    print("\n[OK] extract done")

if __name__ == "__main__":
    main()
