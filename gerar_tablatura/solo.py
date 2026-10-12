"""Pipeline de transcrição de solo:
Demucs 6 faixas (separação) -> basic-pitch (notas polifônicas) -> escolha da faixa do solo
-> melodia + acordes + tom -> letra (faster-whisper) -> dados JSON + cadastro SQLite.

Cada áudio recebe um id (8 hex do SHA-256 do arquivo): o mesmo áudio tem sempre o mesmo id,
mesmo renomeado. Resultados: faixas/<id>/, dados/<id>.json, letras/<id> - <nome>.txt,
tablaturas/<nome>.txt e o registro em musicas.db. Para ver: python app.py

Uso:
    python solo.py              # processa o único áudio da pasta audio/
    python solo.py musica.mp3   # escolhe um áudio quando houver mais de um
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

import librosa
import numpy as np
import soundfile as sf

import banco
import letra
from pastas import BASE_DIR, PASTA_AUDIO, listar_audios

PASTA_TABLATURAS = os.path.join(BASE_DIR, "tablaturas")
PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
PASTA_DADOS = os.path.join(BASE_DIR, "dados")
PASTA_LETRAS = os.path.join(BASE_DIR, "letras")

# Modelo de 6 faixas: separa guitarra e piano/teclado além de voz, bateria, baixo e "outros"
MODELO_DEMUCS = "htdemucs_6s"
FONTES_DEMUCS = ["drums", "bass", "other", "vocals", "guitar", "piano"]
ROTULOS_FAIXAS = {
    "guitar": "Guitarra / violão",
    "piano": "Piano / teclado",
    "other": "Outros instrumentos",
    "vocals": "Voz",
    "bass": "Baixo",
    "drums": "Bateria",
    "acordeon": "Acordeon / teclado (piano + outros)",
}
# O Demucs não tem faixa de acordeon: ele o reparte entre "piano" e "other", trocando de faixa
# ao longo da música. Como as faixas do Demucs somam a mistura original, somar as duas
# reconstrói o instrumento inteiro numa faixa só.
FAIXAS_COMBINADAS = {"acordeon": ["piano", "other"]}
FONTES_MELODIA = ["guitar", "acordeon", "piano", "other", "vocals"]  # faixas transcritas nota a nota
FONTES_SOLO = ["guitar", "acordeon"]                                 # candidatas ao solo automático
FONTES_HARMONIA = ["guitar", "piano", "other", "bass"]               # base para acordes e tom

SR_ANALISE = 22050
HOP_CROMA = 2048            # ~93 ms por frame de croma
AMPLITUDE_MINIMA = 0.35     # notas do basic-pitch mais fracas que isso são ignoradas
DURACAO_MINIMA = 0.06       # segundos; notas mais curtas são descartadas
JANELA_SOLO = 2.0           # segundos por janela na escolha da faixa do solo
DURACAO_MINIMA_ACORDE = 0.6
LIMIAR_SILENCIO_DB = -35    # abaixo disso (relativo ao pico) não há acorde
SEPARADOR = "=" * 50

NOMES_SUSTENIDO = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOMES_BEMOL = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
NOMES_TOM_MAIOR = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
NOMES_TOM_MENOR = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
NOMES_PT = {"C": "Dó", "D": "Ré", "E": "Mi", "F": "Fá", "G": "Sol", "A": "Lá", "B": "Si"}
TIPOS_ACORDE = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10]}
# Perfis de Krumhansl-Kessler para estimativa de tonalidade
PERFIL_MAIOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
PERFIL_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def formatar_tempo(segundos):
    centesimos = int(round(segundos * 100))
    minutos, resto = divmod(centesimos, 6000)
    segs, cent = divmod(resto, 100)
    return f"{minutos:02d}:{segs:02d}.{cent:02d}"


# ---------------------------------------------------------------- nomes musicais
def usa_bemol(tom):
    tonicas_bemol = {5, 10, 3, 8, 1} if tom["modo"] == "maior" else {2, 7, 0, 5, 10, 3}
    return tom["tonica"] in tonicas_bemol


def nome_nota(midi, bemol=False):
    nomes = NOMES_BEMOL if bemol else NOMES_SUSTENIDO
    return f"{nomes[midi % 12]}{midi // 12 - 1}"


def nome_acorde(raiz, tipo, bemol=False):
    return (NOMES_BEMOL if bemol else NOMES_SUSTENIDO)[raiz] + tipo


def nome_tom(tom):
    if tom["modo"] == "maior":
        letra = NOMES_TOM_MAIOR[tom["tonica"]]
    else:
        letra = NOMES_TOM_MENOR[tom["tonica"]]
    acidente = " sustenido" if "#" in letra else " bemol" if "b" in letra else ""
    pt = NOMES_PT[letra[0]] + acidente + " " + tom["modo"]
    cifra = letra + ("m" if tom["modo"] == "menor" else "")
    return f"{cifra} ({pt})"


# ---------------------------------------------------------------- Passo 1: ingestão
def selecionar_audio(argumentos):
    if not os.path.isdir(PASTA_AUDIO):
        print(f"Erro: pasta de áudio não encontrada: {PASTA_AUDIO}")
        return None

    audios = listar_audios()

    if argumentos:
        escolhido = argumentos[0]
        if escolhido not in audios:
            print(f"Erro: '{escolhido}' não encontrado em {PASTA_AUDIO}.")
            if audios:
                print("Arquivos disponíveis:")
                for nome in audios:
                    print(f"  - {nome}")
            return None
        return os.path.join(PASTA_AUDIO, escolhido)

    if not audios:
        print(f"Erro: nenhum arquivo de áudio encontrado em {PASTA_AUDIO}.")
        return None

    if len(audios) > 1:
        processados = banco.arquivos_processados()
        print(f"Foram encontrados {len(audios)} arquivos de áudio em {PASTA_AUDIO}:")
        for nome in audios:
            print(f"  - {nome}" + ("  (já processado)" if nome in processados else ""))
        print('\nEscolha qual decodificar executando: python solo.py "<nome_do_arquivo>"')
        return None

    return os.path.join(PASTA_AUDIO, audios[0])


def verificar_dependencias():
    """Confere o basic-pitch antes da etapa demorada do Demucs."""
    if not letra.disponivel():
        print("Aviso: faster-whisper não instalado; a letra não será transcrita "
              "(python -m pip install faster-whisper).")
    faltando = []
    try:
        import basic_pitch  # noqa: F401
    except ImportError:
        faltando.append("basic-pitch")
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        faltando.append("onnxruntime")
    if faltando:
        print("Erro: dependências não instaladas: " + ", ".join(faltando))
        print("Execute:")
        print("  python -m pip install -r requirements.txt")
        print("  python -m pip install --no-deps basic-pitch==0.4.0")
        return False
    return True


def decodificar_para_wav(caminho_musica, destino, samplerate):
    """Usa o FFmpeg para converter qualquer formato em WAV estéreo."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg não encontrado no PATH do sistema.")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", caminho_musica,
         "-vn", "-ac", "2", "-ar", str(samplerate), destino],
        check=True,
    )


