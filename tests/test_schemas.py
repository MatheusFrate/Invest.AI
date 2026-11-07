"""
Testes dos schemas de validação com Pydantic v2.
"""

import pytest
from pydantic import ValidationError
from invest_ai.agent.schemas import TransactionSchema, TipoOperacao, TipoAtivo


def test_transacao_valida_completa():
    data = {
        "ticker": "petr4",
        "quantidade": 10,
        "valor_unitario": 38.50,
        "valor_total": 385.00,
        "operacao": "compra",
        "corretora": "Rico",
        "data": "04/11/2026"
    }
    tx = TransactionSchema(**data)
    assert tx.ticker == "PETR4"
    assert tx.tipo_ativo == TipoAtivo.ACAO
    assert tx.quantidade == 10
    assert tx.valor_total == 385.00
    assert tx.data == "2026-11-04"


def test_auto_calculo_valor_total():
    tx = TransactionSchema(
        ticker="VALE3",
        quantidade=100,
        valor_unitario=62.50
    )
    assert tx.valor_total == 6250.00


def test_auto_calculo_valor_unitario():
    tx = TransactionSchema(
        ticker="MXRF11",
        quantidade=50,
        valor_total=475.00
    )
    assert tx.tipo_ativo == TipoAtivo.FII
    assert tx.valor_unitario == 9.50


def test_bloqueio_inconsistencia_matematica():
    with pytest.raises(ValidationError) as exc_info:
        TransactionSchema(
            ticker="PETR4",
            quantidade=10,
            valor_unitario=50.00,
            valor_total=600.00
        )
    assert "Inconsistência matemática detectada" in str(exc_info.value)


def test_ticker_invalido():
    with pytest.raises(ValidationError):
        TransactionSchema(
            ticker="INVALIDO_LONG_TICKER",
            quantidade=10,
            valor_total=100.0
        )


def test_conversao_para_engine_legado():
    tx_schema = TransactionSchema(
        ticker="BBDC4",
        quantidade=20,
        valor_unitario=14.00,
        data="2026-11-04"
    )
    engine_tx = tx_schema.to_engine_transaction()
    assert engine_tx.ticker == "BBDC4"
    assert engine_tx.tipo_ativo == "ação"
    assert engine_tx.operacao == "compra"
    assert engine_tx.quantidade == 20.0
    assert engine_tx.valor_total == 280.0
    assert engine_tx.valor_unitario == 14.0
