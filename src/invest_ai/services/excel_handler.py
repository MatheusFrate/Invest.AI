"""
Módulo para ler, salvar, editar e excluir movimentações no Excel (investimento.xlsx)
"""

import os
from datetime import datetime, date
import openpyxl
from typing import List, Tuple, Optional
from invest_ai.core.engine import Transaction
from invest_ai.config import DEFAULT_EXCEL_PATH


def normalizar_data_br(data_val: any) -> str:
    """
    Normaliza formatos de data (datetime, date, YYYY-MM-DD ou DD/MM/YYYY)
    para o formato padrão brasileiro DD/MM/AAAA.
    """
    if not data_val:
        return ""
    if isinstance(data_val, (datetime, date)):
        return data_val.strftime("%d/%m/%Y")

    val_str = str(data_val).strip()
    if not val_str:
        return ""

    # Se for YYYY-MM-DD (com ou sem horário)
    if "-" in val_str:
        data_pura = val_str.split()[0]
        partes = data_pura.split("-")
        if len(partes) == 3 and len(partes[0]) == 4:
            try:
                dt = datetime.strptime(data_pura, "%Y-%m-%d")
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass

    # Se já for DD/MM/YYYY (com ou sem horário)
    if "/" in val_str:
        data_pura = val_str.split()[0]
        partes = data_pura.split("/")
        if len(partes) == 3:
            try:
                dt = datetime.strptime(data_pura, "%d/%m/%Y")
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass

    return val_str


def find_duplicate_transaction_index(
    tx: Transaction,
    existing_transactions: List[Transaction],
) -> Optional[int]:
    """
    Retorna o índice da primeira transação em `existing_transactions` que
    corresponde a `tx` (ticker, operação, data normalizada DD/MM/AAAA, quantidade
    e valores), ou None se não houver correspondência.
    """
    tx_data_norm = normalizar_data_br(tx.data)
    tx_ticker = tx.ticker.strip().upper()
    tx_operacao = tx.operacao.strip().lower()

    for idx, ext in enumerate(existing_transactions):
        if ext.ticker.strip().upper() != tx_ticker:
            continue
        if ext.operacao.strip().lower() != tx_operacao:
            continue
        if normalizar_data_br(ext.data) != tx_data_norm:
            continue
        if abs(ext.quantidade - tx.quantidade) > 0.0001:
            continue
        # Tolerância de 0.005 absorve apenas ruído de ponto flutuante sem confundir diferenças de R$ 0,01
        valor_total_match = abs(ext.valor_total - tx.valor_total) <= 0.005
        valor_unit_match = abs(ext.valor_unitario - tx.valor_unitario) <= 0.005
        if valor_total_match or valor_unit_match:
            return idx

    return None


def is_duplicate_transaction(tx: Transaction, existing_transactions: List[Transaction]) -> bool:
    """
    Verifica se uma transação já existe em uma lista de transações da planilha.
    Compara ticker, operação, data normalizada (DD/MM/AAAA), quantidade e valores.
    """
    return find_duplicate_transaction_index(tx, existing_transactions) is not None


def load_transactions_from_excel(filepath: str = DEFAULT_EXCEL_PATH) -> List[Transaction]:
    if not os.path.exists(filepath):
        return []

    wb = openpyxl.load_workbook(filepath, data_only=True)
    
    target_sheet = None
    for name in wb.sheetnames:
        if 'movimenta' in name.lower():
            target_sheet = wb[name]
            break
    if target_sheet is None and len(wb.sheetnames) > 1:
        target_sheet = wb.sheetnames[1]
    elif target_sheet is None:
        target_sheet = wb.active

    transactions = []
    header = [str(c).lower().strip() if c else "" for c in next(target_sheet.iter_rows(values_only=True))]
    
    col_cota = 0
    col_qtd = 1
    col_total = 2
    col_unit = 3
    col_tag = 4
    col_operacao = 5
    col_data = 6 if len(header) > 6 else -1

    for row_idx, row in enumerate(target_sheet.iter_rows(values_only=True, min_row=2), 2):
        if not any(row):
            continue
        cota = str(row[col_cota]).strip() if row[col_cota] else ""
        if not cota or cota.lower() == 'cota':
            continue

        try:
            qtd = float(row[col_qtd]) if row[col_qtd] is not None else 0.0
            total = float(row[col_total]) if row[col_total] is not None else 0.0
            unit = float(row[col_unit]) if row[col_unit] is not None else (total / qtd if qtd else 0.0)
            tag = str(row[col_tag]).lower().strip() if len(row) > col_tag and row[col_tag] else "fii"
            operacao = str(row[col_operacao]).lower().strip() if len(row) > col_operacao and row[col_operacao] else "compra"
            
            if 'venda' in operacao:
                operacao = 'venda'
            elif 'desdobramento' in operacao or 'split' in operacao:
                operacao = 'desdobramento'
            elif 'agrupamento' in operacao or 'inplit' in operacao:
                operacao = 'agrupamento'
            elif 'conversao' in operacao or 'conversão' in operacao or 'incorporacao' in operacao or 'incorporação' in operacao:
                operacao = 'conversao'
            else:
                operacao = 'compra'

            if 'a' in tag and 'o' in tag:
                tag = 'ação'
            elif 'etf' in tag:
                tag = 'etf'
            elif 'bdr' in tag:
                tag = 'bdr'
            else:
                tag = 'fii'

            data_str = ""
            if col_data != -1 and len(row) > col_data and row[col_data] is not None:
                data_str = normalizar_data_br(row[col_data])

            tx = Transaction(
                id=row_idx,  # guarda o número da linha no Excel para edição/exclusão direta
                data=data_str,
                ticker=cota,
                tipo_ativo=tag,
                operacao=operacao,
                quantidade=qtd,
                valor_total=total,
                valor_unitario=unit
            )
            transactions.append(tx)
        except Exception as e:
            print(f"Erro ao ler linha {row_idx}: {e}")

    return transactions


