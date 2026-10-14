"""Varinha mágica: reprocessa as notas de UMA faixa para corrigir os erros típicos da transcrição.

O basic-pitch (solo.py) é um transcritor polifônico genérico e, rodado de novo, dá exatamente as
mesmas notas. Aqui a 2ª passada usa outro caminho:

- Voz (vocals): detector de altura monofônico (pYIN do librosa) -> curva de altura contínua com a
  probabilidade de haver voz. A curva é suavizada (mediana: tira o vibrato), arredondada para o
  semitom com preferência pelas notas do tom e segmentada com histerese (só troca de nota se a nova
  altura se mantiver por TROCA_MINIMA). Resolve notas que não existem, notas quebradas e notas longas
  demais (a nota acaba quando a voz para). As palavras da letra (letraPalavras) indicam onde uma
  sílaba nova começa na mesma altura.
- Instrumentos (e o solo, faixa a faixa): as notas do basic-pitch ficam, mas passam por limpeza:
  notas iguais seguidas sem novo ataque são unidas, o fim de cada nota é cortado quando o som cai e
  notas muito curtas fora do tom são descartadas.

Nada é gravado aqui: o app.py devolve as notas para a interface, que aplica (com Ctrl+Z) e salva.

Uso de teste:
    python afinar.py <id> <fonte>
"""
import json
import os
import sys

import numpy as np

import tonalidade

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
PASTA_DADOS = os.path.join(BASE_DIR, "dados")

SR = 16000
HOP = 160                   # 10 ms por quadro
QUADRO = 1024               # 64 ms: cabe dois períodos de C2
PASSO = HOP / SR
ESCALA_DO_TOM = {"maior": [0, 2, 4, 5, 7, 9, 11], "menor": [0, 2, 3, 5, 7, 8, 10]}

# voz
PROB_VOZ_MINIMA = 0.05      # probabilidade de haver voz (pYIN) abaixo disso = silêncio; baixa de propósito:
                            # com voz forte, mais aguda ou com backing vocal (ex.: depois de uma modulação)
                            # a confiança cai muito, mas a altura continua certa; a energia separa o silêncio
PROB_AFINACAO = 0.3         # só os quadros com essa confiança entram no cálculo da afinação geral
LIMIAR_SILENCIO_DB = -40    # relativo ao pico da faixa
LIMIAR_VOZ_FORTE_DB = -20   # acima disso a confiança do pYIN não é exigida
JANELA_MEDIANA = 9          # quadros (90 ms): suaviza o vibrato
VIES_TOM = 0.3              # semitons: na dúvida entre duas notas vizinhas, fica a do tom
TROCA_MINIMA = 0.07         # segundos que uma altura nova precisa durar para virar nota nova
DURACAO_MINIMA = 0.08       # notas mais curtas são descartadas
JUNTAR_ATE = 0.12           # intervalo máximo entre duas notas iguais para virarem uma só
QUEDA_SILABA_DB = 4         # queda de energia que confirma uma sílaba nova na mesma altura
DESLIZE_MAXIMO = 0.2        # segundos: nota mais curta que isso, colada numa vizinha a até 2 semitons...
DESLIZE_DESVIO = 0.25       # ...com a curva desviada isso (semitons) em direção à vizinha, é o cantor
                            # deslizando para a nota (entrada por baixo/cima) ou saindo dela: vira parte da vizinha

# instrumentos
JUNTAR_INSTRUMENTO = 0.08   # notas iguais separadas por menos que isso, sem novo ataque, viram uma
ATAQUE_MINIMO_DB = 3        # subida de energia que indica um ataque de verdade
QUEDA_FIM_DB = 18           # a nota acaba quando o som cai isso abaixo do pico dela
CURTA_FORA_DO_TOM = 0.1     # notas fora do tom mais curtas que isso são descartadas


