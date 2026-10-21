#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor web local para navegar diretórios e reproduzir mídia.

Uso:
    python web_server_enhanced.py [DIRETORIO] [PORTA] [--host HOST]
                                  [--title TITULO] [--auth usuario:senha]

Exemplos:
    python web_server_enhanced.py                       # pasta atual, só localhost
    python web_server_enhanced.py D:\\Musicas 8082 --host 0.0.0.0
    python web_server_enhanced.py ~/Videos 8082 --host 0.0.0.0 --auth admin:1234
"""

import argparse
import base64
import datetime
import hmac
import html
import json
import mimetypes
import os
import re
import socket
import threading
import time
import unicodedata
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8082
DEFAULT_TITLE = "Ligações Kainos"
MAX_SEARCH_RESULTS = 100
INDEX_TTL_SECONDS = 30
CHUNK = 64 * 1024

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'}
# Nem todo navegador toca AVI/MKV/WMV/FLV; mp4/webm/mov são os mais compatíveis.
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}
DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'}

ICONS = {'audio': '🎵', 'video': '🎬', 'image': '🖼️', 'document': '📄', 'file': '📦'}


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #
def get_file_type(filename):
    ext = Path(filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return 'audio'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in DOCUMENT_EXTENSIONS:
        return 'document'
    return 'file'


def fmt_size(n):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i, n = 0, float(n)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f} {units[i]}" if i else f"{int(n)} B"


def fmt_title(name):
    stem = Path(name).stem.replace('_', ' ').replace('-', ' ')
    return ' '.join(w.capitalize() for w in stem.split()) or name


def norm(text):
    """Minúsculas, sem acentos e com separadores tratados como espaço."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[_\-.]+', ' ', text).casefold()


def is_hidden_path(url_path):
    """True se qualquer parte do caminho começa com '.' (ex.: /.ssh/id_rsa)."""
    return any(p.startswith('.') for p in url_path.split('/') if p)


def url_quote_path(rel_posix):
    return '/' + urllib.parse.quote(rel_posix)


# --------------------------------------------------------------------------- #
# Índice de arquivos (evita os.walk a cada busca)
# --------------------------------------------------------------------------- #
class FileIndex:
    def __init__(self, root, ttl=INDEX_TTL_SECONDS):
        self.root = root
        self.ttl = ttl
        self.items = []
        self.built_at = 0.0
        self.lock = threading.Lock()

    def _build(self):
        items = []
        for current, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if name.startswith('.'):
                    continue
                full = os.path.join(current, name)
                rel = os.path.relpath(full, self.root).replace(os.sep, '/')
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                ftype = get_file_type(name)
                items.append({
                    'name': name,
                    'path': '/' + rel,
                    'url': url_quote_path(rel),
                    'size': st.st_size,
                    'modified': datetime.datetime.fromtimestamp(st.st_mtime).isoformat(),
                    'type': ftype,
                    'icon': ICONS[ftype],
                    '_norm': norm(name),
                })
        self.items = items
        self.built_at = time.time()

    def get(self):
        with self.lock:
            if time.time() - self.built_at > self.ttl:
                self._build()
            return self.items

    def search(self, query):
        tokens = norm(query).split()
        if not tokens:
            return []
        found = [it for it in self.get() if all(t in it['_norm'] for t in tokens)]
        # Ordena ANTES de limitar, para os mais relevantes não ficarem de fora.
        found.sort(key=lambda it: (not it['_norm'].startswith(tokens[0]), it['name'].casefold()))
        return [{k: v for k, v in it.items() if not k.startswith('_')}
                for it in found[:MAX_SEARCH_RESULTS]]


