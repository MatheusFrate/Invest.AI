"""
Testes de renderização do Card de Transação Human-in-the-Loop na UI Desktop.
Verifica a aplicação de estilos e destaque visual de alerta de discrepância.
"""

from unittest.mock import patch, MagicMock
import pytest

ctk = pytest.importorskip("customtkinter")

# Valida se o ambiente possui servidor gráfico (display) disponível
# No GitHub Actions (Ubuntu/Linux) sem X11/xvfb, testes de GUI devem ser pulados
def _verificar_display_disponivel() -> bool:
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(
    not _verificar_display_disponivel(),
    reason="Ambiente headless sem display gráfico disponível (ex: CI Linux sem X11/xvfb)"
)

from invest_ai.agent.schemas import (
    TransactionSchema,
    BrokerageNoteSchema,
    CorporateEventSchema,
    TipoEventoCorporativo,
    TipoOperacao,
)
from invest_ai.ui.desktop_app import InvestAIApp, _sanitize_markdown, COPILOT_COLORS


def test_add_transaction_card_com_alerta_discrepancia():
    with patch("invest_ai.ui.desktop_app.normalizar_todas_datas_planilha", return_value=0), \
         patch.object(InvestAIApp, "load_data"), \
         patch.object(InvestAIApp, "refresh_quotes_async"):

        app = InvestAIApp()
        app.withdraw()

        try:
            tx_com_alerta = TransactionSchema(
                ticker="MXRF11",
                quantidade=3,
                valor_unitario=3.00,
                cotacao_mercado=9.80,
                alerta_discrepancia=(
                    "⚠️ Atenção: A cotação atual de MXRF11 na B3 é R$ 9,80. "
                    "O preço informado de R$ 3,00 apresenta um desvio de 69%."
                )
            )

            num_filhos_antes = len(app.chat_scroll.winfo_children())
            app._add_transaction_card(tx_com_alerta)
            filhos_depois = app.chat_scroll.winfo_children()

            assert len(filhos_depois) == num_filhos_antes + 1
            card = filhos_depois[-1]

            # Valida borda de atenção âmbar/amarelo
            assert card.cget("border_color") == "#f59e0b"
            assert card.cget("border_width") == 2

            # Valida presença do quadro de alerta com fundo escuro/âmbar
            card_filhos = card.winfo_children()
            alertas = [
                f for f in card_filhos
                if isinstance(f, ctk.CTkFrame) and f.cget("fg_color") == "#451a03"
            ]
            assert len(alertas) == 1
            alerta_frame = alertas[0]
            assert alerta_frame.cget("border_color") == "#f59e0b"

            # Valida texto do alerta dentro do frame
            labels_alerta = [
                lbl for lbl in alerta_frame.winfo_children()
                if isinstance(lbl, ctk.CTkLabel) and "Atenção: A cotação atual" in lbl.cget("text")
            ]
            assert len(labels_alerta) == 1
        finally:
            app.destroy()


def test_add_transaction_card_sem_alerta():
    with patch("invest_ai.ui.desktop_app.normalizar_todas_datas_planilha", return_value=0), \
         patch.object(InvestAIApp, "load_data"), \
         patch.object(InvestAIApp, "refresh_quotes_async"):

        app = InvestAIApp()
        app.withdraw()

        try:
            tx_sem_alerta = TransactionSchema(
                ticker="MXRF11",
                quantidade=3,
                valor_unitario=9.80,
                cotacao_mercado=9.80,
                alerta_discrepancia=None
            )

            num_filhos_antes = len(app.chat_scroll.winfo_children())
            app._add_transaction_card(tx_sem_alerta)
            filhos_depois = app.chat_scroll.winfo_children()

            assert len(filhos_depois) == num_filhos_antes + 1
            card = filhos_depois[-1]

            # Valida borda padrão azul
            assert card.cget("border_color") == "#3b82f6"
            assert card.cget("border_width") == 1

            # Valida ausência do quadro de alerta
            card_filhos = card.winfo_children()
            alertas = [
                f for f in card_filhos
                if isinstance(f, ctk.CTkFrame) and f.cget("fg_color") == "#451a03"
            ]
            assert len(alertas) == 0
        finally:
            app.destroy()


def test_sanitize_markdown_remove_formatacao():
    bruto = "## Resumo\n**MXRF11** com *rendimento* de `R$ 0,10`\n- Item 1\n* Item 2"
    limpo = _sanitize_markdown(bruto)
    assert "**" not in limpo
    assert "`" not in limpo
    assert "##" not in limpo
    assert "• Item 1" in limpo
    assert "• Item 2" in limpo


def test_add_corporate_event_card_e_thinking_indicator():
    with patch("invest_ai.ui.desktop_app.normalizar_todas_datas_planilha", return_value=0), \
         patch.object(InvestAIApp, "load_data"), \
         patch.object(InvestAIApp, "refresh_quotes_async"):

        app = InvestAIApp()
        app.withdraw()

        try:
            # Thinking indicator aparece e é removido corretamente
            app._show_thinking_indicator("Processando")
            assert app._thinking_card is not None
            assert app._thinking_card.winfo_exists()
            app._hide_thinking_indicator()
            assert app._thinking_card is None

            # Card de evento corporativo
            ev = CorporateEventSchema(
                tipo_evento=TipoEventoCorporativo.DESDOBRAMENTO,
                ticker_origem="PETR4",
                fator=2.0,
                data="10/05/2025",
            )
            antes = len(app.chat_scroll.winfo_children())
            app._add_corporate_event_card(ev)
            depois = app.chat_scroll.winfo_children()
            assert len(depois) == antes + 1
            card = depois[-1]
            assert card.cget("border_color") == COPILOT_COLORS["purple"]

            # Navegação destaca o botão Copiloto apenas quando ativo
            app.show_view("copiloto")
            assert app.btn_nav_copiloto.cget("fg_color") == COPILOT_COLORS["primary"]
            app.show_view("carteira")
            assert app.btn_nav_copiloto.cget("fg_color") == "transparent"
        finally:
            app.destroy()


def test_add_batch_brokerage_note_card_renderiza_lote():
    with patch("invest_ai.ui.desktop_app.normalizar_todas_datas_planilha", return_value=0), \
         patch.object(InvestAIApp, "load_data"), \
         patch.object(InvestAIApp, "refresh_quotes_async"):

        app = InvestAIApp()
        app.withdraw()

        try:
            nota = BrokerageNoteSchema(
                corretora="XP",
                data_pregao="15/05/2025",
                numero_nota="12345",
                total_custos_emolumentos=4.50,
                transacoes=[
                    TransactionSchema(
                        operacao=TipoOperacao.COMPRA,
                        ticker="MXRF11",
                        quantidade=10,
                        valor_unitario=9.80,
                        data="15/05/2025",
                    ),
                    TransactionSchema(
                        operacao=TipoOperacao.VENDA,
                        ticker="PETR4",
                        quantidade=5,
                        valor_unitario=38.00,
                        data="15/05/2025",
                    ),
                ],
            )
            antes = len(app.chat_scroll.winfo_children())
            app._add_batch_brokerage_note_card(nota)
            depois = app.chat_scroll.winfo_children()
            assert len(depois) == antes + 1
            card = depois[-1]
            assert card.cget("border_color") == COPILOT_COLORS["blue"]
            assert card.cget("border_width") == 2
        finally:
            app.destroy()
