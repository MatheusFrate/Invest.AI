"""
Testes unitários do motor de cálculo de preço médio e imposto de renda (DARF).
"""

from invest_ai.core.engine import InvestmentEngine, Transaction


def test_calculo_preco_medio_e_carteira():
    engine = InvestmentEngine()
    engine.set_transactions([
        Transaction(data="2026-01-10", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=50, valor_unitario=30.0, valor_total=1500.0),
        Transaction(data="2026-02-10", ticker="PETR4", tipo_ativo="ação", operacao="compra", quantidade=50, valor_unitario=40.0, valor_total=2000.0),
    ])
    res = engine.calculate()
    wallet = res["wallet"]

    assert "PETR4" in wallet
    assert wallet["PETR4"]["quantidade"] == 100.0
    assert wallet["PETR4"]["preco_medio"] == 35.0
    assert wallet["PETR4"]["total_investido"] == 3500.0


def test_apuracao_darf_fii_e_compensacao_prejuizo():
    engine = InvestmentEngine()
    engine.set_transactions([
        # Compra 100 cotas a R$ 10,00 (R$ 1000)
        Transaction(data="2026-01-05", ticker="MXRF11", tipo_ativo="fii", operacao="compra", quantidade=100, valor_unitario=10.0, valor_total=1000.0),
        # Vende 50 cotas em Jan/2026 com prejuízo a R$ 8,00 (-R$ 100)
        Transaction(data="2026-01-20", ticker="MXRF11", tipo_ativo="fii", operacao="venda", quantidade=50, valor_unitario=8.0, valor_total=400.0),
        # Vende 50 cotas em Fev/2026 com lucro a R$ 14,00 (+R$ 200) -> compensa R$ 100 de prejuízo -> base R$ 100 -> 20% = R$ 20
        Transaction(data="2026-02-20", ticker="MXRF11", tipo_ativo="fii", operacao="venda", quantidade=50, valor_unitario=14.0, valor_total=700.0),
    ])
    res = engine.calculate()
    reports = res["tax_reports"]

    assert len(reports) == 2
    # Mês 1: prejuízo de R$ 100
    assert reports[0].mes_ano == "01/2026"
    assert reports[0].imposto_devido == 0.0
    assert reports[0].prejuizo_restante_acumulado == 100.0

    # Mês 2: lucro de R$ 200 abatendo R$ 100 de prejuízo -> imposto R$ 20
    assert reports[1].mes_ano == "02/2026"
    assert reports[1].prejuizo_anterior_compensado == 100.0
    assert reports[1].base_calculo == 100.0
    assert reports[1].imposto_devido == 20.0


def test_apuracao_darf_bdr_sem_isencao_20k():
    engine = InvestmentEngine()
    engine.set_transactions([
        # Compra 100 BDRs a R$ 50,00 (R$ 5.000)
        Transaction(data="2026-01-05", ticker="AAPL34", tipo_ativo="bdr", operacao="compra", quantidade=100, valor_unitario=50.0, valor_total=5000.0),
        # Vende 50 BDRs a R$ 70,00 (R$ 3.500 <= 20k, lucro R$ 1.000) -> 15% = R$ 150 (sem isenção de 20k)
        Transaction(data="2026-02-10", ticker="AAPL34", tipo_ativo="bdr", operacao="venda", quantidade=50, valor_unitario=70.0, valor_total=3500.0),
    ])
    res = engine.calculate()
    reports = res["tax_reports"]

    assert len(reports) == 1
    rep = reports[0]
    assert rep.tipo_ativo == "bdr"
    assert rep.isento is False
    assert rep.aliquota == 0.15
    assert rep.vendas_total == 3500.0
    assert rep.resultado_liquido == 1000.0
    assert rep.base_calculo == 1000.0
    assert rep.imposto_devido == 150.0


def test_apuracao_darf_bdr_prejuizo_e_compensacao():
    engine = InvestmentEngine()
    engine.set_transactions([
        # Compra 100 BDRs a R$ 50,00
        Transaction(data="2026-01-05", ticker="AAPL34", tipo_ativo="bdr", operacao="compra", quantidade=100, valor_unitario=50.0, valor_total=5000.0),
        # Vende 40 BDRs em Jan/2026 a R$ 40,00 -> prejuízo de R$ 400
        Transaction(data="2026-01-20", ticker="AAPL34", tipo_ativo="bdr", operacao="venda", quantidade=40, valor_unitario=40.0, valor_total=1600.0),
        # Vende 60 BDRs em Fev/2026 a R$ 60,00 -> lucro de R$ 600, compensa R$ 400 -> base R$ 200 -> 15% = R$ 30
        Transaction(data="2026-02-20", ticker="AAPL34", tipo_ativo="bdr", operacao="venda", quantidade=60, valor_unitario=60.0, valor_total=3600.0),
    ])
    res = engine.calculate()
    reports = res["tax_reports"]

    assert len(reports) == 2
    assert reports[0].mes_ano == "01/2026"
    assert reports[0].tipo_ativo == "bdr"
    assert reports[0].imposto_devido == 0.0
    assert reports[0].prejuizo_restante_acumulado == 400.0

    assert reports[1].mes_ano == "02/2026"
    assert reports[1].tipo_ativo == "bdr"
    assert reports[1].prejuizo_anterior_compensado == 400.0
    assert reports[1].base_calculo == 200.0
    assert reports[1].imposto_devido == 30.0
    assert reports[1].prejuizo_restante_acumulado == 0.0

    # Verifica reflexo no snapshot anual de IRPF
    snap = engine.gerar_snapshot_anual_irpf(2026)
    meses = {m["mes_ano"]: m for m in snap["renda_variavel"]["meses"]}
    assert meses["01/2026"]["vendas_bdrs"] == 1600.0
    assert meses["01/2026"]["resultado_bdrs"] == -400.0
    assert meses["01/2026"]["darf_bdrs"] == 0.0
    assert meses["02/2026"]["vendas_bdrs"] == 3600.0
    assert meses["02/2026"]["resultado_bdrs"] == 600.0
    assert meses["02/2026"]["darf_bdrs"] == 30.0
    assert meses["02/2026"]["darf_total"] == 30.0
    assert snap["renda_variavel"]["prejuizo_acumulado_final"]["bdr"] == 0.0
