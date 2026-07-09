import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import opener


class TestOpener(unittest.TestCase):
    def setUp(self):
        self.arquivo_temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self.arquivo_temp.close()

    def tearDown(self):
        if os.path.exists(self.arquivo_temp.name):
            os.remove(self.arquivo_temp.name)

    def test_geracao_correta_da_uri_file(self):
        uri = opener.construir_uri_pdf(self.arquivo_temp.name, 1)
        self.assertTrue(uri.startswith("file://"))
        self.assertIn(os.path.basename(self.arquivo_temp.name), uri)

    def test_inclusao_correta_do_fragmento_pagina(self):
        uri = opener.construir_uri_pdf(self.arquivo_temp.name, 43)
        self.assertTrue(uri.endswith("#page=43"))

    def test_inclusao_de_termos_busca(self):
        uri = opener.construir_uri_pdf(self.arquivo_temp.name, 43, "operacoes defensivas")
        self.assertTrue(uri.endswith("#page=43&search=operacoes%20defensivas"))

    def test_tratamento_de_arquivo_inexistente(self):
        with self.assertRaises(opener.ArquivoNaoEncontradoError):
            opener.open_pdf_at_page("/caminho/que/nao/existe.pdf", 1)

    @patch("opener.encontrar_navegador_preferencial")
    @patch("subprocess.Popen")
    def test_open_pdf_at_page_chama_navegador_preferencial_com_app(self, mock_popen, mock_find):
        mock_find.return_value = "/usr/bin/brave-browser"

        uri_retornada = opener.open_pdf_at_page(self.arquivo_temp.name, 5)

        mock_popen.assert_called_once_with(["/usr/bin/brave-browser", f"--app={uri_retornada}"])
        self.assertIn("#page=5", uri_retornada)

    @patch("opener.encontrar_navegador_preferencial")
    @patch("shutil.which")
    @patch("subprocess.Popen")
    @patch.dict("os.environ", {"BROWSER": "firefox"})
    def test_open_pdf_at_page_chama_browser_env(self, mock_popen, mock_which, mock_find):
        mock_find.return_value = None
        mock_which.return_value = "/usr/bin/firefox"

        uri_retornada = opener.open_pdf_at_page(self.arquivo_temp.name, 5)

        mock_popen.assert_called_once_with(["/usr/bin/firefox", uri_retornada])
        self.assertIn("#page=5", uri_retornada)

    @patch("opener.encontrar_navegador_preferencial")
    @patch("opener.webbrowser.open")
    @patch.dict("os.environ", {}, clear=True)
    def test_open_pdf_at_page_fallback_webbrowser(self, mock_webbrowser_open, mock_find):
        mock_find.return_value = None

        uri_retornada = opener.open_pdf_at_page(self.arquivo_temp.name, 5)

        mock_webbrowser_open.assert_called_once_with(uri_retornada)
        self.assertIn("#page=5", uri_retornada)


if __name__ == "__main__":
    unittest.main()
