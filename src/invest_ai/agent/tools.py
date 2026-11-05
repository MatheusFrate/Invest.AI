"""
Ferramentas (Tools) do Agente PydanticAI para o Invest.AI.
Conecta o agente aos serviços de cotação da B3 e ao motor de cálculo tributário e de carteira.
"""

from typing import Dict, List
from pydantic_ai import RunContext

from invest_ai.agent.deps import InvestContext
from invest_ai.services import quotes_service


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
