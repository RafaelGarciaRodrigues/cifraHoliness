"""Coleta os dados do canal do YouTube para a pasta analytics/ (CSVs), para analisar o público e
montar a estratégia do canal. Cada coleta apaga a anterior e grava tudo de novo (a Analytics API
devolve o histórico inteiro desde a criação do canal), exceto os relatórios em lote da Reporting
API (impressões e CTR da thumbnail etc.), que o YouTube só guarda por um tempo: esses se acumulam
em analytics/relatorios_brutos/ e são consolidados em analytics/relatorios/.

Fontes:
  - YouTube Data API v3: canal, vídeos, playlists, comentários e os vídeos originais dos áudios
    (docs/origens.json), cruzados com o cadastro do app (musicas.db, docs/youtube.json);
  - YouTube Analytics API v2 (reports.query): diário, tráfego, termos de busca, retenção,
    demografia, países, dispositivos... do canal e de cada vídeo;
  - YouTube Reporting API v1: cria (uma vez) um pedido para cada tipo de relatório e baixa os
    que o YouTube já gerou.

A pasta analytics/analises/ (análises escritas sobre os dados) também passa de uma coleta para a outra.

A coleta é gravada em analytics.novo/ e só substitui analytics/ se terminar bem.
CSV em UTF-8 com BOM, separador ";" e vírgula decimal (abre direto no Excel em português).

Uso (a interface chama pelo botão "Analytics" da Biblioteca):
    python analytics.py
"""
import csv
import io
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime

import banco
import baixar
import youtube
from pastas import BASE_DIR

PASTA_ANALYTICS = os.path.join(BASE_DIR, "analytics")
PASTA_NOVA = os.path.join(BASE_DIR, "analytics.novo")
PASTA_ANTIGA = os.path.join(BASE_DIR, "analytics.antigo")
BRUTOS = "relatorios_brutos"  # relatórios da Reporting API como o YouTube entrega (acumulam)
ANALISES = "analises"  # análises escritas sobre os dados (não vêm do YouTube): passam de uma coleta para a outra
ESCOPO = youtube.ESCOPO_ANALYTICS

# métricas aceitas pelos relatórios "básicos" (dia, vídeo, país, inscrito ou não...)
BASICAS = ["views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage",
           "likes", "dislikes", "comments", "shares", "subscribersGained", "subscribersLost",
           "videosAddedToPlaylists", "videosRemovedFromPlaylists"]
# métricas que nem todo relatório aceita: são testadas uma a uma quando a consulta completa é recusada
EXTRAS = ["engagedViews", "redViews", "estimatedRedMinutesWatched", "cardImpressions", "cardClicks",
          "cardClickRate", "cardTeaserImpressions", "cardTeaserClicks", "cardTeaserClickRate"]
VISTAS = ["views", "estimatedMinutesWatched"]
# tipos de tráfego que têm detalhe (insightTrafficSourceDetail): termos de busca, vídeos que sugeriram...
# (NOTIFICATION, END_SCREEN, SHORTS_CONTENT_LINKS, VIDEO_REMIXES e CAMPAIGN_CARD: "query is not supported")
TIPOS_DETALHE = ["YT_SEARCH", "RELATED_VIDEO", "EXT_URL", "YT_CHANNEL", "YT_OTHER_PAGE", "SUBSCRIBER",
                 "HASHTAGS", "SOUND_PAGE", "ADVERTISING"]

DESCRICOES = {
    "canal.csv": "dados do canal (inscritos, visualizações, criação...)",
    "videos.csv": "um vídeo por linha: dados do YouTube + do app (música, artista, tom, origem do áudio)",
    "originais.csv": "vídeos de onde vieram os áudios (docs/origens.json): números públicos",
    "playlists.csv": "playlists do canal",
    "comentarios.csv": "comentários e respostas (sem o nome do autor)",
    "sugeridores.csv": "vídeos de outros canais que levaram público para os seus (sugeridos): título, canal, visualizações",
    "totais_videos.csv": "totais de cada vídeo desde a publicação (Analytics)",
    "diario_canal.csv": "o canal dia a dia",
    "diario_videos.csv": "cada vídeo dia a dia",
    "formato_canal.csv": "Shorts x vídeos longos x ao vivo, dia a dia",
    "produto_canal.csv": "YouTube, YouTube Music, Kids...",
    "trafego_canal.csv": "origem do tráfego do canal, dia a dia",
    "trafego_videos.csv": "origem do tráfego de cada vídeo",
    "trafego_detalhe_canal.csv": "detalhe do tráfego do canal: termos de busca (YT_SEARCH), vídeos que sugeriram (RELATED_VIDEO), sites...",
    "trafego_detalhe_videos.csv": "o mesmo detalhe, por vídeo",
    "local_canal.csv": "onde o vídeo foi assistido (página do YouTube, incorporado, Shorts...), dia a dia",
    "local_videos.csv": "onde cada vídeo foi assistido",
    "retencao.csv": "curva de retenção de cada vídeo (0 a 1 = início ao fim do vídeo)",
    "demografia_canal.csv": "idade x sexo do público do canal (% das visualizações de quem estava logado)",
    "demografia_videos.csv": "idade x sexo por vídeo",
    "paises_canal.csv": "países do canal",
    "paises_videos.csv": "países por vídeo",
    "estados_eua.csv": "estados dos EUA",
    "cidades.csv": "principais cidades",
    "dispositivos_canal.csv": "dispositivo x sistema operacional do canal",
    "dispositivos_diario_canal.csv": "dispositivos, dia a dia",
    "dispositivos_videos.csv": "dispositivo x sistema por vídeo",
    "inscritos_canal.csv": "inscritos x não inscritos, dia a dia",
    "inscritos_videos.csv": "inscritos x não inscritos por vídeo",
    "compartilhamento_canal.csv": "por onde compartilharam (WhatsApp, Facebook...)",
    "compartilhamento_videos.csv": "compartilhamentos por vídeo",
    "relatorios_tipos.csv": "tipos de relatório da Reporting API e se já há dados",
    "coleta.csv": "cada consulta feita nesta coleta: parâmetros, linhas e erro",
}


