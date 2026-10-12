"""Gravações feitas na interface (microfone ou câmera) cantando/tocando junto com a música.

Ficam em midias/<id da música>/audio e midias/<id da música>/video. Ao lado de cada arquivo há
um .json com o momento da música em que a gravação começa ("inicio", em segundos; pode ser
negativo se o microfone abriu antes da música soar), a velocidade em que a música tocava durante
a gravação e a duração: é o que permite tocar a gravação sincronizada com a linha do tempo.
"""
import json
import math
import os
import re
import shutil
import subprocess
from datetime import datetime

import pastas

PASTA_MIDIAS = os.path.join(pastas.BASE_DIR, "midias")
TIPOS = ("audio", "video")
NOME = re.compile(r"^\d{8}-\d{6}(?:-\d+)?\.(webm|mp4|ogg)$")  # só nomes gerados por salvar()
TAMANHO_MAXIMO = 4 * 1024 ** 3
BLOCO = 256 * 1024


def pasta(id_musica, tipo):
    return os.path.join(PASTA_MIDIAS, id_musica, tipo)


def caminho(id_musica, tipo, arquivo):
    """Caminho de uma gravação existente, ou None."""
    if tipo not in TIPOS or not NOME.match(arquivo):
        return None
    c = os.path.join(pasta(id_musica, tipo), arquivo)
    return c if os.path.isfile(c) else None


def tipo_mime(tipo, arquivo):
    return f"{tipo}/{arquivo.rsplit('.', 1)[1]}"  # audio/webm, video/mp4, audio/ogg...


def _caminho_metadados(c):
    return os.path.splitext(c)[0] + ".json"


def _ler_metadados(c):
    try:
        with open(_caminho_metadados(c), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _item(tipo, c):
    meta = _ler_metadados(c)
    return {
        "tipo": tipo,
        "arquivo": os.path.basename(c),
        "inicio": float(meta.get("inicio") or 0),
        "velocidade": float(meta.get("velocidade") or 1),
        "duracao": meta.get("duracao"),
        "criado_em": meta.get("criado_em"),
        "tamanho": os.path.getsize(c),
    }


def listar(id_musica):
    """Gravações da música, as mais recentes primeiro (o nome do arquivo é a data e hora)."""
    itens = []
    for tipo in TIPOS:
        p = pasta(id_musica, tipo)
        if os.path.isdir(p):
            itens += [_item(tipo, os.path.join(p, n)) for n in os.listdir(p) if NOME.match(n)]
    return sorted(itens, key=lambda g: g["arquivo"], reverse=True)


def _reempacotar(bruto, destino):
    """O WebM do MediaRecorder sai sem duração nem índice, e o navegador não consegue avançar
    nele; regravar o contêiner com o FFmpeg (-c copy, sem recodificar) resolve. Sem FFmpeg, ou se
    ele falhar, guarda o arquivo como veio."""
    if shutil.which("ffmpeg"):
        comando = ["ffmpeg", "-y", "-loglevel", "error", "-i", bruto, "-c", "copy"]
        if destino.endswith(".mp4"):
            comando += ["-movflags", "+faststart"]
        try:
            r = subprocess.run(comando + [destino], capture_output=True, timeout=600)
            if r.returncode == 0 and os.path.isfile(destino) and os.path.getsize(destino) > 0:
                os.remove(bruto)
                return
        except (OSError, subprocess.SubprocessError):
            pass
        if os.path.exists(destino):
            os.remove(destino)
    os.replace(bruto, destino)


def salvar(id_musica, tipo, mime, entrada, tamanho, inicio, velocidade, duracao):
    """Grava `tamanho` bytes lidos de `entrada` como uma nova gravação e devolve o item da lista."""
    if tipo not in TIPOS:
        raise ValueError("tipo de gravação inválido")
    if not all(math.isfinite(v) for v in (inicio, velocidade)) or not 0.25 <= velocidade <= 2:
        raise ValueError("início ou velocidade inválidos")
    extensao = "mp4" if "mp4" in mime else "ogg" if "ogg" in mime else "webm"
    destino_pasta = pasta(id_musica, tipo)
    os.makedirs(destino_pasta, exist_ok=True)
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    nome, n = f"{base}.{extensao}", 1
    while os.path.exists(os.path.join(destino_pasta, nome)):
        nome, n = f"{base}-{n}.{extensao}", n + 1
    destino = os.path.join(destino_pasta, nome)
    bruto = destino + ".parte"
    try:
        with open(bruto, "wb") as f:
            restante = tamanho
            while restante > 0:
                pedaco = entrada.read(min(BLOCO, restante))
                if not pedaco:
                    raise ValueError("o envio foi interrompido")
                f.write(pedaco)
                restante -= len(pedaco)
        _reempacotar(bruto, destino)
    finally:
        if os.path.exists(bruto):
            os.remove(bruto)
    meta = {
        "inicio": round(inicio, 3),
        "velocidade": velocidade,
        "duracao": round(duracao, 3) if duracao is not None and math.isfinite(duracao) else None,
        "mime": mime,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
    }
    with open(_caminho_metadados(destino), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return _item(tipo, destino)


def atualizar(id_musica, tipo, arquivo, campos):
    """Só o "inicio" é editável (acerto fino da sincronia). Devolve o item, ou None."""
    c = caminho(id_musica, tipo, arquivo)
    if c is None:
        return None
    meta = _ler_metadados(c)
    if "inicio" in campos:
        inicio = float(campos["inicio"])
        if not math.isfinite(inicio):
            raise ValueError("início inválido")
        meta["inicio"] = round(max(-600.0, min(36000.0, inicio)), 3)
    with open(_caminho_metadados(c), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return _item(tipo, c)


def excluir(id_musica, tipo, arquivo):
    c = caminho(id_musica, tipo, arquivo)
    if c is None:
        return False
    os.remove(c)
    if os.path.exists(_caminho_metadados(c)):
        os.remove(_caminho_metadados(c))
    return True
