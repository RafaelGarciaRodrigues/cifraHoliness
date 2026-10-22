"""Indicadores da aba "Estratégia", calculados a partir dos CSVs da coleta do Analytics
(analytics.py → pasta analytics/): canal, apostas (coluna "Aposta" da Biblioteca), vídeos
normalizados pela idade (primeiros 7 e 28 dias), origens do tráfego, termos de busca, público,
sugestões de músicas e o diário de decisões (analytics/analises/diario.json, mantido entre coletas).

Só biblioteca padrão, como o app.py. A análise escrita fica em analytics/analises/*.md.
"""
import csv
import json
import os
import re
import statistics
import threading
import unicodedata
from datetime import date, datetime, timedelta

from pastas import BASE_DIR

PASTA = os.path.join(BASE_DIR, "analytics")
PASTA_ANALISES = os.path.join(PASTA, "analises")
CAMINHO_DIARIO = os.path.join(PASTA_ANALISES, "diario.json")
TRAVA = threading.Lock()

SEM_APOSTA = "Sem aposta"
LOTE = 6               # vídeos com 7 dias de dados para concluir sobre uma aposta
MINIMO_APOSTA = 3      # abaixo disso a aposta fica "aguardando dados"
# metas de 30 dias (analytics/analises/2026-10-21 - analise e estrategia.md)
METAS = {"pct_assistido": 45, "busca_externo": 35, "v7_mediana": 30, "inscritos_por_mil": 10, "horas_semana": 15}
MONETIZACAO = {"horas": 4000, "inscritos": 1000}
# tipo de tráfego do YouTube -> grupo mostrado na tela
GRUPOS = {"RELATED_VIDEO": "sugeridos", "YT_SEARCH": "busca", "HASHTAGS": "busca", "EXT_URL": "externo",
          "NO_LINK_OTHER": "direto", "SUBSCRIBER": "inscritos", "NOTIFICATION": "inscritos",
          "YT_CHANNEL": "canal", "END_SCREEN": "canal", "PLAYLIST": "playlists", "SHORTS": "shorts"}
ORDEM_GRUPOS = ["sugeridos", "busca", "externo", "direto", "inscritos", "canal", "playlists", "shorts", "outros"]
INTENCAO = ("busca", "externo")  # quem procurou a música ou recebeu o link
ROTULOS = {"v7_mediana": "visualizações em 7 dias", "pct_assistido": "% assistido",
           "inscritos_por_mil": "inscritos por mil", "busca_externo": "busca + externo"}


def _valor(v):
    """CSV da coleta (vírgula decimal) -> int/float/str/None."""
    if v is None or v == "":
        return None
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+,\d+(e-?\d+)?", v):
        return float(v.replace(",", "."))
    return v


def _ler(nome):
    try:
        with open(os.path.join(PASTA, nome), encoding="utf-8-sig", newline="") as f:
            return [{k: _valor(v) for k, v in l.items()} for l in csv.DictReader(f, delimiter=";")]
    except OSError:
        return []


def _dia(texto):
    return date.fromisoformat(str(texto)[:10])


def _normalizar(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))).strip()


def _pct(parte, total):
    return round(parte * 100 / total, 1) if total else None


def _soma(linhas, campo):
    return sum(l.get(campo) or 0 for l in linhas)


def _media_ponderada(linhas, campo, peso="views"):
    total = _soma(linhas, peso)
    return round(sum((l.get(campo) or 0) * (l.get(peso) or 0) for l in linhas) / total, 1) if total else None


def _mediana(valores):
    valores = [v for v in valores if v is not None]
    return round(statistics.median(valores), 1) if valores else None


# ---------------------------------------------------------------- diário de decisões
DIARIO_INICIAL = [{
    "id": "d1", "data": "2026-10-21",
    "decisao": "Aposta A (playback com letra no seu tom) como principal; B (tutorial piano & violão) em teste com lote de 6; "
               "títulos no padrão de busca; criar playlists.",
    "resultado": "",
}]


