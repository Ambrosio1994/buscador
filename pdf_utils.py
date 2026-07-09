"""
pdf_utils.py

Funções de leitura e extração de texto de arquivos PDF usando PyMuPDF (fitz).

Este módulo é resistente a erros: PDFs corrompidos, inexistentes ou sem
texto extraível não devem travar o restante do programa.
"""

import os
from typing import List, TypedDict

import fitz  # PyMuPDF


class PaginaExtraida(TypedDict):
    page_number: int
    text: str


class PDFInvalidoError(Exception):
    """Levantada quando o PDF não pode ser aberto (inexistente ou corrompido)."""


def contar_paginas_pdf(path: str) -> int:
    """Retorna o número total de páginas de um PDF."""
    with _abrir_documento(path) as doc:
        return doc.page_count


def extrair_texto_pdf(path: str) -> List[PaginaExtraida]:
    """
    Extrai o texto de cada página de um PDF.

    Retorna uma lista de dicionários {"page_number": N, "text": "..."}.
    Páginas vazias (ou sem texto extraível) retornam text="" e não
    interrompem a extração das demais páginas.

    Levanta PDFInvalidoError se o arquivo não existir ou estiver corrompido.
    """
    paginas: List[PaginaExtraida] = []

    with _abrir_documento(path) as doc:
        for numero_pagina in range(doc.page_count):
            try:
                pagina = doc.load_page(numero_pagina)
                texto = pagina.get_text("text") or ""
            except Exception:
                # Página problemática isolada: não deve derrubar o PDF inteiro.
                texto = ""

            paginas.append(
                {"page_number": numero_pagina + 1, "text": texto.strip()}
            )

    return paginas


def pdf_possui_texto_extraivel(paginas: List[PaginaExtraida]) -> bool:
    """
    Verifica se ao menos uma página do PDF possui texto extraível.

    Usado para identificar PDFs escaneados como imagem (ver seção 7.3
    da especificação): nesses casos, o sistema deve apenas informar o
    usuário, sem tentar fazer OCR na primeira versão.
    """
    return any(pagina["text"].strip() for pagina in paginas)


class _abrir_documento:
    """
    Context manager simples para abrir um PDF com tratamento de erro
    padronizado, garantindo que o documento seja sempre fechado.
    """

    def __init__(self, path: str):
        self.path = path
        self.doc = None

    def __enter__(self) -> fitz.Document:
        if not os.path.isfile(self.path):
            raise PDFInvalidoError(f"Arquivo não encontrado: {self.path}")
        try:
            self.doc = fitz.open(self.path)
        except Exception as exc:
            raise PDFInvalidoError(
                f"Não foi possível abrir o PDF (arquivo corrompido?): {self.path}"
            ) from exc
        return self.doc

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.doc is not None:
            self.doc.close()
