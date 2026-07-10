"""
config.py

Configurações e constantes globais do sistema.
"""

import os
import shutil
import sys

# Diretório base do projeto (onde este arquivo ou o executável está localizado)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Diretório de dados gravável do usuário. BUSCADOR_DATA_DIR facilita instalações
# portáteis e testes; XDG_DATA_HOME segue o padrão dos desktops Linux.
DATA_DIR = os.path.abspath(
    os.environ.get(
        "BUSCADOR_DATA_DIR",
        os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "buscador-manuais",
        ),
    )
)

# Caminho do banco de dados SQLite
DATABASE_PATH = os.path.join(DATA_DIR, "search_index.db")

# Extensão de arquivo considerada válida para indexação
PDF_EXTENSION = ".pdf"

# Palavras irrelevantes (stopwords) ignoradas na busca
STOPWORDS = {
    "de", "da", "do", "das", "dos",
    "a", "o", "e", "para", "com", "em",
    "que", "qual", "quais", "quando", "onde",
}

# Número máximo de resultados retornados por busca
MAX_RESULTS = 20

# Número de palavras de contexto exibidas no trecho (snippet) de resultado
SNIPPET_CONTEXT_WORDS = 20

# Binários de navegadores preferenciais para abertura dos PDFs (ordem de preferência)
PREFERRED_BROWSERS = [
    "brave-browser",
    "brave",
    "google-chrome",
    "chrome",
    "chromium-browser",
    "chromium",
    "firefox",
]


def garantir_diretorio_dados() -> None:
    """Cria o diretório XDG e importa dados legados ao lado do aplicativo."""
    os.makedirs(DATA_DIR, exist_ok=True)
    diretorio_legado = os.path.join(BASE_DIR, "data")
    if os.path.abspath(diretorio_legado) == DATA_DIR or not os.path.isdir(diretorio_legado):
        return
    for nome in ("search_index.db", "settings.json", "history.json"):
        origem = os.path.join(diretorio_legado, nome)
        destino = os.path.join(DATA_DIR, nome)
        if os.path.isfile(origem) and not os.path.exists(destino):
            shutil.copy2(origem, destino)


SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def obter_setting(chave: str, padrao: str = "") -> str:
    """Obtém uma configuração do arquivo settings.json."""
    import json
    garantir_diretorio_dados()
    if not os.path.exists(SETTINGS_PATH):
        return padrao
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(chave, padrao)
    except Exception:
        return padrao


def salvar_setting(chave: str, valor: str) -> None:
    """Salva uma configuração no arquivo settings.json."""
    import json
    garantir_diretorio_dados()
    data = {}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data[chave] = valor
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


HISTORY_PATH = os.path.join(DATA_DIR, "history.json")


def obter_historico() -> list[str]:
    """Obtém o histórico de buscas do arquivo history.json."""
    import json
    garantir_diretorio_dados()
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def salvar_historico(historico: list[str]) -> None:
    """Salva o histórico de buscas no arquivo history.json."""
    import json
    garantir_diretorio_dados()
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=4)
    except Exception:
        pass
