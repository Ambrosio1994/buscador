import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz  # PyMuPDF
import pdf_utils


class TestPdfUtils(unittest.TestCase):
    def setUp(self):
        self.diretorio_temp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.diretorio_temp, ignore_errors=True)

    def _criar_pdf_com_texto(self, nome="teste.pdf", paginas_com_texto=("Ola mundo",)):
        caminho = os.path.join(self.diretorio_temp, nome)
        doc = fitz.open()
        for texto in paginas_com_texto:
            pagina = doc.new_page()
            if texto:
                pagina.insert_text((72, 72), texto)
        doc.save(caminho)
        doc.close()
        return caminho

    def _criar_pdf_corrompido(self, nome="corrompido.pdf"):
        caminho = os.path.join(self.diretorio_temp, nome)
        with open(caminho, "wb") as f:
            f.write(b"isto nao e um PDF valido")
        return caminho

    def test_pdf_com_texto_extraivel(self):
        caminho = self._criar_pdf_com_texto(paginas_com_texto=("Manual de operacoes",))
        paginas = pdf_utils.extrair_texto_pdf(caminho)
        self.assertEqual(len(paginas), 1)
        self.assertIn("Manual de operacoes", paginas[0]["text"])
        self.assertTrue(pdf_utils.pdf_possui_texto_extraivel(paginas))

    def test_pdf_com_pagina_vazia(self):
        caminho = self._criar_pdf_com_texto(
            paginas_com_texto=("Texto normal", "", "Outro texto")
        )
        paginas = pdf_utils.extrair_texto_pdf(caminho)
        self.assertEqual(len(paginas), 3)
        self.assertEqual(paginas[1]["text"], "")
        # Mesmo com uma página vazia, o restante é extraído normalmente.
        self.assertTrue(pdf_utils.pdf_possui_texto_extraivel(paginas))

    def test_pdf_totalmente_sem_texto(self):
        caminho = self._criar_pdf_com_texto(paginas_com_texto=("", ""))
        paginas = pdf_utils.extrair_texto_pdf(caminho)
        self.assertFalse(pdf_utils.pdf_possui_texto_extraivel(paginas))

    def test_pdf_inexistente(self):
        caminho_inexistente = os.path.join(self.diretorio_temp, "nao_existe.pdf")
        with self.assertRaises(pdf_utils.PDFInvalidoError):
            pdf_utils.extrair_texto_pdf(caminho_inexistente)

    def test_pdf_corrompido(self):
        caminho = self._criar_pdf_corrompido()
        with self.assertRaises(pdf_utils.PDFInvalidoError):
            pdf_utils.extrair_texto_pdf(caminho)

    def _criar_pdf_protegido(self, nome="protegido.pdf"):
        caminho = os.path.join(self.diretorio_temp, nome)
        doc = fitz.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "Texto secreto")
        doc.save(caminho, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="123", owner_pw="123")
        doc.close()
        return caminho

    def test_pdf_protegido_por_senha(self):
        caminho = self._criar_pdf_protegido()
        with self.assertRaises(pdf_utils.PDFInvalidoError):
            pdf_utils.extrair_texto_pdf(caminho)

    def test_contagem_correta_de_paginas(self):
        caminho = self._criar_pdf_com_texto(
            paginas_com_texto=("p1", "p2", "p3", "p4")
        )
        self.assertEqual(pdf_utils.contar_paginas_pdf(caminho), 4)


if __name__ == "__main__":
    unittest.main()
