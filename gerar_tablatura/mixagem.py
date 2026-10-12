"""Apoio à aba Mixagem: forma de onda resumida (picos) das faixas e gravações, e exclusão de faixas.

As configurações da mixagem (volume, ganho, efeitos, deslocamento de cada faixa) ficam nas
preferências da música (musicas.db) e o som é processado no navegador; aqui só o que precisa do disco.
"""
import json
import math
import os
import shutil
import subprocess
import threading
from array import array

TAXA_PICOS = 100            # picos por segundo de áudio
_TAXA_DECODIFICACAO = 4000  # basta para achar o volume; decodificar em 44,1 kHz seria lento à toa
_cache = {}                 # (caminho, mtime, tamanho) -> resultado
_trava = threading.Lock()


def picos(caminho):
    """Pico do volume a cada 1/TAXA_PICOS s, de 0 a 255 (raiz quadrada da amplitude, para os
    trechos baixos ainda aparecerem). O FFmpeg decodifica qualquer formato: o WAV das faixas e o
    WebM/MP4 das gravações (do vídeo, só o som)."""
    info = os.stat(caminho)
    chave = (caminho, info.st_mtime_ns, info.st_size)
    with _trava:
        if chave in _cache:
            return _cache[chave]
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg não encontrado no PATH do sistema")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", caminho, "-vn", "-ac", "1", "-ar", str(_TAXA_DECODIFICACAO),
                        "-f", "s16le", "-"], capture_output=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or "o FFmpeg falhou")
    amostras = array("h")
    amostras.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
    passo = _TAXA_DECODIFICACAO // TAXA_PICOS
    valores = []
    for i in range(0, len(amostras), passo):
        bloco = amostras[i:i + passo]
        pico = max(max(bloco), -min(bloco)) / 32768
        valores.append(min(255, round(math.sqrt(pico) * 255)))
    resultado = {"taxa": TAXA_PICOS, "picos": valores}
    with _trava:
        _cache[chave] = resultado
    return resultado


def excluir_faixa(pasta_faixas, pasta_dados, id_musica, nome):
    """Apaga faixas/<id>/<nome>.wav e tira a faixa da lista em dados/<id>.json.
    Reprocessar a música (solo.py) separa de novo as faixas que faltarem."""
    caminho = os.path.join(pasta_faixas, id_musica, nome + ".wav")
    if not os.path.isfile(caminho):
        return False
    os.remove(caminho)
    caminho_dados = os.path.join(pasta_dados, f"{id_musica}.json")
    if os.path.isfile(caminho_dados):
        with open(caminho_dados, encoding="utf-8") as f:
            dados = json.load(f)
        if nome in dados.get("faixas", []):
            dados["faixas"].remove(nome)
            with open(caminho_dados, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
    return True
