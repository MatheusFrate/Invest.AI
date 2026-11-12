"""
Ferramentas (Tools) do Agente PydanticAI para o Invest.AI.
Conecta o agente aos serviços de cotação da B3 e ao motor de cálculo tributário e de carteira.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pydantic_ai import RunContext

from invest_ai.agent.deps import InvestContext
from invest_ai.services import quotes_service
from invest_ai.services.dividends_service import parse_date


def _formatar_moeda(val: float) -> str:
    """Formata valor em padrão monetário brasileiro R$ XX,XX."""
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def obter_cotacao_b3(ticker: str) -> Dict:
    """
    Consulta a cotação em tempo real e a variação do dia de um ativo na B3 (ações, FIIs, ETFs, BDRs).
    Use esta ferramenta para verificar o preço atual de mercado de um ticker.
    """
    clean_ticker = ticker.strip().upper()
    simbolo, preco, var_dia = quotes_service.get_single_quote(clean_ticker)

    if preco is None:
        return {
            "sucesso": False,
            "ticker": clean_ticker,
            "mensagem": f"Não foi possível obter a cotação de '{clean_ticker}'. Verifique se o ticker é válido na B3."
        }

    return {
        "sucesso": True,
        "ticker": clean_ticker,
        "preco_atual": round(preco, 2),
        "variacao_dia_pct": round(var_dia, 2) if var_dia is not None else 0.0,
        "mensagem": f"Cotação de {clean_ticker}: R$ {preco:.2f} ({var_dia:+.2f}% hoje)"
    }


def consultar_posicao_carteira(ctx: RunContext[InvestContext], ticker: str) -> Dict:
    """
    Consulta se o usuário possui determinado ativo em carteira, a quantidade e o preço médio pago.
    """
    clean_ticker = ticker.strip().upper()
    posicao = ctx.deps.obter_posicao_ticker(clean_ticker)

    if not posicao or posicao.get("quantidade", 0) <= 0:
        return {
            "possui": False,
            "ticker": clean_ticker,
            "mensagem": f"Você não possui posição ativa em {clean_ticker} na sua carteira."
        }

    return {
        "possui": True,
        "ticker": clean_ticker,
        "tipo_ativo": posicao.get("tipo_ativo"),
        "quantidade": posicao.get("quantidade"),
        "preco_medio": round(posicao.get("preco_medio", 0.0), 2),
        "total_investido": round(posicao.get("total_investido", 0.0), 2)
    }


def listar_resumo_carteira(ctx: RunContext[InvestContext]) -> List[Dict]:
    """
    Retorna a lista de todos os ativos que o usuário possui atualmente em carteira.
    """
    posicoes = ctx.deps.obter_posicoes_carteira()
    if not posicoes:
        return []

    resumo = []
    for tkr, dados in posicoes.items():
        resumo.append({
            "ticker": tkr,
            "tipo_ativo": dados.get("tipo_ativo"),
            "quantidade": dados.get("quantidade"),
            "preco_medio": round(dados.get("preco_medio", 0.0), 2),
            "total_investido": round(dados.get("total_investido", 0.0), 2)
        })
    return resumo


def simular_impacto_darf(
    ctx: RunContext[InvestContext],
    ticker: str,
    quantidade: float,
    preco_venda: float
) -> Dict:
    """
    Simula o resultado financeiro e o imposto de renda (DARF) devido caso o usuário venda
    determinada quantidade de um ativo por um preço específico.
    Considera as regras de isenção de R$ 20k para ações e alíquota de 20% para FIIs.
    """
    clean_ticker = ticker.strip().upper()
    posicao = ctx.deps.obter_posicao_ticker(clean_ticker)

    if not posicao or posicao.get("quantidade", 0) <= 0:
        return {
            "sucesso": False,
            "mensagem": f"Simulação não pode ser concluída: Você não possui {clean_ticker} em carteira para vender."
        }

    qtd_atual = posicao.get("quantidade", 0.0)
    pm = posicao.get("preco_medio", 0.0)
    tipo_ativo = str(posicao.get("tipo_ativo", "ação")).strip().lower()

    if quantidade > qtd_atual:
        return {
            "sucesso": False,
            "mensagem": f"Você deseja simular a venda de {quantidade} de {clean_ticker}, mas possui apenas {qtd_atual} em carteira."
        }

    valor_venda_total = quantidade * preco_venda
    custo_aquisicao = quantidade * pm
    lucro_prejuizo = valor_venda_total - custo_aquisicao

    isento = False
    aliquota = 0.0
    imposto_devido = 0.0
    justificativa = ""

    if "fii" in tipo_ativo:
        aliquota = 0.20
        if lucro_prejuizo > 0:
            imposto_devido = round(lucro_prejuizo * aliquota, 2)
            justificativa = (
                f"Para Fundos Imobiliários (FIIs), não há faixa de isenção de R$ 20.000. "
                f"A alíquota é de 20% sobre o lucro líquido apurado (R$ {lucro_prejuizo:.2f})."
            )
        else:
            justificativa = (
                f"Venda de FII com prejuízo de R$ {abs(lucro_prejuizo):.2f}. "
                f"Sem imposto devido. O prejuízo poderá ser compensado em lucros futuros de FII."
            )
    else:
        if valor_venda_total <= 20000.0:
            isento = True
            aliquota = 0.0
            imposto_devido = 0.0
            if lucro_prejuizo > 0:
                justificativa = (
                    f"Operação com Ações no mercado à vista com volume total de venda (R$ {valor_venda_total:.2f}) "
                    f"inferior a R$ 20.000,00 no mês. Ganho de capital totalmente isento de Imposto de Renda."
                )
            else:
                justificativa = (
                    f"Venda com prejuízo de R$ {abs(lucro_prejuizo):.2f}. Isento de IR."
                )
        else:
            isento = False
            aliquota = 0.15
            if lucro_prejuizo > 0:
                imposto_devido = round(lucro_prejuizo * aliquota, 2)
                justificativa = (
                    f"Volume de vendas no mês superior a R$ 20.000,00 (R$ {valor_venda_total:.2f}). "
                    f"Aplica-se alíquota de 15% sobre o lucro (R$ {lucro_prejuizo:.2f})."
                )
            else:
                justificativa = (
                    f"Venda com prejuízo de R$ {abs(lucro_prejuizo):.2f}. Sem imposto devido."
                )

    return {
        "sucesso": True,
        "ticker": clean_ticker,
        "tipo_ativo": tipo_ativo,
        "quantidade_simulada": quantidade,
        "preco_venda_unitario": round(preco_venda, 2),
        "valor_total_venda": round(valor_venda_total, 2),
        "preco_medio_aquisicao": round(pm, 2),
        "custo_total_aquisicao": round(custo_aquisicao, 2),
        "lucro_prejuizo_total": round(lucro_prejuizo, 2),
        "aliquota_ir_pct": round(aliquota * 100, 1),
        "imposto_devido": imposto_devido,
        "isento": isento,
        "justificativa": justificativa
    }


def consultar_proventos_periodo(
    ctx: RunContext[InvestContext],
    mes_ano: Optional[str] = None,
    ultimos_n_meses: Optional[int] = None
) -> str:
    """
    Consulta o histórico de dividendos e JCP recebidos na carteira.
    Pode consultar um mês específico (ex: mes_ano='10/2026') ou o acumulado dos últimos N meses (ex: ultimos_n_meses=3 ou 6).
    Retorna o total recebido em R$, a média mensal e a lista discriminada por ativo.
    """
    all_payments, monthly_stats = ctx.deps.obter_proventos_historicos()

    if not all_payments and not monthly_stats:
        return "Nenhum provento registrado ou recebido na sua carteira até o momento."

    # Consulta de um mês específico
    if mes_ano:
        mes_ano_norm = mes_ano.strip().replace("-", "/")
        parts = mes_ano_norm.split("/")
        if len(parts) == 2:
            m = parts[0].zfill(2)
            y = parts[1]
            if len(y) == 2:
                y = f"20{y}"
            mes_ano_norm = f"{m}/{y}"

        pagamentos_mes = [p for p in all_payments if p.get("mes_ano") == mes_ano_norm]
        if not pagamentos_mes:
            return f"Nenhum provento foi registrado no mês {mes_ano_norm} para os ativos da sua carteira."

        total_mes = sum(p["total"] for p in pagamentos_mes)
        ativos_totais: Dict[str, float] = {}
        for p in pagamentos_mes:
            tkr = p["ticker"]
            ativos_totais[tkr] = ativos_totais.get(tkr, 0.0) + p["total"]

        detalhes = " | ".join(
            f"{tkr}: {_formatar_moeda(val)}"
            for tkr, val in sorted(ativos_totais.items(), key=lambda x: x[1], reverse=True)
        )

        return (
            f"Proventos recebidos em {mes_ano_norm}:\n"
            f"• Total recebido: {_formatar_moeda(total_mes)}\n"
            f"• Média mensal: {_formatar_moeda(total_mes)}\n"
            f"• Ativos pagadores: {detalhes}"
        )

    # Consulta acumulada dos últimos N meses (padrão: últimos 12 meses ou todos disponíveis)
    n = ultimos_n_meses if (ultimos_n_meses and ultimos_n_meses > 0) else 12
    meses_ordenados = sorted(
        monthly_stats.items(),
        key=lambda x: x[1].get("timestamp", 0),
        reverse=True
    )

    if not meses_ordenados:
        return "Nenhum provento registrado na carteira para o período solicitado."

    meses_selecionados = meses_ordenados[:n]
    chaves_meses = {m[0] for m in meses_selecionados}
    pagamentos_periodo = [p for p in all_payments if p.get("mes_ano") in chaves_meses]

    total_periodo = sum(p["total"] for p in pagamentos_periodo)
    qtd_meses = len(meses_selecionados)
    media_mensal = total_periodo / qtd_meses if qtd_meses > 0 else 0.0

    ativos_totais = {}
    for p in pagamentos_periodo:
        tkr = p["ticker"]
        ativos_totais[tkr] = ativos_totais.get(tkr, 0.0) + p["total"]

    detalhes = " | ".join(
        f"{tkr}: {_formatar_moeda(val)}"
        for tkr, val in sorted(ativos_totais.items(), key=lambda x: x[1], reverse=True)
    )

    rotulo = f"últimos {qtd_meses} meses" if qtd_meses > 1 else "último mês"
    return (
        f"Proventos recebidos nos {rotulo}:\n"
        f"• Total recebido: {_formatar_moeda(total_periodo)}\n"
        f"• Média mensal: {_formatar_moeda(media_mensal)}\n"
        f"• Detalhamento por ativo: {detalhes}"
    )


def calcular_yield_on_cost(ctx: RunContext[InvestContext], ticker: str) -> str:
    """
    Calcula o Yield on Cost (YoC) real de uma posição em custódia na carteira.
    Fórmula: (Total de proventos pagos por cota nos últimos 12 meses / Preço Médio de aquisição) * 100.
    Explica a taxa de retorno em dividendos sobre o capital efetivamente investido.
    """
    clean_ticker = ticker.strip().upper()
    posicao = ctx.deps.obter_posicao_ticker(clean_ticker)

    if not posicao or posicao.get("quantidade", 0) <= 0:
        return (
            f"Você não possui posição ativa em {clean_ticker} na sua carteira. "
            f"O cálculo do Yield on Cost exige que você possua cotas em custódia com preço médio registrado."
        )

    pm = posicao.get("preco_medio", 0.0)
    qtd = posicao.get("quantidade", 0.0)

    if pm <= 0:
        return f"O preço médio de {clean_ticker} é zero ou não foi computado, impedindo o cálculo de Yield on Cost."

    div_events = ctx.deps.obter_dividendos_ticker(clean_ticker)
    if not div_events:
        return (
            f"Posição em {clean_ticker}: {qtd:g} cotas com Preço Médio de {_formatar_moeda(pm)}.\n"
            f"Não foram localizados eventos de proventos nos últimos 12 meses para {clean_ticker}.\n"
            f"Yield on Cost (YoC): 0,00%."
        )

    # Identificar eventos dos últimos 12 meses
    datas = []
    for d in div_events:
        dt = d.get("dt") or parse_date(d.get("data", ""))
        if dt:
            datas.append(dt)

    if not datas:
        return (
            f"Posição em {clean_ticker}: {qtd:g} cotas com Preço Médio de {_formatar_moeda(pm)}.\n"
            f"Não foi possível converter as datas dos proventos de {clean_ticker}."
        )

    now = datetime.now()
    tem_recente = any((now - dt).days <= 365 for dt in datas if dt <= now)
    ref_date = now if tem_recente else max(datas)
    limite_12m = ref_date - timedelta(days=365)

    eventos_12m = []
    for d in div_events:
        dt = d.get("dt") or parse_date(d.get("data", ""))
        if dt and limite_12m <= dt <= ref_date:
            eventos_12m.append(d)

    total_pago_por_cota = sum(d.get("amount", 0.0) for d in eventos_12m)
    yoc = (total_pago_por_cota / pm) * 100

    renda_anual_posicao = total_pago_por_cota * qtd

    return (
        f"Yield on Cost (YoC) de {clean_ticker}: {yoc:.2f}%\n"
        f"• Preço médio pago: {_formatar_moeda(pm)}\n"
        f"• Proventos pagos por cota (últimos 12 meses): {_formatar_moeda(total_pago_por_cota)}\n"
        f"• Posição em custódia: {qtd:g} cotas\n"
        f"• Renda passiva anual estimada com a posição: {_formatar_moeda(renda_anual_posicao)}\n"
        f"Explicação: Para cada {_formatar_moeda(pm)} investidos em média em {clean_ticker}, "
        f"você recebeu {_formatar_moeda(total_pago_por_cota)} em proventos nos últimos 12 meses, "
        f"o que representa um retorno real em dividendos de {yoc:.2f}% a.a. sobre o seu capital de aquisição."
    )


def resumir_maiores_pagadores(ctx: RunContext[InvestContext], top_n: int = 5) -> str:
    """
    Retorna o ranking dos ativos da carteira que mais geraram renda passiva histórica (dividendos e JCP) em R$.
    """
    all_payments, _ = ctx.deps.obter_proventos_historicos()

    if not all_payments:
        return "Nenhum provento foi registrado na sua carteira até o momento."

    totais: Dict[str, float] = {}
    for p in all_payments:
        tkr = p["ticker"]
        totais[tkr] = totais.get(tkr, 0.0) + p["total"]

    if not totais:
        return "Nenhum provento registrado para calcular o ranking de maiores pagadores."

    ranking = sorted(totais.items(), key=lambda x: x[1], reverse=True)[:top_n]
    total_acumulado = sum(totais.values())

    linhas = []
    for i, (tkr, val) in enumerate(ranking):
        pct = (val / total_acumulado * 100) if total_acumulado > 0 else 0.0
        linhas.append(f"{i + 1}. {tkr}: {_formatar_moeda(val)} ({pct:.1f}% do total)")

    return (
        f"Ranking dos maiores pagadores de renda passiva da sua carteira (Top {len(ranking)}):\n"
        + "\n".join(linhas)
        + f"\n• Total histórico acumulado de proventos: {_formatar_moeda(total_acumulado)}"
    )
