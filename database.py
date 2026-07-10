"""
database.py

Responsável por toda a interação com o banco de dados SQLite:
criação de tabelas, inserção, remoção e consultas de apoio.

A busca textual em si (FTS5 MATCH) fica em search.py; aqui ficam apenas
as operações estruturais do banco (schema e CRUD básico).
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Iterator, Optional

from config import DATABASE_PATH, garantir_diretorio_dados


def conectar(db_path: str = DATABASE_PATH) -> sqlite3.Connection:
    """
    Abre uma conexão com o banco SQLite, garantindo que o diretório exista
    e que chaves estrangeiras (ON DELETE CASCADE) sejam respeitadas.
    Também ativa configurações de alta performance (WAL, cache e sincronização).
    """
    if db_path == DATABASE_PATH:
        garantir_diretorio_dados()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -20000;")  # Cache de ~20MB
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection(db_path: str = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    """Context manager para uso com 'with database.get_connection() as conn:'."""
    conn = conectar(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def criar_banco(conn: sqlite3.Connection) -> None:
    """Cria as tabelas, índices e triggers de sincronização FTS5, se não existirem."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            file_size INTEGER NOT NULL,
            modified_at REAL NOT NULL,
            sha256 TEXT,
            source_root TEXT,
            total_pages INTEGER,
            indexed_at REAL NOT NULL
        );
        """
    )

    # Migração: adiciona a coluna sha256 caso a tabela já exista sem ela
    cursor = conn.execute("PRAGMA table_info(documents);")
    colunas = [row["name"] for row in cursor.fetchall()]
    if "sha256" not in colunas:
        conn.execute("ALTER TABLE documents ADD COLUMN sha256 TEXT;")
    if "source_root" not in colunas:
        conn.execute("ALTER TABLE documents ADD COLUMN source_root TEXT;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_normalized TEXT,
            text_stemmed TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        """
    )

    # Migração: adiciona as colunas caso a tabela já exista sem elas
    cursor = conn.execute("PRAGMA table_info(pages);")
    colunas_pages = [row["name"] for row in cursor.fetchall()]
    if "text_normalized" not in colunas_pages:
        conn.execute("ALTER TABLE pages ADD COLUMN text_normalized TEXT;")
    if "text_stemmed" not in colunas_pages:
        conn.execute("ALTER TABLE pages ADD COLUMN text_stemmed TEXT;")

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            text,
            content='pages',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
        """
    )

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_stemmed_fts USING fts5(
            text_stemmed,
            content='pages',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
        """
    )

    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )
    versao_row = conn.execute(
        "SELECT value FROM app_metadata WHERE key = 'normalization_version';"
    ).fetchone()
    refazer_normalizacao = versao_row is None or int(versao_row["value"]) < 2

    # Backfill automático de bancos criados antes da normalização/stemming.
    filtro = "" if refazer_normalizacao else "WHERE text_normalized IS NULL OR text_stemmed IS NULL"
    pendentes = conn.execute(
        f"SELECT id, text, text_normalized, text_stemmed FROM pages {filtro};"
    ).fetchall()
    if pendentes:
        from search import normalizar_consulta, stemizar_texto

        atualizacoes = []
        for row in pendentes:
            texto_norm = normalizar_consulta(row["text"]) if refazer_normalizacao else (
                row["text_normalized"] or normalizar_consulta(row["text"])
            )
            texto_stem = stemizar_texto(texto_norm) if refazer_normalizacao else (
                row["text_stemmed"] or stemizar_texto(texto_norm)
            )
            atualizacoes.append((texto_norm, texto_stem, row["id"]))
        conn.executemany(
            "UPDATE pages SET text_normalized = ?, text_stemmed = ? WHERE id = ?;",
            atualizacoes,
        )
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild');")
        conn.execute("INSERT INTO pages_stemmed_fts(pages_stemmed_fts) VALUES('rebuild');")
    conn.execute(
        "INSERT INTO app_metadata(key, value) VALUES('normalization_version', '2') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value;"
    )

    # Triggers para sincronização automática com o índice FTS5 (external content)
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS t_pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, text) VALUES(new.id, new.text);
            INSERT INTO pages_stemmed_fts(rowid, text_stemmed) VALUES(new.id, new.text_stemmed);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS t_pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, text) VALUES('delete', old.id, old.text);
            INSERT INTO pages_stemmed_fts(pages_stemmed_fts, rowid, text_stemmed) VALUES('delete', old.id, old.text_stemmed);
        END;
        """
    )

    # Índice de apoio para acelerar as verificações de páginas por documento
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages(document_id);"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vocabulary (
            word TEXT PRIMARY KEY
        );
        """
    )

    conn.commit()


# ---------------------------------------------------------------------------
# Operações sobre 'documents'
# ---------------------------------------------------------------------------

