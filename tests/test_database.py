import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db_path = ":memory:"
        self.conn = database.conectar(self.db_path)

    def tearDown(self):
        self.conn.close()

    def test_criacao_do_banco(self):
        database.criar_banco(self.conn)
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'index');"
        )
        nomes = {row["name"] for row in cursor.fetchall()}
        self.assertIn("documents", nomes)
        self.assertIn("pages", nomes)

    def test_criacao_das_tabelas_idempotente(self):
        database.criar_banco(self.conn)
        database.criar_banco(self.conn)  # não deve levantar erro na segunda chamada

    def test_insercao_de_documento(self):
        database.criar_banco(self.conn)
        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 1024, 111.0, 5, 222.0
        )
        self.assertIsInstance(doc_id, int)
        registro = database.buscar_documento_por_path(self.conn, "/tmp/manual.pdf")
        self.assertEqual(registro["filename"], "manual.pdf")
        self.assertEqual(registro["total_pages"], 5)

    def test_insercao_de_paginas(self):
        database.criar_banco(self.conn)
        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 1024, 111.0, 2, 222.0
        )
        database.inserir_pagina(self.conn, doc_id, 1, "texto da pagina um")
        database.inserir_pagina(self.conn, doc_id, 2, "texto da pagina dois")
        self.assertEqual(database.contar_paginas(self.conn), 2)

    def test_insercao_de_paginas_lote(self):
        database.criar_banco(self.conn)
        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 1024, 111.0, 2, 222.0
        )
        paginas = [
            (doc_id, 1, "texto da pagina um lote"),
            (doc_id, 2, "texto da pagina dois lote")
        ]
        database.inserir_paginas_lote(self.conn, paginas)
        self.assertEqual(database.contar_paginas(self.conn), 2)

    def test_remocao_de_documento(self):
        database.criar_banco(self.conn)
        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 1024, 111.0, 1, 222.0
        )
        database.inserir_pagina(self.conn, doc_id, 1, "conteudo qualquer")

        database.remover_documento(self.conn, doc_id)

        self.assertEqual(database.contar_documentos(self.conn), 0)
        self.assertEqual(database.contar_paginas(self.conn), 0)

    def test_contagem_de_documentos_e_paginas(self):
        database.criar_banco(self.conn)
        self.assertEqual(database.contar_documentos(self.conn), 0)
        self.assertEqual(database.contar_paginas(self.conn), 0)

        doc_id_1 = database.inserir_documento(
            self.conn, "a.pdf", "/tmp/a.pdf", 10, 1.0, 1, 2.0
        )
        doc_id_2 = database.inserir_documento(
            self.conn, "b.pdf", "/tmp/b.pdf", 20, 3.0, 1, 4.0
        )
        database.inserir_pagina(self.conn, doc_id_1, 1, "conteudo a")
        database.inserir_pagina(self.conn, doc_id_2, 1, "conteudo b")

        self.assertEqual(database.contar_documentos(self.conn), 2)
        self.assertEqual(database.contar_paginas(self.conn), 2)

    def test_limpeza_completa_do_banco(self):
        database.criar_banco(self.conn)
        doc_id = database.inserir_documento(
            self.conn, "manual.pdf", "/tmp/manual.pdf", 1024, 111.0, 1, 222.0
        )
        database.inserir_pagina(self.conn, doc_id, 1, "conteudo qualquer")
        self.assertEqual(database.contar_documentos(self.conn), 1)
        self.assertEqual(database.contar_paginas(self.conn), 1)

        # Deleta todos os documentos
        self.conn.execute("DELETE FROM documents;")
        self.conn.commit()

        # Verifica se cascade removeu as paginas e o indice FTS5
        self.assertEqual(database.contar_documentos(self.conn), 0)
        self.assertEqual(database.contar_paginas(self.conn), 0)

    def test_migracao_faz_backfill_e_reconstroi_fts_stemmed(self):
        self.conn.execute(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, "
            "path TEXT NOT NULL UNIQUE, file_size INTEGER NOT NULL, modified_at REAL NOT NULL, "
            "total_pages INTEGER, indexed_at REAL NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE pages (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, "
            "page_number INTEGER NOT NULL, text TEXT NOT NULL)"
        )
        self.conn.execute(
            "INSERT INTO documents VALUES (1, 'manual.pdf', '/tmp/manual.pdf', 1, 1, 1, 1)"
        )
        self.conn.execute("INSERT INTO pages VALUES (1, 1, 1, 'Manuais técnicos')")

        database.criar_banco(self.conn)

        row = self.conn.execute(
            "SELECT text_normalized, text_stemmed FROM pages WHERE id = 1"
        ).fetchone()
        self.assertEqual(row["text_normalized"], "manuais tecnicos")
        self.assertTrue(row["text_stemmed"])
        total = self.conn.execute(
            "SELECT COUNT(*) AS total FROM pages_stemmed_fts WHERE pages_stemmed_fts MATCH 'manu*'"
        ).fetchone()["total"]
        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