def save_transaction_to_excel(
    tx: Transaction,
    filepath: str = DEFAULT_EXCEL_PATH,
    prevent_duplicates: bool = True
) -> bool:
    """
    Salva uma transação no Excel mantendo a data no formato DD/MM/AAAA.
    Se prevent_duplicates for True, evita duplicar operações idênticas na planilha.
    Retorna True se gravado, False se ignorado por duplicidade.
    """
    if prevent_duplicates and os.path.exists(filepath):
        existentes = load_transactions_from_excel(filepath)
        if is_duplicate_transaction(tx, existentes):
            return False

    if not os.path.exists(filepath):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "movimentações"
        ws.append(["Cota", "quantidade", "valor total", "valor da cota", "tag", "operação", "data"])
    else:
        wb = openpyxl.load_workbook(filepath)
        ws = _get_movimentacoes_sheet(wb)

    data_formatada = normalizar_data_br(tx.data)
    ws.append([
        tx.ticker.lower(),
        tx.quantidade,
        round(tx.valor_total, 2),
        round(tx.valor_unitario, 4),
        tx.tipo_ativo,
        tx.operacao,
        data_formatada
    ])
    wb.save(filepath)
    return True


def save_transactions_batch_to_excel(
    txs: List[Transaction],
    filepath: str = DEFAULT_EXCEL_PATH,
    prevent_duplicates: bool = True
) -> Tuple[int, int]:
    """
    Salva uma lista de transações em lote no Excel com formato DD/MM/AAAA.
    Faz verificação 1-para-1 contra as transações já existentes na planilha
    antes deste lote, preservando execuções parciais legítimas na mesma nota.
    Retorna: (total_salvas, total_duplicadas_ignoradas).
    """
    if not txs:
        return 0, 0

    if not os.path.exists(filepath):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "movimentações"
        ws.append(["Cota", "quantidade", "valor total", "valor da cota", "tag", "operação", "data"])
        existentes: List[Transaction] = []
    else:
        wb = openpyxl.load_workbook(filepath)
        ws = _get_movimentacoes_sheet(wb)
        existentes = load_transactions_from_excel(filepath) if prevent_duplicates else []

    existentes_restantes = list(existentes)
    salvas = 0
    duplicadas = 0

    for tx in txs:
        if prevent_duplicates:
            dup_idx = find_duplicate_transaction_index(tx, existentes_restantes)
            if dup_idx is not None:
                existentes_restantes.pop(dup_idx)
                duplicadas += 1
                continue

        data_formatada = normalizar_data_br(tx.data)
        ws.append([
            tx.ticker.lower(),
            tx.quantidade,
            round(tx.valor_total, 2),
            round(tx.valor_unitario, 4),
            tx.tipo_ativo,
            tx.operacao,
            data_formatada
        ])
        salvas += 1

    if salvas > 0:
        wb.save(filepath)

    return salvas, duplicadas


