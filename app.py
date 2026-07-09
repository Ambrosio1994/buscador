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


# Cores da interface (Tema Escuro / Deep Blue)
COLOR_BG_DARKEST = "#0F1322"
COLOR_BG_CARD = "#171E30"
COLOR_BG_HOVER = "#232D48"
COLOR_BG_INPUT = "#1D2438"
COLOR_ACCENT = "#3B82F6"
COLOR_ACCENT_TINT = "#182749"
COLOR_FG_LIGHT = "#F1F5F9"
COLOR_FG_MUTED = "#94A3B8"
COLOR_GREEN = "#10B981"
COLOR_BORDER = "#242F4D"
FONT_FAMILY = "sans-serif"


class BuscadorApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Buscador Offline de Manuais em PDF")
        
        # Remove as bordas nativas da janela para usar barra de título customizada
        self.overrideredirect(True)
        
        # Centraliza a janela na tela
        self.update_idletasks()
        largura = 1100
        altura = 700
        x_split = (self.winfo_screenwidth() - largura) // 2
        y_split = (self.winfo_screenheight() - altura) // 2
        self.geometry(f"{largura}x{altura}+{x_split}+{y_split}")
        self.minsize(800, 500)
        self.config(bg=COLOR_BG_DARKEST)

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
        self.is_maximized = False

        self._construir_interface()
        self._configurar_banco()
        self._atualizar_painel_esquerdo()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------



    def _construir_interface(self) -> None:
        # Configuração de estilos do ttk
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configuração geral de estilos
        style.configure("Custom.Treeview",
                        background=COLOR_BG_CARD,
                        fieldbackground=COLOR_BG_CARD,
                        foreground=COLOR_FG_LIGHT,
                        rowheight=30,
                        borderwidth=0,
                        font=(FONT_FAMILY, 9))
        style.map("Custom.Treeview",
                  background=[("selected", "#203A70")],
                  foreground=[("selected", "#FFFFFF")])
        
        style.configure("Custom.Treeview.Heading",
                        background=COLOR_BG_DARKEST,
                        foreground=COLOR_FG_MUTED,
                        font=(FONT_FAMILY, 9, "bold"),
                        borderwidth=0)
        
        style.configure("Borderless.TCombobox", 
                        background=COLOR_BG_INPUT, 
                        fieldbackground=COLOR_BG_INPUT, 
                        foreground=COLOR_FG_LIGHT,
                        bordercolor=COLOR_BG_INPUT,
                        arrowcolor=COLOR_FG_MUTED,
                        lightcolor=COLOR_BG_INPUT,
                        darkcolor=COLOR_BG_INPUT)
                        
        style.configure("Custom.Horizontal.TProgressbar",
                        background=COLOR_ACCENT,
                        troughcolor=COLOR_BG_INPUT,
                        borderwidth=0)

        # 1. Barra de título da janela (topo, altura fixa e fina)
        self.title_bar = tk.Frame(self, bg=COLOR_BG_DARKEST, height=35)
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)
        
        # Logo/Icon + title
        self.title_logo = tk.Label(self.title_bar, text="📁", fg=COLOR_ACCENT, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 12))
        self.title_logo.pack(side=tk.LEFT, padx=(15, 5))
        
        self.title_label = tk.Label(self.title_bar, text="Buscador Offline de Manuais", fg=COLOR_FG_LIGHT, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 9, "bold"))
        self.title_label.pack(side=tk.LEFT)
        
        # Window controls
        self.btn_close = tk.Label(self.title_bar, text="✕", fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 12, "bold"), cursor="hand2")
        self.btn_close.pack(side=tk.RIGHT, padx=(5, 15))
        self.btn_close.bind("<Button-1>", lambda e: self.destroy())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.config(fg="#EF4444"))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.config(fg=COLOR_FG_MUTED))

        self.btn_max = tk.Label(self.title_bar, text="🗖", fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 10), cursor="hand2")
        self.btn_max.pack(side=tk.RIGHT, padx=5)
        self.btn_max.bind("<Button-1>", lambda e: self._toggle_maximize())
        self.btn_max.bind("<Enter>", lambda e: self.btn_max.config(fg=COLOR_FG_LIGHT))
        self.btn_max.bind("<Leave>", lambda e: self.btn_max.config(fg=COLOR_FG_MUTED))

        self.btn_min = tk.Label(self.title_bar, text="🗕", fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 12), cursor="hand2")
        self.btn_min.pack(side=tk.RIGHT, padx=5)
        self.btn_min.bind("<Button-1>", lambda e: self.iconify())
        self.btn_min.bind("<Enter>", lambda e: self.btn_min.config(fg=COLOR_FG_LIGHT))
        self.btn_min.bind("<Leave>", lambda e: self.btn_min.config(fg=COLOR_FG_MUTED))
        
        # Drag bindings
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._drag)
        self.title_label.bind("<Button-1>", self._start_drag)
        self.title_label.bind("<B1-Motion>", self._drag)
        self.title_bar.bind("<Double-Button-1>", lambda e: self._toggle_maximize())

        # 2. Barra de ações superior (logo abaixo do título)
        frame_acoes = tk.Frame(self, bg=COLOR_BG_DARKEST)
        frame_acoes.pack(fill=tk.X, padx=15, pady=(5, 10))
        
        # Card 1: Pasta selecionada (mais largo)
        self.card_pasta = tk.Frame(frame_acoes, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        self.card_pasta.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        lbl_icon_p = tk.Label(self.card_pasta, text="📁", fg=COLOR_ACCENT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 18))
        lbl_icon_p.pack(side=tk.LEFT, padx=12, pady=10)
        
        text_frame_p = tk.Frame(self.card_pasta, bg=COLOR_BG_CARD)
        text_frame_p.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=6)
        
        lbl_title_p = tk.Label(text_frame_p, text="Pasta selecionada:", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_title_p.pack(anchor=tk.W)
        
        self.label_pasta = tk.Label(text_frame_p, text="Nenhuma pasta selecionada", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"), wraplength=350, justify=tk.LEFT)
        self.label_pasta.pack(anchor=tk.W)
        
        self.btn_alterar_pasta = tk.Button(
            self.card_pasta, text="Alterar...", command=self._selecionar_pasta,
            bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT,
            highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, relief=tk.FLAT, padx=10, pady=5, cursor="hand2"
        )
        self.btn_alterar_pasta.pack(side=tk.RIGHT, padx=12, pady=12)
        
        # Card 2: Diagnóstico
        self.card_diag = tk.Frame(frame_acoes, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, cursor="hand2")
        self.card_diag.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        self.card_diag.bind("<Button-1>", lambda e: self._mostrar_diagnostico())
        
        lbl_icon_diag = tk.Label(self.card_diag, text="📊", fg=COLOR_ACCENT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 18))
        lbl_icon_diag.pack(side=tk.LEFT, padx=12, pady=10)
        lbl_icon_diag.bind("<Button-1>", lambda e: self._mostrar_diagnostico())
        
        text_frame_diag = tk.Frame(self.card_diag, bg=COLOR_BG_CARD)
        text_frame_diag.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=6, padx=(0, 12))
        text_frame_diag.bind("<Button-1>", lambda e: self._mostrar_diagnostico())
        
        lbl_title_diag = tk.Label(text_frame_diag, text="Diagnóstico", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"))
        lbl_title_diag.pack(anchor=tk.W)
        lbl_title_diag.bind("<Button-1>", lambda e: self._mostrar_diagnostico())
        
        lbl_sub_diag = tk.Label(text_frame_diag, text="Estatísticas da base", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_sub_diag.pack(anchor=tk.W)
        lbl_sub_diag.bind("<Button-1>", lambda e: self._mostrar_diagnostico())
        
        self._bind_hover(self.card_diag, [self.card_diag, lbl_icon_diag, text_frame_diag, lbl_title_diag, lbl_sub_diag])
        
        # Card 3: Manutenção
        self.card_manut = tk.Frame(frame_acoes, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, cursor="hand2")
        self.card_manut.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        self.card_manut.bind("<Button-1>", lambda e: self._mostrar_manutencao())
        
        lbl_icon_manut = tk.Label(self.card_manut, text="🛠️", fg=COLOR_ACCENT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 18))
        lbl_icon_manut.pack(side=tk.LEFT, padx=12, pady=10)
        lbl_icon_manut.bind("<Button-1>", lambda e: self._mostrar_manutencao())
        
        text_frame_manut = tk.Frame(self.card_manut, bg=COLOR_BG_CARD)
        text_frame_manut.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=6, padx=(0, 12))
        text_frame_manut.bind("<Button-1>", lambda e: self._mostrar_manutencao())
        
        lbl_title_manut = tk.Label(text_frame_manut, text="Manutenção", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"))
        lbl_title_manut.pack(anchor=tk.W)
        lbl_title_manut.bind("<Button-1>", lambda e: self._mostrar_manutencao())
        
        lbl_sub_manut = tk.Label(text_frame_manut, text="Ações do banco", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_sub_manut.pack(anchor=tk.W)
        lbl_sub_manut.bind("<Button-1>", lambda e: self._mostrar_manutencao())
        
        self._bind_hover(self.card_manut, [self.card_manut, lbl_icon_manut, text_frame_manut, lbl_title_manut, lbl_sub_manut])
        
        # Card 4: Botão "Indexar agora" (Destaque colorido)
        self.card_index = tk.Frame(frame_acoes, bg=COLOR_ACCENT, highlightbackground=COLOR_ACCENT, highlightthickness=1, bd=0, cursor="hand2")
        self.card_index.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        self.card_index.bind("<Button-1>", lambda e: self._indexar_em_thread())
        
        lbl_icon_index = tk.Label(self.card_index, text="🔄", fg="#FFFFFF", bg=COLOR_ACCENT, font=(FONT_FAMILY, 18))
        lbl_icon_index.pack(side=tk.LEFT, padx=12, pady=10)
        lbl_icon_index.bind("<Button-1>", lambda e: self._indexar_em_thread())
        
        text_frame_index = tk.Frame(self.card_index, bg=COLOR_ACCENT)
        text_frame_index.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=6, padx=(0, 12))
        text_frame_index.bind("<Button-1>", lambda e: self._indexar_em_thread())
        
        self.lbl_title_index = tk.Label(text_frame_index, text="Indexar agora", fg="#FFFFFF", bg=COLOR_ACCENT, font=(FONT_FAMILY, 9, "bold"))
        self.lbl_title_index.pack(anchor=tk.W)
        self.lbl_title_index.bind("<Button-1>", lambda e: self._indexar_em_thread())
        
        self.lbl_sub_index = tk.Label(text_frame_index, text="Atualizar PDFs", fg="#E0F2FE", bg=COLOR_ACCENT, font=(FONT_FAMILY, 8))
        self.lbl_sub_index.pack(anchor=tk.W)
        self.lbl_sub_index.bind("<Button-1>", lambda e: self._indexar_em_thread())
        
        # Hover do indexar
        def on_index_enter(e):
            self.card_index.config(bg="#2563EB")
            lbl_icon_index.config(bg="#2563EB")
            text_frame_index.config(bg="#2563EB")
            self.lbl_title_index.config(bg="#2563EB")
            self.lbl_sub_index.config(bg="#2563EB")
        def on_index_leave(e):
            self.card_index.config(bg=COLOR_ACCENT)
            lbl_icon_index.config(bg=COLOR_ACCENT)
            text_frame_index.config(bg=COLOR_ACCENT)
            self.lbl_title_index.config(bg=COLOR_ACCENT)
            self.lbl_sub_index.config(bg=COLOR_ACCENT)
        self.card_index.bind("<Enter>", on_index_enter)
        self.card_index.bind("<Leave>", on_index_leave)
        lbl_icon_index.bind("<Enter>", on_index_enter)
        text_frame_index.bind("<Enter>", on_index_enter)
        self.lbl_title_index.bind("<Enter>", on_index_enter)
        self.lbl_sub_index.bind("<Enter>", on_index_enter)
        
        # Wrapper de compatibilidade para botao_indexar
        class WidgetWrapper:
            def __init__(self, card, lbl_title, lbl_sub, lbl_icon):
                self.card = card
                self.lbl_title = lbl_title
                self.lbl_sub = lbl_sub
                self.lbl_icon = lbl_icon
            def config(self, **kwargs):
                if "state" in kwargs:
                    state = kwargs["state"]
                    if state == tk.DISABLED:
                        self.card.config(bg="#1E293B", highlightbackground=COLOR_BORDER)
                        self.lbl_icon.config(bg="#1E293B", fg=COLOR_FG_MUTED)
                        self.lbl_title.config(bg="#1E293B", fg=COLOR_FG_MUTED)
                        self.lbl_sub.config(bg="#1E293B", fg=COLOR_FG_MUTED)
                        self.card.unbind("<Button-1>")
                        self.lbl_icon.unbind("<Button-1>")
                        self.lbl_title.unbind("<Button-1>")
                        self.lbl_sub.unbind("<Button-1>")
                        self.card.config(cursor="")
                    else:
                        self.card.config(bg=COLOR_ACCENT, highlightbackground=COLOR_ACCENT)
                        self.lbl_icon.config(bg=COLOR_ACCENT, fg="#FFFFFF")
                        self.lbl_title.config(bg=COLOR_ACCENT, fg="#FFFFFF")
                        self.lbl_sub.config(bg=COLOR_ACCENT, fg="#E0F2FE")
                        self.card.bind("<Button-1>", lambda e: self._indexar_em_thread())
                        self.lbl_icon.bind("<Button-1>", lambda e: self._indexar_em_thread())
                        self.lbl_title.bind("<Button-1>", lambda e: self._indexar_em_thread())
                        self.lbl_sub.bind("<Button-1>", lambda e: self._indexar_em_thread())
                        self.card.bind("<Enter>", on_index_enter)
                        self.card.bind("<Leave>", on_index_leave)
                        self.card.config(cursor="hand2")
                else:
                    self.card.config(**kwargs)
            def configure(self, **kwargs):
                self.config(**kwargs)
                
        self.botao_indexar = WidgetWrapper(self.card_index, self.lbl_title_index, self.lbl_sub_index, lbl_icon_index)
        
        # Separador flexível
        spacer = tk.Frame(frame_acoes, bg=COLOR_BG_DARKEST)
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Card 5: Configurações (Extremo direito)
        self.card_config = tk.Frame(frame_acoes, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, cursor="hand2")
        self.card_config.pack(side=tk.RIGHT, fill=tk.BOTH)
        
        lbl_icon_cfg = tk.Label(self.card_config, text="⚙️", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 14))
        lbl_icon_cfg.pack(side=tk.LEFT, padx=(12, 5), pady=10)
        
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
        nome_visualizador_curto = map_exibicao.get(visualizador_salvo, "Sistema").split()[0]
        
        lbl_title_cfg = tk.Label(self.card_config, text=f"Visualizador: {nome_visualizador_curto}", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"))
        lbl_title_cfg.pack(side=tk.LEFT, pady=10)
        
        lbl_arrow_cfg = tk.Label(self.card_config, text="▼", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_arrow_cfg.pack(side=tk.LEFT, padx=(5, 12), pady=10)
        
        self._bind_hover(self.card_config, [self.card_config, lbl_icon_cfg, lbl_title_cfg, lbl_arrow_cfg])
        
        self.menu_visualizador = tk.Menu(self, tearoff=0, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_ACCENT, activeforeground="#FFFFFF", bd=1, relief=tk.FLAT)
        
        def set_visualizador(val):
            map_interno = {
                "Sistema (Padrão)": "sistema",
                "Evince": "evince",
                "Okular": "okular",
                "Brave": "brave-browser",
                "Chrome": "google-chrome",
                "Firefox": "firefox"
            }
            val_interno = map_interno.get(val, "sistema")
            salvar_setting("visualizador_pdf", val_interno)
            self.status_var.set(f"Visualizador PDF alterado para: {val}")
            lbl_title_cfg.config(text=f"Visualizador: {val.split()[0]}")
            
        for opt in ["Sistema (Padrão)", "Evince", "Okular", "Brave", "Chrome", "Firefox"]:
            self.menu_visualizador.add_command(label=opt, command=lambda o=opt: set_visualizador(o))
            
        def show_cfg_menu(event):
            self.menu_visualizador.post(self.card_config.winfo_rootx(), self.card_config.winfo_rooty() + self.card_config.winfo_height())
            
        self.card_config.bind("<Button-1>", show_cfg_menu)
        lbl_icon_cfg.bind("<Button-1>", show_cfg_menu)
        lbl_title_cfg.bind("<Button-1>", show_cfg_menu)
        lbl_arrow_cfg.bind("<Button-1>", show_cfg_menu)

        # 3. Barra de busca (linha própria)
        frame_busca_linha = tk.Frame(self, bg=COLOR_BG_DARKEST)
        frame_busca_linha.pack(fill=tk.X, padx=15, pady=(5, 10))
        
        lbl_buscar_por = tk.Label(frame_busca_linha, text="Buscar por:", fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 10, "bold"))
        lbl_buscar_por.pack(side=tk.LEFT, padx=(0, 10))
        
        # Input container customizado (Fundo escuro/input e borda sutil)
        input_container = tk.Frame(frame_busca_linha, bg=COLOR_BG_INPUT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        input_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        from config import obter_historico
        self.historico_buscas = obter_historico()
        
        self.entrada_busca = ttk.Combobox(
            input_container,
            values=self.historico_buscas,
            font=(FONT_FAMILY, 11),
            style="Borderless.TCombobox"
        )
        self.entrada_busca.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.entrada_busca.bind("<Return>", lambda evento: self._executar_busca())
        self.entrada_busca.bind("<<ComboboxSelected>>", lambda evento: self._executar_busca())
        
        # Botão inline de Limpar (❌) no input
        btn_clear_input = tk.Label(input_container, text="✕", fg=COLOR_FG_MUTED, bg=COLOR_BG_INPUT, font=(FONT_FAMILY, 10, "bold"), cursor="hand2")
        btn_clear_input.pack(side=tk.RIGHT, padx=10)
        btn_clear_input.bind("<Button-1>", lambda e: self._limpar_busca())
        btn_clear_input.bind("<Enter>", lambda e: btn_clear_input.config(fg=COLOR_FG_LIGHT))
        btn_clear_input.bind("<Leave>", lambda e: btn_clear_input.config(fg=COLOR_FG_MUTED))
        
        # Botões de busca à direita
        self.btn_buscar = tk.Button(frame_busca_linha, text="🔍 Buscar", command=self._executar_busca, bg=COLOR_ACCENT, fg="#FFFFFF", activebackground="#2563EB", activeforeground="#FFFFFF", bd=0, padx=20, pady=8, font=(FONT_FAMILY, 10, "bold"), cursor="hand2")
        self.btn_buscar.pack(side=tk.LEFT, padx=(10, 0))
        
        self.btn_limpar = tk.Button(frame_busca_linha, text="🧹 Limpar", command=self._limpar_busca, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, padx=15, pady=8, font=(FONT_FAMILY, 10), cursor="hand2")
        self.btn_limpar.pack(side=tk.LEFT, padx=(5, 0))

        # 4. Linha de modos de busca e filtros
        frame_filtros_linha = tk.Frame(self, bg=COLOR_BG_DARKEST)
        frame_filtros_linha.pack(fill=tk.X, padx=15, pady=(5, 10))
        
        self.modo_busca_var = tk.StringVar(value="amplo")
        frame_modos_container = tk.Frame(frame_filtros_linha, bg=COLOR_BG_DARKEST)
        frame_modos_container.pack(side=tk.LEFT)
        
        def selecionar_modo(modo_val):
            self.modo_busca_var.set(modo_val)
            self._atualizar_estilo_modos()
            
        # Card Modo Amplo
        self.card_m_amplo = tk.Frame(frame_modos_container, cursor="hand2", bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        self.card_m_amplo.pack(side=tk.LEFT, padx=(0, 10))
        self.lbl_m_icon_a = tk.Label(self.card_m_amplo, text="📂", font=(FONT_FAMILY, 14), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_icon_a.pack(side=tk.LEFT, padx=(8, 4), pady=5)
        self.txt_m_frame_a = tk.Frame(self.card_m_amplo, bg=COLOR_BG_CARD)
        self.txt_m_frame_a.pack(side=tk.LEFT, padx=(0, 8), pady=3)
        self.lbl_m_title_a = tk.Label(self.txt_m_frame_a, text="Modo Amplo", font=(FONT_FAMILY, 8, "bold"), bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
        self.lbl_m_title_a.pack(anchor=tk.W)
        self.lbl_m_sub_a = tk.Label(self.txt_m_frame_a, text="Qualquer termo (OR)", font=(FONT_FAMILY, 7), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_sub_a.pack(anchor=tk.W)
        
        for w in [self.card_m_amplo, self.lbl_m_icon_a, self.txt_m_frame_a, self.lbl_m_title_a, self.lbl_m_sub_a]:
            w.bind("<Button-1>", lambda e: selecionar_modo("amplo"))
            
        # Card Modo Preciso
        self.card_m_preciso = tk.Frame(frame_modos_container, cursor="hand2", bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        self.card_m_preciso.pack(side=tk.LEFT, padx=(0, 10))
        self.lbl_m_icon_p = tk.Label(self.card_m_preciso, text="🎯", font=(FONT_FAMILY, 14), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_icon_p.pack(side=tk.LEFT, padx=(8, 4), pady=5)
        self.txt_m_frame_p = tk.Frame(self.card_m_preciso, bg=COLOR_BG_CARD)
        self.txt_m_frame_p.pack(side=tk.LEFT, padx=(0, 8), pady=3)
        self.lbl_m_title_p = tk.Label(self.txt_m_frame_p, text="Modo Preciso", font=(FONT_FAMILY, 8, "bold"), bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
        self.lbl_m_title_p.pack(anchor=tk.W)
        self.lbl_m_sub_p = tk.Label(self.txt_m_frame_p, text="Todos termos (AND)", font=(FONT_FAMILY, 7), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_sub_p.pack(anchor=tk.W)
        
        for w in [self.card_m_preciso, self.lbl_m_icon_p, self.txt_m_frame_p, self.lbl_m_title_p, self.lbl_m_sub_p]:
            w.bind("<Button-1>", lambda e: selecionar_modo("preciso"))
            
        # Card Frase Exata
        self.card_m_frase = tk.Frame(frame_modos_container, cursor="hand2", bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        self.card_m_frase.pack(side=tk.LEFT)
        self.lbl_m_icon_f = tk.Label(self.card_m_frase, text="📝", font=(FONT_FAMILY, 14), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_icon_f.pack(side=tk.LEFT, padx=(8, 4), pady=5)
        self.txt_m_frame_f = tk.Frame(self.card_m_frase, bg=COLOR_BG_CARD)
        self.txt_m_frame_f.pack(side=tk.LEFT, padx=(0, 8), pady=3)
        self.lbl_m_title_f = tk.Label(self.txt_m_frame_f, text="Frase Exata", font=(FONT_FAMILY, 8, "bold"), bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
        self.lbl_m_title_f.pack(anchor=tk.W)
        self.lbl_m_sub_f = tk.Label(self.txt_m_frame_f, text="Sequência exata", font=(FONT_FAMILY, 7), bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
        self.lbl_m_sub_f.pack(anchor=tk.W)
        
        for w in [self.card_m_frase, self.lbl_m_icon_f, self.txt_m_frame_f, self.lbl_m_title_f, self.lbl_m_sub_f]:
            w.bind("<Button-1>", lambda e: selecionar_modo("frase"))
            
        self._atualizar_estilo_modos()
        
        # Filtro rápido
        frame_filtro_container = tk.Frame(frame_filtros_linha, bg=COLOR_BG_DARKEST)
        frame_filtro_container.pack(side=tk.LEFT, padx=(25, 0))
        
        lbl_filtro_desc = tk.Label(frame_filtro_container, text="Filtro rápido:", fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 9, "bold"))
        lbl_filtro_desc.pack(side=tk.LEFT, padx=(0, 5))
        
        filter_input_frame = tk.Frame(frame_filtro_container, bg=COLOR_BG_INPUT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        filter_input_frame.pack(side=tk.LEFT)
        
        self.entrada_filtro = tk.Entry(filter_input_frame, bg=COLOR_BG_INPUT, fg=COLOR_FG_LIGHT, insertbackground=COLOR_FG_LIGHT, font=(FONT_FAMILY, 10), border=0, width=18, highlightthickness=0)
        self.entrada_filtro.pack(side=tk.LEFT, padx=6, pady=4)
        self.entrada_filtro.bind("<KeyRelease>", lambda event: self._filtrar_resultados_tabela())
        
        lbl_filter_icon = tk.Label(filter_input_frame, text="⏳", fg=COLOR_FG_MUTED, bg=COLOR_BG_INPUT, font=(FONT_FAMILY, 8))
        lbl_filter_icon.pack(side=tk.RIGHT, padx=6)
        
        # Histórico (Extremo direito)
        self.btn_hist = tk.Frame(frame_filtros_linha, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, cursor="hand2")
        self.btn_hist.pack(side=tk.RIGHT, fill=tk.Y)
        
        lbl_icon_hist = tk.Label(self.btn_hist, text="🕒", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 10))
        lbl_icon_hist.pack(side=tk.LEFT, padx=(10, 5), pady=5)
        
        lbl_title_hist = tk.Label(self.btn_hist, text="Histórico", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"))
        lbl_title_hist.pack(side=tk.LEFT, pady=5)
        
        lbl_arrow_hist = tk.Label(self.btn_hist, text="▼", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_arrow_hist.pack(side=tk.LEFT, padx=(5, 10), pady=5)
        
        self._bind_hover(self.btn_hist, [self.btn_hist, lbl_icon_hist, lbl_title_hist, lbl_arrow_hist])
        
        def post_hist_menu(event):
            self.menu_hist = tk.Menu(self, tearoff=0, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_ACCENT, activeforeground="#FFFFFF", bd=1, relief=tk.FLAT)
            from config import obter_historico
            self.historico_buscas = obter_historico()
            if not self.historico_buscas:
                self.menu_hist.add_command(label="(Histórico vazio)", state=tk.DISABLED)
            else:
                for h in self.historico_buscas:
                    self.menu_hist.add_command(label=h, command=lambda q=h: [self.entrada_busca.set(q), self._executar_busca()])
            self.menu_hist.post(self.btn_hist.winfo_rootx(), self.btn_hist.winfo_rooty() + self.btn_hist.winfo_height())
            
        self.btn_hist.bind("<Button-1>", post_hist_menu)
        lbl_icon_hist.bind("<Button-1>", post_hist_menu)
        lbl_title_hist.bind("<Button-1>", post_hist_menu)
        lbl_arrow_hist.bind("<Button-1>", post_hist_menu)

        # 5. Corpo principal — layout em duas colunas
        frame_corpo = tk.Frame(self, bg=COLOR_BG_DARKEST)
        frame_corpo.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 10))
        
        # Coluna esquerda: painel lateral
        self.painel_esquerdo = tk.Frame(frame_corpo, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, width=220)
        self.painel_esquerdo.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        self.painel_esquerdo.pack_propagate(False)
        
        # Coluna direita: área de resultados
        self.painel_direito = tk.Frame(frame_corpo, bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        self.painel_direito.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 6. Coluna esquerda — painel lateral
        # 6.1 Seção "Resumo da indexação"
        lbl_hdr_resumo = tk.Label(self.painel_esquerdo, text="RESUMO DA INDEXAÇÃO", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 7, "bold"))
        lbl_hdr_resumo.pack(anchor=tk.W, padx=12, pady=(15, 8))
        
        def criar_linha_estatistica(parent, icon, label_txt):
            row = tk.Frame(parent, bg=COLOR_BG_CARD)
            row.pack(fill=tk.X, padx=12, pady=3)
            badge = tk.Frame(row, bg=COLOR_BG_INPUT, width=22, height=22)
            badge.pack(side=tk.LEFT)
            badge.pack_propagate(False)
            lbl_i = tk.Label(badge, text=icon, fg=COLOR_FG_LIGHT, bg=COLOR_BG_INPUT, font=(FONT_FAMILY, 9))
            lbl_i.pack(expand=True)
            lbl_l = tk.Label(row, text=label_txt, fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
            lbl_l.pack(side=tk.LEFT, padx=6)
            lbl_val = tk.Label(row, text="---", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8, "bold"))
            lbl_val.pack(side=tk.RIGHT)
            return lbl_val
            
        self.val_manuais = criar_linha_estatistica(self.painel_esquerdo, "📄", "Manuais")
        self.val_paginas = criar_linha_estatistica(self.painel_esquerdo, "📖", "Páginas")
        self.val_data = criar_linha_estatistica(self.painel_esquerdo, "📅", "Atualizado")
        
        # Linha especial de status
        row_status = tk.Frame(self.painel_esquerdo, bg=COLOR_BG_CARD)
        row_status.pack(fill=tk.X, padx=12, pady=3)
        badge_s = tk.Frame(row_status, bg=COLOR_BG_INPUT, width=22, height=22)
        badge_s.pack(side=tk.LEFT)
        badge_s.pack_propagate(False)
        lbl_i_s = tk.Label(badge_s, text="●", fg=COLOR_GREEN, bg=COLOR_BG_INPUT, font=(FONT_FAMILY, 9))
        lbl_i_s.pack(expand=True)
        lbl_l_s = tk.Label(row_status, text="Status", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_l_s.pack(side=tk.LEFT, padx=6)
        self.val_status = tk.Label(row_status, text="Pronto", fg=COLOR_GREEN, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8, "bold"))
        self.val_status.pack(side=tk.RIGHT)

        # 6.2 Seção "Acessos rápidos"
        lbl_hdr_acesso = tk.Label(self.painel_esquerdo, text="ACESSOS RÁPIDOS", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 7, "bold"))
        lbl_hdr_acesso.pack(anchor=tk.W, padx=12, pady=(20, 8))
        
        def criar_link_rapido(parent, icon, text_txt, cmd):
            link = tk.Frame(parent, bg=COLOR_BG_CARD, cursor="hand2")
            link.pack(fill=tk.X, padx=12, pady=2)
            lbl_i = tk.Label(link, text=icon, fg=COLOR_ACCENT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9))
            lbl_i.pack(side=tk.LEFT, padx=(5, 6))
            lbl_t = tk.Label(link, text=text_txt, fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
            lbl_t.pack(side=tk.LEFT)
            
            def on_click(e): cmd()
            link.bind("<Button-1>", on_click)
            lbl_i.bind("<Button-1>", on_click)
            lbl_t.bind("<Button-1>", on_click)
            def on_enter(e):
                link.config(bg=COLOR_BG_HOVER)
                lbl_i.config(bg=COLOR_BG_HOVER)
                lbl_t.config(bg=COLOR_BG_HOVER)
            def on_leave(e):
                link.config(bg=COLOR_BG_CARD)
                lbl_i.config(bg=COLOR_BG_CARD)
                lbl_t.config(bg=COLOR_BG_CARD)
            link.bind("<Enter>", on_enter)
            link.bind("<Leave>", on_leave)
            lbl_i.bind("<Enter>", on_enter)
            lbl_t.bind("<Enter>", on_enter)
            
        criar_link_rapido(self.painel_esquerdo, "📂", "Selecionar Pasta", self._selecionar_pasta)
        criar_link_rapido(self.painel_esquerdo, "📊", "Diagnóstico Base", self._mostrar_diagnostico)
        criar_link_rapido(self.painel_esquerdo, "🛠️", "Manutenção Banco", self._mostrar_manutencao)
        criar_link_rapido(self.painel_esquerdo, "💡", "Guia de Uso", self._abrir_guia_uso)

        # 6.3 Bloco "Dicas" (rodapé do painel lateral)
        spacer_dica = tk.Frame(self.painel_esquerdo, bg=COLOR_BG_CARD)
        spacer_dica.pack(fill=tk.BOTH, expand=True)
        
        card_dica = tk.Frame(self.painel_esquerdo, bg="#1E293B", highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
        card_dica.pack(fill=tk.X, padx=12, pady=12, side=tk.BOTTOM)
        
        lbl_dica_hdr = tk.Label(card_dica, text="💡 Dica Útil", fg=COLOR_FG_LIGHT, bg="#1E293B", font=(FONT_FAMILY, 8, "bold"))
        lbl_dica_hdr.pack(anchor=tk.W, padx=10, pady=(8, 2))
        
        lbl_dica_txt = tk.Label(card_dica, text="Use aspas na busca para sequência exata. Mude para o Modo Preciso para refinar os resultados com operador AND.", fg=COLOR_FG_MUTED, bg="#1E293B", font=(FONT_FAMILY, 8), wraplength=170, justify=tk.LEFT)
        lbl_dica_txt.pack(anchor=tk.W, padx=10, pady=(0, 10))

        # 7. Coluna direita — área de resultados
        # 7.1 Cabeçalho da área de resultados
        frame_hdr_dir = tk.Frame(self.painel_direito, bg=COLOR_BG_CARD)
        frame_hdr_dir.pack(fill=tk.X, padx=15, pady=(15, 5))
        
        lbl_res_title = tk.Label(frame_hdr_dir, text="Resultados encontrados:", fg=COLOR_FG_LIGHT, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 9, "bold"))
        lbl_res_title.pack(side=tk.LEFT)
        
        self.badge_count_frame = tk.Frame(frame_hdr_dir, bg=COLOR_ACCENT, padx=6, pady=2)
        self.badge_count_frame.pack(side=tk.LEFT, padx=6)
        
        self.lbl_badge_count = tk.Label(self.badge_count_frame, text="0", fg="#FFFFFF", bg=COLOR_ACCENT, font=(FONT_FAMILY, 7, "bold"))
        self.lbl_badge_count.pack()
        
        lbl_ordenar = tk.Label(frame_hdr_dir, text="Ordenar por:", fg=COLOR_FG_MUTED, bg=COLOR_BG_CARD, font=(FONT_FAMILY, 8))
        lbl_ordenar.pack(side=tk.RIGHT, padx=5)
        
        self.combo_ordenar = ttk.Combobox(frame_hdr_dir, values=["Relevância (Padrão)"], state="readonly", width=18)
        self.combo_ordenar.set("Relevância (Padrão)")
        self.combo_ordenar.pack(side=tk.RIGHT)

        # 7.2 Tabela de resultados
        colunas = ("manual", "pagina", "relevancia", "trecho")
        self.tabela = ttk.Treeview(
            self.painel_direito, columns=colunas, show="headings", selectmode="browse", style="Custom.Treeview"
        )
        self.tabela.heading("manual", text="Manual")
        self.tabela.heading("pagina", text="Página")
        self.tabela.heading("relevancia", text="Relevância")
        self.tabela.heading("trecho", text="Trecho encontrado")
        self.tabela.column("manual", width=180, anchor=tk.W)
        self.tabela.column("pagina", width=60, anchor=tk.CENTER)
        self.tabela.column("relevancia", width=80, anchor=tk.CENTER)
        self.tabela.column("trecho", width=420, anchor=tk.W)
        
        scrollbar = ttk.Scrollbar(
            self.painel_direito, orient=tk.VERTICAL, command=self.tabela.yview
        )
        self.tabela.configure(yscrollcommand=scrollbar.set)
        
        self.tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(15, 0), pady=(5, 15))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 15), pady=(5, 15))

        # Configura menu de contexto
        self.menu_contexto = tk.Menu(self, tearoff=0, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_ACCENT, activeforeground="#FFFFFF")
        self.menu_contexto.add_command(label="Copiar trecho encontrado", command=self._copiar_trecho)
        self.menu_contexto.add_command(label="Copiar nome do manual e página", command=self._copiar_manual_pagina)
        self.menu_contexto.add_separator()
        self.menu_contexto.add_command(label="Abrir PDF na página", command=self._abrir_resultado_selecionado)
        
        self.tabela.bind("<Double-1>", lambda evento: self._abrir_resultado_selecionado())
        self.tabela.bind("<Button-3>", self._mostrar_menu_contexto)

        # Atalhos de teclado
        self.bind("<Control-f>", lambda event: self.entrada_busca.focus())
        self.bind("<Escape>", lambda event: self._limpar_busca())
        self.entrada_busca.focus()

        # 8. Barra inferior (rodapé fixo da janela)
        frame_rodape = tk.Frame(self, bg=COLOR_BG_DARKEST, height=45)
        frame_rodape.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=(0, 10))
        frame_rodape.pack_propagate(False)
        
        self.status_indicator = tk.Label(frame_rodape, text="●", fg=COLOR_GREEN, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 12))
        self.status_indicator.pack(side=tk.LEFT)
        
        self.status_var = tk.StringVar(value="Pronto. Selecione uma pasta de manuais para começar.")
        self.lbl_status = tk.Label(frame_rodape, textvariable=self.status_var, fg=COLOR_FG_MUTED, bg=COLOR_BG_DARKEST, font=(FONT_FAMILY, 9))
        self.lbl_status.pack(side=tk.LEFT, padx=8)
        
        # Botões do rodapé
        self.btn_more = tk.Button(frame_rodape, text="•••", bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, padx=10, pady=5, cursor="hand2")
        self.btn_more.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.menu_more = tk.Menu(self, tearoff=0, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_ACCENT, activeforeground="#FFFFFF", bd=1, relief=tk.FLAT)
        self.menu_more.add_command(label="Ver Diagnóstico...", command=self._mostrar_diagnostico)
        self.menu_more.add_command(label="Ver Manutenção...", command=self._mostrar_manutencao)
        self.menu_more.add_command(label="Ver Guia de Uso...", command=self._abrir_guia_uso)
        self.btn_more.bind("<Button-1>", lambda e: self.menu_more.post(self.btn_more.winfo_rootx(), self.btn_more.winfo_rooty() - 100))
        
        self.btn_copy_meta = tk.Button(frame_rodape, text="🔗 Copiar manual e página", command=self._copiar_manual_pagina, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, padx=12, pady=5, cursor="hand2")
        self.btn_copy_meta.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.btn_copy_snippet = tk.Button(frame_rodape, text="📋 Copiar trecho", command=self._copiar_trecho, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, padx=12, pady=5, cursor="hand2")
        self.btn_copy_snippet.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.btn_open_pdf = tk.Button(frame_rodape, text="📄 Abrir PDF na página", command=self._abrir_resultado_selecionado, bg=COLOR_ACCENT, fg="#FFFFFF", activebackground="#2563EB", activeforeground="#FFFFFF", bd=0, padx=15, pady=6, font=(FONT_FAMILY, 9, "bold"), cursor="hand2")
        self.btn_open_pdf.pack(side=tk.RIGHT)

        # 9. Barra de progresso (oculta por padrão, estilo dark)
        self.progresso = ttk.Progressbar(self, orient=tk.HORIZONTAL, mode="determinate", style="Custom.Horizontal.TProgressbar")

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag(self, event):
        if getattr(self, "is_maximized", False):
            return
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def _toggle_maximize(self) -> None:
        if getattr(self, "is_maximized", False):
            self.attributes("-zoomed", False)
            self.is_maximized = False
            self.btn_max.config(text="🗖")
        else:
            self.attributes("-zoomed", True)
            self.is_maximized = True
            self.btn_max.config(text="🗗")

    def _bind_hover(self, main_widget, elements):
        def on_enter(e):
            for elem in elements:
                elem.config(bg=COLOR_BG_HOVER)
        def on_leave(e):
            for elem in elements:
                elem.config(bg=COLOR_BG_CARD)
        for elem in elements:
            elem.bind("<Enter>", on_enter)
            elem.bind("<Leave>", on_leave)

    def _atualizar_estilo_modos(self):
        modo = self.modo_busca_var.get()
        
        if modo == "amplo":
            self.card_m_amplo.config(bg=COLOR_ACCENT_TINT, highlightbackground=COLOR_ACCENT)
            self.lbl_m_icon_a.config(bg=COLOR_ACCENT_TINT, fg=COLOR_ACCENT)
            self.txt_m_frame_a.config(bg=COLOR_ACCENT_TINT)
            self.lbl_m_title_a.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_a.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_MUTED)
        else:
            self.card_m_amplo.config(bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER)
            self.lbl_m_icon_a.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
            self.txt_m_frame_a.config(bg=COLOR_BG_CARD)
            self.lbl_m_title_a.config(bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_a.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
            
        if modo == "preciso":
            self.card_m_preciso.config(bg=COLOR_ACCENT_TINT, highlightbackground=COLOR_ACCENT)
            self.lbl_m_icon_p.config(bg=COLOR_ACCENT_TINT, fg=COLOR_ACCENT)
            self.txt_m_frame_p.config(bg=COLOR_ACCENT_TINT)
            self.lbl_m_title_p.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_p.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_MUTED)
        else:
            self.card_m_preciso.config(bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER)
            self.lbl_m_icon_p.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
            self.txt_m_frame_p.config(bg=COLOR_BG_CARD)
            self.lbl_m_title_p.config(bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_p.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
            
        if modo == "frase":
            self.card_m_frase.config(bg=COLOR_ACCENT_TINT, highlightbackground=COLOR_ACCENT)
            self.lbl_m_icon_f.config(bg=COLOR_ACCENT_TINT, fg=COLOR_ACCENT)
            self.txt_m_frame_f.config(bg=COLOR_ACCENT_TINT)
            self.lbl_m_title_f.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_f.config(bg=COLOR_ACCENT_TINT, fg=COLOR_FG_MUTED)
        else:
            self.card_m_frase.config(bg=COLOR_BG_CARD, highlightbackground=COLOR_BORDER)
            self.lbl_m_icon_f.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)
            self.txt_m_frame_f.config(bg=COLOR_BG_CARD)
            self.lbl_m_title_f.config(bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT)
            self.lbl_m_sub_f.config(bg=COLOR_BG_CARD, fg=COLOR_FG_MUTED)

    def _abrir_guia_uso(self) -> None:
        janela = tk.Toplevel(self)
        janela.title("Guia de Uso Rápido")
        janela.geometry("600x600")
        janela.transient(self)
        janela.grab_set()
        
        # Tema escuro na janela de ajuda
        janela.config(bg=COLOR_BG_DARKEST)
        
        frame = tk.Frame(janela, bg=COLOR_BG_DARKEST, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)
        
        text_area = tk.Text(frame, wrap=tk.WORD, font=(FONT_FAMILY, 10), bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, insertbackground=COLOR_FG_LIGHT, bd=0, highlightbackground=COLOR_BORDER, highlightthickness=1)
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_area.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_area.configure(yscrollcommand=scroll.set)
        
        guia_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "guia_rapido.md")
        if os.path.exists(guia_path):
            with open(guia_path, "r", encoding="utf-8") as f:
                content = f.read()
            text_area.insert(tk.END, content)
        else:
            text_area.insert(tk.END, "Guia rápido de uso não encontrado.")
        text_area.config(state=tk.DISABLED)
        
        btn_frame = tk.Frame(janela, bg=COLOR_BG_DARKEST, pady=10)
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="Fechar", command=janela.destroy, bg=COLOR_BG_CARD, fg=COLOR_FG_LIGHT, activebackground=COLOR_BG_HOVER, activeforeground=COLOR_FG_LIGHT, highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0, padx=15, pady=5, cursor="hand2").pack(side=tk.RIGHT, padx=15)

    def _atualizar_painel_esquerdo(self) -> None:
        try:
            with database.get_connection(DATABASE_PATH) as conn:
                total_docs = database.contar_documentos(conn)
                total_pags = database.contar_paginas(conn)
                cursor = conn.execute("SELECT MAX(indexed_at) AS ultima FROM documents;")
                row = cursor.fetchone()
                if row and row["ultima"]:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(row["ultima"])
                    data_str = dt.strftime("%d/%m %H:%M")
                else:
                    data_str = "Nunca"
            self.val_manuais.config(text=str(total_docs))
            self.val_paginas.config(text=str(total_pags))
            self.val_data.config(text=data_str)
        except Exception:
            pass

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
        self.label_pasta.config(text=pasta, fg=COLOR_FG_LIGHT)
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
        self._atualizar_painel_esquerdo()

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
                conn.commit()
            
            for linha in self.tabela.get_children():
                self.tabela.delete(linha)
            self.resultados_atuais = []
            
            self.status_var.set("Índice de busca limpo com sucesso.")
            self._atualizar_painel_esquerdo()
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
            self.lbl_badge_count.config(text="0")
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

        try:
            with database.get_connection(DATABASE_PATH) as conn:
                resultados = search.buscar(conn, consulta, modo=modo)
        except Exception as exc:
            messagebox.showerror("Erro na busca", str(exc))
            return

        self.resultados_atuais = resultados

        if not resultados:
            self.status_var.set("Nenhum resultado encontrado.")
            self.lbl_badge_count.config(text="0")
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
        self.lbl_badge_count.config(text=str(len(resultados)))

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
