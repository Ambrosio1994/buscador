#!/usr/bin/env bash
#
# install.sh
#
# Instala todas as dependências necessárias para rodar o Buscador Offline
# de Manuais em PDF. Detecta a distribuição Linux automaticamente
# (Arch/Manjaro ou Debian/Ubuntu/Mint) e usa o gerenciador de pacotes correto.
#
# Também detecta o caso comum de o comando 'python3' apontar para um Python
# instalado via Homebrew/Linuxbrew (que não tem o Tk do sistema vinculado)
# e usa o Python correto do sistema operacional nesse caso.
#
# Uso:
#   chmod +x install.sh
#   ./install.sh

set -e

echo "==> Detectando distribuição Linux..."

if command -v pacman >/dev/null 2>&1; then
    echo "==> Arch Linux / Manjaro detectado."
    sudo pacman -Sy --needed --noconfirm python python-pip tk
    PYTHON_SISTEMA="/usr/bin/python3"

elif command -v apt >/dev/null 2>&1; then
    echo "==> Debian / Ubuntu / Linux Mint detectado."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-tk
    PYTHON_SISTEMA="/usr/bin/python3"

else
    echo "!! Distribuição não reconhecida automaticamente."
    echo "!! Instale manualmente: Python 3, pip e a biblioteca Tk (tkinter) do seu sistema."
    exit 1
fi

# --- Detecta se o 'python3' do PATH aponta para Homebrew/Linuxbrew ---------
PYTHON_DO_PATH="$(command -v python3)"

if [[ "$PYTHON_DO_PATH" == *linuxbrew* || "$PYTHON_DO_PATH" == *homebrew* ]]; then
    echo "==> Aviso: o 'python3' do seu PATH aponta para o Homebrew/Linuxbrew:"
    echo "        $PYTHON_DO_PATH"
    echo "    Esse Python não tem o Tk do sistema vinculado (tkinter não funciona nele)."
    echo "    Usando o Python do sistema em '$PYTHON_SISTEMA' para este projeto."
    PYTHON_BIN="$PYTHON_SISTEMA"
else
    PYTHON_BIN="$PYTHON_DO_PATH"
fi

echo "==> Usando interpretador: $PYTHON_BIN"

echo "==> Verificando se o tkinter está funcionando..."
if ! "$PYTHON_BIN" -c "import tkinter; print('tkinter OK')"; then
    echo "!! O tkinter ainda não está disponível em $PYTHON_BIN."
    echo "!! Verifique se o pacote 'tk' (Arch) ou 'python3-tk' (Debian/Mint) foi instalado corretamente."
    exit 1
fi

echo "==> Instalando PyMuPDF (biblioteca Python para leitura de PDFs)..."
"$PYTHON_BIN" -m pip install pymupdf --break-system-packages

echo ""
echo "==> Instalação concluída com sucesso!"
echo "==> Para rodar o programa, use:"
echo "       $PYTHON_BIN app.py"

if [[ "$PYTHON_BIN" != "$PYTHON_DO_PATH" ]]; then
    echo ""
    echo "==> Atenção: NÃO use apenas 'python3 app.py', pois o 'python3' do seu"
    echo "    terminal aponta para o Homebrew e vai falhar com o mesmo erro de tkinter."
    echo "    Use sempre o comando completo acima."
fi
