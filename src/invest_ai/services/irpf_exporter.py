"""
Gerador e exportador determinístico do Guia Anual de Declaração de IRPF em texto (.txt).
Centraliza a formatação das fichas Bens e Direitos, Rendimentos Isentos e Renda Variável.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from invest_ai.agent.deps import InvestContext


def _formatar_moeda(val: float) -> str:
    """Formata um valor numérico para o padrão monetário brasileiro (R$ X.XXX,XX)."""
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _descricao_unidade_ativo(tipo_ativo: str, qtd: float) -> str:
    """Retorna a descrição da unidade do ativo (ações, cotas, BDRs)."""
    tipo = (tipo_ativo or "").strip().lower()
    if tipo in ("ação", "acao"):
        return "ação" if qtd == 1 else "ações"
    if tipo == "bdr":
        return "BDR" if qtd == 1 else "BDRs"
    return "cota" if qtd == 1 else "cotas"


def _texto_discriminacao(item: Dict, ano: int) -> str:
    """Gera texto pronto de Discriminação para copiar e colar no programa da Receita Federal."""
    ticker = item["ticker"]
    tipo = (item.get("tipo_ativo") or "").strip().lower()
    qtd_atu = item["quantidade_ano_atual"]
    pm_atu = item["preco_medio_ano_atual"]
    custo_atu = item["custo_total_ano_atual"]
    qtd_ant = item["quantidade_ano_anterior"]
    custo_ant = item["custo_total_ano_anterior"]

    if qtd_atu > 0:
        qtd_str = f"{qtd_atu:g}"
        pm_str = _formatar_moeda(pm_atu)
        custo_str = _formatar_moeda(custo_atu)
        if tipo == "fii":
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} do Fundo Imobiliário {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        if tipo in ("ação", "acao"):
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} de {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        if tipo == "etf":
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} do ETF {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        if tipo == "bdr":
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} de {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        return (
            f"{qtd_str} unidades de {ticker}, adquiridas ao preço médio de {pm_str}, "
            f"custo total de {custo_str}."
        )

    return (
        f"Posição encerrada em {ano}. Em 31/12/{ano - 1} possuía {qtd_ant:g} "
        f"{_descricao_unidade_ativo(tipo, qtd_ant)} de {ticker}, com custo total de {_formatar_moeda(custo_ant)}."
    )


def gerar_conteudo_guia_irpf_texto(context: InvestContext, ano: Optional[int] = None) -> str:
    """
    Gera o documento completo do Guia Anual de IRPF em texto plano UTF-8.

    Inclui cabeçalho com Ano-Calendário e data de geração, além das seções:
    1. Ficha Bens e Direitos (Grupo, Código RFB, Situação 31/12/{ano-1}, 31/12/{ano} e Discriminação)
    2. Ficha Rendimentos Isentos e Não Tributáveis (Dividendos vs. Rendimentos de FIIs)
    3. Aba Renda Variável (Resumo mensal, meses isentos, DARFs e prejuízo acumulado)
    """
    if ano is None or ano < 1900 or ano > 9999:
        ano = datetime.now().year - 1

    if not context._carteira_carregada:
        context.carregar_dados()

    snapshot = context.engine.gerar_snapshot_anual_irpf(ano)
    ano_ant = snapshot["ano_anterior"]
    bens = snapshot["bens_e_direitos"]
    rv = snapshot["renda_variavel"]

    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas: List[str] = [
        f"GUIA DE DECLARAÇÃO ANUAL DE IRPF — ANO-CALENDÁRIO {ano}",
        f"Gerado em: {data_geracao}",
        "=" * 72,
        "",
        "1. FICHA BENS E DIREITOS",
    ]

    if not bens:
        linhas.append(f"• Nenhum ativo com saldo em custódia em 31/12/{ano_ant} ou 31/12/{ano}.")
    else:
        for item in bens:
            discriminacao = _texto_discriminacao(item, ano)
            linhas.extend([
                f"• Ativo: {item['ticker']} ({item['tipo_ativo'].upper()})",
                f"  Grupo: {item['grupo_rfb']}",
                f"  Código: {item['codigo_rfb']}",
                f"  Situação em 31/12/{ano_ant}: {_formatar_moeda(item['custo_total_ano_anterior'])}",
                f"  Situação em 31/12/{ano}: {_formatar_moeda(item['custo_total_ano_atual'])}",
                f"  Discriminação: {discriminacao}",
            ])

    # 2. Ficha Rendimentos Isentos e Não Tributáveis
    linhas.extend(["", f"2. FICHA RENDIMENTOS ISENTOS E NÃO TRIBUTÁVEIS ({ano})"])

    mapa_tipos: Dict[str, str] = {}
    for tx in context.engine.transactions:
        if tx.ticker:
            mapa_tipos[tx.ticker.strip().upper()] = (tx.tipo_ativo or "").strip().lower()

    try:
        all_payments, _ = context.obter_proventos_historicos()
    except Exception:
        all_payments = []

    sufixo_ano = f"/{ano}"
    pagamentos_ano = [p for p in all_payments if str(p.get("mes_ano", "")).endswith(sufixo_ano)]

    if not pagamentos_ano:
        linhas.append(
            f"• Nenhum provento registrado ou disponível para {ano} "
            f"(ou consulta de proventos indisponível no momento)."
        )
    else:
        dividendos_acoes: Dict[str, float] = {}
        rendimentos_fiis: Dict[str, float] = {}
        outros_proventos: Dict[str, float] = {}

        for p in pagamentos_ano:
            tkr = str(p.get("ticker", "")).strip().upper()
            val = float(p.get("total", 0.0))
            tipo = mapa_tipos.get(tkr, "ação")
            if tipo == "fii":
                rendimentos_fiis[tkr] = rendimentos_fiis.get(tkr, 0.0) + val
            elif tipo in ("ação", "acao"):
                dividendos_acoes[tkr] = dividendos_acoes.get(tkr, 0.0) + val
            else:
                outros_proventos[tkr] = outros_proventos.get(tkr, 0.0) + val

        if dividendos_acoes:
            total_acoes = sum(dividendos_acoes.values())
            linhas.append(
                f"• Dividendos de Ações (Código 09 - Lucros e dividendos recebidos) — Total: {_formatar_moeda(total_acoes)}"
            )
            for tkr, val in sorted(dividendos_acoes.items(), key=lambda x: x[1], reverse=True):
                linhas.append(f"  - {tkr}: {_formatar_moeda(val)}")

        if rendimentos_fiis:
            total_fiis = sum(rendimentos_fiis.values())
            linhas.append(
                f"• Rendimentos de FIIs (Código 26 - Outros / Rendimentos de FIIs) — Total: {_formatar_moeda(total_fiis)}"
            )
            for tkr, val in sorted(rendimentos_fiis.items(), key=lambda x: x[1], reverse=True):
                linhas.append(f"  - {tkr}: {_formatar_moeda(val)}")

        if outros_proventos:
            total_outros = sum(outros_proventos.values())
            linhas.append(f"• Outros Proventos Isentos — Total: {_formatar_moeda(total_outros)}")
            for tkr, val in sorted(outros_proventos.items(), key=lambda x: x[1], reverse=True):
                linhas.append(f"  - {tkr}: {_formatar_moeda(val)}")

    # 3. Aba Renda Variável
    linhas.extend(["", f"3. ABA RENDA VARIÁVEL ({ano})"])
    meses = rv.get("meses", [])
    if not meses:
        linhas.append(f"• Nenhuma operação de venda registrada no ano-calendário {ano}.")
    else:
        for m in meses:
            partes = [f"• {m['mes_ano']}:"]
            if m["vendas_acoes"] > 0 or m["resultado_acoes"] != 0:
                status_isento = " (ISENTO - vendas <= R$ 20 mil)" if m["lucro_isento_acoes"] > 0 else ""
                partes.append(
                    f"Ações Vendas {_formatar_moeda(m['vendas_acoes'])} | "
                    f"Resultado {_formatar_moeda(m['resultado_acoes'])}{status_isento} | "
                    f"DARF {_formatar_moeda(m['darf_acoes'])}"
                )
            if m["vendas_fiis"] > 0 or m["resultado_fiis"] != 0:
                partes.append(
                    f"FIIs Vendas {_formatar_moeda(m['vendas_fiis'])} | "
                    f"Resultado {_formatar_moeda(m['resultado_fiis'])} | "
                    f"DARF {_formatar_moeda(m['darf_fiis'])}"
                )
            if m.get("vendas_etfs", 0) > 0 or m.get("resultado_etfs", 0) != 0:
                partes.append(
                    f"ETFs Vendas {_formatar_moeda(m['vendas_etfs'])} | "
                    f"Resultado {_formatar_moeda(m['resultado_etfs'])} | "
                    f"DARF {_formatar_moeda(m['darf_etfs'])}"
                )
            if m.get("vendas_bdrs", 0) > 0 or m.get("resultado_bdrs", 0) != 0:
                partes.append(
                    f"BDRs Vendas {_formatar_moeda(m['vendas_bdrs'])} | "
                    f"Resultado {_formatar_moeda(m['resultado_bdrs'])} | "
                    f"DARF {_formatar_moeda(m['darf_bdrs'])}"
                )
            linhas.append(" ".join(partes))

    prej = rv.get("prejuizo_acumulado_final", {})
    linhas.extend([
        f"• Saldo de Prejuízo Acumulado a Compensar em 31/12/{ano} (transportar para {ano + 1}):",
        f"  - Operações Comuns (Ações): {_formatar_moeda(prej.get('acao', 0.0))}",
        f"  - Fundos Imobiliários (FIIs): {_formatar_moeda(prej.get('fii', 0.0))}",
    ])
    if prej.get("etf", 0.0) > 0:
        linhas.append(f"  - ETFs: {_formatar_moeda(prej.get('etf', 0.0))}")
    if prej.get("bdr", 0.0) > 0:
        linhas.append(f"  - BDRs: {_formatar_moeda(prej.get('bdr', 0.0))}")

    return "\n".join(linhas)


def exportar_guia_irpf_txt(context: InvestContext, ano: int, caminho_arquivo: str) -> str:
    """
    Gera o Guia Anual de IRPF e grava o conteúdo em arquivo texto UTF-8.
    Retorna o caminho do arquivo salvo.
    """
    conteudo = gerar_conteudo_guia_irpf_texto(context, ano)
    destino = Path(caminho_arquivo)
    if destino.parent:
        destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    return str(destino)
