"""
Contexto de dependências injetado no PydanticAI (RunContext).
Mantém o estado da carteira, acesso ao InvestmentEngine e caminho da planilha.
"""

from dataclasses import dataclass, field
import os
from typing import Dict, Optional

from invest_ai.config import DEFAULT_EXCEL_PATH, get_active_excel_path
from invest_ai.core.engine import InvestmentEngine, Transaction
from invest_ai.services.excel_handler import load_transactions_from_excel, save_transaction_to_excel


@dataclass
class InvestContext:
    """
    Contexto injetado no agente via PydanticAI RunContext[InvestContext].
    Permite ao agente acessar a carteira, simular DARF e persistir dados.
    """
    excel_path: str = field(default_factory=get_active_excel_path)
    engine: InvestmentEngine = field(default_factory=InvestmentEngine)
    _carteira_carregada: bool = False

    def carregar_dados(self):
        """Carrega as transações do Excel e calcula o estado atual da carteira."""
        if os.path.exists(self.excel_path):
            transacoes = load_transactions_from_excel(self.excel_path)
            self.engine.set_transactions(transacoes)
        self._carteira_carregada = True

    def obter_posicoes_carteira(self) -> Dict[str, Dict]:
        """Retorna o dicionário de posições ativas da carteira (ticker -> dados)."""
        if not self._carteira_carregada:
            self.carregar_dados()
        resultado = self.engine.calculate()
        return resultado.get("wallet", {})

    def obter_posicao_ticker(self, ticker: str) -> Optional[Dict]:
        """Retorna os dados de posição de um ticker específico ou None se não possuir."""
        posicoes = self.obter_posicoes_carteira()
        return posicoes.get(ticker.strip().upper())

    def salvar_transacao(self, tx: Transaction) -> bool:
        """Salva uma nova transação no Excel principal e atualiza o estado em memória do engine."""
        try:
            # Sempre salva na planilha principal se estávamos apenas lendo a de exemplo
            caminho_destino = DEFAULT_EXCEL_PATH if "exemplo" in self.excel_path else self.excel_path
            save_transaction_to_excel(tx, filepath=caminho_destino)
            self.excel_path = caminho_destino
            self.carregar_dados()
            return True
        except Exception as e:
            print(f"Erro ao salvar transação no Excel: {e}")
            return False
