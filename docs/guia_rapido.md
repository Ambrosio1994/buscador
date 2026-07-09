# Guia de Uso Rápido - Buscador Offline de Manuais

Este guia prático fornece instruções detalhadas para o uso eficiente do sistema de busca offline de manuais em PDF.

## 1. Selecionando a Pasta de Manuais
Ao abrir o programa pela primeira vez, você verá a mensagem "Nenhuma pasta selecionada".
1. Clique no botão **"Selecionar pasta..."** no canto superior direito.
2. Navegue pelos diretórios e escolha a pasta principal onde estão armazenados os seus manuais em PDF.
3. Clique em "Abrir" ou "OK". O caminho da pasta selecionada aparecerá na barra superior.

## 2. Indexando e Reindexando Manuais
A busca textual rápida é realizada consultando um banco de dados local (índice), sem ler os arquivos PDF em tempo real.
* **Indexação Inicial:** Na primeira vez que selecionar a pasta, clique no botão **"Indexar"** para processar os arquivos. Uma barra de progresso mostrará o andamento.
* **Reindexação (Incremental):** Se você adicionar novos manuais, atualizar ou excluir arquivos dentro da pasta (ou subpastas), basta clicar no botão **"Indexar"** (ou no menu **"Manutenção..." -> "Reindexar Pasta"**). O sistema lerá apenas os arquivos novos ou alterados (usando o hash SHA-256 para verificar mudanças reais no conteúdo).
* **Recriação do Zero:** Se quiser forçar a reindexação completa de todos os arquivos do zero, clique em **"Manutenção..." -> "Recriar Índice do Zero"**.

## 3. Modos de Busca
O buscador possui três estratégias de consulta na barra superior de opções:
1. **Modo Amplo (OR):** Ideal para explorações iniciais. Retorna páginas que contêm *qualquer um* dos termos pesquisados.
2. **Modo Preciso (AND):** Ideal para perguntas mais longas. Exige que *todos* os termos principais pesquisados estejam presentes na mesma página do PDF.
3. **Frase Exata:** Ideal para quando você copia um trecho exato de uma pergunta ou de um manual. O sistema buscará apenas as ocorrências das palavras na exata sequência digitada.

## 4. Exemplos de Buscas Eficientes
* **Termo Único:** `infraestrutura` (traz páginas com "infraestrutura" ou termos derivados como "infraestruturas").
* **Múltiplos Termos (Modo Preciso):** `operacoes defensivas finalidade` (traz páginas que contêm as três palavras em qualquer ordem).
* **Trecho Específico (Modo Frase Exata):** `"impedir acesso a infraestrutura critica"` (traz somente o trecho idêntico).

## 5. Como Interpretar os Resultados
Os resultados da busca são organizados em uma tabela com quatro colunas:
1. **Manual:** Exibe o caminho relativo do arquivo a partir da pasta selecionada, mostrando a subpasta onde está localizado.
2. **Página:** O número da página dentro do manual.
3. **Relevância:** Classificação visual em **Alta**, **Média** ou **Baixa**:
   * **Alta:** Todos os termos digitados foram encontrados na página (ou casou a frase exata).
   * **Média:** Mais da metade dos termos foram encontrados.
   * **Baixa:** Menos da metade dos termos foram encontrados.
4. **Trecho Encontrado:** Exibe o contexto do texto com os termos buscados em destaque entre colchetes (ex.: `...impedir acesso a [infraestrutura] critica...`).

Dando um **duplo clique** sobre a linha do resultado, o manual é aberto diretamente na página correta!

## 6. O que fazer quando nenhum resultado aparece
1. Verifique a ortografia das palavras pesquisadas.
2. Experimente alternar para o **Modo Amplo** se estiver usando o Modo Preciso ou Frase Exata.
3. Verifique se o termo de busca não é composto apenas por palavras muito genéricas (ex.: "qual a", "de um", "para o"), que são tratadas como *stopwords* e ignoradas.
4. Certifique-se de que a pasta de manuais correta está selecionada e devidamente indexada.

## 7. PDFs Sem Texto Pesquisável (Imagem / Escaneados)
Se um manual foi digitalizado como imagem (sem camada de texto OCR), ele não poderá ser pesquisado pelo sistema.
* Ao final da indexação, o sistema exibirá um aviso alertando se houver PDFs sem texto pesquisável.
* Você também pode conferir essa lista clicando no botão **"Diagnóstico..."**.

## 8. Resolução de Problemas
* **O PDF não abre ao clicar:**
  * Verifique se o arquivo não foi movido, renomeado ou deletado após a indexação. Nesse caso, clique em **"Indexar"** para atualizar o banco de dados.
  * Altere o visualizador de PDF na barra superior (opção **"Visualizador"**) para testar compatibilidade. Por padrão, ele usa o **Sistema** (xdg-open ou navegador), mas você pode forçar o uso de leitores dedicados como **Evince** ou **Okular** se estiverem instalados.
* **O programa travou durante a indexação:**
  * Se houver algum arquivo PDF corrompido, a indexação pulará este arquivo registrando o erro no relatório do botão **"Diagnóstico..."** e prosseguirá normalmente sem travar.
