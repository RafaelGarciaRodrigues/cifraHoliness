"""Encaixe da letra na música por alinhamento forçado acústico (não depende da transcrição do Whisper).

Um modelo wav2vec2 de português (CTC, letra a letra) dá, a cada 20 ms da faixa de voz separada, a
probabilidade de cada letra. Sobre isso roda uma busca de Viterbi num grafo feito com as linhas da
letra digitada:
  - dentro de uma linha, as letras seguem em ordem (CTC: cada letra pode durar vários quadros,
    com "brancos" entre elas);
  - ao terminar uma linha, segue para a próxima (barato) ou pula para qualquer outra (refrão
    cantado de novo, verso repetido: custa um pouco mais); uma linha pode aparecer várias vezes;
  - um estado de "lixo" absorve trechos instrumentais, improvisos e "uô uô" que não estão na letra.
Resultado: onde cada linha é cantada, inclusive as repetições que a letra não escreve.

As probabilidades ficam guardadas em faixas/<id>/encaixe_ctc.npz (o 2º encaixe é instantâneo).

Uso de teste:
    python encaixe.py <id> <letra.txt>
"""
import json
import os
import re
import sys
import threading
import unicodedata

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
MODELO = "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese"
SR = 16000
TRECHO_S = 20          # o modelo roda em pedaços de 20 s (memória)
ARQUIVO_CACHE = "encaixe_ctc.npz"

# custos da busca (em log-probabilidade)
PULO = 8.0             # começar uma linha que não é a seguinte da anterior
SEGUINTE = 1.0         # começar a linha seguinte
LIXO = 1.2             # por quadro de voz no estado de lixo, abaixo do melhor que o modelo reconhece livremente
                       # (silêncio no lixo é de graça)
PAUSA = 0.3            # por quadro de silêncio dentro de uma linha (pausa longa: melhor separar)
BRANCO_VOZ = 0.5       # por quadro com voz passado num "branco" da linha: quase o custo do lixo, então
                       # uma linha só vale onde as letras dela são reconhecidas (não se estica sobre improvisos)
SILENCIO_DB = -35      # faixa de voz abaixo disso (relativo ao pico) é silêncio
VAO_MAXIMO = 4.0       # letras de uma mesma linha separadas por mais que isso (s): vale só o bloco principal
SEGURAR = 0.1          # por quadro segurando a mesma letra (evita letra "esticada" sobre o silêncio)


def _sem_torchvision_quebrado():
    """O transformers importa o torchvision se ele estiver instalado; um torchvision de outra versão do
    torch quebra o import do wav2vec2 ("operator torchvision::nms does not exist"). O wav2vec2 não usa
    o torchvision: se ele não carrega, fica marcado como ausente."""
    if "torchvision" in sys.modules:
        return
    try:
        import torchvision  # noqa: F401
    except Exception:
        for nome in [m for m in sys.modules if m == "torchvision" or m.startswith("torchvision.")]:
            del sys.modules[nome]
        sys.modules["torchvision"] = None  # find_spec devolve None: o transformers trata como não instalado


def _classes_wav2vec2():
    _sem_torchvision_quebrado()
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    return Wav2Vec2ForCTC, Wav2Vec2Processor


ERRO_IMPORT = None  # por que o encaixe pela voz não está disponível (mostrado na interface)


def disponivel():
    global ERRO_IMPORT
    try:
        import torch  # noqa: F401
        _classes_wav2vec2()
        ERRO_IMPORT = None
        return True
    except Exception as e:  # ImportError, ou um pacote quebrado (RuntimeError...)
        ERRO_IMPORT = f"{type(e).__name__}: {e}"
        return False


# ---------------------------------------------------------------- probabilidades (CTC)
def _carregar_modelo():
    Wav2Vec2ForCTC, Wav2Vec2Processor = _classes_wav2vec2()
    processador = Wav2Vec2Processor.from_pretrained(MODELO)
    modelo = Wav2Vec2ForCTC.from_pretrained(MODELO)
    modelo.eval()
    return processador, modelo


