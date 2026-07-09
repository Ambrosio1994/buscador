import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import search


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.conn = database.conectar(":memory:")
        database.criar_banco(self.conn)

        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 100, 1.0, 3, 2.0
        )
        database.inserir_pagina(
            self.conn,
            doc_id,
            1,
            "Manual de Operacoes Defensivas. Finalidade: impedir acesso a infraestrutura critica.",
        )
        database.inserir_pagina(
            self.conn,
            doc_id,
            2,
            "Procedimentos administrativos de compra e patrimonio.",
        )
        database.inserir_pagina(
            self.conn,
            doc_id,
            3,
            "As operações ofensivas seguem outra finalidade tática.",
        )

    def tearDown(self):
        self.conn.close()

    def test_busca_por_palavra_exata(self):
        resultados = search.buscar(self.conn, "infraestrutura")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["page_number"], 1)

    def test_busca_por_varias_palavras(self):
        resultados = search.buscar(self.conn, "operacoes finalidade")
        paginas_encontradas = {r["page_number"] for r in resultados}
        self.assertIn(1, paginas_encontradas)
        self.assertIn(3, paginas_encontradas)

    def test_busca_por_pergunta_completa(self):
        resultados = search.buscar(self.conn, "Qual a finalidade das operações defensivas?")
        self.assertTrue(len(resultados) >= 1)
        self.assertEqual(resultados[0]["page_number"], 1)

    def test_busca_com_acentos(self):
        resultados = search.buscar(self.conn, "operações")
        self.assertTrue(len(resultados) >= 1)

    def test_busca_sem_acentos(self):
        resultados = search.buscar(self.conn, "operacoes")
        self.assertTrue(len(resultados) >= 1)

    def test_busca_sem_resultados(self):
        resultados = search.buscar(self.conn, "termo_que_nao_existe_em_lugar_nenhum")
        self.assertEqual(resultados, [])

    def test_busca_vazia_nao_quebra(self):
        self.assertEqual(search.buscar(self.conn, ""), [])
        self.assertEqual(search.buscar(self.conn, "   "), [])

    def test_busca_apenas_com_stopwords_nao_quebra(self):
        self.assertEqual(search.buscar(self.conn, "de da do que qual"), [])

    def test_ordenacao_dos_resultados_por_relevancia(self):
        resultados = search.buscar(self.conn, "operacoes finalidade defensivas")
        # A página 1 contém mais termos da consulta do que a página 3,
        # então deve aparecer primeiro (score BM25 menor = mais relevante).
        self.assertEqual(resultados[0]["page_number"], 1)

    def test_limite_de_resultados(self):
        resultados = search.buscar(self.conn, "operacoes", limite=1)
        self.assertEqual(len(resultados), 1)

    def test_busca_modo_amplo_vs_preciso(self):
        # Modo amplo (OR) deve retornar as páginas 1 e 3 para a query "operacoes defensivas"
        resultados_amplo = search.buscar(self.conn, "operacoes defensivas", modo="amplo")
        paginas_amplo = {r["page_number"] for r in resultados_amplo}
        self.assertIn(1, paginas_amplo)
        self.assertIn(3, paginas_amplo)

        # Modo preciso (AND) deve retornar apenas a página 1 (que contém ambas as palavras)
        resultados_preciso = search.buscar(self.conn, "operacoes defensivas", modo="preciso")
        paginas_preciso = {r["page_number"] for r in resultados_preciso}
        self.assertIn(1, paginas_preciso)
        self.assertNotIn(3, paginas_preciso)

    def test_busca_modo_frase_exata(self):
        # "operacoes defensivas" deve casar a página 1 pois a frase exata existe lá
        resultados = search.buscar(self.conn, "operacoes defensivas", modo="frase")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["page_number"], 1)

        # "defensivas operacoes" não deve casar nenhuma página no modo frase
        resultados_invertido = search.buscar(self.conn, "defensivas operacoes", modo="frase")
        self.assertEqual(resultados_invertido, [])

        # Mas no modo preciso (AND), a ordem não importa e deve casar a página 1
        resultados_preciso = search.buscar(self.conn, "defensivas operacoes", modo="preciso")
        self.assertEqual(len(resultados_preciso), 1)
        self.assertEqual(resultados_preciso[0]["page_number"], 1)

    def test_classificacao_relevancia(self):
        resultados = search.buscar(self.conn, "operacoes defensivas", modo="amplo")
        # Deve ter a página 1 (2/2 termos = Alta) e a página 3 (1/2 termos = Baixa)
        relevancias = {r["page_number"]: r["relevance_label"] for r in resultados}
        self.assertEqual(relevancias[1], "Alta")
        self.assertEqual(relevancias[3], "Baixa")


class TestNormalizacaoDeConsulta(unittest.TestCase):
    def test_normalizar_consulta(self):
        self.assertEqual(
            search.normalizar_consulta("  Operações  Defensivas!!  "),
            "operacoes defensivas",
        )

    def test_remover_palavras_irrelevantes(self):
        consulta = search.normalizar_consulta("qual a finalidade das operacoes defensivas")
        termos = search.remover_palavras_irrelevantes(consulta)
        self.assertEqual(termos, ["finalidade", "operacoes", "defensivas"])


if __name__ == "__main__":
    unittest.main()