def normalizar_todas_datas_planilha(filepath: str = DEFAULT_EXCEL_PATH) -> int:
    """
    Higieniza a planilha de movimentações existente, convertendo quaisquer datas
    em formato YYYY-MM-DD para o formato padrão brasileiro DD/MM/AAAA.
    Retorna a quantidade de células corrigidas.
    """
    if not os.path.exists(filepath):
        return 0

    wb = openpyxl.load_workbook(filepath)
    ws = _get_movimentacoes_sheet(wb)

    header = [str(c).lower().strip() if c else "" for c in next(ws.iter_rows(values_only=True))]
    col_data_idx = -1
    for idx, h in enumerate(header, 1):
        if "data" in h:
            col_data_idx = idx
            break
    if col_data_idx == -1 and len(header) >= 7:
        col_data_idx = 7

    if col_data_idx == -1:
        return 0

    corrigidas = 0
    for row in range(2, ws.max_row + 1):
        cell = ws.cell(row=row, column=col_data_idx)
        val = cell.value
        if val is not None:
            val_str = str(val).strip()
            if "-" in val_str:
                norm = normalizar_data_br(val_str)
                if norm != val_str:
                    cell.value = norm
                    corrigidas += 1

    if corrigidas > 0:
        wb.save(filepath)

    return corrigidas


def update_transaction_in_excel(tx: Transaction, filepath: str = DEFAULT_EXCEL_PATH):
    """Atualiza a linha existente correspondente a tx.id no Excel."""
    if not os.path.exists(filepath) or not tx.id:
        return

    wb = openpyxl.load_workbook(filepath)
    ws = _get_movimentacoes_sheet(wb)

    row = tx.id
    ws.cell(row=row, column=1, value=tx.ticker.lower())
    ws.cell(row=row, column=2, value=tx.quantidade)
    ws.cell(row=row, column=3, value=round(tx.valor_total, 2))
    ws.cell(row=row, column=4, value=round(tx.valor_unitario, 4))
    ws.cell(row=row, column=5, value=tx.tipo_ativo)
    ws.cell(row=row, column=6, value=tx.operacao)
    ws.cell(row=row, column=7, value=normalizar_data_br(tx.data))

    wb.save(filepath)


def delete_transaction_from_excel(row_id: int, filepath: str = DEFAULT_EXCEL_PATH):
    """Exclui a linha no Excel e salva."""
    if not os.path.exists(filepath) or not row_id:
        return

    wb = openpyxl.load_workbook(filepath)
    ws = _get_movimentacoes_sheet(wb)
    ws.delete_rows(row_id)
    wb.save(filepath)


def _get_movimentacoes_sheet(wb):
    for name in wb.sheetnames:
        if 'movimenta' in name.lower():
            return wb[name]
    if len(wb.sheetnames) > 1:
        return wb.sheetnames[1]
    return wb.active


def load_paid_darfs(filepath: str = DEFAULT_EXCEL_PATH) -> dict:
    """
    Retorna dicionário com os DARFs pagos:
    { ('10/2026', 'fii'): {'valor': 20.0, 'data_pagamento': '13/10/2026'}, ... }
    """
    if not os.path.exists(filepath):
        return {}

    wb = openpyxl.load_workbook(filepath, data_only=True)
    if "darfs_pagos" not in wb.sheetnames:
        return {}

    ws = wb["darfs_pagos"]
    paid = {}
    for row in ws.iter_rows(values_only=True, min_row=2):
        if not any(row):
            continue
        try:
            mes = str(row[0]).strip()
            tipo = str(row[1]).strip().lower()
            valor = float(row[2]) if row[2] is not None else 0.0
            data_pgto = str(row[3]).strip() if len(row) > 3 and row[3] else ""
            paid[(mes, tipo)] = {"valor": valor, "data_pagamento": data_pgto}
        except Exception:
            pass
    return paid


def record_paid_darf(mes_ano: str, tipo_ativo: str, valor_pago: float, data_pagamento: str, filepath: str = DEFAULT_EXCEL_PATH):
    """
    Registra ou atualiza um pagamento de DARF na aba 'darfs_pagos'.
    """
    if not os.path.exists(filepath):
        wb = openpyxl.Workbook()
    else:
        wb = openpyxl.load_workbook(filepath)

    if "darfs_pagos" not in wb.sheetnames:
        ws = wb.create_sheet("darfs_pagos")
        ws.append(["Mês/Ano", "Tipo de Ativo", "Valor Pago", "Data do Pagamento"])
    else:
        ws = wb["darfs_pagos"]

    # Verifica se já existe esse mês e tipo
    found = False
    for row_idx, row in enumerate(ws.iter_rows(values_only=True, min_row=2), 2):
        if row and str(row[0]).strip() == mes_ano and str(row[1]).strip().lower() == tipo_ativo.lower():
            ws.cell(row=row_idx, column=3, value=round(valor_pago, 2))
            ws.cell(row=row_idx, column=4, value=data_pagamento)
            found = True
            break

    if not found:
        ws.append([mes_ano, tipo_ativo.lower(), round(valor_pago, 2), data_pagamento])

    wb.save(filepath)

