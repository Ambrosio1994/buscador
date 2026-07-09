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
    relevance_label: str


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
    - No modo 'amplo', os termos são combinados com OR.
    - No modo 'preciso', os termos são combinados com AND.
    - No modo 'frase', os termos são agrupados em uma única string em aspas duplas,
      exigindo a sequência exata de palavras.
    """
    termos_validos = [t for t in termos if t]
    if not termos_validos:
        return ""

    termos_limpos = [re.sub(r"[^\w]", "", t) for t in termos_validos]
    termos_limpos = [t for t in termos_limpos if t]
    if not termos_limpos:
        return ""

    if modo == "frase":
        return f'"{ " ".join(termos_limpos) }*"'
    
    termos_fts = [f'{t}*' for t in termos_limpos]
    
    if modo == "preciso":
        return " AND ".join(termos_fts)
    else:
        return " OR ".join(termos_fts)


def calcular_score_customizado(
    texto_pagina: str, termos: List[str], bm25_score: float, modo: str = "amplo"
) -> tuple[float, str]:
    """
    Calcula um score personalizado baseado no número de termos casados
    e na proximidade entre eles.
    
    Retorna (score_customizado, etiqueta_relevancia).
    """
    if not termos:
        return bm25_score, "Baixa"

    # Normaliza o texto da página
    texto_norm = normalizar_consulta(texto_pagina)
    palavras_texto = texto_norm.split()
    
    # Encontra ocorrências de cada termo (por prefixo)
    ocorrencias = {}
    for t in termos:
        indices = [i for i, w in enumerate(palavras_texto) if w.startswith(t)]
        if indices:
            ocorrencias[t] = indices
            
    n_matched_terms = len(ocorrencias)
    L = len(termos)
    
    if n_matched_terms == 0:
        return bm25_score, "Baixa"

    # Proximidade: menor janela contendo todos os termos casados
    if n_matched_terms > 1:
        list_of_occurrences = []
        for term, indices in ocorrencias.items():
            for idx in indices:
                list_of_occurrences.append((idx, term))
        list_of_occurrences.sort(key=lambda x: x[0])
        
        required_terms = set(ocorrencias.keys())
        min_len = float('inf')
        
        counts = {}
        left = 0
        for right in range(len(list_of_occurrences)):
            _, r_term = list_of_occurrences[right]
            counts[r_term] = counts.get(r_term, 0) + 1
            
            while len(counts) == len(required_terms):
                window_len = list_of_occurrences[right][0] - list_of_occurrences[left][0] + 1
                if window_len < min_len:
                    min_len = window_len
                
                _, l_term = list_of_occurrences[left]
                counts[l_term] -= 1
                if counts[l_term] == 0:
                    del counts[l_term]
                left += 1
        window_size = min_len if min_len != float('inf') else 1000
    else:
        window_size = 1
        
    # Ajuste do score: mais termos casados diminui o score drasticamente.
    # Proximidade (window_size) adiciona uma penalidade leve.
    # BM25 entra como critério de desempate.
    score_customizado = -1000.0 * n_matched_terms + 0.1 * window_size + bm25_score
    
    # Classificação visual da relevância
    if modo == "frase" or modo == "preciso":
        relevancia = "Alta"
    elif L == 1:
        relevancia = "Alta"
    else:
        if n_matched_terms == L:
            relevancia = "Alta"
        elif n_matched_terms >= L / 2 and n_matched_terms > 1:
            relevancia = "Média"
        else:
            relevancia = "Baixa"
            
    return score_customizado, relevancia


def buscar(
    conn: sqlite3.Connection,
    consulta: str,
    limite: int = MAX_RESULTS,
    modo: str = "amplo",
) -> List[ResultadoBusca]:
    """
    Executa a busca completa: normaliza a consulta, remove stopwords,
    monta a query FTS5 no modo selecionado (amplo, preciso ou frase) e retorna
    os resultados ordenados por relevância baseada em score customizado
    (número de termos combinados e proximidade).

    Retorna lista vazia se a consulta for vazia ou não houver resultados.
    """
    consulta_normalizada = normalizar_consulta(consulta)
    if not consulta_normalizada:
        return []

    termos = remover_palavras_irrelevantes(consulta_normalizada)
    query_fts = montar_query_fts(termos, modo)
    if not query_fts:
        return []

    # Aumentamos o limite no SQL para podermos reordenar via Python
    limite_sql = max(limite * 4, 100)

    sql = """
        SELECT
            documents.filename,
            documents.path,
            pages.page_number,
            pages.text,
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
        cursor = conn.execute(sql, (SNIPPET_CONTEXT_WORDS, query_fts, limite_sql))
    except sqlite3.OperationalError:
        # Consulta FTS malformada (ex.: apenas caracteres especiais) -> sem resultados.
        return []

    resultados_brutos = []
    for row in cursor.fetchall():
        score_custom, relevancia = calcular_score_customizado(
            row["text"], termos, row["score"], modo
        )
        
        resultados_brutos.append(
            {
                "filename": row["filename"],
                "path": row["path"],
                "page_number": row["page_number"],
                "snippet": row["snippet_text"],
                "score": score_custom,
                "relevance_label": relevancia,
            }
        )

    # Ordena pelo score personalizado (menor score = mais relevante)
    resultados_brutos.sort(key=lambda x: x["score"])
    
    return resultados_brutos[:limite]