def _carregar(caminho):
    import librosa
    y, _ = librosa.load(caminho, sr=SR, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=QUADRO, hop_length=HOP, center=True)[0]
    db = 20 * np.log10(rms + 1e-9)
    return y, db - db.max()


def _quadro(t, total):
    return int(min(max(round(t / PASSO), 0), total - 1))


def _escalas(tons, tom):
    """Função t -> escala do tom em vigor no instante t (a música pode modular)."""
    trechos = [(s["t"], _escala(s)) for s in tons or []]
    geral = _escala(tom)

    def escala_em(t):
        atual = geral
        for inicio, escala in trechos:
            if inicio <= t:
                atual = escala
            else:
                break
        return atual
    return escala_em


def _escala(tom):
    if not tom or tom.get("modo") not in ESCALA_DO_TOM:
        return None
    return {(tom["tonica"] + g) % 12 for g in ESCALA_DO_TOM[tom["modo"]]}


def _no_tom(midi, escala):
    return escala is None or midi % 12 in escala


def _quantizar(m, escala):
    """Arredonda para o semitom; se cair fora do tom e a vizinha do tom estiver quase tão perto, usa ela."""
    r = int(round(m))
    if _no_tom(r, escala):
        return r
    for n in sorted((r - 1, r + 1), key=lambda n: abs(m - n)):
        if _no_tom(n, escala) and abs(m - n) < 0.5 + VIES_TOM:
            return n
    return r


