"""
Ponto de entrada para a Interface de Terminal Interativa (CLI) do Invest.AI.
Uso: python cli.py
"""

import os
import sys

_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from invest_ai.ui.cli import main


if __name__ == "__main__":
    main()
