"""
search.py

Responsável por normalizar a consulta do usuário e executar a busca
usando SQLite FTS5, retornando resultados ordenados por relevância.

A busca NUNCA lê os PDFs diretamente (regra da seção 7.2): ela consulta
exclusivamente o índice já construído pelo indexer.py.
"""

import re
import sqlite3
import unicodedata
from typing import List, TypedDict

from config import MAX_RESULTS, SNIPPET_CONTEXT_WORDS, STOPWORDS


class ResultadoBusca(TypedDict):
    filename: str
    path: str
    page_number: int
    snippet: str
    score: float


def _remover_acentos(texto: str) -> str:
    """Remove acentuação, preservando as letras base (á -> a, ç -> c, etc.)."""
    forma_normalizada = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in forma_normalizada if not unicodedata.combining(c))


def normalizar_consulta(consulta: str) -> str:
    """
    Normaliza a consulta do usuário:
    1. converte para minúsculas;
    2. remove acentos;
    3. remove pontuação desnecessária;
    4. remove excesso de espaços.
    """
    texto = consulta.lower()
    texto = _remover_acentos(texto)
    texto = re.sub(r"[^\w\s]", " ", texto)  # remove pontuação, mantém letras/números/underscore
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def remover_palavras_irrelevantes(consulta_normalizada: str) -> List[str]:
    """Remove stopwords da consulta já normalizada, retornando a lista de termos relevantes."""
    palavras = consulta_normalizada.split()
    return [palavra for palavra in palavras if palavra not in STOPWORDS]


def montar_query_fts(termos: List[str], modo: str = "amplo") -> str:
    """
    Monta a expressão de busca para o FTS5 a partir dos termos relevantes.

    Cada termo recebe um '*' para permitir correspondência por prefixo.
    - No modo 'amplo', os termos são combinados com OR (comportamento original).
    - No modo 'preciso', os termos são combinados com AND, exigindo a presença de todos.
    """
    termos_validos = [t for t in termos if t]
    if not termos_validos:
        return ""

    termos_fts = [f'{re.sub(r"[^\w]", "", t)}*' for t in termos_validos if t]
    termos_fts = [t for t in termos_fts if t != "*"]
    
    if modo == "preciso":
        return " AND ".join(termos_fts)
    else:
        return " OR ".join(termos_fts)


def buscar(
    conn: sqlite3.Connection,
    consulta: str,
    limite: int = MAX_RESULTS,
    modo: str = "amplo",
) -> List[ResultadoBusca]:
    """
    Executa a busca completa: normaliza a consulta, remove stopwords,
    monta a query FTS5 no modo selecionado (amplo ou preciso) e retorna
    os resultados ordenados por relevância (BM25 crescente = mais relevante primeiro).

    Retorna lista vazia se a consulta for vazia ou não houver resultados.
    """
    consulta_normalizada = normalizar_consulta(consulta)
    if not consulta_normalizada:
        return []

    termos = remover_palavras_irrelevantes(consulta_normalizada)
    query_fts = montar_query_fts(termos, modo)
    if not query_fts:
        return []

    sql = """
        SELECT
            documents.filename,
            documents.path,
            pages.page_number,
            snippet(pages_fts, 0, '[', ']', '...', ?) AS snippet_text,
            bm25(pages_fts) AS score
        FROM pages_fts
        JOIN pages ON pages_fts.rowid = pages.id
        JOIN documents ON pages.document_id = documents.id
        WHERE pages_fts MATCH ?
        ORDER BY score
        LIMIT ?;
    """

    try:
        cursor = conn.execute(sql, (SNIPPET_CONTEXT_WORDS, query_fts, limite))
    except sqlite3.OperationalError:
        # Consulta FTS malformada (ex.: apenas caracteres especiais) -> sem resultados.
        return []

    resultados: List[ResultadoBusca] = []
    for row in cursor.fetchall():
        resultados.append(
            {
                "filename": row["filename"],
                "path": row["path"],
                "page_number": row["page_number"],
                "snippet": row["snippet_text"],
                "score": row["score"],
            }
        )
    return resultados
