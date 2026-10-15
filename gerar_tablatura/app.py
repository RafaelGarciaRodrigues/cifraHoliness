"""Interface única para todas as músicas processadas pelo solo.py.

Uso:
    python app.py                   # abre http://127.0.0.1:8765 no navegador
    python app.py 9000              # usa outra porta
    python app.py --sem-navegador   # só o servidor (o SOLO.bat abre o navegador)

Servidor local (só biblioteca padrão): serve interface.html, a API do cadastro (musicas.db),
os dados de cada música, as faixas separadas (com suporte a Range, necessário para o
navegador avançar/voltar no áudio), grava a letra editada em letras/, guarda as gravações de
microfone/câmera em midias/, processa áudios novos da pasta audio/ rodando o solo.py e publica os
vídeos de videos/ no YouTube rodando o youtube.py (um por vez, em fila).
"""
import html
import json
import math
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import afinar
import banco
import gravacoes
import encaixe
import letra
import mixagem
import pastas
import tonalidade
import youtube

BASE_DIR = pastas.BASE_DIR
INTERFACE = os.path.join(BASE_DIR, "interface.html")
SCRIPT_SOLO = os.path.join(BASE_DIR, "solo.py")
SCRIPT_VIDEO = os.path.join(BASE_DIR, "video.py")
SCRIPT_YOUTUBE = os.path.join(BASE_DIR, "youtube.py")
PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
PASTA_DADOS = os.path.join(BASE_DIR, "dados")
PASTA_LETRAS = os.path.join(BASE_DIR, "letras")
PASTA_INSTRUMENTOS = os.path.join(BASE_DIR, "instrumentos")
PASTA_NOTAS_VIDEO = os.path.join(tempfile.gettempdir(), "telacifras_notas_video")  # som das notas p/ o vídeo
TAMANHO_MAXIMO_NOTAS = 1 << 30  # Tone.js e amostras (som gerado no navegador)
# formato do vídeo -> (prefixo da tarefa na fila, início da linha do video.py que indica sucesso)
FORMATOS_VIDEO = {"padrao": ("video", "Vídeo finalizado"), "instagram": ("instagram", "Vídeo do Instagram finalizado")}
HOST = "127.0.0.1"  # só a própria máquina acessa
PORTA_PADRAO = 8765


def caminho_notas_video(id_musica, formato):
    """WAV temporário com o áudio do vídeo (a mistura do player; o video.py apaga no fim)."""
    return os.path.join(PASTA_NOTAS_VIDEO, f"{id_musica}-{formato}.wav")


# ---------------------------------------------------------------- processamento (fila)
class Processamentos:
    """Fila de tarefas pesadas, uma de cada vez: processar um áudio (`solo.py "<arquivo>"`,
    chave = nome do arquivo), criar um vídeo de karaokê (`video.py <id> ...`, chave = "video:<id>"; a versão do Instagram, "instagram:<id>")
    ou publicá-lo no YouTube (`youtube.py <id> ...`, chave = "youtube:<id>")."""

    def __init__(self):
        self.trava = threading.Lock()
        self.fila = deque()
        self.estado = {}    # chave -> {estado: na fila|processando|concluido|erro, etapa, log}
        self.comandos = {}  # chave -> (argumentos do script, início da linha que indica sucesso)
        self.tentativas = {}  # chave -> [tentativa atual, total de tentativas]
        self.ocupado = False

    def enfileirar(self, chave, argumentos=None, marcador_sucesso="Pipeline finalizado", tentativas=1):
        """tentativas > 1: se falhar, a tarefa volta para o fim da fila até esgotar as tentativas."""
        with self.trava:
            atual = self.estado.get(chave, {}).get("estado")
            if atual in ("na fila", "processando"):
                return False
            self.estado[chave] = {"estado": "na fila", "etapa": "aguardando na fila", "log": []}
            self.comandos[chave] = (argumentos or [SCRIPT_SOLO, chave], marcador_sucesso)
            self.tentativas[chave] = [1, max(1, tentativas)]
            self.fila.append(chave)
            if not self.ocupado:
                self.ocupado = True
                threading.Thread(target=self._trabalhar, daemon=True).start()
            return True

    def instantaneo(self):
        with self.trava:
            return {a: {**e, "log": e["log"][-15:]} for a, e in self.estado.items()}

    def _trabalhar(self):
        while True:
            with self.trava:
                if not self.fila:
                    self.ocupado = False
                    return
                chave = self.fila.popleft()
                info = self.estado[chave]
                tentativa, total = self.tentativas.get(chave, [1, 1])
                info.update(estado="processando", etapa="iniciando" + (f" (tentativa {tentativa} de {total})" if tentativa > 1 else ""))
                argumentos, marcador = self.comandos[chave]
            self._rodar(argumentos, marcador, info)
            with self.trava:
                tentativa, total = self.tentativas.get(chave, [1, 1])
                if info["estado"] == "erro" and tentativa < total:
                    self.tentativas[chave] = [tentativa + 1, total]
                    info["log"].append(f"--- falhou; tentando de novo (tentativa {tentativa + 1} de {total}) ---")
                    info.update(estado="na fila", etapa=f"falhou; vai tentar de novo ({tentativa + 1}ª de {total} tentativas)")
                    self.fila.append(chave)

    def _rodar(self, argumentos, marcador, info):
        ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.Popen(
                [sys.executable, *argumentos], cwd=BASE_DIR, env=ambiente,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
            )
            for linha in proc.stdout:
                linha = linha.rstrip()
                if not linha:
                    continue
                with self.trava:
                    info["log"].append(linha)
                    del info["log"][:-200]
                    if re.match(r"^\[\d/\d\]", linha) or linha.startswith("      Transcrevendo a voz"):
                        info["etapa"] = linha.strip()
            codigo = proc.wait()
        except OSError as e:
            codigo = -1
            info["log"].append(str(e))
        with self.trava:
            if codigo == 0 and any(l.startswith(marcador) for l in info["log"]):
                info.update(estado="concluido", etapa="concluído")
            else:
                info.update(estado="erro", etapa=f"falhou (código {codigo}); veja o log")


PROCESSAMENTOS = Processamentos()
TENTATIVAS_LOTE = 3  # "Processar todos os não processados": tentativas de cada áudio


