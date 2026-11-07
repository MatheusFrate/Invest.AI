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
