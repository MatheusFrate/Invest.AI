"""
Camada de Interface de Usuário (Desktop GUI com CustomTkinter e CLI com Rich).
"""

from invest_ai.ui.desktop_app import InvestAIApp
from invest_ai.ui.cli import main as run_cli

__all__ = ["InvestAIApp", "run_cli"]
