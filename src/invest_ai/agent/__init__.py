"""
Camada Cognitiva de Agentes com PydanticAI.
"""

from invest_ai.agent.schemas import (
    TipoOperacao,
    TipoAtivo,
    TransactionSchema,
    TaxSimulationResponse,
)
from invest_ai.agent.deps import InvestContext
from invest_ai.agent.tools import (
    obter_cotacao_b3,
    consultar_posicao_carteira,
    listar_resumo_carteira,
    simular_impacto_darf,
)
from invest_ai.agent.agent import (
    resolver_modelo_padrao,
    criar_agente_transacao,
    criar_agente_assistente,
    transaction_agent,
    assistant_agent,
)

__all__ = [
    "TipoOperacao",
    "TipoAtivo",
    "TransactionSchema",
    "TaxSimulationResponse",
    "InvestContext",
    "obter_cotacao_b3",
    "consultar_posicao_carteira",
    "listar_resumo_carteira",
    "simular_impacto_darf",
    "resolver_modelo_padrao",
    "criar_agente_transacao",
    "criar_agente_assistente",
    "transaction_agent",
    "assistant_agent",
]
