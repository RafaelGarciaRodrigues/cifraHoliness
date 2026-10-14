"""Cadastro das músicas processadas (SQLite, arquivo musicas.db).

Campos técnicos são preenchidos pelo solo.py a cada processamento; os campos em EDITAVEIS
pertencem ao usuário e nunca são sobrescritos pelo reprocessamento.
"""
import json
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAMINHO_BANCO = os.path.join(BASE_DIR, "musicas.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS musicas (
    id            TEXT PRIMARY KEY,          -- 8 hex do SHA-256 do arquivo de áudio
    arquivo       TEXT NOT NULL,             -- nome do arquivo em audio/
    titulo        TEXT,
    artista       TEXT,
    categoria     TEXT,
    tags          TEXT,
    favorito      INTEGER NOT NULL DEFAULT 0,
    status        TEXT,
    observacoes   TEXT,
    transposicao  INTEGER NOT NULL DEFAULT 0, -- semitons; define "meu tom"
    preferencias  TEXT,                       -- JSON com o último estado do player
    tom_tonica    INTEGER,
    tom_modo      TEXT,
    duracao       REAL,
    qtd_notas     INTEGER,
    qtd_acordes   INTEGER,
    qtd_frases    INTEGER,
    processado_em TEXT
)
"""

# campo -> conversor/validador do valor vindo da interface
EDITAVEIS = {
    "titulo": lambda v: _texto(v),
    "artista": lambda v: _texto(v),
    "categoria": lambda v: _texto(v),
    "tags": lambda v: _texto(v),
    "status": lambda v: _texto(v),
    "observacoes": lambda v: _texto(v),
    "favorito": lambda v: 1 if v else 0,
    "transposicao": lambda v: max(-12, min(12, int(v))),
    "preferencias": lambda v: json.dumps(v, ensure_ascii=False) if v is not None else None,
}


def _texto(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def conectar():
    con = sqlite3.connect(CAMINHO_BANCO)
    con.row_factory = sqlite3.Row
    con.execute(ESQUEMA)
    return con


def _linha(row):
    if row is None:
        return None
    d = dict(row)
    d["favorito"] = bool(d["favorito"])
    d["preferencias"] = json.loads(d["preferencias"]) if d["preferencias"] else {}
    return d


def registrar_processamento(id_musica, arquivo, titulo_padrao, tom, duracao, qtd_notas, qtd_acordes, qtd_frases):
    """Cria o registro (título = nome do arquivo) ou atualiza só os campos técnicos."""
    agora = datetime.now().isoformat(timespec="seconds")
    with conectar() as con:
        con.execute(
            """INSERT INTO musicas (id, arquivo, titulo, tom_tonica, tom_modo, duracao,
                                    qtd_notas, qtd_acordes, qtd_frases, processado_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   arquivo = excluded.arquivo, tom_tonica = excluded.tom_tonica,
                   tom_modo = excluded.tom_modo, duracao = excluded.duracao,
                   qtd_notas = excluded.qtd_notas, qtd_acordes = excluded.qtd_acordes,
                   qtd_frases = excluded.qtd_frases, processado_em = excluded.processado_em""",
            (id_musica, arquivo, titulo_padrao, tom["tonica"], tom["modo"], round(duracao, 2),
             qtd_notas, qtd_acordes, qtd_frases, agora),
        )


def listar():
    with conectar() as con:
        return [_linha(r) for r in con.execute("SELECT * FROM musicas ORDER BY titulo COLLATE NOCASE")]


def obter(id_musica):
    with conectar() as con:
        return _linha(con.execute("SELECT * FROM musicas WHERE id = ?", (id_musica,)).fetchone())


def arquivos_processados():
    with conectar() as con:
        return {r["arquivo"] for r in con.execute("SELECT arquivo FROM musicas")}


def atualizar(id_musica, campos):
    """Atualiza apenas campos editáveis; devolve o registro atualizado (ou None se não existe)."""
    valores = {c: EDITAVEIS[c](v) for c, v in campos.items() if c in EDITAVEIS}
    with conectar() as con:
        if valores:
            atribuicoes = ", ".join(f"{c} = ?" for c in valores)
            con.execute(f"UPDATE musicas SET {atribuicoes} WHERE id = ?", (*valores.values(), id_musica))
        return _linha(con.execute("SELECT * FROM musicas WHERE id = ?", (id_musica,)).fetchone())


def excluir(id_musica):
    """Tira a música do cadastro; devolve o registro apagado (ou None se não existia)."""
    with conectar() as con:
        row = con.execute("SELECT * FROM musicas WHERE id = ?", (id_musica,)).fetchone()
        if row is not None:
            con.execute("DELETE FROM musicas WHERE id = ?", (id_musica,))
        return _linha(row)


def atualizar_tom(id_musica, tom):
    """Tom do cadastro (o tom em que a música começa, quando ela modula)."""
    with conectar() as con:
        con.execute("UPDATE musicas SET tom_tonica = ?, tom_modo = ? WHERE id = ?", (tom["tonica"], tom["modo"], id_musica))


def atualizar_qtd_frases(id_musica, qtd):
    with conectar() as con:
        con.execute("UPDATE musicas SET qtd_frases = ? WHERE id = ?", (qtd, id_musica))
