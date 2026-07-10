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
from collections import OrderedDict
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
        self._busca_geracao = 0
        self._cache_buscas = OrderedDict()

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

        ttk.Label(frame_topo, text="Visualizador:").pack(side=tk.LEFT, padx=(15, 2))
        self.combo_visualizador = ttk.Combobox(
            frame_topo,
            values=["Sistema (Padrão)", "Evince", "Okular", "Brave", "Chrome", "Firefox"],
            state="readonly",
            width=16,
        )
        self.combo_visualizador.pack(side=tk.LEFT)

        from config import obter_setting, salvar_setting
        visualizador_salvo = obter_setting("visualizador_pdf", "sistema")

        map_exibicao = {
            "sistema": "Sistema (Padrão)",
            "evince": "Evince",
            "okular": "Okular",
            "brave-browser": "Brave",
            "google-chrome": "Chrome",
            "firefox": "Firefox",
        }
        map_interno = {v: k for k, v in map_exibicao.items()}

        self.combo_visualizador.set(map_exibicao.get(visualizador_salvo, "Sistema (Padrão)"))

        def salvar_preferencia_viewer(event):
            val_selecionado = self.combo_visualizador.get()
            val_interno = map_interno.get(val_selecionado, "sistema")
            salvar_setting("visualizador_pdf", val_interno)
            self.status_var.set(f"Visualizador PDF alterado para: {val_selecionado}")

        self.combo_visualizador.bind("<<ComboboxSelected>>", salvar_preferencia_viewer)

        ttk.Button(
            frame_topo, text="Selecionar pasta...", command=self._selecionar_pasta
        ).pack(side=tk.RIGHT, padx=(5, 0))

        self.botao_indexar = ttk.Button(
            frame_topo, text="Indexar", command=self._indexar_em_thread, state=tk.DISABLED
        )
        self.botao_indexar.pack(side=tk.RIGHT, padx=(5, 0))

        self.botao_diagnostico = ttk.Button(
            frame_topo, text="Diagnóstico...", command=self._mostrar_diagnostico
        )
        self.botao_diagnostico.pack(side=tk.RIGHT, padx=(5, 0))

        self.botao_manutencao = ttk.Button(
            frame_topo, text="Manutenção...", command=self._mostrar_manutencao
        )
        self.botao_manutencao.pack(side=tk.RIGHT)

        # --- Barra de busca ---
        frame_busca = ttk.Frame(self, padding=(10, 0, 10, 5))
        frame_busca.pack(fill=tk.X)

        from config import obter_historico
        self.historico_buscas = obter_historico()

        self.entrada_busca = ttk.Combobox(
            frame_busca,
            values=self.historico_buscas,
            font=("TkDefaultFont", 12),
        )
        self.entrada_busca.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entrada_busca.bind("<Return>", lambda evento: self._executar_busca())
        self.entrada_busca.bind("<<ComboboxSelected>>", lambda evento: self._executar_busca())

        ttk.Button(frame_busca, text="Buscar", command=self._executar_busca).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        ttk.Button(frame_busca, text="Limpar", command=self._limpar_busca).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # --- Opções de busca (Modo Amplo / Modo Preciso) ---
        frame_opcoes_busca = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame_opcoes_busca.pack(fill=tk.X)

        self.modo_busca_var = tk.StringVar(value="amplo")

        radio_amplo = ttk.Radiobutton(
            frame_opcoes_busca,
            text="Modo Amplo (qualquer termo - OR)",
            variable=self.modo_busca_var,
            value="amplo",
        )
        radio_amplo.pack(side=tk.LEFT, padx=(0, 15))

        radio_preciso = ttk.Radiobutton(
            frame_opcoes_busca,
            text="Modo Preciso (todos os termos - AND)",
            variable=self.modo_busca_var,
            value="preciso",
        )
        radio_preciso.pack(side=tk.LEFT, padx=(0, 15))

        radio_frase = ttk.Radiobutton(
            frame_opcoes_busca,
            text="Frase Exata (sequência exata)",
            variable=self.modo_busca_var,
            value="frase",
        )
        radio_frase.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(frame_opcoes_busca, text="Filtrar resultados:").pack(side=tk.LEFT, padx=(15, 2))
        self.entrada_filtro = ttk.Entry(frame_opcoes_busca, width=20)
        self.entrada_filtro.pack(side=tk.LEFT)
        self.entrada_filtro.bind("<KeyRelease>", lambda event: self._filtrar_resultados_tabela())

        # --- Lista de resultados ---
        frame_resultados = ttk.Frame(self, padding=(10, 0, 10, 10))
        frame_resultados.pack(fill=tk.BOTH, expand=True)

        colunas = ("manual", "pagina", "relevancia", "trecho")
        self.tabela = ttk.Treeview(
            frame_resultados, columns=colunas, show="headings", selectmode="browse"
        )
        self.tabela.heading("manual", text="Manual")
        self.tabela.heading("pagina", text="Página")
        self.tabela.heading("relevancia", text="Relevância")
        self.tabela.heading("trecho", text="Trecho encontrado")
        self.tabela.column("manual", width=200, anchor=tk.W)
        self.tabela.column("pagina", width=70, anchor=tk.CENTER)
        self.tabela.column("relevancia", width=90, anchor=tk.CENTER)
        self.tabela.column("trecho", width=460, anchor=tk.W)

        scrollbar = ttk.Scrollbar(
            frame_resultados, orient=tk.VERTICAL, command=self.tabela.yview
        )
        self.tabela.configure(yscrollcommand=scrollbar.set)

        self.tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tabela.bind("<Double-1>", lambda evento: self._abrir_resultado_selecionado())

        # Pop-up menu para a tabela (Botão Direito)
        self.menu_contexto = tk.Menu(self, tearoff=0)
        self.menu_contexto.add_command(label="Copiar trecho encontrado", command=self._copiar_trecho)
        self.menu_contexto.add_command(label="Copiar nome do manual e página", command=self._copiar_manual_pagina)
        self.menu_contexto.add_separator()
        self.menu_contexto.add_command(label="Abrir PDF na página", command=self._abrir_resultado_selecionado)

        self.tabela.bind("<Button-3>", self._mostrar_menu_contexto)

        # Atalhos de teclado
        self.bind("<Control-f>", lambda event: self.entrada_busca.focus())
        self.bind("<Escape>", lambda event: self._limpar_busca())

        # Foca no campo de busca ao iniciar o aplicativo
        self.entrada_busca.focus()

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
        self._cache_buscas.clear()
        self.ultimo_resultado_indexacao = resultado
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

    def _mostrar_diagnostico(self) -> None:
        janela = tk.Toplevel(self)
        janela.title("Diagnóstico da Indexação")
        janela.geometry("600x500")
        janela.transient(self)
        janela.grab_set()

        try:
            with database.get_connection(DATABASE_PATH) as conn:
                total_docs = database.contar_documentos(conn)
                total_pags = database.contar_paginas(conn)
                
                cursor = conn.execute("""
                    SELECT filename FROM documents
                    WHERE id NOT IN (SELECT DISTINCT document_id FROM pages);
                """)
                sem_texto_db = [row["filename"] for row in cursor.fetchall()]
                
                cursor = conn.execute("SELECT MAX(indexed_at) AS ultima_ind FROM documents;")
                ultima_ind_val = cursor.fetchone()["ultima_ind"]
        except Exception as exc:
            messagebox.showerror("Erro de Diagnóstico", f"Não foi possível ler as estatísticas: {exc}")
            return

        import datetime
        data_ultima = "Nenhuma indexação registrada"
        if ultima_ind_val:
            data_ultima = datetime.datetime.fromtimestamp(ultima_ind_val).strftime("%d/%m/%Y %H:%M:%S")

        linhas = []
        linhas.append("=== DIAGNÓSTICO DA BASE DE BUSCA ===")
        linhas.append(f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        linhas.append("-" * 45)
        linhas.append(f"Total de Manuais Indexados: {total_docs}")
        linhas.append(f"Total de Páginas Indexadas: {total_pags}")
        linhas.append(f"Última indexação registrada: {data_ultima}")
        linhas.append("-" * 45)
        
        linhas.append(f"PDFs sem texto pesquisável no banco ({len(sem_texto_db)}):")
        if sem_texto_db:
            for f in sem_texto_db:
                linhas.append(f"  - {f}")
        else:
            linhas.append("  (Nenhum)")
            
        linhas.append("-" * 45)
        linhas.append("=== DETALHES DA ÚLTIMA EXECUÇÃO NESTA SESSÃO ===")
        
        res = getattr(self, "ultimo_resultado_indexacao", None)
        if res is None:
            linhas.append("Nenhuma indexação foi executada nesta sessão do aplicativo.")
        else:
            linhas.append(f"Tempo de execução: {res.tempo_execucao:.2f}s")
            
            linhas.append(f"Novos arquivos adicionados ({len(res.novos)}):")
            for f in res.novos:
                linhas.append(f"  - {f}")
            if not res.novos:
                linhas.append("  (Nenhum)")

            linhas.append(f"Arquivos atualizados ({len(res.atualizados)}):")
            for f in res.atualizados:
                linhas.append(f"  - {f}")
            if not res.atualizados:
                linhas.append("  (Nenhum)")

            linhas.append(f"Arquivos removidos ({len(res.removidos)}):")
            for f in res.removidos:
                linhas.append(f"  - {f}")
            if not res.removidos:
                linhas.append("  (Nenhum)")

            linhas.append(f"Arquivos sem texto pesquisável ({len(res.sem_texto_extraivel)}):")
            for f in res.sem_texto_extraivel:
                linhas.append(f"  - {f}")
            if not res.sem_texto_extraivel:
                linhas.append("  (Nenhum)")

            linhas.append(f"Erros de leitura/processamento ({len(res.erros)}):")
            for f in res.erros:
                linhas.append(f"  - {f}")
            if not res.erros:
                linhas.append("  (Nenhum)")

        relatorio_texto = "\n".join(linhas)

        frame_text = ttk.Frame(janela, padding=10)
        frame_text.pack(fill=tk.BOTH, expand=True)

        text_area = tk.Text(frame_text, wrap=tk.WORD, font=("TkFixedFont", 10))
        text_area.insert(tk.END, relatorio_texto)
        text_area.config(state=tk.DISABLED)

        scroll = ttk.Scrollbar(frame_text, orient=tk.VERTICAL, command=text_area.yview)
        text_area.configure(yscrollcommand=scroll.set)
        
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        frame_botoes = ttk.Frame(janela, padding=10)
        frame_botoes.pack(fill=tk.X)

        def copiar():
            self.clipboard_clear()
            self.clipboard_append(relatorio_texto)
            messagebox.showinfo("Copiado", "Relatório copiado para a área de transferência!")

        def salvar():
            caminho_salvar = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Arquivos de Texto", "*.txt")],
                title="Salvar Relatório de Diagnóstico"
            )
            if caminho_salvar:
                try:
                    with open(caminho_salvar, "w", encoding="utf-8") as f:
                        f.write(relatorio_texto)
                    messagebox.showinfo("Salvo", f"Relatório salvo com sucesso em:\n{caminho_salvar}")
                except Exception as e:
                    messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o arquivo: {e}")

        ttk.Button(frame_botoes, text="Copiar", command=copiar).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_botoes, text="Salvar como...", command=salvar).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_botoes, text="Fechar", command=janela.destroy).pack(side=tk.RIGHT, padx=5)

    def _mostrar_manutencao(self) -> None:
        janela = tk.Toplevel(self)
        janela.title("Manutenção do Índice")
        janela.geometry("450x330")
        janela.resizable(False, False)
        janela.transient(self)
        janela.grab_set()

        frame = ttk.Frame(janela, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame, 
            text="Manutenção do Banco de Dados", 
            font=("TkDefaultFont", 12, "bold")
        ).pack(anchor=tk.W, pady=(0, 15))

        btn_reindex = ttk.Button(
            frame, 
            text="Reindexar Pasta (Incremental)", 
            command=lambda: [janela.destroy(), self._indexar_em_thread()]
        )
        btn_reindex.pack(fill=tk.X, pady=5)
        if not self.pasta_selecionada:
            btn_reindex.config(state=tk.DISABLED)

        btn_recriar = ttk.Button(
            frame, 
            text="Recriar Índice do Zero...", 
            command=lambda: [janela.destroy(), self._recriar_indice_do_zero()]
        )
        btn_recriar.pack(fill=tk.X, pady=5)
        if not self.pasta_selecionada:
            btn_recriar.config(state=tk.DISABLED)

        btn_limpar = ttk.Button(
            frame, 
            text="Limpar Índice Atual...", 
            command=lambda: [janela.destroy(), self._limpar_indice()]
        )
        btn_limpar.pack(fill=tk.X, pady=5)

        btn_limpar_hist = ttk.Button(
            frame, 
            text="Limpar Histórico de Buscas...", 
            command=lambda: [janela.destroy(), self._limpar_historico()]
        )
        btn_limpar_hist.pack(fill=tk.X, pady=5)

        ttk.Button(frame, text="Fechar", command=janela.destroy).pack(anchor=tk.E, pady=(15, 0))

    def _limpar_historico(self) -> None:
        if not messagebox.askyesno(
            "Confirmar Limpeza de Histórico",
            "Tem certeza que deseja apagar todo o histórico de pesquisas recentes?"
        ):
            return
        from config import salvar_historico
        self.historico_buscas = []
        salvar_historico(self.historico_buscas)
        self.entrada_busca["values"] = []
        self.status_var.set("Histórico de buscas limpo.")

    def _limpar_indice(self) -> None:
        if not messagebox.askyesno(
            "Confirmar Limpeza", 
            "Tem certeza que deseja apagar todo o índice de busca?\n\n"
            "Todos os dados de manuais e páginas serão removidos do banco."
        ):
            return
            
        try:
            with database.get_connection(DATABASE_PATH) as conn:
                conn.execute("DELETE FROM documents;")
                conn.execute("DELETE FROM vocabulary;")
                conn.commit()
            self._cache_buscas.clear()
            
            for linha in self.tabela.get_children():
                self.tabela.delete(linha)
            self.resultados_atuais = []
            
            self.status_var.set("Índice de busca limpo com sucesso.")
            messagebox.showinfo("Sucesso", "O índice de busca foi limpo e está vazio.")
        except Exception as exc:
            messagebox.showerror("Erro ao Limpar", f"Falha ao limpar índice: {exc}")

    def _recriar_indice_do_zero(self) -> None:
        if not self.pasta_selecionada:
            return
            
        if not messagebox.askyesno(
            "Confirmar Recriação", 
            "Tem certeza que deseja recriar o índice do zero?\n\n"
            "Isso apagará todo o índice atual e iniciará uma nova indexação completa."
        ):
            return

        self.botao_indexar.config(state=tk.DISABLED)
        self.status_var.set("Limpando índice anterior e iniciando indexação completa...")

        self.progresso.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=(0, 5))
        self.progresso["value"] = 0

        thread = threading.Thread(target=self._executar_recriacao, daemon=True)
        thread.start()

    def _executar_recriacao(self) -> None:
        try:
            with database.get_connection(DATABASE_PATH) as conn:
                conn.execute("DELETE FROM documents;")
                conn.commit()
                
                resultado = indexer.indexar_pasta(
                    conn, self.pasta_selecionada, callback_progresso=self._atualizar_progresso
                )
            self.after(0, self._indexacao_concluida, resultado)
        except Exception as exc:
            self.after(0, self._indexacao_falhou, str(exc))

    def _executar_busca(self) -> None:
        consulta = self.entrada_busca.get().strip()

        for linha in self.tabela.get_children():
            self.tabela.delete(linha)
        self.resultados_atuais = []

        if not consulta:
            self.status_var.set("Digite uma palavra-chave, frase ou pergunta para buscar.")
            return

        # Atualiza e salva o histórico de buscas
        from config import salvar_historico
        if consulta in self.historico_buscas:
            self.historico_buscas.remove(consulta)
        self.historico_buscas.insert(0, consulta)
        self.historico_buscas = self.historico_buscas[:15]
        salvar_historico(self.historico_buscas)
        self.entrada_busca["values"] = self.historico_buscas

        modo = self.modo_busca_var.get()
        chave_cache = (search.normalizar_consulta(consulta), modo)
        self._busca_geracao += 1
        geracao = self._busca_geracao
        if chave_cache in self._cache_buscas:
            resultados = self._cache_buscas.pop(chave_cache)
            self._cache_buscas[chave_cache] = resultados
            self._exibir_resultados_busca(geracao, resultados, None)
            return

        self.status_var.set("Buscando...")
        threading.Thread(
            target=self._buscar_em_thread,
            args=(geracao, chave_cache, consulta, modo),
            daemon=True,
        ).start()

    def _buscar_em_thread(self, geracao, chave_cache, consulta, modo) -> None:
        try:
            with database.get_connection(DATABASE_PATH) as conn:
                resultados = search.buscar(conn, consulta, modo=modo)
            erro = None
        except Exception as exc:
            resultados = []
            erro = str(exc)
        self.after(0, self._exibir_resultados_busca, geracao, resultados, erro, chave_cache)

    def _exibir_resultados_busca(self, geracao, resultados, erro=None, chave_cache=None) -> None:
        # Ignora respostas antigas quando uma consulta mais nova já foi iniciada.
        if geracao != self._busca_geracao:
            return
        if erro:
            messagebox.showerror("Erro na busca", erro)
            self.status_var.set("Falha na busca.")
            return
        if chave_cache is not None:
            self._cache_buscas[chave_cache] = resultados
            while len(self._cache_buscas) > 32:
                self._cache_buscas.popitem(last=False)
        self.resultados_atuais = resultados

        if not resultados:
            self.status_var.set("Nenhum resultado encontrado.")
            return

        for resultado in resultados:
            if self.pasta_selecionada:
                try:
                    manual_display = os.path.relpath(resultado["path"], self.pasta_selecionada)
                except ValueError:
                    manual_display = resultado["filename"]
            else:
                partes = resultado["path"].split(os.sep)
                if len(partes) >= 2:
                    manual_display = os.path.join(partes[-2], partes[-1])
                else:
                    manual_display = resultado["filename"]

            self.tabela.insert(
                "",
                tk.END,
                values=(
                    manual_display,
                    resultado["page_number"],
                    resultado["relevance_label"],
                    resultado["snippet"],
                ),
            )

        self.status_var.set(f"{len(resultados)} resultado(s) encontrado(s).")

    def _mostrar_menu_contexto(self, event) -> None:
        iid = self.tabela.identify_row(event.y)
        if iid:
            self.tabela.selection_set(iid)
            self.menu_contexto.post(event.x_root, event.y_root)

    def _copiar_trecho(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        indice = self.tabela.index(selecao[0])
        resultado = self.resultados_atuais[indice]
        
        self.clipboard_clear()
        self.clipboard_append(resultado["snippet"])
        self.status_var.set("Trecho copiado para a área de transferência.")

    def _copiar_manual_pagina(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        indice = self.tabela.index(selecao[0])
        resultado = self.resultados_atuais[indice]
        
        texto_copiar = f"Manual: {resultado['filename']} - Página: {resultado['page_number']}"
        self.clipboard_clear()
        self.clipboard_append(texto_copiar)
        self.status_var.set("Nome do manual e página copiados.")

    def _limpar_busca(self) -> None:
        self.entrada_busca.delete(0, tk.END)
        for linha in self.tabela.get_children():
            self.tabela.delete(linha)
        self.resultados_atuais = []
        self.entrada_filtro.delete(0, tk.END)
        self.status_var.set("Busca limpa.")

    def _filtrar_resultados_tabela(self, event=None) -> None:
        filtro = self.entrada_filtro.get().strip().lower()
        
        for linha in self.tabela.get_children():
            self.tabela.delete(linha)
            
        for resultado in self.resultados_atuais:
            if self.pasta_selecionada:
                try:
                    manual_display = os.path.relpath(resultado["path"], self.pasta_selecionada)
                except ValueError:
                    manual_display = resultado["filename"]
            else:
                partes = resultado["path"].split(os.sep)
                if len(partes) >= 2:
                    manual_display = os.path.join(partes[-2], partes[-1])
                else:
                    manual_display = resultado["filename"]
                    
            if not filtro or filtro in manual_display.lower():
                self.tabela.insert(
                    "",
                    tk.END,
                    values=(
                        manual_display,
                        resultado["page_number"],
                        resultado["relevance_label"],
                        resultado["snippet"],
                    ),
                )

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
