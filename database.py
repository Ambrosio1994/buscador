"""
database.py

Responsável por toda a interação com o banco de dados SQLite:
criação de tabelas, inserção, remoção e consultas de apoio.

A busca textual em si (FTS5 MATCH) fica em search.py; aqui ficam apenas
as operações estruturais do banco (schema e CRUD básico).
"""

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from config import DATABASE_PATH, garantir_diretorio_dados


def conectar(db_path: str = DATABASE_PATH) -> sqlite3.Connection:
    """
    Abre uma conexão com o banco SQLite, garantindo que o diretório exista
    e que chaves estrangeiras (ON DELETE CASCADE) sejam respeitadas.
    Também ativa configurações de alta performance (WAL, cache e sincronização).
    """
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
            total_pages INTEGER,
            indexed_at REAL NOT NULL
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        """
    )

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

    # Triggers para sincronização automática com o índice FTS5 (external content)
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS t_pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, text) VALUES(new.id, new.text);
        END;
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS t_pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, text) VALUES('delete', old.id, old.text);
        END;
        """
    )

    # Índice de apoio para acelerar as verificações de páginas por documento
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages(document_id);"
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
) -> int:
    """Insere um novo documento e retorna o id gerado."""
    cursor = conn.execute(
        """
        INSERT INTO documents (filename, path, file_size, modified_at, total_pages, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (filename, path, file_size, modified_at, total_pages, indexed_at),
    )
    return cursor.lastrowid


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
    conn: sqlite3.Connection, document_id: int, page_number: int, text: str
) -> int:
    """
    Insere uma página no banco. O trigger 't_pages_ai' cuidará de
    replicar o texto na tabela virtual FTS5.
    """
    cursor = conn.execute(
        "INSERT INTO pages (document_id, page_number, text) VALUES (?, ?, ?);",
        (document_id, page_number, text),
    )
    return cursor.lastrowid


def inserir_paginas_lote(
    conn: sqlite3.Connection, paginas: list[tuple[int, int, str]]
) -> None:
    """
    Insere múltiplas páginas de uma vez. O trigger 't_pages_ai' atualizará
    automaticamente a tabela virtual FTS5 para cada página inserida.
    """
    conn.executemany(
        "INSERT INTO pages (document_id, page_number, text) VALUES (?, ?, ?);",
        paginas,
    )


def contar_paginas(conn: sqlite3.Connection) -> int:
    """Retorna a quantidade total de páginas indexadas."""
    cursor = conn.execute("SELECT COUNT(*) AS total FROM pages;")
    return cursor.fetchone()["total"]
