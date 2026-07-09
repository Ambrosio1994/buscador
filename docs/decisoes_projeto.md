# Decisões de Projeto e Arquitetura — Buscador de Manuais

Este documento registra as decisões de engenharia e escolhas arquiteturais tomadas durante a evolução do sistema de busca.

## 1. Coluna de Texto Pré-Normalizado (Implementado)
* **Decisão:** Adicionar a coluna `text_normalized` na tabela `pages` e popular via migração pontual e no fluxo de indexação.
* **Motivo:** O cálculo de normalização (remoção de acentos, pontuação, caixa baixa) estava sendo reprocessado em tempo de busca para cada página retornada no score de proximidade. Pré-calculando na indexação, o tempo de busca caiu pela metade (~4ms para ~2ms).

## 2. Spellcheck e Tolerância a Erros (Implementado)
* **Decisão:** Implementar a correção e tolerância a erros com uma tabela de vocabulário (`vocabulary`) populada a cada indexação e buscas fuzzy via `difflib.get_close_matches` em nível de aplicação (Python).
* **Motivo:** A extensão nativa do SQLite `spellfix1` não é compilada por padrão na distribuição padrão do Python/SQLite no Linux Mint. Exigir que o usuário compile ou instale extensões compartilhadas introduziria grande complexidade e risco de quebra. A solução em Python puro usa a biblioteca padrão (`difflib`), é 100% portátil, segura e executa em menos de 1ms devido ao tamanho controlado do vocabulário do acervo.

## 3. Ajuste de Pesos do Score (Implementado)
* **Decisão:** Substituir a ordenação hierárquica por uma fórmula ponderada de score onde os três sinais (Cobertura, BM25 e Proximidade) são normalizados na escala `[0, 1]`.
  * Cobertura de Termos: **50%**
  * BM25: **35%**
  * Proximidade de Termos (menor janela): **15%**
* **Motivo:** Evita a hierarquia rígida onde um termo a mais dominava tudo mesmo que o resto do documento fosse irrelevante. Com a fórmula ponderada, o ranking tornou-se muito mais equilibrado e calibrado.

## 4. NEAR Nativo do FTS5 vs. Janela Deslizante em Python (Decisão: Manter em Python)
* **Decisão:** Manter a proximidade sendo calculada via algoritmo de janela deslizante (*sliding window*) em Python, em vez de reescrever a query com o operador `NEAR` do FTS5.
* **Motivo:**
  1. **Preservação de Recall (Revocação):** O `NEAR` do FTS5 funciona como um filtro rígido: se os termos estiverem a uma distância maior que a especificada, a página é completamente descartada dos resultados. A lógica em Python calcula a janela e atribui uma nota menor, mas ainda exibe a página caso ela seja relevante por outros critérios (ex.: cobertura total de termos ou alto BM25).
  2. **Incompatibilidade com Modo Amplo (OR):** O operador `NEAR` exige que *todos* os seus termos internos estejam presentes. Em buscas OR (Modo Amplo), onde nem todos os termos são encontrados, a query `NEAR` falharia em trazer correspondências parciais.
  3. **Performance:** Como o cálculo em Python roda apenas sobre a lista de candidatos pré-filtrada pelo SQLite (que é pequena), ele é extremamente leve (executa em < 0.1ms por busca), não justificando a perda de recall provocada pelo `NEAR` do FTS5.
