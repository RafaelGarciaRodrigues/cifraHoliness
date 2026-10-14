"""Mudanças de tom (modulação) ao longo da música, a partir dos acordes detectados.

O solo.py detecta UM tom para a música inteira. Quando a música modula (ex.: sobe um tom no último
refrão), tudo o que vem depois era avaliado no tom errado: notas certas apareciam como "fora do tom"
e a varinha/autotune puxavam para a escala errada.

Aqui cada acorde "vota" nos tons em cujo campo harmônico ele cabe (peso = duração), e uma busca de
Viterbi escolhe a sequência de tons com uma penalidade por troca, para não trocar de tom a cada
acorde emprestado. Trechos curtos demais voltam ao tom vizinho. Só usa os acordes: roda em
milissegundos e serve também para músicas já processadas (o app.py calcula na hora).

Resultado: [{"t", "d", "tonica", "modo"}], cobrindo a música do início ao fim; um item só quando não
há modulação.
"""

# graus (semitons a partir da tônica, tipo do acorde) do campo harmônico, os mesmos do solo.py
GRAUS = {
    "maior": [(0, ""), (2, "m"), (4, "m"), (5, ""), (7, ""), (7, "7"), (9, "m"), (0, "7")],
    "menor": [(0, "m"), (3, ""), (5, "m"), (7, ""), (7, "7"), (7, "m"), (8, ""), (10, ""), (10, "7")],
}
PENALIDADE_TROCA = 12.0   # segundos de acordes "a favor" que uma modulação precisa somar
BONUS_TONICA = 0.5        # o acorde da tônica conta mais (distingue tons vizinhos que dividem acordes)
BONUS_TOM_GERAL = 0.15    # empate: fica o tom detectado para a música inteira
DURACAO_MINIMA = 20.0     # segundos; trechos de tom mais curtos voltam ao tom vizinho


def _campo(tonica, modo):
    diatonicos = {((tonica + g) % 12, t) for g, t in GRAUS[modo]}
    tonico = {(tonica, "m")} if modo == "menor" else {(tonica, ""), (tonica, "7")}
    return diatonicos, tonico


def detectar_modulacoes(acordes, tom_geral, duracao=None):
    """acordes: [{"t", "d", "raiz", "tipo"}] (formato de dados/<id>.json); tom_geral: {"tonica", "modo"}."""
    if not tom_geral:
        return []
    fim = duracao or max((a["t"] + a["d"] for a in acordes), default=0.0)
    unico = [{"t": 0.0, "d": round(fim, 3), **tom_geral}]
    acordes = sorted((a for a in acordes if a.get("d", 0) > 0), key=lambda a: a["t"])
    if len(acordes) < 4:
        return unico

    # relativos (Dó maior / Lá menor) têm o mesmo campo: só considera o modo do tom geral
    modo = tom_geral["modo"]
    tons = [(t, modo) for t in range(12)]
    campos = [_campo(*k) for k in tons]
    geral = tons.index((tom_geral["tonica"], modo))

    def pontos(a, i):
        diatonicos, tonico = campos[i]
        chave = (a["raiz"], a["tipo"])
        p = a["d"] if chave in diatonicos else -a["d"]
        if chave in tonico:
            p += BONUS_TONICA * a["d"]
        if i == geral:
            p += BONUS_TOM_GERAL * a["d"]
        return p

    # Viterbi: melhor sequência de tons (um por acorde), trocar custa PENALIDADE_TROCA
    n = len(tons)
    valor = [pontos(acordes[0], i) for i in range(n)]
    voltas = []
    for a in acordes[1:]:
        melhor = max(range(n), key=lambda i: valor[i])
        novo, volta = [], []
        for i in range(n):
            fica, troca = valor[i], valor[melhor] - PENALIDADE_TROCA
            volta.append(i if fica >= troca else melhor)
            novo.append(max(fica, troca) + pontos(a, i))
        valor = novo
        voltas.append(volta)
    i = max(range(n), key=lambda k: valor[k])
    caminho = [i]
    for volta in reversed(voltas):
        i = volta[i]
        caminho.append(i)
    caminho.reverse()

    # trechos contínuos no mesmo tom
    trechos = []
    for a, i in zip(acordes, caminho):
        if trechos and trechos[-1]["i"] == i:
            trechos[-1]["fim"] = a["t"] + a["d"]
        else:
            trechos.append({"i": i, "inicio": a["t"], "fim": a["t"] + a["d"]})
    # trechos curtos (acordes emprestados, ponte de passagem) juntam-se ao anterior
    limpos = []
    for s in trechos:
        if limpos and (s["fim"] - s["inicio"] < DURACAO_MINIMA or limpos[-1]["i"] == s["i"]):
            limpos[-1]["fim"] = s["fim"]
        else:
            limpos.append(dict(s))
    if len(limpos) > 1 and limpos[0]["fim"] - limpos[0]["inicio"] < DURACAO_MINIMA:
        limpos[1]["inicio"] = limpos[0]["inicio"]
        limpos.pop(0)

    # cobre a música inteira: o 1º começa em 0 e o último vai até o fim
    resultado = []
    for k, s in enumerate(limpos):
        inicio = 0.0 if k == 0 else s["inicio"]
        final = fim if k == len(limpos) - 1 else limpos[k + 1]["inicio"]
        tonica, modo_s = tons[s["i"]]
        resultado.append({"t": round(inicio, 3), "d": round(max(final, inicio) - inicio, 3), "tonica": tonica, "modo": modo_s})
    return resultado


def tom_em(tons, tom_geral, t):
    """Tom em vigor no instante t."""
    atual = tom_geral
    for s in tons or []:
        if s["t"] <= t:
            atual = {"tonica": s["tonica"], "modo": s["modo"]}
        else:
            break
    return atual
