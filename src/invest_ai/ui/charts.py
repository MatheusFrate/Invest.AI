"""
Módulo de geração de gráficos financeiros estilizados (Dark Theme) com Matplotlib.
Fornece funções puras que retornam objetos matplotlib.figure.Figure para integração
no CustomTkinter (FigureCanvasTkAgg) e validação headless em testes unitários.
"""

from typing import Dict, List, Optional, Tuple
from matplotlib.figure import Figure


BG_COLOR = "#2b2b2b"
TEXT_COLOR = "#e5e7eb"
MUTED_TEXT_COLOR = "#9ca3af"
GRID_COLOR = "#3f3f46"
ACCENT_GREEN = "#10b981"
ACCENT_RED = "#ef4444"
ACCENT_AMBER = "#f59e0b"
PALETTE = [
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#8b5cf6",
    "#ec4899",
    "#06b6d4",
    "#f97316",
    "#14b8a6",
]


def _criar_figura_base(figsize: Tuple[float, float]) -> Tuple[Figure, any]:
    """Cria uma Figure e um Axes com estilização Dark consistente."""
    fig = Figure(figsize=figsize, dpi=100, facecolor=BG_COLOR)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(GRID_COLOR)
    return fig, ax


def _renderizar_estado_vazio(ax, titulo: str, mensagem: str) -> None:
    """Exibe mensagem centralizada quando não há dados para plotagem."""
    ax.axis("off")
    ax.set_title(titulo, color=TEXT_COLOR, fontsize=10, fontweight="bold", pad=8)
    ax.text(
        0.5,
        0.5,
        mensagem,
        ha="center",
        va="center",
        color=MUTED_TEXT_COLOR,
        fontsize=9,
        transform=ax.transAxes,
    )


def _calcular_valores_ativos(
    wallet: Dict[str, Dict], live_quotes: Optional[Dict[str, Dict]] = None
) -> List[Tuple[str, str, float]]:
    """
    Calcula o valor atual (ou custo investido como fallback) de cada ativo da carteira.
    Retorna lista de tuplas (ticker, classe_upper, valor_financeiro).
    """
    quotes = live_quotes or {}
    itens: List[Tuple[str, str, float]] = []

    for ticker, dados in wallet.items():
        qtd = float(dados.get("quantidade", 0.0) or 0.0)
        if qtd <= 0:
            continue

        quote = quotes.get(ticker) or {}
        preco_vivo = quote.get("price")
        if preco_vivo is not None and float(preco_vivo) > 0:
            valor = qtd * float(preco_vivo)
        else:
            valor = float(dados.get("total_investido", 0.0) or 0.0)

        if valor > 0:
            classe = str(dados.get("tipo_ativo", "OUTROS")).strip().upper()
            itens.append((ticker.strip().upper(), classe, valor))

    return itens


