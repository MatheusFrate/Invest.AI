"""
Módulo para ler, salvar, editar e excluir movimentações no Excel (investimento.xlsx)
"""

import os
import openpyxl
from typing import List
from invest_ai.core.engine import Transaction
from invest_ai.config import DEFAULT_EXCEL_PATH


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
            else:
                operacao = 'compra'

            if 'a' in tag and 'o' in tag:
                tag = 'ação'
            elif 'etf' in tag:
                tag = 'etf'
            else:
                tag = 'fii'

            data_str = ""
            if col_data != -1 and len(row) > col_data and row[col_data]:
                data_str = str(row[col_data]).strip()

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


def save_transaction_to_excel(tx: Transaction, filepath: str = DEFAULT_EXCEL_PATH):
    if not os.path.exists(filepath):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "movimentações"
        ws.append(["Cota", "quantidade", "valor total", "valor da cota", "tag", "operação", "data"])
    else:
        wb = openpyxl.load_workbook(filepath)
        ws = _get_movimentacoes_sheet(wb)

    ws.append([
        tx.ticker.lower(),
        tx.quantidade,
        round(tx.valor_total, 2),
        round(tx.valor_unitario, 4),
        tx.tipo_ativo,
        tx.operacao,
        tx.data
    ])
    wb.save(filepath)


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
    ws.cell(row=row, column=7, value=tx.data)

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

