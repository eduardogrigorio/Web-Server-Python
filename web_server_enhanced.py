#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import html
import http.server
import socketserver
import urllib.parse
import datetime
import socket
import json
import mimetypes
from pathlib import Path

# Padrões (podem ser sobrescritos por argumentos)
PORT = 8082
DIRECTORY = "/home/ubuntu"
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}
DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'}

class EnhancedFileServerHandler(http.server.SimpleHTTPRequestHandler):
    """Servidor de arquivos com busca avançada e interface melhorada."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        """Processa requisições GET com suporte a busca."""
        parsed = urllib.parse.urlparse(self.path)
        
        # API de busca
        if parsed.path == '/api/search':
            self.handle_search_api(parsed)
            return
            
        # Listagem de diretório personalizada
        if parsed.path.endswith('/') or os.path.isdir(self.translate_path(parsed.path)):
            self.list_directory_enhanced(self.translate_path(parsed.path))
            return
            
        # Arquivos normais
        super().do_GET()

    def handle_search_api(self, parsed):
        """API de busca que retorna resultados em JSON."""
        qs = urllib.parse.parse_qs(parsed.query)
        query = (qs.get('q', [''])[0] or '').strip().lower()
        
        if not query:
            self.send_json_response({'results': [], 'total': 0})
            return
            
        results = []
        total = 0
        
        # Busca recursiva em todos os diretórios
        for root, dirs, files in os.walk(DIRECTORY):
            # Ignora diretórios ocultos
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file.startswith('.'):
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, DIRECTORY)
                
                # Verifica se o arquivo corresponde à busca
                if (query in file.lower() or 
                    query in Path(file).stem.replace('_', ' ').replace('-', ' ').lower()):
                    
                    try:
                        stat = os.stat(file_path)
                        file_info = {
                            'name': file,
                            'path': '/' + rel_path.replace('\\', '/'),
                            'size': stat.st_size,
                            'modified': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'type': self.get_file_type(file),
                            'icon': self.get_file_icon(file)
                        }
                        results.append(file_info)
                        total += 1
                        
                        # Limita resultados para performance
                        if total >= 100:
                            break
                    except OSError:
                        continue
                        
            if total >= 100:
                break
                
        # Ordena por relevância (nome exato primeiro, depois por nome)
        results.sort(key=lambda x: (query not in x['name'].lower(), x['name'].lower()))
        
        self.send_json_response({'results': results, 'total': total})

    def send_json_response(self, data):
        """Envia resposta JSON."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def get_file_type(self, filename):
        """Determina o tipo do arquivo."""
        ext = Path(filename).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            return 'audio'
        elif ext in VIDEO_EXTENSIONS:
            return 'video'
        elif ext in IMAGE_EXTENSIONS:
            return 'image'
        elif ext in DOCUMENT_EXTENSIONS:
            return 'document'
        else:
            return 'file'

    def get_file_icon(self, filename):
        """Retorna o ícone apropriado para o arquivo."""
        file_type = self.get_file_type(filename)
        icons = {
            'audio': '🎵',
            'video': '🎬',
            'image': '🖼️',
            'document': '📄',
            'file': '📦'
        }
        return icons.get(file_type, '📦')

    def list_directory_enhanced(self, path):
        """Listagem de diretório com interface melhorada."""
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            self.send_error(404, "Diretório não encontrado")
            return

        # Query string para busca local
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        search = (qs.get('search', [''])[0] or '').strip().lower()
        base_path = parsed.path

        # Cabeçalhos HTTP
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        # Utilitários
        def fmt_size(n):
            units = ['B','KB','MB','GB','TB']
            i = 0
            n = float(n)
            while n >= 1024 and i < len(units)-1:
                n /= 1024; i += 1
            return f"{n:.1f} {units[i]}" if i else f"{int(n)} B"

        def fmt_title(name):
            n = Path(name).stem.replace('_',' ').replace('-',' ')
            return ' '.join(w.capitalize() for w in n.split())

        # Breadcrumbs
        crumbs = ['<a href="/">Início</a>']
        acc = ''
        parts = [p for p in base_path.strip('/').split('/') if p]
        for i, p in enumerate(parts):
            acc += '/' + p
            if i == len(parts) - 1:
                crumbs.append(html.escape(p))
            else:
                crumbs.append(f'<a href="{acc}/">{html.escape(p)}</a>')
        crumbs_html = ' / '.join(crumbs)

        # HTML completo
        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ligações Kainos - Buscador de Arquivos</title>
