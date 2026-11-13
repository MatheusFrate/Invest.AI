"""
Testes automatizados para Eventos Corporativos na B3:
desdobramento (split), agrupamento (inplit) e conversão/incorporação de ticker.
"""

from datetime import datetime
from pathlib import Path
import openpyxl
import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from invest_ai.core.engine import InvestmentEngine, Transaction
from invest_ai.services.dividends_service import calculate_historical_dividends
from invest_ai.services.excel_handler import (
    load_transactions_from_excel,
    save_transaction_to_excel,
)
from invest_ai.agent.schemas import (
    CorporateEventSchema,
    TipoAtivo,
    TipoEventoCorporativo,
)
from invest_ai.agent.agent import criar_agente_evento_corporativo


def test_desdobramento_preserva_custo_e_recalcula_pm():
    engine = InvestmentEngine()
    engine.set_transactions([
        Transaction(
            data="10/01/2025",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=10.0,
            valor_total=1000.0,
            valor_unitario=100.0,
        ),
        Transaction(
            data="15/06/2025",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="desdobramento",
            quantidade=10.0,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
    ])

    res = engine.calculate()
    assert res["sales"] == []
    assert res["tax_reports"] == []
    pos = res["wallet"]["XPML11"]
    assert pos["quantidade"] == pytest.approx(100.0)
    assert pos["preco_medio"] == pytest.approx(10.0)
    assert pos["total_investido"] == pytest.approx(1000.0)


def test_agrupamento_preserva_custo_e_recalcula_pm():
    engine = InvestmentEngine()
    engine.set_transactions([
        Transaction(
            data="10/01/2025",
            ticker="MGLU3",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=100.0,
            valor_total=100.0,
            valor_unitario=1.0,
        ),
        Transaction(
            data="20/06/2025",
            ticker="MGLU3",
            tipo_ativo="ação",
            operacao="agrupamento",
            quantidade=0.1,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
    ])

    res = engine.calculate()
    assert res["sales"] == []
    assert res["tax_reports"] == []
    pos = res["wallet"]["MGLU3"]
    assert pos["quantidade"] == pytest.approx(10.0)
    assert pos["preco_medio"] == pytest.approx(10.0)
    assert pos["total_investido"] == pytest.approx(100.0)


def test_conversao_ticker_e_snapshot_irpf():
    engine = InvestmentEngine()
    engine.set_transactions([
        Transaction(
            data="10/03/2024",
            ticker="IRDM11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=50.0,
            valor_total=4000.0,
            valor_unitario=80.0,
        ),
        Transaction(
            data="15/05/2025",
            ticker="IRDM11->IRIM11",
            tipo_ativo="fii",
            operacao="conversao",
            quantidade=1.0,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
    ])

    res = engine.calculate()
    assert res["sales"] == []
    assert res["tax_reports"] == []
    assert "IRDM11" not in res["wallet"]
    assert "IRDM11->IRIM11" not in res["wallet"]

    pos = res["wallet"]["IRIM11"]
    assert pos["quantidade"] == pytest.approx(50.0)
    assert pos["preco_medio"] == pytest.approx(80.0)
    assert pos["total_investido"] == pytest.approx(4000.0)

    snapshot = engine.gerar_snapshot_anual_irpf(2025)
    assert snapshot["renda_variavel"]["meses"] == []

    bens = {b["ticker"]: b for b in snapshot["bens_e_direitos"]}
    assert "IRDM11" in bens
    assert bens["IRDM11"]["quantidade_ano_anterior"] == pytest.approx(50.0)
    assert bens["IRDM11"]["custo_total_ano_anterior"] == pytest.approx(4000.0)
    assert bens["IRDM11"]["quantidade_ano_atual"] == pytest.approx(0.0)
    assert bens["IRDM11"]["custo_total_ano_atual"] == pytest.approx(0.0)

    assert "IRIM11" in bens
    assert bens["IRIM11"]["quantidade_ano_anterior"] == pytest.approx(0.0)
    assert bens["IRIM11"]["custo_total_ano_anterior"] == pytest.approx(0.0)
    assert bens["IRIM11"]["quantidade_ano_atual"] == pytest.approx(50.0)
    assert bens["IRIM11"]["preco_medio_ano_atual"] == pytest.approx(80.0)
    assert bens["IRIM11"]["custo_total_ano_atual"] == pytest.approx(4000.0)


def test_dividends_service_com_eventos_corporativos():
    txs = [
        Transaction(
            data="01/01/2025",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=10.0,
            valor_total=1000.0,
            valor_unitario=100.0,
        ),
        Transaction(
            data="01/06/2025",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="desdobramento",
            quantidade=10.0,
        ),
        Transaction(
            data="01/01/2025",
            ticker="IRDM11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=50.0,
            valor_total=4000.0,
            valor_unitario=80.0,
        ),
        Transaction(
            data="01/05/2025",
            ticker="IRDM11->IRIM11",
            tipo_ativo="fii",
            operacao="conversao",
            quantidade=1.0,
        ),
    ]

    divs = {
        "XPML11": [
            {
                "data": "15/06/2025",
                "mes_ano": "06/2025",
                "dt": datetime(2025, 6, 15),
                "timestamp": int(datetime(2025, 6, 15).timestamp()),
                "amount": 0.90,
            }
        ],
        "IRIM11": [
            {
                "data": "15/05/2025",
                "mes_ano": "05/2025",
                "dt": datetime(2025, 5, 15),
                "timestamp": int(datetime(2025, 5, 15).timestamp()),
                "amount": 0.80,
            }
        ],
    }

    payments, _ = calculate_historical_dividends(txs, divs)
    by_ticker = {p["ticker"]: p for p in payments}

    assert by_ticker["XPML11"]["qtd"] == pytest.approx(100.0)
    assert by_ticker["XPML11"]["total"] == pytest.approx(90.0)
    assert by_ticker["IRIM11"]["qtd"] == pytest.approx(50.0)
    assert by_ticker["IRIM11"]["total"] == pytest.approx(40.0)


def test_corporate_event_schema_validacoes_e_conversao_engine():
    ev_conv = CorporateEventSchema(
        tipo_evento="conversao",
        ticker_origem="irdm11",
        ticker_destino="irim11",
        fator=1.0,
        data="2025-05-15",
    )
    assert ev_conv.ticker_origem == "IRDM11"
    assert ev_conv.ticker_destino == "IRIM11"
    assert ev_conv.tipo_ativo == TipoAtivo.FII
    assert ev_conv.data == "15/05/2025"

    tx_conv = ev_conv.to_engine_transaction()
    assert tx_conv.ticker == "IRDM11->IRIM11"
    assert tx_conv.operacao == "conversao"
    assert tx_conv.quantidade == 1.0
    assert tx_conv.valor_total == 0.0

    ev_split = CorporateEventSchema(
        tipo_evento=TipoEventoCorporativo.DESDOBRAMENTO,
        ticker_origem="XPML11",
        fator=10.0,
        data="15/06/2025",
    )
    tx_split = ev_split.to_engine_transaction()
    assert tx_split.ticker == "XPML11"
    assert tx_split.operacao == "desdobramento"
    assert tx_split.quantidade == 10.0

    with pytest.raises(ValidationError):
        CorporateEventSchema(
            tipo_evento="conversao",
            ticker_origem="IRDM11",
            ticker_destino=None,
            fator=1.0,
        )

    with pytest.raises(ValidationError):
        CorporateEventSchema(
            tipo_evento="conversao",
            ticker_origem="IRDM11",
            ticker_destino="IRDM11",
            fator=1.0,
        )

    with pytest.raises(ValidationError):
        CorporateEventSchema(
            tipo_evento="desdobramento",
            ticker_origem="XPML11",
            fator=0.0,
        )


def test_corporate_event_agent_com_test_model():
    mock_model = TestModel(
        custom_output_args={
            "tipo_evento": "conversao",
            "ticker_origem": "IRDM11",
            "ticker_destino": "IRIM11",
            "fator": 1.0,
            "data": "12/11/2026",
            "tipo_ativo": "fii",
        }
    )
    agent = criar_agente_evento_corporativo(model=mock_model)
    res = agent.run_sync("IRDM11 virou IRIM11 hoje")

    assert isinstance(res.output, CorporateEventSchema)
    assert res.output.tipo_evento == TipoEventoCorporativo.CONVERSAO
    assert res.output.ticker_origem == "IRDM11"
    assert res.output.ticker_destino == "IRIM11"
    assert res.output.fator == 1.0


def test_excel_roundtrip_eventos_corporativos(tmp_path: Path):
    excel_path = tmp_path / "teste_eventos.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimentações"
    ws.append(["Cota", "Quantidade", "Valor Total", "Valor Unitário", "Tipo", "Operação", "Data"])
    wb.save(excel_path)

    txs_in = [
        Transaction(
            data="15/06/2025",
            ticker="XPML11",
            tipo_ativo="fii",
            operacao="desdobramento",
            quantidade=10.0,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
        Transaction(
            data="20/06/2025",
            ticker="MGLU3",
            tipo_ativo="ação",
            operacao="agrupamento",
            quantidade=0.1,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
        Transaction(
            data="15/05/2025",
            ticker="IRDM11->IRIM11",
            tipo_ativo="fii",
            operacao="conversao",
            quantidade=1.0,
            valor_total=0.0,
            valor_unitario=0.0,
        ),
    ]

    for tx in txs_in:
        assert save_transaction_to_excel(tx, str(excel_path), prevent_duplicates=True) is True

    loaded = load_transactions_from_excel(str(excel_path))
    assert len(loaded) == 3
    assert [(t.ticker, t.operacao, t.quantidade) for t in loaded] == [
        ("XPML11", "desdobramento", 10.0),
        ("MGLU3", "agrupamento", 0.1),
        ("IRDM11->IRIM11", "conversao", 1.0),
    ]