# ---------------------------------------------------------------- Passo 2: separação de fontes
def separar_fontes(caminho_musica, pasta_trabalho, pasta_faixas):
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    modelo = get_model(MODELO_DEMUCS)
    modelo.eval()

    caminho_wav = os.path.join(pasta_trabalho, "entrada.wav")
    decodificar_para_wav(caminho_musica, caminho_wav, modelo.samplerate)
    dados, _ = sf.read(caminho_wav, dtype="float32", always_2d=True)
    wav = torch.from_numpy(dados.T.copy())

    # Normalização igual à usada pela CLI do Demucs
    ref = wav.mean(0)
    media, desvio = ref.mean(), ref.std() + 1e-8
    wav = (wav - media) / desvio

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"      Dispositivo: {dispositivo}")
    with torch.no_grad():
        fontes = apply_model(modelo, wav[None], device=dispositivo, progress=True)[0]
    fontes = fontes * desvio + media

    # Faixas em WAV 24 bits na taxa original do modelo (44.1 kHz) para audição em alta qualidade
    os.makedirs(pasta_faixas, exist_ok=True)
    caminhos = {}
    for nome, fonte in zip(modelo.sources, fontes):
        caminho = os.path.join(pasta_faixas, f"{nome}.wav")
        sf.write(caminho, fonte.clamp(-1, 1).cpu().numpy().T, modelo.samplerate, subtype="PCM_24")
        caminhos[nome] = caminho
    combinar_faixas(caminhos, pasta_faixas)
    return caminhos