<style>
:root{{--bg:#101418;--card:#151b22;--tx:#e8eef5;--mut:#9fb3c8;--ac:#3ea6ff;--hover:#2a3240}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Ubuntu,Helvetica,Arial,sans-serif;background:#e0e0e0;color:var(--tx)}}
header{{padding:20px;border-bottom:1px solid #1f2630;background:linear-gradient(350deg, #3f991e 0%, #308900 50%, #186300 51%, #28a745 100%)}}
.header-content{{display:flex;justify-content:space-between;align-items:center;max-width:1200px;margin:0 auto}}
.logo{{font-size:2rem;font-weight:700;color:white;text-shadow:2px 2px 4px rgba(0,0,0,0.3)}}
.logo span{{color:#ffcc00}}
nav a{{color:rgba(255,255,255,0.9);margin-right:12px;text-decoration:none;padding:8px 15px;border-radius:4px;transition:background-color 0.3s}}
nav a:hover{{background-color:rgba(255,255,255,0.2)}}
.wrap{{max-width:1200px;margin:0 auto;padding:20px}}
.crumbs{{font-size:13px;color:var(--mut);margin-bottom:14px}}
.search-container{{margin:20px 0;position:relative}}
.search-box{{display:flex;gap:8px;margin-bottom:10px}}
#searchInput{{flex:1;padding:12px 16px;border:1px solid #2a3240;background:#ffffff;;color:var(--tx);border-radius:8px;font-size:16px}}
#searchInput:focus{{outline:none;border-color:var(--ac);box-shadow:0 0 0 2px rgba(62,166,255,0.2)}}
button{{padding:12px 16px;border:0;border-radius:8px;background:#20c10e;color:#07243a;font-weight:600;cursor:pointer;transition:background-color 0.3s}}
button:hover{{background:#2d8ae6}}
.search-results{{display:none;position:absolute;top:100%;left:0;right:0;background:var(--card);border:1px solid #2a3240;border-radius:8px;max-height:400px;overflow-y:auto;z-index:1000;box-shadow:0 4px 12px rgba(0,0,0,0.3)}}
.search-result-item{{padding:12px 16px;border-bottom:1px solid #1e2633;cursor:pointer;display:flex;align-items:center;gap:10px}}
.search-result-item:hover{{background:var(--hover)}}
.search-result-item:last-child{{border-bottom:none}}
.result-icon{{font-size:18px}}
.result-info{{flex:1}}
.result-name{{font-weight:500;margin-bottom:2px}}
.result-path{{font-size:12px;color:var(--mut)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
.card{{background:#00631b;border:1px solid #1e2633;border-radius:12px;padding:14px;transition:transform 0.2s,box-shadow 0.2s}}
.card:hover{{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.2)}}
.title{{margin:0 0 8px;font-weight:600}}
.title a{{color:var(--tx);text-decoration:none}}
.title a:hover{{color:var(--ac)}}
.meta{{font-size:12px;color:var(--mut);margin-bottom:8px}}
audio,video{{width:100%;border-radius:6px}}
.empty{{padding:30px;text-align:center;color:var(--mut)}}
.loading{{display:none;text-align:center;padding:20px;color:var(--mut)}}
@media (max-width: 768px){{
.header-content{{flex-direction:column;text-align:center}}
nav{{margin-top:15px}}
.logo{{font-size:1.5rem}}
}}
</style>
</head>
<body>
<header>
  <div class="header-content">
    <div class="logo">Ligações <span>Kainos</span></div>
    <nav>
      <a href="/">Início</a>
      <a href="#">Categorias</a>
      <a href="#">Recentes</a>
      <a href="#">Contato</a>
    </nav>
  </div>
</header>
<main class="wrap">
  <div class="crumbs">{crumbs_html}</div>
  
  <div class="search-container">
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="🔎 Buscar arquivos..." autocomplete="off">
      <button onclick="performSearch()">Buscar</button>
    </div>
    <div class="search-results" id="searchResults"></div>
    <div class="loading" id="loading">Buscando...</div>
  </div>
"""

        # Busca local no diretório atual
        base_no_query = html.escape(base_path or '/')
        if search:
            html_content += f'<h3>Resultados para "{html.escape(search)}":</h3>'

        # Cartões (pastas e arquivos)
        cards = []
        found = False

        # Link para diretório pai
        if base_path != '/':
            parent = os.path.dirname(base_path.rstrip('/')) or '/'
            cards.append(
                '<div class="card"><h3 class="title">📁 '
                '<a href="' + parent + '/">.. (voltar)</a></h3></div>'
            )

        # Pastas
        for name in entries:
            if name.startswith('.'): 
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                if search and search not in name.lower():
                    continue
                found = True
                href = urllib.parse.quote(name) + '/'
                cards.append(
                    '<div class="card"><h3 class="title">📁 '
                    '<a href="' + href + '">' + html.escape(name) + '/</a></h3></div>'
                )

        # Arquivos
        for name in entries:
            if name.startswith('.'):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                continue

            try:
                st = os.stat(full)
                dt = datetime.datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')
                size = fmt_size(st.st_size)
                title = fmt_title(name)

                if search and (search not in name.lower() and search not in title.lower()):
                    continue

                found = True
                href = urllib.parse.quote(name)
                ext = Path(name).suffix.lower()

                if ext in AUDIO_EXTENSIONS:
                    cards.append(
                        '<div class="card">'
                        '<h3 class="title">🎵 ' + html.escape(title) + '</h3>'
                        '<div class="meta">Data: ' + dt + ' • Tamanho: ' + size + '</div>'
                        '<audio controls preload="metadata" src="' + href + '">Seu navegador não suporta áudio.</audio>'
                        '</div>'
                    )
                elif ext in VIDEO_EXTENSIONS:
                    cards.append(
                        '<div class="card">'
                        '<h3 class="title">🎬 ' + html.escape(title) + '</h3>'
                        '<div class="meta">Data: ' + dt + ' • Tamanho: ' + size + '</div>'
                        '<video controls preload="metadata" src="' + href + '">Seu navegador não suporta vídeo.</video>'
                        '</div>'
                    )
                elif ext in IMAGE_EXTENSIONS:
                    cards.append(
                        '<div class="card">'
                        '<h3 class="title">🖼️ <a href="' + href + '">' + html.escape(title) + '</a></h3>'
                        '<div class="meta">Data: ' + dt + ' • Tamanho: ' + size + '</div>'
                        '<img src="' + href + '" style="width:100%;border-radius:6px;margin-top:8px" loading="lazy">'
                        '</div>'
                    )
                else:
                    cards.append(
                        '<div class="card">'
                        '<h3 class="title">📦 <a href="' + href + '">' + html.escape(name) + '</a></h3>'
                        '<div class="meta">Data: ' + dt + ' • Tamanho: ' + size + '</div>'
                        '</div>'
                    )
            except OSError:
                continue

        if not found:
            if search:
                cards.append(
                    '<div class="card empty">Nenhum resultado para "' + html.escape(search) +
                    '". <a href="' + base_no_query + '">Voltar</a>.</div>'
                )
            else:
                cards.append('<div class="card empty">Diretório vazio.</div>')

        html_content += '<div class="grid">' + '\n'.join(cards) + '</div>'

        # JavaScript para busca em tempo real
        html_content += """
<script>
let searchTimeout;
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
const loading = document.getElementById('loading');

searchInput.addEventListener('input', function() {
    clearTimeout(searchTimeout);
    const query = this.value.trim();
    
    if (query.length < 2) {
        searchResults.style.display = 'none';
        return;
    }
    
    searchTimeout = setTimeout(() => {
        performGlobalSearch(query);
    }, 300);
});

searchInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const query = this.value.trim();
        if (query) {
            performGlobalSearch(query);
        }
    }
});

// Fechar resultados ao clicar fora
document.addEventListener('click', function(e) {
    if (!e.target.closest('.search-container')) {
        searchResults.style.display = 'none';
    }
});

async function performGlobalSearch(query) {
    loading.style.display = 'block';
    searchResults.style.display = 'none';
    
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        loading.style.display = 'none';
        displaySearchResults(data.results);
    } catch (error) {
        loading.style.display = 'none';
        console.error('Erro na busca:', error);
    }
}

function displaySearchResults(results) {
    if (results.length === 0) {
        searchResults.innerHTML = '<div class="search-result-item">Nenhum resultado encontrado</div>';
    } else {
        searchResults.innerHTML = results.map(file => `
            <div class="search-result-item" onclick="openFile('${file.path}')">
                <span class="result-icon">${file.icon}</span>
                <div class="result-info">
                    <div class="result-name">${file.name}</div>
                    <div class="result-path">${file.path}</div>
                </div>
            </div>
        `).join('');
    }
    
    searchResults.style.display = 'block';
}

function openFile(path) {
    window.open(path, '_blank');
    searchResults.style.display = 'none';
}

function performSearch() {
    const query = searchInput.value.trim();
    if (query) {
        window.location.href = `?search=${encodeURIComponent(query)}`;
    }
}
</script>
</main>
</body>
</html>"""

        self.wfile.write(html_content.encode('utf-8', 'surrogateescape'))


def get_local_ip():
    """Obtém o IP local (para exibir no console)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server():
    os.chdir(DIRECTORY)
    with socketserver.TCPServer(("0.0.0.0", PORT), EnhancedFileServerHandler) as httpd:
        print("🚀 Servidor de Busca de Arquivos iniciado!")
        print("=" * 50)
        print(f"📁 Diretório: {DIRECTORY}")
        print(f"🌐 Local: http://localhost:{PORT}")
        print(f"🌍 Rede: http://{get_local_ip()}:{PORT}")
        print("=" * 50)
        print("✨ Funcionalidades:")
        print("  • Busca em tempo real")
        print("  • Suporte a áudio, vídeo e imagens")
        print("  • Interface responsiva")
        print("  • Navegação por pastas")
        print("=" * 50)
        print("Pressione Ctrl+C para encerrar.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Servidor encerrado.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1]:
        DIRECTORY = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2]:
        try:
            PORT = int(sys.argv[2])
        except ValueError:
            print(f"Porta inválida: {sys.argv[2]}. Usando {PORT}.")
    run_server()