def create_allocation_by_class_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    figsize: Tuple[float, float] = (4.5, 2.5),
) -> Figure:
    """Gera gráfico de rosca (donut) com a alocação da carteira por classe de ativo."""
    fig, ax = _criar_figura_base(figsize)
    ativos = _calcular_valores_ativos(wallet, live_quotes)

    por_classe: Dict[str, float] = {}
    for _, classe, valor in ativos:
        por_classe[classe] = por_classe.get(classe, 0.0) + valor

    total = sum(por_classe.values())
    if total <= 0:
        _renderizar_estado_vazio(ax, "Alocação por Classe", "Sem ativos em custódia")
        fig.tight_layout()
        return fig

    ordenado = sorted(por_classe.items(), key=lambda x: x[1], reverse=True)
    labels = [c for c, _ in ordenado]
    valores = [v for _, v in ordenado]
    cores = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]

    wedges, _, autotexts = ax.pie(
        valores,
        colors=cores,
        autopct="%1.1f%%",
        pctdistance=0.77,
        startangle=90,
        wedgeprops=dict(width=0.45, edgecolor=BG_COLOR, linewidth=2),
        textprops=dict(color=TEXT_COLOR, fontsize=8, fontweight="bold"),
    )
    for txt in autotexts:
        txt.set_color("#ffffff")

    for wedge, lbl, val in zip(wedges, labels, valores):
        pct = (val / total) * 100.0 if total > 0 else 0.0
        wedge._tooltip_text = (
            f"{lbl}: R$ {val:,.2f} ({pct:.1f}%)"
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    legend_labels = [
        f"{lbl}: R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        for lbl, val in zip(labels, valores)
    ]
    ax.legend(
        wedges,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(0.95, 0.5),
        frameon=False,
        labelcolor=TEXT_COLOR,
        fontsize=8,
    )
    ax.set_title("Alocação por Classe", color=TEXT_COLOR, fontsize=10, fontweight="bold", pad=8)
    fig.tight_layout()
    return fig


def create_allocation_by_ticker_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (5.0, 2.5),
) -> Figure:
    """Gera gráfico de barras horizontais com o percentual dos principais ativos."""
    fig, ax = _criar_figura_base(figsize)
    ativos = _calcular_valores_ativos(wallet, live_quotes)

    total = sum(v for _, _, v in ativos)
    if total <= 0:
        _renderizar_estado_vazio(ax, "Distribuição por Ativo (%)", "Sem ativos em custódia")
        fig.tight_layout()
        return fig

    ordenado = sorted(ativos, key=lambda x: x[2], reverse=True)
    principais = [(t, v) for t, _, v in ordenado[:top_n]]
    if len(ordenado) > top_n:
        restante = sum(v for _, _, v in ordenado[top_n:])
        if restante > 0:
            principais.append(("OUTROS", restante))

    # Inverte para que o maior fique no topo do barh
    principais_rev = list(reversed(principais))
    tickers = [t for t, _ in principais_rev]
    percentuais = [(v / total) * 100.0 for _, v in principais_rev]
    cores = [
        PALETTE[(len(principais) - 1 - idx) % len(PALETTE)]
        for idx in range(len(principais_rev))
    ]

    bars = ax.barh(tickers, percentuais, color=cores, height=0.6)
    max_pct = max(percentuais) if percentuais else 10.0
    ax.set_xlim(0, max_pct * 1.25)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.xaxis.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax.set_axisbelow(True)

    for (ticker, val), bar, pct in zip(principais_rev, bars, percentuais):
        bar._tooltip_text = (
            f"{ticker}: {pct:.1f}% (R$ {val:,.2f})"
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )
        ax.text(
            bar.get_width() + max_pct * 0.02,
            bar.get_y() + bar.get_height() / 2.0,
            f"{pct:.1f}%",
            va="center",
            ha="left",
            color=TEXT_COLOR,
            fontsize=8,
        )

    ax.set_title("Distribuição por Ativo (%)", color=TEXT_COLOR, fontsize=10, fontweight="bold", pad=8)
    fig.tight_layout()
    return fig


def create_monthly_dividends_figure(
    mensal_stats: Dict[str, Dict],
    max_months: int = 12,
    figsize: Tuple[float, float] = (8.5, 2.2),
) -> Figure:
    """Gera gráfico de barras verticais com a evolução mensal dos proventos em R$."""
    fig, ax = _criar_figura_base(figsize)

    if not mensal_stats:
        _renderizar_estado_vazio(ax, "Evolução Mensal de Proventos (R$)", "Sem proventos registrados")
        fig.tight_layout()
        return fig

    # Seleciona os últimos max_months mais recentes e ordena cronologicamente (esq -> dir)
    mais_recentes = sorted(
        mensal_stats.items(),
        key=lambda item: item[1].get("timestamp", 0),
        reverse=True,
    )[:max_months]
    cronologico = sorted(mais_recentes, key=lambda item: item[1].get("timestamp", 0))

    meses = [m for m, _ in cronologico]
    totais = [float(st.get("total", 0.0) or 0.0) for _, st in cronologico]

    if sum(totais) <= 0:
        _renderizar_estado_vazio(ax, "Evolução Mensal de Proventos (R$)", "Sem proventos registrados")
        fig.tight_layout()
        return fig

    bars = ax.bar(meses, totais, color=ACCENT_GREEN, width=0.55)
    max_val = max(totais) if totais else 1.0
    ax.set_ylim(0, max_val * 1.25)
    ax.yaxis.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=8)

    for mes, bar, val in zip(meses, bars, totais):
        bar._tooltip_text = f"{mes}: R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_val * 0.03,
            f"R$ {val:.2f}".replace(".", ","),
            ha="center",
            va="bottom",
            color=TEXT_COLOR,
            fontsize=7.5,
        )

    ax.set_title(
        "Evolução Mensal de Proventos (R$)",
        color=TEXT_COLOR,
        fontsize=10,
        fontweight="bold",
        pad=8,
    )
    fig.tight_layout()
    return fig


