"""Pastas do projeto e formatos de áudio aceitos (módulo leve, compartilhado por solo.py e app.py)."""
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_AUDIO = os.path.join(BASE_DIR, "audio")

# Qualquer formato que o FFmpeg decodifique (inclui contêineres de vídeo, dos quais só o áudio é usado)
EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".m4b", ".aac", ".wma",
    ".webm", ".weba", ".mka", ".aiff", ".aif", ".aifc", ".alac", ".ape", ".wv", ".amr",
    ".ac3", ".eac3", ".dts", ".mp2", ".mpc", ".caf", ".au", ".snd", ".ra", ".tta",
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".3gp", ".3g2", ".ts", ".mpeg", ".mpg",
}


def listar_audios():
    """Nomes dos arquivos de áudio em audio/, em ordem alfabética."""
    if not os.path.isdir(PASTA_AUDIO):
        return []
    return sorted(n for n in os.listdir(PASTA_AUDIO) if os.path.splitext(n)[1].lower() in EXTENSOES_AUDIO)


def base_video(registro):
    """Nome do vídeo de karaokê da música, sem extensão: "<Artista> - <Título>" (video.py grava
    videos/<base>.mp4, ou <base> (2).mp4... se já existe; youtube.py procura por ele)."""
    titulo = registro["titulo"] or os.path.splitext(registro["arquivo"])[0]
    base = f"{registro['artista']} - {titulo}" if registro["artista"] else titulo
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .") or registro["id"]
