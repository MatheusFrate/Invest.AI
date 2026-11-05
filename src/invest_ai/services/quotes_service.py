"""
Módulo para coletar cotações em tempo real de ativos da B3 via Yahoo Finance.
"""

import concurrent.futures
import json
import urllib.request
from typing import Dict, Optional, Tuple


def get_single_quote(ticker: str) -> Tuple[str, Optional[float], Optional[float]]:
    """
    Retorna (ticker, preco_atual, variacao_dia_pct)
    """
    clean_ticker = ticker.strip().upper()
    yahoo_ticker = f"{clean_ticker}.SA" if not clean_ticker.endswith(".SA") else clean_ticker

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?interval=1d&range=1d"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose")
            var_pct = ((price - prev_close) / prev_close * 100) if (price and prev_close) else 0.0
            return clean_ticker, float(price) if price is not None else None, float(var_pct)
    except Exception:
        return clean_ticker, None, None


def fetch_all_quotes(tickers: list) -> Dict[str, Dict]:
    """
    Busca cotações em paralelo para múltiplos tickers.
    Retorna: { 'MXRF11': {'price': 9.45, 'var_dia': 1.07}, ... }
    """
    unique_tickers = list(set([t.strip().upper() for t in tickers if t]))
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for ticker, price, var_dia in executor.map(get_single_quote, unique_tickers):
            if price is not None:
                results[ticker] = {
                    "price": price,
                    "var_dia": var_dia
                }

    return results
