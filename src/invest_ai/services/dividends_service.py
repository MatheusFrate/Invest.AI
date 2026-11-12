"""
Módulo para consultar dividendos históricos de ativos da B3 via Yahoo Finance
e calcular proventos recebidos com base na linha do tempo das movimentações.
"""

import concurrent.futures
import json
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from invest_ai.core.engine import Transaction


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        if "/" in date_str:
            parts = date_str.strip().split("/")
            if len(parts) == 3:
                return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        elif "-" in date_str:
            parts = date_str.strip().split("-")
            if len(parts) == 3:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        pass
    return None


def get_dividends_for_ticker(ticker: str) -> List[Dict]:
    """
    Retorna lista de dividendos pagos:
    [{'data': 'DD/MM/YYYY', 'mes_ano': 'MM/YYYY', 'dt': datetime, 'timestamp': int, 'amount': float}, ...]
    """
    clean = ticker.strip().upper()
    yahoo_ticker = f"{clean}.SA" if not clean.endswith(".SA") else clean

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}?events=div&interval=1mo&range=2y"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            events = data["chart"]["result"][0].get("events", {})
            divs = events.get("dividends", {})

            result = []
            for ts_str, item in divs.items():
                ts = int(ts_str)
                dt = datetime.fromtimestamp(ts)
                amt = float(item.get("amount", 0.0))
                if amt > 0:
                    result.append({
                        "ticker": clean,
                        "data": dt.strftime("%d/%m/%Y"),
                        "mes_ano": dt.strftime("%m/%Y"),
                        "dt": dt,
                        "timestamp": ts,
                        "amount": amt
                    })

            result.sort(key=lambda x: x["timestamp"], reverse=True)
            return result
    except Exception:
        return []


def fetch_all_dividends(tickers: list) -> Dict[str, List[Dict]]:
    unique_tickers = list(set([t.strip().upper() for t in tickers if t]))
    dividends_by_ticker = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_ticker = {executor.submit(get_dividends_for_ticker, t): t for t in unique_tickers}
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                dividends_by_ticker[ticker] = future.result()
            except Exception:
                dividends_by_ticker[ticker] = []

    return dividends_by_ticker


def calculate_historical_dividends(transactions: List[Transaction], dividends_by_ticker: Dict[str, List[Dict]]):
    """
    Calcula quanto foi recebido em cada evento de dividendo,
    considerando a quantidade exata de cotas que o investidor possuía
    até a data daquele provento.
    """
    # 1. Trata e ordena transações cronologicamente
    # Para transações sem data, assume a ordem de inserção
    parsed_txs = []
    default_dt = datetime(2020, 1, 1)

    for idx, tx in enumerate(transactions):
        dt = parse_date(tx.data) or default_dt
        parsed_txs.append((dt, idx, tx))

    # Ordena por data e índice original
    parsed_txs.sort(key=lambda x: (x[0], x[1]))

    all_payments = []
    monthly_stats = {}  # mes_ano -> {'total': float, 'ativos': set(), 'timestamp': int, 'investido_na_epoca': float}

    for ticker, div_list in dividends_by_ticker.items():
        for d in div_list:
            div_dt = d.get("dt") or parse_date(d.get("data"))
            if not div_dt:
                continue

            # Calcular posição da carteira até div_dt considerando compras, vendas e eventos corporativos
            qtd_por_ticker: Dict[str, float] = {}

            for tx_dt, _, tx in parsed_txs:
                if tx_dt > div_dt:
                    continue
                if tx.operacao == "compra":
                    qtd_por_ticker[tx.ticker] = qtd_por_ticker.get(tx.ticker, 0.0) + tx.quantidade
                elif tx.operacao == "venda":
                    nova_qtd = qtd_por_ticker.get(tx.ticker, 0.0) - tx.quantidade
                    qtd_por_ticker[tx.ticker] = 0.0 if nova_qtd <= 0.0001 else nova_qtd
                elif tx.operacao in ("desdobramento", "agrupamento"):
                    if tx.quantidade > 0 and tx.ticker in qtd_por_ticker:
                        qtd_por_ticker[tx.ticker] *= tx.quantidade
                elif tx.operacao == "conversao" and "->" in tx.ticker:
                    origem, destino = [p.strip().upper() for p in tx.ticker.split("->", 1)]
                    fator = tx.quantidade if tx.quantidade > 0 else 1.0
                    qtd_orig = qtd_por_ticker.get(origem, 0.0)
                    if qtd_orig > 0:
                        qtd_por_ticker[origem] = 0.0
                        qtd_por_ticker[destino] = qtd_por_ticker.get(destino, 0.0) + qtd_orig * fator

            qtd_na_epoca = qtd_por_ticker.get(ticker, 0.0)

            if qtd_na_epoca > 0:
                total_pago = qtd_na_epoca * d["amount"]
                mes_ano = d["mes_ano"]

                all_payments.append({
                    "data": d["data"],
                    "mes_ano": mes_ano,
                    "timestamp": d["timestamp"],
                    "ticker": ticker,
                    "qtd": qtd_na_epoca,
                    "unit": d["amount"],
                    "total": total_pago
                })

                if mes_ano not in monthly_stats:
                    monthly_stats[mes_ano] = {
                        "total": 0.0, 
                        "ativos": set(), 
                        "timestamp": d["timestamp"]
                    }
                monthly_stats[mes_ano]["total"] += total_pago
                monthly_stats[mes_ano]["ativos"].add(ticker)

    all_payments.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_payments, monthly_stats
