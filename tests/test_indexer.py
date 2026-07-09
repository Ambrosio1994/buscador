import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz  # PyMuPDF

import database
import indexer


class TestIndexer(unittest.TestCase):
    def setUp(self):
        self.diretorio_temp = tempfile.mkdtemp()
        self.conn = database.conectar(":memory:")
        database.criar_banco(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.diretorio_temp, ignore_errors=True)

    def _criar_pdf(self, nome, texto="Conteudo de teste"):
        caminho = os.path.join(self.diretorio_temp, nome)
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), texto)
        doc.save(caminho)
        doc.close()
        return caminho

    def test_indexar_pasta_com_pdfs(self):
        self._criar_pdf("manual1.pdf", "Texto do manual um")
        self._criar_pdf("manual2.pdf", "Texto do manual dois")

        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        self.assertEqual(len(resultado.novos), 2)
        self.assertEqual(database.contar_documentos(self.conn), 2)

    def test_nao_reindexar_arquivo_igual(self):
        self._criar_pdf("manual1.pdf")
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        self.assertEqual(resultado.novos, [])
        self.assertEqual(resultado.atualizados, [])
        self.assertIn("manual1.pdf", resultado.inalterados)

    def test_reindexar_arquivo_alterado(self):
        caminho = self._criar_pdf("manual1.pdf", "Texto original")
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        time.sleep(0.05)
        # Recria o arquivo com conteúdo e data de modificação diferentes.
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "Texto atualizado e maior que o original")
        doc.save(caminho)
        doc.close()
        os.utime(caminho, None)

        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        self.assertIn("manual1.pdf", resultado.atualizados)

    def test_nao_reindexar_se_conteudo_igual_mas_data_diferente(self):
        caminho = self._criar_pdf("manual1.pdf", "Mesmo conteudo")
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        # Guarda registro original
        reg_original = database.buscar_documento_por_path(self.conn, caminho)
        self.assertIsNotNone(reg_original)

        time.sleep(0.05)
        # Toca no arquivo (muda apenas a data de modificação)
        os.utime(caminho, None)
        stat = os.stat(caminho)
        self.assertNotEqual(reg_original["modified_at"], stat.st_mtime)

        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        # Deve marcar como inalterados (mesmo hash sha256)
        self.assertIn("manual1.pdf", resultado.inalterados)
        self.assertNotIn("manual1.pdf", resultado.atualizados)

        # E os metadados no banco devem ter sido atualizados com a nova data
        reg_novo = database.buscar_documento_por_path(self.conn, caminho)
        self.assertAlmostEqual(reg_novo["modified_at"], stat.st_mtime, places=4)

    def test_remover_do_indice_pdf_apagado(self):
        caminho = self._criar_pdf("manual1.pdf")
        indexer.indexar_pasta(self.conn, self.diretorio_temp)

        os.remove(caminho)
        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        self.assertIn("manual1.pdf", resultado.removidos)
        self.assertEqual(database.contar_documentos(self.conn), 0)

    def test_lidar_com_pasta_vazia(self):
        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)
        self.assertEqual(resultado.novos, [])
        self.assertEqual(database.contar_documentos(self.conn), 0)

    def test_lidar_com_arquivo_que_nao_e_pdf(self):
        caminho_txt = os.path.join(self.diretorio_temp, "leia_me.txt")
        with open(caminho_txt, "w") as f:
            f.write("isto nao e um pdf")

        resultado = indexer.indexar_pasta(self.conn, self.diretorio_temp)

        self.assertEqual(resultado.novos, [])
        self.assertEqual(database.contar_documentos(self.conn), 0)

    def test_lidar_com_pasta_inexistente(self):
        resultado = indexer.indexar_pasta(self.conn, "/caminho/que/nao/existe")
        self.assertEqual(resultado.novos, [])
        self.assertEqual(resultado.erros, [])


if __name__ == "__main__":
    unittest.main()
