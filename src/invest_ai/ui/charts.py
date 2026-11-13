"""
Módulo de geração de gráficos financeiros estilizados (Dark / Light Theme) com Matplotlib.
Fornece funções puras que retornam objetos matplotlib.figure.Figure para integração
no CustomTkinter (FigureCanvasTkAgg) e validação headless em testes unitários.
"""

import math
from typing import Dict, List, Optional, Tuple
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter


FONT_FAMILY = ["Segoe UI", "DejaVu Sans", "sans-serif"]

# Tokens padrão (Dark Theme alinhado ao UI_COLORS de base_window.py)
BG_COLOR = "#1e293b"
SURFACE_ALT_COLOR = "#243044"
TEXT_COLOR = "#f8fafc"
MUTED_TEXT_COLOR = "#94a3b8"
SUBTLE_TEXT_COLOR = "#64748b"
GRID_COLOR = "#334155"
ACCENT_PRIMARY = "#6366f1"
ACCENT_BLUE = "#3b82f6"
ACCENT_GREEN = "#10b981"
ACCENT_RED = "#ef4444"
ACCENT_AMBER = "#f59e0b"
PALETTE = [
    "#6366f1",
    "#10b981",
    "#3b82f6",
    "#f59e0b",
    "#ec4899",
    "#06b6d4",
    "#8b5cf6",
    "#14b8a6",
]

CHART_THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#1e293b",
        "surface_alt": "#243044",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "subtle": "#64748b",
        "grid": "#334155",
        "zero_line": "#475569",
        "tooltip_bg": "#0f172a",
        "tooltip_border": "#334155",
        "tooltip_text": "#f8fafc",
        "donut_edge": "#1e293b",
        "donut_pct": "#ffffff",
        "primary": "#6366f1",
        "blue": "#3b82f6",
        "green": "#10b981",
        "red": "#ef4444",
        "amber": "#f59e0b",
    },
    "light": {
        "bg": "#ffffff",
        "surface_alt": "#f1f5f9",
        "text": "#0f172a",
        "muted": "#475569",
        "subtle": "#64748b",
        "grid": "#e2e8f0",
        "zero_line": "#cbd5e1",
        "tooltip_bg": "#0f172a",
        "tooltip_border": "#334155",
        "tooltip_text": "#f8fafc",
        "donut_edge": "#ffffff",
        "donut_pct": "#ffffff",
        "primary": "#6366f1",
        "blue": "#3b82f6",
        "green": "#10b981",
        "red": "#ef4444",
        "amber": "#f59e0b",
    },
}


def get_chart_theme(theme: str = "dark") -> Dict[str, str]:
    """Retorna o dicionário de tokens de cores para o tema solicitado ('dark' ou 'light')."""
    return CHART_THEMES.get((theme or "dark").strip().lower(), CHART_THEMES["dark"])


def _format_brl(valor: float, signed: bool = False) -> str:
    """Formata um valor numérico no padrão monetário brasileiro (R$ 1.234,56)."""
    formatted = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if signed:
        sinal = "+" if valor >= 0 else "-"
        return f"{sinal}R$ {formatted}"
    if valor < 0:
        return f"-R$ {formatted}"
    return f"R$ {formatted}"


