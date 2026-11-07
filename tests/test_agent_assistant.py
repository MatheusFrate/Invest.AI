"""
Testes do assistente e consultor fiscal (assistant_agent).
"""

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.exceptions import UnexpectedModelBehavior

from invest_ai.agent.agent import criar_agente_assistente, criar_agente_transacao
from invest_ai.agent.schemas import TransactionSchema


def test_assistente_fiscal_resposta(populated_context):
    texto_resposta = "Você possui 100 ações de PETR4 com preço médio de R$ 30,00."
    test_model = TestModel(custom_output_text=texto_resposta)
    
    agent = criar_agente_assistente(model=test_model)
    res = agent.run_sync("Qual é o meu preço médio em PETR4?", deps=populated_context)
    
    assert res.output == texto_resposta


def test_agente_transacao_esgota_retries_em_dados_invalidos(empty_context):
    # Sem custom_output_args, o TestModel gera dados não conformes com TransactionSchema
    # O agente tentará até o limite de 3 retries antes de estourar a exceção
    agent = criar_agente_transacao(model=TestModel())
    
    with pytest.raises(UnexpectedModelBehavior) as exc_info:
        agent.run_sync("Comprei alguma coisa", deps=empty_context)
    
    assert "Exceeded maximum output retries (3)" in str(exc_info.value)
