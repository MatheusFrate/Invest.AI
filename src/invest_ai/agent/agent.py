"""
Definição dos Agentes PydanticAI para o Invest.AI.
Configura modelo (Gemini, OpenAI ou TestModel), injeção de dependências e ferramentas.
"""

import os
from typing import Optional, Union
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.fallback import FallbackModel

from invest_ai.agent.deps import InvestContext
from invest_ai.agent.schemas import TransactionSchema
from invest_ai.agent.tools import (
    obter_cotacao_b3,
    consultar_posicao_carteira,
    listar_resumo_carteira,
    simular_impacto_darf
)

# Carrega variáveis de ambiente (.env)
load_dotenv()
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# Compatibilidade para Google Gemini: se o usuário colocou GEMINI_API_KEY, copia para GOOGLE_API_KEY
if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")


def resolver_modelo_padrao() -> Union[str, FallbackModel]:
    """
    Resolve o modelo de IA baseado nas chaves disponíveis no ambiente.
    Utiliza FallbackModel com cadeia de resiliência:
    1. gemini-flash-lite-latest (endpoint estável e leve)
    2. gemini-3.5-flash-lite
    3. gemini-3.5-flash
    Isso contorna eventuais picos de tráfego 503 (Unavailable) na camada gratuita da Google.
    """
    custom_model = os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL")
    if custom_model:
        return custom_model

    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return FallbackModel(
            "google:gemini-flash-lite-latest",
            "google:gemini-3.5-flash-lite",
            "google:gemini-3.5-flash"
        )
    elif os.getenv("OPENAI_API_KEY"):
        return "openai:gpt-4o-mini"
    return "test"


# =====================================================================
# 1. Agente de Extração e Validação de Transações (Structured Output)
# =====================================================================
PROMPT_EXTRATOR_TRANSACAO = """
Você é um auditor financeiro e registrador especializado em ativos negociados na B3 (ações, FIIs, ETFs e BDRs).
Sua missão é extrair rigorosamente os dados da transação financeira informada pelo usuário em linguagem natural.

Diretrizes obrigatórias:
1. Identifique o Ticker correto (sempre em maiúsculas, ex: PETR4, VALE3, MXRF11).
2. Se o usuário mencionar o nome da empresa (ex: "comprei Petrobras"), converta para o ticker correto (ex: PETR4).
3. Identifique a operação: "compra" ou "venda".
4. Extraia a quantidade negociada.
5. Extraia o valor unitário e/ou valor total. Lembre-se: quantidade * valor_unitario DEVE ser igual ao valor_total.
6. A data deve ser formatada como YYYY-MM-DD. Se o usuário disser "hoje" ou omitir a data, use a data atual.
7. Se identificar a corretora (ex: NuInvest, XP, Rico, Clear), preencha o campo correspondente.
8. Se houver qualquer divergência matemática ou formato inválido, ajuste antes de finalizar o schema.
"""


def criar_agente_transacao(model: Optional[Union[str, FallbackModel, any]] = None) -> Agent[InvestContext, TransactionSchema]:
    """
    Cria o agente responsável por ler texto desestruturado e retornar um TransactionSchema estrito.
    """
    modelo_ativo = model or resolver_modelo_padrao()

    agente = Agent(
        modelo_ativo,
        deps_type=InvestContext,
        output_type=TransactionSchema,
        system_prompt=PROMPT_EXTRATOR_TRANSACAO,
        retries=3,
        tools=[obter_cotacao_b3]
    )

    return agente


# =====================================================================
# 2. Agente Assistente e Consultor Fiscal (DARF e Carteira)
# =====================================================================
PROMPT_ASSISTENTE_FISCAL = """
Você é um consultor tributário e assessor de investimentos especializado no mercado de capitais brasileiro (B3).
Você tem acesso às ferramentas para consultar a carteira do usuário, verificar cotações e simular cálculo de DARF.

Diretrizes obrigatórias:
1. Sempre use as ferramentas disponíveis quando o usuário fizer perguntas sobre sua carteira ou simulações.
2. Não invente posições em carteira nem cotações; chame as ferramentas:
   - Para saber se o usuário tem o ativo e o preço médio: use `consultar_posicao_carteira`.
   - Para ver a carteira toda: use `listar_resumo_carteira`.
   - Para cotação atual: use `obter_cotacao_b3`.
   - Para calcular imposto sobre venda: use `simular_impacto_darf`.
3. Regras Fiscais da B3 para suas explicações:
   - FIIs: Alíquota fixa de 20% sobre o lucro líquido. NÃO possuem faixa de isenção de R$ 20.000.
   - Ações (mercado à vista): Vendas no mês até R$ 20.000 são totalmente ISENTAS de IR. Vendas acima de R$ 20.000 pagam 15% de IR sobre o lucro.
   - Prejuízos: Podem ser compensados com lucros futuros da mesma espécie de ativo.
4. Formatação de Saída (CRÍTICO):
   - NUNCA use sintaxe Markdown (como **, *, #, __, ```). A interface gráfica desktop do aplicativo não suporta Markdown e exibe os asteriscos e cerquilhas literalmente.
   - Responda em TEXTO PURO, limpo e direto.
   - Para listas de ativos ou valores, use marcadores simples como "• " ou "- ".
   - Para destacar nomes de ativos e valores, use CAIXA ALTA ou escreva diretamente (ex: PETR4: 28 ações com preço médio de R$ 35,15).
   - Seja conciso, amigável e objetivo.
"""


def criar_agente_assistente(model: Optional[Union[str, FallbackModel, any]] = None) -> Agent[InvestContext, str]:
    """
    Cria o agente consultor de investimentos e cálculo fiscal.
    """
    modelo_ativo = model or resolver_modelo_padrao()

    agente = Agent(
        modelo_ativo,
        deps_type=InvestContext,
        output_type=str,
        system_prompt=PROMPT_ASSISTENTE_FISCAL,
        retries=2,
        tools=[
            obter_cotacao_b3,
            consultar_posicao_carteira,
            listar_resumo_carteira,
            simular_impacto_darf
        ]
    )

    return agente


# Instâncias padrão prontas para importação direta
transaction_agent = criar_agente_transacao()
assistant_agent = criar_agente_assistente()
