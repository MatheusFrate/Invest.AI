"""
Contexto de dependências injetado no PydanticAI (RunContext).
Mantém o estado da carteira, acesso ao InvestmentEngine e caminho da planilha.
"""

from dataclasses import dataclass, field
import os
from typing import Dict, List, Optional, Tuple

from invest_ai.config import DEFAULT_EXCEL_PATH, get_active_excel_path
from invest_ai.core.engine import InvestmentEngine, Transaction
from invest_ai.services.excel_handler import load_transactions_from_excel, save_transaction_to_excel
from invest_ai.services.dividends_service import (
    fetch_all_dividends,
    calculate_historical_dividends,
    get_dividends_for_ticker,
)


@dataclass
class InvestContext:
    """
    Contexto injetado no agente via PydanticAI RunContext[InvestContext].
    Permite ao agente acessar a carteira, simular DARF e persistir dados.
    """
    excel_path: str = field(default_factory=get_active_excel_path)
    engine: InvestmentEngine = field(default_factory=InvestmentEngine)
    _carteira_carregada: bool = False
    _dividends_data: Optional[Dict[str, List[Dict]]] = None
    _cached_payments: Optional[List[Dict]] = None
    _cached_monthly_stats: Optional[Dict[str, Dict]] = None

    def carregar_dados(self):
        """Carrega as transações do Excel e calcula o estado atual da carteira."""
        if os.path.exists(self.excel_path):
            transacoes = load_transactions_from_excel(self.excel_path)
            self.engine.set_transactions(transacoes)
        self._carteira_carregada = True
        self._cached_payments = None
        self._cached_monthly_stats = None

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

    def definir_dados_proventos(self, dados: Dict[str, List[Dict]]):
        """Permite injetar dados simulados ou mockados de proventos (útil para testes e modo offline)."""
        self._dividends_data = dados
        self._cached_payments = None
        self._cached_monthly_stats = None

    def obter_proventos_historicos(self, force_refresh: bool = False) -> Tuple[List[Dict], Dict[str, Dict]]:
        """
        Retorna os proventos históricos calculados da carteira:
        (todos_pagamentos, mensal_stats).
        Utiliza cache interno para evitar chamadas repetidas na mesma sessão.
        """
        if not force_refresh and self._cached_payments is not None and self._cached_monthly_stats is not None:
            return self._cached_payments, self._cached_monthly_stats

        if not self._carteira_carregada:
            self.carregar_dados()

        if self._dividends_data is None:
            tickers = list({tx.ticker.strip().upper() for tx in self.engine.transactions if tx.ticker})
            posicoes = self.obter_posicoes_carteira()
            tickers = list(set(tickers) | {t.strip().upper() for t in posicoes.keys() if t})

            if tickers:
                try:
                    self._dividends_data = fetch_all_dividends(tickers)
                except Exception:
                    self._dividends_data = {}
            else:
                self._dividends_data = {}

        pagamentos, stats = calculate_historical_dividends(
            self.engine.transactions,
            self._dividends_data or {}
        )
        self._cached_payments = pagamentos
        self._cached_monthly_stats = stats
        return pagamentos, stats

    def obter_dividendos_ticker(self, ticker: str) -> List[Dict]:
        """
        Retorna a lista bruta de eventos de dividendos de um ticker específico.
        """
        clean = ticker.strip().upper()
        if self._dividends_data is not None:
            return self._dividends_data.get(clean, [])

        self.obter_proventos_historicos()
        if self._dividends_data is not None:
            return self._dividends_data.get(clean, [])

        try:
            divs = get_dividends_for_ticker(clean)
            if self._dividends_data is None:
                self._dividends_data = {}
            self._dividends_data[clean] = divs
            return divs
        except Exception:
            return []

    def salvar_transacao(self, tx: Transaction) -> bool:
        """Salva uma nova transação no Excel principal e atualiza o estado em memória do engine."""
        try:
            # Sempre salva na planilha principal se estávamos apenas lendo a de exemplo
            caminho_destino = DEFAULT_EXCEL_PATH if "exemplo" in self.excel_path else self.excel_path
            save_transaction_to_excel(tx, filepath=caminho_destino)
            self.excel_path = caminho_destino
            self.carregar_dados()
            self._cached_payments = None
            self._cached_monthly_stats = None
            return True
        except Exception as e:
            print(f"Erro ao salvar transação no Excel: {e}")
            return False
