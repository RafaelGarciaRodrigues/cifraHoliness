"""Publicação dos vídeos de karaokê (pasta videos/) no YouTube, pela YouTube Data API v3
(google-api-python-client, videos.insert), com a thumbnail de videos/thumbnail/ (thumbnails.set).

A conta é conectada uma vez pela interface (Biblioteca → ⚙ YouTube), com o OAuth do Google: as
credenciais do app ficam em docs/client_secret_*.json, o token da conta em docs/youtube_token.json
e a parametrização (modelos de título/descrição, privacidade...) e os vídeos já publicados em
docs/youtube.json.

Uso (a interface chama pelo botão da coluna "YT"):
    python youtube.py <id> --arquivo "<vídeo em videos/>" --titulo "..." [--descricao "..."]
                      [--tags "a, b"] [--privacidade private|unlisted|public]
"""
import argparse
import glob
import json
import os
import re
import sys
import threading
import time
from datetime import datetime

from pastas import BASE_DIR, padrao_videos

# o retorno do OAuth é http://localhost (local), não https
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
# o Google pode devolver os escopos em outra ordem ou somados aos já concedidos
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

PASTA_DOCS = os.path.join(BASE_DIR, "docs")
PASTA_VIDEOS = os.path.join(BASE_DIR, "videos")
PASTA_THUMBNAIL = os.path.join(PASTA_VIDEOS, "thumbnail")  # capa de cada vídeo: <nome do vídeo>.jpg
CAMINHO_TOKEN = os.path.join(PASTA_DOCS, "youtube_token.json")
CAMINHO_ESTADO = os.path.join(PASTA_DOCS, "youtube.json")
# leitura do YouTube Analytics e da Reporting API (analytics.py); contas conectadas antes dele
# precisam entrar de novo ("Trocar conta") para autorizar
ESCOPO_ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"
ESCOPO_COMENTARIOS = "https://www.googleapis.com/auth/youtube.force-ssl"  # o commentThreads exige, mesmo só para ler
ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload",
           "https://www.googleapis.com/auth/youtube.readonly",  # nome do canal e vídeos
           ESCOPO_COMENTARIOS,
           ESCOPO_ANALYTICS]
ROTA_RETORNO = "/api/youtube/retorno"

PRIVACIDADES = ("private", "unlisted", "public")
CATEGORIAS = {"10": "Música", "22": "Pessoas e blogs", "24": "Entretenimento", "27": "Educação"}
CONFIG_PADRAO = {
    "titulo": "{titulo} - {artista} (Karaokê) - {voz}",
    "descricao": "{titulo}\nArtista: {artista}\nTom: {tom}\nExtensão vocal: {extensao}\nCategoria vocal: {voz}"
                 "\n\nVídeo de karaokê com a letra sincronizada."
                 "\n\nLetra:\n{letra}",
    "tags": "karaokê, letra, {artista}, {titulo}",
    # hashtags: vão no fim da descrição (é lá que o YouTube as reconhece; as 3 primeiras aparecem
    # acima do título). {titulo}/{artista} entram tudo junto, sem espaço
    "hashtags": "#{titulo} #{artista} #karaoke #playback #letra #piano #cifra #louvor #gospel #worship "
                "#pianotutorial #tutorialpiano #jesus",
    "categoria": "10",
    "privacidade": "private",
    "infantil": False,
    "idioma": "pt-BR",
    "notificar": True,
}
TRAVA = threading.Lock()
_FLUXOS = {}  # state do OAuth -> Flow (guarda o code_verifier até o Google redirecionar de volta)


