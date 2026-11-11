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
    assert tx.data == "04/11/2026"


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
    assert engine_tx.data == "04/11/2026"


def test_schema_com_campos_de_mercado_e_discrepancia():
    alerta = "⚠️ Atenção: A cotação atual de MXRF11 na B3 é R$ 9,80. O preço informado de R$ 3,00 apresenta um desvio de 69%."
    tx = TransactionSchema(
        ticker="MXRF11",
        quantidade=3,
        valor_unitario=3.00,
        cotacao_mercado=9.80,
        alerta_discrepancia=alerta
    )
    assert tx.cotacao_mercado == 9.80
    assert tx.alerta_discrepancia == alerta

    # Garante que to_engine_transaction() funciona sem ser afetado pelos novos campos
    engine_tx = tx.to_engine_transaction()
    assert engine_tx.ticker == "MXRF11"
    assert engine_tx.quantidade == 3.0
    assert engine_tx.valor_unitario == 3.00
    assert engine_tx.valor_total == 9.00


def test_retrocompatibilidade_campos_opcionais_default_none():
    tx = TransactionSchema(
        ticker="PETR4",
        quantidade=10,
        valor_unitario=38.50
    )
    assert tx.cotacao_mercado is None
    assert tx.alerta_discrepancia is None

