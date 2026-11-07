"""
Fixtures compartilhadas para a suíte de testes.
"""

import pytest
from unittest.mock import MagicMock
from invest_ai.agent.deps import InvestContext
from invest_ai.core.engine import Transaction


@pytest.fixture
def empty_context():
    """Contexto com carteira vazia para testes de novos aportes."""
    return InvestContext(excel_path="mock_empty.xlsx")


@pytest.fixture
def populated_context():
    """Contexto com ativos pré-carregados para testes de custódia e simulação de DARF."""
    ctx = InvestContext(excel_path="mock_populated.xlsx")
    txs = [
        Transaction(
            data="2026-01-10",
            ticker="PETR4",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=100.0,
            valor_unitario=30.0,
            valor_total=3000.0
        ),
        Transaction(
            data="2026-01-15",
            ticker="MXRF11",
            tipo_ativo="fii",
            operacao="compra",
            quantidade=50.0,
            valor_unitario=10.0,
            valor_total=500.0
        ),
        Transaction(
            data="2026-02-01",
            ticker="VALE3",
            tipo_ativo="ação",
            operacao="compra",
            quantidade=1000.0,
            valor_unitario=50.0,
            valor_total=50000.0
        )
    ]
    ctx.engine.set_transactions(txs)
    ctx._carteira_carregada = True
    return ctx


@pytest.fixture
def mock_run_context(populated_context):
    """Mock de RunContext do PydanticAI contendo o contexto populado."""
    run_ctx = MagicMock()
    run_ctx.deps = populated_context
    return run_ctx
