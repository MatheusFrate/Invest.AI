"""
Camada de Serviços Externos e Persistência (Excel, Yahoo Finance Cotações e Dividendos).
"""

from invest_ai.services.excel_handler import (
    DEFAULT_EXCEL_PATH,
    load_transactions_from_excel,
    save_transaction_to_excel,
    save_transactions_batch_to_excel,
    is_duplicate_transaction,
    normalizar_data_br,
    normalizar_todas_datas_planilha,
    update_transaction_in_excel,
    delete_transaction_from_excel,
    load_paid_darfs,
    record_paid_darf,
)
from invest_ai.services.quotes_service import get_single_quote, fetch_all_quotes
from invest_ai.services.dividends_service import (
    get_dividends_for_ticker,
    fetch_all_dividends,
    calculate_historical_dividends,
)

__all__ = [
    "DEFAULT_EXCEL_PATH",
    "load_transactions_from_excel",
    "save_transaction_to_excel",
    "save_transactions_batch_to_excel",
    "is_duplicate_transaction",
    "normalizar_data_br",
    "normalizar_todas_datas_planilha",
    "update_transaction_in_excel",
    "delete_transaction_from_excel",
    "load_paid_darfs",
    "record_paid_darf",
    "get_single_quote",
    "fetch_all_quotes",
    "get_dividends_for_ticker",
    "fetch_all_dividends",
    "calculate_historical_dividends",
]