def create_profitability_by_ticker_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (5.0, 2.5),
) -> Figure:
    """Gera gráfico de barras horizontais divergentes com a rentabilidade (%) por ativo."""
    fig, ax = _criar_figura_base(figsize)
    quotes = live_quotes or {}
    itens: List[Tuple[str, float, float]] = []

    for ticker, dados in wallet.items():
        qtd = float(dados.get("quantidade", 0.0) or 0.0)
        investido = float(dados.get("total_investido", 0.0) or 0.0)
        if qtd <= 0 or investido <= 0:
            continue
        quote = quotes.get(ticker) or {}
        preco_vivo = quote.get("price")
        if preco_vivo is not None and float(preco_vivo) > 0:
            valor_atual = qtd * float(preco_vivo)
        else:
            valor_atual = investido
        lucro = valor_atual - investido
        rentab = (lucro / investido) * 100.0
        itens.append((ticker.strip().upper(), rentab, lucro))

    if not itens:
        _renderizar_estado_vazio(ax, "Rentabilidade por Ativo (%)", "Sem ativos em custódia")
        fig.tight_layout()
        return fig

    # Seleciona os top_n por maior variação absoluta e ordena para exibição
    top_itens = sorted(itens, key=lambda x: abs(x[1]), reverse=True)[:top_n]
    ordenados = sorted(top_itens, key=lambda x: x[1])
    tickers = [t for t, _, _ in ordenados]
    rentabs = [r for _, r, _ in ordenados]
    lucros = [l for _, _, l in ordenados]
    cores = [ACCENT_GREEN if r >= 0 else ACCENT_RED for r in rentabs]

    bars = ax.barh(tickers, rentabs, color=cores, height=0.6)
    max_abs = max((abs(r) for r in rentabs), default=5.0)
    pad = max(max_abs * 0.28, 2.0)
    min_x = min(min(rentabs), 0.0) - pad
    max_x = max(max(rentabs), 0.0) + pad
    ax.set_xlim(min_x, max_x)
    ax.axvline(0, color=GRID_COLOR, linewidth=1)
    ax.xaxis.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax.set_axisbelow(True)

    offset = max(max_abs * 0.03, 0.3)
    for ticker, bar, r, l in zip(tickers, bars, rentabs, lucros):
        ha = "left" if r >= 0 else "right"
        x_pos = bar.get_width() + offset if r >= 0 else bar.get_width() - offset
        ax.text(
            x_pos,
            bar.get_y() + bar.get_height() / 2.0,
            f"{r:+.1f}%",
            va="center",
            ha=ha,
            color=TEXT_COLOR,
            fontsize=8,
        )
        sinal = "+" if l >= 0 else "-"
        bar._tooltip_text = (
            f"{ticker}: {r:+.2f}% ({sinal}R$ {abs(l):,.2f})"
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    ax.set_title("Rentabilidade por Ativo (%)", color=TEXT_COLOR, fontsize=10, fontweight="bold", pad=8)
    fig.tight_layout()
    return fig


def create_sales_darf_summary_figure(
    tax_reports: List,
    max_months: int = 8,
    figsize: Tuple[float, float] = (8.5, 1.8),
) -> Figure:
    """Gera gráfico mensal comparando Resultado Líquido (R$) e DARF Apurado (R$)."""
    fig, ax = _criar_figura_base(figsize)

    if not tax_reports:
        _renderizar_estado_vazio(ax, "Resumo Mensal: Resultado vs. DARF (R$)", "Sem vendas apuradas")
        fig.tight_layout()
        return fig

    por_mes: Dict[str, Dict[str, float]] = {}
    for rep in tax_reports:
        if isinstance(rep, dict):
            mes_ano = str(rep.get("mes_ano", "")).strip()
            res_liq = float(rep.get("resultado_liquido", 0.0) or 0.0)
            darf = float(rep.get("imposto_devido", 0.0) or 0.0)
        else:
            mes_ano = str(getattr(rep, "mes_ano", "")).strip()
            res_liq = float(getattr(rep, "resultado_liquido", 0.0) or 0.0)
            darf = float(getattr(rep, "imposto_devido", 0.0) or 0.0)
        if not mes_ano:
            continue
        bucket = por_mes.setdefault(mes_ano, {"resultado": 0.0, "darf": 0.0})
        bucket["resultado"] += res_liq
        bucket["darf"] += darf

    if not por_mes:
        _renderizar_estado_vazio(ax, "Resumo Mensal: Resultado vs. DARF (R$)", "Sem vendas apuradas")
        fig.tight_layout()
        return fig

    def _mes_sort_key(mes_str: str) -> Tuple[int, int]:
        try:
            mm, yyyy = mes_str.split("/")
            return int(yyyy), int(mm)
        except Exception:
            return (0, 0)

    meses_ord = sorted(por_mes.keys(), key=_mes_sort_key)[-max_months:]
    resultados = [por_mes[m]["resultado"] for m in meses_ord]
    darfs = [por_mes[m]["darf"] for m in meses_ord]

    x_idx = list(range(len(meses_ord)))
    width = 0.36
    x_res = [x - width / 2 for x in x_idx]
    x_darf = [x + width / 2 for x in x_idx]
    cores_res = [ACCENT_GREEN if v >= 0 else ACCENT_RED for v in resultados]

    bars_res = ax.bar(x_res, resultados, width=width, color=cores_res, label="Resultado Líquido")
    bars_darf = ax.bar(x_darf, darfs, width=width, color=ACCENT_AMBER, label="DARF Devido")

    for mes, b_res, v_res in zip(meses_ord, bars_res, resultados):
        b_res._tooltip_text = f"{mes} • Resultado: R$ {v_res:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    for mes, b_darf, v_darf in zip(meses_ord, bars_darf, darfs):
        b_darf._tooltip_text = f"{mes} • DARF: R$ {v_darf:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    ax.axhline(0, color=GRID_COLOR, linewidth=1)
    ax.yaxis.grid(True, linestyle="--", alpha=0.25, color=GRID_COLOR)
    ax.set_axisbelow(True)
    ax.set_xticks(x_idx)
    ax.set_xticklabels(meses_ord, fontsize=8)
    ax.legend(loc="upper right", frameon=False, labelcolor=TEXT_COLOR, fontsize=7.5, ncol=2)
    ax.set_title(
        "Resumo Mensal: Resultado vs. DARF (R$)",
        color=TEXT_COLOR,
        fontsize=10,
        fontweight="bold",
        pad=8,
    )
    fig.tight_layout()
    return fig


def attach_matplotlib_tooltip(canvas, figure: Figure):
    """Conecta tooltip interativo (hover) nos patches visíveis de uma Figure no canvas."""
    from matplotlib.patches import Rectangle, Wedge

    axes = [ax for ax in figure.axes if ax.axison]
    if not axes:
        return None

    ax = axes[0]
    annot = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(8, 8),
        textcoords="offset points",
        bbox=dict(boxstyle="round,pad=0.35", fc="#18181b", ec="#3f3f46", alpha=0.95),
        color="#ffffff",
        fontsize=8,
    )
    annot.set_visible(False)

    def _get_patch_anchor(patch) -> Tuple[float, float]:
        if isinstance(patch, Rectangle):
            return patch.get_x() + patch.get_width() / 2.0, patch.get_y() + patch.get_height() / 2.0
        if isinstance(patch, Wedge):
            import math
            ang = math.radians((patch.theta1 + patch.theta2) / 2.0)
            r = patch.r * 0.65
            return patch.center[0] + r * math.cos(ang), patch.center[1] + r * math.sin(ang)
        return 0.0, 0.0

    def _on_hover(event):
        if event.inaxes not in axes:
            if annot.get_visible():
                annot.set_visible(False)
                canvas.draw_idle()
            return

        for target_ax in axes:
            for patch in target_ax.patches:
                if not isinstance(patch, (Rectangle, Wedge)):
                    continue
                contains, _ = patch.contains(event)
                if contains:
                    texto = getattr(patch, "_tooltip_text", "")
                    if not texto:
                        continue
                    x, y = _get_patch_anchor(patch)
                    annot.xy = (x, y)
                    annot.set_text(texto)
                    annot.set_visible(True)
                    canvas.draw_idle()
                    return

        if annot.get_visible():
            annot.set_visible(False)
            canvas.draw_idle()

    return canvas.mpl_connect("motion_notify_event", _on_hover)
