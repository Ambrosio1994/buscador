"""
opener.py

Responsável por abrir um PDF no visualizador/navegador padrão do sistema,
diretamente na página indicada, a partir de um resultado de busca.
"""

import os
import shutil
import subprocess
import webbrowser
from urllib.request import pathname2url

from config import PREFERRED_BROWSERS


class ArquivoNaoEncontradoError(Exception):
    """Levantada quando o caminho do PDF informado não existe mais no disco."""


def construir_uri_pdf(path: str, page_number: int, termos_busca: str | None = None) -> str:
    """
    Converte um caminho local de arquivo em uma URI 'file://' com o
    fragmento '#page=N' (e opcionalmente '&search=termos'), usado por navegadores
    e visualizadores de PDF para abrir diretamente na página e destacar as palavras.
    """
    import urllib.parse
    caminho_absoluto = os.path.abspath(path)
    uri = "file://" + pathname2url(caminho_absoluto)
    
    fragmento = f"page={page_number}"
    if termos_busca:
        # Codifica os termos de busca para uso seguro em URLs
        termos_codificados = urllib.parse.quote(termos_busca)
        fragmento += f"&search={termos_codificados}"
        
    return f"{uri}#{fragmento}"


def encontrar_navegador_preferencial() -> str | None:
    """
    Percorre a lista de navegadores preferenciais e retorna o caminho completo
    do primeiro binário encontrado no PATH do sistema via shutil.which().
    """
    for browser in PREFERRED_BROWSERS:
        caminho = shutil.which(browser)
        if caminho:
            return caminho
    return None


def open_pdf_at_page(path: str, page_number: int, termos_busca: str | None = None) -> str:
    """
    Abre o PDF informado na página indicada, destacando os termos se fornecidos.
    Tenta as seguintes opções em ordem:
    1. Chamar o binário de navegador preferencial encontrado via encontrar_navegador_preferencial()
       (usando --app se for um navegador baseado em Chromium/Brave/Chrome).
    2. Usar o executável definido na variável de ambiente $BROWSER.
    3. Cair para o comportamento padrão do python (webbrowser.open) como último recurso.

    Retorna a URI utilizada para abrir o arquivo.
    Levanta ArquivoNaoEncontradoError se o arquivo não existir.
    """
    if not os.path.isfile(path):
        raise ArquivoNaoEncontradoError(f"Arquivo não encontrado: {path}")

    uri = construir_uri_pdf(path, page_number, termos_busca)

    # 1. Tentar navegador preferencial encontrado
    binario_navegador = encontrar_navegador_preferencial()
    if binario_navegador:
        nome_binario = os.path.basename(binario_navegador).lower()
        # Se for baseado em Chromium/Brave/Chrome, usa modo app para interface limpa (sem abas)
        if any(c in nome_binario for c in ["brave", "chrome", "chromium"]):
            try:
                subprocess.Popen([binario_navegador, f"--app={uri}"])
                return uri
            except Exception:
                pass
        else:
            try:
                subprocess.Popen([binario_navegador, uri])
                return uri
            except Exception:
                pass

    # 2. Tentar a variável de ambiente $BROWSER
    env_browser = os.environ.get("BROWSER")
    if env_browser:
        binario_env = shutil.which(env_browser)
        if binario_env:
            try:
                subprocess.Popen([binario_env, uri])
                return uri
            except Exception:
                pass

    # 3. Fallback: comportamento original
    webbrowser.open(uri)
    return uri