def _energia_db(y, passo, quadros):
    """Volume da voz (dB relativos ao pico) em cada quadro do modelo."""
    import librosa
    hop = max(1, int(round(passo * SR)))
    rms = librosa.feature.rms(y=y, frame_length=2 * hop, hop_length=hop, center=True)[0]
    db = librosa.amplitude_to_db(rms, ref=np.max)
    if len(db) < quadros:
        db = np.pad(db, (0, quadros - len(db)), constant_values=-80)
    return db[:quadros].astype(np.float32)


def emissoes(id_musica, caminho_voz=None):
    """(logp [quadros x vocabulário], volume da voz em dB por quadro, segundos por quadro,
    vocabulário {letra: índice}, índice do branco)"""
    pasta = os.path.join(PASTA_FAIXAS, id_musica)
    caminho_voz = caminho_voz or os.path.join(pasta, "vocals.wav")
    cache = os.path.join(pasta, ARQUIVO_CACHE)
    if os.path.isfile(cache) and os.path.getmtime(cache) >= os.path.getmtime(caminho_voz):
        d = np.load(cache, allow_pickle=False)
        if str(d["modelo"]) == MODELO and "db" in d:
            vocab = json.loads(str(d["vocab"]))
            return d["logp"].astype(np.float32), d["db"], float(d["passo"]), vocab, int(d["branco"])

    import librosa
    import torch
    processador, modelo = _carregar_modelo()
    y, _ = librosa.load(caminho_voz, sr=SR, mono=True)
    pico = np.max(np.abs(y)) or 1.0
    y = y / pico * 0.9
    partes = []
    with torch.inference_mode():
        for i in range(0, len(y), TRECHO_S * SR):
            pedaco = y[i:i + TRECHO_S * SR]
            if len(pedaco) < SR // 10:
                break
            entrada = processador(pedaco, sampling_rate=SR, return_tensors="pt").input_values
            logits = modelo(entrada).logits[0]
            partes.append(torch.log_softmax(logits, dim=-1).numpy())
    logp = np.concatenate(partes).astype(np.float32)
    passo = len(y) / SR / len(logp)
    vocab = processador.tokenizer.get_vocab()
    branco = processador.tokenizer.pad_token_id
    db = _energia_db(y, passo, len(logp))
    np.savez_compressed(cache, logp=logp.astype(np.float16), db=db, passo=passo, vocab=json.dumps(vocab),
                        branco=branco, modelo=MODELO)
    return logp, db, passo, vocab, branco


# ---------------------------------------------------------------- texto -> letras do modelo
def tokens(linha, vocab):
    """Letras da linha que o modelo conhece, em minúsculas; palavras separadas por "|"."""
    texto = unicodedata.normalize("NFC", linha.lower())
    palavras = []
    for palavra in re.findall(r"[^\W\d_]+", texto):
        ids = [vocab[c] if c in vocab else vocab.get(_sem_acento(c)) for c in palavra]
        ids = [i for i in ids if i is not None]
        if ids:
            palavras.append(ids)
    sep = vocab.get("|")
    resultado = []
    for k, ids in enumerate(palavras):
        if k and sep is not None:
            resultado.append(sep)
        resultado.extend(ids)
    return resultado


def _sem_acento(c):
    return unicodedata.normalize("NFD", c)[0]


# ---------------------------------------------------------------- busca (Viterbi)
def _bloco_principal(trecho, passo):
    """Uma linha cujas letras se espalham (ex.: improviso no fim) fica só com o maior bloco de letras
    sem vão maior que VAO_MAXIMO."""
    k, a, b, letras = trecho
    quadros = sorted(letras.values())
    if not quadros:
        return trecho
    blocos, atual = [], [quadros[0]]
    for q in quadros[1:]:
        if (q - atual[-1]) * passo > VAO_MAXIMO:
            blocos.append(atual)
            atual = []
        atual.append(q)
    blocos.append(atual)
    if len(blocos) == 1:
        return trecho
    maior = max(blocos, key=len)
    fim = b if maior is blocos[-1] else max(q for q in quadros if q <= maior[-1])
    return [k, maior[0], fim, letras]


