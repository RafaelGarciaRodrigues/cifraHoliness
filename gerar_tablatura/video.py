"""Vídeo de karaokê: fundo preto, letra rolando para cima, frase atual em branco no centro (as
palavras já cantadas ficam amarelas), frases já cantadas (em cima) e as próximas (embaixo) em
cinza. Na base, o violão e o piano do player (como em "instrumentos" na interface): a cifra do
acorde no violão, a nota da melodia e o acorde (mão esquerda) marcados no teclado, com o nome do
acorde à esquerda e a nota à direita, nas cores da interface. O áudio é a mistura das faixas
separadas escolhidas. Resultado: videos/<Artista> - <Título>.mp4 ou, com --formato instagram,
videos/instagram/<Artista> - <Título>.mp4 (vertical 1080×1920, H.264 + AAC, 30 qps; sem marca
d'água, com o acorde no canto superior esquerdo e a nota no superior direito).

Uso (a interface chama pelo botão "Criar vídeo"):
    python video.py <id> --faixas vocals,guitar [--inicio 30.5] [--fim 95] [--notas solo]
                       [--sintetizado notas.wav | --audio mistura.wav] [--formato padrao|instagram]
--audio: o áudio pronto do vídeo, a mistura do player renderizada no navegador (faixas e gravações
com a mixagem, notas sintetizadas com timbre e efeitos, volumes e limitador), já no trecho; quando
vem, é o único áudio do vídeo. Sem ele, mistura as faixas aqui (--sintetizado: som das notas à parte).
Os dois arquivos são apagados no fim.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import banco
import letra
import tonalidade
from pastas import BASE_DIR, base_video

PASTA_FAIXAS = os.path.join(BASE_DIR, "faixas")
PASTA_LETRAS = os.path.join(BASE_DIR, "letras")
PASTA_VIDEOS = os.path.join(BASE_DIR, "videos")
PASTA_INSTAGRAM = os.path.join(PASTA_VIDEOS, "instagram")
PASTA_DADOS = os.path.join(BASE_DIR, "dados")

# Medidas em pixels de cada formato. usar_formato() as copia para as variáveis do módulo abaixo,
# que o resto do código lê na hora de desenhar.
FORMATOS = {
    "padrao": {
        "LARGURA": 1280, "ALTURA": 720,
        "ALTURA_LINHA": 92,                 # distância vertical entre frases
        "TAM_ATUAL": 58, "TAM_OUTRAS": 46,  # tamanho da fonte da frase atual e das demais
        "MARGEM_LATERAL": 60,
        "FADE_BORDAS": 110,                 # pixels de esmaecimento no alto e embaixo da letra
        "FAIXA_INSTRUMENTOS": 150,          # violão + teclado, na base
        "FAIXA_MARCA": 34,                  # embaixo dos instrumentos, com a marca d'água (0: sem marca)
        "MARGEM_PIANO": 10,                 # acima e abaixo das teclas, dentro da faixa dos instrumentos
        "TAM_TITULO": 76, "TAM_SUBTITULO": 38,
        "LATERAL_PIANO": 190,               # de cada lado dos instrumentos: acorde (esq.) e nota (dir.)
        "TAM_ROTULO_PIANO": 64,
        "ROTULOS_NO_TOPO": False,           # acorde e nota nos cantos de cima, em vez de ao lado do teclado
    },
    "instagram": {  # vertical 1080×1920 (9:16, Reels), sem marca d'água
        "LARGURA": 1080, "ALTURA": 1920,
        "ALTURA_LINHA": 124, "TAM_ATUAL": 72, "TAM_OUTRAS": 56, "MARGEM_LATERAL": 50, "FADE_BORDAS": 260,
        "FAIXA_INSTRUMENTOS": 210, "FAIXA_MARCA": 0, "MARGEM_PIANO": 24,
        "TAM_TITULO": 96, "TAM_SUBTITULO": 50,
        "LATERAL_PIANO": 30, "TAM_ROTULO_PIANO": 96, "ROTULOS_NO_TOPO": True,
    },
}
QPS = 30                               # quadros por segundo
CINZA = 110                            # 0 = preto, 255 = branco
COR_CANTADA = (255, 215, 0)            # amarelo das palavras já cantadas da frase atual
TRANSICAO = 0.4                        # segundos de rolagem antes da próxima frase começar


def usar_formato(nome):
    """Passa a desenhar no formato `nome` (FORMATOS)."""
    medidas = FORMATOS[nome]
    globals().update(medidas)
    globals()["FAIXA_PIANO"] = medidas["FAIXA_INSTRUMENTOS"] + medidas["FAIXA_MARCA"]  # faixa da base
    globals()["ALTURA_LETRA"] = medidas["ALTURA"] - FAIXA_PIANO  # a frase atual fica no meio dessa área


usar_formato("padrao")
FONTES = [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf",
          r"C:\Windows\Fonts\arialbd.ttf", "DejaVuSans-Bold.ttf"]
FONTE_SIMBOLOS = [r"C:\Windows\Fonts\seguisym.ttf", "DejaVuSans.ttf"]  # têm a nota musical ♪
INTERVALO_MINIMO = 3.0                 # silêncio da voz (s) a partir do qual aparecem as notas ♪ ♪ ♪
DURACAO_ABERTURA, FADE_ABERTURA = 4.0, 0.6   # título, artista e tom no começo do vídeo
TAM_TITULO, TAM_SUBTITULO = 76, 38
INTRO_MINIMA = 6.0                     # segundos antes da primeira frase; se faltar, entra silêncio no começo

# nomes do tom (mesma grafia do solo.py e da interface)
TOM_MAIOR = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
TOM_MENOR = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
NOMES_PT = {"C": "Dó", "D": "Ré", "E": "Mi", "F": "Fá", "G": "Sol", "A": "Lá", "B": "Si"}


def nome_tom(tonica, modo):
    letra_tom = (TOM_MAIOR if modo == "maior" else TOM_MENOR)[tonica % 12]
    acidente = " sustenido" if "#" in letra_tom else " bemol" if "b" in letra_tom else ""
    cifra = letra_tom + ("m" if modo == "menor" else "")
    return f"Tom: {cifra} ({NOMES_PT[letra_tom[0]]}{acidente} {modo})"


def carregar_fonte(tamanho):
    for caminho in FONTES:
        try:
            return ImageFont.truetype(caminho, tamanho)
        except OSError:
            continue
    return ImageFont.load_default(tamanho)


def renderizar_texto(texto, tamanho, brilho, altura=None, com_palavras=False):
    """Texto como máscara em tons de cinza (0 = fundo); diminui a fonte se não couber na largura.
    Com com_palavras=True devolve também, para cada palavra, o intervalo x que ela ocupa."""
    altura = altura or ALTURA_LINHA
    fonte = carregar_fonte(tamanho)
    while tamanho > 20 and fonte.getlength(texto) > LARGURA - 2 * MARGEM_LATERAL:
        tamanho -= 2
        fonte = carregar_fonte(tamanho)
    largura = int(fonte.getlength(texto)) + 8
    img = Image.new("L", (max(largura, 1), altura), 0)
    ImageDraw.Draw(img).text((largura / 2, altura / 2), texto, fill=brilho, font=fonte, anchor="mm")
    if not com_palavras:
        return np.asarray(img)
    x0 = (largura - fonte.getlength(texto)) / 2  # onde o texto começa (está centralizado)
    faixas = [(int(x0 + fonte.getlength(texto[:m.start()])), int(round(x0 + fonte.getlength(texto[:m.end()]))) + 1)
              for m in re.finditer(r"\S+", texto)]
    return np.asarray(img), faixas


# ---------------------------------------------------------------- tempo de cada palavra
# Mesma lógica do painel da letra (interface.html: palavrasDe / estimarPalavras)
def _normalizar(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[\W_]+", " ", s).strip()


def tempos_das_palavras(frase, transcricao):
    """Início de cada palavra da frase. Frase igual à transcrição: tempos exatos (deslocados se a
    frase foi movida). Frase corrigida: as palavras que continuam iguais herdam o tempo da
    transcrição e as trocadas são distribuídas entre as vizinhas."""
    palavras = frase["texto"].split()
    ini, fim = frase["inicio"], frase["fim"]
    alvo = _normalizar(frase["texto"])
    for p in transcricao:
        if abs(p["inicio"] - ini) < 1.5 and _normalizar(p["texto"]) == alvo and len(p.get("palavras") or []) == len(palavras):
            return [w["inicio"] + ini - p["inicio"] for w in p["palavras"]]

    originais = sorted((w for p in transcricao if not (p["fim"] < ini - 1.5 or p["inicio"] > fim + 1.5)
                        for w in p.get("palavras") or []
                        if w["inicio"] >= ini - 1.5 and w["fim"] <= fim + 1.5), key=lambda w: w["inicio"])
    casadas = [None] * len(palavras)
    blocos = difflib.SequenceMatcher(None, [_normalizar(w) for w in palavras],
                                     [_normalizar(w["texto"]) for w in originais], autojunk=False)
    for b in blocos.get_matching_blocks():
        for d in range(b.size):
            if _normalizar(palavras[b.a + d]):
                casadas[b.a + d] = originais[b.b + d]
    inicios = [c["inicio"] if c else None for c in casadas]
    i = 0
    while i < len(palavras):  # distribui as não casadas entre as âncoras vizinhas
        if inicios[i] is not None:
            i += 1
            continue
        k = i
        while k < len(palavras) and inicios[k] is None:
            k += 1
        de = casadas[i - 1]["fim"] if i > 0 and casadas[i - 1] else (inicios[i - 1] if i > 0 else ini)
        ate = inicios[k] if k < len(palavras) else fim
        pesos = [len(w) + 1 for w in palavras[i:k]]
        t = de
        for j, peso in zip(range(i, k), pesos):
            inicios[j] = t
            t += max(0.0, ate - de) * peso / sum(pesos)
        i = k
    return inicios


def renderizar_abertura(titulo, artista, tom):
    """Tela de abertura: título grande e, embaixo, artista e tom (menores), centralizados."""
    linhas = [renderizar_texto(titulo, TAM_TITULO, 255, int(TAM_TITULO * 1.6))]
    linhas += [renderizar_texto(t, TAM_SUBTITULO, 200, int(TAM_SUBTITULO * 1.7)) for t in (artista, tom) if t]
    tela = np.zeros((ALTURA, LARGURA), np.uint8)
    y = (ALTURA - sum(img.shape[0] for img in linhas)) // 2
    for img in linhas:
        h, w = img.shape
        x = (LARGURA - w) // 2
        tela[y:y + h, x:x + w] = img
        y += h
    return tela


def opacidade_abertura(tv):
    """0 → 1 no fade de entrada, 1 durante a abertura, 1 → 0 no fade de saída."""
    return max(0.0, min(1.0, tv / FADE_ABERTURA, (DURACAO_ABERTURA - tv) / FADE_ABERTURA))


def opacidade_letra(tv):
    """A letra entra (com fade) quando a abertura termina."""
    return max(0.0, min(1.0, (tv - DURACAO_ABERTURA) / FADE_ABERTURA))


def renderizar_notas(tamanho, brilho):
    """Três notas musicais na mesma linha: só música tocando, ninguém cantando."""
    img = Image.new("L", (int(tamanho * 5.2), ALTURA_LINHA), 0)
    desenho = ImageDraw.Draw(img)
    for caminho in FONTE_SIMBOLOS:
        try:
            fonte = ImageFont.truetype(caminho, int(tamanho * 1.1))
            desenho.text((img.width / 2, ALTURA_LINHA / 2), "♪   ♪   ♪",
                         fill=brilho, font=fonte, anchor="mm")
            return np.asarray(img)
        except OSError:
            continue
    # sem fonte com o símbolo: desenha as notas (cabeça + haste + bandeira)
    for k in range(3):
        cx, cy, r = img.width / 2 + (k - 1) * tamanho * 1.6, ALTURA_LINHA / 2 + tamanho * 0.3, tamanho * 0.22
        desenho.ellipse([cx - r * 1.3, cy - r, cx + r * 1.3, cy + r], fill=brilho)
        desenho.line([cx + r * 1.2, cy, cx + r * 1.2, cy - tamanho * 0.9], fill=brilho, width=max(2, tamanho // 12))
        desenho.line([cx + r * 1.2, cy - tamanho * 0.9, cx + r * 2.6, cy - tamanho * 0.5], fill=brilho,
                     width=max(2, tamanho // 12))
    return np.asarray(img)


def com_intervalos(frases, fim_video, inicio_video=0.0):
    """Insere linhas de notas (texto None) onde a voz fica calada por INTERVALO_MINIMO ou mais:
    antes da primeira frase, entre frases e depois da última."""
    itens, cursor = [], inicio_video
    for f in frases:
        if f["inicio"] - cursor >= INTERVALO_MINIMO:
            itens.append({"inicio": cursor + (0.3 if itens else 0.0), "fim": f["inicio"], "texto": None})
        itens.append(f)
        cursor = max(cursor, f["fim"])
    if fim_video - cursor >= INTERVALO_MINIMO:
        itens.append({"inicio": cursor + (0.3 if itens else 0.0), "fim": fim_video, "texto": None})
    return itens


def suavizar(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class Karaoke:
    def __init__(self, frases, fim_video, inicio_video=0.0, transcricao=()):
        self.frases = com_intervalos(frases, fim_video, inicio_video)
        self.inicios = [f["inicio"] for f in self.frases]
        notas_branco, notas_cinza = renderizar_notas(TAM_ATUAL, 255), renderizar_notas(TAM_OUTRAS, CINZA)
        self.branco, self.faixas_x, self.tempos = [], [], []
        for f in self.frases:
            if f["texto"]:
                img, faixas = renderizar_texto(f["texto"], TAM_ATUAL, 255, com_palavras=True)
                self.branco.append(img)
                self.faixas_x.append(faixas)
                self.tempos.append(tempos_das_palavras(f, transcricao))
            else:  # linha de notas ♪ ♪ ♪: sem palavras para marcar
                self.branco.append(notas_branco)
                self.faixas_x.append([])
                self.tempos.append([])
        self.cinza = [renderizar_texto(f["texto"], TAM_OUTRAS, CINZA) if f["texto"] else notas_cinza
                      for f in self.frases]
        # esmaecimento perto do alto e de baixo da área da letra (abaixo dela fica o piano)
        y = np.arange(ALTURA)
        self.fade = np.clip(np.minimum(y, ALTURA_LETRA - 1 - y) / FADE_BORDAS, 0, 1).astype(np.float32)[:, None]

    def rolagem(self, t):
        """Posição contínua da letra: i + fração, onde i é a última frase já iniciada."""
        i = int(np.searchsorted(self.inicios, t, side="right")) - 1
        proximo = self.inicios[i + 1] if i + 1 < len(self.inicios) else None
        fracao = suavizar((t - (proximo - TRANSICAO)) / TRANSICAO) if proximo is not None else 0.0
        return i, i + fracao

    def quadro(self, t):
        """Quadro RGB (ALTURA × LARGURA × 3) no instante t da música."""
        tela = np.zeros((ALTURA, LARGURA), np.uint8)
        atual, s = self.rolagem(t)
        cantada = None  # região da frase atual já cantada: (ya, yb, xa, xc)
        for k in range(max(0, int(s) - 5), min(len(self.frases), int(s) + 7)):
            centro_y = ALTURA_LETRA / 2 + (k - s) * ALTURA_LINHA
            em_evidencia = k == atual and t <= self.frases[k]["fim"] + 0.3
            img = self.branco[k] if em_evidencia else self.cinza[k]
            h, w = img.shape
            y0, x0 = int(round(centro_y - h / 2)), (LARGURA - w) // 2
            ya, yb = max(0, y0), min(ALTURA_LETRA, y0 + h)
            xa, xb = max(0, x0), min(LARGURA, x0 + w)
            if ya >= yb or xa >= xb:
                continue
            recorte = img[ya - y0:yb - y0, xa - x0:xb - x0]
            np.maximum(tela[ya:yb, xa:xb], recorte, out=tela[ya:yb, xa:xb])
            if em_evidencia:
                n = sum(1 for inicio in self.tempos[k] if inicio <= t)  # palavras já cantadas
                if n:
                    cantada = (ya, yb, xa, min(xb, x0 + self.faixas_x[k][n - 1][1]))
        tela = (tela * self.fade).astype(np.uint8)
        rgb = np.repeat(tela[:, :, None], 3, axis=2)
        if cantada and cantada[3] > cantada[2]:
            ya, yb, xa, xc = cantada
            brilho = tela[ya:yb, xa:xc].astype(np.uint16)
            for canal, valor in enumerate(COR_CANTADA):  # branco -> amarelo, mantendo o anti-serrilhado
                rgb[ya:yb, xa:xc, canal] = (brilho * valor // 255).astype(np.uint8)
        return rgb


# ---------------------------------------------------------------- violão + piano (os mesmos do player)
# Teclado de 5 oitavas (C2 a C7) com as medidas reais (mm); a oitava retirada (C1) dá lugar ao braço
# do violão com a cifra do acorde, da mesma altura das teclas. A nota da melodia nas cores de "Nota"
# (verde no campo harmônico do tom, cor do acorde se é nota do acorde fora do tom, vermelho fora) e o
# acorde em posição fechada na mão esquerda (fundamental entre C2 e B2) na cor de "Acorde".
# Cores do tema escuro da interface; mesma lógica de interface.html (classeCampo, notasMaoEsquerda).
PIANO_MIN, PIANO_MAX = 36, 96
BRANCA_L, BRANCA_A, PRETA_L, PRETA_A = 23.5, 150, 13.7, 95
PRETAS_X = {1: 14.0, 3: 41.9, 6: 82.6, 8: 108.0, 10: 133.4}
BRANCAS_I = {0: 0, 2: 1, 4: 2, 5: 3, 7: 4, 9: 5, 11: 6}
LARGURA_PIANO_MM = ((PIANO_MAX - PIANO_MIN) // 12 * 7 + 1) * BRANCA_L
LARGURA_VIOLAO_MM = 7 * BRANCA_L       # o violão ocupa o lugar de uma oitava do teclado
COR_OK, COR_ERRO, COR_ACORDE = (81, 207, 102), (255, 107, 107), (151, 117, 250)
COR_SEM_TOM, COR_SUAVE = (255, 122, 61), (154, 154, 162)
NOTAS_DO_ACORDE = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10]}
ESCALA_DO_TOM = {"maior": [0, 2, 4, 5, 7, 9, 11], "menor": [0, 2, 3, 5, 7, 8, 10]}
SUSTENIDOS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BEMOIS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def classe_campo(midi, acorde, tom):
    intervalos = NOTAS_DO_ACORDE.get(acorde["tipo"]) if acorde else None
    no_acorde = bool(intervalos) and (midi - acorde["raiz"]) % 12 in intervalos
    escala = ESCALA_DO_TOM.get(tom["modo"]) if tom else None
    no_tom = (midi - tom["tonica"]) % 12 in escala if escala else None
    return "noCampo" if no_tom else "noAcorde" if no_acorde else "foraCampo" if no_tom is False else ""


COR_DA_CLASSE = {"noCampo": COR_OK, "noAcorde": COR_ACORDE, "foraCampo": COR_ERRO, "": COR_SEM_TOM}

# Formas do violão: as mesmas de FORMAS_VIOLAO em interface.html (da 6ª corda para a 1ª; -1 não
# tocar, 0 solta, n casa), por tipo e pela nota da fundamental (0 = C)
FORMAS_VIOLAO = {
    "": [[-1, 3, 2, 0, 1, 0], [-1, 4, 6, 6, 6, 4], [-1, -1, 0, 2, 3, 2], [-1, 6, 8, 8, 8, 6], [0, 2, 2, 1, 0, 0],
         [1, 3, 3, 2, 1, 1], [2, 4, 4, 3, 2, 2], [3, 2, 0, 0, 0, 3], [4, 6, 6, 5, 4, 4], [-1, 0, 2, 2, 2, 0],
         [-1, 1, 3, 3, 3, 1], [-1, 2, 4, 4, 4, 2]],
    "m": [[-1, 3, 5, 5, 4, 3], [-1, 4, 6, 6, 5, 4], [-1, -1, 0, 2, 3, 1], [-1, 6, 8, 8, 7, 6], [0, 2, 2, 0, 0, 0],
          [1, 3, 3, 1, 1, 1], [2, 4, 4, 2, 2, 2], [3, 5, 5, 3, 3, 3], [4, 6, 6, 4, 4, 4], [-1, 0, 2, 2, 1, 0],
          [-1, 1, 3, 3, 2, 1], [-1, 2, 4, 4, 3, 2]],
    "7": [[-1, 3, 2, 3, 1, 0], [-1, 4, 6, 4, 6, 4], [-1, -1, 0, 2, 1, 2], [-1, 6, 8, 6, 8, 6], [0, 2, 0, 1, 0, 0],
          [1, 3, 1, 2, 1, 1], [2, 4, 2, 3, 2, 2], [3, 2, 0, 0, 0, 1], [4, 6, 4, 5, 4, 4], [-1, 0, 2, 0, 2, 0],
          [-1, 1, 3, 1, 3, 1], [-1, 2, 1, 2, 0, 2]],
}
CASAS_VIOLAO = 5
COR_BRACO, COR_CASAS = (225, 225, 230), (120, 120, 128)


def desenhar_violao(d, x_meio, y_topo, altura, acorde, fonte_casa):
    """Diagrama vertical de 5 casas (no estilo do SVGuitar da interface) com o topo da linha dos X/○
    em y_topo e a última casa em y_topo + altura (alinhado com as teclas)."""
    forma = FORMAS_VIOLAO.get(acorde["tipo"], [None] * 12)[acorde["raiz"] % 12] if acorde else None
    # proporções do player: casa = 1,4 × distância entre cordas; X/○ ocupam ~1 distância acima
    esp = altura / (CASAS_VIOLAO * 1.4 + 1.25)
    casa = 1.4 * esp
    topo_grade = y_topo + altura - CASAS_VIOLAO * casa
    x0 = x_meio - 3.1 * esp  # um pouco à esquerda do meio: à direita fica o espaço do "4fr"
    linha = max(1, round(esp * 0.09))
    cor_linha = COR_BRACO if forma else COR_CASAS
    casas = [c for c in forma if c > 0] if forma else []
    maior, menor = (max(casas), min(casas)) if casas else (0, 0)
    posicao = menor if maior > CASAS_VIOLAO else 1
    for i in range(6):  # cordas
        x = x0 + i * esp
        d.line([x, topo_grade, x, topo_grade + CASAS_VIOLAO * casa], fill=cor_linha, width=linha)
    for f in range(CASAS_VIOLAO + 1):  # trastes (o primeiro é a pestana do braço quando começa na 1ª casa)
        y = topo_grade + f * casa
        largura = max(linha * 3, round(esp * 0.28)) if f == 0 and posicao == 1 else linha
        d.line([x0, y, x0 + 5 * esp, y], fill=cor_linha, width=largura)
    if not forma:
        return
    if posicao > 1:
        d.text((x0 + 5 * esp + esp * 0.45, topo_grade + casa / 2), f"{posicao}fr", fill=COR_BRACO,
               font=fonte_casa, anchor="lm")
    rel = lambda c: c - posicao + 1  # noqa: E731
    centro = lambda c: topo_grade + (rel(c) - 0.5) * casa  # noqa: E731
    raio = 0.75 * esp / 2
    grave = next(i for i, c in enumerate(forma) if c >= 0)
    pestana = 0 not in forma and menor > 0 and forma[grave] == menor and forma[5] == menor
    if pestana:
        y = centro(menor)
        d.rounded_rectangle([x0 + grave * esp - raio, y - raio, x0 + 5 * esp + raio, y + raio],
                            radius=raio, fill=COR_ACORDE)
    y_ind = y_topo + 0.4 * esp
    for i, c in enumerate(forma):
        x = x0 + i * esp
        if c < 0:  # não tocar: X
            r = 0.26 * esp
            d.line([x - r, y_ind - r, x + r, y_ind + r], fill=COR_BRACO, width=linha + 1)
            d.line([x - r, y_ind + r, x + r, y_ind - r], fill=COR_BRACO, width=linha + 1)
        elif c == 0:  # solta: ○
            r = 0.3 * esp
            d.ellipse([x - r, y_ind - r, x + r, y_ind + r], outline=COR_BRACO, width=linha + 1)
        elif not (pestana and c == menor):
            y = centro(c)
            d.ellipse([x - raio, y - raio, x + raio, y + raio], fill=COR_ACORDE)


class Piano:
    """Faixa da base do vídeo (FAIXA_PIANO × LARGURA, RGB) no instante t; refeita só quando muda."""

    def __init__(self, notas, acordes, tom, tons=None, vocais=None):
        # extensão vocal: teclas fora da nota mais grave/mais aguda da faixa de voz ficam com leve sombra
        alturas = [n["midi"] for n in vocais or []]
        self.faixa_voz = (min(alturas), max(alturas)) if alturas else None
        self.notas = sorted(notas, key=lambda n: n["t"])
        self.acordes = sorted(acordes, key=lambda a: a["t"])
        self.inicios_notas = [n["t"] for n in self.notas]
        self.inicios_acordes = [a["t"] for a in self.acordes]
        self.tom = self.tom_geral = tom
        self.tons = tons or []  # tom de cada trecho (a música pode modular)
        bemois = [5, 10, 3, 8, 1] if tom and tom["modo"] == "maior" else [2, 7, 0, 5, 10, 3]
        self.nomes = BEMOIS if tom and tom["tonica"] % 12 in bemois else SUSTENIDOS
        largura = LARGURA - 2 * LATERAL_PIANO
        total_mm = LARGURA_VIOLAO_MM + LARGURA_PIANO_MM  # violão + teclado
        self.k = min(largura / total_mm, (FAIXA_INSTRUMENTOS - 2 * MARGEM_PIANO) / BRANCA_A)  # px por mm
        self.xv = (LARGURA - total_mm * self.k) / 2      # início do violão (antes do teclado)
        self.x0 = self.xv + LARGURA_VIOLAO_MM * self.k    # início do teclado
        self.y0 = FAIXA_INSTRUMENTOS - MARGEM_PIANO - BRANCA_A * self.k
        self.fonte = carregar_fonte(TAM_ROTULO_PIANO)
        self.fonte_casa = carregar_fonte(max(10, int(BRANCA_A * self.k * 0.11)))
        self.fonte_c = carregar_fonte(max(9, int(BRANCA_L * self.k * 0.5)))
        self.chave, self.imagem, self.topo = None, None, None

    @staticmethod
    def _ativo(lista, inicios, t):
        i = int(np.searchsorted(inicios, t, side="right")) - 1
        return lista[i] if i >= 0 and t < lista[i]["t"] + lista[i]["d"] else None

    def _tecla(self, m):
        oitava = (m - PIANO_MIN) // 12 * 7 * BRANCA_L
        preta = m % 12 in PRETAS_X
        x = self.x0 + (oitava + (PRETAS_X[m % 12] if preta else BRANCAS_I[m % 12] * BRANCA_L)) * self.k
        return preta, x, (PRETA_L if preta else BRANCA_L) * self.k, (PRETA_A if preta else BRANCA_A) * self.k

    def faixa(self, t):
        nota = self._ativo(self.notas, self.inicios_notas, t)
        acorde = self._ativo(self.acordes, self.inicios_acordes, t)
        self.tom = tonalidade.tom_em(self.tons, self.tom_geral, t)
        chave = (nota["midi"] if nota else None, (acorde["raiz"], acorde["tipo"]) if acorde else None,
                 (self.tom["tonica"], self.tom["modo"]) if self.tom else None)
        if chave != self.chave:
            self.chave, self.imagem = chave, self._desenhar(nota, acorde)
            if ROTULOS_NO_TOPO:
                self.topo = self._rotulos_topo(nota, acorde)
        return self.imagem

    def _textos(self, nota, acorde):
        """(texto e cor do acorde, texto e cor da nota)"""
        classe = classe_campo(nota["midi"], acorde, self.tom) if nota else ""
        texto_acorde = self.nomes[acorde["raiz"] % 12] + acorde["tipo"] if acorde else "—"
        texto_nota = f"{self.nomes[nota['midi'] % 12]}{nota['midi'] // 12 - 1}" if nota else "—"
        return ((texto_acorde, COR_ACORDE if acorde else COR_SUAVE),
                (texto_nota, COR_DA_CLASSE[classe] if nota else COR_SUAVE))

    def _rotulos_topo(self, nota, acorde):
        """Faixa do alto do vídeo (RGB, fundo preto): acorde no canto esquerdo e nota no direito."""
        altura = int(TAM_ROTULO_PIANO * 1.6)
        img = Image.new("RGB", (LARGURA, altura), (0, 0, 0))
        d = ImageDraw.Draw(img)
        (ta, ca), (tn, cn) = self._textos(nota, acorde)
        margem = MARGEM_LATERAL
        d.text((margem, altura / 2 + MARGEM_PIANO), ta, fill=ca, font=self.fonte, anchor="lm")
        d.text((LARGURA - margem, altura / 2 + MARGEM_PIANO), tn, fill=cn, font=self.fonte, anchor="rm")
        return np.asarray(img)

    def _desenhar(self, nota, acorde):
        img = Image.new("RGB", (LARGURA, FAIXA_PIANO), (0, 0, 0))
        d = ImageDraw.Draw(img)
        marcadas = {}  # midi -> (cor, melodia?)
        if acorde and acorde["tipo"] in NOTAS_DO_ACORDE:
            raiz = 36 + acorde["raiz"] % 12
            for i in NOTAS_DO_ACORDE[acorde["tipo"]]:
                marcadas[raiz + i] = (COR_ACORDE, False)
        classe = classe_campo(nota["midi"], acorde, self.tom) if nota else ""
        if nota:
            marcadas[nota["midi"]] = (COR_DA_CLASSE[classe], True)
        y0 = self.y0
        for preta in (False, True):  # brancas primeiro, pretas por cima
            for m in range(PIANO_MIN, PIANO_MAX + 1):
                e_preta, x, w, h = self._tecla(m)
                if e_preta != preta:
                    continue
                cor, melodia = marcadas.get(m, (None, False))
                fundo = cor or ((31, 31, 34) if preta else (251, 250, 246))
                if not cor and self.faixa_voz and not self.faixa_voz[0] <= m <= self.faixa_voz[1]:  # marcada: sem sombra
                    sombra = 0.45 if preta else 0.2  # como o rgba(0,0,0,a) da interface
                    fundo = tuple(round(c * (1 - sombra)) for c in fundo)
                d.rectangle([x, y0, x + w - 1, y0 + h - 1], fill=fundo,
                            outline=None if preta else (138, 138, 138))
                if melodia:  # bolinha branca, como no player
                    r = max(2, min(w * 0.22, 5))
                    cy = y0 + h - min(w * 0.5, 10)
                    d.ellipse([x + w / 2 - r, cy - r, x + w / 2 + r, cy + r], fill=(255, 255, 255))
                if not preta and m % 12 == 0 and not cor and w >= 12:
                    d.text((x + w / 2, y0 + h - 3), f"C{m // 12 - 1}", fill=(138, 138, 138),
                           font=self.fonte_c, anchor="ms")
        d.rectangle([self.x0, y0, self.x0 + LARGURA_PIANO_MM * self.k, y0 + max(2, 3 * self.k)], fill=(122, 31, 31))
        # violão no lugar da oitava retirada, com a altura das teclas
        desenhar_violao(d, self.xv + LARGURA_VIOLAO_MM * self.k / 2, y0, BRANCA_A * self.k, acorde, self.fonte_casa)
        if not ROTULOS_NO_TOPO:  # acorde à esquerda e nota à direita, centralizados nas laterais
            cy = y0 + BRANCA_A * self.k / 2
            (ta, ca), (tn, cn) = self._textos(nota, acorde)
            d.text((self.xv / 2, cy), ta, fill=ca, font=self.fonte, anchor="mm")
            d.text((LARGURA - self.xv / 2, cy), tn, fill=cn, font=self.fonte, anchor="mm")
        return np.asarray(img)


# ---------------------------------------------------------------- marca d'água
MARCA_TEXTO = "@Louvores.Karaoke"
MARCA_OPACIDADE = 0.6
MARCA_ESCALA = 0.75                    # tamanho em relação ao desenho original


class MarcaDagua:
    """Logo do YouTube (o bi-youtube da interface, desenhado) + @canal, pequena, no canto esquerdo
    abaixo do violão e do teclado (faixa FAIXA_MARCA). Pré-renderizada em RGBA; a cada quadro só
    mistura essa região."""

    def __init__(self):
        e = MARCA_ESCALA
        fonte = carregar_fonte(round(22 * e))
        logo_l, logo_a, espaco = round(34 * e), round(24 * e), round(9 * e)
        largura = logo_l + espaco + int(fonte.getlength(MARCA_TEXTO)) + 4
        altura = round(30 * e)
        img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y0 = (altura - logo_a) // 2
        d.rounded_rectangle([0, y0, logo_l - 1, y0 + logo_a - 1], radius=round(7 * e), fill=(255, 0, 0, 255))
        cx, cy = logo_l / 2 + e, y0 + logo_a / 2
        d.polygon([(cx - 5 * e, cy - 6.5 * e), (cx - 5 * e, cy + 6.5 * e), (cx + 7 * e, cy)], fill=(255, 255, 255, 255))
        d.text((logo_l + espaco, altura / 2), MARCA_TEXTO, fill=(255, 255, 255, 255), font=fonte, anchor="lm")
        rgba = np.asarray(img).astype(np.float32)
        self.rgb = rgba[:, :, :3]
        self.alfa = rgba[:, :, 3:] / 255 * MARCA_OPACIDADE
        self.x, self.y = 24, ALTURA - FAIXA_MARCA + (FAIXA_MARCA - altura) // 2

    def aplicar(self, quadro):
        h, w = self.alfa.shape[:2]
        regiao = quadro[self.y:self.y + h, self.x:self.x + w].astype(np.float32)
        quadro[self.y:self.y + h, self.x:self.x + w] = (regiao * (1 - self.alfa) + self.rgb * self.alfa).astype(np.uint8)


def nome_arquivo(registro, pasta=None):
    pasta = pasta or PASTA_VIDEOS
    base = base_video(registro)
    return os.path.join(pasta, base + ".mp4")  # criar de novo substitui o anterior (no fim, com os.replace)


def main(argumentos):
    p = argparse.ArgumentParser(description="Cria o vídeo de karaokê de uma música processada.")
    p.add_argument("id")
    p.add_argument("--faixas", required=True, help="faixas separadas a misturar, separadas por vírgula")
    p.add_argument("--inicio", type=float, default=0.0)
    p.add_argument("--fim", type=float, default=None)
    p.add_argument("--notas", default="solo", help="fontes das notas do piano, separadas por vírgula (as marcadas no player)")
    p.add_argument("--sintetizado", default=None, help="WAV com o som das notas (começa no início do trecho)")
    p.add_argument("--audio", default=None, help="WAV com o áudio pronto do vídeo (a mistura do player, já no trecho)")
    p.add_argument("--formato", choices=list(FORMATOS), default="padrao",
                   help="padrao: 1280×720 em videos/; instagram: vertical 1080×1920 em videos/instagram/")
    a = p.parse_args(argumentos)

    if not re.fullmatch(r"[0-9a-f]{8}", a.id) or (registro := banco.obter(a.id)) is None:
        print("Erro: música não encontrada.")
        return 1
    if shutil.which("ffmpeg") is None:
        print("Erro: FFmpeg não encontrado no PATH do sistema.")
        return 1
    nomes = [n for n in a.faixas.split(",") if re.fullmatch(r"[a-z]+", n)]
    caminhos = [os.path.join(PASTA_FAIXAS, a.id, n + ".wav") for n in nomes]
    if not caminhos or not all(os.path.exists(c) for c in caminhos):
        print("Erro: faixas não encontradas: " + a.faixas)
        return 1

    print("[1/3] Preparando letra e faixas...", flush=True)
    import soundfile as sf
    duracao_audio = min(sf.info(c).duration for c in caminhos)
    inicio = max(0.0, a.inicio)
    fim = min(a.fim if a.fim is not None else duracao_audio, duracao_audio)
    if fim - inicio < 1:
        print("Erro: o trecho escolhido tem menos de 1 segundo.")
        return 1
    caminho_letra = letra.localizar(PASTA_LETRAS, a.id)
    frases = [f for f in (letra.ler(caminho_letra) if caminho_letra else []) if f["texto"].strip()]

    # Introdução mínima: se a letra começa antes de INTRO_MINIMA s do início do trecho, o vídeo
    # ganha silêncio no começo (áudio e letra deslocados juntos)
    no_trecho = [f for f in frases if inicio < f["fim"] and f["inicio"] < fim]
    silencio = max(0.0, INTRO_MINIMA - max(0.0, no_trecho[0]["inicio"] - inicio)) if no_trecho else 0.0
    dados = {}  # notas, acordes, tom e tempos palavra a palavra da transcrição (os mesmos do player)
    caminho_dados = os.path.join(PASTA_DADOS, f"{a.id}.json")
    if os.path.exists(caminho_dados):
        with open(caminho_dados, encoding="utf-8") as f_dados:
            dados = json.load(f_dados)
    titulo = registro["titulo"] or os.path.splitext(registro["arquivo"])[0]
    tom = nome_tom(registro["tom_tonica"], registro["tom_modo"]) if registro["tom_tonica"] is not None else None
    trabalho = {"frases": frases, "dados": dados, "duracao_audio": duracao_audio, "inicio": inicio, "fim": fim,
                "silencio": silencio, "caminhos": caminhos, "sintetizado": a.sintetizado, "notas": a.notas, "audio": a.audio,
                "titulo": titulo, "artista": registro["artista"], "tom": tom}

    instagram = a.formato == "instagram"
    pasta = PASTA_INSTAGRAM if instagram else PASTA_VIDEOS
    os.makedirs(pasta, exist_ok=True)
    saida = nome_arquivo(registro, pasta)
    if not renderizar(a.formato, saida, trabalho, "[2/3] Renderizando o vídeo", "[3/3] Finalizando o arquivo..."):
        return 1
    rotulo = "Vídeo do Instagram finalizado!" if instagram else "Vídeo finalizado!"
    print(f"{rotulo} {os.path.relpath(saida, BASE_DIR)}", flush=True)
    return 0


def renderizar(formato, saida, w, rotulo_progresso, rotulo_final):
    """Gera um MP4 (H.264 + AAC, QPS quadros por segundo) no formato dado; True se deu certo."""
    usar_formato(formato)
    inicio, fim, silencio, caminhos = w["inicio"], w["fim"], w["silencio"], w["caminhos"]
    dados = w["dados"]
    karaoke = Karaoke(w["frases"], w["duracao_audio"], inicio_video=inicio - silencio,
                      transcricao=dados.get("letraPalavras", []))
    melodias = dados.get("melodias") or {}
    marca = MarcaDagua() if FAIXA_MARCA else None
    gravacoes_midi = dados.get("midi") or {}  # "midi:<gravação>": notas tocadas no teclado MIDI
    notas = [n for fonte in w["notas"].split(",")
             for n in ((gravacoes_midi.get(fonte[5:]) or {}).get("notas") if fonte.startswith("midi:")
                       else melodias.get(fonte)) or []]  # várias fontes: juntas
    piano = Piano(notas or melodias.get("solo") or [], dados.get("acordes") or [], dados.get("tom"),
                  dados.get("tons"), melodias.get("vocals"))
    abertura = renderizar_abertura(w["titulo"], w["artista"], w["tom"])  # tom original: as faixas não são transpostas
    temporario = saida + ".parcial.mp4"

    # Quadros RGB chegam pelo stdin; o áudio é mixado pelo próprio FFmpeg
    comando = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{LARGURA}x{ALTURA}", "-r", str(QPS), "-i", "-"]
    if w["audio"] and os.path.isfile(w["audio"]):  # a mistura pronta do player: o único áudio
        comando += ["-t", f"{fim - inicio:.3f}", "-i", w["audio"]]
        n_audios = 1
    else:
        for c in caminhos:
            comando += ["-ss", f"{inicio:.3f}", "-t", f"{fim - inicio:.3f}", "-i", c]
        n_audios = len(caminhos)
    if not w["audio"] and w["sintetizado"] and os.path.isfile(w["sintetizado"]):  # já começa no início do trecho
        comando += ["-t", f"{fim - inicio:.3f}", "-i", w["sintetizado"]]
        n_audios += 1
    entradas = "".join(f"[{k + 1}:a]" for k in range(n_audios))
    mistura = f"{entradas}amix=inputs={n_audios}:normalize=0:duration=first," if n_audios > 1 else f"{entradas}"
    atraso = f",adelay=delays={int(round(silencio * 1000))}:all=1" if silencio > 0 else ""
    comando += ["-filter_complex", f"{mistura}alimiter=limit=0.95{atraso}[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", temporario]

    total = int(round((fim - inicio + silencio) * QPS))
    ffmpeg = subprocess.Popen(comando, stdin=subprocess.PIPE)
    ultimo = -1
    try:
        for q in range(total):
            tv = q / QPS  # tempo no vídeo; o da música é deslocado pelo silêncio inicial
            quadro = karaoke.quadro(inicio - silencio + tv)
            quadro[ALTURA_LETRA:] = piano.faixa(inicio - silencio + tv)
            if piano.topo is not None:  # acorde e nota nos cantos de cima
                h = piano.topo.shape[0]
                np.maximum(quadro[:h], piano.topo, out=quadro[:h])
            if marca:
                marca.aplicar(quadro)
            if (op := opacidade_letra(tv)) < 1:
                quadro = (quadro * op).astype(np.uint8)
            if (op := opacidade_abertura(tv)) > 0:
                np.maximum(quadro, (abertura * op).astype(np.uint8)[:, :, None], out=quadro)
            ffmpeg.stdin.write(quadro.tobytes())
            pct = q * 100 // total
            if pct != ultimo and pct % 2 == 0:
                print(f"{rotulo_progresso}: {pct}%", flush=True)
                ultimo = pct
        ffmpeg.stdin.close()
    except OSError:  # BrokenPipeError / "Invalid argument" no Windows: o FFmpeg fechou antes; o erro aparece abaixo
        pass
    print(rotulo_final, flush=True)
    if ffmpeg.wait() != 0:
        if os.path.exists(temporario):
            os.remove(temporario)
        print(f"Erro: o FFmpeg falhou ao gerar o vídeo ({formato}).")
        return False
    os.replace(temporario, saida)
    return True


def _main_limpando(argumentos):
    """main() e, no fim (deu certo ou não), apaga os WAV temporários (som das notas / mistura)."""
    try:
        return main(argumentos)
    finally:
        for opcao in ("--sintetizado", "--audio"):
            if opcao not in argumentos:
                continue
            caminho = argumentos[argumentos.index(opcao) + 1:][:1]
            if caminho and os.path.basename(os.path.dirname(caminho[0])) == "telacifras_notas_video":
                try:
                    os.remove(caminho[0])
                except OSError:
                    pass


if __name__ == "__main__":
    sys.exit(_main_limpando(sys.argv[1:]))
