"""
Testes unitários headless para o módulo de geração de gráficos Matplotlib (charts.py).
"""

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
import pytest

from invest_ai.ui.charts import (
    create_allocation_by_class_figure,
    create_allocation_by_ticker_figure,
    create_monthly_dividends_figure,
)


def test_create_allocation_by_class_figure_com_dados_e_vazio():
    wallet = {
        "MXRF11": {"quantidade": 100.0, "total_investido": 950.0, "tipo_ativo": "fii"},
        "PETR4": {"quantidade": 20.0, "total_investido": 700.0, "tipo_ativo": "ação"},
        "IVVB11": {"quantidade": 2.0, "total_investido": 600.0, "tipo_ativo": "etf"},
    }
    live_quotes = {
        "MXRF11": {"price": 10.0},  # 1000.0
        "PETR4": {"price": 40.0},   # 800.0
        # IVVB11 sem cotação viva -> usa fallback total_investido (600.0)
    }

    fig = create_allocation_by_class_figure(wallet, live_quotes)
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    assert ax.get_title() == "Alocação por Classe"
    assert len(ax.patches) == 3  # 3 classes: FII, AÇÃO, ETF

    legend = ax.get_legend()
    assert legend is not None
    legend_texts = [t.get_text() for t in legend.get_texts()]
    assert any("FII" in txt and "1.000,00" in txt for txt in legend_texts)
    assert any("AÇÃO" in txt and "800,00" in txt for txt in legend_texts)
    assert any("ETF" in txt and "600,00" in txt for txt in legend_texts)

    # Caso vazio
    fig_vazia = create_allocation_by_class_figure({})
    assert isinstance(fig_vazia, Figure)
    ax_vazia = fig_vazia.axes[0]
    assert any("Sem ativos em custódia" in t.get_text() for t in ax_vazia.texts)


def test_create_allocation_by_ticker_figure_top_n_e_outros():
    wallet = {
        f"ATV{i}11": {"quantidade": 10.0, "total_investido": float((10 - i) * 100), "tipo_ativo": "fii"}
        for i in range(1, 7)  # 6 ativos: 900, 800, 700, 600, 500, 400
    }

    fig = create_allocation_by_ticker_figure(wallet, top_n=4)
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    assert ax.get_title() == "Distribuição por Ativo (%)"

    y_labels = [lbl.get_text() for lbl in ax.get_yticklabels()]
    assert "OUTROS" in y_labels
    assert len(y_labels) == 5  # top 4 + OUTROS
    # Maior ativo deve ficar no topo do eixo Y (último tick em barh)
    assert y_labels[-1] == "ATV111"

    # Caso vazio
    fig_vazia = create_allocation_by_ticker_figure({})
    ax_vazia = fig_vazia.axes[0]
    assert any("Sem ativos em custódia" in t.get_text() for t in ax_vazia.texts)


def test_create_monthly_dividends_figure_ordenacao_cronologica_e_vazio():
    mensal_stats = {
        "10/2026": {"total": 125.50, "ativos": {"MXRF11"}, "timestamp": 1790812800},
        "08/2026": {"total": 80.00, "ativos": {"MXRF11"}, "timestamp": 1785542400},
        "09/2026": {"total": 95.25, "ativos": {"MXRF11", "RZAG11"}, "timestamp": 1788220800},
    }

    fig = create_monthly_dividends_figure(mensal_stats, max_months=12)
    assert isinstance(fig, Figure)
    ax = fig.axes[0]
    assert ax.get_title() == "Evolução Mensal de Proventos (R$)"

    x_labels = [lbl.get_text() for lbl in ax.get_xticklabels()]
    assert x_labels == ["08/2026", "09/2026", "10/2026"]

    bar_heights = [rect.get_height() for rect in ax.patches]
    assert bar_heights == pytest.approx([80.00, 95.25, 125.50])

    # Caso vazio
    fig_vazia = create_monthly_dividends_figure({})
    ax_vazia = fig_vazia.axes[0]
    assert any("Sem proventos registrados" in t.get_text() for t in ax_vazia.texts)


def test_attach_tree_scrollbars_configures_x_and_y_scroll(monkeypatch):
    from unittest.mock import MagicMock
    from invest_ai.ui import base_window

    created_scrollbars = []

    class FakeScrollbar:
        def __init__(self, parent, orient=None, command=None):
            self.parent = parent
            self.orient = orient
            self.command = command
            self.set = MagicMock()
            self.grid = MagicMock()
            created_scrollbars.append(self)

    monkeypatch.setattr(base_window.ttk, "Scrollbar", FakeScrollbar)

    container = MagicMock()
    tree = MagicMock()

    app = base_window.InvestApp.__new__(base_window.InvestApp)
    app._attach_tree_scrollbars(container, tree)

    container.grid_rowconfigure.assert_called_once_with(0, weight=1)
    container.grid_columnconfigure.assert_called_once_with(0, weight=1)

    assert len(created_scrollbars) == 2
    y_sb, x_sb = created_scrollbars
    assert y_sb.orient == "vertical"
    assert y_sb.command is tree.yview
    assert x_sb.orient == "horizontal"
    assert x_sb.command is tree.xview

    tree.configure.assert_called_once_with(yscrollcommand=y_sb.set, xscrollcommand=x_sb.set)
    tree.grid.assert_called_once_with(row=0, column=0, sticky="nsew")
    y_sb.grid.assert_called_once_with(row=0, column=1, sticky="ns")
    x_sb.grid.assert_called_once_with(row=1, column=0, sticky="ew")