# --------------------------------------------------------------------------- #
# Template (separado do código Python, sem f-string)
# --------------------------------------------------------------------------- #
TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%% - Buscador de Arquivos</title>
<style>
:root{--bg:#f2f5f3;--card:#ffffff;--tx:#1c2a22;--mut:#5f7367;--ac:#1e8e3e;--ac-dark:#176b2f;--line:#d9e2dc}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--tx)}
header{padding:20px;background:linear-gradient(350deg,#3f991e 0%,#308900 50%,#186300 51%,#28a745 100%)}
.header-content{display:flex;justify-content:space-between;align-items:center;max-width:1200px;margin:0 auto}
.logo{font-size:2rem;font-weight:700;color:#fff;text-shadow:2px 2px 4px rgba(0,0,0,.3)}
.logo a{color:inherit;text-decoration:none}
.wrap{max-width:1200px;margin:0 auto;padding:20px}
.crumbs{font-size:14px;color:var(--mut);margin-bottom:14px;word-break:break-word}
.crumbs a{color:var(--ac-dark)}
.search-container{margin:20px 0;position:relative}
.search-box{display:flex;gap:8px}
#searchInput{flex:1;padding:12px 16px;border:1px solid var(--line);background:#fff;color:var(--tx);border-radius:8px;font-size:16px}
#searchInput:focus{outline:none;border-color:var(--ac);box-shadow:0 0 0 3px rgba(30,142,62,.2)}
button{padding:12px 18px;border:0;border-radius:8px;background:var(--ac);color:#fff;font-weight:600;cursor:pointer;transition:background-color .2s}
button:hover{background:var(--ac-dark)}
.search-results{display:none;position:absolute;top:100%;left:0;right:0;margin-top:6px;background:var(--card);border:1px solid var(--line);border-radius:8px;max-height:400px;overflow-y:auto;z-index:1000;box-shadow:0 6px 16px rgba(0,0,0,.15)}
.search-result-item{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px;color:var(--tx);text-decoration:none}
a.search-result-item:hover{background:#eaf5ee}
.search-result-item:last-child{border-bottom:none}
.result-info{flex:1;min-width:0}
.result-name{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.result-path{font-size:12px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.12)}
.title{margin:0 0 8px;font-weight:600;font-size:1rem;word-break:break-word}
.title a{color:var(--tx);text-decoration:none}
.title a:hover{color:var(--ac)}
.meta{font-size:12px;color:var(--mut);margin-bottom:8px}
audio,video{width:100%;border-radius:6px}
img.thumb{width:100%;max-height:220px;object-fit:cover;border-radius:6px;margin-top:8px}
.empty{padding:30px;text-align:center;color:var(--mut)}
.loading{display:none;text-align:center;padding:10px;color:var(--mut)}
@media (max-width:768px){.logo{font-size:1.5rem}}
</style>
</head>
<body>
<header>
  <div class="header-content">
    <div class="logo"><a href="/">%%TITLE%%</a></div>
  </div>
</header>
<main class="wrap">
  <div class="crumbs">%%CRUMBS%%</div>
  <div class="search-container">
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="🔎 Buscar arquivos em todas as pastas..."
             autocomplete="off" aria-label="Buscar arquivos">
      <button id="searchBtn" type="button">Buscar</button>
    </div>
    <div class="loading" id="loading">Buscando...</div>
    <div class="search-results" id="searchResults"></div>
  </div>
  <div class="grid">%%CARDS%%</div>
</main>
<script>
const input = document.getElementById('searchInput');
const box = document.getElementById('searchResults');
const loading = document.getElementById('loading');
let timer = null, seq = 0;

function msg(text) {
  const d = document.createElement('div');
  d.className = 'search-result-item';
  d.textContent = text;
  return d;
}

function render(results) {
  box.replaceChildren();
  if (!results.length) {
    box.appendChild(msg('Nenhum resultado encontrado'));
  } else {
    results.forEach(f => {
      const a = document.createElement('a');
      a.className = 'search-result-item';
      a.href = f.url;            // já vem com percent-encoding do servidor
      a.target = '_blank';
      a.rel = 'noopener';
      const icon = document.createElement('span');
      icon.textContent = f.icon;
      const info = document.createElement('div');
      info.className = 'result-info';
      const name = document.createElement('div');
      name.className = 'result-name';
      name.textContent = f.name;   // textContent: sem risco de XSS
      const path = document.createElement('div');
      path.className = 'result-path';
      path.textContent = f.path;
      info.append(name, path);
      a.append(icon, info);
      box.appendChild(a);
    });
  }
  box.style.display = 'block';
}

async function search(q) {
  const mine = ++seq;
  loading.style.display = 'block';
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    const data = await r.json();
    if (mine !== seq) return;      // descarta respostas antigas
    render(data.results);
  } catch (err) {
    console.error('Erro na busca:', err);
    if (mine === seq) { box.replaceChildren(msg('Erro ao buscar')); box.style.display = 'block'; }
  } finally {
    if (mine === seq) loading.style.display = 'none';
  }
}

function doSearch() {
  const q = input.value.trim();
  if (q) search(q);
}

input.addEventListener('input', () => {
  clearTimeout(timer);
  const q = input.value.trim();
  if (q.length < 2) { box.style.display = 'none'; return; }
  timer = setTimeout(() => search(q), 300);
});
input.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
  if (e.key === 'Escape') { box.style.display = 'none'; }
});
document.getElementById('searchBtn').addEventListener('click', doSearch);
document.addEventListener('click', e => {
  if (!e.target.closest('.search-container')) box.style.display = 'none';
});
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
class FileServerHandler(SimpleHTTPRequestHandler):
    # Configurados em run_server()
    root = ""
    title = DEFAULT_TITLE
    auth_token = None     # "Basic xxxxx" ou None
    index = None

    server_version = "FileServer/2.0"

    # --- infraestrutura -------------------------------------------------- #
    def handle(self):
        # Quedas de conexão são normais em streaming; evita traceback no console.
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def check_auth(self):
        if not self.auth_token:
            return True
        given = self.headers.get('Authorization', '')
        if hmac.compare_digest(given.encode(), self.auth_token.encode()):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Servidor de Arquivos"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def is_inside_root(self, fs_path):
        real = os.path.realpath(fs_path)
        return real == self.root or real.startswith(self.root + os.sep)

    # --- roteamento ------------------------------------------------------ #
    def do_GET(self):
        self.dispatch(head_only=False)

    def do_HEAD(self):
        self.dispatch(head_only=True)

    def dispatch(self, head_only):
        if not self.check_auth():
            return
        parsed = urllib.parse.urlparse(self.path)
        url_path = urllib.parse.unquote(parsed.path)

        if parsed.path == '/api/search':
            self.handle_search_api(parsed, head_only)
            return

        # Bloqueia dotfiles (.ssh, .env, .bash_history...) também no acesso direto.
        if is_hidden_path(url_path):
            self.send_error(404, "Não encontrado")
            return

        fs_path = self.translate_path(parsed.path)
        if not self.is_inside_root(fs_path):
            self.send_error(404, "Não encontrado")
            return

        if os.path.isdir(fs_path):
            if not parsed.path.endswith('/'):
                location = parsed.path + '/' + (('?' + parsed.query) if parsed.query else '')
                self.send_response(301)
                self.send_header('Location', location)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.list_directory_enhanced(fs_path, url_path, head_only)
            return

        if os.path.isfile(fs_path):
            self.serve_file(fs_path, head_only)
            return

        self.send_error(404, "Não encontrado")

    # --- API de busca ---------------------------------------------------- #
    def handle_search_api(self, parsed, head_only):
        qs = urllib.parse.parse_qs(parsed.query)
        query = (qs.get('q', [''])[0] or '').strip()
        results = self.index.search(query) if query else []
        body = json.dumps({'results': results, 'total': len(results)},
                          ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        # Sem Access-Control-Allow-Origin: outros sites não devem ler esta API.
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    # --- arquivos com suporte a Range (seek em áudio/vídeo) --------------- #
    def serve_file(self, fs_path, head_only):
        try:
            size = os.path.getsize(fs_path)
            f = open(fs_path, 'rb')
        except OSError:
            self.send_error(404, "Não encontrado")
            return

        with f:
            ctype = mimetypes.guess_type(fs_path)[0] or 'application/octet-stream'
            start, end, status = 0, size - 1, 200

            rng = self.headers.get('Range')
            if rng and size > 0:
                m = re.match(r'^bytes=(\d*)-(\d*)$', rng.strip())
                if m and (m.group(1) or m.group(2)):
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:  # "bytes=-N" = últimos N bytes
                        start = max(size - int(m.group(2)), 0)
                    end = min(end, size - 1)
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    status = 206

            length = max(end - start + 1, 0)
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(length))
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.send_header('Last-Modified', self.date_time_string(os.path.getmtime(fs_path)))
            self.end_headers()

            if head_only or length == 0:
                return
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    # --- listagem de diretório ------------------------------------------- #
    def build_breadcrumbs(self, url_path):
        crumbs = ['<a href="/">Início</a>']
        parts = [p for p in url_path.strip('/').split('/') if p]
        acc = []
        for i, p in enumerate(parts):
            acc.append(p)
            if i == len(parts) - 1:
                crumbs.append(html.escape(p))
            else:
                href = '/' + '/'.join(urllib.parse.quote(x) for x in acc) + '/'
                crumbs.append(f'<a href="{href}">{html.escape(p)}</a>')
        return ' / '.join(crumbs)

    def list_directory_enhanced(self, fs_path, url_path, head_only):
        try:
            names = [n for n in os.listdir(fs_path) if not n.startswith('.')]
        except OSError:
            self.send_error(404, "Diretório não encontrado")
            return

        entries = []
        for name in names:
            full = os.path.join(fs_path, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            entries.append((name, full, st, os.path.isdir(full)))
        # Pastas primeiro, depois arquivos; sem diferenciar maiúsculas/minúsculas.
        entries.sort(key=lambda e: (not e[3], e[0].casefold()))

        cards = []
        parts = [p for p in url_path.strip('/').split('/') if p]
        if parts:
            parent = '/' + '/'.join(urllib.parse.quote(p) for p in parts[:-1])
            parent = parent if parent == '/' else parent + '/'
            cards.append('<div class="card"><h3 class="title">📁 '
                         f'<a href="{parent}">.. (voltar)</a></h3></div>')

        for name, full, st, is_dir in entries:
            href = urllib.parse.quote(name)
            safe_name = html.escape(name)
            if is_dir:
                cards.append('<div class="card"><h3 class="title">📁 '
                             f'<a href="{href}/">{safe_name}/</a></h3></div>')
                continue

            dt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')
            meta = f'<div class="meta">Data: {dt} • Tamanho: {fmt_size(st.st_size)}</div>'
            title = html.escape(fmt_title(name))
            ext = Path(name).suffix.lower()

            if ext in AUDIO_EXTENSIONS:
                cards.append(f'<div class="card"><h3 class="title">🎵 {title}</h3>{meta}'
                             f'<audio controls preload="none" src="{href}">'
                             'Seu navegador não suporta áudio.</audio></div>')
            elif ext in VIDEO_EXTENSIONS:
                cards.append(f'<div class="card"><h3 class="title">🎬 {title}</h3>{meta}'
                             f'<video controls preload="none" src="{href}">'
                             'Seu navegador não suporta vídeo.</video></div>')
            elif ext in IMAGE_EXTENSIONS:
                cards.append(f'<div class="card"><h3 class="title">🖼️ '
                             f'<a href="{href}">{title}</a></h3>{meta}'
                             f'<img class="thumb" src="{href}" alt="{title}" loading="lazy"></div>')
            else:
                cards.append(f'<div class="card"><h3 class="title">📦 '
                             f'<a href="{href}">{safe_name}</a></h3>{meta}</div>')

        if not entries:
            cards.append('<div class="card empty">Diretório vazio.</div>')

        page = (TEMPLATE
                .replace('%%TITLE%%', html.escape(self.title))
                .replace('%%CRUMBS%%', self.build_breadcrumbs(url_path))
                .replace('%%CARDS%%', '\n'.join(cards)))
        body = page.encode('utf-8', 'surrogateescape')

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


# --------------------------------------------------------------------------- #
# Inicialização
# --------------------------------------------------------------------------- #
def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def parse_args():
    p = argparse.ArgumentParser(description="Servidor web de arquivos e mídia.")
    p.add_argument('directory', nargs='?', default=None,
                   help="pasta a servir (padrão: pasta atual)")
    p.add_argument('port', nargs='?', type=int, default=DEFAULT_PORT,
                   help=f"porta (padrão: {DEFAULT_PORT})")
    p.add_argument('--host', default='127.0.0.1',
                   help="endereço de escuta; use 0.0.0.0 para liberar na rede (padrão: 127.0.0.1)")
    p.add_argument('--title', default=DEFAULT_TITLE, help="título exibido no topo")
    p.add_argument('--auth', metavar='USUARIO:SENHA', default=None,
                   help="ativa autenticação HTTP Basic")
    return p.parse_args()


def run_server():
    args = parse_args()
    root = os.path.realpath(os.path.expanduser(args.directory or os.getcwd()))
    if not os.path.isdir(root):
        raise SystemExit(f"Diretório inválido: {root}")

    FileServerHandler.root = root
    FileServerHandler.title = args.title
    FileServerHandler.index = FileIndex(root)
    if args.auth:
        if ':' not in args.auth:
            raise SystemExit("--auth deve ter o formato usuario:senha")
        token = base64.b64encode(args.auth.encode('utf-8')).decode('ascii')
        FileServerHandler.auth_token = 'Basic ' + token

    handler = partial(FileServerHandler, directory=root)
    with ThreadingHTTPServer((args.host, args.port), handler) as httpd:
        print("🚀 Servidor de Arquivos iniciado!")
        print("=" * 50)
        print(f"📁 Diretório: {root}")
        print(f"🌐 Local: http://localhost:{args.port}")
        if args.host in ('0.0.0.0', '::'):
            print(f"🌍 Rede:  http://{get_local_ip()}:{args.port}")
            if not args.auth:
                print("⚠️  Sem senha: qualquer pessoa na rede acessa estes arquivos (--auth usuario:senha).")
        print(f"🔐 Autenticação: {'ativada' if args.auth else 'desativada'}")
        print("=" * 50)
        print("Pressione Ctrl+C para encerrar.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Servidor encerrado.")


if __name__ == "__main__":
    run_server()