def inserir_documento(
    conn: sqlite3.Connection,
    filename: str,
    path: str,
    file_size: int,
    modified_at: float,
    total_pages: int,
    indexed_at: float,
    sha256: str = "",
    source_root: Optional[str] = None,
) -> int:
    """Insere um novo documento e retorna o id gerado."""
    cursor = conn.execute(
        """
        INSERT INTO documents (filename, path, file_size, modified_at, sha256, total_pages, indexed_at, source_root)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (filename, path, file_size, modified_at, sha256, total_pages, indexed_at, source_root),
    )
    return cursor.lastrowid


def atualizar_metadados_documento(
    conn: sqlite3.Connection,
    document_id: int,
    file_size: int,
    modified_at: float,
    sha256: str,
    indexed_at: float,
) -> None:
    """Atualiza metadados e o hash de um documento existente."""
    conn.execute(
        """
        UPDATE documents
        SET file_size = ?, modified_at = ?, sha256 = ?, indexed_at = ?
        WHERE id = ?;
        """,
        (file_size, modified_at, sha256, indexed_at, document_id),
    )


def buscar_documento_por_path(
    conn: sqlite3.Connection, path: str
) -> Optional[sqlite3.Row]:
    """Retorna o registro do documento pelo caminho, ou None se não existir."""
    cursor = conn.execute(
        "SELECT * FROM documents WHERE path = ?;", (path,)
    )
    return cursor.fetchone()


def listar_documentos(conn: sqlite3.Connection) -> list:
    """Retorna todos os documentos indexados."""
    cursor = conn.execute("SELECT * FROM documents;")
    return cursor.fetchall()


def listar_documentos_da_origem(conn: sqlite3.Connection, source_root: str) -> list:
    """Lista documentos vinculados a uma raiz, incluindo legados dentro dela."""
    raiz = os.path.normcase(os.path.realpath(source_root))
    documentos = []
    for doc in listar_documentos(conn):
        origem = doc["source_root"]
        if origem and os.path.normcase(os.path.realpath(origem)) == raiz:
            documentos.append(doc)
            continue
        if not origem:
            try:
                if os.path.commonpath([raiz, os.path.normcase(os.path.realpath(doc["path"]))]) == raiz:
                    documentos.append(doc)
            except ValueError:
                pass
    return documentos


def remover_documento(conn: sqlite3.Connection, document_id: int) -> None:
    """
    Remove um documento do banco. A deleção em cascata (ON DELETE CASCADE)
    removerá as páginas correspondentes na tabela 'pages', e o trigger
    't_pages_ad' atualizará automaticamente a tabela virtual FTS5.
    
    Nota: A transação deve ser commitada pelo chamador.
    """
    conn.execute("DELETE FROM documents WHERE id = ?;", (document_id,))


def contar_documentos(conn: sqlite3.Connection) -> int:
    """Retorna a quantidade de documentos indexados."""
    cursor = conn.execute("SELECT COUNT(*) AS total FROM documents;")
    return cursor.fetchone()["total"]


# ---------------------------------------------------------------------------
# Operações sobre 'pages' e 'pages_fts'
# ---------------------------------------------------------------------------

def inserir_pagina(
    conn: sqlite3.Connection,
    document_id: int,
    page_number: int,
    text: str,
    text_normalized: Optional[str] = None,
    text_stemmed: Optional[str] = None
) -> int:
    """
    Insere uma página no banco. Os triggers cuidarão de
    replicar o texto nas tabelas virtuais FTS5.
    """
    from search import normalizar_consulta, stemizar_texto
    if text_normalized is None:
        text_normalized = normalizar_consulta(text)
    if text_stemmed is None:
        text_stemmed = stemizar_texto(text_normalized)
    cursor = conn.execute(
        "INSERT INTO pages (document_id, page_number, text, text_normalized, text_stemmed) VALUES (?, ?, ?, ?, ?);",
        (document_id, page_number, text, text_normalized, text_stemmed),
    )
    return cursor.lastrowid


def inserir_paginas_lote(
    conn: sqlite3.Connection, paginas: list
) -> None:
    """
    Insere múltiplas páginas de uma vez. Os triggers atualizarão
    automaticamente as tabelas virtuais FTS5 para cada página inserida.
    """
    from search import normalizar_consulta, stemizar_texto
    processado = []
    for item in paginas:
        if len(item) == 3:
            doc_id, p_num, txt = item
            txt_norm = normalizar_consulta(txt)
            txt_stem = stemizar_texto(txt_norm)
            processado.append((doc_id, p_num, txt, txt_norm, txt_stem))
        elif len(item) == 4:
            doc_id, p_num, txt, txt_norm = item
            txt_stem = stemizar_texto(txt_norm)
            processado.append((doc_id, p_num, txt, txt_norm, txt_stem))
        else:
            processado.append(item)

    conn.executemany(
        "INSERT INTO pages (document_id, page_number, text, text_normalized, text_stemmed) VALUES (?, ?, ?, ?, ?);",
        processado,
    )


def contar_paginas(conn: sqlite3.Connection) -> int:
    """Retorna a quantidade total de páginas indexadas."""
    cursor = conn.execute("SELECT COUNT(*) AS total FROM pages;")
    return cursor.fetchone()["total"]


def atualizar_vocabulario(conn: sqlite3.Connection) -> None:
    """
    Atualiza a lista de termos únicos e válidos na tabela virtual/auxiliar 'vocabulary'
    a partir da coluna 'text_normalized' de todas as páginas.
    """
    conn.execute("DELETE FROM vocabulary;")
    cursor = conn.execute("SELECT text_normalized FROM pages;")
    palavras_unicas = set()
    for row in cursor:
        texto = row["text_normalized"]
        if texto:
            for palavra in texto.split():
                # Apenas palavras com pelo menos 3 letras e puramente alfabéticas
                if len(palavra) >= 3 and palavra.isalpha():
                    palavras_unicas.add(palavra)
    
    conn.executemany(
        "INSERT OR IGNORE INTO vocabulary (word) VALUES (?);",
        [(w,) for w in palavras_unicas]
    )
