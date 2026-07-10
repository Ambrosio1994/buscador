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


class ErroBusca(RuntimeError):
    """Falha estrutural ao consultar os índices FTS."""


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
    texto = _remover_acentos(consulta.lower())
    # Além dos componentes, indexa a forma compacta de códigos técnicos:
    # "XP-400" -> "xp 400 xp400" e "AB.12/7" -> "ab 12 7 ab127".
    codigos = re.findall(r"\b[\w]+(?:[-./][\w]+)+\b", texto)
    compactos = [re.sub(r"[-./]", "", codigo) for codigo in codigos]
    texto = re.sub(r"[^\w\s]", " ", texto)  # remove pontuação, mantém letras/números/underscore
    texto = re.sub(r"\s+", " ", texto).strip()
    if compactos:
        texto = f"{texto} {' '.join(compactos)}".strip()
    return texto


def stemizar_palavra(palavra: str) -> str:
    """
    Reduz uma palavra em português ao seu radical de forma simplificada e eficiente.
    Remove plurais, gêneros e sufixos comuns.
    """
    if len(palavra) < 4:
        return palavra

    w = palavra.lower()

    # 1. Plurais
    if w.endswith("s"):
        if w.endswith("ns"):
            w = w[:-2] + "m"
        elif w.endswith("es"):
            if w.endswith("coes"):
                w = w[:-4] + "cao"
            else:
                w = w[:-2]
        elif w.endswith("is"):
            if w.endswith("ais"):
                w = w[:-3] + "al"
            elif w.endswith("eis"):
                w = w[:-3] + "el"
            elif w.endswith("ois"):
                w = w[:-3] + "ol"
            elif w.endswith("uis"):
                w = w[:-3] + "ul"
            else:
                w = w[:-1]
        else:
            w = w[:-1]

    # 2. Sufixo Adverbial
    if w.endswith("mente"):
        w = w[:-5]

    # 3. Sufixos Nominais / Gênero
    if w.endswith("cao"):
        w = w[:-3] + "ca"
    
    if w.endswith("al") and len(w) > 4:
        w = w[:-2]
        
    if w.endswith("idade") and len(w) > 6:
        w = w[:-5]

    # 4. Redução de Gênero
    if w.endswith("a") and not w.endswith("ia"):
        w = w[:-1] + "o"

    return w


def stemizar_texto(texto: str) -> str:
    """Aplica o stemmer simplificado sobre todas as palavras de um texto normalizado."""
    if not texto:
        return ""
    return " ".join(stemizar_palavra(w) for w in texto.split())


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


def calcular_janela_e_matches(
    texto_norm: str, termos: List[str]
) -> tuple[int, int]:
    """
    Calcula a quantidade de termos únicos casados e a menor janela de proximidade.
    Retorna (n_matched_terms, window_size).
    """
    if not termos:
        return 0, 1000

    palavras_texto = texto_norm.split()
    
    # Encontra ocorrências de cada termo (por prefixo)
    ocorrencias = {}
    for t in termos:
        indices = [i for i, w in enumerate(palavras_texto) if w.startswith(t)]
        if indices:
            ocorrencias[t] = indices
            
    n_matched_terms = len(ocorrencias)
    
    if n_matched_terms == 0:
        return 0, 1000

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
        
    return n_matched_terms, window_size


