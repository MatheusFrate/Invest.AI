"""
Configurações e diretórios globais da aplicação Invest.AI.
"""

import os
import sys

# Se estiver rodando empacotado pelo PyInstaller (.exe), usa a pasta do executável
if getattr(sys, "frozen", False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    # src/invest_ai/config.py -> src/invest_ai -> src -> ROOT_DIR
    ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_EXCEL_PATH = os.path.join(DATA_DIR, "investimento.xlsx")
EXAMPLE_EXCEL_PATH = os.path.join(DATA_DIR, "investimento_exemplo.xlsx")


def get_active_excel_path() -> str:
    """
    Retorna o caminho da planilha principal. Se não existir mas houver a de exemplo,
    retorna a de exemplo como leitura inicial.
    """
    if os.path.exists(DEFAULT_EXCEL_PATH):
        return DEFAULT_EXCEL_PATH
    if os.path.exists(EXAMPLE_EXCEL_PATH):
        return EXAMPLE_EXCEL_PATH
    return DEFAULT_EXCEL_PATH