# ---------------------------------------------------------------- estado (docs/youtube.json)
def _ler_estado():
    try:
        with open(CAMINHO_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _alterar_estado(funcao):
    with TRAVA:
        estado = _ler_estado()
        funcao(estado)
        os.makedirs(PASTA_DOCS, exist_ok=True)
        with open(CAMINHO_ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)


def config():
    return {**CONFIG_PADRAO, **_ler_estado().get("config", {})}


def salvar_config(campos):
    """Valida e grava a parametrização vinda da interface; devolve a configuração completa."""
    nova = config()
    for campo in ("titulo", "descricao", "tags", "hashtags", "idioma"):
        if campo in campos:
            nova[campo] = str(campos[campo] or "").strip()
    if "categoria" in campos:
        if str(campos["categoria"]) not in CATEGORIAS:
            raise ValueError("categoria inválida")
        nova["categoria"] = str(campos["categoria"])
    if "privacidade" in campos:
        if campos["privacidade"] not in PRIVACIDADES:
            raise ValueError("privacidade inválida")
        nova["privacidade"] = campos["privacidade"]
    for campo in ("infantil", "notificar"):
        if campo in campos:
            nova[campo] = bool(campos[campo])
    if not nova["titulo"]:
        raise ValueError("o modelo de título não pode ficar vazio")
    _alterar_estado(lambda e: e.__setitem__("config", nova))
    return nova


def publicados():
    """Nome do arquivo em videos/ -> {id_musica, video_id, url, titulo, privacidade, publicado_em}."""
    return _ler_estado().get("publicados", {})


def _registrar_publicacao(arquivo, dados):
    """Grava a publicação do arquivo. Se ele já tinha sido publicado (o YouTube não deixa trocar o
    arquivo de um vídeo: publicar de novo cria outro vídeo), as anteriores ficam em "anteriores",
    para lembrar de apagar no YouTube Studio."""
    def alterar(estado):
        publicados = estado.setdefault("publicados", {})
        antigo = publicados.get(arquivo)
        if antigo:
            anteriores = antigo.pop("anteriores", [])
            dados["anteriores"] = [antigo] + anteriores
        publicados[arquivo] = dados
    _alterar_estado(alterar)


# ---------------------------------------------------------------- vídeos da pasta videos/
def videos_da_musica(registro):
    """Vídeos gerados pelo video.py para a música (<base>.mp4, <base> (2).mp4...), do mais novo
    ao mais antigo. A base vem do título/artista atuais do cadastro."""
    if not os.path.isdir(PASTA_VIDEOS):
        return []
    padrao = padrao_videos(registro)  # todos os tons ("... - Tom F#.mp4") e os antigos, sem o tom
    nomes = [n for n in os.listdir(PASTA_VIDEOS) if padrao.fullmatch(n)]
    return sorted(nomes, key=lambda n: os.path.getmtime(os.path.join(PASTA_VIDEOS, n)), reverse=True)


def situacao_videos(registros):
    """id da música -> {arquivo: vídeo mais recente, publicado: dados da publicação ou None}."""
    ja_publicados = publicados()
    situacao = {}
    for r in registros:
        nomes = videos_da_musica(r)
        if nomes:
            situacao[r["id"]] = {"arquivo": nomes[0], "publicado": ja_publicados.get(nomes[0])}
    return situacao


# ---------------------------------------------------------------- conta (OAuth)
def caminho_segredo():
    """Credenciais do app no Google Cloud (client_secret_*.json baixado do console)."""
    achados = sorted(glob.glob(os.path.join(PASTA_DOCS, "client_secret*.json")))
    return achados[0] if achados else None


def redirect_uri(porta):
    return f"http://localhost:{porta}{ROTA_RETORNO}"


def credenciais():
    """Credenciais da conta conectada (renovadas se expiraram), ou None se não há conta."""
    if not os.path.isfile(CAMINHO_TOKEN):
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    # com os escopos gravados no token (os autorizados de fato), não os de ESCOPOS
    cred = Credentials.from_authorized_user_file(CAMINHO_TOKEN)
    if not cred.valid and cred.expired and cred.refresh_token:
        cred.refresh(Request())
        _salvar_token(cred)
    return cred


def _token_tem_escopo(escopo):
    try:
        with open(CAMINHO_TOKEN, encoding="utf-8") as f:
            return escopo in (json.load(f).get("scopes") or [])
    except (OSError, ValueError):
        return False


def _salvar_token(cred):
    os.makedirs(PASTA_DOCS, exist_ok=True)
    with open(CAMINHO_TOKEN, "w", encoding="utf-8") as f:
        f.write(cred.to_json())


def iniciar_conexao(porta):
    """Endereço da tela de login do Google; ela volta para ROTA_RETORNO com o código."""
    from google_auth_oauthlib.flow import Flow
    segredo = caminho_segredo()
    if not segredo:
        raise RuntimeError("credenciais da API não encontradas (docs/client_secret_*.json)")
    fluxo = Flow.from_client_secrets_file(segredo, scopes=ESCOPOS, redirect_uri=redirect_uri(porta))
    # offline + consent: o Google entrega o refresh_token, para não pedir login a cada envio
    url, estado = fluxo.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    with TRAVA:
        _FLUXOS[estado] = fluxo
    return url


def concluir_conexao(estado, url_retorno):
    """Troca o código devolvido pelo Google pelo token e guarda; devolve o nome do canal."""
    with TRAVA:
        fluxo = _FLUXOS.pop(estado, None)
    if fluxo is None:
        raise RuntimeError("login expirado ou desconhecido; clique em Conectar de novo")
    fluxo.fetch_token(authorization_response=url_retorno)
    _salvar_token(fluxo.credentials)
    canal = None
    try:
        from googleapiclient.discovery import build
        servico = build("youtube", "v3", credentials=fluxo.credentials, cache_discovery=False)
        itens = servico.channels().list(part="snippet", mine=True).execute().get("items", [])
        canal = itens[0]["snippet"]["title"] if itens else None
    except Exception:  # o nome do canal é só informativo
        pass
    _alterar_estado(lambda e: e.__setitem__("canal", canal))
    return canal


def desconectar():
    if os.path.isfile(CAMINHO_TOKEN):
        os.remove(CAMINHO_TOKEN)
    _alterar_estado(lambda e: e.pop("canal", None))


def situacao(porta):
    """Resumo para a tela de parametrização."""
    return {
        "credenciais": os.path.basename(caminho_segredo() or "") or None,
        "conectado": os.path.isfile(CAMINHO_TOKEN),
        "analytics": _token_tem_escopo(ESCOPO_ANALYTICS) and _token_tem_escopo(ESCOPO_COMENTARIOS),
        "canal": _ler_estado().get("canal"),
        "redirect_uri": redirect_uri(porta),
        "config": config(),
        "categorias": CATEGORIAS,
    }


def caminho_thumbnail(arquivo):
    """Capa do vídeo (videos/thumbnail/<nome do vídeo>.jpg), criada junto com ele; None se não existe."""
    caminho = os.path.join(PASTA_THUMBNAIL, os.path.splitext(arquivo)[0] + ".jpg")
    return caminho if os.path.isfile(caminho) else None


# ---------------------------------------------------------------- envio (videos.insert)
def _limpar_titulo(titulo):
    # o YouTube recusa "<" e ">" e títulos com mais de 100 caracteres
    return re.sub(r"\s+", " ", titulo.replace("<", "").replace(">", "")).strip()[:100]


def _limpar_tags(texto):
    tags, total = [], 0
    for t in (t.strip().replace("<", "").replace(">", "") for t in texto.split(",")):
        if t and t.lower() not in (x.lower() for x in tags) and total + len(t) <= 450:  # limite: 500
            tags.append(t)
            total += len(t) + 1
    return tags


def _limpar_hashtags(texto):
    """'#a #b, c' -> '#a #b #c':só letras, números e _ (sem espaço), sem repetir; acima de 60 o
    YouTube ignora todas, então fica nas 60 primeiras."""
    hashtags = []
    for t in re.split(r"[\s,;]+", texto):
        t = re.sub(r"[^\w]", "", t)
        if t and ("#" + t).lower() not in (x.lower() for x in hashtags):
            hashtags.append("#" + t)
    return " ".join(hashtags[:60])


def main(argumentos):
    p = argparse.ArgumentParser(description="Publica no YouTube um vídeo de karaokê da pasta videos/.")
    p.add_argument("id")
    p.add_argument("--arquivo", required=True, help="nome do vídeo dentro de videos/")
    p.add_argument("--titulo", required=True)
    p.add_argument("--descricao", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--hashtags", default="", help='palavras-chave para o fim da descrição: "#a #b"')
    p.add_argument("--privacidade", choices=PRIVACIDADES, default=None)
    a = p.parse_args(argumentos)

    caminho = os.path.join(PASTA_VIDEOS, a.arquivo)
    if os.path.basename(a.arquivo) != a.arquivo or not os.path.isfile(caminho):
        print(f"Erro: vídeo não encontrado: videos/{a.arquivo}")
        return 1
    titulo = _limpar_titulo(a.titulo)
    if not titulo:
        print("Erro: o título do vídeo está vazio.")
        return 1
    cfg = config()
    privacidade = a.privacidade or cfg["privacidade"]

    print("[1/4] Conectando ao YouTube...", flush=True)
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("Erro: instale as bibliotecas: pip install google-api-python-client google-auth-oauthlib")
        return 1
    try:
        cred = credenciais()
    except Exception as e:
        print(f"Erro: não foi possível renovar o acesso à conta ({e}); conecte a conta de novo no botão 'YouTube' da Biblioteca.")
        return 1
    if cred is None:
        print("Erro: nenhuma conta do YouTube conectada; use o botão 'YouTube' da Biblioteca.")
        return 1
    servico = build("youtube", "v3", credentials=cred, cache_discovery=False)

    descricao = a.descricao.replace("<", "").replace(">", "").rstrip()
    if hashtags := _limpar_hashtags(a.hashtags):  # no fim da descrição, sem cortar no limite de 5000
        descricao = (descricao[:5000 - len(hashtags) - 2] + "\n\n" + hashtags).lstrip()
    snippet = {"title": titulo, "description": descricao[:5000], "categoryId": cfg["categoria"]}
    if tags := _limpar_tags(a.tags):
        snippet["tags"] = tags
    if cfg["idioma"]:
        snippet["defaultLanguage"] = snippet["defaultAudioLanguage"] = cfg["idioma"]
    corpo = {"snippet": snippet,
             "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": cfg["infantil"], "embeddable": True}}
    midia = MediaFileUpload(caminho, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    pedido = servico.videos().insert(part="snippet,status", body=corpo, media_body=midia,
                                     notifySubscribers=cfg["notificar"])

    resposta, tentativas, ultimo = None, 0, -1
    while resposta is None:
        try:
            progresso, resposta = pedido.next_chunk()
            tentativas = 0
            if progresso and (pct := int(progresso.progress() * 100)) != ultimo:
                print(f"[2/4] Enviando o vídeo: {pct}%", flush=True)
                ultimo = pct
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tentativas < 5:
                tentativas += 1
                time.sleep(2 ** tentativas)
                continue
            motivo = e.reason or str(e)
            if "quota" in motivo.lower():
                motivo += " (a cota diária da API acabou; tente amanhã)"
            print(f"Erro: o YouTube recusou o envio: {motivo}")
            return 1
        except OSError as e:
            if tentativas < 5:
                tentativas += 1
                time.sleep(2 ** tentativas)
                continue
            print(f"Erro: falha de conexão durante o envio: {e}")
            return 1

    video_id = resposta["id"]
    if thumbnail := caminho_thumbnail(a.arquivo):
        print("[3/4] Enviando a thumbnail...", flush=True)
        try:
            servico.thumbnails().set(videoId=video_id,
                                     media_body=MediaFileUpload(thumbnail, mimetype="image/jpeg")).execute()
        except HttpError as e:  # o vídeo já foi publicado: só avisa (ex.: canal sem verificação de telefone)
            motivo = e.reason or str(e)
            if e.resp.status == 403:
                motivo += " (para usar thumbnails personalizadas o canal precisa ser verificado em youtube.com/verify)"
            print(f"Aviso: a thumbnail não foi enviada: {motivo}", flush=True)
        except OSError as e:
            print(f"Aviso: a thumbnail não foi enviada: {e}", flush=True)
    else:
        print("[3/4] Sem thumbnail em videos/thumbnail/ (crie o vídeo de novo para gerá-la)", flush=True)

    print("[4/4] Registrando a publicação...", flush=True)
    url = f"https://youtu.be/{video_id}"
    _registrar_publicacao(a.arquivo, {
        "id_musica": a.id, "video_id": video_id, "url": url, "titulo": titulo,
        "privacidade": resposta.get("status", {}).get("privacyStatus", privacidade),
        "publicado_em": datetime.now().isoformat(timespec="seconds"),
    })
    print(f"Publicado! {url}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
