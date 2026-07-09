import csv
import datetime
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import indexer
import search

# =====================================================================
# CONFIGURAÇÕES E LIMITES DE PERFORMANCE (Critérios de Aceite)
# =====================================================================
# Limites em segundos
LIMITE_INDEXACAO_INICIAL_SEG = 5.0      # 30 PDFs (1200 páginas) em até 5 segundos
LIMITE_REINDEXACAO_INCREMENTAL_SEG = 0.5  # Reindexação sem alterações em até 0.5 segundos
LIMITE_BUSCA_MS = 100.0                 # Buscas complexas em menos de 100ms
LIMITE_ESCALA_SEG = 10.0                # 60 PDFs (2400 páginas) em até 10 segundos


class TestPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Evita execução acidental durante "unittest discover"
        if not os.environ.get("RUN_PERFORMANCE_TESTS"):
            raise unittest.SkipTest(
                "Testes de performance ignorados. Execute diretamente via python3 tests/test_performance.py"
            )

    def setUp(self):
        # Diretorio temporário para os PDFs sintéticos
        self.diretorio_temp = tempfile.mkdtemp()
        
        # Banco de dados temporário em arquivo real para testar I/O físico (WAL, synchronous etc.)
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.conn = database.conectar(self.db_path)
        database.criar_banco(self.conn)

    def tearDown(self):
        self.conn.close()
        # Fecha fd e remove banco temporário
        try:
            os.close(self.db_fd)
        except OSError:
            pass
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        # Limpa arquivos de log/WAL associados ao banco temporário se houver
        for ext in ["-wal", "-shm"]:
            caminho_extra = self.db_path + ext
            if os.path.exists(caminho_extra):
                os.remove(caminho_extra)

        # Remove pasta de PDFs
        shutil.rmtree(self.diretorio_temp, ignore_errors=True)

    def _gerar_pdfs_sinteticos(self, count: int, paginas: int) -> None:
        """Gera PDFs sintéticos com texto simulando conteúdo real."""
        import fitz
        for i in range(count):
            caminho = os.path.join(self.diretorio_temp, f"manual_sintetico_{i}.pdf")
            doc = fitz.open()
            for p in range(paginas):
                page = doc.new_page()
                texto = (
                    f"Pagina {p + 1} do manual sintetico de teste numero {i}.\n"
                    "Este documento contem instrucoes sobre operacoes defensivas de sistemas.\n"
                    "A infraestrutura critica deve ser protegida de forma robusta e persistente."
                )
                page.insert_text((72, 72), texto)
            doc.save(caminho)
            doc.close()

    def _salvar_resultado(self, teste_nome: str, valor: float) -> None:
        """Salva a medição em um arquivo CSV para acompanhamento histórico."""
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "performance_results.csv")
        headers = ["timestamp", "teste_nome", "valor"]
        exists = os.path.exists(csv_path)
        
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(headers)
            writer.writerow([datetime.datetime.now().isoformat(), teste_nome, valor])

    def test_performance_indexacao_inicial(self):
        """Mede o tempo da indexação inicial de 30 PDFs com 40 páginas cada (1.200 páginas)."""
        print("\n[Gerando 30 PDFs sintéticos com 40 páginas cada...]")
        self._gerar_pdfs_sinteticos(30, 40)

        t_inicio = time.perf_counter()
        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)
        t_fim = time.perf_counter()
        
        tempo_total = t_fim - t_inicio
        print(f" -> Indexação Inicial (1200 págs): {tempo_total:.4f}s (Novos: {len(resultado.novos)})")
        self._salvar_resultado("indexacao_inicial_1200_pags", tempo_total)
        
        self.assertLess(tempo_total, LIMITE_INDEXACAO_INICIAL_SEG, "Indexação inicial superou o tempo limite.")

    def test_performance_reindexacao_incremental(self):
        """Mede o tempo de reindexação incremental quando nenhum arquivo mudou."""
        self._gerar_pdfs_sinteticos(30, 40)
        # Primeira indexação
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        t_inicio = time.perf_counter()
        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)
        t_fim = time.perf_counter()

        tempo_total = t_fim - t_inicio
        print(f" -> Reindexação Incremental (sem alterações): {tempo_total:.4f}s (Inalterados: {len(resultado.inalterados)})")
        self._salvar_resultado("reindexacao_incremental", tempo_total)

        self.assertLess(tempo_total, LIMITE_REINDEXACAO_INCREMENTAL_SEG, "Reindexação incremental superou o tempo limite.")

    def test_performance_busca(self):
        """Mede o tempo de execução de diferentes tipos de consultas FTS5."""
        self._gerar_pdfs_sinteticos(30, 40)
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        consultas = [
            ("infraestrutura", "termo_unico"),
            ("operacoes defensivas", "frase_completa"),
            ("Qual a finalidade das operacoes defensivas?", "pergunta_com_stopwords")
        ]

        for query, desc in consultas:
            t_inicio = time.perf_counter()
            resultados = search.buscar(self.conn, query)
            t_fim = time.perf_counter()

            tempo_ms = (t_fim - t_inicio) * 1000.0
            print(f" -> Busca ({desc} - '{query}'): {tempo_ms:.2f}ms (Encontrados: {len(resultados)})")
            self._salvar_resultado(f"busca_{desc}", tempo_ms)
            
            self.assertLess(tempo_ms, LIMITE_BUSCA_MS, f"Busca '{query}' superou o tempo limite de {LIMITE_BUSCA_MS}ms.")

    def test_performance_escala_dobro(self):
        """Mede o tempo de escala indexando o dobro do volume esperado (60 PDFs com 40 páginas cada = 2.400 páginas)."""
        print("\n[Gerando 60 PDFs sintéticos com 40 páginas cada (Escala)...]")
        self._gerar_pdfs_sinteticos(60, 40)

        t_inicio = time.perf_counter()
        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)
        t_fim = time.perf_counter()

        tempo_total = t_fim - t_inicio
        print(f" -> Indexação de Escala (2400 págs): {tempo_total:.4f}s (Novos: {len(resultado.novos)})")
        self._salvar_resultado("indexacao_escala_2400_pags", tempo_total)

        self.assertLess(tempo_total, LIMITE_ESCALA_SEG, "Indexação de escala superou o tempo limite.")


if __name__ == "__main__":
    # Define a flag de ambiente para habilitar a execução ao chamar o arquivo diretamente
    os.environ["RUN_PERFORMANCE_TESTS"] = "1"
    unittest.main()
