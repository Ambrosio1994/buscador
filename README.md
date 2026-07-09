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

1. Instale o Python, o gerenciador de pacotes, o Tkinter e suporte a ambientes virtuais do sistema operacional:
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-tk python3-venv
   ```

2. Crie um ambiente virtual na raiz do projeto:
   ```bash
   python3 -m venv .venv
   ```

3. Ative o ambiente virtual:
   ```bash
   source .venv/bin/activate
   ```

4. Instale as dependências necessárias do projeto:
   ```bash
   pip install -r requirements.txt
   ```

## Como usar

Com o ambiente virtual ativado, execute o sistema pela interface gráfica:
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

## Como usar o Executável (Release)

Se você preferir executar o programa sem instalar dependências do Python:
1. Baixe o executável `app` da aba **Releases** no GitHub.
2. Dê permissão de execução para o arquivo:
   ```bash
   chmod +x app
   ```
3. Execute o programa dando um duplo clique ou executando no terminal:
   ```bash
   ./app
   ```

## Segurança e Privacidade (100% Offline)

* **Sem conexão de rede:** O sistema é totalmente offline. Nenhuma informação, consulta textual ou documento em PDF é enviado para a internet.
* **Dependências locais:** Não há dependências que realizem chamadas externas.
* **Onde os dados ficam salvos:** Todos os dados gerados (banco de índice e histórico) ficam armazenados localmente na subpasta `data` do diretório do programa:
  * `data/search_index.db`: Banco de dados SQLite com os textos indexados e metadados.
  * `data/settings.json`: Configurações de preferência do usuário (ex: visualizador de PDF preferido).
  * `data/history.json`: Histórico local das pesquisas recentes.

## Recursos de Performance e Acurácia

O buscador possui algoritmos avançados integrados para garantir resultados de alto nível e velocidade extrema:
* **Pré-normalização na Indexação:** A limpeza de texto (diacríticos, acentos, pontuação, caixa baixa) é feita uma única vez na indexação e salva no banco na coluna `text_normalized`, dobrando a velocidade das buscas.
* **Corretor Ortográfico (Spellcheck) Offline:** Correção automática de erros de digitação baseada no vocabulário dos seus manuais indexados e busca por aproximação via `difflib`.
* **Fórmula de Score Ponderada:** Ordenação baseada em pesos calibrados: Cobertura de Termos (50%), relevância BM25 (35%) e Proximidade de Termos (15%).
* **Busca por Radical (Stemming):** Stemmer integrado para o português que mapeia plurais, gêneros e derivações de volta ao radical, rodando buscas exatas e por radical em paralelo para máxima revocação.
* **Filtros e Atalhos:** Filtre os resultados instantaneamente na tabela por pasta/categoria e use `Ctrl+F` para focar na busca e `Esc` para limpar.

## Executando os testes

```bash
python3 -m unittest discover -s tests -v
```

48 testes unitários e de integração cobrindo banco de dados, extração de PDF, indexação incremental com hashes SHA-256, modos de busca, filtros, histórico, corretor ortográfico, stemming e abertura de arquivos.

Para rodar os testes de performance, execute:
```bash
RUN_PERFORMANCE_TESTS=1 python tests/test_performance.py
```
