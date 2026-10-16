"""Muda o tom das faixas separadas de uma música, sem tocar nos arquivos originais.

Uso: python transpor.py <id> <semitons>

Cada faixa de faixas/<id>/ (menos a bateria, que não tem tom) é transposta com o Rubber Band (filtro
`rubberband` do FFmpeg, o de melhor qualidade disponível) e gravada numa pasta nova
faixas/<id>/tom<±N>_<hora>/. Só no fim o faixas/<id>/tom.json passa a apontar para ela (quantos
semitons, a pasta e de quais originais, pela data de modificação, as cópias vieram). O servidor
(app.py) entrega essas cópias no lugar das originais; "voltar ao original" apaga o tom.json (as
originais voltam a valer na hora, sem perda nenhuma) e depois as pastas.

Pasta nova a cada transposição e apagar o tom.json primeiro: no Windows não dá para apagar um arquivo
que o player está tocando; a pasta antiga fica para trás e é apagada numa próxima vez.

A transposição é sempre a partir das originais (nunca de uma cópia já transposta), para não somar
distorções. A voz mantém os formantes (não fica "de esquilo"); os instrumentos não precisam.
Reprocessar a música (as faixas originais mudam) invalida a transposição sozinho.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
SEM_TOM = {"drums"}           # percussão: fica como está
LIMITE = 12                   # semitons, para cima ou para baixo
PROCESSOS_JUNTOS = 3          # faixas transpostas ao mesmo tempo


def _ponteiro(id_musica):
    return os.path.join(PASTA_FAIXAS, id_musica, "tom.json")


def ler_transposicao(id_musica):
    """{"semitons", "pasta", "fontes": {nome: mtime}} da transposição em vigor, ou None (sem
    transposição, ou feita de faixas que já mudaram, por exemplo depois de reprocessar a música)."""
    try:
        with open(_ponteiro(id_musica), encoding="utf-8") as f:
            info = json.load(f)
        pasta = os.path.join(PASTA_FAIXAS, id_musica, os.path.basename(info["pasta"]))
        fontes = {}
        for nome, mtime in info["fontes"].items():
            original = os.path.join(PASTA_FAIXAS, id_musica, nome + ".wav")
            if not os.path.isfile(original):
                continue  # faixa apagada na tabela das faixas: as outras continuam transpostas
            if os.path.getmtime(original) != mtime or not os.path.isfile(os.path.join(pasta, nome + ".wav")):
                return None
            fontes[nome] = mtime
        return {**info, "pasta": pasta, "fontes": fontes} if info.get("semitons") and fontes else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def faixa_transposta(id_musica, nome):
    """Caminho da cópia transposta da faixa, se houver uma válida."""
    info = ler_transposicao(id_musica)
    return os.path.join(info["pasta"], nome + ".wav") if info and nome in info["fontes"] else None


def limpar_sobras(id_musica, manter=None):
    """Apaga as pastas de transposições que não estão em uso; as que o Windows não deixar apagar
    (arquivo aberto no player) ficam para a próxima vez."""
    pasta = os.path.join(PASTA_FAIXAS, id_musica)
    if not os.path.isdir(pasta):
        return
    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome)
        if nome.startswith("tom") and os.path.isdir(caminho) and caminho != manter:
            shutil.rmtree(caminho, ignore_errors=True)


def apagar(id_musica):
    """Volta ao original: sem o tom.json o servidor entrega as originais na hora."""
    if os.path.isfile(_ponteiro(id_musica)):
        os.remove(_ponteiro(id_musica))
    limpar_sobras(id_musica)


def _transpor(origem, destino, semitons, voz):
    filtro = f"rubberband=pitch={2 ** (semitons / 12):.8f}:pitchq=quality:transients=mixed"
    if voz:
        filtro += ":formant=preserved"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", origem, "-af", filtro, "-c:a", "pcm_s24le", destino],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{os.path.basename(origem)}: {r.stderr.strip() or 'o FFmpeg falhou'}")


def transpor(id_musica, semitons):
    if not semitons or abs(semitons) > LIMITE:
        raise ValueError(f"semitons deve estar entre -{LIMITE} e {LIMITE}, diferente de 0")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg não encontrado no PATH do sistema")
    pasta = os.path.join(PASTA_FAIXAS, id_musica)
    nomes = sorted(n[:-4] for n in os.listdir(pasta) if n.endswith(".wav") and n[:-4] not in SEM_TOM)
    if not nomes:
        raise RuntimeError("a música não tem faixas separadas para transpor")
    atual = ler_transposicao(id_musica)
    limpar_sobras(id_musica, manter=atual and atual["pasta"])  # restos de vezes anteriores
    nova = os.path.join(pasta, f"tom{semitons:+d}_{int(time.time())}")
    os.makedirs(nova)
    fontes = {n: os.path.getmtime(os.path.join(pasta, n + ".wav")) for n in nomes}
    print(f"Transpondo {len(nomes)} faixa(s) {semitons:+d} semitom(ns) com o Rubber Band: {', '.join(nomes)}", flush=True)
    feitas = 0

    def uma(nome):
        _transpor(os.path.join(pasta, nome + ".wav"), os.path.join(nova, nome + ".wav"), semitons, nome == "vocals")
        return nome

    try:
        with ThreadPoolExecutor(PROCESSOS_JUNTOS) as executor:
            for nome in executor.map(uma, nomes):
                feitas += 1
                print(f"[{feitas}/{len(nomes)}] {nome} transposta", flush=True)
    except BaseException:
        shutil.rmtree(nova, ignore_errors=True)  # falhou no meio: o tom anterior continua valendo
        raise
    temporario = _ponteiro(id_musica) + ".novo"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump({"semitons": semitons, "pasta": os.path.basename(nova), "fontes": fontes}, f)
    os.replace(temporario, _ponteiro(id_musica))  # a troca de tom acontece aqui, de uma vez
    limpar_sobras(id_musica, manter=nova)
    print(f"Transposição finalizada: {semitons:+d} semitom(ns)", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("uso: python transpor.py <id> <semitons>")
    try:
        transpor(sys.argv[1], int(sys.argv[2]))
    except (ValueError, RuntimeError, OSError) as e:
        print(f"Erro: {e}", flush=True)
        sys.exit(1)