# ---------------------------------------------------------------- vídeo renderizado no navegador
class SessoesVideo:
    """Vídeo de karaokê desenhado pela interface (o mesmo HTML/canvas das abas YouTube e Instagram do
    player): o navegador manda os quadros em JPEG, em lotes, e o FFmpeg os junta com o áudio (a mistura
    do player, já enviada em caminho_notas_video). A situação aparece na fila (PROCESSAMENTOS.estado),
    na chave do formato ("video:<id>" / "instagram:<id>"), como os vídeos do video.py."""
    PASTAS = {"padrao": os.path.join(BASE_DIR, "videos"), "instagram": os.path.join(BASE_DIR, "videos", "instagram")}
    QPS = 30
    MEDIDAS = {"padrao": (1280, 720), "instagram": (1080, 1920)}
    SEM_RESPOSTA = 120  # s sem receber quadros: o navegador fechou; a sessão é cancelada

    def __init__(self):
        self.trava = threading.Lock()
        self.sessoes = {}  # chave da fila -> {token, proc, saida, temporario, total, recebidos, audio, ultimo, trava}
        threading.Thread(target=self._vigiar, daemon=True).start()

    @staticmethod
    def nome_arquivo(registro, pasta):
        base = pastas.base_video(registro)
        caminho, n = os.path.join(pasta, base + ".mp4"), 2
        while os.path.exists(caminho):  # não sobrescreve vídeos anteriores
            caminho = os.path.join(pasta, f"{base} ({n}).mp4")
            n += 1
        return caminho

    def _estado(self, chave, **campos):
        with PROCESSAMENTOS.trava:
            info = PROCESSAMENTOS.estado.setdefault(chave, {"estado": "processando", "etapa": "", "log": []})
            linha = campos.pop("linha", None)
            if linha:
                info["log"].append(linha)
                del info["log"][:-200]
            info.update(campos)

    def iniciar(self, registro, formato, total, silencio, duracao):
        """Abre o FFmpeg para receber `total` quadros; devolve o token da sessão (ou lança ValueError)."""
        if shutil.which("ffmpeg") is None:
            raise ValueError("FFmpeg não encontrado no PATH do sistema")
        audio = caminho_notas_video(registro["id"], formato)
        if not os.path.isfile(audio):
            raise ValueError("o áudio do vídeo não foi recebido")
        chave = f"{FORMATOS_VIDEO[formato][0]}:{registro['id']}"
        with self.trava:
            if chave in self.sessoes or PROCESSAMENTOS.estado.get(chave, {}).get("estado") in ("na fila", "processando"):
                raise RuntimeError("este vídeo já está sendo criado")
            pasta = self.PASTAS[formato]
            os.makedirs(pasta, exist_ok=True)
            saida = self.nome_arquivo(registro, pasta)
            temporario = saida + ".parcial.mp4"
            largura, altura = self.MEDIDAS[formato]
            atraso = f",adelay=delays={int(round(silencio * 1000))}:all=1" if silencio > 0 else ""
            comando = ["ffmpeg", "-y", "-loglevel", "error",
                       "-f", "image2pipe", "-framerate", str(self.QPS), "-c:v", "mjpeg", "-i", "-",
                       "-t", f"{duracao:.3f}", "-i", audio,
                       "-filter_complex", f"[0:v]scale={largura}:{altura},format=yuv420p[v];"
                                          f"[1:a]alimiter=limit=0.95{atraso}[a]",
                       "-map", "[v]", "-map", "[a]",
                       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                       "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", temporario]
            proc = subprocess.Popen(comando, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            token = os.urandom(8).hex()
            self.sessoes[chave] = {"token": token, "proc": proc, "saida": saida, "temporario": temporario,
                                   "total": max(1, int(total)), "recebidos": 0, "audio": audio,
                                   "ultimo": time.time(), "trava": threading.Lock(), "formato": formato}
        self._estado(chave, estado="processando", etapa="[2/3] Renderizando o vídeo (no navegador): 0%", log=[],
                     linha="[1/3] Áudio recebido; renderizando os quadros do HTML...")
        return chave, token

    def _sessao(self, chave, token):
        with self.trava:
            s = self.sessoes.get(chave)
        if not s or s["token"] != token:
            raise KeyError("sessão de vídeo não encontrada (expirou ou foi cancelada)")
        return s

    def receber(self, chave, token, leitor, tamanho, quadros):
        """Repassa ao FFmpeg um lote de quadros JPEG (concatenados) lidos de `leitor`."""
        s = self._sessao(chave, token)
        with s["trava"]:
            restante = tamanho
            try:
                while restante > 0:
                    pedaco = leitor.read(min(1 << 20, restante))
                    if not pedaco:
                        raise OSError("envio interrompido")
                    s["proc"].stdin.write(pedaco)
                    restante -= len(pedaco)
            except OSError as e:
                self.cancelar(chave, token, f"o FFmpeg parou de receber os quadros: {e}")
                raise
            s["recebidos"] += quadros
            s["ultimo"] = time.time()
            pct = min(99, s["recebidos"] * 100 // s["total"])
        self._estado(chave, etapa=f"[2/3] Renderizando o vídeo (no navegador): {pct}%")

    @staticmethod
    def _erro_ffmpeg(s):
        try:
            return (s["proc"].stderr.read() or b"").decode("utf-8", "replace").strip()[-400:]
        except (OSError, ValueError):
            return ""

    def concluir(self, chave, token):
        """Fecha a entrada do FFmpeg e termina o arquivo numa thread (a resposta volta na hora)."""
        s = self._sessao(chave, token)
        self._estado(chave, etapa="[3/3] Finalizando o arquivo...", linha="[3/3] Finalizando o arquivo...")

        def terminar():
            with s["trava"]:
                try:
                    s["proc"].stdin.close()
                except OSError:
                    pass
                erro = self._erro_ffmpeg(s)
                codigo = s["proc"].wait()
            with self.trava:
                self.sessoes.pop(chave, None)
            self._apagar_audio(s)
            if codigo != 0 or not os.path.isfile(s["temporario"]):
                self._apagar(s["temporario"])
                self._estado(chave, estado="erro", etapa=f"falhou (código {codigo}); veja o log",
                             linha=f"Erro: o FFmpeg falhou ao gerar o vídeo. {erro}".strip())
                return
            os.replace(s["temporario"], s["saida"])
            marcador = FORMATOS_VIDEO[s["formato"]][1]
            self._estado(chave, estado="concluido", etapa="concluído",
                         linha=f"{marcador}! {os.path.relpath(s['saida'], BASE_DIR)}")

        threading.Thread(target=terminar, daemon=True).start()

    def cancelar(self, chave, token=None, motivo="cancelado"):
        with self.trava:
            s = self.sessoes.get(chave)
            if not s or (token is not None and s["token"] != token):
                return False
            self.sessoes.pop(chave, None)
        try:
            s["proc"].kill()
            s["proc"].wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        erro = self._erro_ffmpeg(s)  # o FFmpeg já terminou: a leitura não trava
        self._apagar(s["temporario"])
        self._apagar_audio(s)
        self._estado(chave, estado="erro", etapa="falhou; veja o log",
                     linha=f"Erro: vídeo não criado ({motivo}). {erro}".strip())
        return True

    @staticmethod
    def _apagar(caminho):
        try:
            os.remove(caminho)
        except OSError:
            pass

    def _apagar_audio(self, s):
        self._apagar(s["audio"])

    def _vigiar(self):
        while True:
            time.sleep(10)
            with self.trava:
                paradas = [c for c, s in self.sessoes.items() if time.time() - s["ultimo"] > self.SEM_RESPOSTA]
            for chave in paradas:
                self.cancelar(chave, motivo="o navegador parou de enviar os quadros")


SESSOES_VIDEO = SessoesVideo()


class Servidor(ThreadingHTTPServer):
    # Com SO_REUSEADDR (padrão do http.server), o Windows deixa duas instâncias escutarem a
    # mesma porta; em modo exclusivo, a segunda recebe erro e avisa que já está aberta.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def listar_audios():
    """Todos os áudios da pasta audio/, com o registro do cadastro quando já processados."""
    registros = {m["arquivo"]: m for m in banco.listar()}
    return [{"arquivo": n, "musica": registros.get(n)} for n in pastas.listar_audios()]

ID = r"([0-9a-f]{8})"
ROTA_MUSICA = re.compile(rf"^/api/musicas/{ID}$")
ROTA_LETRA = re.compile(rf"^/api/musicas/{ID}/letra$")
ROTA_ENCAIXE = re.compile(rf"^/api/musicas/{ID}/letra/encaixar$")
ROTA_VIDEO = re.compile(rf"^/api/musicas/{ID}/video$")
ROTA_VIDEO_NOTAS = re.compile(rf"^/api/musicas/{ID}/video/notas$")
ROTA_VIDEO_QUADROS = re.compile(rf"^/api/musicas/{ID}/video/quadros$")
ROTA_VIDEO_SESSAO = re.compile(rf"^/api/musicas/{ID}/video/(concluir|cancelar)$")
ROTA_YOUTUBE = re.compile(rf"^/api/musicas/{ID}/youtube$")
ROTA_FAIXA = re.compile(rf"^/faixas/{ID}/([a-z]+)\.wav$")
ROTA_GRAVACOES = re.compile(rf"^/api/musicas/{ID}/gravacoes$")
ROTA_GRAVACAO_NOVA = re.compile(rf"^/api/musicas/{ID}/gravacoes/(audio|video)$")
ROTA_GRAVACAO = re.compile(rf"^/api/musicas/{ID}/gravacoes/(audio|video)/([^/]+)$")
ROTA_MIDIA = re.compile(rf"^/midias/{ID}/(audio|video)/([^/]+)$")
ROTA_PICOS = re.compile(rf"^/api/musicas/{ID}/picos/(faixa|audio|video)/([^/]+)$")
ROTA_FAIXA_API = re.compile(rf"^/api/musicas/{ID}/faixas/([a-z]+)$")
ROTA_INSTRUMENTO = re.compile(r"^/instrumentos/((?:[a-z0-9_-]+/)?[A-Za-z0-9_#.-]+\.(?:js|mp3|wav|ogg))$")
ROTA_NOTAS = re.compile(rf"^/api/musicas/{ID}/notas/([a-z]+)$")
ROTA_MIDI = re.compile(rf"^/api/musicas/{ID}/midi/([a-z0-9]{{1,20}})$")  # gravações do teclado MIDI
ROTA_REPROCESSAR = re.compile(rf"^/api/musicas/{ID}/reprocessar/([a-z]+)$")  # varinha mágica (afinar.py)
TRAVA_DADOS = threading.Lock()  # dados/<id>.json é regravado por mais de uma rota
INICIO_SERVIDOR = time.time()


def servidor_desatualizado():
    """O interface.html é lido do disco a cada acesso, mas o código Python só ao iniciar: se algum
    .py mudou depois disso, as rotas novas ainda não existem e é preciso reiniciar o servidor."""
    return any(os.path.getmtime(os.path.join(BASE_DIR, n)) > INICIO_SERVIDOR
               for n in os.listdir(BASE_DIR) if n.endswith(".py"))
BLOCO = 256 * 1024


class Manipulador(BaseHTTPRequestHandler):
    server_version = "TelaSolos/1.0"

    # ------------------------------------------------------------ respostas
    def _json(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, status, mensagem):
        self._json({"erro": mensagem}, status)

    def _html(self, titulo, texto, status=200):
        """Página simples (retorno do login do Google, aberto numa janela à parte)."""
        corpo = (f'<!doctype html><meta charset="utf-8"><title>{html.escape(titulo)}</title>'
                 f'<body style="font:16px system-ui;padding:32px"><h2>{html.escape(titulo)}</h2>'
                 f'<p>{html.escape(texto)}</p><p>Pode fechar esta janela.</p>'
                 '<script>if (window.opener) { window.opener.postMessage("youtube", "*"); '
                 'setTimeout(() => window.close(), 1500); }</script>').encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _ler_json(self):
        # Exigir JSON impede que outros sites façam POST "simples" para o servidor local
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ValueError("Content-Type deve ser application/json")
        tamanho = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(tamanho) or b"{}")

    def _arquivo(self, caminho, tipo=None):
        """Envia um arquivo, respeitando o cabeçalho Range (resposta 206)."""
        tamanho = os.path.getsize(caminho)
        inicio, fim = 0, tamanho - 1
        faixa = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if faixa and (faixa.group(1) or faixa.group(2)):
            if faixa.group(1):
                inicio = int(faixa.group(1))
                fim = min(int(faixa.group(2)), tamanho - 1) if faixa.group(2) else tamanho - 1
            else:  # "bytes=-N": últimos N bytes
                inicio = max(0, tamanho - int(faixa.group(2)))
            if inicio > fim:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{tamanho}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inicio}-{fim}/{tamanho}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo or mimetypes.guess_type(caminho)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(fim - inicio + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(caminho, "rb") as f:
            f.seek(inicio)
            restante = fim - inicio + 1
            while restante > 0:
                pedaco = f.read(min(BLOCO, restante))
                if not pedaco:
                    break
                self.wfile.write(pedaco)
                restante -= len(pedaco)

    # ------------------------------------------------------------ rotas
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        caminho = unquote(urlparse(self.path).path)
        try:
            if caminho in ("/", "/index.html"):
                return self._arquivo(INTERFACE, "text/html; charset=utf-8")
            if caminho in ("/documentacao", "/ajuda"):  # a aba Ajuda da interface (documentação e referências)
                self.send_response(302)
                self.send_header("Location", "/#ajuda")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if caminho == "/api/musicas":
                return self._json(banco.listar())
            if caminho == "/api/servidor":
                return self._json({"desatualizado": servidor_desatualizado()})
            if caminho == "/api/youtube":
                return self._json({**youtube.situacao(self.server.server_address[1]),
                                   "videos": youtube.situacao_videos(banco.listar()),
                                   "processamentos": PROCESSAMENTOS.instantaneo()})
            if caminho == "/api/youtube/conectar":
                return self._conectar_youtube()
            if caminho == youtube.ROTA_RETORNO:
                return self._retorno_youtube()
            if caminho == "/api/audios":
                return self._json({"audios": listar_audios(), "processamentos": PROCESSAMENTOS.instantaneo()})
            if m := ROTA_MUSICA.match(caminho):
                return self._musica(m.group(1))
            if m := ROTA_LETRA.match(caminho):
                return self._letra(m.group(1))
            if m := ROTA_FAIXA.match(caminho):
                arquivo = os.path.join(PASTA_FAIXAS, m.group(1), m.group(2) + ".wav")
                if os.path.isfile(arquivo):
                    return self._arquivo(arquivo, "audio/wav")
            if m := ROTA_GRAVACOES.match(caminho):
                return self._json(gravacoes.listar(m.group(1)))
            if m := ROTA_MIDIA.match(caminho):
                if arquivo := gravacoes.caminho(*m.groups()):
                    return self._arquivo(arquivo, gravacoes.tipo_mime(m.group(2), m.group(3)))
            if m := ROTA_PICOS.match(caminho):
                return self._picos(*m.groups())
            if (m := ROTA_INSTRUMENTO.match(caminho)) and ".." not in m.group(1):
                arquivo = os.path.join(PASTA_INSTRUMENTOS, *m.group(1).split("/"))
                if os.path.isfile(arquivo):
                    return self._arquivo(arquivo, "text/javascript" if arquivo.endswith(".js") else None)
            self._erro(404, "não encontrado")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # o navegador cancelou o download (comum ao avançar no áudio)

    def do_POST(self):
        url = urlparse(self.path)
        caminho = url.path
        if m := ROTA_VIDEO.match(caminho):
            return self._criar_video(m.group(1))
        if m := ROTA_VIDEO_SESSAO.match(caminho):
            return self._sessao_video(*m.groups())
        if m := ROTA_YOUTUBE.match(caminho):
            return self._publicar_youtube(m.group(1))
        if m := ROTA_ENCAIXE.match(caminho):
            return self._encaixar_letra(m.group(1))
        if m := ROTA_REPROCESSAR.match(caminho):
            return self._reprocessar_notas(*m.groups())
        if caminho == "/api/youtube/desconectar":
            youtube.desconectar()
            return self._json({"ok": True})
        if m := ROTA_GRAVACAO_NOVA.match(caminho):
            return self._salvar_gravacao(m.group(1), m.group(2), url.query)
        if caminho != "/api/processar":
            return self._erro(404, "não encontrado")
        try:
            corpo = self._ler_json()
            arquivo = str(corpo.get("arquivo", ""))
        except (ValueError, TypeError, AttributeError) as e:
            return self._erro(400, str(e))
        if corpo.get("todos"):
            # todos os áudios ainda não processados; se um falhar, tenta de novo (até 3 vezes)
            pendentes = [a["arquivo"] for a in listar_audios() if not a["musica"]]
            novos = [a for a in pendentes if PROCESSAMENTOS.enfileirar(a, tentativas=TENTATIVAS_LOTE)]
            return self._json({"ok": True, "enfileirados": novos, "processamentos": PROCESSAMENTOS.instantaneo()})
        # só aceita nomes que estão de fato na pasta audio/ (nada de caminhos arbitrários)
        if arquivo not in pastas.listar_audios():
            return self._erro(404, f"'{arquivo}' não está na pasta audio")
        PROCESSAMENTOS.enfileirar(arquivo)
        self._json({"ok": True, "processamentos": PROCESSAMENTOS.instantaneo()})

    def do_PATCH(self):
        caminho = urlparse(self.path).path
        if g := ROTA_GRAVACAO.match(caminho):
            try:
                item = gravacoes.atualizar(*g.groups(), self._ler_json())
            except (ValueError, TypeError) as e:
                return self._erro(400, str(e))
            return self._json(item) if item else self._erro(404, "gravação não encontrada")
        m = ROTA_MUSICA.match(caminho)
        if not m:
            return self._erro(404, "não encontrado")
        try:
            campos = self._ler_json()
            registro = banco.atualizar(m.group(1), campos)
        except (ValueError, TypeError) as e:
            return self._erro(400, str(e))
        if registro is None:
            return self._erro(404, "música não cadastrada")
        self._json(registro)

    def do_PUT(self):
        caminho = urlparse(self.path).path
        if caminho == "/api/youtube/config":
            try:
                return self._json(youtube.salvar_config(self._ler_json()))
            except (ValueError, TypeError, AttributeError) as e:
                return self._erro(400, str(e))
        if n := ROTA_NOTAS.match(caminho):
            return self._salvar_notas(*n.groups())
        if n := ROTA_MIDI.match(caminho):
            return self._salvar_midi(*n.groups())
        if n := ROTA_VIDEO_NOTAS.match(caminho):
            return self._salvar_notas_video(n.group(1), urlparse(self.path).query)
        if n := ROTA_VIDEO_QUADROS.match(caminho):
            return self._quadros_video(n.group(1), urlparse(self.path).query)
        m = ROTA_LETRA.match(caminho)
        if not m:
            return self._erro(404, "não encontrado")
        id_musica = m.group(1)
        registro = banco.obter(id_musica)
        if registro is None:
            return self._erro(404, "música não cadastrada")
        try:
            frases = [{"inicio": max(0.0, float(f["inicio"])), "fim": float(f["fim"]), "texto": str(f["texto"])}
                      for f in self._ler_json().get("frases", [])]
        except (ValueError, TypeError, KeyError) as e:
            return self._erro(400, f"letra inválida: {e}")
        for f in frases:
            f["fim"] = max(f["fim"], f["inicio"] + 0.05)
        caminho = letra.localizar(PASTA_LETRAS, id_musica) or letra.caminho_novo(
            PASTA_LETRAS, id_musica, os.path.splitext(registro["arquivo"])[0])
        letra.escrever(caminho, frases, registro["titulo"] or registro["arquivo"], id_musica)
        banco.atualizar_qtd_frases(id_musica, len(frases))
        self._json({"ok": True, "arquivo": os.path.basename(caminho), "frases": len(frases)})

    def do_DELETE(self):
        url = urlparse(self.path)
        caminho = url.path
        if m := ROTA_MIDI.match(caminho):
            return self._excluir_midi(*m.groups())
        if m := ROTA_MUSICA.match(caminho):
            return self._excluir_musica(m.group(1), parse_qs(url.query).get("audio") == ["1"])
        if caminho == "/api/audios":
            return self._excluir_audio((parse_qs(url.query).get("arquivo") or [""])[0])
        if m := ROTA_FAIXA_API.match(caminho):
            notas = parse_qs(url.query).get("notas") == ["1"]  # tabela das faixas: apaga também as notas
            with TRAVA_DADOS:
                excluida = mixagem.excluir_faixa(PASTA_FAIXAS, PASTA_DADOS, *m.groups(), notas=notas)
            if not excluida:
                return self._erro(404, "faixa não encontrada")
            return self._json({"ok": True})
        m = ROTA_GRAVACAO.match(caminho)
        if not m:
            return self._erro(404, "não encontrado")
        if not gravacoes.excluir(*m.groups()):
            return self._erro(404, "gravação não encontrada")
        self._json({"ok": True})

    # ------------------------------------------------------------ excluir (aba Biblioteca)
    def _processando(self, arquivo=None, id_musica=None):
        """Há processamento (ou vídeo/publicação) desta música na fila ou rodando?"""
        chaves = {arquivo} | ({f"{p}:{id_musica}" for p in ("video", "instagram", "youtube")} if id_musica else set())
        return any(e["estado"] in ("na fila", "processando")
                   for c, e in PROCESSAMENTOS.instantaneo().items() if c in chaves)

    def _excluir_musica(self, id_musica, com_audio):
        """Apaga a música: cadastro, dados/<id>.json, faixas/<id>/, gravações (midias/<id>/) e a letra;
        com_audio, também o arquivo em audio/ (senão ele volta para a lista como não processado).
        Os vídeos de videos/ ficam."""
        registro = banco.obter(id_musica)
        if registro is None:
            return self._erro(404, "música não cadastrada")
        if self._processando(registro["arquivo"], id_musica):
            return self._erro(409, "a música está sendo processada (ou o vídeo dela): espere terminar")
        apagados = []
        try:
            with TRAVA_DADOS:
                banco.excluir(id_musica)
                for pasta in (os.path.join(PASTA_FAIXAS, id_musica), os.path.join(gravacoes.PASTA_MIDIAS, id_musica)):
                    if os.path.isdir(pasta):
                        shutil.rmtree(pasta)
                        apagados.append(os.path.relpath(pasta, BASE_DIR) + os.sep)
                arquivos = [os.path.join(PASTA_DADOS, f"{id_musica}.json"), letra.localizar(PASTA_LETRAS, id_musica)]
                if com_audio and os.path.basename(registro["arquivo"]) in pastas.listar_audios():
                    arquivos.append(os.path.join(pastas.PASTA_AUDIO, registro["arquivo"]))
                for arquivo in arquivos:
                    if arquivo and os.path.isfile(arquivo):
                        os.remove(arquivo)
                        apagados.append(os.path.relpath(arquivo, BASE_DIR))
        except OSError as e:
            return self._erro(500, f"apagada só em parte ({', '.join(apagados) or 'nada'}): {e}")
        self._json({"ok": True, "apagados": apagados})

    def _excluir_audio(self, arquivo):
        """Apaga um áudio ainda não processado da pasta audio/ (só nomes que estão de fato nela)."""
        if arquivo not in pastas.listar_audios():
            return self._erro(404, f"'{arquivo}' não está na pasta audio")
        if self._processando(arquivo):
            return self._erro(409, "o áudio está sendo processado: espere terminar")
        try:
            os.remove(os.path.join(pastas.PASTA_AUDIO, arquivo))
        except OSError as e:
            return self._erro(500, f"não foi possível apagar: {e}")
        self._json({"ok": True})

    def _salvar_notas(self, id_musica, fonte):
        """Notas editadas na interface: substitui melodias[fonte] em dados/<id>.json."""
        caminho_dados = os.path.join(PASTA_DADOS, f"{id_musica}.json")
        if banco.obter(id_musica) is None or not os.path.isfile(caminho_dados):
            return self._erro(404, "música não encontrada")
        try:
            notas = []
            for n in self._ler_json().get("notas", []):
                nota = {"t": round(max(0.0, float(n["t"])), 3), "d": round(max(0.01, float(n["d"])), 3), "midi": int(n["midi"])}
                if not 0 <= nota["midi"] <= 127:
                    raise ValueError(f"nota MIDI fora da faixa: {nota['midi']}")
                if "f" in n:  # no "solo": de qual faixa veio a nota
                    if not re.fullmatch(r"[a-z]+", str(n["f"])):
                        raise ValueError("faixa de origem inválida")
                    nota["f"] = str(n["f"])
                notas.append(nota)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            return self._erro(400, f"notas inválidas: {e}")
        with TRAVA_DADOS:
            with open(caminho_dados, encoding="utf-8") as f:
                dados = json.load(f)
            if fonte not in dados.get("melodias", {}):
                return self._erro(404, f"fonte de notas desconhecida: {fonte}")
            dados["melodias"][fonte] = sorted(notas, key=lambda n: n["t"])
            with open(caminho_dados, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
        self._json({"ok": True, "notas": len(notas)})

    # ------------------------------------------------------------ gravações MIDI
    # Ficam em dados/<id>.json, em "midi": {gravação: {nome, criado_em, notas: [{t, d, midi, v}]}}
    # (v = força da tecla, 1 a 127). A interface grava, edita e apaga; o solo.py as preserva.
    def _salvar_midi(self, id_musica, gravacao):
        caminho_dados = os.path.join(PASTA_DADOS, f"{id_musica}.json")
        if banco.obter(id_musica) is None or not os.path.isfile(caminho_dados):
            return self._erro(404, "música não encontrada")
        try:
            corpo = self._ler_json()
            nome = re.sub(r"\s+", " ", str(corpo.get("nome") or "")).strip()[:60]
            notas = []
            for n in corpo.get("notas", []):
                nota = {"t": round(max(0.0, float(n["t"])), 3), "d": round(max(0.01, float(n["d"])), 3),
                        "midi": int(n["midi"]), "v": int(n.get("v", 100))}
                if not 0 <= nota["midi"] <= 127 or not 1 <= nota["v"] <= 127:
                    raise ValueError("nota ou força fora da faixa MIDI")
                notas.append(nota)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            return self._erro(400, f"gravação MIDI inválida: {e}")
        with TRAVA_DADOS:
            with open(caminho_dados, encoding="utf-8") as f:
                dados = json.load(f)
            todas = dados.setdefault("midi", {})
            atual = todas.get(gravacao, {})
            todas[gravacao] = {"nome": nome or atual.get("nome") or f"MIDI {len(todas) + 1}",
                               "criado_em": atual.get("criado_em") or datetime.now().isoformat(timespec="seconds"),
                               "notas": sorted(notas, key=lambda n: n["t"])}
            with open(caminho_dados, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
        self._json({"ok": True, "gravacao": todas[gravacao] | {"id": gravacao}})

    def _excluir_midi(self, id_musica, gravacao):
        caminho_dados = os.path.join(PASTA_DADOS, f"{id_musica}.json")
        if not os.path.isfile(caminho_dados):
            return self._erro(404, "música não encontrada")
        with TRAVA_DADOS:
            with open(caminho_dados, encoding="utf-8") as f:
                dados = json.load(f)
            if gravacao not in dados.get("midi", {}):
                return self._erro(404, "gravação MIDI não encontrada")
            del dados["midi"][gravacao]
            with open(caminho_dados, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
        self._json({"ok": True})

    def _picos(self, id_musica, tipo, nome):
        if tipo == "faixa":
            arquivo = os.path.join(PASTA_FAIXAS, id_musica, nome + ".wav")
            arquivo = arquivo if re.fullmatch(r"[a-z]+", nome) and os.path.isfile(arquivo) else None
        else:
            arquivo = gravacoes.caminho(id_musica, tipo, nome)
        if not arquivo:
            return self._erro(404, "não encontrado")
        try:
            self._json(mixagem.picos(arquivo))
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self._erro(503, f"forma de onda indisponível: {e}")

    def _salvar_gravacao(self, id_musica, tipo, consulta):
        if banco.obter(id_musica) is None:
            return self._erro(404, "música não cadastrada")
        mime = self.headers.get("Content-Type", "")
        # Corpo binário em vez de JSON: audio/* e video/* também não são tipos "simples" para o
        # navegador, então outros sites continuam sem conseguir enviar para o servidor local.
        if not mime.startswith(("audio/", "video/")):
            return self._erro(400, "Content-Type deve ser audio/* ou video/*")
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            params = {k: v[0] for k, v in parse_qs(consulta).items()}
            inicio = float(params.get("inicio", 0))
            velocidade = float(params.get("velocidade", 1))
            duracao = float(params["duracao"]) if "duracao" in params else None
        except ValueError as e:
            return self._erro(400, str(e))
        if not 0 < tamanho <= gravacoes.TAMANHO_MAXIMO:
            return self._erro(400, "gravação vazia ou grande demais")
        if duracao is not None and not math.isfinite(duracao):
            duracao = None
        try:
            item = gravacoes.salvar(id_musica, tipo, mime, self.rfile, tamanho, inicio, velocidade, duracao)
        except ValueError as e:
            return self._erro(400, str(e))
        except OSError as e:
            return self._erro(500, f"não foi possível salvar: {e}")
        self._json(item, 201)

    def _salvar_notas_video(self, id_musica, query):
        """Recebe o WAV com o áudio do próximo vídeo do formato ?formato=padrao|instagram: a mistura do
        player renderizada no navegador (um arquivo por formato: os dois podem estar na fila)."""
        if banco.obter(id_musica) is None:
            return self._erro(404, "música não cadastrada")
        formato = (parse_qs(query).get("formato") or ["padrao"])[0]
        if formato not in FORMATOS_VIDEO:
            return self._erro(400, "formato de vídeo inválido")
        if self.headers.get("Content-Type", "") != "audio/wav":
            return self._erro(400, "Content-Type deve ser audio/wav")
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not 44 < tamanho <= TAMANHO_MAXIMO_NOTAS:
            return self._erro(400, "áudio vazio ou grande demais")
        os.makedirs(PASTA_NOTAS_VIDEO, exist_ok=True)
        destino = caminho_notas_video(id_musica, formato)
        try:
            with open(destino + ".parcial", "wb") as f:
                restante = tamanho
                while restante > 0:
                    pedaco = self.rfile.read(min(1 << 20, restante))
                    if not pedaco:
                        raise OSError("envio interrompido")
                    f.write(pedaco)
                    restante -= len(pedaco)
            os.replace(destino + ".parcial", destino)
        except OSError as e:
            return self._erro(500, f"não foi possível salvar: {e}")
        self._json({"ok": True})

    def _criar_video(self, id_musica):
        if (registro := banco.obter(id_musica)) is None:
            return self._erro(404, "música não cadastrada")
        try:
            corpo = self._ler_json()
            if corpo.get("html"):  # quadros desenhados pela interface (abas YouTube/Instagram do player)
                return self._iniciar_video_html(registro, corpo)
            faixas = [str(f) for f in corpo.get("faixas", [])]
            inicio = max(0.0, float(corpo.get("inicio") or 0))
            fim = corpo.get("fim")
            fim = float(fim) if fim is not None else None
            notas = str(corpo.get("notas") or "solo")
            audio_mixado = bool(corpo.get("audioMixado"))
            formato = str(corpo.get("formato") or "padrao")
        except (ValueError, TypeError) as e:
            return self._erro(400, str(e))
        if formato not in FORMATOS_VIDEO:
            return self._erro(400, "formato de vídeo inválido")
        faixas = [f for f in faixas if re.fullmatch(r"[a-z]+", f)
                  and os.path.isfile(os.path.join(PASTA_FAIXAS, id_musica, f + ".wav"))]
        if not faixas:
            return self._erro(400, "marque ao menos uma faixa para o áudio do vídeo")
        argumentos = [SCRIPT_VIDEO, id_musica, "--faixas", ",".join(faixas), "--inicio", f"{inicio:.3f}",
                      "--formato", formato]
        if fim is not None:
            argumentos += ["--fim", f"{fim:.3f}"]
        if re.fullmatch(r"(?:[a-z]+|midi:[a-z0-9]+)(?:,(?:[a-z]+|midi:[a-z0-9]+))*", notas):  # notas do piano no vídeo
            argumentos += ["--notas", notas]
        audio = caminho_notas_video(id_musica, formato)
        usa_mistura = audio_mixado and os.path.isfile(audio)
        if usa_mistura:  # a mistura do player (o video.py apaga no fim)
            argumentos += ["--audio", audio]
        chave, marcador = FORMATOS_VIDEO[formato]
        PROCESSAMENTOS.enfileirar(f"{chave}:{id_musica}", argumentos, marcador)
        # "audio": confirma à interface que o vídeo usa a mistura enviada (servidor atualizado)
        self._json({"ok": True, "audio": usa_mistura, "processamentos": PROCESSAMENTOS.instantaneo()})

    def _iniciar_video_html(self, registro, corpo):
        formato = str(corpo.get("formato") or "padrao")
        if formato not in FORMATOS_VIDEO:
            return self._erro(400, "formato de vídeo inválido")
        try:
            total = int(corpo["total"])
            silencio = max(0.0, float(corpo.get("silencio") or 0))
            duracao = float(corpo["duracao"])
        except (KeyError, ValueError, TypeError) as e:
            return self._erro(400, f"parâmetros inválidos: {e}")
        if not 0 < total <= 30 * 60 * 60 or duracao <= 0:
            return self._erro(400, "duração do vídeo inválida")
        try:
            chave, token = SESSOES_VIDEO.iniciar(registro, formato, total, silencio, duracao)
        except RuntimeError as e:
            return self._erro(409, str(e))
        except (ValueError, OSError) as e:
            return self._erro(400, str(e))
        self._json({"ok": True, "sessao": token, "processamentos": PROCESSAMENTOS.instantaneo()})

    def _quadros_video(self, id_musica, query):
        """Lote de quadros JPEG (concatenados) do vídeo em criação: ?formato=&sessao=&n=<quadros>."""
        q = parse_qs(query)
        formato = (q.get("formato") or [""])[0]
        if formato not in FORMATOS_VIDEO or self.headers.get("Content-Type", "") != "image/jpeg":
            return self._erro(400, "formato ou Content-Type inválido")
        try:
            n = int((q.get("n") or ["0"])[0])
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._erro(400, "parâmetros inválidos")
        if tamanho <= 0 or tamanho > 1 << 30:
            return self._erro(400, "lote vazio ou grande demais")
        chave = f"{FORMATOS_VIDEO[formato][0]}:{id_musica}"
        try:
            SESSOES_VIDEO.receber(chave, (q.get("sessao") or [""])[0], self.rfile, tamanho, n)
        except KeyError as e:
            return self._erro(404, str(e.args[0]))
        except OSError as e:
            return self._erro(500, f"o vídeo falhou: {e}")
        self._json({"ok": True})

    def _sessao_video(self, id_musica, acao):
        try:
            corpo = self._ler_json()
            formato, token = str(corpo.get("formato") or ""), str(corpo.get("sessao") or "")
        except (ValueError, TypeError, AttributeError) as e:
            return self._erro(400, str(e))
        if formato not in FORMATOS_VIDEO:
            return self._erro(400, "formato de vídeo inválido")
        chave = f"{FORMATOS_VIDEO[formato][0]}:{id_musica}"
        if acao == "cancelar":
            SESSOES_VIDEO.cancelar(chave, token, str(corpo.get("motivo") or "cancelado na interface")[:300])
            return self._json({"ok": True, "processamentos": PROCESSAMENTOS.instantaneo()})
        try:
            SESSOES_VIDEO.concluir(chave, token)
        except KeyError as e:
            return self._erro(404, str(e.args[0]))
        self._json({"ok": True, "processamentos": PROCESSAMENTOS.instantaneo()})

    # ------------------------------------------------------------ YouTube
    def _conectar_youtube(self):
        """Abre (numa janela à parte) o login do Google para autorizar o envio de vídeos."""
        try:
            url = youtube.iniciar_conexao(self.server.server_address[1])
        except ImportError:
            return self._html("Bibliotecas ausentes",
                              "Instale: pip install google-api-python-client google-auth-oauthlib", 500)
        except (RuntimeError, OSError, ValueError) as e:
            return self._html("Não foi possível conectar", str(e), 500)
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _retorno_youtube(self):
        params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        if "error" in params:
            return self._html("Conexão cancelada", f"O Google respondeu: {params['error']}", 400)
        # o Google volta para http://localhost:<porta>/...; é esse endereço que o OAuth confere
        url_retorno = f"http://localhost:{self.server.server_address[1]}{self.path}"
        try:
            canal = youtube.concluir_conexao(params.get("state", ""), url_retorno)
        except Exception as e:  # erros do oauthlib/Google têm vários tipos
            return self._html("Não foi possível conectar", str(e), 400)
        self._html("Conta do YouTube conectada", f"Canal: {canal}" if canal else "Conta conectada.")

    def _encaixar_letra(self, id_musica):
        """Encaixa as linhas da letra na faixa de voz (encaixe.py); demora na 1ª vez de cada música."""
        if banco.obter(id_musica) is None:
            return self._erro(404, "música não cadastrada")
        try:
            linhas = [str(l) for l in self._ler_json().get("linhas", [])][:500]
        except (ValueError, TypeError, AttributeError) as e:
            return self._erro(400, str(e))
        if not linhas:
            return self._erro(400, "nenhuma linha de letra")
        if not os.path.isfile(os.path.join(PASTA_FAIXAS, id_musica, "vocals.wav")):
            return self._erro(400, "faixa de voz (vocals.wav) não encontrada; processe a música de novo")
        if not encaixe.disponivel():
            return self._erro(400, "o modelo de voz não carrega (pip install transformers torch): "
                                   f"{encaixe.ERRO_IMPORT}")
        try:
            trechos = encaixe.encaixar_musica(id_musica, linhas)
        except Exception as e:  # download do modelo, memória...
            return self._erro(500, f"falha no encaixe: {e}")
        self._json({"trechos": trechos})

    def _reprocessar_notas(self, id_musica, fonte):
        """Varinha mágica: notas novas de uma faixa (afinar.py). Não grava: a interface aplica e salva."""
        if banco.obter(id_musica) is None or not os.path.isfile(os.path.join(PASTA_DADOS, f"{id_musica}.json")):
            return self._erro(404, "música não encontrada")
        try:
            notas, metodo = afinar.reprocessar(id_musica, fonte)
        except KeyError as e:
            return self._erro(404, str(e.args[0]))
        except FileNotFoundError as e:
            return self._erro(400, str(e))
        except Exception as e:  # librosa, memória...
            return self._erro(500, f"falha ao reprocessar: {e}")
        self._json({"notas": notas, "metodo": metodo})

    def _publicar_youtube(self, id_musica):
        registro = banco.obter(id_musica)
        if registro is None:
            return self._erro(404, "música não cadastrada")
        try:
            corpo = self._ler_json()
            arquivo = str(corpo.get("arquivo", ""))
            titulo = str(corpo.get("titulo") or "").strip()
            descricao = str(corpo.get("descricao") or "")
            tags = str(corpo.get("tags") or "")
            hashtags = str(corpo.get("hashtags") or "")
            privacidade = str(corpo.get("privacidade") or youtube.config()["privacidade"])
        except (ValueError, TypeError) as e:
            return self._erro(400, str(e))
        # só vídeos gerados para esta música (nada de caminhos arbitrários)
        if arquivo not in youtube.videos_da_musica(registro):
            return self._erro(404, f"vídeo '{arquivo}' não encontrado em videos/")
        if not titulo:
            return self._erro(400, "informe o título do vídeo")
        if privacidade not in youtube.PRIVACIDADES:
            return self._erro(400, "privacidade inválida")
        if not os.path.isfile(youtube.CAMINHO_TOKEN):
            return self._erro(400, "conecte a conta do YouTube em ⚙ YouTube antes de publicar")
        argumentos = [SCRIPT_YOUTUBE, id_musica, "--arquivo", arquivo, "--titulo", titulo,
                      "--descricao", descricao, "--tags", tags, "--hashtags", hashtags,
                      "--privacidade", privacidade]
        PROCESSAMENTOS.enfileirar(f"youtube:{id_musica}", argumentos, "Publicado!")
        self._json({"ok": True, "processamentos": PROCESSAMENTOS.instantaneo()})

    # ------------------------------------------------------------ dados
    def _musica(self, id_musica):
        registro = banco.obter(id_musica)
        caminho_dados = os.path.join(PASTA_DADOS, f"{id_musica}.json")
        if registro is None or not os.path.isfile(caminho_dados):
            return self._erro(404, "música não encontrada; rode o solo.py novamente")
        with open(caminho_dados, encoding="utf-8") as f:
            dados = json.load(f)
        if "tons" not in dados:
            dados, registro = self._detectar_tons(id_musica, caminho_dados, registro)
        self._json({"musica": registro, "dados": dados})

    def _detectar_tons(self, id_musica, caminho_dados, registro):
        """Músicas processadas antes da detecção de modulação: calcula o tom de cada trecho pelos
        acordes (instantâneo) e grava; se a música modula, o tom dela passa a ser o do início."""
        with TRAVA_DADOS:
            with open(caminho_dados, encoding="utf-8") as f:
                dados = json.load(f)
            tons = tonalidade.detectar_modulacoes(dados.get("acordes") or [], dados.get("tom"), dados.get("duracao"))
            dados["tons"] = tons
            if len(tons) > 1:
                dados["tom"] = {"tonica": tons[0]["tonica"], "modo": tons[0]["modo"]}
            with open(caminho_dados, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
        if len(tons) > 1:
            banco.atualizar_tom(id_musica, dados["tom"])
            registro = banco.obter(id_musica)
        return dados, registro

    def _letra(self, id_musica):
        caminho = letra.localizar(PASTA_LETRAS, id_musica)
        if not caminho:
            return self._json({"arquivo": None, "frases": []})
        self._json({"arquivo": os.path.basename(caminho), "frases": letra.ler(caminho)})

    def log_message(self, formato, *args):
        if not self.path.startswith(("/faixas/", "/midias/", "/instrumentos/")):  # o áudio gera muitas requisições de Range
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), formato % args))


def main():
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    porta = int(argumentos[0]) if argumentos else PORTA_PADRAO
    abrir_navegador = "--sem-navegador" not in sys.argv
    banco.conectar().close()  # cria o banco se ainda não existe
    url = f"http://{HOST}:{porta}/"
    try:
        servidor = Servidor((HOST, porta), Manipulador)
    except OSError:
        print(f"A porta {porta} já está em uso: a interface provavelmente já está aberta em {url}")
        return 1
    print(f"Interface em {url}  (feche esta janela ou use Ctrl+C para encerrar)")
    if abrir_navegador:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
