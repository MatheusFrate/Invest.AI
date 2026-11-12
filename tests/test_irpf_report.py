"""
Testes automatizados do Módulo de Declaração Anual de IRPF (Marco 2).
Cobre o motor determinístico de corte anual no InvestmentEngine,
a ferramenta gerar_guia_irpf e a integração com assistant_agent via TestModel.
"""

from datetime import datetime
from unittest.mock import MagicMock
import pytest
from pydantic_ai.models.test import TestModel

from invest_ai.agent.deps import InvestContext
from invest_ai.agent.tools import gerar_guia_irpf
from invest_ai.agent.agent import criar_agente_assistente
from invest_ai.core.engine import InvestmentEngine, Transaction


def test_snapshot_anual_irpf_posicoes_e_zeramento():
    """
    Valida posições em 31/12/2024 e 31/12/2025 com:
    - Compra no ano anterior (2024) + novo aporte em 2025 (PETR4)
    - Venda parcial em 2025 (MXRF11)
    - Venda total em 2025 (VALE3: saldo anterior preservado e saldo atual R$ 0,00)
    - Compra e venda total dentro de 2025 (BOVA11: não deve aparecer em Bens e Direitos)
    - Transações fora de ordem e mistura de formatos DD/MM/YYYY e YYYY-MM-DD
    """
    engine = InvestmentEngine()
    engine.set_transactions([
        # Fora de ordem propositalmente
        Transaction(data="15/06/2025", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=100, valor_unitario=40.0),
        Transaction(data="2024-03-10", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=100, valor_unitario=30.0),
        Transaction(data="10/05/2024", ticker="MXRF11", tipo_ativo="fii", operacao="compra", quantidade=200, valor_unitario=10.0),
        Transaction(data="2025-08-20", ticker="MXRF11", tipo_ativo="fii", operacao="venda", quantidade=50, valor_unitario=11.0),
        Transaction(data="2024-11-05", ticker="VALE3", tipo_ativo="ação", operacao="compra", quantidade=50, valor_unitario=60.0),
        Transaction(data="20/04/2025", ticker="VALE3", tipo_ativo="ação", operacao="venda", quantidade=50, valor_unitario=70.0),
        Transaction(data="2025-02-01", ticker="BOVA11", tipo_ativo="etf", operacao="compra", quantidade=10, valor_unitario=120.0),
        Transaction(data="2025-09-01", ticker="BOVA11", tipo_ativo="etf", operacao="venda", quantidade=10, valor_unitario=130.0),
        Transaction(data="2025-03-15", ticker="IVVB11", tipo_ativo="etf", operacao="compra", quantidade=10, valor_unitario=300.0),
        Transaction(data="2025-04-10", ticker="AAPL34", tipo_ativo="bdr", operacao="compra", quantidade=20, valor_unitario=50.0),
        # Transação de 2026 deve ser ignorada no snapshot de 2025
        Transaction(data="2026-01-10", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=500, valor_unitario=50.0),
    ])

    snap = engine.gerar_snapshot_anual_irpf(2025)
    assert snap["ano"] == 2025
    assert snap["ano_anterior"] == 2024

    bens = {item["ticker"]: item for item in snap["bens_e_direitos"]}

    # BOVA11 foi comprado e zerado em 2025 -> não entra em Bens e Direitos
    assert "BOVA11" not in bens

    # PETR4: 100 @ 30 em 2024; +100 @ 40 em 2025 -> 200 @ 35 (R$ 7.000,00)
    petr = bens["PETR4"]
    assert petr["grupo_rfb"] == "03 - Participações Societárias"
    assert petr["codigo_rfb"] == "01 - Ações (inclusive as listadas em bolsa)"
    assert petr["quantidade_ano_anterior"] == 100.0
    assert petr["custo_total_ano_anterior"] == 3000.0
    assert petr["quantidade_ano_atual"] == 200.0
    assert petr["preco_medio_ano_atual"] == 35.0
    assert petr["custo_total_ano_atual"] == 7000.0

    # MXRF11: 200 @ 10 em 2024; venda de 50 em 2025 -> 150 @ 10 (R$ 1.500,00)
    mxrf = bens["MXRF11"]
    assert mxrf["grupo_rfb"] == "07 - Fundos"
    assert mxrf["codigo_rfb"] == "03 - Fundos de Investimento Imobiliário (FII)"
    assert mxrf["quantidade_ano_anterior"] == 200.0
    assert mxrf["custo_total_ano_anterior"] == 2000.0
    assert mxrf["quantidade_ano_atual"] == 150.0
    assert mxrf["custo_total_ano_atual"] == 1500.0

    # VALE3: 50 @ 60 em 2024 (R$ 3.000,00); vendida totalmente em 2025 -> saldo 0,00
    vale = bens["VALE3"]
    assert vale["quantidade_ano_anterior"] == 50.0
    assert vale["custo_total_ano_anterior"] == 3000.0
    assert vale["quantidade_ano_atual"] == 0.0
    assert vale["custo_total_ano_atual"] == 0.0

    # IVVB11 (ETF) e AAPL34 (BDR): mapeamento oficial RFB
    assert bens["IVVB11"]["grupo_rfb"] == "07 - Fundos"
    assert bens["IVVB11"]["codigo_rfb"] == "09 - Demais Fundos de Índice de Mercado (ETF)"
    assert bens["AAPL34"]["grupo_rfb"] == "04 - Aplicações e Investimentos"
    assert bens["AAPL34"]["codigo_rfb"] == "04 - Ativos negociados em bolsa no exterior / BDRs"


