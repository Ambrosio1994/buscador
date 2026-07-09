# Buscador Offline de Manuais em PDF

Ferramenta leve e totalmente offline para pesquisar rapidamente em uma pasta
local de manuais em PDF, feita para uso em Linux Mint em máquinas com pouca
RAM e pouco armazenamento (ex.: ambiente de prova/consulta com tempo
limitado).

## Stack

- **Python 3**
- **Tkinter** — interface gráfica
- **SQLite + FTS5** — índice de busca textual local
- **PyMuPDF (fitz)** — extração de texto dos PDFs

## Instalação (Linux Mint)

```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
pip install pymupdf --break-system-packages
```

## Como usar

```bash
python3 app.py
```

1. Clique em **"Selecionar pasta..."** e escolha a pasta com os manuais em PDF.
2. Clique em **"Indexar"**. Na primeira vez, todos os PDFs serão lidos e
   indexados. Nas próximas vezes, apenas arquivos novos, alterados ou
   removidos serão reprocessados.
3. Digite uma palavra-chave, frase ou pergunta no campo de busca e pressione
   Enter (ou clique em "Buscar").
4. Dê duplo clique em um resultado (ou selecione e clique em "Abrir PDF na
   página") para abrir o manual diretamente na página encontrada.

## Estrutura do projeto

```text
buscador_manuais/
├── app.py           # Interface gráfica (Tkinter)
├── database.py       # Schema e operações do SQLite
├── indexer.py         # Indexação incremental dos PDFs
├── search.py          # Normalização de consulta e busca FTS5
├── pdf_utils.py        # Extração de texto com PyMuPDF
├── opener.py            # Abertura do PDF na página correta
├── config.py             # Constantes e caminhos
├── tests/                 # Testes automatizados (unittest)
└── data/
    └── search_index.db     # Banco de índice (gerado automaticamente)
```

## Executando os testes

```bash
python3 -m unittest discover -s tests -v
```

35 testes cobrindo banco de dados, extração de PDF, indexação, busca e
abertura de arquivo.

## Limitações da primeira versão (MVP)

- PDFs escaneados como imagem (sem texto extraível) não são pesquisáveis —
  o sistema apenas avisa quando isso ocorre. OCR fica para uma versão futura.
- Não há destaque visual de sinônimos, correção ortográfica ou histórico de
  buscas nesta versão (ver seção "Melhorias futuras" na especificação
  original).

## Desempenho observado

Em teste de carga com 30 PDFs de 40 páginas (1.200 páginas no total):

- Indexação completa: ~0,3s
- Busca (qualquer consulta): 1,7ms a 2,6ms
- Reindexação sem alterações: instantânea

Bem dentro do critério de aceite de "busca em menos de 1 segundo".
