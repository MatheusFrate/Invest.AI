"""
Interface Gráfica Moderna para Controle de Investimentos e DARF (FIIs e Ações)
Com suporte a Edição e Exclusão de operações cadastradas.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from datetime import datetime
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from invest_ai.core.engine import InvestmentEngine, Transaction
from invest_ai.services.quotes_service import fetch_all_quotes
from invest_ai.services.dividends_service import fetch_all_dividends, calculate_historical_dividends
from invest_ai.ui.charts import (
    create_allocation_by_class_figure,
    create_allocation_by_ticker_figure,
    create_monthly_dividends_figure,
    create_profitability_by_ticker_figure,
    create_sales_darf_summary_figure,
    create_total_return_pct_figure,
    create_total_return_breakdown_figure,
    attach_matplotlib_tooltip,
)
from invest_ai.services.excel_handler import (
    load_transactions_from_excel, 
    save_transaction_to_excel, 
    update_transaction_in_excel,
    delete_transaction_from_excel,
    load_paid_darfs,
    record_paid_darf,
    DEFAULT_EXCEL_PATH
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Tokens compartilhados de design (Light, Dark) para coesão visual entre base_window, desktop_app e charts
UI_COLORS = {
    "bg_app": ("#f8fafc", "#0f172a"),
    "bg_sidebar": ("#ffffff", "#111827"),
    "bg_surface": ("#ffffff", "#1e293b"),
    "bg_surface_alt": ("#f1f5f9", "#243044"),
    "bg_hover": ("#e2e8f0", "#334155"),
    "border": ("#e2e8f0", "#334155"),
    "border_strong": ("#cbd5e1", "#475569"),
    "text_primary": ("#0f172a", "#f8fafc"),
    "text_secondary": ("#475569", "#94a3b8"),
    "text_muted": ("#64748b", "#64748b"),
    "primary": "#6366f1",
    "primary_hover": "#4f46e5",
    "blue": "#3b82f6",
    "blue_hover": "#2563eb",
    "teal": "#0d9488",
    "teal_hover": "#0f766e",
    "success": "#10b981",
    "success_hover": "#059669",
    "success_text": ("#059669", "#34d399"),
    "success_tint": ("#ecfdf5", "#064e3b"),
    "danger": "#ef4444",
    "danger_hover": "#dc2626",
    "danger_text": ("#dc2626", "#f87171"),
    "danger_tint": ("#fef2f2", "#450a0a"),
    "warning": "#f59e0b",
    "warning_hover": "#d97706",
    "warning_text": ("#d97706", "#fbbf24"),
    "warning_tint": ("#fffbeb", "#451a03"),
    "info_tint": ("#eff6ff", "#172554"),
}

UI_FONTS = {
    "family": "Segoe UI",
    "title_xl": ("Segoe UI", 22, "bold"),
    "title_lg": ("Segoe UI", 20, "bold"),
    "section_md": ("Segoe UI", 15, "bold"),
    "kpi_val": ("Segoe UI", 18, "bold"),
    "kpi_lbl": ("Segoe UI", 11, "bold"),
    "body": ("Segoe UI", 13, "normal"),
    "body_bold": ("Segoe UI", 13, "bold"),
    "nav_btn": ("Segoe UI", 13, "bold"),
    "caption": ("Segoe UI", 11, "normal"),
}


class InvestApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Calculadora de Investimentos & DARF - FIIs e Ações")
        self.geometry("1180x760")
        self.minsize(1000, 680)
        self.configure(fg_color=UI_COLORS["bg_app"])

        self.engine = InvestmentEngine()
        self.transactions = []
        self.editing_tx_id = None  # None = Nova operação, int = Editando operação existente
        self.live_quotes = {}  # Cache de cotações B3 {ticker: {'price': float, 'var_dia': float}}
        self.is_fetching_quotes = False
        self.dividends_data = {}  # Cache de proventos B3 {ticker: [{...}, ...]}
        self.is_fetching_dividends = False
        self.charts_visible = True
        self.carteira_chart_mode = "Alocação"
        self.vendas_chart_visible = False
        self.rentab_charts_visible = True
        self._chart_figures = {}
        self._last_wallet = {}
        self._last_calc_res = {"wallet": {}, "tax_reports": [], "sales": []}
        self._last_dividends_calc = ([], {})
        self._empty_overlays = {}
        self._current_view = "carteira"

        # Variáveis de filtro e ordenação das tabelas
        self.carteira_filter_tipo = "Todos"
        self.carteira_sort_col = "ticker"
        self.carteira_sort_reverse = False
        self.rentab_filter_tipo = "Todos"
        self.rentab_sort_col = "retorno_total_pct"
        self.rentab_sort_reverse = True
        self.vendas_filter_ano = "Todos"
        self.proventos_filter_ano = "Todos"
        self.historico_sort_col = "id"
        self.historico_sort_reverse = False
        self.historico_filter_text = ""

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._configure_treeview_style()
        self._build_sidebar()
        self._build_main_panel()
        self.show_view("carteira")

        self.load_data()
        # Busca cotações e proventos automaticamente ao iniciar
        self.after(500, self.refresh_quotes_async)
        self.after(1000, self.refresh_dividends_async)

    def _is_dark_mode(self) -> bool:
        return ctk.get_appearance_mode().lower() == "dark"

    def _configure_treeview_dark_style(self) -> None:
        """Mantido por retrocompatibilidade; delega para _configure_treeview_style."""
        self._configure_treeview_style()

    def _configure_treeview_style(self) -> None:
        """Configura tema moderno ('clam') para ttk.Treeview e ttk.Scrollbar conforme Dark/Light."""
        dark = self._is_dark_mode()
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = "#1e293b" if dark else "#ffffff"
        fg = "#f8fafc" if dark else "#0f172a"
        sel_bg = "#312e81" if dark else "#e0e7ff"
        sel_fg = "#ffffff" if dark else "#1e1b4b"
        head_bg = "#0f172a" if dark else "#f1f5f9"
        head_fg = "#94a3b8" if dark else "#475569"
        head_active = "#1e293b" if dark else "#e2e8f0"
        scroll_bg = "#334155" if dark else "#cbd5e1"
        scroll_hover = "#475569" if dark else "#94a3b8"
        scroll_trough = "#0f172a" if dark else "#f1f5f9"
        scroll_arrow = "#94a3b8" if dark else "#475569"

        # Remove o elemento Treeview.field do tema clam para eliminar a borda branca 3D
        try:
            style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            background=bg,
            foreground=fg,
            fieldbackground=bg,
            relief="flat",
            borderwidth=0,
            lightcolor=bg,
            darkcolor=bg,
            bordercolor=bg,
            rowheight=32,
            font=(UI_FONTS["family"], 10),
        )
        style.map(
            "Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        style.configure(
            "Treeview.Heading",
            background=head_bg,
            foreground=head_fg,
            relief="flat",
            borderwidth=0,
            lightcolor=head_bg,
            darkcolor=head_bg,
            bordercolor=head_bg,
            padding=(8, 6),
            font=(UI_FONTS["family"], 10, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", head_active)],
            foreground=[("active", fg)],
        )
        for sb_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(
                sb_style,
                background=scroll_bg,
                troughcolor=scroll_trough,
                bordercolor=scroll_trough,
                lightcolor=scroll_trough,
                darkcolor=scroll_trough,
                arrowcolor=scroll_arrow,
                borderwidth=0,
                gripcount=0,
                relief="flat",
            )
            style.map(
                sb_style,
                background=[("active", scroll_hover)],
            )

        # Atualiza tags de zebra/semântica em todas as tabelas já criadas
        even_bg = "#1e293b" if dark else "#ffffff"
        odd_bg = "#243044" if dark else "#f8fafc"
        profit_fg = "#34d399" if dark else "#059669"
        loss_fg = "#f87171" if dark else "#dc2626"
        warn_fg = "#fbbf24" if dark else "#d97706"
        for attr in (
            "tree_carteira",
            "tree_darf",
            "tree_sales",
            "tree_proventos_mes",
            "tree_proventos_detalhe",
            "tree_rentabilidade",
            "tree_historico",
        ):
            tree = getattr(self, attr, None)
            if tree is not None:
                tree.tag_configure("even", background=even_bg)
                tree.tag_configure("odd", background=odd_bg)
                tree.tag_configure("profit", foreground=profit_fg)
                tree.tag_configure("loss", foreground=loss_fg)
                tree.tag_configure("warning", foreground=warn_fg)

    def _toggle_appearance_mode(self) -> None:
        """Alterna entre modo Escuro e Claro mantendo Treeviews sincronizadas."""
        new_mode = "Light" if self._is_dark_mode() else "Dark"
        ctk.set_appearance_mode(new_mode)
        self._configure_treeview_style()
        if hasattr(self, "btn_theme_toggle"):
            label = "🌙 Tema: Escuro" if new_mode == "Dark" else "☀️ Tema: Claro"
            self.btn_theme_toggle.configure(text=label)

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=232,
            corner_radius=0,
            fg_color=UI_COLORS["bg_sidebar"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_rowconfigure(8, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="📈 InvestDARF",
            font=ctk.CTkFont(*UI_FONTS["title_xl"]),
            text_color=UI_COLORS["text_primary"],
            anchor="w",
        )
        logo_label.grid(row=0, column=0, padx=20, pady=(24, 18), sticky="ew")

        nav_kwargs = dict(
            height=38,
            corner_radius=8,
            anchor="w",
            font=ctk.CTkFont(*UI_FONTS["nav_btn"]),
            fg_color="transparent",
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
        )

        self.btn_nav_carteira = ctk.CTkButton(
            self.sidebar_frame,
            text="📊  Carteira Atual",
            command=lambda: self.show_view("carteira"),
            **nav_kwargs,
        )
        self.btn_nav_carteira.grid(row=1, column=0, padx=16, pady=4, sticky="ew")

        self.btn_nav_vendas = ctk.CTkButton(
            self.sidebar_frame,
            text="💰  Vendas & DARF",
            command=lambda: self.show_view("vendas"),
            **nav_kwargs,
        )
        self.btn_nav_vendas.grid(row=2, column=0, padx=16, pady=4, sticky="ew")

        self.btn_nav_proventos = ctk.CTkButton(
            self.sidebar_frame,
            text="💵  Proventos Recebidos",
            command=lambda: self.show_view("proventos"),
            **nav_kwargs,
        )
        self.btn_nav_proventos.grid(row=3, column=0, padx=16, pady=4, sticky="ew")

        self.btn_nav_rentabilidade = ctk.CTkButton(
            self.sidebar_frame,
            text="📈  Rentabilidade Total",
            command=lambda: self.show_view("rentabilidade"),
            **nav_kwargs,
        )
        self.btn_nav_rentabilidade.grid(row=4, column=0, padx=16, pady=4, sticky="ew")

        self.btn_nav_nova = ctk.CTkButton(
            self.sidebar_frame,
            text="➕  Nova Operação",
            command=self.prepare_new_operation,
            height=38,
            corner_radius=8,
            anchor="w",
            font=ctk.CTkFont(*UI_FONTS["nav_btn"]),
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
            text_color="#ffffff",
        )
        self.btn_nav_nova.grid(row=5, column=0, padx=16, pady=(8, 4), sticky="ew")

        self.btn_nav_historico = ctk.CTkButton(
            self.sidebar_frame,
            text="📑  Extrato Completo",
            command=lambda: self.show_view("historico"),
            **nav_kwargs,
        )
        self.btn_nav_historico.grid(row=6, column=0, padx=16, pady=4, sticky="ew")

        # Rodapé da Sidebar
        divider = ctk.CTkFrame(self.sidebar_frame, height=1, fg_color=UI_COLORS["border"])
        divider.grid(row=8, column=0, padx=16, pady=(12, 8), sticky="sew")

        self.lbl_sync_status = ctk.CTkLabel(
            self.sidebar_frame,
            text="✅ Dados prontos",
            text_color=UI_COLORS["text_secondary"],
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            anchor="w",
        )
        self.lbl_sync_status.grid(row=9, column=0, padx=18, pady=(4, 2), sticky="ew")

        lbl_status = ctk.CTkLabel(
            self.sidebar_frame,
            text="Planilha: investimento.xlsx",
            text_color=UI_COLORS["text_muted"],
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            anchor="w",
        )
        lbl_status.grid(row=10, column=0, padx=18, pady=(0, 8), sticky="ew")

        self.btn_theme_toggle = ctk.CTkButton(
            self.sidebar_frame,
            text="🌙 Tema: Escuro",
            command=self._toggle_appearance_mode,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.btn_theme_toggle.grid(row=11, column=0, padx=16, pady=(0, 6), sticky="ew")

        btn_reload = ctk.CTkButton(
            self.sidebar_frame,
            text="🔄 Recarregar Dados",
            command=self.load_data,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        btn_reload.grid(row=12, column=0, padx=16, pady=(0, 18), sticky="ew")

    def _build_main_panel(self):
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.views = {
            "carteira": self._create_carteira_view(),
            "vendas": self._create_vendas_view(),
            "proventos": self._create_proventos_view(),
            "rentabilidade": self._create_rentabilidade_view(),
            "form_op": self._create_form_op_view(),
            "historico": self._create_historico_view()
        }

    def show_view(self, name: str):
        self._current_view = name
        for v_name, frame in self.views.items():
            if v_name == name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

        nav_map = {
            "carteira": getattr(self, "btn_nav_carteira", None),
            "vendas": getattr(self, "btn_nav_vendas", None),
            "proventos": getattr(self, "btn_nav_proventos", None),
            "rentabilidade": getattr(self, "btn_nav_rentabilidade", None),
            "historico": getattr(self, "btn_nav_historico", None),
            "copiloto": getattr(self, "btn_nav_copiloto", None),
        }
        for v_name, btn in nav_map.items():
            if btn is None:
                continue
            if v_name == name:
                btn.configure(
                    fg_color=UI_COLORS["primary"],
                    hover_color=UI_COLORS["primary_hover"],
                    text_color="#ffffff",
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=UI_COLORS["bg_hover"],
                    text_color=UI_COLORS["text_primary"],
                )

    def _attach_tree_scrollbars(self, container, tree: ttk.Treeview) -> None:
        """Anexa barras de rolagem vertical e horizontal a um ttk.Treeview dentro de container."""
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        y_scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

    def _setup_tree_tags_and_context_menu(
        self, tree: ttk.Treeview, ticker_col_idx: int | None = None, allow_crud: bool = False
    ) -> None:
        """Configura tags de zebra/semântica e menu de contexto (botão direito) no Treeview."""
        dark = self._is_dark_mode()
        tree.tag_configure("even", background="#1e293b" if dark else "#ffffff")
        tree.tag_configure("odd", background="#243044" if dark else "#f8fafc")
        tree.tag_configure("profit", foreground="#34d399" if dark else "#059669")
        tree.tag_configure("loss", foreground="#f87171" if dark else "#dc2626")
        tree.tag_configure("warning", foreground="#fbbf24" if dark else "#d97706")
        self._bind_tree_context_menu(tree, ticker_col_idx=ticker_col_idx, allow_crud=allow_crud)

    def _bind_tree_context_menu(
        self, tree: ttk.Treeview, ticker_col_idx: int | None = None, allow_crud: bool = False
    ) -> None:
        """Associa menu de contexto com cópia e ações de edição/exclusão ao botão direito."""
        menu = tk.Menu(
            tree,
            tearoff=0,
            bg="#1e293b",
            fg="#f8fafc",
            activebackground=UI_COLORS["primary"],
            activeforeground="#ffffff",
            bd=0,
        )

        def _copy_text(texto: str):
            self.clipboard_clear()
            self.clipboard_append(texto)

        def _on_right_click(event):
            row_id = tree.identify_row(event.y)
            if not row_id:
                return
            tree.selection_set(row_id)
            vals = tree.item(row_id, "values") or ()
            menu.delete(0, "end")

            if ticker_col_idx is not None and 0 <= ticker_col_idx < len(vals):
                ticker_val = str(vals[ticker_col_idx]).strip()
                if ticker_val:
                    menu.add_command(
                        label=f"📋 Copiar Ticker ({ticker_val})",
                        command=lambda t=ticker_val: _copy_text(t),
                    )

            if vals:
                linha_txt = " | ".join(str(v) for v in vals)
                menu.add_command(
                    label="📋 Copiar Linha",
                    command=lambda s=linha_txt: _copy_text(s),
                )

            if allow_crud:
                menu.add_separator()
                menu.add_command(label="✏️ Editar Operação", command=self.edit_selected_operation)
                menu.add_command(label="🗑️ Excluir Operação", command=self.delete_selected_operation)

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        tree.bind("<Button-3>", _on_right_click)

    def _create_page_header(self, parent, title_text: str, subtitle_text: str) -> ctk.CTkFrame:
        """Cria cabeçalho padronizado com título, subtítulo e área de ações à direita."""
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w", padx=(0, 12))

        title = ctk.CTkLabel(
            title_box,
            text=title_text,
            font=ctk.CTkFont(*UI_FONTS["title_lg"]),
            text_color=UI_COLORS["text_primary"],
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            title_box,
            text=subtitle_text,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            text_color=UI_COLORS["text_secondary"],
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))
        return header

    def _create_table_card(self, parent, height: int | None = None) -> ctk.CTkFrame:
        """Cria container elevado com borda sutil para abrigar Treeview e empty state."""
        kwargs = dict(
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        if height is not None:
            kwargs["height"] = height
        card = ctk.CTkFrame(parent, **kwargs)
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        return card

    def _register_empty_state(
        self, key: str, container: ctk.CTkFrame, title: str, subtitle: str
    ) -> None:
        """Registra um overlay de estado vazio centralizado sobre o container da tabela."""
        overlay = ctk.CTkFrame(container, fg_color=UI_COLORS["bg_surface"], corner_radius=8)
        lbl_title = ctk.CTkLabel(
            overlay,
            text=title,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_primary"],
        )
        lbl_title.pack(pady=(8, 2))
        lbl_sub = ctk.CTkLabel(
            overlay,
            text=subtitle,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_sub.pack(pady=(0, 8))
        self._empty_overlays[key] = overlay

    def _set_empty_state(self, key: str, is_empty: bool) -> None:
        """Exibe ou oculta o overlay de estado vazio registrado para uma tabela."""
        overlay = self._empty_overlays.get(key)
        if overlay is None:
            return
        if is_empty:
            overlay.place(relx=0.5, rely=0.55, anchor="center")
            overlay.lift()
        else:
            overlay.place_forget()

    # -------------------------------------------------------------
    # VIEW: CARTEIRA ATUAL
    # -------------------------------------------------------------
    def _create_carteira_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=0)
        frame.grid_rowconfigure(3, weight=0)
        frame.grid_rowconfigure(4, weight=1)

        # Cabeçalho com Título, Toggle de Gráficos e Botão de Atualizar B3
        header_frame = self._create_page_header(
            frame,
            "Carteira Atual",
            "Posição consolidada em tempo real com preço médio e cotações B3",
        )

        self.btn_toggle_charts = ctk.CTkButton(
            header_frame,
            text="📊 Ocultar Gráficos",
            command=self._toggle_carteira_charts,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.btn_toggle_charts.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.btn_refresh_quotes = ctk.CTkButton(
            header_frame,
            text="📡 Atualizar B3",
            command=self.refresh_quotes_async,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["blue"],
            hover_color=UI_COLORS["blue_hover"],
            text_color="#ffffff",
        )
        self.btn_refresh_quotes.grid(row=0, column=2, sticky="e")

        # Cards de Resumo Expandidos (Total Investido, Patrimônio Atual, Lucro/Prejuízo, Prejuízo Acum. IR)
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_total_investido = self._create_stat_card(cards_frame, 0, "TOTAL INVESTIDO", "R$ 0,00", UI_COLORS["blue"])
        self.card_patrimonio_atual = self._create_stat_card(cards_frame, 1, "PATRIMÔNIO ATUAL", "R$ 0,00", UI_COLORS["success"])
        self.card_lucro_total = self._create_stat_card(cards_frame, 2, "LUCRO / PREJUÍZO", "R$ 0,00", UI_COLORS["primary"])
        self.card_prejuizo_acum = self._create_stat_card(cards_frame, 3, "PREJUÍZO ACUM. (IR)", "R$ 0,00", UI_COLORS["warning"])

        # Gráficos da Carteira (Rosca por Classe + Barras por Ativo / Rentabilidade)
        self.carteira_charts_frame = ctk.CTkFrame(frame, height=230, fg_color="transparent")
        self.carteira_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.carteira_charts_frame.grid_propagate(False)
        self.carteira_charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.carteira_charts_frame.grid_rowconfigure(0, weight=1)

        self.chart_class_container = ctk.CTkFrame(
            self.carteira_charts_frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.chart_class_container.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.chart_ticker_container = ctk.CTkFrame(
            self.carteira_charts_frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.chart_ticker_container.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # Barra de Filtro Rápido por Classe de Ativo e Seletor de Gráfico
        filter_bar = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        filter_bar.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        filter_bar.grid_columnconfigure(1, weight=1)

        lbl_filtro_c = ctk.CTkLabel(
            filter_bar,
            text="Classe:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_filtro_c.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)

        self.seg_filtro_carteira_tipo = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Todos", "FII", "AÇÃO", "ETF", "BDR"],
            command=self._on_carteira_tipo_filter_changed,
            height=30,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            selected_color=UI_COLORS["primary"],
            selected_hover_color=UI_COLORS["primary_hover"],
            unselected_color=UI_COLORS["bg_surface_alt"],
            unselected_hover_color=UI_COLORS["bg_hover"],
        )
        self.seg_filtro_carteira_tipo.set("Todos")
        self.seg_filtro_carteira_tipo.grid(row=0, column=1, sticky="w", pady=8)

        lbl_modo_g = ctk.CTkLabel(
            filter_bar,
            text="Gráfico:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_modo_g.grid(row=0, column=2, sticky="e", padx=(12, 8), pady=8)

        self.seg_carteira_chart_mode = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Alocação", "Rentabilidade"],
            command=self._on_carteira_chart_mode_changed,
            height=30,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            selected_color=UI_COLORS["primary"],
            selected_hover_color=UI_COLORS["primary_hover"],
            unselected_color=UI_COLORS["bg_surface_alt"],
            unselected_hover_color=UI_COLORS["bg_hover"],
        )
        self.seg_carteira_chart_mode.set("Alocação")
        self.seg_carteira_chart_mode.grid(row=0, column=3, sticky="e", padx=(0, 12), pady=8)

        tbl_container = self._create_table_card(frame)
        tbl_container.grid(row=4, column=0, sticky="nsew")

        cols = ("ticker", "tipo", "quantidade", "preco_medio", "preco_atual", "total_investido", "patrimonio_atual", "lucro_prej", "rentabilidade")
        self.tree_carteira = ttk.Treeview(tbl_container, columns=cols, show="headings", selectmode="browse", height=8)
        carteira_headings = {
            "ticker": "Ativo / Cota",
            "tipo": "Tipo",
            "quantidade": "Qtd",
            "preco_medio": "Preço Médio (PM)",
            "preco_atual": "Preço Atual (B3)",
            "total_investido": "Total Investido",
            "patrimonio_atual": "Patrimônio Atual",
            "lucro_prej": "Lucro/Prejuízo",
            "rentabilidade": "Rentab. (%)",
        }
        for col_id, col_title in carteira_headings.items():
            suf = " ▲" if col_id == "ticker" else " ↕"
            self.tree_carteira.heading(
                col_id,
                text=f"{col_title}{suf}",
                command=lambda c=col_id: self._sort_carteira(c),
            )

        self.tree_carteira.column("ticker", width=95, minwidth=85, anchor="center")
        self.tree_carteira.column("tipo", width=75, minwidth=65, anchor="center")
        self.tree_carteira.column("quantidade", width=85, minwidth=70, anchor="e")
        self.tree_carteira.column("preco_medio", width=120, minwidth=105, anchor="e")
        self.tree_carteira.column("preco_atual", width=120, minwidth=105, anchor="e")
        self.tree_carteira.column("total_investido", width=125, minwidth=110, anchor="e")
        self.tree_carteira.column("patrimonio_atual", width=130, minwidth=115, anchor="e")
        self.tree_carteira.column("lucro_prej", width=125, minwidth=110, anchor="e")
        self.tree_carteira.column("rentabilidade", width=105, minwidth=95, anchor="e")

        self._attach_tree_scrollbars(tbl_container, self.tree_carteira)
        self._setup_tree_tags_and_context_menu(self.tree_carteira, ticker_col_idx=0)
        self._register_empty_state(
            "carteira",
            tbl_container,
            "Nenhum ativo encontrado na carteira",
            "Cadastre uma compra em Nova Operação ou ajuste o filtro de classe.",
        )

        return frame

    # -------------------------------------------------------------
    # VIEW: VENDAS & DARF
    # -------------------------------------------------------------
    def _create_vendas_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=0)
        frame.grid_rowconfigure(4, weight=1)
        frame.grid_rowconfigure(6, weight=2)

        header_frame = self._create_page_header(
            frame,
            "Apuração de Vendas & DARF",
            "Cálculo mensal de imposto, compensação de prejuízos e controle de DARFs",
        )

        self.btn_toggle_vendas_chart = ctk.CTkButton(
            header_frame,
            text="📊 Mostrar Gráfico",
            command=self._toggle_vendas_chart,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.btn_toggle_vendas_chart.grid(row=0, column=1, sticky="e")

        info_frame = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["info_tint"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        info_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        info_lbl = ctk.CTkLabel(
            info_frame,
            text="Regra dos FIIs: Alíquota de 20% sobre o lucro líquido. Prejuízo acumulado abate lucros futuros.\n"
                 "Regra de Ações: Vendas totais até R$ 20.000 no mês são isentas de IR no swing trade.",
            justify="left",
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            text_color=UI_COLORS["text_primary"],
        )
        info_lbl.pack(padx=14, pady=10, anchor="w")

        # Subcabeçalho com Título, Filtro de Ano e Botão de Marcar DARF Pago
        sub1_box = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        sub1_box.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        sub1_box.grid_columnconfigure(0, weight=1)

        lbl_sub1 = ctk.CTkLabel(
            sub1_box,
            text="📅 Resumo Fiscal por Mês",
            font=ctk.CTkFont(*UI_FONTS["section_md"]),
            text_color=UI_COLORS["text_primary"],
            anchor="w",
        )
        lbl_sub1.grid(row=0, column=0, sticky="w", padx=(14, 8), pady=8)

        lbl_ano_v = ctk.CTkLabel(
            sub1_box,
            text="Ano:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_ano_v.grid(row=0, column=1, sticky="e", padx=(0, 6), pady=8)

        self.opt_filtro_vendas_ano = ctk.CTkOptionMenu(
            sub1_box,
            values=["Todos"],
            command=self._on_vendas_ano_filter_changed,
            width=105,
            height=30,
            corner_radius=8,
            fg_color=UI_COLORS["bg_surface_alt"],
            button_color=UI_COLORS["primary"],
            button_hover_color=UI_COLORS["primary_hover"],
            text_color=UI_COLORS["text_primary"],
        )
        self.opt_filtro_vendas_ano.set("Todos")
        self.opt_filtro_vendas_ano.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=8)

        btn_pagar_darf = ctk.CTkButton(
            sub1_box,
            text="🧾 Marcar DARF Pago",
            command=self.mark_darf_as_paid,
            height=30,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
            text_color="#ffffff",
        )
        btn_pagar_darf.grid(row=0, column=3, sticky="e", padx=(0, 12), pady=8)

        # Gráfico Opcional de Resultado vs. DARF (oculto por padrão para preservar espaço vertical)
        self.vendas_chart_frame = ctk.CTkFrame(
            frame,
            height=175,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.vendas_chart_frame.grid_propagate(False)

        tbl_darf_container = self._create_table_card(frame, height=140)
        tbl_darf_container.grid(row=4, column=0, sticky="nsew", pady=(0, 12))

        darf_cols = ("mes", "tipo", "total_vendas", "resultado", "prej_compensado", "base_calc", "imposto_devido", "prej_acumulado", "status_pgto")
        self.tree_darf = ttk.Treeview(tbl_darf_container, columns=darf_cols, show="headings", selectmode="browse", height=5)
        self.tree_darf.heading("mes", text="Mês/Ano")
        self.tree_darf.heading("tipo", text="Tipo")
        self.tree_darf.heading("total_vendas", text="Total Vendido")
        self.tree_darf.heading("resultado", text="Lucro/Prejuízo")
        self.tree_darf.heading("prej_compensado", text="Prej. Compensado")
        self.tree_darf.heading("base_calc", text="Base de Cálculo")
        self.tree_darf.heading("imposto_devido", text="DARF Apurado")
        self.tree_darf.heading("prej_acumulado", text="Prejuízo Acumulado")
        self.tree_darf.heading("status_pgto", text="Situação DARF")

        for c in darf_cols:
            self.tree_darf.column(c, anchor="center" if c in ["mes", "tipo", "status_pgto"] else "e", width=110, minwidth=95)
        self.tree_darf.column("status_pgto", width=135, minwidth=115)

        self._attach_tree_scrollbars(tbl_darf_container, self.tree_darf)
        self._setup_tree_tags_and_context_menu(self.tree_darf, ticker_col_idx=None)
        self._register_empty_state(
            "darf",
            tbl_darf_container,
            "Nenhuma apuração fiscal no período",
            "Registre uma venda ou altere o filtro de ano acima.",
        )

        lbl_sub2 = ctk.CTkLabel(
            frame,
            text="🧾 Histórico Detalhado de Vendas",
            font=ctk.CTkFont(*UI_FONTS["section_md"]),
            text_color=UI_COLORS["text_primary"],
        )
        lbl_sub2.grid(row=5, column=0, sticky="w", pady=(2, 6))

        tbl_sales_container = self._create_table_card(frame, height=180)
        tbl_sales_container.grid(row=6, column=0, sticky="nsew")

        sale_cols = ("data", "ticker", "tipo", "qtd", "pm_compra", "preco_venda", "total_venda", "resultado")
        self.tree_sales = ttk.Treeview(tbl_sales_container, columns=sale_cols, show="headings", selectmode="browse", height=8)
        self.tree_sales.heading("data", text="Data")
        self.tree_sales.heading("ticker", text="Ativo")
        self.tree_sales.heading("tipo", text="Tipo")
        self.tree_sales.heading("qtd", text="Qtd")
        self.tree_sales.heading("pm_compra", text="PM de Compra")
        self.tree_sales.heading("preco_venda", text="Preço Venda")
        self.tree_sales.heading("total_venda", text="Valor Venda")
        self.tree_sales.heading("resultado", text="Resultado")

        for c in sale_cols:
            self.tree_sales.column(c, anchor="center" if c in ["data", "ticker", "tipo"] else "e", width=105, minwidth=90)

        self._attach_tree_scrollbars(tbl_sales_container, self.tree_sales)
        self._setup_tree_tags_and_context_menu(self.tree_sales, ticker_col_idx=1)
        self._register_empty_state(
            "sales",
            tbl_sales_container,
            "Nenhuma venda registrada",
            "Quando houver vendas cadastradas, o detalhamento aparecerá aqui.",
        )

        return frame

    # -------------------------------------------------------------
    # VIEW: PROVENTOS & DIVIDENDOS RECEBIDOS
    # -------------------------------------------------------------
    def _create_proventos_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=0)
        frame.grid_rowconfigure(4, weight=1)
        frame.grid_rowconfigure(6, weight=2)

        # Cabeçalho com Título e Botão de Consulta de Proventos
        header_frame = self._create_page_header(
            frame,
            "Proventos & Dividendos",
            "Rendimentos mensais, Yield on Cost e histórico oficial por ativo",
        )

        self.btn_refresh_divs = ctk.CTkButton(
            header_frame,
            text="📡 Atualizar Proventos",
            command=self.refresh_dividends_async,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
            text_color="#ffffff",
        )
        self.btn_refresh_divs.grid(row=0, column=1, sticky="e")

        # Cards de Resumo de Proventos
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.card_total_proventos = self._create_stat_card(cards_frame, 0, "TOTAL RECEBIDO (HISTÓRICO)", "R$ 0,00", UI_COLORS["success"])
        self.card_media_mensal = self._create_stat_card(cards_frame, 1, "MÉDIA MENSAL (12M)", "R$ 0,00", UI_COLORS["blue"])
        self.card_yield_medio = self._create_stat_card(cards_frame, 2, "YIELD ON COST (12M)", "0.00%", UI_COLORS["warning"])

        # Gráfico de Evolução Mensal de Proventos
        self.proventos_chart_frame = ctk.CTkFrame(
            frame,
            height=205,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.proventos_chart_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.proventos_chart_frame.grid_propagate(False)

        # Tabela 1: Resumo Mensal de Proventos + Filtro por Ano
        sub1_frame = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        sub1_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        sub1_frame.grid_columnconfigure(0, weight=1)

        lbl_sub1 = ctk.CTkLabel(
            sub1_frame,
            text="📅 Rendimentos Recebidos por Mês",
            font=ctk.CTkFont(*UI_FONTS["section_md"]),
            text_color=UI_COLORS["text_primary"],
            anchor="w",
        )
        lbl_sub1.grid(row=0, column=0, sticky="w", padx=(14, 8), pady=8)

        lbl_ano_p = ctk.CTkLabel(
            sub1_frame,
            text="Ano:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_ano_p.grid(row=0, column=1, sticky="e", padx=(0, 6), pady=8)

        self.opt_filtro_proventos_ano = ctk.CTkOptionMenu(
            sub1_frame,
            values=["Todos"],
            command=self._on_proventos_ano_filter_changed,
            width=105,
            height=30,
            corner_radius=8,
            fg_color=UI_COLORS["bg_surface_alt"],
            button_color=UI_COLORS["primary"],
            button_hover_color=UI_COLORS["primary_hover"],
            text_color=UI_COLORS["text_primary"],
        )
        self.opt_filtro_proventos_ano.set("Todos")
        self.opt_filtro_proventos_ano.grid(row=0, column=2, sticky="e", padx=(0, 12), pady=8)

        tbl_month_container = self._create_table_card(frame, height=130)
        tbl_month_container.grid(row=4, column=0, sticky="nsew", pady=(0, 12))

        month_cols = ("mes", "total_recebido", "ativos_pagadores", "yield_mes")
        self.tree_proventos_mes = ttk.Treeview(tbl_month_container, columns=month_cols, show="headings", selectmode="browse", height=4)
        self.tree_proventos_mes.heading("mes", text="Mês/Ano")
        self.tree_proventos_mes.heading("total_recebido", text="Total Recebido (R$)")
        self.tree_proventos_mes.heading("ativos_pagadores", text="Qtd Ativos Pagadores")
        self.tree_proventos_mes.heading("yield_mes", text="Yield no Mês (%)")

        self.tree_proventos_mes.column("mes", anchor="center", width=120, minwidth=110)
        self.tree_proventos_mes.column("total_recebido", anchor="e", width=150, minwidth=110)
        self.tree_proventos_mes.column("ativos_pagadores", anchor="center", width=150, minwidth=110)
        self.tree_proventos_mes.column("yield_mes", anchor="e", width=130, minwidth=110)

        self._attach_tree_scrollbars(tbl_month_container, self.tree_proventos_mes)
        self._setup_tree_tags_and_context_menu(self.tree_proventos_mes, ticker_col_idx=None)
        self._register_empty_state(
            "proventos_mes",
            tbl_month_container,
            "Nenhum provento mensal no período",
            "Clique em Atualizar Proventos ou selecione outro ano.",
        )

        # Tabela 2: Detalhamento por Ativo / Pagamento
        lbl_sub2 = ctk.CTkLabel(
            frame,
            text="🧾 Detalhamento por Ativo e Pagamento Oficial",
            font=ctk.CTkFont(*UI_FONTS["section_md"]),
            text_color=UI_COLORS["text_primary"],
        )
        lbl_sub2.grid(row=5, column=0, sticky="w", pady=(2, 6))

        tbl_divs_container = self._create_table_card(frame, height=160)
        tbl_divs_container.grid(row=6, column=0, sticky="nsew")

        div_cols = ("data", "ticker", "qtd_cotas", "valor_cota", "total_pago")
        self.tree_proventos_detalhe = ttk.Treeview(tbl_divs_container, columns=div_cols, show="headings", selectmode="browse", height=6)
        self.tree_proventos_detalhe.heading("data", text="Data / Mês")
        self.tree_proventos_detalhe.heading("ticker", text="Ativo / Cota")
        self.tree_proventos_detalhe.heading("qtd_cotas", text="Qtd Cotas")
        self.tree_proventos_detalhe.heading("valor_cota", text="Provento / Cota")
        self.tree_proventos_detalhe.heading("total_pago", text="Total Recebido")

        self.tree_proventos_detalhe.column("data", anchor="center", width=120, minwidth=110)
        self.tree_proventos_detalhe.column("ticker", anchor="center", width=120, minwidth=110)
        self.tree_proventos_detalhe.column("qtd_cotas", anchor="e", width=120, minwidth=110)
        self.tree_proventos_detalhe.column("valor_cota", anchor="e", width=130, minwidth=110)
        self.tree_proventos_detalhe.column("total_pago", anchor="e", width=140, minwidth=110)

        self._attach_tree_scrollbars(tbl_divs_container, self.tree_proventos_detalhe)
        self._setup_tree_tags_and_context_menu(self.tree_proventos_detalhe, ticker_col_idx=1)
        self._register_empty_state(
            "proventos_detalhe",
            tbl_divs_container,
            "Nenhum pagamento detalhado",
            "Os pagamentos individuais por ativo aparecerão aqui após sincronizar.",
        )

        self._render_proventos_chart({})
        return frame

    # -------------------------------------------------------------
    # VIEW: RENTABILIDADE TOTAL (VALORIZAÇÃO DA COTA + PROVENTOS)
    # -------------------------------------------------------------
    def _create_rentabilidade_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=0)
        frame.grid_rowconfigure(3, weight=0)
        frame.grid_rowconfigure(4, weight=1)

        # Cabeçalho
        header_frame = self._create_page_header(
            frame,
            "Rentabilidade Total (Cota + Proventos)",
            "Retorno consolidado somando valorização de mercado e proventos recebidos",
        )

        self.btn_toggle_rentab_charts = ctk.CTkButton(
            header_frame,
            text="📊 Ocultar Gráficos",
            command=self._toggle_rentab_charts,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.btn_toggle_rentab_charts.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.btn_sync_rentab = ctk.CTkButton(
            header_frame,
            text="📡 Atualizar Dados",
            command=self._sync_all_for_rentabilidade,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["teal"],
            hover_color=UI_COLORS["teal_hover"],
            text_color="#ffffff",
        )
        self.btn_sync_rentab.grid(row=0, column=2, sticky="e")

        # Cards de Resumo Consolidado (4 colunas)
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_rentab_investido = self._create_stat_card(cards_frame, 0, "TOTAL INVESTIDO", "R$ 0,00", UI_COLORS["blue"])
        self.card_rentab_valorizacao = self._create_stat_card(cards_frame, 1, "VALORIZAÇÃO DA COTA", "R$ 0,00", UI_COLORS["primary"])
        self.card_rentab_proventos = self._create_stat_card(cards_frame, 2, "PROVENTOS ACUMULADOS", "R$ 0,00", UI_COLORS["success"])
        self.card_rentab_total = self._create_stat_card(cards_frame, 3, "RETORNO TOTAL", "R$ 0,00", UI_COLORS["teal"])

        # Gráficos (Composição Cota vs. Proventos + Retorno Total %)
        self.rentab_charts_frame = ctk.CTkFrame(frame, height=225, fg_color="transparent")
        self.rentab_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.rentab_charts_frame.grid_propagate(False)
        self.rentab_charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.rentab_charts_frame.grid_rowconfigure(0, weight=1)

        self.chart_rentab_breakdown_container = ctk.CTkFrame(
            self.rentab_charts_frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.chart_rentab_breakdown_container.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.chart_rentab_pct_container = ctk.CTkFrame(
            self.rentab_charts_frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.chart_rentab_pct_container.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # Barra de Filtro Rápido por Classe
        filter_bar = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        filter_bar.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        filter_bar.grid_columnconfigure(1, weight=1)

        lbl_filtro_r = ctk.CTkLabel(
            filter_bar,
            text="Classe:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_filtro_r.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)

        self.seg_filtro_rentab_tipo = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Todos", "FII", "AÇÃO", "ETF", "BDR"],
            command=self._on_rentab_tipo_filter_changed,
            height=30,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            selected_color=UI_COLORS["primary"],
            selected_hover_color=UI_COLORS["primary_hover"],
            unselected_color=UI_COLORS["bg_surface_alt"],
            unselected_hover_color=UI_COLORS["bg_hover"],
        )
        self.seg_filtro_rentab_tipo.set("Todos")
        self.seg_filtro_rentab_tipo.grid(row=0, column=1, sticky="w", pady=8)

        # Tabela Consolidada
        tbl_container = self._create_table_card(frame)
        tbl_container.grid(row=4, column=0, sticky="nsew")

        cols = (
            "ticker",
            "tipo",
            "investido",
            "patrimonio",
            "val_cota",
            "val_cota_pct",
            "proventos",
            "yoc_pct",
            "retorno_total",
            "retorno_total_pct",
        )
        self.tree_rentabilidade = ttk.Treeview(
            tbl_container, columns=cols, show="headings", selectmode="browse", height=8
        )
        rentab_headings = {
            "ticker": "Ativo / Cota",
            "tipo": "Tipo",
            "investido": "Total Investido",
            "patrimonio": "Patrimônio Atual",
            "val_cota": "Valoriz. Cota (R$)",
            "val_cota_pct": "Valoriz. (%)",
            "proventos": "Proventos (R$)",
            "yoc_pct": "Yield s/ Custo",
            "retorno_total": "Retorno Total (R$)",
            "retorno_total_pct": "Retorno Total (%)",
        }
        for col_id, col_title in rentab_headings.items():
            suf = " ▼" if col_id == "retorno_total_pct" else " ↕"
            self.tree_rentabilidade.heading(
                col_id,
                text=f"{col_title}{suf}",
                command=lambda c=col_id: self._sort_rentabilidade(c),
            )

        self.tree_rentabilidade.column("ticker", width=90, minwidth=80, anchor="center")
        self.tree_rentabilidade.column("tipo", width=70, minwidth=60, anchor="center")
        self.tree_rentabilidade.column("investido", width=115, minwidth=100, anchor="e")
        self.tree_rentabilidade.column("patrimonio", width=120, minwidth=105, anchor="e")
        self.tree_rentabilidade.column("val_cota", width=125, minwidth=105, anchor="e")
        self.tree_rentabilidade.column("val_cota_pct", width=95, minwidth=85, anchor="e")
        self.tree_rentabilidade.column("proventos", width=115, minwidth=100, anchor="e")
        self.tree_rentabilidade.column("yoc_pct", width=105, minwidth=95, anchor="e")
        self.tree_rentabilidade.column("retorno_total", width=130, minwidth=110, anchor="e")
        self.tree_rentabilidade.column("retorno_total_pct", width=125, minwidth=105, anchor="e")

        self._attach_tree_scrollbars(tbl_container, self.tree_rentabilidade)
        self._setup_tree_tags_and_context_menu(self.tree_rentabilidade, ticker_col_idx=0)
        self._register_empty_state(
            "rentabilidade",
            tbl_container,
            "Nenhum ativo para exibir rentabilidade",
            "Ajuste o filtro de classe ou atualize os dados da B3.",
        )

        self._render_rentab_charts({}, {}, {})
        return frame

    # -------------------------------------------------------------
    # VIEW: FORMULÁRIO OPERAÇÃO (NOVA / EDITAR)
    # -------------------------------------------------------------
    def _create_form_op_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        header_frame = self._create_page_header(
            frame,
            "Cadastrar Nova Movimentação",
            "Registre compras ou vendas de FIIs, Ações e ETFs com cálculo automático",
        )
        # Mantém referência para atualização dinâmica do título em preparar/editar operação
        self.lbl_form_title = header_frame.winfo_children()[0].winfo_children()[0]

        form = ctk.CTkFrame(
            frame,
            width=660,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=14,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        form.grid(row=1, column=0, sticky="n", pady=8, padx=20)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        fields = [
            ("Código do Ativo / Cota:", "entry_cota", "Ex: MXRF11, PETR4"),
            ("Tipo de Ativo:", "opt_tag", ["fii", "ação", "etf"]),
            ("Tipo de Operação:", "opt_operacao", ["compra", "venda"]),
            ("Quantidade de Cotas:", "entry_qtd", "Ex: 10"),
            ("Valor Total Gasto/Recebido (R$):", "entry_total", "Ex: 102.50 (Valor da nota)"),
            ("Preço por Cota (R$) [Automático]:", "entry_unit", "Calculado automaticamente"),
            ("Data (DD/MM/AAAA) [Opcional]:", "entry_data", datetime.now().strftime("%d/%m/%Y")),
        ]

        self.form_inputs = {}

        for idx, (label_text, key, default) in enumerate(fields):
            lbl = ctk.CTkLabel(
                form,
                text=label_text,
                font=ctk.CTkFont(*UI_FONTS["body_bold"]),
                text_color=UI_COLORS["text_primary"],
            )
            lbl.grid(row=idx, column=0, padx=(24, 16), pady=(14 if idx == 0 else 8, 8), sticky="w")

            if isinstance(default, list):
                widget = ctk.CTkOptionMenu(
                    form,
                    values=default,
                    width=260,
                    height=36,
                    corner_radius=8,
                    fg_color=UI_COLORS["bg_surface_alt"],
                    button_color=UI_COLORS["primary"],
                    button_hover_color=UI_COLORS["primary_hover"],
                    text_color=UI_COLORS["text_primary"],
                )
                widget.set(default[0])
            else:
                widget = ctk.CTkEntry(
                    form,
                    placeholder_text=default,
                    width=260,
                    height=36,
                    corner_radius=8,
                    fg_color=UI_COLORS["bg_surface_alt"],
                    border_color=UI_COLORS["border"],
                    text_color=UI_COLORS["text_primary"],
                )
                if key == "entry_data" and default:
                    widget.insert(0, default)

            widget.grid(row=idx, column=1, padx=(16, 24), pady=(14 if idx == 0 else 8, 8), sticky="e")
            self.form_inputs[key] = widget

        # Cálculo automático dinâmico enquanto digita
        self.form_inputs["entry_total"].bind("<KeyRelease>", lambda event: self._auto_calc_price("from_total"))
        self.form_inputs["entry_qtd"].bind("<KeyRelease>", lambda event: self._auto_calc_price("from_qtd"))
        self.form_inputs["entry_unit"].bind("<KeyRelease>", lambda event: self._auto_calc_price("from_unit"))

        # Máscara automática de data (DD/MM/AAAA)
        self.form_inputs["entry_data"].bind("<KeyRelease>", self._format_date_mask)
        self.form_inputs["entry_data"].bind("<FocusOut>", self._validate_date_focusout)

        # Botões de Ação
        btn_box = ctk.CTkFrame(form, fg_color="transparent")
        btn_box.grid(row=len(fields), column=0, columnspan=2, padx=24, pady=(20, 22), sticky="ew")
        btn_box.grid_columnconfigure((0, 1), weight=1)

        self.btn_salvar_op = ctk.CTkButton(
            btn_box,
            text="💾 Salvar Operação",
            command=self.save_operation,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
            text_color="#ffffff",
        )
        self.btn_salvar_op.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_cancelar_edicao = ctk.CTkButton(
            btn_box,
            text="Cancelar",
            command=lambda: self.show_view("historico"),
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        self.btn_cancelar_edicao.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        return frame

    # -------------------------------------------------------------
    # VIEW: HISTÓRICO COMPLETO COM BOTÕES EDITAR / EXCLUIR
    # -------------------------------------------------------------
    def _create_historico_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        self._create_page_header(
            frame,
            "Extrato Completo de Operações",
            "Pesquise, ordene, edite ou exclua movimentações registradas na planilha",
        )

        # Barra de ferramentas com Busca por Ativo, Editar e Excluir
        toolbar = ctk.CTkFrame(
            frame,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        btn_edit = ctk.CTkButton(
            toolbar,
            text="✏️ Editar Selecionada",
            command=self.edit_selected_operation,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["blue"],
            hover_color=UI_COLORS["blue_hover"],
            text_color="#ffffff",
        )
        btn_edit.pack(side="left", padx=(12, 8), pady=8)

        btn_delete = ctk.CTkButton(
            toolbar,
            text="🗑️ Excluir Selecionada",
            command=self.delete_selected_operation,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            fg_color=UI_COLORS["danger"],
            hover_color=UI_COLORS["danger_hover"],
            text_color="#ffffff",
        )
        btn_delete.pack(side="left", padx=(0, 16), pady=8)

        # Campo de Busca/Filtro por Ativo
        lbl_busca = ctk.CTkLabel(
            toolbar,
            text="🔍 Filtrar Ativo:",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_busca.pack(side="left", padx=(0, 6), pady=8)

        self.entry_filtro_ativo = ctk.CTkEntry(
            toolbar,
            placeholder_text="Ex: MXRF11, PETR4...",
            width=190,
            height=34,
            corner_radius=8,
            fg_color=UI_COLORS["bg_surface_alt"],
            border_color=UI_COLORS["border"],
            text_color=UI_COLORS["text_primary"],
        )
        self.entry_filtro_ativo.pack(side="left", padx=(0, 8), pady=8)
        self.entry_filtro_ativo.bind("<KeyRelease>", self._on_filter_historico_changed)

        btn_limpar_filtro = ctk.CTkButton(
            toolbar,
            text="Limpar",
            command=self._clear_filter_historico,
            height=34,
            width=72,
            corner_radius=8,
            font=ctk.CTkFont(*UI_FONTS["caption"]),
            fg_color=UI_COLORS["bg_surface_alt"],
            hover_color=UI_COLORS["bg_hover"],
            text_color=UI_COLORS["text_primary"],
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        btn_limpar_filtro.pack(side="left", padx=(0, 10), pady=8)

        lbl_dica = ctk.CTkLabel(
            toolbar,
            text="Dica: clique no título da coluna para ordenar.",
            text_color=UI_COLORS["text_muted"],
            font=ctk.CTkFont(*UI_FONTS["caption"]),
        )
        lbl_dica.pack(side="right", padx=12, pady=8)

        # Tabela
        tbl_container = self._create_table_card(frame)
        tbl_container.grid(row=2, column=0, sticky="nsew")

        cols = ("id", "data", "cota", "tipo", "operacao", "quantidade", "preco_unit", "valor_total")
        self.tree_historico = ttk.Treeview(tbl_container, columns=cols, show="headings", selectmode="browse", height=12)

        # Cabeçalhos com ordenação por clique
        self.tree_historico.heading("id", text="#", command=lambda: self._sort_historico("id"))
        self.tree_historico.heading("data", text="Data ↕", command=lambda: self._sort_historico("data"))
        self.tree_historico.heading("cota", text="Ativo / Cota ↕", command=lambda: self._sort_historico("cota"))
        self.tree_historico.heading("tipo", text="Tipo ↕", command=lambda: self._sort_historico("tipo"))
        self.tree_historico.heading("operacao", text="Operação ↕", command=lambda: self._sort_historico("operacao"))
        self.tree_historico.heading("quantidade", text="Qtd ↕", command=lambda: self._sort_historico("quantidade"))
        self.tree_historico.heading("preco_unit", text="Preço Unit. ↕", command=lambda: self._sort_historico("preco_unit"))
        self.tree_historico.heading("valor_total", text="Valor Total ↕", command=lambda: self._sort_historico("valor_total"))

        self.tree_historico.column("id", width=45, minwidth=40, anchor="center")
        self.tree_historico.column("data", width=100, minwidth=90, anchor="center")
        self.tree_historico.column("cota", width=110, minwidth=95, anchor="center")
        self.tree_historico.column("tipo", width=80, minwidth=70, anchor="center")
        self.tree_historico.column("operacao", width=95, minwidth=85, anchor="center")
        self.tree_historico.column("quantidade", width=90, minwidth=75, anchor="e")
        self.tree_historico.column("preco_unit", width=110, minwidth=95, anchor="e")
        self.tree_historico.column("valor_total", width=120, minwidth=105, anchor="e")

        # Double click para editar
        self.tree_historico.bind("<Double-1>", lambda event: self.edit_selected_operation())

        self._attach_tree_scrollbars(tbl_container, self.tree_historico)
        self._setup_tree_tags_and_context_menu(self.tree_historico, ticker_col_idx=2, allow_crud=True)
        self._register_empty_state(
            "historico",
            tbl_container,
            "Nenhuma operação encontrada",
            "Limpe o filtro de busca ou cadastre uma nova movimentação.",
        )

        return frame

    def _sort_historico(self, col: str):
        if self.historico_sort_col == col:
            self.historico_sort_reverse = not self.historico_sort_reverse
        else:
            self.historico_sort_col = col
            self.historico_sort_reverse = False

        # Atualiza os cabeçalhos com setas indicativas
        col_names = {
            "id": "#",
            "data": "Data",
            "cota": "Ativo / Cota",
            "tipo": "Tipo",
            "operacao": "Operação",
            "quantidade": "Qtd",
            "preco_unit": "Preço Unit.",
            "valor_total": "Valor Total"
        }
        for c, base_title in col_names.items():
            if c == self.historico_sort_col:
                arrow = " ▲" if not self.historico_sort_reverse else " ▼"
                self.tree_historico.heading(c, text=f"{base_title}{arrow}")
            else:
                self.tree_historico.heading(c, text=f"{base_title} ↕")

        self._populate_historico_table()

    def _on_filter_historico_changed(self, event=None):
        self.historico_filter_text = self.entry_filtro_ativo.get().strip().upper()
        self._populate_historico_table()

    def _clear_filter_historico(self):
        self.entry_filtro_ativo.delete(0, "end")
        self.historico_filter_text = ""
        self._populate_historico_table()

    def _populate_historico_table(self):
        for item in self.tree_historico.get_children():
            self.tree_historico.delete(item)

        # Filtragem por ticker ou texto
        filtered = self.transactions
        if self.historico_filter_text:
            filtro = self.historico_filter_text.upper()
            filtered = [tx for tx in filtered if filtro in (tx.ticker or "").upper()]

        # Função de chave para ordenação
        def get_sort_key(tx):
            col = self.historico_sort_col
            if col == "id":
                return tx.id if tx.id is not None else 0
            elif col == "data":
                if tx.data:
                    try:
                        return datetime.strptime(tx.data, "%d/%m/%Y")
                    except Exception:
                        pass
                return datetime.min
            elif col == "cota":
                return (tx.ticker or "").upper()
            elif col == "tipo":
                return (tx.tipo_ativo or "").lower()
            elif col == "operacao":
                return (tx.operacao or "").lower()
            elif col == "quantidade":
                return tx.quantidade or 0.0
            elif col == "preco_unit":
                return tx.valor_unitario or 0.0
            elif col == "valor_total":
                return tx.valor_total or 0.0
            return tx.id or 0

        sorted_txs = sorted(filtered, key=get_sort_key, reverse=self.historico_sort_reverse)

        for idx, tx in enumerate(sorted_txs, 1):
            zebra = "even" if idx % 2 == 0 else "odd"
            self.tree_historico.insert("", "end", iid=str(tx.id), values=(
                idx,
                tx.data or "-",
                tx.ticker,
                tx.tipo_ativo.upper(),
                tx.operacao.capitalize(),
                f"{tx.quantidade:g}",
                f"R$ {tx.valor_unitario:.2f}",
                f"R$ {tx.valor_total:.2f}"
            ), tags=(zebra,))

        self._set_empty_state("historico", len(sorted_txs) == 0)

    # -------------------------------------------------------------
    # AUXILIARES VISUAIS & DADOS
    # -------------------------------------------------------------
    def _create_stat_card(self, parent, col, title, initial_val, color):
        """Cria card de KPI compacto com superfície elevada, borda sutil e barra lateral de acento."""
        card = ctk.CTkFrame(
            parent,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=10,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        padx = (0, 6) if col == 0 else (6, 0)
        card.grid(row=0, column=col, padx=padx, pady=2, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        accent_bar = ctk.CTkFrame(card, width=4, height=36, fg_color=color, corner_radius=2)
        accent_bar.grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=10, sticky="ns")

        lbl_title = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(*UI_FONTS["kpi_lbl"]),
            text_color=UI_COLORS["text_secondary"],
            anchor="w",
            justify="left",
        )
        lbl_title.grid(row=0, column=1, padx=(10, 12), pady=(8, 1), sticky="ew")

        lbl_val = ctk.CTkLabel(
            card,
            text=initial_val,
            font=ctk.CTkFont(*UI_FONTS["kpi_val"]),
            text_color=UI_COLORS["text_primary"],
            anchor="w",
            justify="left",
        )
        lbl_val.grid(row=1, column=1, padx=(10, 12), pady=(0, 8), sticky="ew")

        return lbl_val

    def _on_carteira_chart_mode_changed(self, value: str):
        self.carteira_chart_mode = value
        if self.charts_visible:
            self._render_carteira_charts(self._last_wallet, self.live_quotes)

    def _on_carteira_tipo_filter_changed(self, value: str):
        self.carteira_filter_tipo = value
        self._populate_carteira_table()

    def _sort_carteira(self, col: str):
        if self.carteira_sort_col == col:
            self.carteira_sort_reverse = not self.carteira_sort_reverse
        else:
            self.carteira_sort_col = col
            self.carteira_sort_reverse = False

        col_names = {
            "ticker": "Ativo / Cota",
            "tipo": "Tipo",
            "quantidade": "Qtd",
            "preco_medio": "Preço Médio (PM)",
            "preco_atual": "Preço Atual (B3)",
            "total_investido": "Total Investido",
            "patrimonio_atual": "Patrimônio Atual",
            "lucro_prej": "Lucro/Prejuízo",
            "rentabilidade": "Rentab. (%)",
        }
        for c, base_title in col_names.items():
            if c == self.carteira_sort_col:
                arrow = " ▲" if not self.carteira_sort_reverse else " ▼"
                self.tree_carteira.heading(c, text=f"{base_title}{arrow}")
            else:
                self.tree_carteira.heading(c, text=f"{base_title} ↕")

        self._populate_carteira_table()

    def _populate_carteira_table(self):
        for item in self.tree_carteira.get_children():
            self.tree_carteira.delete(item)

        wallet = self._last_calc_res.get("wallet", {})
        linhas = []
        for ticker, data in wallet.items():
            tipo_upper = data["tipo_ativo"].upper()
            if self.carteira_filter_tipo != "Todos" and tipo_upper != self.carteira_filter_tipo:
                continue

            qtd = data["quantidade"]
            investido = data["total_investido"]
            quote_data = self.live_quotes.get(ticker)
            if quote_data and quote_data.get("price") is not None:
                cur_price = quote_data["price"]
                cur_val = qtd * cur_price
                lucro_prej = cur_val - investido
                rentab = ((cur_val - investido) / investido * 100) if investido > 0 else 0.0
                str_preco_atual = f"R$ {cur_price:.2f}"
                str_patrimonio = f"R$ {cur_val:.2f}"
                str_lucro_prej = f"{'+' if lucro_prej >= 0 else '-'}R$ {abs(lucro_prej):.2f}"
                str_rentab = f"{rentab:+.2f}%"
            else:
                cur_price = 0.0
                cur_val = investido
                lucro_prej = 0.0
                rentab = 0.0
                str_preco_atual = "Consultando..."
                str_patrimonio = f"R$ {investido:.2f}"
                str_lucro_prej = "R$ 0,00"
                str_rentab = "0.00%"

            linhas.append({
                "ticker": data["ticker"],
                "tipo": tipo_upper,
                "quantidade": qtd,
                "preco_medio": data["preco_medio"],
                "preco_atual": cur_price,
                "total_investido": investido,
                "patrimonio_atual": cur_val,
                "lucro_prej": lucro_prej,
                "rentabilidade": rentab,
                "values": (
                    data["ticker"],
                    tipo_upper,
                    f"{qtd:g}",
                    f"R$ {data['preco_medio']:.2f}",
                    str_preco_atual,
                    f"R$ {investido:.2f}",
                    str_patrimonio,
                    str_lucro_prej,
                    str_rentab,
                ),
            })

        sort_col = self.carteira_sort_col
        linhas.sort(key=lambda r: r.get(sort_col, r["ticker"]), reverse=self.carteira_sort_reverse)

        for idx, row in enumerate(linhas):
            tags = ["even" if idx % 2 == 0 else "odd"]
            if row["lucro_prej"] > 0.005:
                tags.append("profit")
            elif row["lucro_prej"] < -0.005:
                tags.append("loss")
            self.tree_carteira.insert("", "end", values=row["values"], tags=tuple(tags))

        self._set_empty_state("carteira", len(linhas) == 0)

    def _on_vendas_ano_filter_changed(self, value: str):
        self.vendas_filter_ano = value
        self._populate_vendas_tables()
        if self.vendas_chart_visible:
            self._render_vendas_chart()

    def _toggle_vendas_chart(self):
        self.vendas_chart_visible = not self.vendas_chart_visible
        if self.vendas_chart_visible:
            self.vendas_chart_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
            self.btn_toggle_vendas_chart.configure(text="📊 Ocultar Gráfico")
            self._render_vendas_chart()
        else:
            self.vendas_chart_frame.grid_forget()
            self.btn_toggle_vendas_chart.configure(text="📊 Mostrar Gráfico")

    def _render_vendas_chart(self):
        reports = self._filtered_tax_reports()
        fig_vendas = create_sales_darf_summary_figure(reports)
        self._render_figure_in_container(self.vendas_chart_frame, fig_vendas, "vendas_darf")

    def _filtered_tax_reports(self):
        reports = self._last_calc_res.get("tax_reports", [])
        if self.vendas_filter_ano == "Todos":
            return reports
        return [t for t in reports if t.mes_ano.endswith(f"/{self.vendas_filter_ano}")]

    def _populate_vendas_tables(self):
        res = self._last_calc_res
        for item in self.tree_darf.get_children():
            self.tree_darf.delete(item)

        paid_darfs = load_paid_darfs(DEFAULT_EXCEL_PATH)
        filtered_reports = self._filtered_tax_reports()
        for idx, tax in enumerate(filtered_reports):
            status_darf = f"R$ {tax.imposto_devido:.2f}"
            key_pgto = (tax.mes_ano, tax.tipo_ativo.lower())
            esta_pago = key_pgto in paid_darfs

            if tax.isento:
                status_darf = "Isento (<= 20k)"
                status_pgto = "Isento"
            elif tax.imposto_devido == 0:
                status_darf = "R$ 0,00"
                status_pgto = "Sem imposto"
            elif esta_pago:
                dt_paga = paid_darfs[key_pgto].get("data_pagamento", "")
                status_pgto = f"Pago ✅ ({dt_paga})" if dt_paga else "Pago ✅"
            elif tax.imposto_devido < 10.0:
                status_pgto = "Acumular (< R$ 10)"
            else:
                status_pgto = "Pendente ⚠️"

            res_formatado = f"R$ {tax.resultado_liquido:.2f}"
            if tax.resultado_liquido < 0:
                res_formatado = f"-R$ {abs(tax.resultado_liquido):.2f}"

            tags = ["even" if idx % 2 == 0 else "odd"]
            if "Pendente" in status_pgto:
                tags.append("warning")
            elif "Pago" in status_pgto:
                tags.append("profit")
            elif tax.resultado_liquido < 0:
                tags.append("loss")

            iid = f"{tax.mes_ano}__{tax.tipo_ativo.lower()}"
            self.tree_darf.insert("", "end", iid=iid, values=(
                tax.mes_ano,
                tax.tipo_ativo.upper(),
                f"R$ {tax.vendas_total:.2f}",
                res_formatado,
                f"R$ {tax.prejuizo_anterior_compensado:.2f}",
                f"R$ {tax.base_calculo:.2f}",
                status_darf,
                f"R$ {tax.prejuizo_restante_acumulado:.2f}",
                status_pgto
            ), tags=tuple(tags))

        self._set_empty_state("darf", len(filtered_reports) == 0)

        for item in self.tree_sales.get_children():
            self.tree_sales.delete(item)

        sales = res.get("sales", [])
        if self.vendas_filter_ano != "Todos":
            sales = [s for s in sales if (s.data or "").endswith(f"/{self.vendas_filter_ano}")]

        for idx, s in enumerate(sales):
            res_val = f"R$ {s.lucro_prejuizo:.2f}"
            if s.lucro_prejuizo < 0:
                res_val = f"-R$ {abs(s.lucro_prejuizo):.2f}"

            tags = ["even" if idx % 2 == 0 else "odd"]
            if s.lucro_prejuizo > 0.005:
                tags.append("profit")
            elif s.lucro_prejuizo < -0.005:
                tags.append("loss")

            self.tree_sales.insert("", "end", values=(
                s.data or "-",
                s.ticker,
                s.tipo_ativo.upper(),
                f"{s.quantidade_vendida:g}",
                f"R$ {s.preco_medio_compra:.2f}",
                f"R$ {s.preco_venda_unitario:.2f}",
                f"R$ {s.valor_venda_total:.2f}",
                res_val
            ), tags=tuple(tags))

        self._set_empty_state("sales", len(sales) == 0)

    def load_data(self):
        """Carrega transações do Excel e atualiza a interface."""
        self.transactions = load_transactions_from_excel(DEFAULT_EXCEL_PATH)
        self.engine.set_transactions(self.transactions)
        res = self.engine.calculate()
        self._last_calc_res = res

        # 1. Atualiza cards e tabela da Carteira
        total_investido_carteira = 0.0
        patrimonio_total_mercado = 0.0

        for ticker, data in res["wallet"].items():
            qtd = data["quantidade"]
            investido = data["total_investido"]
            total_investido_carteira += investido

            quote_data = self.live_quotes.get(ticker)
            if quote_data and quote_data.get("price") is not None:
                patrimonio_total_mercado += qtd * quote_data["price"]
            else:
                patrimonio_total_mercado += investido

        self._populate_carteira_table()

        lucro_total_carteira = patrimonio_total_mercado - total_investido_carteira
        rentab_total_carteira = ((lucro_total_carteira / total_investido_carteira) * 100) if total_investido_carteira > 0 else 0.0

        self.card_total_investido.configure(text=f"R$ {total_investido_carteira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_patrimonio_atual.configure(text=f"R$ {patrimonio_total_mercado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        lucro_color = (
            UI_COLORS["success_text"]
            if lucro_total_carteira > 0.005
            else (UI_COLORS["danger_text"] if lucro_total_carteira < -0.005 else UI_COLORS["text_primary"])
        )
        self.card_lucro_total.configure(
            text=f"{'+' if lucro_total_carteira >= 0 else '-'}R$ {abs(lucro_total_carteira):,.2f} ({rentab_total_carteira:+.2f}%)".replace(",", "X").replace(".", ",").replace("X", "."),
            text_color=lucro_color,
        )

        self._last_wallet = res["wallet"]
        if self.charts_visible:
            self._render_carteira_charts(res["wallet"], self.live_quotes)

        # 2. Atualiza filtro de anos de Vendas & DARF e preenche tabelas
        anos_vendas = sorted(
            {
                t.mes_ano.split("/")[-1]
                for t in res["tax_reports"]
                if "/" in (t.mes_ano or "")
            },
            reverse=True,
        )
        opcoes_anos = ["Todos"] + anos_vendas
        self.opt_filtro_vendas_ano.configure(values=opcoes_anos)
        if self.vendas_filter_ano not in opcoes_anos:
            self.vendas_filter_ano = "Todos"
            self.opt_filtro_vendas_ano.set("Todos")

        ultimo_prejuizo_fii = (
            res["tax_reports"][-1].prejuizo_restante_acumulado if res["tax_reports"] else 0.0
        )
        self.card_prejuizo_acum.configure(text=f"R$ {ultimo_prejuizo_fii:.2f}".replace(".", ","))

        self._populate_vendas_tables()
        if self.vendas_chart_visible:
            self._render_vendas_chart()

        # 3. Extrato Completo
        self._populate_historico_table()

        # 4. Rentabilidade Total (Cota + Proventos)
        if self.dividends_data:
            self._last_dividends_calc = calculate_historical_dividends(
                self.transactions, self.dividends_data
            )
        self._update_rentabilidade_view()

    def _update_sync_status_label(self):
        if self.is_fetching_quotes or self.is_fetching_dividends:
            self.lbl_sync_status.configure(text="⏳ Sincronizando B3...", text_color=UI_COLORS["warning_text"])
            if hasattr(self, "btn_sync_rentab"):
                self.btn_sync_rentab.configure(text="⏳ Atualizando...", state="disabled")
        else:
            self.lbl_sync_status.configure(text="✅ B3 sincronizada", text_color=UI_COLORS["success_text"])
            if hasattr(self, "btn_sync_rentab"):
                self.btn_sync_rentab.configure(text="📡 Atualizar Dados", state="normal")

    def refresh_quotes_async(self):
        """Dispara a busca de cotações em background sem travar a interface."""
        if self.is_fetching_quotes:
            return

        self.is_fetching_quotes = True
        self.btn_refresh_quotes.configure(text="⏳ Atualizando...", state="disabled")
        self._update_sync_status_label()

        def task():
            res = self.engine.calculate()
            tickers = list(res['wallet'].keys())
            novas_cotacoes = fetch_all_quotes(tickers)
            self.live_quotes.update(novas_cotacoes)

            # Agenda a atualização na thread principal do Tkinter
            self.after(0, self._on_quotes_fetched)

        threading.Thread(target=task, daemon=True).start()

    def _on_quotes_fetched(self):
        self.is_fetching_quotes = False
        self.btn_refresh_quotes.configure(text="📡 Atualizar B3", state="normal")
        self._update_sync_status_label()
        self.load_data()

    def refresh_dividends_async(self):
        """Busca histórico oficial de proventos pagos em background e calcula rendimentos da carteira."""
        if self.is_fetching_dividends:
            return

        self.is_fetching_dividends = True
        self.btn_refresh_divs.configure(text="⏳ Buscando Proventos...", state="disabled")
        self._update_sync_status_label()

        def task():
            res = self.engine.calculate()
            tickers = list(res['wallet'].keys())
            novos_proventos = fetch_all_dividends(tickers)
            self.dividends_data.update(novos_proventos)

            self.after(0, self._on_dividends_fetched)

        threading.Thread(target=task, daemon=True).start()

    def _on_dividends_fetched(self):
        self.is_fetching_dividends = False
        self.btn_refresh_divs.configure(text="📡 Atualizar Proventos", state="normal")
        self._update_sync_status_label()
        self._update_dividends_view()

    def _on_proventos_ano_filter_changed(self, value: str):
        self.proventos_filter_ano = value
        self._populate_proventos_tables()

    def _update_dividends_view(self):
        """Calcula os proventos com base nas cotas do usuário e preenche as tabelas."""
        todos_pagamentos, mensal_stats = calculate_historical_dividends(
            self.transactions, self.dividends_data
        )
        self._last_dividends_calc = (todos_pagamentos, mensal_stats)

        anos_prov = sorted(
            {m.split("/")[-1] for m in mensal_stats.keys() if "/" in m},
            reverse=True,
        )
        opcoes_anos = ["Todos"] + anos_prov
        self.opt_filtro_proventos_ano.configure(values=opcoes_anos)
        if self.proventos_filter_ano not in opcoes_anos:
            self.proventos_filter_ano = "Todos"
            self.opt_filtro_proventos_ano.set("Todos")

        self._populate_proventos_tables()

    def _populate_proventos_tables(self):
        res = self.engine.calculate()
        carteira = res["wallet"]
        todos_pagamentos, mensal_stats = self._last_dividends_calc

        for item in self.tree_proventos_mes.get_children():
            self.tree_proventos_mes.delete(item)
        for item in self.tree_proventos_detalhe.get_children():
            self.tree_proventos_detalhe.delete(item)

        ano_filtro = self.proventos_filter_ano
        if ano_filtro != "Todos":
            pagamentos_filtrados = [p for p in todos_pagamentos if str(p.get("data", "")).endswith(f"/{ano_filtro}")]
            stats_filtradas = {m: st for m, st in mensal_stats.items() if m.endswith(f"/{ano_filtro}")}
        else:
            pagamentos_filtrados = todos_pagamentos
            stats_filtradas = mensal_stats

        for idx, p in enumerate(pagamentos_filtrados):
            zebra = "even" if idx % 2 == 0 else "odd"
            self.tree_proventos_detalhe.insert("", "end", values=(
                p["data"],
                p["ticker"],
                f"{p['qtd']:g}",
                f"R$ {p['unit']:.4f}",
                f"R$ {p['total']:.2f}"
            ), tags=(zebra, "profit"))

        meses_ordenados = sorted(stats_filtradas.items(), key=lambda x: x[1]["timestamp"], reverse=True)
        total_historico_recebido = sum(st["total"] for st in stats_filtradas.values())

        meses_12m = meses_ordenados[:12]
        total_12m = sum(st["total"] for _, st in meses_12m)
        total_investido_carteira = sum(d["total_investido"] for d in carteira.values())

        for idx, (mes_ano, st) in enumerate(meses_ordenados):
            total_mes = st["total"]
            qtd_atv = len(st["ativos"])
            yield_mes = (total_mes / total_investido_carteira * 100) if total_investido_carteira > 0 else 0.0
            zebra = "even" if idx % 2 == 0 else "odd"

            self.tree_proventos_mes.insert("", "end", values=(
                mes_ano,
                f"R$ {total_mes:.2f}",
                f"{qtd_atv} ativo(s)",
                f"{yield_mes:.2f}%"
            ), tags=(zebra,))

        media_mensal = (total_12m / len(meses_12m)) if meses_12m else 0.0
        yield_anual = (total_12m / total_investido_carteira * 100) if total_investido_carteira > 0 else 0.0

        self.card_total_proventos.configure(text=f"R$ {total_historico_recebido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_media_mensal.configure(text=f"R$ {media_mensal:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_yield_medio.configure(text=f"{yield_anual:.2f}% a.a.")
        self._set_empty_state("proventos_mes", len(meses_ordenados) == 0)
        self._set_empty_state("proventos_detalhe", len(pagamentos_filtrados) == 0)
        self._render_proventos_chart(stats_filtradas)
        self._update_rentabilidade_view()

    def _sync_all_for_rentabilidade(self):
        """Dispara atualização simultânea de cotações B3 e histórico de proventos."""
        self.refresh_quotes_async()
        self.refresh_dividends_async()

    def _toggle_rentab_charts(self):
        """Alterna a exibição do painel de gráficos da tela de Rentabilidade Total."""
        self.rentab_charts_visible = not self.rentab_charts_visible
        if self.rentab_charts_visible:
            self.rentab_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
            self.btn_toggle_rentab_charts.configure(text="📊 Ocultar Gráficos")
            proventos_map = self._consolidar_proventos_por_ticker()
            self._render_rentab_charts(self._last_wallet, self.live_quotes, proventos_map)
        else:
            self.rentab_charts_frame.grid_forget()
            self.btn_toggle_rentab_charts.configure(text="📊 Mostrar Gráficos")

    def _on_rentab_tipo_filter_changed(self, value: str):
        self.rentab_filter_tipo = value
        self._populate_rentabilidade_table()

    def _sort_rentabilidade(self, col: str):
        if self.rentab_sort_col == col:
            self.rentab_sort_reverse = not self.rentab_sort_reverse
        else:
            self.rentab_sort_col = col
            self.rentab_sort_reverse = col not in ("ticker", "tipo")

        col_names = {
            "ticker": "Ativo / Cota",
            "tipo": "Tipo",
            "investido": "Total Investido",
            "patrimonio": "Patrimônio Atual",
            "val_cota": "Valoriz. Cota (R$)",
            "val_cota_pct": "Valoriz. (%)",
            "proventos": "Proventos (R$)",
            "yoc_pct": "Yield s/ Custo",
            "retorno_total": "Retorno Total (R$)",
            "retorno_total_pct": "Retorno Total (%)",
        }
        for c, base_title in col_names.items():
            if c == self.rentab_sort_col:
                arrow = " ▲" if not self.rentab_sort_reverse else " ▼"
                self.tree_rentabilidade.heading(c, text=f"{base_title}{arrow}")
            else:
                self.tree_rentabilidade.heading(c, text=f"{base_title} ↕")

        self._populate_rentabilidade_table()

    def _consolidar_proventos_por_ticker(self) -> dict[str, float]:
        """Soma os proventos recebidos por ticker, preservando o vínculo após conversões de código."""
        conv_map: dict[str, str] = {}
        for tx in self.transactions:
            if tx.operacao == "conversao" and "->" in tx.ticker:
                origem, destino = [p.strip().upper() for p in tx.ticker.split("->", 1)]
                if origem and destino:
                    conv_map[origem] = destino

        def _resolver_destino(t: str) -> str:
            atual = t.strip().upper()
            visitados = set()
            while atual in conv_map and atual not in visitados:
                visitados.add(atual)
                atual = conv_map[atual]
            return atual

        totais: dict[str, float] = {}
        todos_pagamentos, _ = self._last_dividends_calc
        for p in todos_pagamentos:
            ticker_atual = _resolver_destino(str(p.get("ticker", "")))
            totais[ticker_atual] = totais.get(ticker_atual, 0.0) + float(p.get("total", 0.0) or 0.0)
        return totais

    def _update_rentabilidade_view(self):
        """Atualiza cards, gráficos e tabela consolidada de Rentabilidade Total."""
        wallet = self._last_calc_res.get("wallet", {})
        proventos_map = self._consolidar_proventos_por_ticker()

        total_investido = 0.0
        patrimonio_atual = 0.0
        proventos_carteira_ativa = 0.0

        for ticker, data in wallet.items():
            qtd = data["quantidade"]
            investido = data["total_investido"]
            total_investido += investido

            quote_data = self.live_quotes.get(ticker)
            if quote_data and quote_data.get("price") is not None:
                patrimonio_atual += qtd * quote_data["price"]
            else:
                patrimonio_atual += investido

            proventos_carteira_ativa += proventos_map.get(ticker.upper(), 0.0)

        # Soma também proventos de ativos eventualmente já encerrados para o consolidado geral
        proventos_totais = sum(proventos_map.values()) if proventos_map else proventos_carteira_ativa
        valorizacao_cota = patrimonio_atual - total_investido
        retorno_total = valorizacao_cota + proventos_totais

        val_pct = (valorizacao_cota / total_investido * 100.0) if total_investido > 0 else 0.0
        prov_pct = (proventos_totais / total_investido * 100.0) if total_investido > 0 else 0.0
        total_pct = (retorno_total / total_investido * 100.0) if total_investido > 0 else 0.0

        def _fmt_rs(val: float, with_sign: bool = False) -> str:
            s = f"R$ {abs(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if with_sign:
                return f"{'+' if val >= 0 else '-'}{s}"
            return f"-{s}" if val < 0 else s

        val_color = (
            UI_COLORS["success_text"]
            if valorizacao_cota > 0.005
            else (UI_COLORS["danger_text"] if valorizacao_cota < -0.005 else UI_COLORS["text_primary"])
        )
        ret_color = (
            UI_COLORS["success_text"]
            if retorno_total > 0.005
            else (UI_COLORS["danger_text"] if retorno_total < -0.005 else UI_COLORS["text_primary"])
        )

        self.card_rentab_investido.configure(text=_fmt_rs(total_investido))
        self.card_rentab_valorizacao.configure(
            text=f"{_fmt_rs(valorizacao_cota, True)} ({val_pct:+.2f}%)",
            text_color=val_color,
        )
        self.card_rentab_proventos.configure(
            text=f"{_fmt_rs(proventos_totais, True)} (+{prov_pct:.2f}%)",
            text_color=UI_COLORS["success_text"] if proventos_totais > 0 else UI_COLORS["text_primary"],
        )
        self.card_rentab_total.configure(
            text=f"{_fmt_rs(retorno_total, True)} ({total_pct:+.2f}%)",
            text_color=ret_color,
        )

        self._populate_rentabilidade_table(proventos_map)
        if self.rentab_charts_visible:
            self._render_rentab_charts(wallet, self.live_quotes, proventos_map)

    def _populate_rentabilidade_table(self, proventos_map: dict[str, float] | None = None):
        if proventos_map is None:
            proventos_map = self._consolidar_proventos_por_ticker()

        for item in self.tree_rentabilidade.get_children():
            self.tree_rentabilidade.delete(item)

        wallet = self._last_calc_res.get("wallet", {})
        linhas = []
        for ticker, data in wallet.items():
            tipo_upper = data["tipo_ativo"].upper()
            if self.rentab_filter_tipo != "Todos" and tipo_upper != self.rentab_filter_tipo:
                continue

            qtd = data["quantidade"]
            investido = data["total_investido"]
            quote_data = self.live_quotes.get(ticker)
            if quote_data and quote_data.get("price") is not None:
                patrimonio = qtd * quote_data["price"]
                str_patrimonio = f"R$ {patrimonio:.2f}"
            else:
                patrimonio = investido
                str_patrimonio = f"R$ {investido:.2f}"

            val_cota = patrimonio - investido
            val_cota_pct = (val_cota / investido * 100.0) if investido > 0 else 0.0
            proventos = proventos_map.get(ticker.upper(), 0.0)
            yoc_pct = (proventos / investido * 100.0) if investido > 0 else 0.0
            retorno_total = val_cota + proventos
            retorno_total_pct = (retorno_total / investido * 100.0) if investido > 0 else 0.0

            linhas.append({
                "ticker": data["ticker"],
                "tipo": tipo_upper,
                "investido": investido,
                "patrimonio": patrimonio,
                "val_cota": val_cota,
                "val_cota_pct": val_cota_pct,
                "proventos": proventos,
                "yoc_pct": yoc_pct,
                "retorno_total": retorno_total,
                "retorno_total_pct": retorno_total_pct,
                "values": (
                    data["ticker"],
                    tipo_upper,
                    f"R$ {investido:.2f}",
                    str_patrimonio,
                    f"{'+' if val_cota >= 0 else '-'}R$ {abs(val_cota):.2f}",
                    f"{val_cota_pct:+.2f}%",
                    f"R$ {proventos:.2f}",
                    f"+{yoc_pct:.2f}%",
                    f"{'+' if retorno_total >= 0 else '-'}R$ {abs(retorno_total):.2f}",
                    f"{retorno_total_pct:+.2f}%",
                ),
            })

        sort_col = self.rentab_sort_col
        linhas.sort(key=lambda r: r.get(sort_col, r["ticker"]), reverse=self.rentab_sort_reverse)

        for idx, row in enumerate(linhas):
            tags = ["even" if idx % 2 == 0 else "odd"]
            if row["retorno_total"] > 0.005:
                tags.append("profit")
            elif row["retorno_total"] < -0.005:
                tags.append("loss")
            self.tree_rentabilidade.insert("", "end", values=row["values"], tags=tuple(tags))

        self._set_empty_state("rentabilidade", len(linhas) == 0)

    def _render_rentab_charts(self, wallet: dict, live_quotes: dict, proventos_map: dict):
        """Atualiza os gráficos da tela de Rentabilidade Total."""
        fig_break = create_total_return_breakdown_figure(wallet, live_quotes, proventos_map)
        self._render_figure_in_container(self.chart_rentab_breakdown_container, fig_break, "rentab_breakdown")

        fig_pct = create_total_return_pct_figure(wallet, live_quotes, proventos_map)
        self._render_figure_in_container(self.chart_rentab_pct_container, fig_pct, "rentab_pct")

    def _render_figure_in_container(self, container, figure, slot_key: str):
        """Renderiza uma Figure Matplotlib em um container CTkFrame fechando a figura anterior."""
        prev_fig = self._chart_figures.pop(slot_key, None)
        if prev_fig is not None:
            plt.close(prev_fig)

        for child in container.winfo_children():
            child.destroy()

        canvas = FigureCanvasTkAgg(figure, master=container)
        canvas.draw()
        attach_matplotlib_tooltip(canvas, figure)
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True, padx=4, pady=4)
        self._chart_figures[slot_key] = figure

    def _toggle_carteira_charts(self):
        """Alterna a exibição do painel de gráficos da Carteira Atual."""
        self.charts_visible = not self.charts_visible
        if self.charts_visible:
            self.carteira_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
            self.btn_toggle_charts.configure(text="📊 Ocultar Gráficos")
            self._render_carteira_charts(self._last_wallet, self.live_quotes)
        else:
            self.carteira_charts_frame.grid_forget()
            self.btn_toggle_charts.configure(text="📊 Mostrar Gráficos")

    def _render_carteira_charts(self, wallet: dict, live_quotes: dict):
        """Atualiza os gráficos de alocação por classe e distribuição/rentabilidade por ativo."""
        fig_class = create_allocation_by_class_figure(wallet, live_quotes)
        self._render_figure_in_container(self.chart_class_container, fig_class, "carteira_class")

        if self.carteira_chart_mode == "Rentabilidade":
            fig_ticker = create_profitability_by_ticker_figure(wallet, live_quotes)
        else:
            fig_ticker = create_allocation_by_ticker_figure(wallet, live_quotes)
        self._render_figure_in_container(self.chart_ticker_container, fig_ticker, "carteira_ticker")

    def _render_proventos_chart(self, mensal_stats: dict):
        """Atualiza o gráfico de evolução mensal de proventos."""
        fig_divs = create_monthly_dividends_figure(mensal_stats)
        self._render_figure_in_container(self.proventos_chart_frame, fig_divs, "proventos_mensal")

    def mark_darf_as_paid(self):
        """Abre janela para confirmar e registrar o pagamento do DARF selecionado."""
        selected = self.tree_darf.selection()
        if not selected:
            messagebox.showwarning("Seleção Necessária", "Selecione uma linha do Resumo Fiscal para marcar o DARF como pago.")
            return

        iid = selected[0]
        if "__" not in iid:
            return

        mes_ano, tipo = iid.split("__")
        item_vals = self.tree_darf.item(iid, "values")
        # item_vals: [mes, tipo, total_vendas, resultado, prej_comp, base_calc, imposto, prej_acum, status]
        imposto_str = item_vals[6].replace("R$", "").strip().replace(",", ".")

        try:
            imposto_val = float(imposto_str)
        except ValueError:
            imposto_val = 0.0

        if imposto_val <= 0:
            messagebox.showinfo("Sem Imposto", f"Não há imposto devido para {mes_ano} ({tipo.upper()}).")
            return

        # Modal de Confirmação
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirmar Pagamento de DARF")
        dialog.geometry("420x280")
        dialog.resizable(False, False)
        dialog.configure(fg_color=UI_COLORS["bg_app"])
        dialog.grab_set()

        card = ctk.CTkFrame(
            dialog,
            fg_color=UI_COLORS["bg_surface"],
            corner_radius=12,
            border_width=1,
            border_color=UI_COLORS["border"],
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        lbl_info = ctk.CTkLabel(
            card,
            text=f"Registrar pagamento de DARF\nPeríodo: {mes_ano} | Tipo: {tipo.upper()}\nValor Devido: R$ {imposto_val:.2f}",
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
            text_color=UI_COLORS["text_primary"],
            justify="center",
        )
        lbl_info.pack(pady=(16, 12))

        f_inputs = ctk.CTkFrame(card, fg_color="transparent")
        f_inputs.pack(pady=4)

        lbl_dt = ctk.CTkLabel(
            f_inputs,
            text="Data do Pagamento:",
            font=ctk.CTkFont(*UI_FONTS["body"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_dt.grid(row=0, column=0, padx=10, pady=6, sticky="w")
        ent_dt = ctk.CTkEntry(
            f_inputs,
            width=155,
            height=34,
            corner_radius=8,
            fg_color=UI_COLORS["bg_surface_alt"],
            border_color=UI_COLORS["border"],
        )
        ent_dt.insert(0, datetime.now().strftime("%d/%m/%Y"))
        ent_dt.grid(row=0, column=1, padx=10, pady=6)

        lbl_val = ctk.CTkLabel(
            f_inputs,
            text="Valor Pago (R$):",
            font=ctk.CTkFont(*UI_FONTS["body"]),
            text_color=UI_COLORS["text_secondary"],
        )
        lbl_val.grid(row=1, column=0, padx=10, pady=6, sticky="w")
        ent_val = ctk.CTkEntry(
            f_inputs,
            width=155,
            height=34,
            corner_radius=8,
            fg_color=UI_COLORS["bg_surface_alt"],
            border_color=UI_COLORS["border"],
        )
        ent_val.insert(0, f"{imposto_val:.2f}")
        ent_val.grid(row=1, column=1, padx=10, pady=6)

        def confirmar():
            dt_pg = ent_dt.get().strip()
            v_str = ent_val.get().strip().replace(",", ".")
            try:
                v_pago = float(v_str)
                if v_pago <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showwarning("Valor Inválido", "Digite um valor de pagamento válido.")
                return

            try:
                record_paid_darf(mes_ano, tipo, v_pago, dt_pg, DEFAULT_EXCEL_PATH)
                messagebox.showinfo("Sucesso", f"DARF de {mes_ano} ({tipo.upper()}) marcado como pago!")
                dialog.destroy()
                self.load_data()
            except Exception as e:
                messagebox.showerror("Erro ao Gravar", f"Erro ao salvar no Excel:\n{e}")

        btn_ok = ctk.CTkButton(
            card,
            text="✅ Confirmar Pagamento",
            command=confirmar,
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
            text_color="#ffffff",
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(*UI_FONTS["body_bold"]),
        )
        btn_ok.pack(pady=(16, 12), padx=24, fill="x")

    # -------------------------------------------------------------
    # GESTÃO DE OPERAÇÃO: NOVA / EDITAR / EXCLUIR
    # -------------------------------------------------------------
    def _auto_calc_price(self, source: str):
        """Calcula automaticamente preço por cota ou valor total dinamicamente enquanto o usuário digita."""
        qtd_text = self.form_inputs["entry_qtd"].get().strip().replace(",", ".")
        total_text = self.form_inputs["entry_total"].get().strip().replace(",", ".")
        unit_text = self.form_inputs["entry_unit"].get().strip().replace(",", ".")

        try:
            qtd = float(qtd_text) if qtd_text else 0.0
        except ValueError:
            return

        if qtd <= 0:
            return

        if source in ("from_total", "from_qtd"):
            if not total_text:
                return
            try:
                total = float(total_text)
                if total > 0:
                    unit_calc = total / qtd
                    # Atualiza o campo unitário
                    self.form_inputs["entry_unit"].delete(0, "end")
                    self.form_inputs["entry_unit"].insert(0, f"{unit_calc:.4f}")
            except ValueError:
                pass

        elif source == "from_unit":
            if not unit_text:
                return
            try:
                unit = float(unit_text)
                if unit > 0:
                    total_calc = qtd * unit
                    # Atualiza o campo total
                    self.form_inputs["entry_total"].delete(0, "end")
                    self.form_inputs["entry_total"].insert(0, f"{total_calc:.2f}")
            except ValueError:
                pass

    def _format_date_mask(self, event):
        """Formata a data automaticamente no padrão DD/MM/AAAA enquanto o usuário digita."""
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Tab"):
            return

        entry = self.form_inputs["entry_data"]
        raw = entry.get()
        # Filtra apenas números
        digits = "".join([c for c in raw if c.isdigit()])[:8]

        # Monta com barras
        formatted = ""
        if len(digits) > 4:
            formatted = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
        elif len(digits) > 2:
            formatted = f"{digits[:2]}/{digits[2:]}"
        else:
            formatted = digits

        if formatted != raw:
            entry.delete(0, "end")
            entry.insert(0, formatted)

    def _validate_date_focusout(self, event):
        """Valida se a data digitada é válida quando o campo perde o foco."""
        entry = self.form_inputs["entry_data"]
        text = entry.get().strip()
        if not text:
            return
        
        # Se digitou sem barras mas com 8 dígitos, formata
        digits = "".join([c for c in text if c.isdigit()])
        if len(digits) == 8 and "/" not in text:
            text = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
            entry.delete(0, "end")
            entry.insert(0, text)

        try:
            datetime.strptime(text, "%d/%m/%Y")
        except ValueError:
            messagebox.showwarning(
                "Data Inválida", 
                f"A data '{text}' não é uma data válida.\nUse o formato DD/MM/AAAA (ex: 10/10/2026)."
            )

    def prepare_new_operation(self):
        self.editing_tx_id = None
        self.lbl_form_title.configure(text="Cadastrar Nova Movimentação")
        self.btn_salvar_op.configure(
            text="💾 Salvar Operação",
            fg_color=UI_COLORS["success"],
            hover_color=UI_COLORS["success_hover"],
        )
        
        # Limpar campos
        self.form_inputs["entry_cota"].delete(0, "end")
        self.form_inputs["opt_tag"].set("fii")
        self.form_inputs["opt_operacao"].set("compra")
        self.form_inputs["entry_qtd"].delete(0, "end")
        self.form_inputs["entry_unit"].delete(0, "end")
        self.form_inputs["entry_total"].delete(0, "end")
        self.form_inputs["entry_data"].delete(0, "end")
        self.form_inputs["entry_data"].insert(0, datetime.now().strftime("%d/%m/%Y"))

        self.show_view("form_op")

    def edit_selected_operation(self):
        selected = self.tree_historico.selection()
        if not selected:
            messagebox.showwarning("Seleção Necessária", "Selecione uma operação no extrato para editar.")
            return

        row_id = int(selected[0])
        # Achar a transação com esse id
        tx = next((t for t in self.transactions if t.id == row_id), None)
        if not tx:
            messagebox.showerror("Erro", "Transação não encontrada.")
            return

        self.editing_tx_id = tx.id
        self.lbl_form_title.configure(text=f"✏️ Editar Operação #{tx.id} ({tx.ticker})")
        self.btn_salvar_op.configure(
            text="💾 Atualizar Operação",
            fg_color=UI_COLORS["blue"],
            hover_color=UI_COLORS["blue_hover"],
        )

        # Preencher campos
        self.form_inputs["entry_cota"].delete(0, "end")
        self.form_inputs["entry_cota"].insert(0, tx.ticker)

        self.form_inputs["opt_tag"].set(tx.tipo_ativo if tx.tipo_ativo in ["fii", "ação", "etf"] else "fii")
        self.form_inputs["opt_operacao"].set(tx.operacao)

        self.form_inputs["entry_qtd"].delete(0, "end")
        self.form_inputs["entry_qtd"].insert(0, str(tx.quantidade))

        self.form_inputs["entry_unit"].delete(0, "end")
        self.form_inputs["entry_unit"].insert(0, f"{tx.valor_unitario:.4f}")

        self.form_inputs["entry_total"].delete(0, "end")
        self.form_inputs["entry_total"].insert(0, f"{tx.valor_total:.2f}")

        self.form_inputs["entry_data"].delete(0, "end")
        if tx.data:
            self.form_inputs["entry_data"].insert(0, tx.data)

        self.show_view("form_op")

    def delete_selected_operation(self):
        selected = self.tree_historico.selection()
        if not selected:
            messagebox.showwarning("Seleção Necessária", "Selecione uma operação no extrato para excluir.")
            return

        row_id = int(selected[0])
        tx = next((t for t in self.transactions if t.id == row_id), None)
        if not tx:
            return

        resp = messagebox.askyesno(
            "Confirmar Exclusão", 
            f"Tem certeza que deseja excluir a operação:\n\n"
            f"Ativo: {tx.ticker}\n"
            f"Tipo: {tx.operacao.upper()} de {tx.quantidade:g} cotas\n"
            f"Valor: R$ {tx.valor_total:.2f}?"
        )
        if not resp:
            return

        try:
            delete_transaction_from_excel(row_id, DEFAULT_EXCEL_PATH)
            messagebox.showinfo("Sucesso", "Operação excluída com sucesso!")
            self.load_data()
        except Exception as e:
            messagebox.showerror("Erro ao Excluir", f"Não foi possível excluir a linha:\n{e}")

    def save_operation(self):
        cota = self.form_inputs["entry_cota"].get().strip().upper()
        tag = self.form_inputs["opt_tag"].get().strip().lower()
        operacao = self.form_inputs["opt_operacao"].get().strip().lower()
        qtd_str = self.form_inputs["entry_qtd"].get().strip().replace(",", ".")
        unit_str = self.form_inputs["entry_unit"].get().strip().replace(",", ".")
        total_str = self.form_inputs["entry_total"].get().strip().replace(",", ".")
        data_str = self.form_inputs["entry_data"].get().strip()

        if not cota:
            messagebox.showwarning("Campo Obrigatório", "Por favor, digite o código do ativo (ex: MXRF11).")
            return

        try:
            qtd = float(qtd_str)
            if qtd <= 0:
                raise ValueError()
        except Exception:
            messagebox.showwarning("Valor Inválido", "A quantidade deve ser um número maior que zero.")
            return

        try:
            unit = float(unit_str) if unit_str else 0.0
            total = float(total_str) if total_str else 0.0

            if unit <= 0 and total <= 0:
                messagebox.showwarning("Valor Inválido", "Informe o Preço Unitário ou o Valor Total.")
                return

            if total <= 0 and unit > 0:
                total = qtd * unit
            elif unit <= 0 and total > 0:
                unit = total / qtd

        except Exception:
            messagebox.showwarning("Valor Inválido", "Informe valores numéricos válidos para preço ou total.")
            return

        # Validação e formatação de data
        if data_str:
            digits = "".join([c for c in data_str if c.isdigit()])
            if len(digits) == 8 and "/" not in data_str:
                data_str = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
            try:
                datetime.strptime(data_str, "%d/%m/%Y")
            except ValueError:
                messagebox.showwarning(
                    "Data Inválida", 
                    f"A data informada '{data_str}' não é válida.\nUtilize o formato DD/MM/AAAA (ex: 10/10/2026)."
                )
                return

        tx = Transaction(
            id=self.editing_tx_id,
            ticker=cota,
            tipo_ativo=tag,
            operacao=operacao,
            quantidade=qtd,
            valor_total=total,
            valor_unitario=unit,
            data=data_str
        )

        try:
            if self.editing_tx_id is not None:
                # Atualização
                update_transaction_in_excel(tx, DEFAULT_EXCEL_PATH)
                messagebox.showinfo("Sucesso", f"Operação #{tx.id} atualizada com sucesso!")
            else:
                # Nova operação
                save_transaction_to_excel(tx, DEFAULT_EXCEL_PATH)
                messagebox.showinfo("Sucesso", f"Operação de {operacao.upper()} cadastrada com sucesso!")

            self.load_data()
            self.show_view("historico" if self.editing_tx_id is not None else ("vendas" if operacao == "venda" else "carteira"))
            self.editing_tx_id = None

        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar na planilha:\n{e}")


if __name__ == "__main__":
    app = InvestApp()
    app.mainloop()