def test_snapshot_anual_irpf_renda_variavel_e_prejuizo_transportado():
    """
    Valida apuração mensal de Renda Variável do ano-calendário e compensação/transporte
    de prejuízos acumulados entre anos.
    """
    engine = InvestmentEngine()
    engine.set_transactions([
        # Prejuízo em FII em 2024: compra 100 @ 100, vende 100 @ 90 -> prejuízo R$ 1.000
        Transaction(data="2024-01-10", ticker="HGLG11", tipo_ativo="fii", operacao="compra", quantidade=100, valor_unitario=100.0),
        Transaction(data="2024-06-15", ticker="HGLG11", tipo_ativo="fii", operacao="venda", quantidade=100, valor_unitario=90.0),
        # Compra FII em 2025 e vende com lucro de R$ 400 em 03/2025 -> compensa R$ 400, sobra R$ 600 de prejuízo
        Transaction(data="2025-01-10", ticker="HGLG11", tipo_ativo="fii", operacao="compra", quantidade=100, valor_unitario=100.0),
        Transaction(data="2025-03-20", ticker="HGLG11", tipo_ativo="fii", operacao="venda", quantidade=100, valor_unitario=104.0),
        # Ações em 2025:
        # 05/2025: venda <= 20k com lucro (isento)
        Transaction(data="2025-02-01", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=100, valor_unitario=30.0),
        Transaction(data="2025-05-10", ticker="PETR4", tipo_ativo="ação", operacao="venda", quantidade=100, valor_unitario=35.0),
        # 07/2025: venda > 20k com prejuízo de R$ 500 -> acumula R$ 500 para 2026
        Transaction(data="2025-06-01", ticker="VALE3", tipo_ativo="ação", operacao="compra", quantidade=500, valor_unitario=50.0),
        Transaction(data="2025-07-15", ticker="VALE3", tipo_ativo="ação", operacao="venda", quantidade=500, valor_unitario=49.0),
    ])

    snap = engine.gerar_snapshot_anual_irpf(2025)
    rv = snap["renda_variavel"]
    meses = {m["mes_ano"]: m for m in rv["meses"]}

    assert set(meses.keys()) == {"03/2025", "05/2025", "07/2025"}

    # 03/2025: FII teve lucro de 400, mas compensou com prejuízo de 1000 de 2024 -> DARF = 0
    assert meses["03/2025"]["resultado_fiis"] == 400.0
    assert meses["03/2025"]["darf_fiis"] == 0.0

    # 05/2025: Ações venda 3.500 (<= 20k) com lucro 500 -> isento
    assert meses["05/2025"]["vendas_acoes"] == 3500.0
    assert meses["05/2025"]["resultado_acoes"] == 500.0
    assert meses["05/2025"]["lucro_isento_acoes"] == 500.0
    assert meses["05/2025"]["darf_acoes"] == 0.0

    # 07/2025: Ações venda 24.500 (> 20k) com prejuízo -500
    assert meses["07/2025"]["vendas_acoes"] == 24500.0
    assert meses["07/2025"]["resultado_acoes"] == -500.0
    assert meses["07/2025"]["lucro_isento_acoes"] == 0.0
    assert meses["07/2025"]["darf_acoes"] == 0.0

    # Prejuízo acumulado transportado em 31/12/2025
    assert rv["prejuizo_acumulado_final"]["fii"] == 600.0
    assert rv["prejuizo_acumulado_final"]["acao"] == 500.0


