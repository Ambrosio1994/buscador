"""
indexer.py

Responsável por percorrer uma pasta de PDFs e manter o índice no banco
de dados sincronizado com o conteúdo real da pasta:

- indexa arquivos novos;
- reindexa arquivos alterados (tamanho ou data de modificação diferentes);
- não reindexa arquivos inalterados;
- remove do banco arquivos que não existem mais na pasta.

Regra fundamental (seção 7.2 da especificação): a busca nunca lê os PDFs
diretamente. Toda leitura acontece aqui, durante a indexação.
"""

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import database
from config import PDF_EXTENSION
from pdf_utils import PDFInvalidoError, extrair_texto_pdf, pdf_possui_texto_extraivel


@dataclass
class ResultadoIndexacao:
    """Resumo do que aconteceu em uma execução de indexação."""

    novos: List[str] = field(default_factory=list)
    atualizados: List[str] = field(default_factory=list)
    inalterados: List[str] = field(default_factory=list)
    removidos: List[str] = field(default_factory=list)
    sem_texto_extraivel: List[str] = field(default_factory=list)
    erros: List[str] = field(default_factory=list)
    tempo_execucao: float = 0.0
    total_documentos: int = 0
    total_paginas: int = 0

    def total_processado(self) -> int:
        return len(self.novos) + len(self.atualizados)


def listar_pdfs_da_pasta(pasta: str) -> List[str]:
    """Retorna os caminhos absolutos de todos os arquivos .pdf da pasta e subpastas (recursivo)."""
    if not os.path.isdir(pasta):
        return []

    arquivos = []
    for raiz, _, files in os.walk(pasta):
        for nome in sorted(files):
            if nome.lower().endswith(PDF_EXTENSION):
                caminho = os.path.join(raiz, nome)
                arquivos.append(os.path.abspath(caminho))
    return sorted(arquivos)


def calcular_sha256(caminho: str) -> str:
    """Calcula o hash SHA-256 de um arquivo lendo-o em blocos."""
    sha256_hash = hashlib.sha256()
    try:
        with open(caminho, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return ""


def _indexar_arquivo(
    conn: sqlite3.Connection,
    caminho: str,
    registro_existente: Optional[sqlite3.Row],
    resultado: ResultadoIndexacao,
    source_root: str,
) -> None:
    """Indexa (ou reindexa) um único arquivo PDF."""
    nome_arquivo = os.path.basename(caminho)

    try:
        paginas = extrair_texto_pdf(caminho)
    except PDFInvalidoError as exc:
        resultado.erros.append(f"{nome_arquivo}: {exc}")
        return

    if not pdf_possui_texto_extraivel(paginas):
        resultado.sem_texto_extraivel.append(nome_arquivo)
        # Mesmo sem texto, o documento é registrado para que o usuário veja
        # que ele foi processado (apenas sem conteúdo pesquisável).

    stat = os.stat(caminho)
    agora = time.time()
    sha256_val = calcular_sha256(caminho)

    # Se já existia, remove o registro antigo (e páginas associadas) antes de reindexar.
    if registro_existente is not None:
        database.remover_documento(conn, registro_existente["id"])

    document_id = database.inserir_documento(
        conn,
        filename=nome_arquivo,
        path=caminho,
        file_size=stat.st_size,
        modified_at=stat.st_mtime,
        total_pages=len(paginas),
        indexed_at=agora,
        sha256=sha256_val,
        source_root=source_root,
    )

    from search import normalizar_consulta
    paginas_lote = [
        (document_id, p["page_number"], p["text"], normalizar_consulta(p["text"]))
        for p in paginas
        if p["text"]
    ]
    if paginas_lote:
        database.inserir_paginas_lote(conn, paginas_lote)

    if registro_existente is not None:
        resultado.atualizados.append(nome_arquivo)
    else:
        resultado.novos.append(nome_arquivo)


def indexar_pasta(
    conn: sqlite3.Connection,
    pasta: str,
    callback_progresso: Optional[Callable[[int, int, str], None]] = None,
) -> ResultadoIndexacao:
    """
    Sincroniza o índice do banco com o conteúdo atual da pasta de PDFs.

    Retorna um ResultadoIndexacao descrevendo o que foi feito.
    """
    inicio = time.perf_counter()
    resultado = ResultadoIndexacao()

    if not os.path.isdir(pasta):
        raise ValueError(f"Pasta de manuais inexistente ou inacessível: {pasta}")
    source_root = os.path.realpath(os.path.abspath(pasta))

    caminhos_na_pasta = listar_pdfs_da_pasta(source_root)
    documentos_origem = database.listar_documentos_da_origem(conn, source_root)
    documentos_no_banco = {doc["path"]: doc for doc in documentos_origem}

    # Vincula registros legados à raiz sem exigir reindexação.
    conn.executemany(
        "UPDATE documents SET source_root = ? WHERE id = ? AND source_root IS NULL;",
        [(source_root, doc["id"]) for doc in documentos_origem],
    )

    # 1. Remove do banco documentos cujo arquivo não existe mais na pasta.
    caminhos_set = set(caminhos_na_pasta)
    for caminho_salvo, registro in documentos_no_banco.items():
        if caminho_salvo not in caminhos_set:
            database.remover_documento(conn, registro["id"])
            resultado.removidos.append(os.path.basename(caminho_salvo))

    # 2. Indexa arquivos novos ou reindexa arquivos alterados com suporte a progresso.
    total = len(caminhos_na_pasta)
    for i, caminho in enumerate(caminhos_na_pasta, 1):
        nome_arquivo = os.path.basename(caminho)
        if callback_progresso:
            callback_progresso(i, total, nome_arquivo)

        registro_existente = documentos_no_banco.get(caminho)

        if registro_existente is not None:
            stat = os.stat(caminho)
            # 1. Se tamanho e data de modificação forem idênticos, assume inalterado sem calcular hash (rápido)
            if (registro_existente["file_size"] == stat.st_size 
                    and registro_existente["modified_at"] == stat.st_mtime):
                resultado.inalterados.append(nome_arquivo)
                continue

            # 2. Se mudou data ou tamanho, calcula o SHA-256 para verificar alteração real
            sha256_atual = calcular_sha256(caminho)
            
            # Se o hash coincide com o salvo (e não for nulo/vazio), o conteúdo real é idêntico
            if registro_existente["sha256"] and registro_existente["sha256"] == sha256_atual:
                # Apenas atualizamos metadados no banco para evitar novos cálculos no futuro
                database.atualizar_metadados_documento(
                    conn,
                    registro_existente["id"],
                    stat.st_size,
                    stat.st_mtime,
                    sha256_atual,
                    time.time(),
                )
                resultado.inalterados.append(nome_arquivo)
                continue

        _indexar_arquivo(conn, caminho, registro_existente, resultado, source_root)

    if resultado.novos or resultado.atualizados or resultado.removidos:
        database.atualizar_vocabulario(conn)
    conn.commit()

    resultado.tempo_execucao = time.perf_counter() - inicio
    resultado.total_documentos = database.contar_documentos(conn)
    resultado.total_paginas = database.contar_paginas(conn)

    return resultado
