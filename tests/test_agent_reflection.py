"""
Teste comprobatório do Loop de Reflexão e Auto-Correção (Reflection / Retry Loop).
Demonstra como o PydanticAI rejeita uma resposta matematicamente inconsistente gerada
pelo modelo e força o agente a reprocessar e corrigir os dados autonomamente.
"""

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart

from invest_ai.agent.agent import criar_agente_transacao
from invest_ai.agent.deps import InvestContext
from invest_ai.agent.schemas import TransactionSchema


def test_loop_de_reflexao_e_autocorrecao():
    """
    Cenário:
    Turno 1: O modelo tenta entregar uma conta errada: 10 * 50 = 600.
             O Pydantic intercepta, dispara ValidationError e devolve o erro ao modelo.
    Turno 2: O modelo lê a mensagem de erro da validação e corrige a conta para 500.
             O Pydantic aprova e o agente finaliza com sucesso.
    """
    chamadas_modelo = 0

    def modelo_simulado_com_erro_inicial(messages, info):
        nonlocal chamadas_modelo
        chamadas_modelo += 1
        output_tool = info.output_tools[0].name

        if chamadas_modelo == 1:
            # Turno 1: Tentativa com matemática errada (10 * 50 != 600)
            args_com_erro = {
                "ticker": "PETR4",
                "quantidade": 10,
                "valor_unitario": 50.0,
                "valor_total": 600.0,
                "operacao": "compra"
            }
            return ModelResponse(parts=[ToolCallPart(output_tool, args_com_erro)])
        else:
            # Turno 2: Resposta corrigida após o feedback de erro do Pydantic
            args_corrigidos = {
                "ticker": "PETR4",
                "quantidade": 10,
                "valor_unitario": 50.0,
                "valor_total": 500.0,
                "operacao": "compra"
            }
            return ModelResponse(parts=[ToolCallPart(output_tool, args_corrigidos)])

    # Cria o agente acoplado a este modelo simulado
    agente = criar_agente_transacao(model=FunctionModel(modelo_simulado_com_erro_inicial))
    ctx = InvestContext(excel_path="mock_reflection.xlsx")

    # Executa o agente
    resultado = agente.run_sync(
        "Comprei 10 ações da PETR4 a R$ 50,00 cada dando R$ 600 no total",
        deps=ctx
    )

    # 1. Comprova que houve exatamente 2 turnos de inferência (1 erro + 1 correção)
    assert chamadas_modelo == 2, f"Esperado 2 turnos de inferência, mas foram {chamadas_modelo}"

    # 2. Comprova que o resultado final foi aceito e corrigido com sucesso
    output: TransactionSchema = resultado.output
    assert output.ticker == "PETR4"
    assert output.quantidade == 10.0
    assert output.valor_unitario == 50.0
    assert output.valor_total == 500.0
