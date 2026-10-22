"""Baixa o áudio de um vídeo do YouTube para a pasta audio/ (MP3), com o yt-dlp: ele pega só a
trilha de áudio direto dos servidores do YouTube (sem tocar o vídeo) e o FFmpeg converte para MP3.
Depois disso o arquivo aparece na Biblioteca como qualquer áudio colocado na pasta.

A origem (link, título e canal do vídeo) fica em docs/origens.json, pelo nome do arquivo em audio/,
para rastrear de onde veio cada música (coluna "Origem" da Biblioteca).

Uso (a interface chama pela aba "Adicionar"):
    python baixar.py "<link do YouTube>"
"""
import json
import os
import re
import shutil
import sys
import threading
from datetime import datetime

from pastas import BASE_DIR, PASTA_AUDIO

CAMINHO_ORIGENS = os.path.join(BASE_DIR, "docs", "origens.json")
TRAVA = threading.Lock()
# youtube.com/watch?v=, youtu.be/, /shorts/, /live/, music.youtube.com...: o id do vídeo tem 11 caracteres
PADRAO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")


def id_do_video(url):
    """Id do vídeo no link do YouTube, ou None se o link não é de um vídeo do YouTube."""
    if not re.match(r"^https?://([a-z0-9-]+\.)*(youtube\.com|youtu\.be|youtube-nocookie\.com)/", url or "", re.I):
        return None
    m = PADRAO_ID.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- docs/origens.json
def origens():
    """Nome do arquivo em audio/ -> {url, video_id, titulo, canal, baixado_em}."""
    try:
        with open(CAMINHO_ORIGENS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _registrar_origem(arquivo, dados):
    with TRAVA:
        todas = origens()
        todas[arquivo] = dados
        os.makedirs(os.path.dirname(CAMINHO_ORIGENS), exist_ok=True)
        with open(CAMINHO_ORIGENS, "w", encoding="utf-8") as f:
            json.dump(todas, f, ensure_ascii=False, indent=2)


def _nome_livre(base):
    """<base>.mp3 sem caracteres proibidos no Windows; se já existe, <base> (2).mp3..."""
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")[:150] or "audio"
    nome, n = base + ".mp3", 2
    while os.path.exists(os.path.join(PASTA_AUDIO, nome)):
        nome, n = f"{base} ({n}).mp3", n + 1
    return nome


def main(argumentos):
    if len(argumentos) != 1:
        print("uso: python baixar.py \"<link do YouTube>\"")
        return 1
    url = argumentos[0].strip()
    video_id = id_do_video(url)
    if not video_id:
        print("Erro: o link não é de um vídeo do YouTube.")
        return 1
    try:
        import yt_dlp
    except ImportError:
        print("Erro: instale o yt-dlp: python -m pip install -U yt-dlp")
        return 1
    if shutil.which("ffmpeg") is None:
        print("Erro: FFmpeg não encontrado no PATH do sistema.")
        return 1
    ja = next((a for a, o in origens().items() if o.get("video_id") == video_id
               and os.path.isfile(os.path.join(PASTA_AUDIO, a))), None)
    if ja:
        print(f"Erro: este vídeo já foi baixado: audio\\{ja}")
        return 1

    opcoes_base = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True}
    if shutil.which("node"):  # o YouTube exige um runtime de JavaScript; o padrão do yt-dlp é o Deno
        opcoes_base["js_runtimes"] = {"node": {}}
    print("[1/3] Lendo as informações do vídeo...", flush=True)
    url_video = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(opcoes_base) as ydl:
            info = ydl.extract_info(url_video, download=False)
    except Exception as e:  # yt_dlp.utils.DownloadError e afins
        print(f"Erro: não foi possível ler o vídeo: {e}")
        return 1
    titulo, canal = info.get("title") or video_id, info.get("uploader") or info.get("channel") or ""
    nome = _nome_livre(titulo)
    pasta_temp = os.path.join(PASTA_AUDIO, ".baixando")  # o .mp3 só aparece em audio/ quando fica pronto
    os.makedirs(pasta_temp, exist_ok=True)
    temporario = os.path.join(pasta_temp, video_id)

    ultimo = [-1]
    def progresso(d):
        if d.get("status") == "downloading" and (total := d.get("total_bytes") or d.get("total_bytes_estimate")):
            pct = int(d.get("downloaded_bytes", 0) * 100 / total)
            if pct != ultimo[0] and pct % 5 == 0:
                print(f"[2/3] Baixando o áudio: {pct}%", flush=True)
                ultimo[0] = pct

    opcoes = {**opcoes_base, "format": "bestaudio/best", "outtmpl": temporario + ".%(ext)s",
              "progress_hooks": [progresso],
              # MP3 de melhor qualidade (VBR V0)
              "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}]}
    print(f"[2/3] Baixando o áudio de \"{titulo}\"...", flush=True)
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url_video])
    except Exception as e:
        print(f"Erro: o download falhou: {e}")
        return 1
    finally:
        for n in os.listdir(pasta_temp):  # sobras do download (.webm, .part...)
            if n.startswith(video_id) and not n.endswith(".mp3"):
                try:
                    os.remove(os.path.join(pasta_temp, n))
                except OSError:
                    pass
    if not os.path.isfile(temporario + ".mp3"):
        print("Erro: o FFmpeg não gerou o MP3.")
        return 1
    print("[3/3] Salvando em audio\\...", flush=True)
    os.replace(temporario + ".mp3", os.path.join(PASTA_AUDIO, nome))
    try:
        os.rmdir(pasta_temp)  # só se ficou vazia (outro download pode estar usando)
    except OSError:
        pass
    _registrar_origem(nome, {"url": url_video, "video_id": video_id, "titulo": titulo, "canal": canal,
                             "baixado_em": datetime.now().isoformat(timespec="seconds")})
    print(f"Download finalizado! audio\\{nome}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
