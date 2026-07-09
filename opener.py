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
    Respeita a configuração de visualizador preferencial salva pelo usuário e
    cai para fallbacks (Evince, Okular, Navegadores, xdg-open) se necessário.

    Retorna a URI ou o comando utilizado para abrir o arquivo.
    Levanta ArquivoNaoEncontradoError se o arquivo não existir.
    """
    if not os.path.isfile(path):
        raise ArquivoNaoEncontradoError(f"Arquivo não encontrado: {path}")

    from config import obter_setting
    visualizador = obter_setting("visualizador_pdf", "sistema")
    uri = construir_uri_pdf(path, page_number, termos_busca)

    # 1. Tentar o visualizador configurado pelo usuário se for específico
    if visualizador == "evince" and shutil.which("evince"):
        try:
            subprocess.Popen(["evince", "-p", str(page_number), path])
            return uri
        except Exception:
            pass
    elif visualizador == "okular" and shutil.which("okular"):
        try:
            subprocess.Popen(["okular", "-p", str(page_number), path])
            return uri
        except Exception:
            pass
    elif visualizador in ["brave-browser", "google-chrome", "chromium", "firefox"]:
        binario = shutil.which(visualizador)
        if binario:
            try:
                if visualizador in ["brave-browser", "google-chrome", "chromium"]:
                    subprocess.Popen([binario, f"--app={uri}"])
                else:
                    subprocess.Popen([binario, uri])
                return uri
            except Exception:
                pass

    # 2. Se estiver em modo 'sistema' (ou se o preferencial falhou), tenta navegadores preferenciais
    binario_navegador = encontrar_navegador_preferencial()
    if binario_navegador:
        nome_binario = os.path.basename(binario_navegador).lower()
        try:
            if any(c in nome_binario for c in ["brave", "chrome", "chromium"]):
                subprocess.Popen([binario_navegador, f"--app={uri}"])
            else:
                subprocess.Popen([binario_navegador, uri])
            return uri
        except Exception:
            pass

    # 3. Tentar a variável de ambiente $BROWSER
    env_browser = os.environ.get("BROWSER")
    if env_browser:
        binario_env = shutil.which(env_browser)
        if binario_env:
            try:
                subprocess.Popen([binario_env, uri])
                return uri
            except Exception:
                pass

    # 4. Tenta Evince ou Okular se estiverem instalados (apenas em modo sistema)
    if visualizador == "sistema":
        for viewer in ["evince", "okular"]:
            if shutil.which(viewer):
                try:
                    if viewer == "evince":
                        subprocess.Popen(["evince", "-p", str(page_number), path])
                    else:
                        subprocess.Popen(["okular", "-p", str(page_number), path])
                    return uri
                except Exception:
                    pass

    # 5. Fallback final usando xdg-open do Linux (apenas em modo sistema)
    if visualizador == "sistema" and shutil.which("xdg-open"):
        try:
            subprocess.Popen(["xdg-open", path])
            return uri
        except Exception:
            pass

    # 6. Fallback extremo: webbrowser
    webbrowser.open(uri)
    return uri