class Fatal(Exception):
    """Erro que impede a coleta (sem acesso, API desativada, cota): os dados antigos ficam."""


def _motivo(e):
    """(motivo, mensagem) de um HttpError do Google."""
    try:
        erro = json.loads(e.content.decode("utf-8")).get("error", {})
        detalhes = erro.get("errors") or [{}]
        return detalhes[0].get("reason") or erro.get("status") or "", erro.get("message") or str(e)
    except (ValueError, AttributeError):
        return "", str(e)


def _numero(v):
    """Formato do Excel em português: vírgula decimal."""
    if isinstance(v, float):
        return repr(v).replace(".", ",")
    if isinstance(v, str) and re.fullmatch(r"-?\d+\.\d+(e-?\d+)?", v):
        return v.replace(".", ",")
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (list, tuple)):
        return " | ".join(map(str, v))
    return "" if v is None else v


def _segundos(iso):
    """'PT1H2M3S' -> 3723."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


class Coleta:
    def __init__(self, cred):
        from googleapiclient.discovery import build
        self.cred = cred
        self.dados = build("youtube", "v3", credentials=cred, cache_discovery=False)
        self.analytics = build("youtubeAnalytics", "v2", credentials=cred, cache_discovery=False)
        self.tabelas = {}       # arquivo -> lista de linhas (dict)
        self.aceitas = {}       # nome da consulta -> métricas extras que o YouTube aceitou
        self.avisos = []
        self.inicio = self.fim = date.today().isoformat()

    # ------------------------------------------------------------ utilidades
    def linhas(self, arquivo, novas):
        self.tabelas.setdefault(arquivo, []).extend(novas)

    def registrar(self, arquivo, parametros, linhas, erro=""):
        self.linhas("coleta.csv", [{"arquivo": arquivo, "parametros": json.dumps(parametros, ensure_ascii=False),
                                    "linhas": linhas, "erro": erro}])

    def executar(self, pedido):
        """Executa um pedido da API, tentando de novo em falhas temporárias; erros de acesso viram Fatal."""
        from googleapiclient.errors import HttpError
        for tentativa in range(4):
            try:
                return pedido.execute()
            except HttpError as e:
                motivo, mensagem = _motivo(e)
                status = e.resp.status
                if status in (500, 502, 503, 504) and tentativa < 3:
                    time.sleep(2 ** tentativa)
                    continue
                if status == 401 or motivo in ("accessNotConfigured", "SERVICE_DISABLED", "insufficientPermissions",
                                                "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "quotaExceeded",
                                                "dailyLimitExceeded", "rateLimitExceeded"):
                    if "has not been used" in mensagem or "disabled" in mensagem or motivo in ("accessNotConfigured", "SERVICE_DISABLED"):
                        mensagem += ("\n  Ative as APIs no Google Cloud (mesmo projeto do client_secret):"
                                     "\n  https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com"
                                     "\n  https://console.cloud.google.com/apis/library/youtubereporting.googleapis.com")
                    raise Fatal(mensagem) from e
                raise
            except OSError:
                if tentativa < 3:
                    time.sleep(2 ** tentativa)
                    continue
                raise

    # ------------------------------------------------------------ Analytics API
    def consultar(self, arquivo, dimensoes="", metricas=BASICAS, extras=(), filtros=None, ordem=None,
                  maximo=None, colunas=None, nome=None):
        """reports.query; devolve as linhas (dict) e as acrescenta em `arquivo` com `colunas` na frente.
        Se o YouTube recusa a consulta (cada relatório aceita só algumas métricas), descobre na 1ª vez de
        cada `nome` quais métricas (de `metricas` e `extras`) ele aceita, testando uma a uma."""
        from googleapiclient.errors import HttpError
        nome = nome or arquivo
        base = {"ids": "channel==MINE", "startDate": self.inicio, "endDate": self.fim}
        if dimensoes:
            base["dimensions"] = dimensoes
        if filtros:
            base["filters"] = filtros
        if ordem:
            base["sort"] = ordem
        if maximo:
            base["maxResults"] = maximo
        todas = list(dict.fromkeys(list(metricas) + list(extras)))
        aceitas = self.aceitas.get(nome, todas)
        resposta, erro = None, ""
        for tentativa in ("completa", "testada", "principais"):
            parametros = {**base, "metrics": ",".join(aceitas)}
            if not aceitas:
                break
            try:
                resposta = self.executar(self.analytics.reports().query(**parametros))
                break
            except HttpError as e:
                erro = _motivo(e)[1]
                if tentativa == "completa" and nome not in self.aceitas:
                    aceitas = []
                    for metrica in todas:  # quais métricas este relatório aceita
                        try:
                            self.executar(self.analytics.reports().query(**{**base, "metrics": metrica}))
                            aceitas.append(metrica)
                        except HttpError:
                            pass
                    self.aceitas[nome] = aceitas
                    continue
                # aceitas uma a uma, mas não juntas: fica só com as principais (sem as extras)
                principais = [m for m in aceitas if m in metricas]
                if tentativa != "principais" and principais != aceitas:
                    aceitas = principais
                    continue
                break
        if resposta is None:
            self.registrar(arquivo, parametros, 0, erro or "nenhuma métrica aceita por este relatório")
            return []
        self.aceitas[nome] = aceitas
        cab = [c["name"] for c in resposta.get("columnHeaders", [])]
        linhas = [{**(colunas or {}), **dict(zip(cab, r))} for r in resposta.get("rows") or []]
        self.linhas(arquivo, linhas)
        self.registrar(arquivo, parametros, len(linhas))
        return linhas

    # ------------------------------------------------------------ Data API
    def paginas(self, metodo, chave="items", **parametros):
        while True:
            r = self.executar(metodo(**parametros))
            yield from r.get(chave, [])
            if not (token := r.get("nextPageToken")):
                return
            parametros["pageToken"] = token

    def canal(self):
        itens = self.executar(self.dados.channels().list(
            part="snippet,statistics,contentDetails,brandingSettings,status,topicDetails", mine=True)).get("items", [])
        if not itens:
            raise Fatal("a conta conectada não tem canal no YouTube")
        c = itens[0]
        sn, st, br = c.get("snippet", {}), c.get("statistics", {}), c.get("brandingSettings", {}).get("channel", {})
        self.canal_id = c["id"]
        self.inicio = (sn.get("publishedAt") or self.fim)[:10]
        self.linhas("canal.csv", [{
            "canal_id": c["id"], "titulo": sn.get("title"), "url_personalizada": sn.get("customUrl"),
            "criado_em": sn.get("publishedAt"), "pais": sn.get("country") or br.get("country"),
            "idioma_padrao": sn.get("defaultLanguage") or br.get("defaultLanguage"),
            "inscritos": st.get("subscriberCount"), "inscritos_ocultos": st.get("hiddenSubscriberCount"),
            "visualizacoes": st.get("viewCount"), "videos": st.get("videoCount"),
            "palavras_chave": br.get("keywords"), "descricao": sn.get("description"),
            "privacidade": c.get("status", {}).get("privacyStatus"),
            "vinculado": c.get("status", {}).get("isLinked"),
            "uploads_longos": c.get("status", {}).get("longUploadsStatus"),
            "infantil": c.get("status", {}).get("madeForKids"),
            "topicos": [t.rsplit("/", 1)[-1] for t in c.get("topicDetails", {}).get("topicCategories", [])],
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
        }])
        self.registrar("canal.csv", {"mine": True}, 1)
        return c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

    def _detalhes_videos(self, ids, parte):
        for i in range(0, len(ids), 50):
            yield from self.executar(self.dados.videos().list(part=parte, id=",".join(ids[i:i + 50]),
                                                              maxResults=50)).get("items", [])

    def videos(self, uploads):
        ids = [it["contentDetails"]["videoId"] for it in
               self.paginas(self.dados.playlistItems().list, part="contentDetails", playlistId=uploads, maxResults=50)] if uploads else []
        # o que o app sabe de cada vídeo publicado por ele (docs/youtube.json, incluindo as versões anteriores)
        app = {}
        for arquivo, p in youtube.publicados().items():
            for i, pub in enumerate([p] + p.get("anteriores", [])):
                app.setdefault(pub.get("video_id"), {**pub, "arquivo": arquivo, "versao_atual": i == 0})
        origens = baixar.origens()
        self.videos_ids = []
        for v in self._detalhes_videos(ids, "snippet,contentDetails,statistics,status,topicDetails"):
            sn, cd, st, ss = v.get("snippet", {}), v.get("contentDetails", {}), v.get("statistics", {}), v.get("status", {})
            pub = app.get(v["id"], {})
            reg = banco.obter(pub["id_musica"]) if pub.get("id_musica") else None
            reg = reg or {}
            origem = origens.get(reg.get("arquivo") or "", {})
            tom = re.search(r" - Tom ([A-G][#b]?m?)(?: \(\d+\))?\.mp4$", pub.get("arquivo", ""))
            self.videos_ids.append((v["id"], sn.get("publishedAt") or ""))
            self.linhas("videos.csv", [{
                "video_id": v["id"], "url": f"https://youtu.be/{v['id']}", "titulo": sn.get("title"),
                "publicado_em": sn.get("publishedAt"), "duracao_s": _segundos(cd.get("duration")),
                "provavel_short": (_segundos(cd.get("duration")) or 999) <= 180,
                "privacidade": ss.get("privacyStatus"), "infantil": ss.get("madeForKids"),
                "licenca": ss.get("license"), "incorporavel": ss.get("embeddable"),
                "definicao": cd.get("definition"), "legenda": cd.get("caption"),
                "conteudo_licenciado": cd.get("licensedContent"),
                "bloqueado_em": (cd.get("regionRestriction") or {}).get("blocked"),
                "categoria_id": sn.get("categoryId"), "idioma": sn.get("defaultLanguage"),
                "idioma_audio": sn.get("defaultAudioLanguage"), "tags": sn.get("tags") or [],
                "qtd_tags": len(sn.get("tags") or []), "tamanho_titulo": len(sn.get("title") or ""),
                "hashtags": re.findall(r"#\w+", sn.get("description") or ""),
                "tamanho_descricao": len(sn.get("description") or ""),
                "topicos": [t.rsplit("/", 1)[-1] for t in v.get("topicDetails", {}).get("topicCategories", [])],
                "visualizacoes": st.get("viewCount"), "curtidas": st.get("likeCount"),
                "comentarios": st.get("commentCount"), "favoritos": st.get("favoriteCount"),
                # do app
                "publicado_pelo_app": bool(pub), "versao_atual": pub.get("versao_atual"),
                "arquivo_video": pub.get("arquivo"), "id_musica": pub.get("id_musica"),
                "musica": reg.get("titulo"), "artista": reg.get("artista"),
                "aposta": reg.get("categoria"),  # coluna "Aposta" da Biblioteca (campo categoria do banco)
                "tags_app": reg.get("tags"), "status_app": reg.get("status"), "favorita": reg.get("favorito"),
                "tom_video": tom.group(1) if tom else None, "transposicao": reg.get("transposicao"),
                "tom_original_tonica": reg.get("tom_tonica"), "tom_original_modo": reg.get("tom_modo"),
                "duracao_musica_s": reg.get("duracao"), "qtd_notas": reg.get("qtd_notas"),
                "qtd_acordes": reg.get("qtd_acordes"), "qtd_frases": reg.get("qtd_frases"),
                "tem_thumbnail_local": bool(youtube.caminho_thumbnail(pub["arquivo"])) if pub.get("arquivo") else None,
                "arquivo_audio": reg.get("arquivo"), "origem_video_id": origem.get("video_id"),
                "origem_url": origem.get("url"), "origem_titulo": origem.get("titulo"), "origem_canal": origem.get("canal"),
                "descricao": sn.get("description"),
            }])
        self.registrar("videos.csv", {"playlist": uploads}, len(self.videos_ids))

    def originais(self):
        origens = baixar.origens()
        musicas = {r.get("arquivo"): r for r in banco.listar()}
        por_id = {o["video_id"]: (a, o) for a, o in origens.items() if o.get("video_id")}
        n = 0
        for v in self._detalhes_videos(list(por_id), "snippet,contentDetails,statistics"):
            arquivo, o = por_id[v["id"]]
            sn, st = v.get("snippet", {}), v.get("statistics", {})
            reg = musicas.get(arquivo) or {}
            n += 1
            self.linhas("originais.csv", [{
                "origem_video_id": v["id"], "url": o.get("url"), "titulo": sn.get("title"),
                "canal": sn.get("channelTitle"), "canal_id": sn.get("channelId"), "publicado_em": sn.get("publishedAt"),
                "duracao_s": _segundos(v.get("contentDetails", {}).get("duration")),
                "visualizacoes": st.get("viewCount"), "curtidas": st.get("likeCount"), "comentarios": st.get("commentCount"),
                "categoria_id": sn.get("categoryId"), "idioma_audio": sn.get("defaultAudioLanguage"),
                "tags": sn.get("tags") or [], "arquivo_audio": arquivo, "baixado_em": o.get("baixado_em"),
                "id_musica": reg.get("id"), "musica": reg.get("titulo"), "artista": reg.get("artista"),
                "aposta": reg.get("categoria"),
            }])
        self.registrar("originais.csv", {"videos": len(por_id)}, n)

    def playlists(self):
        n = 0
        for p in self.paginas(self.dados.playlists().list, part="snippet,contentDetails,status", mine=True, maxResults=50):
            n += 1
            self.linhas("playlists.csv", [{
                "playlist_id": p["id"], "titulo": p["snippet"].get("title"), "criada_em": p["snippet"].get("publishedAt"),
                "videos": p.get("contentDetails", {}).get("itemCount"), "privacidade": p.get("status", {}).get("privacyStatus"),
                "descricao": p["snippet"].get("description"),
            }])
        self.registrar("playlists.csv", {"mine": True}, n)

    def comentarios(self):
        from googleapiclient.errors import HttpError

        def linha(c, video, pai=None, respostas=None):
            sn = c["snippet"]
            return {"video_id": video, "comentario_id": c["id"], "resposta_de": pai,
                    "publicado_em": sn.get("publishedAt"), "atualizado_em": sn.get("updatedAt"),
                    "curtidas": sn.get("likeCount"), "respostas": respostas,
                    "do_canal": (sn.get("authorChannelId") or {}).get("value") == self.canal_id,
                    "texto": sn.get("textOriginal") or sn.get("textDisplay")}
        # vídeo a vídeo (com o escopo youtube.force-ssl, exigido pelo commentThreads)
        for video, _ in self.videos_ids:
            n = 0
            try:
                for t in self.paginas(self.dados.commentThreads().list, part="snippet,replies", maxResults=100,
                                      videoId=video, textFormat="plainText"):
                    sn = t["snippet"]
                    novas = [linha(sn["topLevelComment"], video, respostas=sn.get("totalReplyCount"))]
                    novas += [linha(r, video, pai=t["id"]) for r in t.get("replies", {}).get("comments", [])]
                    self.linhas("comentarios.csv", novas)
                    n += len(novas)
            except (HttpError, Fatal) as e:  # comentários desativados etc.: não impede o resto
                self.registrar("comentarios.csv", {"video": video}, n, _motivo(e)[1] if isinstance(e, HttpError) else str(e))
                continue
            self.registrar("comentarios.csv", {"video": video}, n)

    # ------------------------------------------------------------ relatórios do Analytics
    def relatorios_canal(self):
        c = self.consultar
        c("diario_canal.csv", "day", BASICAS, EXTRAS, ordem="day")
        c("formato_canal.csv", "day,creatorContentType", BASICAS, ["engagedViews"], ordem="day")
        c("produto_canal.csv", "youtubeProduct", VISTAS + ["averageViewDuration"], ["engagedViews"])
        c("trafego_canal.csv", "day,insightTrafficSourceType", VISTAS, ["engagedViews"], ordem="day")
        c("local_canal.csv", "day,insightPlaybackLocationType", VISTAS, ["engagedViews"], ordem="day")
        c("demografia_canal.csv", "ageGroup,gender", ["viewerPercentage"])
        c("paises_canal.csv", "country", BASICAS, ["engagedViews", "redViews"])
        c("estados_eua.csv", "province", VISTAS + ["averageViewDuration", "averageViewPercentage"], filtros="country==US")
        c("cidades.csv", "city", VISTAS + ["averageViewDuration", "averageViewPercentage"], ordem="-views", maximo=25)
        c("dispositivos_canal.csv", "deviceType,operatingSystem", VISTAS, ["engagedViews"])
        c("dispositivos_diario_canal.csv", "day,deviceType", VISTAS, ordem="day")
        c("inscritos_canal.csv", "day,subscribedStatus", BASICAS, ordem="day")
        c("compartilhamento_canal.csv", "sharingService", ["shares"])
        for tipo in TIPOS_DETALHE:
            c("trafego_detalhe_canal.csv", "insightTrafficSourceDetail", VISTAS, filtros=f"insightTrafficSourceType=={tipo}",
              ordem="-views", maximo=25, colunas={"tipo": tipo}, nome="detalhe_canal")
        c("totais_videos.csv", "video", BASICAS, EXTRAS, ordem="-views", maximo=200)

    def relatorios_video(self, video, publicado):
        c = self.consultar
        col = {"video_id": video}
        f = f"video=={video}"
        inicio, self.inicio = self.inicio, max(self.inicio, publicado[:10] or self.inicio)
        try:
            c("diario_videos.csv", "day", BASICAS, EXTRAS, filtros=f, ordem="day", colunas=col, nome="diario_video")
            trafego = c("trafego_videos.csv", "insightTrafficSourceType", VISTAS, ["engagedViews", "averageViewDuration"],
                        filtros=f, colunas=col, nome="trafego_video")
            for tipo in sorted({t.get("insightTrafficSourceType") for t in trafego} & set(TIPOS_DETALHE)):
                c("trafego_detalhe_videos.csv", "insightTrafficSourceDetail", VISTAS, ["averageViewDuration"],
                  filtros=f"{f};insightTrafficSourceType=={tipo}", ordem="-views", maximo=25,
                  colunas={**col, "tipo": tipo}, nome="detalhe_video")
            c("local_videos.csv", "insightPlaybackLocationType", VISTAS, ["engagedViews"], filtros=f, colunas=col, nome="local_video")
            c("retencao.csv", "elapsedVideoTimeRatio", ["audienceWatchRatio", "relativeRetentionPerformance"],
              ["startedWatching", "stoppedWatching", "totalSegmentImpressions"], filtros=f, colunas=col, nome="retencao")
            c("demografia_videos.csv", "ageGroup,gender", ["viewerPercentage"], filtros=f, colunas=col, nome="demografia_video")
            c("paises_videos.csv", "country", BASICAS, ["engagedViews"], filtros=f, colunas=col, nome="paises_video")
            c("dispositivos_videos.csv", "deviceType,operatingSystem", VISTAS, ["engagedViews"], filtros=f, colunas=col,
              nome="dispositivos_video")
            c("inscritos_videos.csv", "subscribedStatus", BASICAS, filtros=f, colunas=col, nome="inscritos_video")
            c("compartilhamento_videos.csv", "sharingService", ["shares"], filtros=f, colunas=col, nome="compartilhamento_video")
        finally:
            self.inicio = inicio

    def sugeridores(self):
        """Vídeos de outros canais que mandaram público pelos sugeridos (RELATED_VIDEO), com título, canal e
        visualizações (Data API): mostram onde está a demanda e quem é o "vizinho" do canal no algoritmo."""
        meus = {v for v, _ in self.videos_ids}
        para_mim = {}
        for l in self.tabelas.get("trafego_detalhe_videos.csv", []):
            if l.get("tipo") == "RELATED_VIDEO" and (sid := l.get("insightTrafficSourceDetail")) not in meus:
                d = para_mim.setdefault(sid, {"views": 0, "minutos": 0, "videos": set()})
                d["views"] += l.get("views") or 0
                d["minutos"] += l.get("estimatedMinutesWatched") or 0
                d["videos"].add(l["video_id"])
        n = 0
        for v in self._detalhes_videos(list(para_mim), "snippet,statistics,contentDetails"):
            sn, st, d = v.get("snippet", {}), v.get("statistics", {}), para_mim[v["id"]]
            n += 1
            self.linhas("sugeridores.csv", [{
                "video_id": v["id"], "url": f"https://www.youtube.com/watch?v={v['id']}", "titulo": sn.get("title"),
                "canal": sn.get("channelTitle"), "canal_id": sn.get("channelId"), "publicado_em": sn.get("publishedAt"),
                "duracao_s": _segundos(v.get("contentDetails", {}).get("duration")),
                "visualizacoes": st.get("viewCount"), "curtidas": st.get("likeCount"),
                "views_para_mim": d["views"], "minutos_para_mim": d["minutos"], "meus_videos": sorted(d["videos"]),
            }])
        self.registrar("sugeridores.csv", {"videos": len(para_mim)}, n)

    # ------------------------------------------------------------ Reporting API (relatórios em lote)
    def relatorios_lote(self, pasta, pasta_antiga):
        """Cria um pedido para cada tipo de relatório (uma vez; o YouTube passa a gerá-los todo dia) e
        baixa os que ainda não estão em relatorios_brutos/ (que vem da coleta anterior)."""
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from google.auth.transport.requests import AuthorizedSession
        brutos = os.path.join(pasta, BRUTOS)
        if os.path.isdir(os.path.join(pasta_antiga, BRUTOS)):
            shutil.copytree(os.path.join(pasta_antiga, BRUTOS), brutos)
        rep = build("youtubereporting", "v1", credentials=self.cred, cache_discovery=False)
        try:
            tipos = list(self.paginas(rep.reportTypes().list, "reportTypes"))
        except (HttpError, Fatal) as e:  # sem a Reporting API, o resto da coleta continua valendo
            motivo = _motivo(e)[1] if isinstance(e, HttpError) else str(e)
            self.registrar("relatorios", {}, 0, motivo)
            self.avisos.append(f"Reporting API indisponível: {motivo}")
            return
        tipos = [t for t in tipos if not t.get("systemManaged")]
        pedidos = {j["reportTypeId"]: j for j in self.paginas(rep.jobs().list, "jobs")}
        criados = []
        for t in tipos:
            if t["id"] not in pedidos and not t.get("deprecateTime"):
                try:
                    pedidos[t["id"]] = self.executar(rep.jobs().create(body={"reportTypeId": t["id"], "name": f"TelaCifras {t['id']}"}))
                    criados.append(t["id"])
                except HttpError as e:
                    self.registrar("relatorios", {"criar": t["id"]}, 0, _motivo(e)[1])
        if criados:
            self.avisos.append(f"Reporting API: {len(criados)} tipo(s) de relatório pedidos agora; o YouTube leva "
                               "até uns 2 dias para gerar os primeiros (impressões e CTR da thumbnail vêm em channel_reach_*).")
        sessao = AuthorizedSession(self.cred)
        baixados = 0
        resumo = []
        for tipo, job in sorted(pedidos.items()):
            pasta_tipo = os.path.join(brutos, tipo)
            try:
                relatorios = list(self.paginas(rep.jobs().reports().list, "reports", jobId=job["id"]))
            except HttpError as e:
                self.registrar("relatorios", {"listar": tipo}, 0, _motivo(e)[1])
                continue
            for r in relatorios:
                nome = f"{r['startTime'][:10]}_{re.sub(r'[^0-9]', '', r['createTime'])[:14]}.csv"
                destino = os.path.join(pasta_tipo, nome)
                if os.path.isfile(destino):
                    continue
                resposta = sessao.get(r["downloadUrl"], timeout=120)
                if resposta.status_code != 200:
                    self.registrar("relatorios", {"baixar": tipo, "inicio": r["startTime"]}, 0, f"HTTP {resposta.status_code}")
                    continue
                os.makedirs(pasta_tipo, exist_ok=True)
                with open(destino, "wb") as f:
                    f.write(resposta.content)
                baixados += 1
            arquivos = sorted(os.listdir(pasta_tipo)) if os.path.isdir(pasta_tipo) else []
            resumo.append({"tipo": tipo, "pedido_id": job["id"], "pedido_criado_em": job.get("createTime"),
                           "criado_agora": tipo in criados, "dias_baixados": len({a[:10] for a in arquivos})})
            self._consolidar(pasta, tipo, pasta_tipo, arquivos)
        self.linhas("relatorios_tipos.csv", resumo)
        self.registrar("relatorios", {"tipos": len(pedidos)}, baixados)

    def _consolidar(self, pasta, tipo, pasta_tipo, arquivos):
        """Junta os relatórios diários de um tipo em relatorios/<tipo>.csv (do mesmo dia, o gerado por último)."""
        ultimo = {}
        for a in arquivos:  # nome: <dia>_<criado em>.csv; em ordem, o último de cada dia fica
            ultimo[a[:10]] = a
        cabecalho, linhas = None, []
        for a in sorted(ultimo.values()):
            with open(os.path.join(pasta_tipo, a), encoding="utf-8-sig", newline="") as f:
                leitor = csv.reader(f)
                cab = next(leitor, None)
                if cab is None:
                    continue
                cabecalho = cabecalho or cab
                linhas += [dict(zip(cab, l)) for l in leitor]
        if cabecalho:
            self.tabelas[os.path.join("relatorios", tipo + ".csv")] = linhas

    # ------------------------------------------------------------ gravação
    def gravar(self, pasta):
        resumo = []
        for arquivo, linhas in self.tabelas.items():
            colunas = list(dict.fromkeys(k for l in linhas for k in l))
            caminho = os.path.join(pasta, arquivo)
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
                escritor = csv.writer(f, delimiter=";")
                escritor.writerow(colunas)
                for l in linhas:
                    escritor.writerow([_numero(l.get(c)) for c in colunas])
            resumo.append((arquivo, len(linhas)))
        return sorted(resumo)

    def leia_me(self, pasta, resumo, canal):
        erros = [l for l in self.tabelas.get("coleta.csv", []) if l.get("erro")]
        vazios = [a for a, n in resumo if n == 0]
        texto = io.StringIO()
        p = lambda s="": print(s, file=texto)
        p(f"Coleta do YouTube Analytics — canal {canal}")
        p(f"Feita em {datetime.now():%d/%m/%Y %H:%M}; período: {self.inicio} a {self.fim} (os dados do YouTube chegam com 1 a 3 dias de atraso).")
        p("CSV: UTF-8, separador ';', vírgula decimal. Datas no formato ISO (AAAA-MM-DD).")
        p()
        p("Arquivos (linhas):")
        for arquivo, n in resumo:
            p(f"  {arquivo:<42} {n:>7}  {DESCRICOES.get(arquivo, '')}")
        p()
        p("Observações:")
        p("  - Demografia (idade/sexo) é o % das visualizações de quem estava logado; com poucas visualizações o")
        p("    YouTube não devolve nada (privacidade), por isso alguns arquivos podem vir vazios.")
        p("  - averageViewPercentage e audienceWatchRatio: em % / fração do vídeo assistido.")
        p("  - relativeRetentionPerformance: 0 a 1, retenção comparada com vídeos de duração parecida no YouTube (0,5 = média).")
        p("  - relatorios/: relatórios em lote da Reporting API (por vídeo e por dia), consolidados de relatorios_brutos/,")
        p("    que é mantido entre coletas (o YouTube só guarda esses relatórios por um tempo).")
        p("  - analises/: análises escritas sobre estes dados; também é mantida entre coletas.")
        for a in self.avisos:
            p(f"  - {a}")
        if vazios:
            p()
            p("Vieram vazios: " + ", ".join(vazios))
        if erros:
            p()
            p(f"Consultas recusadas pelo YouTube ({len(erros)}; detalhes em coleta.csv):")
            for e in {(l['arquivo'], l['erro']) for l in erros}:
                p(f"  {e[0]}: {e[1][:200]}")
        with open(os.path.join(pasta, "leia-me.txt"), "w", encoding="utf-8-sig") as f:
            f.write(texto.getvalue())


def main(argumentos):
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        print("Erro: instale as bibliotecas: pip install google-api-python-client google-auth-oauthlib")
        return 1
    print("[1/6] Conectando ao YouTube...", flush=True)
    try:
        cred = youtube.credenciais()
    except Exception as e:
        print(f"Erro: não foi possível renovar o acesso à conta ({e}); conecte a conta de novo em '⚙ YouTube'.")
        return 1
    if cred is None:
        print("Erro: nenhuma conta do YouTube conectada; use o botão '⚙ YouTube' da Biblioteca.")
        return 1
    if not cred.has_scopes([ESCOPO, youtube.ESCOPO_COMENTARIOS]):
        print("Erro: falta autorizar a leitura do YouTube Analytics: em '⚙ YouTube', clique em 'Trocar conta' "
              "e entre de novo com a mesma conta (sem_escopo_analytics).")
        return 1

    shutil.rmtree(PASTA_NOVA, ignore_errors=True)
    os.makedirs(PASTA_NOVA)
    coleta = Coleta(cred)
    try:
        uploads = coleta.canal()
        nome_canal = coleta.tabelas["canal.csv"][0]["titulo"]
        print(f"[2/6] Lendo os vídeos, playlists e comentários de \"{nome_canal}\"...", flush=True)
        coleta.videos(uploads)
        coleta.originais()
        coleta.playlists()
        coleta.comentarios()
        print("[3/6] Analytics do canal...", flush=True)
        coleta.relatorios_canal()
        for i, (video, publicado) in enumerate(coleta.videos_ids, 1):
            print(f"[4/6] Analytics dos vídeos: {i} de {len(coleta.videos_ids)}", flush=True)
            coleta.relatorios_video(video, publicado)
        coleta.sugeridores()
        print("[5/6] Relatórios em lote (Reporting API)...", flush=True)
        coleta.relatorios_lote(PASTA_NOVA, PASTA_ANALYTICS)
    except Fatal as e:
        shutil.rmtree(PASTA_NOVA, ignore_errors=True)
        print(f"Erro: {e}")
        print("Os dados anteriores de analytics\\ foram mantidos.")
        return 1
    except (HttpError, OSError) as e:
        shutil.rmtree(PASTA_NOVA, ignore_errors=True)
        print(f"Erro: {_motivo(e)[1] if isinstance(e, HttpError) else e}")
        print("Os dados anteriores de analytics\\ foram mantidos.")
        return 1

    print("[6/6] Gravando os CSVs em analytics\\...", flush=True)
    if os.path.isdir(os.path.join(PASTA_ANALYTICS, ANALISES)):
        shutil.copytree(os.path.join(PASTA_ANALYTICS, ANALISES), os.path.join(PASTA_NOVA, ANALISES))
    resumo = coleta.gravar(PASTA_NOVA)
    coleta.leia_me(PASTA_NOVA, resumo, nome_canal)
    # troca: a pasta antiga só some depois que a nova está no lugar
    shutil.rmtree(PASTA_ANTIGA, ignore_errors=True)
    try:
        if os.path.isdir(PASTA_ANALYTICS):
            os.rename(PASTA_ANALYTICS, PASTA_ANTIGA)
        os.rename(PASTA_NOVA, PASTA_ANALYTICS)
    except OSError as e:
        if not os.path.isdir(PASTA_ANALYTICS) and os.path.isdir(PASTA_ANTIGA):
            os.rename(PASTA_ANTIGA, PASTA_ANALYTICS)
        print(f"Erro: não foi possível substituir a pasta analytics\\ ({e}). Feche os CSVs abertos (Excel) e tente de novo;"
              " a coleta nova ficou em analytics.novo\\.")
        return 1
    shutil.rmtree(PASTA_ANTIGA, ignore_errors=True)
    recusadas = sum(1 for l in coleta.tabelas.get("coleta.csv", []) if l.get("erro"))
    print(f"Coleta finalizada! {len(resumo)} arquivos em analytics\\"
          + (f" ({recusadas} consulta(s) recusada(s); veja leia-me.txt)" if recusadas else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
