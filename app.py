"""
app.py

Interface gráfica (Tkinter) do Buscador Offline de Manuais em PDF.

Permite:
- selecionar a pasta local de manuais em PDF;
- disparar a indexação (inicial ou incremental) pela interface;
- digitar buscas (palavras-chave, frases ou perguntas);
- visualizar resultados com manual, página, trecho e relevância;
- abrir o PDF na página correta com um clique/duplo clique.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import database
import indexer
import opener
import search
from config import DATABASE_PATH


class BuscadorApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Buscador Offline de Manuais em PDF")
        self.geometry("900x600")
        self.minsize(700, 450)

        # Configura o ícone da janela (favicon)
        try:
            import sys
            if getattr(sys, "frozen", False):
                diretorio_base = sys._MEIPASS
            else:
                diretorio_base = os.path.dirname(os.path.abspath(__file__))
            caminho_icone = os.path.join(diretorio_base, "simbolo_easa.png")
            if os.path.exists(caminho_icone):
                self.icon_img = tk.PhotoImage(file=caminho_icone)
                self.iconphoto(False, self.icon_img)
        except Exception:
            pass

        self.pasta_selecionada: str | None = None
        self.resultados_atuais: list[search.ResultadoBusca] = []

        self._construir_interface()
        self._configurar_banco()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------

    def _construir_interface(self) -> None:
        # --- Barra superior: seleção de pasta e indexação ---
        frame_topo = ttk.Frame(self, padding=10)
        frame_topo.pack(fill=tk.X)

        self.label_pasta = ttk.Label(
            frame_topo, text="Nenhuma pasta selecionada", foreground="gray"
        )
        self.label_pasta.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            frame_topo, text="Selecionar pasta...", command=self._selecionar_pasta
        ).pack(side=tk.RIGHT, padx=(5, 0))

        self.botao_indexar = ttk.Button(
            frame_topo, text="Indexar", command=self._indexar_em_thread, state=tk.DISABLED
        )
        self.botao_indexar.pack(side=tk.RIGHT)

        # --- Barra de busca ---
        frame_busca = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame_busca.pack(fill=tk.X)

        self.entrada_busca = ttk.Entry(frame_busca, font=("TkDefaultFont", 12))
        self.entrada_busca.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entrada_busca.bind("<Return>", lambda evento: self._executar_busca())

        ttk.Button(frame_busca, text="Buscar", command=self._executar_busca).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # --- Lista de resultados ---
        frame_resultados = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame_resultados.pack(fill=tk.BOTH, expand=True)

        colunas = ("manual", "pagina", "trecho")
        self.tabela = ttk.Treeview(
            frame_resultados, columns=colunas, show="headings", selectmode="browse"
        )
        self.tabela.heading("manual", text="Manual")
        self.tabela.heading("pagina", text="Página")
        self.tabela.heading("trecho", text="Trecho encontrado")
        self.tabela.column("manual", width=200, anchor=tk.W)
        self.tabela.column("pagina", width=70, anchor=tk.CENTER)
        self.tabela.column("trecho", width=550, anchor=tk.W)

        scrollbar = ttk.Scrollbar(
            frame_resultados, orient=tk.VERTICAL, command=self.tabela.yview
        )
        self.tabela.configure(yscrollcommand=scrollbar.set)

        self.tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tabela.bind("<Double-1>", lambda evento: self._abrir_resultado_selecionado())

        ttk.Button(
            self, text="Abrir PDF na página", command=self._abrir_resultado_selecionado
        ).pack(pady=(0, 5))

        # --- Barra de status ---
        self.status_var = tk.StringVar(value="Selecione uma pasta de manuais para começar.")
        barra_status = ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5
        )
        barra_status.pack(fill=tk.X, side=tk.BOTTOM)

        # --- Barra de progresso (oculta por padrão, posicionada acima da barra de status) ---
        self.progresso = ttk.Progressbar(self, orient=tk.HORIZONTAL, mode="determinate")

    def _configurar_banco(self) -> None:
        with database.get_connection(DATABASE_PATH) as conn:
            database.criar_banco(conn)

    # ------------------------------------------------------------------
    # Ações da interface
    # ------------------------------------------------------------------

    def _selecionar_pasta(self) -> None:
        pasta = filedialog.askdirectory(title="Selecione a pasta com os manuais em PDF")
        if not pasta:
            return

        self.pasta_selecionada = pasta
        self.label_pasta.config(text=pasta, foreground="black")
        self.botao_indexar.config(state=tk.NORMAL)
        self.status_var.set("Pasta selecionada. Clique em 'Indexar' para atualizar o índice.")

    def _indexar_em_thread(self) -> None:
        """Executa a indexação em uma thread separada para não travar a interface."""
        if not self.pasta_selecionada:
            return

        self.botao_indexar.config(state=tk.DISABLED)
        self.status_var.set("Iniciando indexação dos manuais...")

        # Exibe a barra de progresso
        self.progresso.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 5))
        self.progresso["value"] = 0

        thread = threading.Thread(target=self._indexar, daemon=True)
        thread.start()

    def _indexar(self) -> None:
        try:
            with database.get_connection(DATABASE_PATH) as conn:
                resultado = indexer.indexar_pasta(
                    conn, self.pasta_selecionada, callback_progresso=self._atualizar_progresso
                )
            self.after(0, self._indexacao_concluida, resultado)
        except Exception as exc:
            self.after(0, self._indexacao_falhou, str(exc))

    def _atualizar_progresso(self, atual: int, total: int, nome_arquivo: str) -> None:
        """Recebe notificações de progresso da thread de indexação."""
        self.after(0, self._definir_progresso, atual, total, nome_arquivo)

    def _definir_progresso(self, atual: int, total: int, nome_arquivo: str) -> None:
        """Atualiza a barra de progresso e o status da interface na thread principal."""
        percentual = (atual / total) * 100 if total > 0 else 0
        self.progresso["value"] = percentual
        self.status_var.set(f"Indexando [{atual}/{total}]: {nome_arquivo}...")

    def _indexacao_concluida(self, resultado: indexer.ResultadoIndexacao) -> None:
        self.botao_indexar.config(state=tk.NORMAL)
        self.progresso.pack_forget()

        partes = []
        if resultado.novos:
            partes.append(f"{len(resultado.novos)} novo(s)")
        if resultado.atualizados:
            partes.append(f"{len(resultado.atualizados)} atualizado(s)")
        if resultado.removidos:
            partes.append(f"{len(resultado.removidos)} removido(s)")
        if not partes:
            partes.append("nenhuma alteração")

        mensagem = (
            f"Indexação concluída em {resultado.tempo_execucao:.2f}s ({', '.join(partes)}). "
            f"Total indexado: {resultado.total_documentos} manual(ais) e {resultado.total_paginas} página(s)."
        )
        self.status_var.set(mensagem)

        if resultado.sem_texto_extraivel:
            nomes = ", ".join(resultado.sem_texto_extraivel)
            messagebox.showwarning(
                "PDFs sem texto extraível",
                f"Os seguintes arquivos não possuem texto extraível "
                f"(talvez sejam PDFs escaneados):\n\n{nomes}",
            )

        if resultado.erros:
            nomes = "\n".join(resultado.erros)
            messagebox.showerror(
                "Erros durante a indexação",
                f"Alguns arquivos não puderam ser processados:\n\n{nomes}",
            )

    def _indexacao_falhou(self, mensagem_erro: str) -> None:
        self.botao_indexar.config(state=tk.NORMAL)
        self.progresso.pack_forget()
        self.status_var.set("Falha na indexação.")
        messagebox.showerror("Erro na indexação", mensagem_erro)

    def _executar_busca(self) -> None:
        consulta = self.entrada_busca.get().strip()

        for linha in self.tabela.get_children():
            self.tabela.delete(linha)
        self.resultados_atuais = []

        if not consulta:
            self.status_var.set("Digite uma palavra-chave, frase ou pergunta para buscar.")
            return

        try:
            with database.get_connection(DATABASE_PATH) as conn:
                resultados = search.buscar(conn, consulta)
        except Exception as exc:
            messagebox.showerror("Erro na busca", str(exc))
            return

        self.resultados_atuais = resultados

        if not resultados:
            self.status_var.set("Nenhum resultado encontrado.")
            return

        for resultado in resultados:
            self.tabela.insert(
                "",
                tk.END,
                values=(resultado["filename"], resultado["page_number"], resultado["snippet"]),
            )

        self.status_var.set(f"{len(resultados)} resultado(s) encontrado(s).")

    def _abrir_resultado_selecionado(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showinfo("Nenhum resultado selecionado", "Selecione um resultado da lista.")
            return

        indice = self.tabela.index(selecao[0])
        resultado = self.resultados_atuais[indice]

        # Limpa pontuação da busca para usar como destaque (highlight) no PDF
        import re
        consulta = self.entrada_busca.get().strip()
        termos_destaque = re.sub(r'[^\w\s-]', '', consulta).strip()

        try:
            opener.open_pdf_at_page(
                resultado["path"],
                resultado["page_number"],
                termos_busca=termos_destaque,
            )
        except opener.ArquivoNaoEncontradoError as exc:
            messagebox.showerror("Arquivo não encontrado", str(exc))


def main() -> None:
    app = BuscadorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
