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


class InvestApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Calculadora de Investimentos & DARF - FIIs e Ações")
        self.geometry("1120x740")
        self.minsize(980, 670)

        self.engine = InvestmentEngine()
        self.transactions = []
        self.editing_tx_id = None  # None = Nova operação, int = Editando operação existente
        self.live_quotes = {}  # Cache de cotações B3 {ticker: {'price': float, 'var_dia': float}}
        self.is_fetching_quotes = False
        self.dividends_data = {}  # Cache de proventos B3 {ticker: [{...}, ...]}
        self.is_fetching_dividends = False
        self.charts_visible = True
        self._chart_figures = {}
        self._last_wallet = {}

        # Variáveis de filtro e ordenação do extrato
        self.historico_sort_col = "id"
        self.historico_sort_reverse = False
        self.historico_filter_text = ""

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_panel()

        self.load_data()
        # Busca cotações e proventos automaticamente ao iniciar
        self.after(500, self.refresh_quotes_async)
        self.after(1000, self.refresh_dividends_async)

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="📈 InvestDARF", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        logo_label.grid(row=0, column=0, padx=20, pady=(25, 20))

        self.btn_nav_carteira = ctk.CTkButton(
            self.sidebar_frame, text="📊 Carteira Atual", 
            command=lambda: self.show_view("carteira"),
            height=40, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.btn_nav_carteira.grid(row=1, column=0, padx=20, pady=8, sticky="ew")

        self.btn_nav_vendas = ctk.CTkButton(
            self.sidebar_frame, text="💰 Vendas & DARF", 
            command=lambda: self.show_view("vendas"),
            height=40, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.btn_nav_vendas.grid(row=2, column=0, padx=20, pady=8, sticky="ew")

        self.btn_nav_proventos = ctk.CTkButton(
            self.sidebar_frame, text="💵 Proventos Recebidos", 
            command=lambda: self.show_view("proventos"),
            height=40, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.btn_nav_proventos.grid(row=3, column=0, padx=20, pady=8, sticky="ew")

        self.btn_nav_nova = ctk.CTkButton(
            self.sidebar_frame, text="➕ Nova Operação", 
            command=self.prepare_new_operation,
            height=40, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1f7a1f", hover_color="#145214"
        )
        self.btn_nav_nova.grid(row=4, column=0, padx=20, pady=8, sticky="ew")

        self.btn_nav_historico = ctk.CTkButton(
            self.sidebar_frame, text="📑 Extrato Completo", 
            command=lambda: self.show_view("historico"),
            height=40, font=ctk.CTkFont(size=14, weight="bold")
        )
        self.btn_nav_historico.grid(row=5, column=0, padx=20, pady=8, sticky="ew")

        lbl_status = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Planilha:\ninvestimento.xlsx", 
            text_color="gray70", 
            font=ctk.CTkFont(size=11)
        )
        lbl_status.grid(row=7, column=0, padx=20, pady=(10, 5))

        btn_reload = ctk.CTkButton(
            self.sidebar_frame, text="🔄 Recarregar Dados", 
            command=self.load_data, height=32, 
            fg_color="#333333", hover_color="#444444"
        )
        btn_reload.grid(row=8, column=0, padx=20, pady=(5, 20), sticky="ew")

    def _build_main_panel(self):
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.views = {
            "carteira": self._create_carteira_view(),
            "vendas": self._create_vendas_view(),
            "proventos": self._create_proventos_view(),
            "form_op": self._create_form_op_view(),
            "historico": self._create_historico_view()
        }

    def show_view(self, name: str):
        for v_name, frame in self.views.items():
            if v_name == name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

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

    # -------------------------------------------------------------
    # VIEW: CARTEIRA ATUAL
    # -------------------------------------------------------------
    def _create_carteira_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=0)
        frame.grid_rowconfigure(3, weight=1)

        # Cabeçalho com Título e Botão de Atualizar Cotações B3
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame, text="Carteira Atual (Posição em Aberto & Cotação B3)", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w")

        self.btn_toggle_charts = ctk.CTkButton(
            header_frame, text="📊 Ocultar Gráficos",
            command=self._toggle_carteira_charts,
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#374151", hover_color="#4b5563"
        )
        self.btn_toggle_charts.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.btn_refresh_quotes = ctk.CTkButton(
            header_frame, text="📡 Atualizar Cotações B3", 
            command=self.refresh_quotes_async,
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f538d", hover_color="#14375e"
        )
        self.btn_refresh_quotes.grid(row=0, column=2, sticky="e")

        # Cards de Resumo Expandidos (Total Investido, Patrimônio Atual, Lucro/Prejuízo Total, Prejuízo a Compensar)
        cards_frame = ctk.CTkFrame(frame)
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.card_total_investido = self._create_stat_card(cards_frame, 0, "Total Investido", "R$ 0,00", "#1f538d")
        self.card_patrimonio_atual = self._create_stat_card(cards_frame, 1, "Patrimônio Atual (B3)", "R$ 0,00", "#145214")
        self.card_lucro_total = self._create_stat_card(cards_frame, 2, "Lucro / Prejuízo Total", "R$ 0,00", "#2d4a22")
        self.card_prejuizo_acum = self._create_stat_card(cards_frame, 3, "Prejuízo a Compensar (IR)", "R$ 0,00", "#b35900")

        # Gráficos da Carteira (Rosca por Classe + Barras por Ativo)
        self.carteira_charts_frame = ctk.CTkFrame(frame, height=230)
        self.carteira_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.carteira_charts_frame.grid_propagate(False)
        self.carteira_charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.carteira_charts_frame.grid_rowconfigure(0, weight=1)

        self.chart_class_container = ctk.CTkFrame(
            self.carteira_charts_frame, fg_color="#2b2b2b", corner_radius=8
        )
        self.chart_class_container.grid(row=0, column=0, sticky="nsew", padx=(6, 4), pady=6)

        self.chart_ticker_container = ctk.CTkFrame(
            self.carteira_charts_frame, fg_color="#2b2b2b", corner_radius=8
        )
        self.chart_ticker_container.grid(row=0, column=1, sticky="nsew", padx=(4, 6), pady=6)

        tbl_container = ctk.CTkFrame(frame)
        tbl_container.grid(row=3, column=0, sticky="nsew")
        tbl_container.grid_rowconfigure(0, weight=1)
        tbl_container.grid_columnconfigure(0, weight=1)

        cols = ("ticker", "tipo", "quantidade", "preco_medio", "preco_atual", "total_investido", "patrimonio_atual", "lucro_prej", "rentabilidade")
        self.tree_carteira = ttk.Treeview(tbl_container, columns=cols, show="headings", selectmode="browse", height=8)
        self.tree_carteira.heading("ticker", text="Ativo / Cota")
        self.tree_carteira.heading("tipo", text="Tipo")
        self.tree_carteira.heading("quantidade", text="Qtd")
        self.tree_carteira.heading("preco_medio", text="Preço Médio (PM)")
        self.tree_carteira.heading("preco_atual", text="Preço Atual (B3)")
        self.tree_carteira.heading("total_investido", text="Total Investido")
        self.tree_carteira.heading("patrimonio_atual", text="Patrimônio Atual")
        self.tree_carteira.heading("lucro_prej", text="Lucro/Prejuízo")
        self.tree_carteira.heading("rentabilidade", text="Rentab. (%)")

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

        return frame

    # -------------------------------------------------------------
    # VIEW: VENDAS & DARF
    # -------------------------------------------------------------
    def _create_vendas_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        frame.grid_rowconfigure(5, weight=2)

        title = ctk.CTkLabel(
            frame, text="Apuração de Vendas & Cálculo de DARF", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        info_frame = ctk.CTkFrame(frame, fg_color="#1c2430", corner_radius=8)
        info_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15), padx=2)
        info_lbl = ctk.CTkLabel(
            info_frame, 
            text="📌 Regra dos FIIs: Alíquota de 20% sobre o lucro líquido. Venda com prejuízo acumula saldo para abater dos lucros futuros.\n"
                 "📌 Regra de Ações: Vendas totais até R$ 20.000 no mês são isentas de IR no swing trade.",
            justify="left", font=ctk.CTkFont(size=12)
        )
        info_lbl.pack(padx=15, pady=10, anchor="w")

        # Subcabeçalho com Título e Botão de Marcar DARF Pago
        sub1_box = ctk.CTkFrame(frame, fg_color="transparent")
        sub1_box.grid(row=2, column=0, sticky="ew", pady=(5, 5))
        sub1_box.grid_columnconfigure(0, weight=1)

        lbl_sub1 = ctk.CTkLabel(sub1_box, text="📅 Resumo Fiscal por Período / Mês", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sub1.grid(row=0, column=0, sticky="w")

        btn_pagar_darf = ctk.CTkButton(
            sub1_box, text="🧾 Marcar DARF como Pago", 
            command=self.mark_darf_as_paid,
            height=32, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f7a1f", hover_color="#145214"
        )
        btn_pagar_darf.grid(row=0, column=1, sticky="e")

        tbl_darf_container = ctk.CTkFrame(frame, height=135)
        tbl_darf_container.grid(row=3, column=0, sticky="nsew", pady=(0, 15))
        tbl_darf_container.grid_rowconfigure(0, weight=1)
        tbl_darf_container.grid_columnconfigure(0, weight=1)

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

        lbl_sub2 = ctk.CTkLabel(frame, text="🧾 Histórico Detalhado de Vendas", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sub2.grid(row=4, column=0, sticky="w", pady=(5, 5))

        tbl_sales_container = ctk.CTkFrame(frame, height=180)
        tbl_sales_container.grid(row=5, column=0, sticky="nsew")
        tbl_sales_container.grid_rowconfigure(0, weight=1)
        tbl_sales_container.grid_columnconfigure(0, weight=1)

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
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header_frame, text="Proventos & Rendimentos (Dividendos Recebidos)", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w")

        self.btn_refresh_divs = ctk.CTkButton(
            header_frame, text="📡 Buscar Histórico de Proventos", 
            command=self.refresh_dividends_async,
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#145214", hover_color="#0e3a0e"
        )
        self.btn_refresh_divs.grid(row=0, column=1, sticky="e")

        # Cards de Resumo de Proventos
        cards_frame = ctk.CTkFrame(frame)
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.card_total_proventos = self._create_stat_card(cards_frame, 0, "Total de Proventos Estimados (12M)", "R$ 0,00", "#145214")
        self.card_media_mensal = self._create_stat_card(cards_frame, 1, "Média Mensal Estimada", "R$ 0,00", "#1f538d")
        self.card_yield_medio = self._create_stat_card(cards_frame, 2, "Dividend Yield Anual (Yield on Cost)", "0.00%", "#b35900")

        # Gráfico de Evolução Mensal de Proventos
        self.proventos_chart_frame = ctk.CTkFrame(
            frame, height=200, fg_color="#2b2b2b", corner_radius=8
        )
        self.proventos_chart_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.proventos_chart_frame.grid_propagate(False)

        # Tabela 1: Resumo Mensal de Proventos
        lbl_sub1 = ctk.CTkLabel(frame, text="📅 Rendimentos Recebidos por Mês", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sub1.grid(row=3, column=0, sticky="w", pady=(5, 5))

        tbl_month_container = ctk.CTkFrame(frame, height=130)
        tbl_month_container.grid(row=4, column=0, sticky="nsew", pady=(0, 12))
        tbl_month_container.grid_rowconfigure(0, weight=1)
        tbl_month_container.grid_columnconfigure(0, weight=1)

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

        # Tabela 2: Detalhamento por Ativo / Pagamento
        lbl_sub2 = ctk.CTkLabel(frame, text="🧾 Detalhamento por Ativo e Pagamento Oficial", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sub2.grid(row=5, column=0, sticky="w", pady=(5, 5))

        tbl_divs_container = ctk.CTkFrame(frame, height=160)
        tbl_divs_container.grid(row=6, column=0, sticky="nsew")
        tbl_divs_container.grid_rowconfigure(0, weight=1)
        tbl_divs_container.grid_columnconfigure(0, weight=1)

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

        self._render_proventos_chart({})
        return frame

    # -------------------------------------------------------------
    # VIEW: FORMULÁRIO OPERAÇÃO (NOVA / EDITAR)
    # -------------------------------------------------------------
    def _create_form_op_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        self.lbl_form_title = ctk.CTkLabel(
            frame, text="Cadastrar Nova Movimentação (Compra ou Venda)", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.lbl_form_title.grid(row=0, column=0, sticky="w", pady=(0, 20))

        form = ctk.CTkFrame(frame, width=620)
        form.grid(row=1, column=0, sticky="n", pady=10, padx=40)
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
            lbl = ctk.CTkLabel(form, text=label_text, font=ctk.CTkFont(size=14))
            lbl.grid(row=idx, column=0, padx=20, pady=10, sticky="w")

            if isinstance(default, list):
                widget = ctk.CTkOptionMenu(form, values=default, width=250)
                widget.set(default[0])
            else:
                widget = ctk.CTkEntry(form, placeholder_text=default, width=250)
                if key == "entry_data" and default:
                    widget.insert(0, default)
            
            widget.grid(row=idx, column=1, padx=20, pady=10, sticky="e")
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
        btn_box.grid(row=len(fields), column=0, columnspan=2, padx=20, pady=(25, 20), sticky="ew")
        btn_box.grid_columnconfigure((0, 1), weight=1)

        self.btn_salvar_op = ctk.CTkButton(
            btn_box, text="💾 Salvar Operação", 
            command=self.save_operation,
            height=45, font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#1f7a1f", hover_color="#145214"
        )
        self.btn_salvar_op.grid(row=0, column=0, padx=5, sticky="ew")

        self.btn_cancelar_edicao = ctk.CTkButton(
            btn_box, text="❌ Cancelar", 
            command=lambda: self.show_view("historico"),
            height=45, font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#666666", hover_color="#555555"
        )
        self.btn_cancelar_edicao.grid(row=0, column=1, padx=5, sticky="ew")

        return frame

    # -------------------------------------------------------------
    # VIEW: HISTÓRICO COMPLETO COM BOTÕES EDITAR / EXCLUIR
    # -------------------------------------------------------------
    def _create_historico_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            frame, text="Extrato de Todas as Operações Cadastradas", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Barra de ferramentas com Busca por Ativo, Editar e Excluir
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        btn_edit = ctk.CTkButton(
            toolbar, text="✏️ Editar Selecionada", 
            command=self.edit_selected_operation,
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1f538d", hover_color="#14375e"
        )
        btn_edit.pack(side="left", padx=(0, 8))

        btn_delete = ctk.CTkButton(
            toolbar, text="🗑️ Excluir Selecionada", 
            command=self.delete_selected_operation,
            height=34, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#8a1c1c", hover_color="#631414"
        )
        btn_delete.pack(side="left", padx=(0, 15))

        # Campo de Busca/Filtro por Ativo
        lbl_busca = ctk.CTkLabel(toolbar, text="🔍 Filtrar Ativo:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_busca.pack(side="left", padx=(5, 5))

        self.entry_filtro_ativo = ctk.CTkEntry(toolbar, placeholder_text="Ex: MXRF11, PETR4...", width=180, height=34)
        self.entry_filtro_ativo.pack(side="left", padx=(0, 8))
        self.entry_filtro_ativo.bind("<KeyRelease>", self._on_filter_historico_changed)

        btn_limpar_filtro = ctk.CTkButton(
            toolbar, text="✖ Limpar", 
            command=self._clear_filter_historico,
            height=34, width=70, font=ctk.CTkFont(size=12),
            fg_color="#444444", hover_color="#555555"
        )
        btn_limpar_filtro.pack(side="left", padx=(0, 10))

        lbl_dica = ctk.CTkLabel(
            toolbar, 
            text="💡 Dica: Clique no título de qualquer coluna para ordenar.", 
            text_color="gray70", font=ctk.CTkFont(size=11)
        )
        lbl_dica.pack(side="right", padx=5)

        # Tabela
        tbl_container = ctk.CTkFrame(frame)
        tbl_container.grid(row=2, column=0, sticky="nsew")
        tbl_container.grid_rowconfigure(0, weight=1)
        tbl_container.grid_columnconfigure(0, weight=1)

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
            self.tree_historico.insert("", "end", iid=str(tx.id), values=(
                idx,
                tx.data or "-",
                tx.ticker,
                tx.tipo_ativo.upper(),
                tx.operacao.capitalize(),
                f"{tx.quantidade:g}",
                f"R$ {tx.valor_unitario:.2f}",
                f"R$ {tx.valor_total:.2f}"
            ))

    # -------------------------------------------------------------
    # AUXILIARES VISUAIS & DADOS
    # -------------------------------------------------------------
    def _create_stat_card(self, parent, col, title, initial_val, color):
        card = ctk.CTkFrame(parent, fg_color=color, corner_radius=10)
        card.grid(row=0, column=col, padx=8, pady=8, sticky="ew")

        lbl_title = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="normal"), text_color="white")
        lbl_title.pack(padx=15, pady=(10, 2), anchor="w")

        lbl_val = ctk.CTkLabel(card, text=initial_val, font=ctk.CTkFont(size=20, weight="bold"), text_color="white")
        lbl_val.pack(padx=15, pady=(0, 10), anchor="w")

        return lbl_val

    def load_data(self):
        """Carrega transações do Excel e atualiza a interface."""
        self.transactions = load_transactions_from_excel(DEFAULT_EXCEL_PATH)
        self.engine.set_transactions(self.transactions)
        res = self.engine.calculate()

        # 1. Tabela Carteira com Cotações de Mercado B3
        for item in self.tree_carteira.get_children():
            self.tree_carteira.delete(item)

        total_investido_carteira = 0.0
        patrimonio_total_mercado = 0.0

        for ticker, data in sorted(res['wallet'].items()):
            qtd = data['quantidade']
            investido = data['total_investido']
            total_investido_carteira += investido

            # Verifica se temos cotação de mercado para esse ativo
            quote_data = self.live_quotes.get(ticker)
            if quote_data and quote_data.get("price") is not None:
                cur_price = quote_data["price"]
                cur_val = qtd * cur_price
                lucro_prej = cur_val - investido
                rentab = ((cur_val - investido) / investido * 100) if investido > 0 else 0.0
                patrimonio_total_mercado += cur_val

                str_preco_atual = f"R$ {cur_price:.2f}"
                str_patrimonio = f"R$ {cur_val:.2f}"
                str_lucro_prej = f"{'+' if lucro_prej >= 0 else '-'}R$ {abs(lucro_prej):.2f}"
                str_rentab = f"{rentab:+.2f}%"
            else:
                patrimonio_total_mercado += investido
                str_preco_atual = "Consultando..."
                str_patrimonio = f"R$ {investido:.2f}"
                str_lucro_prej = "R$ 0,00"
                str_rentab = "0.00%"

            self.tree_carteira.insert("", "end", values=(
                data['ticker'],
                data['tipo_ativo'].upper(),
                f"{qtd:g}",
                f"R$ {data['preco_medio']:.2f}",
                str_preco_atual,
                f"R$ {investido:.2f}",
                str_patrimonio,
                str_lucro_prej,
                str_rentab
            ))

        lucro_total_carteira = patrimonio_total_mercado - total_investido_carteira
        rentab_total_carteira = ((lucro_total_carteira / total_investido_carteira) * 100) if total_investido_carteira > 0 else 0.0

        self.card_total_investido.configure(text=f"R$ {total_investido_carteira:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_patrimonio_atual.configure(text=f"R$ {patrimonio_total_mercado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_lucro_total.configure(
            text=f"{'+' if lucro_total_carteira >= 0 else '-'}R$ {abs(lucro_total_carteira):,.2f} ({rentab_total_carteira:+.2f}%)".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        self._last_wallet = res['wallet']
        if self.charts_visible:
            self._render_carteira_charts(res['wallet'], self.live_quotes)

        # 2. Resumo DARF (com controle de DARFs pagos)
        for item in self.tree_darf.get_children():
            self.tree_darf.delete(item)

        paid_darfs = load_paid_darfs(DEFAULT_EXCEL_PATH)
        ultimo_prejuizo_fii = 0.0

        for tax in res['tax_reports']:
            ultimo_prejuizo_fii = tax.prejuizo_restante_acumulado
            status_darf = f"R$ {tax.imposto_devido:.2f}"
            
            # Chave de busca de pagamento
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

            # Identificador único para a linha: MES__TIPO
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
            ))

        self.card_prejuizo_acum.configure(text=f"R$ {ultimo_prejuizo_fii:.2f}".replace(".", ","))

        # 3. Tabela Vendas
        for item in self.tree_sales.get_children():
            self.tree_sales.delete(item)

        for s in res['sales']:
            res_val = f"R$ {s.lucro_prejuizo:.2f}"
            if s.lucro_prejuizo < 0:
                res_val = f"-R$ {abs(s.lucro_prejuizo):.2f}"

            self.tree_sales.insert("", "end", values=(
                s.data or "-",
                s.ticker,
                s.tipo_ativo.upper(),
                f"{s.quantidade_vendida:g}",
                f"R$ {s.preco_medio_compra:.2f}",
                f"R$ {s.preco_venda_unitario:.2f}",
                f"R$ {s.valor_venda_total:.2f}",
                res_val
            ))

        # 4. Extrato Completo
        self._populate_historico_table()

    def refresh_quotes_async(self):
        """Dispara a busca de cotações em background sem travar a interface."""
        if self.is_fetching_quotes:
            return

        self.is_fetching_quotes = True
        self.btn_refresh_quotes.configure(text="⏳ Atualizando...", state="disabled")

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
        self.btn_refresh_quotes.configure(text="📡 Atualizar Cotações B3", state="normal")
        self.load_data()

    def refresh_dividends_async(self):
        """Busca histórico oficial de proventos pagos em background e calcula rendimentos da carteira."""
        if self.is_fetching_dividends:
            return

        self.is_fetching_dividends = True
        self.btn_refresh_divs.configure(text="⏳ Buscando Proventos...", state="disabled")

        def task():
            res = self.engine.calculate()
            tickers = list(res['wallet'].keys())
            novos_proventos = fetch_all_dividends(tickers)
            self.dividends_data.update(novos_proventos)

            self.after(0, self._on_dividends_fetched)

        threading.Thread(target=task, daemon=True).start()

    def _on_dividends_fetched(self):
        self.is_fetching_dividends = False
        self.btn_refresh_divs.configure(text="📡 Buscar Histórico de Proventos", state="normal")
        self._update_dividends_view()

    def _update_dividends_view(self):
        """Calcula os proventos com base nas cotas do usuário e preenche as tabelas."""
        res = self.engine.calculate()
        carteira = res['wallet']

        for item in self.tree_proventos_mes.get_children():
            self.tree_proventos_mes.delete(item)
        for item in self.tree_proventos_detalhe.get_children():
            self.tree_proventos_detalhe.delete(item)

        # Cálculo real baseado na posição de cotas que você possuía em cada época
        todos_pagamentos, mensal_stats = calculate_historical_dividends(
            self.transactions, self.dividends_data
        )

        for p in todos_pagamentos:
            self.tree_proventos_detalhe.insert("", "end", values=(
                p["data"],
                p["ticker"],
                f"{p['qtd']:g}",
                f"R$ {p['unit']:.4f}",
                f"R$ {p['total']:.2f}"
            ))

        # Preencher tabela mensal
        meses_ordenados = sorted(mensal_stats.items(), key=lambda x: x[1]["timestamp"], reverse=True)
        total_historico_recebido = sum(st["total"] for st in mensal_stats.values())
        
        # Últimos 12 meses para cálculo de média e yield anual
        meses_12m = meses_ordenados[:12]
        total_12m = sum(st["total"] for _, st in meses_12m)

        total_investido_carteira = sum(d['total_investido'] for d in carteira.values())

        for mes_ano, st in meses_ordenados:
            total_mes = st["total"]
            qtd_atv = len(st["ativos"])
            yield_mes = (total_mes / total_investido_carteira * 100) if total_investido_carteira > 0 else 0.0

            self.tree_proventos_mes.insert("", "end", values=(
                mes_ano,
                f"R$ {total_mes:.2f}",
                f"{qtd_atv} ativo(s)",
                f"{yield_mes:.2f}%"
            ))

        media_mensal = (total_12m / len(meses_12m)) if meses_12m else 0.0
        yield_anual = (total_12m / total_investido_carteira * 100) if total_investido_carteira > 0 else 0.0

        self.card_total_proventos.configure(text=f"R$ {total_historico_recebido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_media_mensal.configure(text=f"R$ {media_mensal:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.card_yield_medio.configure(text=f"{yield_anual:.2f}% a.a.")
        self._render_proventos_chart(mensal_stats)

    def _render_figure_in_container(self, container, figure, slot_key: str):
        """Renderiza uma Figure Matplotlib em um container CTkFrame fechando a figura anterior."""
        prev_fig = self._chart_figures.pop(slot_key, None)
        if prev_fig is not None:
            plt.close(prev_fig)

        for child in container.winfo_children():
            child.destroy()

        canvas = FigureCanvasTkAgg(figure, master=container)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True, padx=4, pady=4)
        self._chart_figures[slot_key] = figure

    def _toggle_carteira_charts(self):
        """Alterna a exibição do painel de gráficos da Carteira Atual."""
        self.charts_visible = not self.charts_visible
        if self.charts_visible:
            self.carteira_charts_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
            self.btn_toggle_charts.configure(text="📊 Ocultar Gráficos")
            self._render_carteira_charts(self._last_wallet, self.live_quotes)
        else:
            self.carteira_charts_frame.grid_forget()
            self.btn_toggle_charts.configure(text="📊 Mostrar Gráficos")

    def _render_carteira_charts(self, wallet: dict, live_quotes: dict):
        """Atualiza os gráficos de alocação por classe e distribuição por ativo."""
        fig_class = create_allocation_by_class_figure(wallet, live_quotes)
        self._render_figure_in_container(self.chart_class_container, fig_class, "carteira_class")

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
        dialog.geometry("400x260")
        dialog.resizable(False, False)
        dialog.grab_set()

        lbl_info = ctk.CTkLabel(
            dialog, 
            text=f"Registrar pagamento de DARF:\n\nPeríodo: {mes_ano} | Tipo: {tipo.upper()}\nValor Devido: R$ {imposto_val:.2f}",
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="center"
        )
        lbl_info.pack(pady=(20, 15))

        f_inputs = ctk.CTkFrame(dialog, fg_color="transparent")
        f_inputs.pack(pady=5)

        lbl_dt = ctk.CTkLabel(f_inputs, text="Data do Pagamento:", font=ctk.CTkFont(size=13))
        lbl_dt.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ent_dt = ctk.CTkEntry(f_inputs, width=150)
        ent_dt.insert(0, datetime.now().strftime("%d/%m/%Y"))
        ent_dt.grid(row=0, column=1, padx=10, pady=5)

        lbl_val = ctk.CTkLabel(f_inputs, text="Valor Pago (R$):", font=ctk.CTkFont(size=13))
        lbl_val.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ent_val = ctk.CTkEntry(f_inputs, width=150)
        ent_val.insert(0, f"{imposto_val:.2f}")
        ent_val.grid(row=1, column=1, padx=10, pady=5)

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

        btn_ok = ctk.CTkButton(dialog, text="✅ Confirmar Pagamento", command=confirmar, fg_color="#1f7a1f", hover_color="#145214", height=36)
        btn_ok.pack(pady=(20, 10), padx=30, fill="x")

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
        self.lbl_form_title.configure(text="Cadastrar Nova Movimentação (Compra ou Venda)")
        self.btn_salvar_op.configure(text="💾 Salvar Operação", fg_color="#1f7a1f", hover_color="#145214")
        
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
        self.btn_salvar_op.configure(text="💾 Atualizar Operação", fg_color="#1f538d", hover_color="#14375e")

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