def buscar(
    conn: sqlite3.Connection,
    consulta: str,
    limite: int = MAX_RESULTS,
    modo: str = "amplo",
) -> List[ResultadoBusca]:
    """
    Executa a busca completa: normaliza a consulta, remove stopwords,
    busca tanto de forma exata quanto por radical (stemmer) em paralelo,
    mescla as duas listas priorizando os resultados exatos e ordena
    por score ponderado (cobertura de termos, proximidade e BM25).

    Retorna lista vazia se a consulta for vazia ou não houver resultados.
    """
    consulta_normalizada = normalizar_consulta(consulta)
    if not consulta_normalizada:
        return []

    termos = remover_palavras_irrelevantes(consulta_normalizada)

    query_original = montar_query_fts(termos, modo)
    if not query_original:
        return []
    try:
        possui_resultado_original = conn.execute(
            "SELECT 1 FROM pages_fts WHERE pages_fts MATCH ? LIMIT 1;",
            (query_original,),
        ).fetchone() is not None
    except sqlite3.OperationalError as exc:
        raise ErroBusca(f"Falha ao consultar o índice textual: {exc}") from exc

    # Spellcheck/Fuzzy Correction usando vocabulário local
    import difflib
    termos_corrigidos = []
    for t in termos:
        if possui_resultado_original:
            termos_corrigidos.append(t)
            continue
        if len(t) < 4:
            termos_corrigidos.append(t)
            continue
        # Se o termo já existe (ou tem palavra começando com ele), não altera
        existente = conn.execute(
            "SELECT 1 FROM vocabulary WHERE word >= ? AND word < ? LIMIT 1;",
            (t, t + "\U0010ffff"),
        ).fetchone()
        if existente:
            termos_corrigidos.append(t)
        else:
            # Restringe o fuzzy a palavras de tamanho próximo e mesma inicial.
            candidatos = conn.execute(
                "SELECT word FROM vocabulary WHERE word LIKE ? "
                "AND length(word) BETWEEN ? AND ? LIMIT 500;",
                (t[0] + "%", max(1, len(t) - 2), len(t) + 2),
            ).fetchall()
            matches = difflib.get_close_matches(
                t, [row["word"] for row in candidatos], n=1, cutoff=0.75
            )
            if matches:
                termos_corrigidos.append(matches[0])
            else:
                termos_corrigidos.append(t)
                
    termos = termos_corrigidos
    query_fts = montar_query_fts(termos, modo)
    if not query_fts:
        return []

    # Termos stemizados para a busca secundária por radical
    termos_stemmed = [stemizar_palavra(t) for t in termos]
    query_fts_stemmed = montar_query_fts(termos_stemmed, modo)

    # Limite aumentado no SQL para reordenação no Python
    limite_sql = max(limite * 4, 100)

    # 1. SQL para busca exata (pages_fts)
    sql_exact = """
        SELECT
            documents.filename,
            documents.path,
            pages.page_number,
            pages.text,
            pages.text_normalized,
            pages.text_stemmed,
            snippet(pages_fts, 0, '[', ']', '...', ?) AS snippet_text,
            bm25(pages_fts) AS score
        FROM pages_fts
        JOIN pages ON pages_fts.rowid = pages.id
        JOIN documents ON pages.document_id = documents.id
        WHERE pages_fts MATCH ?
        ORDER BY score
        LIMIT ?;
    """

    # 2. SQL para busca por radical (pages_stemmed_fts)
    sql_stemmed = """
        SELECT
            documents.filename,
            documents.path,
            pages.page_number,
            pages.text,
            pages.text_normalized,
            pages.text_stemmed,
            snippet(pages_stemmed_fts, 0, '[', ']', '...', ?) AS snippet_text,
            bm25(pages_stemmed_fts) AS score
        FROM pages_stemmed_fts
        JOIN pages ON pages_stemmed_fts.rowid = pages.id
        JOIN documents ON pages.document_id = documents.id
        WHERE pages_stemmed_fts MATCH ?
        ORDER BY score
        LIMIT ?;
    """

    rows_exact = []
    try:
        cursor = conn.execute(sql_exact, (SNIPPET_CONTEXT_WORDS, query_fts, limite_sql))
        rows_exact = cursor.fetchall()
    except sqlite3.OperationalError as exc:
        raise ErroBusca(f"Falha ao consultar o índice textual: {exc}") from exc

    rows_stemmed = []
    if len(rows_exact) < limite:
        try:
            cursor_s = conn.execute(sql_stemmed, (SNIPPET_CONTEXT_WORDS, query_fts_stemmed, limite_sql))
            rows_stemmed = cursor_s.fetchall()
        except sqlite3.OperationalError as exc:
            raise ErroBusca(f"Falha ao consultar o índice por radical: {exc}") from exc

    if not rows_exact and not rows_stemmed:
        resultados_metadados = []
        for doc in conn.execute("SELECT filename, path FROM documents;"):
            metadados = normalizar_consulta(f"{doc['filename']} {doc['path']}")
            palavras = metadados.split()
            encontrados = sum(1 for termo in termos if any(w.startswith(termo) for w in palavras))
            corresponde = encontrados == len(termos) if modo in ("preciso", "frase") else encontrados > 0
            if corresponde:
                resultados_metadados.append({
                    "filename": doc["filename"], "path": doc["path"], "page_number": 1,
                    "snippet": f"Correspondência no nome ou categoria do manual: [{doc['filename']}]",
                    "score": 0.90 + 0.10 * (encontrados / len(termos)),
                    "relevance_label": "Alta" if encontrados == len(termos) else "Média",
                })
        resultados_metadados.sort(key=lambda x: x["score"], reverse=True)
        return resultados_metadados[:limite]

    L = len(termos)
    candidatos_dict = {}

    # Insere resultados da busca exata
    for row in rows_exact:
        key = (row["path"], row["page_number"])
        texto_norm = row["text_normalized"] if row["text_normalized"] is not None else normalizar_consulta(row["text"])
        n_matched_terms, window_size = calcular_janela_e_matches(texto_norm, termos)
        candidatos_dict[key] = {
            "row": row,
            "n_matched_terms": n_matched_terms,
            "window_size": window_size,
            "bm25": row["score"],
            "is_exact": True
        }

    # Insere resultados da busca por radical (se não existirem já)
    for row in rows_stemmed:
        key = (row["path"], row["page_number"])
        if key not in candidatos_dict:
            texto_norm = row["text_normalized"] if row["text_normalized"] is not None else normalizar_consulta(row["text"])
            n_matched_terms, window_size = calcular_janela_e_matches(texto_norm, termos)
            candidatos_dict[key] = {
                "row": row,
                "n_matched_terms": n_matched_terms,
                "window_size": window_size,
                "bm25": row["score"],
                "is_exact": False
            }

    candidatos = list(candidatos_dict.values())

    # Normalização dos sinais
    w_min = min(c["window_size"] for c in candidatos)
    w_max = max(c["window_size"] for c in candidatos)
    b_min = min(c["bm25"] for c in candidatos)
    b_max = max(c["bm25"] for c in candidatos)

    resultados_brutos = []
    for c in candidatos:
        row = c["row"]
        n_matched = c["n_matched_terms"]
        w = c["window_size"]
        b = c["bm25"]

        cobertura_norm = n_matched / L if L > 0 else 0.0

        if w_max > w_min:
            proximidade_norm = 1.0 - (w - w_min) / (w_max - w_min)
        else:
            proximidade_norm = 1.0

        if b_max > b_min:
            bm25_norm = (b_max - b) / (b_max - b_min)
        else:
            bm25_norm = 1.0

        score_final = 0.50 * cobertura_norm + 0.35 * bm25_norm + 0.15 * proximidade_norm

        # Penalidade para resultados que só casaram via radical (stemmer)
        if not c["is_exact"]:
            score_final = score_final * 0.80

        # Classificação de relevância
        if modo == "frase" or modo == "preciso":
            relevancia = "Alta"
        elif L <= 1:
            relevancia = "Alta"
        else:
            if n_matched == L:
                relevancia = "Alta"
            elif n_matched >= L / 2 and n_matched > 1:
                relevancia = "Média"
            else:
                relevancia = "Baixa"

        resultados_brutos.append({
            "filename": row["filename"],
            "path": row["path"],
            "page_number": row["page_number"],
            "snippet": row["snippet_text"],
            "score": score_final,
            "relevance_label": relevancia,
        })

    # Nome e caminho do manual funcionam como metadados de alta relevância.
    # Isso encontra códigos/categorias presentes apenas no nome do arquivo.
    chaves_existentes = {(r["path"], r["page_number"]) for r in resultados_brutos}
    for doc in conn.execute("SELECT filename, path FROM documents;"):
        metadados = normalizar_consulta(f"{doc['filename']} {doc['path']}")
        encontrados = sum(1 for termo in termos if any(w.startswith(termo) for w in metadados.split()))
        corresponde = encontrados == L if modo in ("preciso", "frase") else encontrados > 0
        if corresponde and (doc["path"], 1) not in chaves_existentes:
            resultados_brutos.append({
                "filename": doc["filename"],
                "path": doc["path"],
                "page_number": 1,
                "snippet": f"Correspondência no nome ou categoria do manual: [{doc['filename']}]",
                "score": 0.90 + 0.10 * (encontrados / L),
                "relevance_label": "Alta" if encontrados == L else "Média",
            })
        elif corresponde:
            for resultado in resultados_brutos:
                if resultado["path"] == doc["path"]:
                    resultado["score"] += 0.12 * (encontrados / L)

    # Ordena e promove diversidade: no máximo duas páginas por manual na
    # primeira passagem, preenchendo vagas restantes depois.
    resultados_brutos.sort(key=lambda x: x["score"], reverse=True)
    diversos = []
    excedentes = []
    por_documento = {}
    for resultado in resultados_brutos:
        path = resultado["path"]
        por_documento[path] = por_documento.get(path, 0) + 1
        (diversos if por_documento[path] <= 2 else excedentes).append(resultado)

    return (diversos + excedentes)[:limite]
