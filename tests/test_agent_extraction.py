"""
Testes de extração estruturada do transaction_agent.
"""

from pydantic_ai.models.test import TestModel
from invest_ai.agent.agent import criar_agente_transacao
from invest_ai.agent.schemas import TransactionSchema, TipoAtivo, TipoOperacao


def test_extracao_aporte_simples(empty_context):
    test_model = TestModel(
        custom_output_args={
            "ticker": "PETR4",
            "quantidade": 100,
            "valor_unitario": 38.50,
            "operacao": "compra",
            "corretora": "XP",
            "data": "2026-11-04"
        }
    )
    agent = criar_agente_transacao(model=test_model)
    res = agent.run_sync("Comprei 100 ações de PETR4 a 38.50 na XP hoje", deps=empty_context)
    
    output = res.output
    assert isinstance(output, TransactionSchema)
    assert output.ticker == "PETR4"
    assert output.quantidade == 100.0
    assert output.valor_unitario == 38.50
    assert output.valor_total == 3850.00
    assert output.tipo_ativo == TipoAtivo.ACAO
    assert output.operacao == TipoOperacao.COMPRA


def test_extracao_venda_fii(empty_context):
    test_model = TestModel(
        custom_output_args={
            "ticker": "MXRF11",
            "quantidade": 50,
            "valor_unitario": 9.80,
            "operacao": "venda",
            "corretora": "NuInvest"
        }
    )
    agent = criar_agente_transacao(model=test_model)
    res = agent.run_sync("Vendi 50 MXRF11 a 9.80 pela NuInvest", deps=empty_context)
    
    output = res.output
    assert output.ticker == "MXRF11"
    assert output.tipo_ativo == TipoAtivo.FII
    assert output.operacao == TipoOperacao.VENDA
    assert output.valor_total == 490.00
