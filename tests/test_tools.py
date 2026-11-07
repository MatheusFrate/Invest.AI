"""
Testes das ferramentas (Tools) acopladas ao PydanticAI.
"""

from unittest.mock import patch
from invest_ai.agent.tools import (
    obter_cotacao_b3,
    consultar_posicao_carteira,
    listar_resumo_carteira,
    simular_impacto_darf
)


def test_obter_cotacao_b3():
    with patch("invest_ai.services.quotes_service.get_single_quote") as mock_quote:
        mock_quote.return_value = ("PETR4", 38.50, 1.25)
        res = obter_cotacao_b3("petr4")
        assert res["sucesso"] is True
        assert res["ticker"] == "PETR4"
        assert res["preco_atual"] == 38.50
        assert res["variacao_dia_pct"] == 1.25


def test_consultar_posicao_existente(mock_run_context):
    res = consultar_posicao_carteira(mock_run_context, "PETR4")
    assert res["possui"] is True
    assert res["ticker"] == "PETR4"
    assert res["quantidade"] == 100.0
    assert res["preco_medio"] == 30.0


def test_consultar_posicao_inexistente(mock_run_context):
    res = consultar_posicao_carteira(mock_run_context, "ITUB4")
    assert res["possui"] is False
    assert "não possui" in res["mensagem"]


def test_listar_resumo_carteira(mock_run_context):
    resumo = listar_resumo_carteira(mock_run_context)
    tickers = [item["ticker"] for item in resumo]
    assert "PETR4" in tickers
    assert "MXRF11" in tickers
    assert "VALE3" in tickers


def test_simular_darf_fii_lucro(mock_run_context):
    # 50 cotas de MXRF11 (PM R$ 10,00) vendidas a R$ 12,00 -> Lucro R$ 100 -> IR 20% = R$ 20
    res = simular_impacto_darf(mock_run_context, ticker="MXRF11", quantidade=50, preco_venda=12.0)
    assert res["sucesso"] is True
    assert res["lucro_prejuizo_total"] == 100.0
    assert res["imposto_devido"] == 20.0
    assert res["aliquota_ir_pct"] == 20.0
    assert res["isento"] is False


def test_simular_darf_acao_isenta(mock_run_context):
    # 100 ações de PETR4 (PM R$ 30,00) vendidas a R$ 35,00 -> Venda R$ 3.500 (<= 20k) -> Isenta
    res = simular_impacto_darf(mock_run_context, ticker="PETR4", quantidade=100, preco_venda=35.0)
    assert res["sucesso"] is True
    assert res["lucro_prejuizo_total"] == 500.0
    assert res["isento"] is True
    assert res["imposto_devido"] == 0.0


def test_simular_darf_acao_tributada(mock_run_context):
    # 500 ações de VALE3 (PM R$ 50,00) vendidas a R$ 60,00 -> Venda R$ 30.000 (> 20k) -> 15% sobre lucro de 5k
    res = simular_impacto_darf(mock_run_context, ticker="VALE3", quantidade=500, preco_venda=60.0)
    assert res["sucesso"] is True
    assert res["valor_total_venda"] == 30000.0
    assert res["isento"] is False
    assert res["lucro_prejuizo_total"] == 5000.0
    assert res["imposto_devido"] == 750.0
    assert res["aliquota_ir_pct"] == 15.0


def test_simular_venda_quantidade_maior_que_posse(mock_run_context):
    res = simular_impacto_darf(mock_run_context, ticker="PETR4", quantidade=200, preco_venda=35.0)
    assert res["sucesso"] is False
    assert "possui apenas 100" in res["mensagem"]