def encaixar(linhas, logp, db, vocab, branco, passo):
    """Devolve [(índice da linha, quadro inicial, quadro final)] na ordem do tempo."""
    T = len(logp)
    seqs = [tokens(l, vocab) for l in linhas]
    validas = [k for k, s in enumerate(seqs) if s]
    if not validas:
        return []
    # estados: para cada linha, branco, l1, branco, l2, ..., ln, branco
    rot, ini, fim = [], [], []
    for k in range(len(linhas)):
        ini.append(len(rot))
        s = seqs[k]
        if s:
            for c in s:
                rot.extend([branco, c])
            rot.append(branco)
        fim.append(len(rot))
    rot = np.array(rot, dtype=np.int64)
    S, n = len(rot), len(linhas)
    linha_de = np.zeros(S, dtype=np.int64)
    pode_pular2 = np.zeros(S, dtype=bool)   # pular o branco entre duas letras diferentes
    eh_inicio = np.zeros(S, dtype=bool)     # 1º branco ou 1ª letra: onde se entra na linha
    primeiro = np.zeros(S, dtype=bool)      # 1º branco: não vem do estado anterior (é de outra linha)
    for k in validas:
        a, b = ini[k], fim[k]
        linha_de[a:b] = k
        eh_inicio[a] = eh_inicio[a + 1] = True
        primeiro[a] = True
        for s in range(a + 2, b):
            pode_pular2[s] = rot[s] != branco and rot[s] != rot[s - 2]
    finais = np.array([fim[k] - 1 for k in validas] + [fim[k] - 2 for k in validas])  # branco final / última letra

    NEG = -1e30
    silencio = db < SILENCIO_DB
    lixo_quadro = np.where(silencio, 0.0, logp.max(axis=1) - LIXO)
    eh_branco = rot == branco
    v = np.full(S, NEG)
    lixo = np.full(n + 1, NEG)  # lixo depois da linha k (k = n: antes de qualquer linha)
    lixo[n] = 0.0
    # caminho de volta: movimento dentro da linha (0 fica, 1 anterior, 2 duas antes, 3 entrou) e de onde entrou
    mov = np.zeros((T, S), dtype=np.int8)
    entrou_de = np.zeros((T, n), dtype=np.int32)    # estado de saída (>=0) ou -1-k (lixo depois de k)
    lixo_de = np.zeros((T, n + 1), dtype=np.int32)  # -1: ficou no lixo; senão o estado final de onde veio

    seguinte_de = np.full(n, -1)  # linha válida anterior a cada linha (para "seguinte")
    ant = None
    for k in validas:
        seguinte_de[k] = ant if ant is not None else n
        ant = k
    validas_arr = np.array(validas)

    for t in range(T):
        e = logp[t, rot] - np.where(eh_branco, PAUSA if silencio[t] else BRANCO_VOZ, 0.0)
        # saída de cada linha (melhor entre branco final e última letra), no quadro anterior
        saida_val = np.full(n, NEG)
        saida_est = np.zeros(n, dtype=np.int64)
        for k in validas:
            a, b = fim[k] - 2, fim[k] - 1
            if v[a] >= v[b]:
                saida_val[k], saida_est[k] = v[a], a
            else:
                saida_val[k], saida_est[k] = v[b], b
        # melhor origem para entrar numa linha: saída de linha ou lixo
        fonte_val = np.concatenate([saida_val, lixo])                # 0..n-1 saídas, n..2n lixo
        fonte_cod = np.concatenate([saida_est, -1 - np.arange(n + 1)])
        melhor = int(np.argmax(fonte_val))
        pulo_val, pulo_cod = fonte_val[melhor] - PULO, fonte_cod[melhor]
        entrada_val = np.full(n, NEG)
        entrada_cod = np.zeros(n, dtype=np.int64)
        for k in validas:
            p = seguinte_de[k]
            if p == n:
                sv, sc = lixo[n], -1 - n
            else:
                sv, sc = (saida_val[p], saida_est[p]) if saida_val[p] >= lixo[p] else (lixo[p], -1 - p)
            sv -= SEGUINTE
            if sv >= pulo_val:
                entrada_val[k], entrada_cod[k] = sv, sc
            else:
                entrada_val[k], entrada_cod[k] = pulo_val, pulo_cod
        entrou_de[t] = entrada_cod
        # lixo: fica, ou vem da saída da linha k
        novo_lixo = lixo.copy()
        de = np.full(n + 1, -1, dtype=np.int64)
        melhora = saida_val > lixo[:n]
        novo_lixo[:n][melhora] = saida_val[melhora]
        de[:n][melhora] = saida_est[melhora]
        lixo_de[t] = de
        novo_lixo += lixo_quadro[t]

        # dentro das linhas (CTC)
        fica = v - np.where(eh_branco, 0.0, SEGURAR)
        um = np.concatenate([[NEG], v[:-1]])
        um[primeiro] = NEG
        dois = np.concatenate([[NEG, NEG], v[:-2]])
        dois[~pode_pular2] = NEG
        entra = np.full(S, NEG)
        for k in validas:
            entra[ini[k]] = entra[ini[k] + 1] = entrada_val[k]
        pilha = np.stack([fica, um, dois, entra])
        escolha = np.argmax(pilha, axis=0)
        v = pilha[escolha, np.arange(S)] + e
        mov[t] = escolha
        lixo = novo_lixo

    # final: melhor entre lixo e saídas de linha
    cand = [(lixo[k], -1 - k) for k in range(n + 1)] + [(v[s], int(s)) for s in finais]
    _, estado = max(cand)
    trechos = []
    atual = None  # [linha, primeiro quadro, último quadro com letra]
    t = T - 1
    while t >= 0:
        if estado < 0:  # no lixo depois da linha -1-estado
            k = -1 - estado
            origem = lixo_de[t][k] if k < n else -1
            if origem >= 0:
                estado = int(origem)
            t -= 1
            continue
        s = estado
        k = int(linha_de[s])
        if rot[s] != branco:
            if atual is None or atual[0] != k:
                atual = [k, t, t, {}]
                trechos.append(atual)
            atual[1] = t
            atual[3][s] = t  # quadro em que a letra começa (o menor visto voltando)
        m = mov[t][s]
        if m == 0:
            estado = s
        elif m == 1:
            estado = s - 1
        elif m == 2:
            estado = s - 2
        else:  # entrou nesta linha no quadro t: veio do que estava em t-1
            estado = int(entrou_de[t][k])
            atual = None
        t -= 1
    trechos.reverse()
    trechos = [_bloco_principal(tr, passo) for tr in trechos]
    if DIAGNOSTICO:
        ivocab = {i: c for c, i in vocab.items()}
        for k, a, b, letras in trechos:
            print(" ", linhas[k][:30], " ".join(f"{ivocab.get(int(rot[s]), '?')}@{q * passo:.1f}" for s, q in sorted(letras.items())))
    return [(k, a, b) for k, a, b, _ in trechos]


DIAGNOSTICO = False  # True: imprime o quadro de cada letra encaixada
TRAVA = threading.Lock()  # um encaixe por vez (o modelo ocupa a CPU e ~1,5 GB de memória)


def encaixar_musica(id_musica, linhas):
    """[{linha, inicio, fim}] em segundos, na ordem do tempo."""
    with TRAVA:
        logp, db, passo, vocab, branco = emissoes(id_musica)
    return [{"linha": k, "inicio": round(a * passo, 3), "fim": round((b + 1) * passo, 3)}
            for k, a, b in encaixar(linhas, logp, db, vocab, branco, passo)]


if __name__ == "__main__":
    import time
    id_musica, arquivo = sys.argv[1], sys.argv[2]
    linhas = [l.strip() for l in open(arquivo, encoding="utf-8") if l.strip() and not l.startswith(("[", "("))]
    t0 = time.time()
    resultado = encaixar_musica(id_musica, linhas)
    print(f"{len(resultado)} frases em {time.time() - t0:.1f} s")
    for r in resultado:
        m, s = divmod(r["inicio"], 60)
        print(f"{int(m)}:{s:05.2f}  {r['fim'] - r['inicio']:5.2f}s  {linhas[r['linha']]}")