def _trechos(mascara):
    """[(início, fim)] dos trechos contínuos verdadeiros."""
    d = np.diff(np.concatenate(([0], mascara.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _inicios_silabas(letra_palavras):
    inicios = []
    for frase in letra_palavras or []:
        for p in frase.get("palavras") or []:
            if isinstance(p.get("inicio"), (int, float)):
                inicios.append(float(p["inicio"]))
    return np.array(sorted(inicios))


def _ha_silaba(inicios, t0, t1):
    return len(inicios) and np.any((inicios > t0) & (inicios < t1))


def notas_voz(caminho, escala_em, letra_palavras=None):
    import librosa
    from scipy.signal import medfilt

    y, db = _carregar(caminho)
    f0, voz, prob = librosa.pyin(y, sr=SR, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
                                 frame_length=QUADRO, hop_length=HOP, center=True)
    n = min(len(f0), len(db))
    f0, voz, prob, db = f0[:n], voz[:n], prob[:n], db[:n]
    # com a voz forte, vale a decisão do pYIN (voz/sem voz) mesmo com confiança quase nula: é o caso de
    # voz com backing vocal, em que a confiança oscila quadro a quadro e picotaria as notas
    ativo = voz & np.isfinite(f0) & (db > LIMIAR_SILENCIO_DB) & ((prob >= PROB_VOZ_MINIMA) | (db > LIMIAR_VOZ_FORTE_DB))
    altura = np.full(n, np.nan)
    altura[ativo] = librosa.hz_to_midi(f0[ativo])
    # afinação geral da gravação (cantor/banda fora do Lá 440): desconta o desvio típico de todas as notas
    confiante = ativo & (prob >= PROB_AFINACAO)
    if confiante.any():
        desvio = altura[confiante] - np.round(altura[confiante])
        altura -= float(np.angle(np.mean(np.exp(2j * np.pi * desvio))) / (2 * np.pi))

    troca = max(1, round(TROCA_MINIMA / PASSO))
    suave = np.full(n, np.nan)  # curva já suavizada (para reconhecer os deslizes)
    brutas = []  # (quadro inicial, quadro final, midi)
    for a, b in _trechos(ativo):
        k = min(JANELA_MEDIANA, b - a if (b - a) % 2 else b - a - 1)  # a mediana pede janela ímpar
        trecho = medfilt(altura[a:b], k) if k >= 3 else altura[a:b]
        suave[a:b] = trecho
        q = [_quantizar(m, escala_em((a + k) * PASSO)) for k, m in enumerate(trecho)]
        atual, inicio, i = q[0], 0, 1
        while i < len(q):
            if q[i] == atual:
                i += 1
                continue
            j = i
            while j < len(q) and q[j] == q[i]:
                j += 1
            if j - i >= troca:  # altura nova estável: começa outra nota
                brutas.append((a + inicio, a + i, atual))
                atual, inicio = q[i], i
            i = j  # oscilação curta: fica na nota atual
        brutas.append((a + inicio, b, atual))

    silabas = _inicios_silabas(letra_palavras)
    # sílaba nova na mesma altura: divide a nota onde a palavra começa, se a energia confirmar
    divididas = []
    for a, b, midi in brutas:
        cortes = [a]
        if len(silabas):
            t0, t1 = a * PASSO + 0.1, b * PASSO - 0.1
            for t in silabas[(silabas > t0) & (silabas < t1)]:
                k = _quadro(t, n)
                vizinho = db[max(a, k - 5):k + 5]
                if len(vizinho) and np.median(db[a:b]) - vizinho.min() >= QUEDA_SILABA_DB:
                    cortes.append(k)
        cortes.append(b)
        divididas += [(c0, c1, midi) for c0, c1 in zip(cortes, cortes[1:]) if c1 > c0]

    # notas quebradas: iguais, quase encostadas e sem sílaba nova entre elas viram uma só
    notas = []
    for a, b, midi in divididas:
        if notas:
            pa, pb, pm = notas[-1]
            if pm == midi and (a - pb) * PASSO < JUNTAR_ATE and not _ha_silaba(silabas, pb * PASSO - 0.05, a * PASSO + 0.05):
                notas[-1] = (pa, b, midi)
                continue
        notas.append((a, b, midi))
    notas = _absorver_deslizes(notas, suave, silabas)

    return [{"t": round(float(a * PASSO), 3), "d": round(float((b - a) * PASSO), 3), "midi": int(midi)}
            for a, b, midi in notas if (b - a) * PASSO >= DURACAO_MINIMA and 0 <= midi <= 127]


def _absorver_deslizes(notas, suave, silabas):
    """Entrada deslizada ("scoop": começa abaixo e sobe até a nota) e saída deslizada (cai no fim) viram
    notinhas curtas de meio/um tom ao lado da nota de verdade. Se a nota curta encosta numa vizinha pelo menos tão
    longa, a até 2 semitons, a curva dela está puxada na direção da vizinha e não há sílaba nova entre as
    duas, ela é absorvida pela vizinha."""
    notas = list(notas)
    i = 0
    while i < len(notas):
        a, b, m = notas[i]
        curva = suave[a:b]
        curva = curva[np.isfinite(curva)]
        absorvida = False
        if (b - a) * PASSO < DESLIZE_MAXIMO and len(curva):
            media = float(curva.mean())
            for j in (i + 1, i - 1):  # a seguinte (entrada deslizada) ou a anterior (saída)
                if not 0 <= j < len(notas):
                    continue
                ja, jb, jm = notas[j]
                fronteira = b if j > i else a
                intervalo = (ja - b) if j > i else (a - jb)
                if (intervalo * PASSO > 0.05 or not 0 < abs(jm - m) <= 2 or jb - ja < b - a
                        or (media - m) * np.sign(jm - m) < DESLIZE_DESVIO
                        or _ha_silaba(silabas, fronteira * PASSO - 0.05, fronteira * PASSO + 0.05)):
                    continue
                notas[j] = (min(a, ja), max(b, jb), jm)
                del notas[i]
                absorvida = True
                break
        if absorvida:
            i = max(0, i - 1)  # a vizinha cresceu: reavalia a partir dela
        else:
            i += 1
    return notas


def limpar_instrumento(notas, db, escala_em):
    """Pós-processamento das notas do basic-pitch de uma faixa de instrumento (db: energia da faixa)."""
    total = len(db)
    notas = sorted((dict(n) for n in notas), key=lambda n: n["t"])

    def ataque(t):
        k = _quadro(t, total)
        antes, depois = db[max(0, k - 5):k + 1], db[k:k + 6]
        return len(antes) and len(depois) and depois.max() - antes.min() >= ATAQUE_MINIMO_DB

    unidas = []
    for n in notas:
        if unidas:
            p = unidas[-1]
            fim = p["t"] + p["d"]
            if p["midi"] == n["midi"] and n["t"] - fim < JUNTAR_INSTRUMENTO and not ataque(n["t"]):
                p["d"] = round(max(fim, n["t"] + n["d"]) - p["t"], 3)
                continue
        unidas.append(n)

    for n in unidas:  # corta o fim quando o som cai bem abaixo do pico da nota
        a, b = _quadro(n["t"], total), _quadro(n["t"] + n["d"], total) + 1
        if b - a < 3:
            continue
        trecho = db[a:b]
        pico = int(np.argmax(trecho))
        caiu = np.flatnonzero(trecho[pico:] < trecho[pico] - QUEDA_FIM_DB)
        if len(caiu):
            n["d"] = round(max(DURACAO_MINIMA, (pico + caiu[0]) * PASSO), 3)

    return [n for n in unidas
            if n["d"] >= DURACAO_MINIMA and (n["d"] >= CURTA_FORA_DO_TOM or _no_tom(n["midi"], escala_em(n["t"])))]


def reprocessar(id_musica, fonte):
    """Devolve (notas novas da fonte, descrição do método). Não grava nada."""
    with open(os.path.join(PASTA_DADOS, f"{id_musica}.json"), encoding="utf-8") as f:
        dados = json.load(f)
    melodias = dados.get("melodias", {})
    if fonte not in melodias:
        raise KeyError(f"fonte de notas desconhecida: {fonte}")
    tom = dados.get("tom")
    tons = dados.get("tons")
    if tons is None:
        tons = tonalidade.detectar_modulacoes(dados.get("acordes") or [], tom, dados.get("duracao"))
    escala_em = _escalas(tons, tom)
    pasta = os.path.join(PASTA_FAIXAS, id_musica)
    wav = lambda f: os.path.join(pasta, f"{f}.wav")

    if fonte == "vocals":
        if not os.path.isfile(wav("vocals")):
            raise FileNotFoundError("faixa de voz (vocals.wav) não encontrada; processe a música de novo")
        return notas_voz(wav("vocals"), escala_em, dados.get("letraPalavras")), "voz: detector de altura pYIN"

    energias = {}

    def energia(f):
        if f not in energias:
            if not os.path.isfile(wav(f)):
                raise FileNotFoundError(f"faixa {f}.wav não encontrada; processe a música de novo")
            energias[f] = _carregar(wav(f))[1]
        return energias[f]

    notas = melodias[fonte]
    if fonte != "solo":
        return limpar_instrumento(notas, energia(fonte), escala_em), "instrumento: limpeza das notas"
    # solo: cada nota veio de uma faixa (f); limpa cada faixa com a energia dela
    resultado = []
    for f in sorted({n.get("f") for n in notas if n.get("f")}):
        resultado += [{**n, "f": f} for n in limpar_instrumento([n for n in notas if n.get("f") == f], energia(f), escala_em)]
    resultado += [n for n in notas if not n.get("f")]
    return sorted(resultado, key=lambda n: n["t"]), "solo: limpeza das notas, faixa a faixa"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    antes = len(json.load(open(os.path.join(PASTA_DADOS, f"{sys.argv[1]}.json"), encoding="utf-8"))["melodias"][sys.argv[2]])
    novas, metodo = reprocessar(sys.argv[1], sys.argv[2])
    print(f"{metodo}: {antes} -> {len(novas)} notas")
    for n in novas[:20]:
        print(n)
