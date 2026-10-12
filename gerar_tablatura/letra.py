"""Letra da música: transcrição da faixa de voz (faster-whisper) e o arquivo letras/<id> - <nome>.txt.

Formato do .txt (editável à mão ou pela interface):
    # comentário (ignorado)
    [00:12.40 - 00:15.90] frase cantada
O fim ("- 00:15.90") é opcional; sem ele a frase vai até o início da próxima.
"""
import glob
import os
import re

MODELO_WHISPER = "medium"   # "small" é ~3x mais rápido, mas erra mais no canto
PAUSA_FRASE = 0.6           # segundos de silêncio entre palavras que separam frases
MAX_PALAVRAS = 12           # frases maiores são quebradas na maior pausa interna
LIMIAR_VOZ_DB = -32         # frase cuja voz fica abaixo disso (relativo ao pico) é descartada
DURACAO_PADRAO = 3.0        # fim assumido para a última frase sem fim explícito

_LINHA = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)(?:\s*-\s*(\d+):(\d+(?:\.\d+)?))?\]\s*(.*)$")


def disponivel():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _tempo(segundos):
    centesimos = int(round(segundos * 100))
    minutos, resto = divmod(centesimos, 6000)
    return f"{minutos:02d}:{resto // 100:02d}.{resto % 100:02d}"


def _nome_seguro(nome):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome).strip(" .") or "musica"


# ---------------------------------------------------------------- arquivo .txt
def localizar(pasta, id_musica):
    achados = sorted(glob.glob(os.path.join(glob.escape(pasta), f"{id_musica}*.txt")))
    return achados[0] if achados else None


def caminho_novo(pasta, id_musica, nome_base):
    return os.path.join(pasta, f"{id_musica} - {_nome_seguro(nome_base)}.txt")


def ler(caminho):
    """Devolve [{inicio, fim, texto}] ordenado; fins ausentes são completados."""
    frases = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            m = _LINHA.match(linha)
            if m:
                inicio = int(m.group(1)) * 60 + float(m.group(2))
                fim = int(m.group(3)) * 60 + float(m.group(4)) if m.group(3) else None
                texto = m.group(5).strip()
            else:  # linha sem tempo: continua logo depois da frase anterior
                inicio = frases[-1]["fim"] or frases[-1]["inicio"] if frases else 0.0
                fim, texto = None, linha
            frases.append({"inicio": inicio, "fim": fim, "texto": texto})
    frases.sort(key=lambda f: f["inicio"])
    for i, f in enumerate(frases):
        proximo = frases[i + 1]["inicio"] if i + 1 < len(frases) else None
        if f["fim"] is None or f["fim"] <= f["inicio"]:
            f["fim"] = proximo if proximo is not None and proximo > f["inicio"] else f["inicio"] + DURACAO_PADRAO
    return frases


def escrever(caminho, frases, titulo, id_musica):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(f"# Letra: {titulo} (id {id_musica})\n")
        f.write("# Formato: [início - fim] frase · linhas começando com # são ignoradas\n\n")
        for fr in sorted(frases, key=lambda x: x["inicio"]):
            texto = " ".join(str(fr["texto"]).split())  # uma frase por linha
            f.write(f"[{_tempo(fr['inicio'])} - {_tempo(fr['fim'])}] {texto}\n")


# ---------------------------------------------------------------- transcrição
def _dividir_longa(palavras):
    if len(palavras) <= MAX_PALAVRAS:
        return [palavras]
    pausas = [palavras[i + 1]["inicio"] - palavras[i]["fim"] for i in range(len(palavras) - 1)]
    # corta na maior pausa, evitando pedaços de uma palavra só
    corte = max(range(1, len(palavras) - 1), key=lambda i: pausas[i - 1]) if len(palavras) > 2 else 1
    return _dividir_longa(palavras[:corte]) + _dividir_longa(palavras[corte:])


def transcrever(caminho_voz, modelo=MODELO_WHISPER):
    """Transcreve a faixa de voz separada; devolve [{inicio, fim, texto, palavras}]."""
    import librosa
    import numpy as np
    from faster_whisper import WhisperModel

    whisper = WhisperModel(modelo, device="auto", compute_type="int8")
    segmentos, _ = whisper.transcribe(
        caminho_voz, language="pt", word_timestamps=True, vad_filter=True,
        condition_on_previous_text=False,  # evita repetir/inventar texto em trechos instrumentais
        beam_size=5,
    )

    grupos = []
    for seg in segmentos:
        atual = []
        for w in seg.words or []:
            texto = w.word.strip()
            if not texto:
                continue
            if atual and w.start - atual[-1]["fim"] > PAUSA_FRASE:
                grupos.append(atual)
                atual = []
            atual.append({"inicio": round(float(w.start), 3), "fim": round(float(w.end), 3), "texto": texto})
        if atual:
            grupos.append(atual)

    # descarta "frases" onde a faixa de voz está praticamente muda (alucinação do modelo)
    y, sr = librosa.load(caminho_voz, sr=16000, mono=True)
    hop = 800  # 50 ms
    db = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=hop)[0], ref=np.max)

    frases = []
    for grupo in grupos:
        for palavras in _dividir_longa(grupo):
            i0, i1 = int(palavras[0]["inicio"] * sr / hop), int(palavras[-1]["fim"] * sr / hop) + 1
            if i0 >= len(db) or np.max(db[i0:i1]) < LIMIAR_VOZ_DB:
                continue
            frases.append({
                "inicio": palavras[0]["inicio"], "fim": palavras[-1]["fim"],
                "texto": " ".join(p["texto"] for p in palavras), "palavras": palavras,
            })
    return frases
