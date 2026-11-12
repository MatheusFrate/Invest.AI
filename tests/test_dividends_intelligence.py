"""
Testes automatizados do Módulo de Inteligência de Proventos e Renda Passiva (Marco 1).
Cobre as novas ferramentas de PydanticAI e a integração com o assistant_agent usando TestModel.
"""

from datetime import datetime
from unittest.mock import MagicMock
import pytest
from pydantic_ai.models.test import TestModel

from invest_ai.agent.deps import InvestContext
from invest_ai.core.engine import Transaction
from invest_ai.agent.tools import (
    consultar_proventos_periodo,
    calcular_yield_on_cost,
    resumir_maiores_pagadores,
)
from invest_ai.agent.agent import criar_agente_assistente


@pytest.fixture
def dividends_context():
    """Contexto com transações e dividendos pré-configurados de forma determinística."""
    ctx = InvestContext(excel_path="mock_dividends.xlsx")

    # Transações de compra
    txs = [
        Transaction(
            data="2026-01-10",
            ticker="PETR4",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=100.0,
            valor_unitario=30.0,
            valor_total=3000.0,
        ),
        Transaction(
            data="2026-01-15",
            ticker="MXRF11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=100.0,
            valor_unitario=10.0,
            valor_total=1000.0,
        ),
        Transaction(
            data="2026-02-01",
            ticker="VALE3",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=200.0,
            valor_unitario=60.0,
            valor_total=12000.0,
        ),
    ]
    ctx.engine.set_transactions(txs)
    ctx._carteira_carregada = True

    # Eventos de proventos mockados
    mock_divs = {
        "MXRF11": [
            {
                "ticker": "MXRF11",
                "data": "15/02/2026",
                "mes_ano": "02/2026",
                "dt": datetime(2026, 2, 15),
                "timestamp": int(datetime(2026, 2, 15).timestamp()),
                "amount": 0.10,
            },
            {
                "ticker": "MXRF11",
                "data": "15/03/2026",
                "mes_ano": "03/2026",
                "dt": datetime(2026, 3, 15),
                "timestamp": int(datetime(2026, 3, 15).timestamp()),
                "amount": 0.10,
            },
            {
                "ticker": "MXRF11",
                "data": "15/04/2026",
                "mes_ano": "04/2026",
                "dt": datetime(2026, 4, 15),
                "timestamp": int(datetime(2026, 4, 15).timestamp()),
                "amount": 0.12,
            },
        ],
        "PETR4": [
            {
                "ticker": "PETR4",
                "data": "20/03/2026",
                "mes_ano": "03/2026",
                "dt": datetime(2026, 3, 20),
                "timestamp": int(datetime(2026, 3, 20).timestamp()),
                "amount": 1.50,
            }
        ],
        "VALE3": [
            {
                "ticker": "VALE3",
                "data": "10/04/2026",
                "mes_ano": "04/2026",
                "dt": datetime(2026, 4, 10),
                "timestamp": int(datetime(2026, 4, 10).timestamp()),
                "amount": 2.00,
            }
        ],
    }
    ctx.definir_dados_proventos(mock_divs)
    return ctx


@pytest.fixture
def mock_dividends_run_ctx(dividends_context):
    """Mock de RunContext para ferramentas PydanticAI."""
    run_ctx = MagicMock()
    run_ctx.deps = dividends_context
    return run_ctx


def test_invest_context_cache_and_mock(dividends_context):
    """Testa cache de cálculo de proventos e invalidação no InvestContext."""
    payments1, stats1 = dividends_context.obter_proventos_historicos()
    assert len(payments1) == 5  # 3 MXRF11 + 1 PETR4 + 1 VALE3
    assert "03/2026" in stats1
    assert "04/2026" in stats1

    # Segunda chamada deve vir do cache
    payments2, stats2 = dividends_context.obter_proventos_historicos()
    assert payments1 is payments2
    assert stats1 is stats2

    # Obter eventos de ticker específico
    divs_mxrf = dividends_context.obter_dividendos_ticker("MXRF11")
    assert len(divs_mxrf) == 3


def test_consultar_proventos_mes_especifico(mock_dividends_run_ctx):
    """Testa consulta de proventos de um mês específico (03/2026)."""
    # 03/2026: MXRF11 (100 * 0.10 = R$ 10,00) + PETR4 (100 * 1.50 = R$ 150,00) = R$ 160,00
    res = consultar_proventos_periodo(mock_dividends_run_ctx, mes_ano="03/2026")
    assert "Proventos recebidos em 03/2026" in res
    assert "R$ 160,00" in res
    assert "PETR4: R$ 150,00" in res
    assert "MXRF11: R$ 10,00" in res


def test_consultar_proventos_mes_sem_pagamentos(mock_dividends_run_ctx):
    """Testa consulta para um mês sem proventos registrados."""
    res = consultar_proventos_periodo(mock_dividends_run_ctx, mes_ano="01/2026")
    assert "Nenhum provento foi registrado no mês 01/2026" in res


def test_consultar_proventos_ultimos_n_meses(mock_dividends_run_ctx):
    """Testa consulta acumulada dos últimos N meses."""
    # 04/2026: VALE3 (R$ 400) + MXRF11 (R$ 12) = R$ 412
    # 03/2026: PETR4 (R$ 150) + MXRF11 (R$ 10) = R$ 160
    # Últimos 2 meses: 412 + 160 = R$ 572, média = R$ 286
    res = consultar_proventos_periodo(mock_dividends_run_ctx, ultimos_n_meses=2)
    assert "últimos 2 meses" in res
    assert "R$ 572,00" in res
    assert "R$ 286,00" in res