def combinar_faixas(caminhos, pasta_faixas):
    """Grava as FAIXAS_COMBINADAS (soma de faixas do Demucs) que ainda não existem."""
    for nome, partes in FAIXAS_COMBINADAS.items():
        caminho = os.path.join(pasta_faixas, f"{nome}.wav")
        if not os.path.exists(caminho):
            samplerate = sf.info(caminhos[partes[0]]).samplerate
            soma = sum(sf.read(caminhos[p], dtype="float32", always_2d=True)[0] for p in partes)
            sf.write(caminho, np.clip(soma, -1, 1), samplerate, subtype="PCM_24")
        caminhos[nome] = caminho


def faixas_ja_separadas(pasta_faixas):
    """Se o Demucs já rodou para este áudio (mesmo id), devolve os caminhos das faixas."""
    caminhos = {f: os.path.join(pasta_faixas, f"{f}.wav") for f in FONTES_DEMUCS}
    if not all(os.path.exists(c) for c in caminhos.values()):
        return None
    combinar_faixas(caminhos, pasta_faixas)
    return caminhos


def calcular_id(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()[:8]


# ---------------------------------------------------------------- Passo 3: notas e melodia
def transcrever_notas(caminhos, fontes):
    """Transcrição polifônica (basic-pitch) de cada faixa; devolve {fonte: [notas]}."""
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, predict

    modelo = Model(ICASSP_2022_MODEL_PATH)
    resultado = {}
    for fonte in fontes:
        if fonte not in caminhos:
            continue
        print(f"      {ROTULOS_FAIXAS[fonte]}...")
        _, _, eventos = predict(
            caminhos[fonte], modelo,
            onset_threshold=0.5,
            frame_threshold=0.3,
            minimum_note_length=DURACAO_MINIMA * 1000,
            minimum_frequency=librosa.note_to_hz("C2"),
            maximum_frequency=librosa.note_to_hz("C7"),
            melodia_trick=True,
        )
        resultado[fonte] = sorted(
            ({"inicio": float(ini), "fim": float(fim), "midi": int(midi), "amp": float(amp)}
             for ini, fim, midi, amp, _ in eventos),
            key=lambda n: n["inicio"],
        )
    return resultado


def extrair_melodia(notas, passo=0.01):
    """Linha melódica = nota mais aguda entre as que soam com força comparável à mais forte
    (evita que harmônicos fracos uma oitava acima virem melodia). Cada nota mantida preserva
    o próprio ataque, então notas repetidas continuam separadas."""
    notas = [n for n in notas if n["amp"] >= AMPLITUDE_MINIMA and n["fim"] - n["inicio"] >= DURACAO_MINIMA]
    if not notas:
        return []

    total = int(max(n["fim"] for n in notas) / passo) + 2
    spans = [(int(n["inicio"] / passo), max(int(n["inicio"] / passo) + 1, int(n["fim"] / passo))) for n in notas]

    amp_max = np.zeros(total)
    for n, (i0, i1) in zip(notas, spans):
        np.maximum(amp_max[i0:i1], n["amp"], out=amp_max[i0:i1])

    topo = np.full(total, -1)
    for n, (i0, i1) in zip(notas, spans):
        relevante = n["amp"] >= 0.5 * amp_max[i0:i1]
        topo[i0:i1] = np.where(relevante, np.maximum(topo[i0:i1], n["midi"]), topo[i0:i1])

    melodia = []
    for n, (i0, i1) in zip(notas, spans):
        no_topo = topo[i0:i1] == n["midi"]
        if no_topo.mean() < 0.5:
            continue
        a = int(np.argmax(no_topo))
        b = a
        while b < len(no_topo) and no_topo[b]:
            b += 1
        melodia.append({"inicio": (i0 + a) * passo, "fim": (i0 + b) * passo, "midi": n["midi"]})

    melodia.sort(key=lambda n: n["inicio"])
    for atual, proxima in zip(melodia, melodia[1:]):
        atual["fim"] = min(atual["fim"], proxima["inicio"])
    return [n for n in melodia if n["fim"] - n["inicio"] >= DURACAO_MINIMA]


def carregar_faixas(caminhos, fontes):
    return {f: librosa.load(caminhos[f], sr=SR_ANALISE, mono=True)[0] for f in fontes if f in caminhos}


def escolher_fonte_solo(melodias, notas, audios, duracao):
    """Para cada janela de JANELA_SOLO segundos, pontua as faixas candidatas (a do acordeon
    já junta piano + outros, então o solo não "pula" de faixa quando o Demucs a troca):
    volume × presença de melodia ÷ √polifonia. Instrumento que faz acordes (muitas notas
    simultâneas) perde para o que faz linha melódica. Devolve a fonte por janela."""
    candidatas = [f for f in FONTES_SOLO if f in melodias and f in audios]
    n_jan = int(np.ceil(duracao / JANELA_SOLO))
    if not candidatas or n_jan == 0:
        return [None] * n_jan

    def ocupacao(lista):
        occ = np.zeros(n_jan)
        for n in lista:
            t = n["inicio"]
            while t < n["fim"]:
                j = int(t // JANELA_SOLO)
                if j >= n_jan:
                    break
                fim_jan = (j + 1) * JANELA_SOLO
                occ[j] += min(n["fim"], fim_jan) - t
                t = fim_jan
        return occ

    pontos = np.zeros((len(candidatas), n_jan))
    tam = int(JANELA_SOLO * SR_ANALISE)
    for k, fonte in enumerate(candidatas):
        y = audios[fonte]
        rms = np.array([np.sqrt(np.mean(y[j * tam:(j + 1) * tam] ** 2)) if j * tam < len(y) else 0.0
                        for j in range(n_jan)])
        tempo_melodia = ocupacao(melodias[fonte])
        tempo_notas = ocupacao([n for n in notas[fonte] if n["amp"] >= AMPLITUDE_MINIMA])
        polifonia = np.maximum(1.0, tempo_notas / np.maximum(tempo_melodia, 1e-6))
        pontos[k] = rms * (tempo_melodia / JANELA_SOLO) / np.sqrt(polifonia)

    escolha = np.argmax(pontos, axis=0)
    fraco = pontos.max(axis=0) < 0.05 * pontos.max()
    escolha = np.where(fraco, -1, escolha)

    # Suaviza trocas rápidas de faixa: moda numa vizinhança de 5 janelas (~10 s)
    suave = escolha.copy()
    for j in range(n_jan):
        viz = escolha[max(0, j - 2):j + 3]
        suave[j] = Counter(viz.tolist()).most_common(1)[0][0]
    return [candidatas[k] if k >= 0 else None for k in suave]


def montar_melodia_solo(melodias, fonte_por_janela):
    solo = []
    for fonte in set(f for f in fonte_por_janela if f):
        for n in melodias[fonte]:
            j = min(int(n["inicio"] // JANELA_SOLO), len(fonte_por_janela) - 1)
            if fonte_por_janela[j] == fonte:
                solo.append({**n, "fonte": fonte})
    solo.sort(key=lambda n: n["inicio"])
    for atual, proxima in zip(solo, solo[1:]):
        atual["fim"] = min(atual["fim"], proxima["inicio"])
    return [n for n in solo if n["fim"] - n["inicio"] >= DURACAO_MINIMA]


def trechos_do_solo(fonte_por_janela):
    trechos = []
    for j, fonte in enumerate(fonte_por_janela):
        if fonte is None:
            continue
        if trechos and trechos[-1]["fonte"] == fonte and trechos[-1]["fim"] == j * JANELA_SOLO:
            trechos[-1]["fim"] = (j + 1) * JANELA_SOLO
        else:
            trechos.append({"inicio": j * JANELA_SOLO, "fim": (j + 1) * JANELA_SOLO, "fonte": fonte})
    return trechos


# ---------------------------------------------------------------- Passo 4: acordes e tom
def detectar_acordes(audios):
    """Croma sincronizado às batidas + gabaritos de acordes (maior, menor, 7ª) com reforço
    da nota do baixo, suavizado por Viterbi. Devolve (acordes, croma total)."""
    harmonia = sum(audios[f] for f in FONTES_HARMONIA if f in audios)
    percussao = harmonia + audios.get("drums", 0)
    baixo = audios.get("bass")

    croma = librosa.feature.chroma_cqt(y=harmonia, sr=SR_ANALISE, hop_length=HOP_CROMA, bins_per_octave=36)
    n_frames = croma.shape[1]
    if baixo is not None:
        croma_baixo = librosa.feature.chroma_cqt(y=baixo, sr=SR_ANALISE, hop_length=HOP_CROMA,
                                                 fmin=librosa.note_to_hz("C1"), n_octaves=4, bins_per_octave=36)
    else:
        croma_baixo = np.zeros_like(croma)

    # Batidas; trechos sem batida detectada (ex.: introdução sem bateria) recebem grade regular
    _, batidas = librosa.beat.beat_track(y=percussao, sr=SR_ANALISE, hop_length=HOP_CROMA)
    passo = int(np.median(np.diff(batidas))) if len(batidas) > 2 else max(1, int(0.5 * SR_ANALISE / HOP_CROMA))
    grade = [0]
    for b in list(batidas) + [n_frames]:
        while b - grade[-1] > 1.5 * passo:
            grade.append(grade[-1] + passo)
        grade.append(int(b))
    grade = librosa.util.fix_frames(np.unique(grade), x_min=0, x_max=n_frames)

    C = librosa.util.sync(croma, grade, aggregate=np.median)
    B = librosa.util.sync(croma_baixo, grade, aggregate=np.median)
    C = C / (np.linalg.norm(C, axis=0, keepdims=True) + 1e-9)
    B = B / (B.max(axis=0, keepdims=True) + 1e-9)

    rotulos, gabaritos = [], []
    for raiz in range(12):
        for tipo, intervalos in TIPOS_ACORDE.items():
            v = np.zeros(12)
            v[[(raiz + i) % 12 for i in intervalos]] = 1.0
            if tipo == "7":
                v[(raiz + 10) % 12] = 0.6
            gabaritos.append(v / np.linalg.norm(v))
            rotulos.append((raiz, tipo))
    gabaritos = np.array(gabaritos)
    raizes = np.array([r for r, _ in rotulos])

    semelhanca = gabaritos @ C + 0.15 * B[raizes]
    semelhanca[[i for i, (_, t) in enumerate(rotulos) if t == "7"]] -= 0.05  # 7ª só quando clara

    energia = librosa.util.sync(librosa.feature.rms(y=harmonia, hop_length=HOP_CROMA), grade, aggregate=np.mean)[0]
    silencio = librosa.amplitude_to_db(energia, ref=np.max) < LIMIAR_SILENCIO_DB
    semelhanca = np.vstack([semelhanca, silencio[None] * 1.2])  # último estado = "sem acorde"

    prob = np.exp(semelhanca * 12)
    prob /= prob.sum(axis=0, keepdims=True)
    caminho = librosa.sequence.viterbi_discriminative(prob, librosa.sequence.transition_loop(prob.shape[0], 0.8))

    tempos = librosa.frames_to_time(grade, sr=SR_ANALISE, hop_length=HOP_CROMA)
    segmentos = []
    for k, estado in enumerate(caminho):
        inicio, fim = tempos[k], tempos[k + 1] if k + 1 < len(tempos) else tempos[k]
        if segmentos and segmentos[-1]["estado"] == estado:
            segmentos[-1]["fim"] = fim
        else:
            segmentos.append({"estado": int(estado), "inicio": float(inicio), "fim": float(fim)})

    # Acordes curtos demais são incorporados ao anterior
    limpos = []
    for s in segmentos:
        if limpos and (s["fim"] - s["inicio"] < DURACAO_MINIMA_ACORDE or limpos[-1]["estado"] == s["estado"]):
            limpos[-1]["fim"] = s["fim"]
        else:
            limpos.append(s)

    acordes = []
    for s in limpos:
        if s["estado"] >= len(rotulos):
            continue
        raiz, tipo = rotulos[s["estado"]]
        # Mesmo acorde separado só por uma pausa curta vira um acorde só
        if acordes and (acordes[-1]["raiz"], acordes[-1]["tipo"]) == (raiz, tipo) and s["inicio"] - acordes[-1]["fim"] < 1.5:
            acordes[-1]["fim"] = s["fim"]
        else:
            acordes.append({"inicio": s["inicio"], "fim": s["fim"], "raiz": raiz, "tipo": tipo})
    return acordes, croma.sum(axis=1)


def detectar_tom(croma_total, acordes):
    """Correlação com perfis de Krumhansl-Kessler + quanto dos acordes cabe no campo harmônico,
    com bônus para o acorde da tônica (mais frequente e costuma encerrar a música)."""
    duracao = Counter()
    for a in acordes:
        duracao[(a["raiz"], a["tipo"])] += a["fim"] - a["inicio"]
    total = sum(duracao.values()) or 1.0
    ultimo = (acordes[-1]["raiz"], acordes[-1]["tipo"]) if acordes else None

    def campo(tonica, modo):
        if modo == "maior":
            graus = [(0, ""), (2, "m"), (4, "m"), (5, ""), (7, ""), (7, "7"), (9, "m"), (0, "7")]
            tonico = {(tonica, ""), (tonica, "7")}
        else:
            graus = [(0, "m"), (3, ""), (5, "m"), (7, ""), (7, "7"), (7, "m"), (8, ""), (10, ""), (10, "7")]
            tonico = {(tonica, "m")}
        diatonicos = {((tonica + g) % 12, t) for g, t in graus}
        return diatonicos, tonico

    melhor, melhor_pontos = None, -np.inf
    for tonica in range(12):
        for modo, perfil in (("maior", PERFIL_MAIOR), ("menor", PERFIL_MENOR)):
            pontos = np.corrcoef(croma_total, np.roll(perfil, tonica))[0, 1]
            diatonicos, tonico = campo(tonica, modo)
            pontos += sum(d for k, d in duracao.items() if k in diatonicos) / total
            pontos += 0.5 * sum(d for k, d in duracao.items() if k in tonico) / total
            pontos += 0.2 if ultimo in tonico else 0.0
            if pontos > melhor_pontos:
                melhor, melhor_pontos = {"tonica": tonica, "modo": modo}, pontos
    return melhor


# ---------------------------------------------------------------- Passo 5: exportação
def exportar_txt(solo, acordes, tom, caminho_musica, nome_base):
    os.makedirs(PASTA_TABLATURAS, exist_ok=True)
    caminho_txt = os.path.join(PASTA_TABLATURAS, f"{nome_base}.txt")
    bemol = usa_bemol(tom)

    linhas_notas, fonte_atual = [], None
    for n in solo:
        if n["fonte"] != fonte_atual:
            if linhas_notas:
                linhas_notas.append("")
            linhas_notas.append(f"--- solo em: {ROTULOS_FAIXAS[n['fonte']]} ---")
            fonte_atual = n["fonte"]
        linhas_notas.append(f"[{formatar_tempo(n['inicio'])}] -> {nome_nota(n['midi'], bemol)}")
    linhas_acordes = [f"[{formatar_tempo(a['inicio'])}] -> {nome_acorde(a['raiz'], a['tipo'], bemol)}"
                      for a in acordes]

    with open(caminho_txt, "w", encoding="utf-8") as f_out:
        f_out.write(f"{SEPARADOR}\n")
        f_out.write("TRANSCRIÇÃO DE SOLO AUTOMATIZADA\n")
        f_out.write(f"Arquivo de Origem: {os.path.basename(caminho_musica)}\n")
        f_out.write("Instrumento Alvo: Solo (faixa escolhida automaticamente por trecho)\n")
        f_out.write(f"Tom: {nome_tom(tom)}\n")
        f_out.write(f"{SEPARADOR}\n\n")
        f_out.write("\n".join(linhas_notas))
        f_out.write(f"\n\n{SEPARADOR}\nACORDES\n{SEPARADOR}\n\n")
        f_out.write("\n".join(linhas_acordes))
        f_out.write(f"\n\n{SEPARADOR}\n")
        f_out.write("Fim da transcrição de notas.\n")
    return caminho_txt


def exportar_dados(id_musica, solo, melodias, trechos, acordes, tom, caminho_musica, caminhos_faixas,
                   duracao, letra_palavras):
    """Grava dados/<id>.json, lido pela interface (app.py)."""
    os.makedirs(PASTA_DADOS, exist_ok=True)
    caminho = os.path.join(PASTA_DADOS, f"{id_musica}.json")

    def notas_json(lista):
        return [{"t": round(n["inicio"], 3), "d": round(n["fim"] - n["inicio"], 3), "midi": n["midi"],
                 **({"f": n["fonte"]} if "fonte" in n else {})} for n in lista]

    dados = {
        "id": id_musica,
        "origem": os.path.basename(caminho_musica),
        "duracao": round(duracao, 2),
        "tom": tom,
        "rotulos": ROTULOS_FAIXAS,
        "faixas": list(caminhos_faixas),
        "melodias": {"solo": notas_json(solo), **{f: notas_json(m) for f, m in melodias.items()}},
        "trechosSolo": [{"t": round(s["inicio"], 3), "d": round(s["fim"] - s["inicio"], 3), "f": s["fonte"]}
                        for s in trechos],
        "acordes": [{"t": round(a["inicio"], 3), "d": round(a["fim"] - a["inicio"], 3),
                     "raiz": a["raiz"], "tipo": a["tipo"]} for a in acordes],
        # tempos palavra a palavra da transcrição, usados no destaque estilo karaokê
        "letraPalavras": letra_palavras,
    }
    try:  # gravações do teclado MIDI (feitas na interface) sobrevivem a um novo processamento
        with open(caminho, encoding="utf-8") as f_in:
            anteriores = json.load(f_in).get("midi")
        if anteriores:
            dados["midi"] = anteriores
    except (OSError, ValueError):
        pass
    with open(caminho, "w", encoding="utf-8") as f_out:
        json.dump(dados, f_out, ensure_ascii=False)
    return caminho


def obter_letra(id_musica, titulo, caminho_voz):
    """Transcreve a letra só se ainda não existe arquivo em letras/ (as correções do usuário
    nunca são sobrescritas). Devolve (tempos palavra a palavra, qtd de frases, caminho)."""
    existente = letra.localizar(PASTA_LETRAS, id_musica)
    if existente:
        print(f"      Letra já existe ({os.path.basename(existente)}); mantida.")
        anterior = []
        caminho_dados = os.path.join(PASTA_DADOS, f"{id_musica}.json")
        if os.path.exists(caminho_dados):
            with open(caminho_dados, encoding="utf-8") as f:
                anterior = json.load(f).get("letraPalavras", [])
        return anterior, len(letra.ler(existente)), existente
    if not letra.disponivel():
        print("      faster-whisper não instalado; letra não transcrita.")
        return [], 0, None
    print(f"      Transcrevendo a voz (Whisper '{letra.MODELO_WHISPER}', pode demorar alguns minutos)...")
    frases = letra.transcrever(caminho_voz)
    caminho = letra.caminho_novo(PASTA_LETRAS, id_musica, titulo)
    letra.escrever(caminho, frases, titulo, id_musica)
    return frases, len(frases), caminho


# ---------------------------------------------------------------- pipeline
def analisar_faixas(caminhos):
    """Etapas 2 a 4 a partir das faixas já separadas."""
    print("[2/6] Transcrevendo notas de cada faixa (basic-pitch)...")
    notas = transcrever_notas(caminhos, FONTES_MELODIA)
    melodias = {fonte: extrair_melodia(lista) for fonte, lista in notas.items()}

    print("[3/6] Identificando o instrumento do solo em cada trecho...")
    audios = carregar_faixas(caminhos, set(FONTES_SOLO + FONTES_HARMONIA + ["drums"]))
    duracao = max(len(y) for y in audios.values()) / SR_ANALISE
    fonte_por_janela = escolher_fonte_solo(melodias, notas, audios, duracao)
    solo = montar_melodia_solo(melodias, fonte_por_janela)
    trechos = trechos_do_solo(fonte_por_janela)

    print("[4/6] Detectando acordes e tom da música...")
    acordes, croma_total = detectar_acordes(audios)
    tom = detectar_tom(croma_total, acordes)
    return solo, melodias, trechos, acordes, tom, duracao


def executar_pipeline(caminho_musica):
    arquivo = os.path.basename(caminho_musica)
    nome_base = os.path.splitext(arquivo)[0]
    id_musica = calcular_id(caminho_musica)
    print(f"Arquivo selecionado: {arquivo} (id {id_musica})")
    pasta_faixas = os.path.join(PASTA_FAIXAS, id_musica)

    # faixas de versões anteriores ficavam em faixas/<nome do arquivo>
    pasta_antiga = os.path.join(PASTA_FAIXAS, nome_base)
    if os.path.isdir(pasta_antiga) and not os.path.exists(pasta_faixas):
        os.rename(pasta_antiga, pasta_faixas)

    caminhos = faixas_ja_separadas(pasta_faixas)
    if caminhos:
        print(f"[1/6] Faixas já separadas encontradas em {pasta_faixas}; reaproveitando "
              "(apague a pasta para separar de novo).")
    else:
        pasta_trabalho = tempfile.mkdtemp(prefix="solo_pipeline_")
        try:
            print("[1/6] Separando fontes com Inteligência Artificial (Demucs, 6 faixas)...")
            caminhos = separar_fontes(caminho_musica, pasta_trabalho, pasta_faixas)
        finally:
            shutil.rmtree(pasta_trabalho, ignore_errors=True)

    solo, melodias, trechos, acordes, tom, duracao = analisar_faixas(caminhos)

    print("[5/6] Letra da música...")
    cadastro = banco.obter(id_musica)
    titulo = (cadastro or {}).get("titulo") or nome_base
    letra_palavras, qtd_frases, caminho_letra = obter_letra(id_musica, titulo, caminhos["vocals"])

    print("[6/6] Gravando transcrição, dados e cadastro...")
    caminho_txt = exportar_txt(solo, acordes, tom, caminho_musica, nome_base)
    caminho_dados = exportar_dados(id_musica, solo, melodias, trechos, acordes, tom, caminho_musica,
                                   caminhos, duracao, letra_palavras)
    banco.registrar_processamento(id_musica, arquivo, nome_base, tom, duracao, len(solo), len(acordes), qtd_frases)

    print(f"Pipeline finalizado! Tom: {nome_tom(tom)} · {len(solo)} notas do solo · "
          f"{len(acordes)} acordes · {qtd_frases} frases de letra.")
    if trechos:
        print("Solo por trecho: " + ", ".join(
            f"{formatar_tempo(t['inicio'])} {ROTULOS_FAIXAS[t['fonte']]}" for t in trechos))
    print(f"Faixas separadas: {pasta_faixas}")
    print(f"Transcrição:      {caminho_txt}")
    print(f"Dados:            {caminho_dados}")
    if caminho_letra:
        print(f"Letra:            {caminho_letra}")
    print("Para abrir a interface: python app.py")


def main():
    caminho_musica = selecionar_audio(sys.argv[1:])
    if caminho_musica is None or not verificar_dependencias():
        return 1
    executar_pipeline(caminho_musica)
    return 0


if __name__ == "__main__":
    sys.exit(main())