def diario():
    try:
        with open(CAMINHO_DIARIO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return [dict(d) for d in DIARIO_INICIAL]


def salvar_diario(itens):
    """Grava a lista inteira (a tela edita e manda de volta); devolve a lista gravada."""
    if not isinstance(itens, list):
        raise ValueError("lista de decisões inválida")
    limpos = []
    for i, d in enumerate(itens[:500]):
        if not isinstance(d, dict):
            raise ValueError("decisão inválida")
        data = str(d.get("data") or date.today().isoformat())[:10]
        date.fromisoformat(data)  # ValueError se a data é inválida
        limpos.append({"id": str(d.get("id") or f"d{i + 1}")[:20], "data": data,
                       "decisao": str(d.get("decisao") or "").strip()[:2000],
                       "resultado": str(d.get("resultado") or "").strip()[:2000]})
    with TRAVA:
        os.makedirs(PASTA_ANALISES, exist_ok=True)
        temporario = CAMINHO_DIARIO + ".parcial"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(limpos, f, ensure_ascii=False, indent=2)
        os.replace(temporario, CAMINHO_DIARIO)
    return limpos


def analises():
    """Análises escritas (analytics/analises/*.md), da mais nova para a mais antiga."""
    if not os.path.isdir(PASTA_ANALISES):
        return []
    return sorted((n for n in os.listdir(PASTA_ANALISES) if n.lower().endswith(".md")), reverse=True)


def caminho_analise(nome):
    return os.path.join(PASTA_ANALISES, nome) if nome in analises() else None


# ---------------------------------------------------------------- indicadores
def _grupos_trafego(linhas):
    """[{insightTrafficSourceType, views, ...}] -> {grupo: views}."""
    g = {}
    for l in linhas:
        grupo = GRUPOS.get(l.get("insightTrafficSourceType"), "outros")
        g[grupo] = g.get(grupo, 0) + (l.get("views") or 0)
    return g


def _intencao(grupos):
    total = sum(grupos.values())
    return _pct(sum(grupos.get(k, 0) for k in INTENCAO), total)


def situacao():
    leia_me = os.path.join(PASTA, "leia-me.txt")
    if not os.path.isfile(leia_me):
        return {"vazio": True, "diario": diario(), "analises": analises()}
    canal = (_ler("canal.csv") or [{}])[0]
    diario_canal = sorted(_ler("diario_canal.csv"), key=lambda l: str(l["day"]))
    if not diario_canal:
        return {"vazio": True, "diario": diario(), "analises": analises()}
    ate = _dia(diario_canal[-1]["day"])
    janela = lambda linhas, dias, fim=ate: [l for l in linhas if fim - timedelta(days=dias) < _dia(l["day"]) <= fim]

    # ---- canal
    semana, anterior = janela(diario_canal, 7), janela(diario_canal, 7, ate - timedelta(days=7))
    mes = janela(diario_canal, 28)
    trafego_canal = _ler("trafego_canal.csv")
    trafego_mes = _grupos_trafego(janela(trafego_canal, 28))
    horas_ano = _soma(janela(diario_canal, 365), "estimatedMinutesWatched") / 60
    horas_semana = _soma(semana, "estimatedMinutesWatched") / 60
    inscritos = canal.get("inscritos") or 0
    kpis = {
        "horas_semana": round(horas_semana, 1),
        "horas_semana_anterior": round(_soma(anterior, "estimatedMinutesWatched") / 60, 1),
        "views_semana": _soma(semana, "views"), "views_semana_anterior": _soma(anterior, "views"),
        "inscritos": inscritos,
        "inscritos_28d": _soma(mes, "subscribersGained") - _soma(mes, "subscribersLost"),
        "pct_assistido_28d": _media_ponderada(mes, "averageViewPercentage"),
        "busca_externo_28d": _intencao(trafego_mes),
        "inscritos_por_mil_28d": round(_soma(mes, "subscribersGained") * 1000 / _soma(mes, "views"), 1) if _soma(mes, "views") else None,
        "horas_ano": round(horas_ano, 1),
        # no ritmo da última semana
        "dias_para_horas": round((MONETIZACAO["horas"] - horas_ano) / (horas_semana / 7)) if horas_semana else None,
    }

    # ---- vídeos
    totais = {l["video"]: l for l in _ler("totais_videos.csv")}
    diarios = {}
    for l in _ler("diario_videos.csv"):
        diarios.setdefault(l["video_id"], []).append(l)
    trafegos = {}
    for l in _ler("trafego_videos.csv"):
        trafegos.setdefault(l["video_id"], []).append(l)
    dispositivos = {}
    for l in _ler("dispositivos_videos.csv"):
        d = dispositivos.setdefault(l["video_id"], {})
        d[l["deviceType"]] = d.get(l["deviceType"], 0) + (l.get("views") or 0)
    detalhes = {}
    for l in _ler("trafego_detalhe_videos.csv"):
        detalhes.setdefault(l["video_id"], []).append(l)

    videos = []
    for v in _ler("videos.csv"):
        vid = v["video_id"]
        publicado = _dia(v["publicado_em"])
        dias = (ate - publicado).days + 1  # dias com dados (o Analytics vai até `ate`)
        dia_a_dia = sorted(diarios.get(vid, []), key=lambda l: str(l["day"]))
        primeiros = lambda n: sum(l.get("views") or 0 for l in dia_a_dia if (_dia(l["day"]) - publicado).days < n)
        t = totais.get(vid, {})
        grupos = _grupos_trafego(trafegos.get(vid, []))
        termos = sorted(({"termo": str(l["insightTrafficSourceDetail"]), "views": l.get("views") or 0}
                         for l in detalhes.get(vid, []) if l.get("tipo") == "YT_SEARCH"), key=lambda x: -x["views"])
        videos.append({
            "video_id": vid, "url": v.get("url"), "titulo": str(v.get("titulo") or ""),
            "musica": str(v["musica"]) if v.get("musica") is not None else None,
            "artista": v.get("artista"), "id_musica": v.get("id_musica"),
            "aposta": str(v["aposta"]) if v.get("aposta") is not None else SEM_APOSTA,
            "tom": v.get("tom_video"), "publicado": publicado.isoformat(), "dias": dias,
            "duracao_s": v.get("duracao_s"), "thumbnail": v.get("tem_thumbnail_local"),
            "views": t.get("views") or 0, "views_publicas": v.get("visualizacoes") or 0,
            "v7": primeiros(7) if dias > 0 else None, "v7_completo": dias >= 7,
            "v28": primeiros(28) if dias > 0 else None, "v28_completo": dias >= 28,
            "minutos": t.get("estimatedMinutesWatched") or 0,
            "pct_assistido": t.get("averageViewPercentage"), "duracao_media": t.get("averageViewDuration"),
            "inscritos": (t.get("subscribersGained") or 0) - (t.get("subscribersLost") or 0),
            "curtidas": t.get("likes") or 0, "compartilhamentos": t.get("shares") or 0,
            "trafego": grupos, "busca_externo": _intencao(grupos), "dispositivos": dispositivos.get(vid, {}),
            "termos": termos[:10],
            "diario": [{"dia": str(l["day"]), "views": l.get("views") or 0} for l in dia_a_dia],
        })
    videos.sort(key=lambda x: x["publicado"], reverse=True)

    # ---- apostas
    def resumo(lista):
        completos = [x for x in lista if x["v7_completo"]]
        views = sum(x["views"] for x in lista)
        grupos = {}
        for x in lista:
            for k, n in x["trafego"].items():
                grupos[k] = grupos.get(k, 0) + n
        disp = {}
        for x in lista:
            for k, n in x["dispositivos"].items():
                disp[k] = disp.get(k, 0) + n
        com_pct = [{"views": x["views"], "p": x["pct_assistido"]} for x in lista if x["pct_assistido"] is not None]
        melhor = max(lista, key=lambda x: (x["pct_assistido"] or 0) * min(x["views"], 50), default=None)
        return {
            "videos": len(lista), "completos": len(completos), "views": views,
            "v7_mediana": _mediana([x["v7"] for x in completos]),
            "pct_assistido": _media_ponderada(com_pct, "p"),
            "inscritos_por_mil": round(sum(x["inscritos"] for x in lista) * 1000 / views, 1) if views else None,
            "busca_externo": _intencao(grupos), "trafego": grupos, "dispositivos": disp,
            "minutos_por_view": round(sum(x["minutos"] for x in lista) / views, 2) if views else None,
            "melhor": melhor and {"titulo": melhor["musica"] or melhor["titulo"], "video_id": melhor["video_id"],
                                  "pct_assistido": melhor["pct_assistido"], "views": melhor["views"]},
        }
    referencia = resumo(videos)
    apostas = []
    for nome in sorted({x["aposta"] for x in videos}, key=lambda n: (n == SEM_APOSTA, n.lower())):
        r = resumo([x for x in videos if x["aposta"] == nome])
        chaves = ("v7_mediana", "pct_assistido", "inscritos_por_mil", "busca_externo")
        acima = [k for k in chaves if r[k] is not None and referencia[k] is not None and r[k] >= referencia[k]]
        if r["completos"] < MINIMO_APOSTA:
            sinal, motivo = "aguardando", f"faltam {MINIMO_APOSTA - r['completos']} vídeo(s) com 7 dias de dados para comparar"
        elif len(acima) >= 3:
            sinal, motivo = "aprofundar", "acima da média do canal em " + ", ".join(ROTULOS[k] for k in acima)
        elif len(acima) <= 1 and r["completos"] >= LOTE:
            sinal, motivo = "abandonar", "abaixo da média do canal em quase tudo, com o lote completo"
        else:
            sinal, motivo = "ajustar", (f"acima da média em {', '.join(ROTULOS[k] for k in acima)}" if acima else "abaixo da média em tudo") + \
                            ("" if r["completos"] >= LOTE else f"; lote em {r['completos']}/{LOTE}")
        apostas.append({"nome": nome, **r, "sinal": sinal, "motivo": motivo, "acima": acima})

    # ---- origens do tráfego por semana (segunda-feira)
    semanas = {}
    for l in trafego_canal:
        d = _dia(l["day"])
        inicio = (d - timedelta(days=d.weekday())).isoformat()
        g = semanas.setdefault(inicio, {})
        grupo = GRUPOS.get(l.get("insightTrafficSourceType"), "outros")
        g[grupo] = g.get(grupo, 0) + (l.get("views") or 0)

    # ---- termos de busca (canal + vídeos) e sugestões
    minhas = {_normalizar(x["musica"]) for x in videos if x["musica"]} | \
             {_normalizar(x["titulo"].split(" - ")[0]) for x in videos}
    minhas = {m for m in minhas if len(m) > 3}
    tem_musica = lambda texto: any(m in _normalizar(texto) for m in minhas)
    termos = {}
    for l in _ler("trafego_detalhe_canal.csv") + [l for ls in detalhes.values() for l in ls]:
        if l.get("tipo") != "YT_SEARCH":
            continue
        termo = str(l["insightTrafficSourceDetail"])
        t = termos.setdefault(termo, {"termo": termo, "views": 0, "minutos": 0, "videos": set()})
        if l.get("video_id"):
            t["videos"].add(l["video_id"])
        else:  # a linha do canal já é o total do termo
            t["views"] = max(t["views"], l.get("views") or 0)
            t["minutos"] = max(t["minutos"], l.get("estimatedMinutesWatched") or 0)
    for ls in detalhes.values():  # termos que só aparecem nos vídeos
        for l in ls:
            if l.get("tipo") == "YT_SEARCH":
                t = termos[str(l["insightTrafficSourceDetail"])]
                t["_soma"] = t.get("_soma", 0) + (l.get("views") or 0)
                t["_min"] = t.get("_min", 0) + (l.get("estimatedMinutesWatched") or 0)
    lista_termos = []
    for t in termos.values():
        t["views"] = max(t["views"], t.pop("_soma", 0))
        t["minutos"] = max(t["minutos"], t.pop("_min", 0))
        t["videos"] = sorted(t["videos"])
        t["tem_video"] = tem_musica(t["termo"])
        lista_termos.append(t)
    lista_termos.sort(key=lambda t: (-t["views"], t["termo"]))

    sugeridores = []
    for s in _ler("sugeridores.csv"):
        sugeridores.append({
            "video_id": s["video_id"], "url": s.get("url"), "titulo": str(s.get("titulo") or ""), "canal": s.get("canal"),
            "visualizacoes": s.get("visualizacoes") or 0, "views_para_mim": s.get("views_para_mim") or 0,
            "tem_video": tem_musica(s.get("titulo")),
        })
    sugeridores.sort(key=lambda s: (-s["views_para_mim"], -s["visualizacoes"]))

    # ---- público
    dispositivos_canal = {}
    for l in _ler("dispositivos_canal.csv"):
        d = dispositivos_canal.setdefault(l["deviceType"], {"views": 0, "minutos": 0})
        d["views"] += l.get("views") or 0
        d["minutos"] += l.get("estimatedMinutesWatched") or 0
    compartilhamento = {str(l["sharingService"]): l.get("shares") or 0 for l in _ler("compartilhamento_canal.csv")}

    coleta = _ler("coleta.csv")
    tipos = _ler("relatorios_tipos.csv")
    alcance = [t for t in tipos if str(t.get("tipo", "")).startswith("channel_reach")]
    return {
        "vazio": False,
        "canal": {"titulo": canal.get("titulo"), "url": canal.get("url_personalizada"), "criado_em": canal.get("criado_em"),
                  "visualizacoes": canal.get("visualizacoes"), "videos": canal.get("videos")},
        "coletado_em": canal.get("coletado_em") or datetime.fromtimestamp(os.path.getmtime(leia_me)).isoformat(timespec="seconds"),
        "dados_ate": ate.isoformat(),
        "metas": METAS, "monetizacao": MONETIZACAO, "lote": LOTE, "kpis": kpis,
        "apostas": apostas, "referencia": referencia, "videos": videos,
        "diario_canal": [{"dia": str(l["day"]), "views": l.get("views") or 0,
                          "minutos": l.get("estimatedMinutesWatched") or 0} for l in diario_canal],
        "trafego_semanas": [{"semana": k, **semanas[k]} for k in sorted(semanas)],
        "grupos": ORDEM_GRUPOS,
        "termos": lista_termos[:60], "sugeridores": sugeridores[:40],
        "demografia": [{"idade": str(l["ageGroup"]).replace("age", ""), "sexo": l["gender"], "pct": l.get("viewerPercentage") or 0}
                       for l in _ler("demografia_canal.csv")],
        "dispositivos": dispositivos_canal, "compartilhamento": compartilhamento,
        "paises": [{"pais": l["country"], "views": l.get("views") or 0} for l in _ler("paises_canal.csv")],
        "avisos": {
            "recusadas": sum(1 for l in coleta if l.get("erro")),
            "retencao": bool(_ler("retencao.csv")),
            "alcance_dias": max((t.get("dias_baixados") or 0 for t in alcance), default=0),
            "sugeridores": os.path.isfile(os.path.join(PASTA, "sugeridores.csv")),
        },
        "diario": diario(), "analises": analises(),
    }