def _criar_figura_base(
    figsize: Tuple[float, float], theme: str = "dark"
) -> Tuple[Figure, any, Dict[str, str]]:
    """Cria uma Figure e um Axes com estilização moderna consistente com o tema."""
    t = get_chart_theme(theme)
    fig = Figure(figsize=figsize, dpi=100, facecolor=t["bg"])
    fig._chart_theme_tokens = t
    ax = fig.add_subplot(111)
    ax.set_facecolor(t["bg"])
    ax.tick_params(colors=t["muted"], labelsize=8, length=0, pad=5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(t["grid"])
        ax.spines[spine].set_linewidth(0.8)
    return fig, ax, t


def _aplicar_titulo(ax, titulo: str, t: Dict[str, str]) -> None:
    """Aplica título padronizado ao eixo."""
    ax.set_title(
        titulo,
        color=t["text"],
        fontsize=10.5,
        fontweight="bold",
        pad=10,
        fontfamily=FONT_FAMILY,
    )


def _configurar_grid(
    ax,
    axis: str,
    t: Dict[str, str],
    zero_line: bool = False,
    hide_spines: Tuple[str, ...] = (),
) -> None:
    """Configura gridlines sutis, linha de referência zero e visibilidade de spines."""
    ax.set_axisbelow(True)
    if axis == "x":
        ax.xaxis.grid(True, linestyle=(0, (3, 3)), alpha=0.65, linewidth=0.7, color=t["grid"])
        if zero_line:
            ax.axvline(0, color=t["zero_line"], linewidth=1.0, zorder=2)
    elif axis == "y":
        ax.yaxis.grid(True, linestyle=(0, (3, 3)), alpha=0.65, linewidth=0.7, color=t["grid"])
        if zero_line:
            ax.axhline(0, color=t["zero_line"], linewidth=1.0, zorder=2)
    for spine in hide_spines:
        ax.spines[spine].set_visible(False)


def _renderizar_estado_vazio(
    ax,
    titulo: str,
    mensagem: str,
    t: Optional[Dict[str, str]] = None,
    subtitulo: str = "Os dados aparecerão aqui assim que houver movimentações.",
) -> None:
    """Exibe cartão centralizado elegante quando não há dados para plotagem."""
    tokens = t or CHART_THEMES["dark"]
    ax.axis("off")
    _aplicar_titulo(ax, titulo, tokens)
    ax.text(
        0.5,
        0.56,
        mensagem,
        ha="center",
        va="center",
        color=tokens["text"],
        fontsize=9.5,
        fontweight="bold",
        fontfamily=FONT_FAMILY,
        transform=ax.transAxes,
        bbox=dict(
            boxstyle="round,pad=0.65",
            facecolor=tokens["surface_alt"],
            edgecolor=tokens["grid"],
            linewidth=1.0,
        ),
    )
    ax.text(
        0.5,
        0.34,
        subtitulo,
        ha="center",
        va="center",
        color=tokens["muted"],
        fontsize=8,
        fontfamily=FONT_FAMILY,
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
    theme: str = "dark",
) -> Figure:
    """Gera gráfico de rosca (donut) com a alocação da carteira por classe de ativo."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)
    ativos = _calcular_valores_ativos(wallet, live_quotes)

    por_classe: Dict[str, float] = {}
    for _, classe, valor in ativos:
        por_classe[classe] = por_classe.get(classe, 0.0) + valor

    total = sum(por_classe.values())
    if total <= 0:
        _renderizar_estado_vazio(ax, "Alocação por Classe", "Sem ativos em custódia", t=t)
        fig.tight_layout(pad=1.0)
        return fig

    ordenado = sorted(por_classe.items(), key=lambda x: x[1], reverse=True)
    labels = [c for c, _ in ordenado]
    valores = [v for _, v in ordenado]
    cores = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]

    wedges, _, autotexts = ax.pie(
        valores,
        colors=cores,
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 4.0 else "",
        pctdistance=0.79,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor=t["donut_edge"], linewidth=2.2),
        textprops=dict(color=t["donut_pct"], fontsize=7.5, fontweight="bold", fontfamily=FONT_FAMILY),
    )
    for txt in autotexts:
        txt.set_color(t["donut_pct"])

    # Rótulo central dentro da rosca com o patrimônio total
    ax.text(
        0,
        0.09,
        "Total",
        ha="center",
        va="center",
        color=t["muted"],
        fontsize=7.5,
        fontfamily=FONT_FAMILY,
    )
    ax.text(
        0,
        -0.11,
        _format_brl(total),
        ha="center",
        va="center",
        color=t["text"],
        fontsize=8.5,
        fontweight="bold",
        fontfamily=FONT_FAMILY,
    )

    for wedge, lbl, val in zip(wedges, labels, valores):
        pct = (val / total) * 100.0 if total > 0 else 0.0
        wedge._tooltip_text = f"{lbl}: {_format_brl(val)} ({pct:.1f}%)"

    legend_labels = [f"{lbl}: {_format_brl(val)}" for lbl, val in zip(labels, valores)]
    ax.legend(
        wedges,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(0.98, 0.5),
        frameon=False,
        labelcolor=t["text"],
        fontsize=8,
        handlelength=1.1,
        handleheight=0.9,
        labelspacing=0.6,
    )
    _aplicar_titulo(ax, "Alocação por Classe", t)
    fig.tight_layout(pad=1.0)
    return fig


def create_allocation_by_ticker_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (5.0, 2.5),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico de barras horizontais com o percentual dos principais ativos."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)
    ativos = _calcular_valores_ativos(wallet, live_quotes)

    total = sum(v for _, _, v in ativos)
    if total <= 0:
        _renderizar_estado_vazio(ax, "Distribuição por Ativo (%)", "Sem ativos em custódia", t=t)
        fig.tight_layout(pad=1.0)
        return fig

    ordenado = sorted(ativos, key=lambda x: x[2], reverse=True)
    principais = [(tk, v) for tk, _, v in ordenado[:top_n]]
    if len(ordenado) > top_n:
        restante = sum(v for _, _, v in ordenado[top_n:])
        if restante > 0:
            principais.append(("OUTROS", restante))

    # Inverte para que o maior fique no topo do barh
    principais_rev = list(reversed(principais))
    tickers = [tk for tk, _ in principais_rev]
    percentuais = [(v / total) * 100.0 for _, v in principais_rev]
    cores = [
        t["subtle"]
        if tk == "OUTROS"
        else PALETTE[(len(principais) - 1 - idx) % len(PALETTE)]
        for idx, tk in enumerate(tickers)
    ]

    bars = ax.barh(tickers, percentuais, color=cores, height=0.58, alpha=0.95)
    max_pct = max(percentuais) if percentuais else 10.0
    ax.set_xlim(0, max_pct * 1.24)
    _configurar_grid(ax, "x", t, hide_spines=("left", "bottom"))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax.tick_params(axis="y", colors=t["text"], labelsize=8.5)

    for (ticker, val), bar, pct in zip(principais_rev, bars, percentuais):
        bar._tooltip_text = f"{ticker}: {pct:.1f}% ({_format_brl(val)})"
        ax.text(
            bar.get_width() + max_pct * 0.025,
            bar.get_y() + bar.get_height() / 2.0,
            f"{pct:.1f}%",
            va="center",
            ha="left",
            color=t["text"],
            fontsize=8,
            fontweight="bold",
            fontfamily=FONT_FAMILY,
        )

    _aplicar_titulo(ax, "Distribuição por Ativo (%)", t)
    fig.tight_layout(pad=1.0)
    return fig


def create_monthly_dividends_figure(
    mensal_stats: Dict[str, Dict],
    max_months: int = 12,
    figsize: Tuple[float, float] = (8.5, 2.2),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico de barras verticais com a evolução mensal dos proventos em R$."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)

    if not mensal_stats:
        _renderizar_estado_vazio(
            ax,
            "Evolução Mensal de Proventos (R$)",
            "Sem proventos registrados",
            t=t,
            subtitulo="Os recebimentos mensais serão exibidos automaticamente após consulta.",
        )
        fig.tight_layout(pad=1.0)
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
        _renderizar_estado_vazio(
            ax,
            "Evolução Mensal de Proventos (R$)",
            "Sem proventos registrados",
            t=t,
            subtitulo="Os recebimentos mensais serão exibidos automaticamente após consulta.",
        )
        fig.tight_layout(pad=1.0)
        return fig

    bars = ax.bar(meses, totais, color=t["green"], width=0.52, alpha=0.92)
    max_val = max(totais) if totais else 1.0
    ax.set_ylim(0, max_val * 1.28)
    _configurar_grid(ax, "y", t, hide_spines=("left",))
    ax.tick_params(axis="x", colors=t["text"], labelsize=7.5 if len(meses) > 8 else 8)

    for mes, bar, val in zip(meses, bars, totais):
        bar._tooltip_text = f"{mes}: {_format_brl(val)}"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max_val * 0.035,
            f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            ha="center",
            va="bottom",
            color=t["text"],
            fontsize=7.5,
            fontweight="bold",
            fontfamily=FONT_FAMILY,
        )

    _aplicar_titulo(ax, "Evolução Mensal de Proventos (R$)", t)
    fig.tight_layout(pad=1.0)
    return fig


def _render_diverging_barh(
    ax,
    tickers: List[str],
    values: List[float],
    tooltips: List[str],
    titulo: str,
    t: Dict[str, str],
) -> None:
    """Renderiza gráfico de barras horizontais divergentes com rótulos e grid padronizados."""
    cores = [t["green"] if v >= 0 else t["red"] for v in values]
    bars = ax.barh(tickers, values, color=cores, height=0.58, alpha=0.94)

    max_abs = max((abs(v) for v in values), default=5.0)
    pad = max(max_abs * 0.30, 2.5)
    ax.set_xlim(min(min(values), 0.0) - pad, max(max(values), 0.0) + pad)
    _configurar_grid(ax, "x", t, zero_line=True, hide_spines=("left", "bottom"))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:+.0f}%"))
    ax.tick_params(axis="y", colors=t["text"], labelsize=8.5)

    offset = max(max_abs * 0.035, 0.35)
    for bar, val, tooltip_text in zip(bars, values, tooltips):
        ha = "left" if val >= 0 else "right"
        x_pos = bar.get_width() + offset if val >= 0 else bar.get_width() - offset
        ax.text(
            x_pos,
            bar.get_y() + bar.get_height() / 2.0,
            f"{val:+.1f}%",
            va="center",
            ha=ha,
            color=t["text"],
            fontsize=8,
            fontweight="bold",
            fontfamily=FONT_FAMILY,
        )
        bar._tooltip_text = tooltip_text

    _aplicar_titulo(ax, titulo, t)


def create_profitability_by_ticker_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (5.0, 2.5),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico de barras horizontais divergentes com a rentabilidade (%) por ativo."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)
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
        _renderizar_estado_vazio(ax, "Rentabilidade por Ativo (%)", "Sem ativos em custódia", t=t)
        fig.tight_layout(pad=1.0)
        return fig

    top_itens = sorted(itens, key=lambda x: abs(x[1]), reverse=True)[:top_n]
    ordenados = sorted(top_itens, key=lambda x: x[1])
    tickers = [tk for tk, _, _ in ordenados]
    rentabs = [r for _, r, _ in ordenados]
    tooltips = [f"{tk}: {r:+.2f}% ({_format_brl(l, signed=True)})" for tk, r, l in ordenados]

    _render_diverging_barh(ax, tickers, rentabs, tooltips, "Rentabilidade por Ativo (%)", t)
    fig.tight_layout(pad=1.0)
    return fig


def create_sales_darf_summary_figure(
    tax_reports: List,
    max_months: int = 8,
    figsize: Tuple[float, float] = (8.5, 1.8),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico mensal comparando Resultado Líquido (R$) e DARF Apurado (R$)."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)

    if not tax_reports:
        _renderizar_estado_vazio(
            ax,
            "Resumo Mensal: Resultado vs. DARF (R$)",
            "Sem vendas apuradas",
            t=t,
            subtitulo="Vendas realizadas aparecerão aqui com apuração de DARF.",
        )
        fig.tight_layout(pad=1.0)
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
        _renderizar_estado_vazio(
            ax,
            "Resumo Mensal: Resultado vs. DARF (R$)",
            "Sem vendas apuradas",
            t=t,
            subtitulo="Vendas realizadas aparecerão aqui com apuração de DARF.",
        )
        fig.tight_layout(pad=1.0)
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
    width = 0.35
    x_res = [x - width / 2 for x in x_idx]
    x_darf = [x + width / 2 for x in x_idx]
    cores_res = [t["green"] if v >= 0 else t["red"] for v in resultados]

    bars_res = ax.bar(
        x_res, resultados, width=width, color=cores_res, alpha=0.94, label="Resultado Líquido"
    )
    bars_darf = ax.bar(
        x_darf, darfs, width=width, color=t["amber"], alpha=0.94, label="DARF Devido"
    )

    for mes, b_res, v_res in zip(meses_ord, bars_res, resultados):
        b_res._tooltip_text = f"{mes} • Resultado: {_format_brl(v_res, signed=True)}"
    for mes, b_darf, v_darf in zip(meses_ord, bars_darf, darfs):
        b_darf._tooltip_text = f"{mes} • DARF: {_format_brl(v_darf)}"

    todos_vals = resultados + darfs + [0.0]
    min_y = min(todos_vals)
    max_y = max(todos_vals)
    span = max(max_y - min_y, 10.0)
    ax.set_ylim(min_y - span * 0.14 if min_y < 0 else 0.0, max_y + span * 0.22)

    _configurar_grid(ax, "y", t, zero_line=True, hide_spines=("left",))
    ax.set_xticks(x_idx)
    ax.set_xticklabels(meses_ord, fontsize=8, color=t["text"])
    ax.legend(
        loc="upper right",
        frameon=False,
        labelcolor=t["text"],
        fontsize=7.5,
        ncol=2,
        handlelength=1.1,
    )
    _aplicar_titulo(ax, "Resumo Mensal: Resultado vs. DARF (R$)", t)
    fig.tight_layout(pad=1.0)
    return fig


def attach_matplotlib_tooltip(canvas, figure: Figure, theme: Optional[str] = None):
    """Conecta tooltip interativo (hover) nos patches visíveis de uma Figure no canvas."""
    from matplotlib.patches import Rectangle, Wedge

    axes = [ax for ax in figure.axes if ax.axison]
    if not axes:
        return None

    t = get_chart_theme(theme) if theme else getattr(figure, "_chart_theme_tokens", CHART_THEMES["dark"])
    ax = axes[0]
    annot = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(10, 10),
        textcoords="offset points",
        bbox=dict(
            boxstyle="round,pad=0.45",
            fc=t["tooltip_bg"],
            ec=t["tooltip_border"],
            lw=1.0,
            alpha=0.96,
        ),
        color=t["tooltip_text"],
        fontsize=8,
        fontfamily=FONT_FAMILY,
        zorder=20,
    )
    annot.set_visible(False)

    def _get_patch_anchor(patch) -> Tuple[float, float]:
        if isinstance(patch, Rectangle):
            return patch.get_x() + patch.get_width() / 2.0, patch.get_y() + patch.get_height() / 2.0
        if isinstance(patch, Wedge):
            ang = math.radians((patch.theta1 + patch.theta2) / 2.0)
            r = patch.r * 0.65
            return patch.center[0] + r * math.cos(ang), patch.center[1] + r * math.sin(ang)
        return 0.0, 0.0

    def _ajustar_posicao_tooltip(target_ax, x: float, y: float) -> None:
        """Posiciona o tooltip evitando cortes nas bordas do gráfico."""
        try:
            disp_x, disp_y = target_ax.transData.transform((x, y))
            rel_x, rel_y = target_ax.transAxes.inverted().transform((disp_x, disp_y))
        except Exception:
            rel_x, rel_y = 0.5, 0.5

        dx = -10 if rel_x > 0.62 else 10
        dy = -14 if rel_y > 0.72 else 10
        annot.set_position((dx, dy))
        annot.set_ha("right" if rel_x > 0.62 else "left")
        annot.set_va("top" if rel_y > 0.72 else "bottom")

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
                    _ajustar_posicao_tooltip(target_ax, x, y)
                    annot.set_text(texto)
                    annot.set_visible(True)
                    canvas.draw_idle()
                    return

        if annot.get_visible():
            annot.set_visible(False)
            canvas.draw_idle()

    return canvas.mpl_connect("motion_notify_event", _on_hover)


def _calcular_retorno_total_ativos(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    proventos_por_ticker: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    Calcula o retorno total por ativo unificando valorização da cota e proventos recebidos.
    """
    quotes = live_quotes or {}
    proventos_map = {k.strip().upper(): float(v or 0.0) for k, v in (proventos_por_ticker or {}).items()}
    itens: List[Dict] = []

    for ticker, dados in wallet.items():
        qtd = float(dados.get("quantidade", 0.0) or 0.0)
        investido = float(dados.get("total_investido", 0.0) or 0.0)
        if qtd <= 0 or investido <= 0:
            continue

        t_upper = ticker.strip().upper()
        quote = quotes.get(ticker) or quotes.get(t_upper) or {}
        preco_vivo = quote.get("price")
        if preco_vivo is not None and float(preco_vivo) > 0:
            patrimonio = qtd * float(preco_vivo)
        else:
            patrimonio = investido

        ganho_cota = patrimonio - investido
        proventos = proventos_map.get(t_upper, 0.0)
        retorno_rs = ganho_cota + proventos
        cota_pct = (ganho_cota / investido) * 100.0
        prov_pct = (proventos / investido) * 100.0
        total_pct = (retorno_rs / investido) * 100.0

        itens.append({
            "ticker": t_upper,
            "investido": investido,
            "patrimonio": patrimonio,
            "ganho_cota": ganho_cota,
            "proventos": proventos,
            "retorno_rs": retorno_rs,
            "cota_pct": cota_pct,
            "prov_pct": prov_pct,
            "total_pct": total_pct,
        })

    return itens


def create_total_return_pct_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    proventos_por_ticker: Optional[Dict[str, float]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (4.8, 2.4),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico de barras horizontais divergentes com o Retorno Total (%) (Cota + Proventos)."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)
    itens = _calcular_retorno_total_ativos(wallet, live_quotes, proventos_por_ticker)

    if not itens:
        _renderizar_estado_vazio(ax, "Retorno Total por Ativo (%)", "Sem ativos em custódia", t=t)
        fig.tight_layout(pad=1.0)
        return fig

    top_itens = sorted(itens, key=lambda x: abs(x["total_pct"]), reverse=True)[:top_n]
    ordenados = sorted(top_itens, key=lambda x: x["total_pct"])

    tickers = [x["ticker"] for x in ordenados]
    totais_pct = [x["total_pct"] for x in ordenados]
    tooltips = [
        f"{x['ticker']}: {x['total_pct']:+.2f}% "
        f"(Cota: {x['cota_pct']:+.2f}% | Prov: +{x['prov_pct']:.2f}%)"
        for x in ordenados
    ]

    _render_diverging_barh(ax, tickers, totais_pct, tooltips, "Retorno Total por Ativo (%)", t)
    fig.tight_layout(pad=1.0)
    return fig


def create_total_return_breakdown_figure(
    wallet: Dict[str, Dict],
    live_quotes: Optional[Dict[str, Dict]] = None,
    proventos_por_ticker: Optional[Dict[str, float]] = None,
    top_n: int = 8,
    figsize: Tuple[float, float] = (4.8, 2.4),
    theme: str = "dark",
) -> Figure:
    """Gera gráfico comparando Valorização da Cota (R$) vs. Proventos Recebidos (R$) por ativo."""
    fig, ax, t = _criar_figura_base(figsize, theme=theme)
    itens = _calcular_retorno_total_ativos(wallet, live_quotes, proventos_por_ticker)

    if not itens:
        _renderizar_estado_vazio(
            ax, "Composição: Cota vs. Proventos (R$)", "Sem ativos em custódia", t=t
        )
        fig.tight_layout(pad=1.0)
        return fig

    top_itens = sorted(itens, key=lambda x: abs(x["retorno_rs"]), reverse=True)[:top_n]
    ordenados = sorted(top_itens, key=lambda x: x["retorno_rs"])

    y_idx = list(range(len(ordenados)))
    height = 0.35
    y_cota = [y - height / 2 for y in y_idx]
    y_prov = [y + height / 2 for y in y_idx]

    ganhos_cota = [x["ganho_cota"] for x in ordenados]
    proventos = [x["proventos"] for x in ordenados]
    cores_cota = [t["blue"] if v >= 0 else t["red"] for v in ganhos_cota]

    bars_cota = ax.barh(
        y_cota, ganhos_cota, height=height, color=cores_cota, alpha=0.94, label="Valorização"
    )
    bars_prov = ax.barh(
        y_prov, proventos, height=height, color=t["green"], alpha=0.94, label="Proventos"
    )

    for item, b_cota in zip(ordenados, bars_cota):
        v = item["ganho_cota"]
        b_cota._tooltip_text = (
            f"{item['ticker']} • Cota: {_format_brl(v, signed=True)} ({item['cota_pct']:+.2f}%)"
        )
    for item, b_prov in zip(ordenados, bars_prov):
        v = item["proventos"]
        b_prov._tooltip_text = (
            f"{item['ticker']} • Proventos: {_format_brl(v, signed=True)} ({item['prov_pct']:.2f}%)"
        )

    todos_vals = ganhos_cota + proventos + [0.0]
    min_x = min(todos_vals)
    max_x = max(todos_vals)
    span = max(max_x - min_x, 10.0)
    ax.set_xlim(min_x - span * 0.14 if min_x < 0 else 0.0, max_x + span * 0.14)

    _configurar_grid(ax, "x", t, zero_line=True, hide_spines=("left", "bottom"))
    ax.set_yticks(y_idx)
    ax.set_yticklabels([x["ticker"] for x in ordenados], fontsize=8.5, color=t["text"])
    ax.legend(
        loc="lower right",
        frameon=False,
        labelcolor=t["text"],
        fontsize=7.5,
        handlelength=1.1,
    )
    _aplicar_titulo(ax, "Composição: Cota vs. Proventos (R$)", t)
    fig.tight_layout(pad=1.0)
    return fig