def test_calcular_yield_on_cost_sucesso(mock_dividends_run_ctx):
    """Testa cálculo do Yield on Cost com base no Preço Médio e histórico."""
    # MXRF11: PM = R$ 10,00 | Proventos 12m = 0.10 + 0.10 + 0.12 = 0.32 | YoC = (0.32 / 10.0) * 100 = 3.20%
    res_mxrf = calcular_yield_on_cost(mock_dividends_run_ctx, ticker="MXRF11")
    assert "Yield on Cost (YoC) de MXRF11: 3.20%" in res_mxrf
    assert "R$ 10,00" in res_mxrf
    assert "R$ 0,32" in res_mxrf

    # PETR4: PM = R$ 30,00 | Proventos 12m = 1.50 | YoC = (1.50 / 30.0) * 100 = 5.00%
    res_petr = calcular_yield_on_cost(mock_dividends_run_ctx, ticker="PETR4")
    assert "Yield on Cost (YoC) de PETR4: 5.00%" in res_petr
    assert "R$ 30,00" in res_petr
    assert "R$ 1,50" in res_petr


def test_calcular_yield_on_cost_ativo_inexistente(mock_dividends_run_ctx):
    """Testa cálculo de YoC para ativo que o investidor não possui em carteira."""
    res = calcular_yield_on_cost(mock_dividends_run_ctx, ticker="ITUB4")
    assert "Você não possui posição ativa em ITUB4" in res


def test_calcular_yield_on_cost_sem_proventos(mock_dividends_run_ctx):
    """Testa cálculo de YoC para ativo sem proventos no período."""
    # Adicionamos uma posição sem eventos de dividendo
    mock_dividends_run_ctx.deps.engine.transactions.append(
        Transaction(
            data="2026-01-01",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=10.0,
            valor_unitario=100.0,
            valor_total=1000.0,
        )
    )
    mock_dividends_run_ctx.deps._cached_payments = None
    mock_dividends_run_ctx.deps._cached_monthly_stats = None

    res = calcular_yield_on_cost(mock_dividends_run_ctx, ticker="XPML11")
    assert "0,00%" in res or "Não foram localizados eventos" in res


def test_resumir_maiores_pagadores(mock_dividends_run_ctx):
    """Testa ranking dos maiores pagadores de renda passiva."""
    # VALE3: 200 * 2.00 = R$ 400,00
    # PETR4: 100 * 1.50 = R$ 150,00
    # MXRF11: 100 * (0.10 + 0.10 + 0.12) = R$ 32,00
    # Total = R$ 582,00
    res = resumir_maiores_pagadores(mock_dividends_run_ctx, top_n=3)
    assert "Ranking dos maiores pagadores" in res
    assert "1. VALE3: R$ 400,00" in res
    assert "2. PETR4: R$ 150,00" in res
    assert "3. MXRF11: R$ 32,00" in res
    assert "Total histórico acumulado de proventos: R$ 582,00" in res


def test_resumir_maiores_pagadores_carteira_vazia():
    """Testa ranking para contexto sem proventos registrados."""
    ctx_vazio = InvestContext(excel_path="empty.xlsx")
    ctx_vazio.definir_dados_proventos({})
    run_ctx = MagicMock()
    run_ctx.deps = ctx_vazio

    res = resumir_maiores_pagadores(run_ctx)
    assert "Nenhum provento foi registrado" in res


def test_assistant_agent_perguntas_proventos_com_test_model(dividends_context):
    """Testa chamadas ao assistant_agent com perguntas sobre dividendos usando TestModel."""
    resposta_esperada = "Nos últimos 2 meses você recebeu R$ 572,00 de proventos, média de R$ 286,00 por mês."
    test_model = TestModel(custom_output_text=resposta_esperada)

    agent = criar_agente_assistente(model=test_model)

    res1 = agent.run_sync(
        "Quanto recebi de dividendos nos últimos meses?",
        deps=dividends_context,
    )
    assert res1.output == resposta_esperada

    res2 = agent.run_sync(
        "Qual o Yield on Cost de MXRF11 na minha carteira?",
        deps=dividends_context,
    )
    assert res2.output == resposta_esperada

    res3 = agent.run_sync(
        "Quais são os meus maiores pagadores de dividendos?",
        deps=dividends_context,
    )
    assert res3.output == resposta_esperada


def test_consultar_proventos_formato_mes_abreviado(mock_dividends_run_ctx):
    """Testa se o parser normaliza datas como '3/26' ou '03-2026'."""
    res = consultar_proventos_periodo(mock_dividends_run_ctx, mes_ano="3/26")
    assert "Proventos recebidos em 03/2026" in res
    assert "R$ 160,00" in res


def test_consultar_proventos_carteira_vazia():
    """Testa retorno seguro para contexto sem nenhuma transação ou provento."""
    ctx_vazio = InvestContext(excel_path="empty.xlsx")
    ctx_vazio.definir_dados_proventos({})
    run_ctx = MagicMock()
    run_ctx.deps = ctx_vazio

    res = consultar_proventos_periodo(run_ctx)
    assert "Nenhum provento" in res


def test_calcular_yield_on_cost_preco_medio_zero(mock_dividends_run_ctx):
    """Testa tratamento para preço médio zero ou inválido."""
    mock_dividends_run_ctx.deps.engine.transactions.append(
        Transaction(
            data="2026-01-01",
            ticker="BONUS3",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=10.0,
            valor_unitario=0.0,
            valor_total=0.0,
        )
    )
    mock_dividends_run_ctx.deps._cached_payments = None
    mock_dividends_run_ctx.deps._cached_monthly_stats = None

    res = calcular_yield_on_cost(mock_dividends_run_ctx, ticker="BONUS3")
    assert "zero ou não foi computado" in res
