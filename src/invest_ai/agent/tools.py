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
    Considera isenção de R$ 20k apenas para ações, alíquota de 20% para FIIs,
    15% sem isenção para BDRs e ETFs, e compensação de prejuízos acumulados por classe.
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

    # Obtém o saldo de prejuízo acumulado da mesma classe de ativo
    tipo_norm = "ação" if tipo_ativo in ("ação", "acao") else tipo_ativo
    prejuizo_acumulado = 0.0
    calc = ctx.deps.engine.calculate()
    for rep in calc.get("tax_reports", []):
        rep_tipo = "ação" if rep.tipo_ativo in ("ação", "acao") else rep.tipo_ativo
        if rep_tipo == tipo_norm:
            prejuizo_acumulado = rep.prejuizo_restante_acumulado

    isento = False
    aliquota = 0.0
    imposto_devido = 0.0
    prejuizo_compensado = 0.0
    justificativa = ""

    if "fii" in tipo_ativo:
        aliquota = 0.20
        if lucro_prejuizo > 0:
            prejuizo_compensado = min(lucro_prejuizo, prejuizo_acumulado)
            base_calculo = lucro_prejuizo - prejuizo_compensado
            imposto_devido = round(base_calculo * aliquota, 2)
            justificativa = (
                f"Para Fundos Imobiliários (FIIs), não há faixa de isenção de R$ 20.000. "
                f"A alíquota é de 20% sobre a base tributável (R$ {base_calculo:.2f})."
            )
            if prejuizo_compensado > 0:
                justificativa += f" Prejuízo acumulado compensado: R$ {prejuizo_compensado:.2f}."
        else:
            justificativa = (
                f"Venda de FII com prejuízo de R$ {abs(lucro_prejuizo):.2f}. "
                f"Sem imposto devido. O prejuízo poderá ser compensado em lucros futuros de FII."
            )
    elif tipo_norm in ("bdr", "etf"):
        aliquota = 0.15
        nome_classe = "BDRs" if tipo_norm == "bdr" else "ETFs"
        if lucro_prejuizo > 0:
            prejuizo_compensado = min(lucro_prejuizo, prejuizo_acumulado)
            base_calculo = lucro_prejuizo - prejuizo_compensado
            imposto_devido = round(base_calculo * aliquota, 2)
            justificativa = (
                f"Para {nome_classe}, não há faixa de isenção de R$ 20.000. "
                f"A alíquota é de 15% sobre a base tributável (R$ {base_calculo:.2f})."
            )
            if prejuizo_compensado > 0:
                justificativa += f" Prejuízo acumulado compensado: R$ {prejuizo_compensado:.2f}."
        else:
            justificativa = (
                f"Venda de {nome_classe} com prejuízo de R$ {abs(lucro_prejuizo):.2f}. "
                f"Sem imposto devido. O prejuízo poderá ser compensado em lucros futuros de {nome_classe}."
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
                prejuizo_compensado = min(lucro_prejuizo, prejuizo_acumulado)
                base_calculo = lucro_prejuizo - prejuizo_compensado
                imposto_devido = round(base_calculo * aliquota, 2)
                justificativa = (
                    f"Volume de vendas no mês superior a R$ 20.000,00 (R$ {valor_venda_total:.2f}). "
                    f"Aplica-se alíquota de 15% sobre a base tributável (R$ {base_calculo:.2f})."
                )
                if prejuizo_compensado > 0:
                    justificativa += f" Prejuízo acumulado compensado: R$ {prejuizo_compensado:.2f}."
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
        "prejuizo_compensado": round(prejuizo_compensado, 2),
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
        elif tipo in ("ação", "acao"):
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} de {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        elif tipo == "etf":
            return (
                f"{qtd_str} {_descricao_unidade_ativo(tipo, qtd_atu)} do ETF {ticker}, "
                f"adquiridas ao preço médio de {pm_str}, custo total de {custo_str}."
            )
        elif tipo == "bdr":
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


def gerar_guia_irpf(ctx: RunContext[InvestContext], ano: Optional[int] = None) -> str:
    """
    Gera o Guia completo para a Declaração Anual de Imposto de Renda (IRPF) referente ao ano-calendário informado.
    Se o ano não for informado (ou inválido), utiliza automaticamente o ano-calendário anterior ao atual.
    Calcula posições em 31/12 do ano anterior e do ano-base para a ficha Bens e Direitos (com textos de Discriminação prontos),
    agrupa proventos isentos recebidos no ano e resume a aba Renda Variável mês a mês com prejuízos a compensar.
    """
    if ano is None or ano < 1900 or ano > 9999:
        ano = datetime.now().year - 1

    if not ctx.deps._carteira_carregada:
        ctx.deps.carregar_dados()

    snapshot = ctx.deps.engine.gerar_snapshot_anual_irpf(ano)
    ano_ant = snapshot["ano_anterior"]
    bens = snapshot["bens_e_direitos"]
    rv = snapshot["renda_variavel"]

    linhas: List[str] = [
        f"GUIA DE DECLARAÇÃO ANUAL DE IRPF — ANO-CALENDÁRIO {ano}",
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
    for tx in ctx.deps.engine.transactions:
        if tx.ticker:
            mapa_tipos[tx.ticker.strip().upper()] = (tx.tipo_ativo or "").strip().lower()

    try:
        all_payments, _ = ctx.deps.obter_proventos_historicos()
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
            linhas.append(f"• Dividendos de Ações (Código 09 - Lucros e dividendos recebidos) — Total: {_formatar_moeda(total_acoes)}")
            for tkr, val in sorted(dividendos_acoes.items(), key=lambda x: x[1], reverse=True):
                linhas.append(f"  - {tkr}: {_formatar_moeda(val)}")

        if rendimentos_fiis:
            total_fiis = sum(rendimentos_fiis.values())
            linhas.append(f"• Rendimentos de FIIs (Código 26 - Outros / Rendimentos de FIIs) — Total: {_formatar_moeda(total_fiis)}")
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
