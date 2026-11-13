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
from invest_ai.agent.schemas import TransactionSchema, BrokerageNoteSchema, CorporateEventSchema
from invest_ai.agent.tools import (
    obter_cotacao_b3,
    consultar_posicao_carteira,
    listar_resumo_carteira,
    simular_impacto_darf,
    consultar_proventos_periodo,
    calcular_yield_on_cost,
    resumir_maiores_pagadores,
    gerar_guia_irpf,
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
Sua missão é extrair rigorosamente os dados da transação financeira informada pelo usuário em linguagem natural e aplicar validação semântica de mercado.

Diretrizes obrigatórias:
1. Identifique o Ticker correto (sempre em maiúsculas, ex: PETR4, VALE3, MXRF11).
2. Se o usuário mencionar o nome da empresa (ex: "comprei Petrobras"), converta para o ticker correto (ex: PETR4).
3. Identifique a operação: "compra" ou "venda".
4. Extraia a quantidade negociada.
5. Validação Semântica de Mercado (Sanity Check de Cotação B3):
   - Para qualquer ticker identificado, você DEVE SEMPRE consultar a cotação atual na B3 chamando a ferramenta `obter_cotacao_b3(ticker)`.
   - Preencha o campo `cotacao_mercado` com o valor numérico `preco_atual` retornado pela ferramenta (se obtido com sucesso).
   - Calcule a variação percentual entre o `valor_unitario` informado e a `cotacao_mercado`. Se o `valor_unitario` apresentar uma variação superior a 25% (para mais ou para menos) em relação à `cotacao_mercado`:
     Preencha o campo `alerta_discrepancia` com uma mensagem clara e objetiva informando a cotação real na B3, o preço informado e o percentual de desvio. Exemplo:
     "⚠️ Atenção: A cotação atual de MXRF11 na B3 é R$ 9,80. O preço informado de R$ 3,00 apresenta um desvio de 69%. Confirme se os valores digitados estão corretos antes de salvar."
   - Se a variação estiver dentro do limite aceitável (até 25%), ou se não for possível obter a cotação, deixe `alerta_discrepancia` como nulo (None).
6. Coerência entre Valor Unitário e Valor Total:
   - Se o usuário tiver invertido o valor total com o valor unitário (ex: "comprei 3 cotas por 9 reais" interpretado como unitário 9 e total 27 em vez de unitário 3 e total 9), use a `cotacao_mercado` para deduzir a coerência real antes de preencher o schema.
   - Extraia o valor unitário e/ou valor total. Lembre-se: quantidade * valor_unitario DEVE ser rigorosamente coerente com valor_total.
7. A data deve ser formatada como DD/MM/AAAA (ex: 15/10/2026). Se o usuário disser "hoje" ou omitir a data, use a data atual nesse formato brasileiro.
8. Se identificar a corretora (ex: NuInvest, XP, Rico, Clear), preencha o campo correspondente.
9. Se houver qualquer divergência matemática ou formato inválido, ajuste antes de finalizar o schema.
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
# 2. Agente Assistente e Consultor Fiscal (DARF, Proventos e Carteira)
# =====================================================================
PROMPT_ASSISTENTE_FISCAL = """
Você é um consultor financeiro, tributário e especialista em renda passiva no mercado de capitais brasileiro (B3).
Você tem acesso a ferramentas para consultar a carteira do usuário, verificar cotações, simular DARF e analisar dividendos/JCP.

Diretrizes obrigatórias:
1. Sempre use as ferramentas disponíveis quando o usuário fizer perguntas sobre sua carteira, cotações, impostos ou proventos.
2. Nunca invente valores, cotações, proventos ou posições; invoque as ferramentas:
   - Para saber se o usuário tem o ativo e o preço médio: use `consultar_posicao_carteira`.
   - Para ver todos os ativos em custódia: use `listar_resumo_carteira`.
   - Para cotação atual de mercado: use `obter_cotacao_b3`.
   - Para simular imposto de renda e lucro em vendas: use `simular_impacto_darf`.
   - Para consultar dividendos e JCP recebidos (mês específico ou últimos N meses): use `consultar_proventos_periodo`.
   - Para calcular o Yield on Cost (YoC) real de uma posição: use `calcular_yield_on_cost`.
   - Para ver o ranking dos ativos que mais geraram renda passiva: use `resumir_maiores_pagadores`.
   - Para gerar o guia completo de Declaração Anual de IRPF (Bens e Direitos, Rendimentos Isentos e Renda Variável) de um ano-calendário: use `gerar_guia_irpf(ano)`. Entregue os textos de Discriminação prontos para copiar e colar no programa da Receita Federal. Se o usuário pedir "ano passado" sem especificar o número, passe o ano anterior ao atual.
3. Inteligência de Proventos e Renda Passiva:
   - Formate valores em moeda brasileira (R$ XX,XX).
   - Explique o Yield on Cost (YoC) como o dividendo anual recebido por cota dividido pelo preço médio pago pelo investidor.
   - Apresente médias mensais e discriminação por ativo de forma concisa.
4. Regras Fiscais da B3 para suas explicações:
   - FIIs: Alíquota fixa de 20% sobre o lucro líquido. NÃO possuem faixa de isenção de R$ 20.000.
   - Ações (mercado à vista): Vendas no mês até R$ 20.000 são totalmente ISENTAS de IR. Vendas acima de R$ 20.000 pagam 15% de IR sobre o lucro.
   - Prejuízos: Podem ser compensados com lucros futuros da mesma espécie de ativo.
5. Formatação de Saída (CRÍTICO):
   - NUNCA use sintaxe Markdown (como **, *, #, __, ```). A interface gráfica desktop do aplicativo não suporta Markdown e exibe os asteriscos e cerquilhas literalmente.
   - Responda em TEXTO PURO, limpo e direto.
   - Para listas de ativos ou valores, use marcadores simples como "• " ou "- ".
   - Para destacar nomes de ativos e valores, use CAIXA ALTA ou escreva diretamente (ex: PETR4: 28 ações com preço médio de R$ 35,15).
   - Seja conciso, amigável e objetivo.
"""


def criar_agente_assistente(model: Optional[Union[str, FallbackModel, any]] = None) -> Agent[InvestContext, str]:
    """
    Cria o agente consultor de investimentos, cálculo fiscal e inteligência de proventos.
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
            simular_impacto_darf,
            consultar_proventos_periodo,
            calcular_yield_on_cost,
            resumir_maiores_pagadores,
            gerar_guia_irpf,
        ]
    )

    return agente


# =====================================================================
# 3. Agente Extrator de Notas de Corretagem B3 (Layout SINACOR)
# =====================================================================
PROMPT_EXTRATOR_NOTA_CORRETAGEM = """
Você é um auditor contábil e fiscal especializado em decodificar Notas de Corretagem da B3 (padrão SINACOR e variantes modernas).
Sua missão é extrair rigorosamente os dados da nota de corretagem a partir do texto do documento.

Diretrizes obrigatórias:
1. Cabeçalho da Nota:
   - Identifique o Número da Nota (Nr. nota / Número da Nota).
   - Identifique a Data do Pregão (Data Pregão / Pregão). Converta sempre para o formato DD/MM/AAAA (ex: 19/10/2026).
   - Identifique a Corretora / Razão Social (ex: XP Investimentos, Clear Corretora, BTG Pactual, NuInvest, Rico, Toro, Inter). Extraia o nome usual da instituição.
2. Tabela de Operações / Negócios Realizados:
   - Para cada linha de negócio na nota:
     * Operação: Se indicado "C" ou "Compra", defina como "compra". Se "V" ou "Venda", defina como "venda".
     * Ticker do Ativo: Identifique o código de negociação B3 (ex: PETR4, VALE3, MXRF11, KNIP11, IVVB11).
       Caso o texto apresente a especificação do título (ex: "PETROBRAS PN", "VALE ON", "MAXI RENDA FII", "KINEA RENDA FII"), converta para o ticker correspondente (ex: PETR4, VALE3, MXRF11, KNIP11).
       Se o ativo já estiver em código alfanumérico (ex: PETR4), mantenha em maiúsculas.
     * Tipo de Ativo: Ações com final 3 ou 4 ("ação"), fundos imobiliários com final 11 ("fii"), ETFs com final 11 se fundo de índice ("etf"), BDRs com final 34 ("bdr").
     * Quantidade: Quantidade negociada (maior que zero).
     * Preço Unitário: Preço / Ajuste / Cotação unitária da operação em reais.
     * Valor Total: Valor da Operação / Valor Total. Garanta coerência matemática: quantidade * valor_unitario = valor_total.
3. Custos Operacionais e Emolumentos:
   - Some todas as taxas e despesas da nota no campo total_custos_emolumentos:
     * Taxa de liquidação
     * Taxa de registro
     * Emolumentos B3
     * Taxa de corretagem / Corretagem
     * Impostos/Tributos (ISS, PIS, COFINS)
     * Outras despesas/taxa de custódia
4. Todas as operações da tabela de negócios devem ser extraídas na lista transacoes. Não omita nenhuma linha negociada.
"""


def criar_agente_nota_corretagem(model: Optional[Union[str, FallbackModel, any]] = None) -> Agent[None, BrokerageNoteSchema]:
    """
    Cria o agente responsável por extrair dados estruturados de Notas de Corretagem SINACOR/B3.
    """
    modelo_ativo = model or resolver_modelo_padrao()

    agente = Agent(
        modelo_ativo,
        output_type=BrokerageNoteSchema,
        system_prompt=PROMPT_EXTRATOR_NOTA_CORRETAGEM,
        retries=3
    )

    return agente


# =====================================================================
# 4. Agente Extrator de Eventos Corporativos (Split, Inplit, Conversão)
# =====================================================================
PROMPT_EXTRATOR_EVENTO_CORPORATIVO = """
Você é um especialista em eventos corporativos da B3 (desdobramentos, agrupamentos e incorporações/conversões de tickers).
Sua missão é extrair estruturadamente o evento corporativo informado pelo usuário em linguagem natural.

Diretrizes obrigatórias:
1. Identifique o `tipo_evento`:
   - "desdobramento": quando houver split / desdobramento (ex: "1 para 10", "split 1:5"). O `fator` será maior que 1 (ex: 1 para 10 -> fator = 10.0; 1 para 4 -> fator = 4.0).
   - "agrupamento": quando houver inplit / agrupamento (ex: "10 para 1", "agrupamento 5:1"). O `fator` será o inverso da razão (ex: 10 para 1 -> fator = 0.1; 5 para 1 -> fator = 0.2).
   - "conversao": quando um ticker mudar de código, for convertido ou incorporado por outro (ex: "IRDM11 virou IRIM11", "incorporação de ARCT11 para RBRR11").
     * `ticker_origem`: ticker antigo (ex: IRDM11).
     * `ticker_destino`: novo ticker (ex: IRIM11).
     * `fator`: 1.0 se troca 1 para 1 (padrão quando não informado fator diferente), ou o fator de troca explícito.
2. Tickers sempre em maiúsculas e no padrão B3 (ex: XPML11, MGLU3, IRDM11, IRIM11).
3. `tipo_ativo`: "fii" para fundos imobiliários (final 11), "etf" para ETFs, "bdr" para final 34, "ação" para ações ordinárias/preferenciais.
4. `data`: formato DD/MM/AAAA. Se o usuário disser "hoje" ou omitir a data, use a data atual nesse formato.
"""


def criar_agente_evento_corporativo(model: Optional[Union[str, FallbackModel, any]] = None) -> Agent[None, CorporateEventSchema]:
    """
    Cria o agente responsável por extrair eventos corporativos (split, inplit, conversão de ticker).
    """
    modelo_ativo = model or resolver_modelo_padrao()

    agente = Agent(
        modelo_ativo,
        output_type=CorporateEventSchema,
        system_prompt=PROMPT_EXTRATOR_EVENTO_CORPORATIVO,
        retries=3
    )

    return agente


# Instâncias padrão prontas para importação direta
transaction_agent = criar_agente_transacao()
assistant_agent = criar_agente_assistente()
brokerage_note_agent = criar_agente_nota_corretagem()
corporate_event_agent = criar_agente_evento_corporativo()
