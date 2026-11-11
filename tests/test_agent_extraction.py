"""
Testes de extração estruturada do transaction_agent.
"""

from unittest.mock import patch
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart
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


def test_extracao_discrepancia_cotacao_b3_gera_alerta(empty_context):
    alerta_esperado = (
        "⚠️ Atenção: A cotação atual de MXRF11 na B3 é R$ 9,80. "
        "O preço informado de R$ 3,00 apresenta um desvio de 69%. "
        "Confirme se os valores digitados estão corretos antes de salvar."
    )
    test_model = TestModel(
        call_tools=[],
        custom_output_args={
            "ticker": "MXRF11",
            "quantidade": 3,
            "valor_unitario": 3.00,
            "valor_total": 9.00,
            "operacao": "compra",
            "cotacao_mercado": 9.80,
            "alerta_discrepancia": alerta_esperado
        }
    )
    agent = criar_agente_transacao(model=test_model)
    res = agent.run_sync("Comprei 3 cotas de MXRF11 a R$ 3,00", deps=empty_context)

    output = res.output
    assert isinstance(output, TransactionSchema)
    assert output.ticker == "MXRF11"
    assert output.quantidade == 3.0
    assert output.valor_unitario == 3.00
    assert output.valor_total == 9.00
    assert output.cotacao_mercado == 9.80
    assert output.alerta_discrepancia == alerta_esperado
    assert "MXRF11" in output.alerta_discrepancia
    assert "9,80" in output.alerta_discrepancia


def test_extracao_cotacao_alinhada_sem_alerta(empty_context):
    test_model = TestModel(
        call_tools=[],
        custom_output_args={
            "ticker": "MXRF11",
            "quantidade": 3,
            "valor_unitario": 9.80,
            "valor_total": 29.40,
            "operacao": "compra",
            "cotacao_mercado": 9.80,
            "alerta_discrepancia": None
        }
    )
    agent = criar_agente_transacao(model=test_model)
    res = agent.run_sync("Comprei 3 cotas de MXRF11 a R$ 9,80", deps=empty_context)

    output = res.output
    assert isinstance(output, TransactionSchema)
    assert output.ticker == "MXRF11"
    assert output.cotacao_mercado == 9.80
    assert output.alerta_discrepancia is None


def test_agente_transacao_invoca_tool_cotacao_e_registra_discrepancia(empty_context):
    turno = 0
    alerta_esperado = (
        "⚠️ Atenção: A cotação atual de MXRF11 na B3 é R$ 9,80. "
        "O preço informado de R$ 3,00 apresenta um desvio de 69%."
    )

    def simulador_agente(messages, info):
        nonlocal turno
        turno += 1
        if turno == 1:
            return ModelResponse(parts=[ToolCallPart("obter_cotacao_b3", {"ticker": "MXRF11"})])
        else:
            output_tool = info.output_tools[0].name
            args = {
                "ticker": "MXRF11",
                "quantidade": 3,
                "valor_unitario": 3.0,
                "valor_total": 9.0,
                "operacao": "compra",
                "cotacao_mercado": 9.80,
                "alerta_discrepancia": alerta_esperado
            }
            return ModelResponse(parts=[ToolCallPart(output_tool, args)])

    with patch("invest_ai.services.quotes_service.get_single_quote", return_value=("MXRF11", 9.80, 0.5)):
        agente = criar_agente_transacao(model=FunctionModel(simulador_agente))
        res = agente.run_sync("Comprei 3 cotas de MXRF11 a R$ 3,00", deps=empty_context)

        assert res.output.ticker == "MXRF11"
        assert res.output.cotacao_mercado == 9.80
        assert res.output.alerta_discrepancia == alerta_esperado
        assert turno == 2