def test_tool_gerar_guia_irpf_com_proventos_mockados():
    """Valida a ferramenta gerar_guia_irpf com dados e proventos mockados (offline)."""
    ctx = InvestContext(excel_path="nao_existe.xlsx")
    ctx.engine.set_transactions([
        Transaction(data="2024-06-10", ticker="MXRF11", tipo_ativo="fii", operacao="compra", quantidade=100, valor_unitario=10.0),
        Transaction(data="2025-02-10", ticker="MXRF11", tipo_ativo="fii", operacao="compra", quantidade=60, valor_unitario=9.22),
        Transaction(data="2025-03-05", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=50, valor_unitario=35.0),
        Transaction(data="2025-08-15", ticker="PETR4", tipo_ativo="ação", operacao="venda", quantidade=50, valor_unitario=38.0),
    ])
    ctx._carteira_carregada = True
    ctx.definir_dados_proventos({
        "MXRF11": [
            {"data": "15/05/2025", "mes_ano": "05/2025", "amount": 0.10, "timestamp": int(datetime(2025, 5, 15).timestamp()), "dt": datetime(2025, 5, 15)},
            {"data": "15/01/2026", "mes_ano": "01/2026", "amount": 0.10, "timestamp": int(datetime(2026, 1, 15).timestamp()), "dt": datetime(2026, 1, 15)},
        ],
        "PETR4": [
            {"data": "20/06/2025", "mes_ano": "06/2025", "amount": 1.00, "timestamp": int(datetime(2025, 6, 20).timestamp()), "dt": datetime(2025, 6, 20)},
        ],
    })

    run_ctx = MagicMock()
    run_ctx.deps = ctx

    relatorio = gerar_guia_irpf(run_ctx, 2025)

    assert "ANO-CALENDÁRIO 2025" in relatorio
    assert "1. FICHA BENS E DIREITOS" in relatorio
    assert "07 - Fundos" in relatorio
    assert "03 - Fundos de Investimento Imobiliário (FII)" in relatorio
    assert "160 cotas do Fundo Imobiliário MXRF11" in relatorio
    assert "2. FICHA RENDIMENTOS ISENTOS E NÃO TRIBUTÁVEIS (2025)" in relatorio
    assert "Dividendos de Ações" in relatorio
    assert "PETR4: R$ 50,00" in relatorio
    assert "Rendimentos de FIIs" in relatorio
    assert "MXRF11: R$ 16,00" in relatorio
    assert "3. ABA RENDA VARIÁVEL (2025)" in relatorio
    assert "08/2025:" in relatorio
    assert "ISENTO" in relatorio
    # Garante que provento de 2026 não vazou para 2025 (160 * 0.10 = 16,00 e não 32,00)
    assert "MXRF11: R$ 32,00" not in relatorio


def test_tool_gerar_guia_irpf_offline_sem_proventos():
    """Garante que gerar_guia_irpf não quebra se a consulta de proventos falhar offline."""
    ctx = InvestContext(excel_path="nao_existe.xlsx")
    ctx.engine.set_transactions([
        Transaction(data="2025-01-10", ticker="VALE3", tipo_ativo="ação", operacao="compra", quantidade=10, valor_unitario=60.0),
    ])
    ctx._carteira_carregada = True
    ctx.obter_proventos_historicos = MagicMock(side_effect=RuntimeError("Sem internet"))

    run_ctx = MagicMock()
    run_ctx.deps = ctx

    relatorio = gerar_guia_irpf(run_ctx, 2025)
    assert "VALE3" in relatorio
    assert "Nenhum provento registrado ou disponível para 2025" in relatorio


def test_assistant_agent_irpf_com_test_model():
    """Valida que o assistant_agent possui e aciona a ferramenta gerar_guia_irpf via TestModel."""
    ctx = InvestContext(excel_path="nao_existe.xlsx")
    ctx.engine.set_transactions([
        Transaction(data="2025-01-10", ticker="MXRF11", tipo_ativo="fii", operacao="compra", quantidade=100, valor_unitario=10.0),
    ])
    ctx._carteira_carregada = True
    ctx.definir_dados_proventos({})

    test_model = TestModel()
    agent = criar_agente_assistente(model=test_model)

    res = agent.run_sync(
        "Monte meu guia de declaração de IRPF de 2025",
        deps=ctx,
    )

    assert res.output is not None
    assert "gerar_guia_irpf" in test_model.last_model_request_parameters.function_tools[0].name or any(
        t.name == "gerar_guia_irpf"
        for t in test_model.last_model_request_parameters.function_tools
    )
