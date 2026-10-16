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


TOM_MAIOR = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]  # os mesmos da interface
TOM_MENOR = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]


def cifra_tom(tonica, modo):
    """"F#", "Bb", "C#m"... (como cifraTom da interface)."""
    return (TOM_MAIOR if modo == "maior" else TOM_MENOR)[tonica % 12] + ("m" if modo == "menor" else "")


def _base_musica(registro):
    titulo = registro["titulo"] or os.path.splitext(registro["arquivo"])[0]
    base = f"{registro['artista']} - {titulo}" if registro["artista"] else titulo
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .") or registro["id"]


def base_video(registro, semitons=0):
    """Nome do vídeo de karaokê da música, sem extensão: "<Artista> - <Título> - Tom F#", com o tom em
    que o vídeo sai (o da música + os semitons das faixas transpostas). Um arquivo por tom: dá para
    publicar a mesma música em tons diferentes; criar de novo no mesmo tom substitui o anterior."""
    base = _base_musica(registro)
    if registro.get("tom_tonica") is not None:
        base += f" - Tom {cifra_tom(registro['tom_tonica'] + semitons, registro.get('tom_modo') or 'maior')}"
    return base


def padrao_videos(registro):
    """Regex dos vídeos da música em qualquer tom (e os antigos, sem o tom e/ou com " (2)")."""
    return re.compile(re.escape(_base_musica(registro)) + r"( - Tom [A-G][#b]?m?)?( \(\d+\))?\.mp4", re.IGNORECASE)
