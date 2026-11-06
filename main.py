"""
Ponto de entrada principal para a Interface Gráfica Desktop do Invest.AI.
Uso: python main.py
"""

import os
import sys

_SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from invest_ai.ui.desktop_app import InvestAIApp


if __name__ == "__main__":
    app = InvestAIApp()
    app.mainloop()
