"""
Invest.AI • Interface Gráfica Moderna com Copiloto PydanticAI Integrado.
Extensão do aplicativo de investimentos desktop com suporte a linguagem natural,
extração estruturada e simulação fiscal da B3.
"""

import os
import re
import time
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import customtkinter as ctk

from invest_ai.ui.base_window import InvestApp
from invest_ai.agent.deps import InvestContext
from invest_ai.agent.agent import (
    transaction_agent,
    assistant_agent,
    brokerage_note_agent,
    corporate_event_agent,
    resolver_modelo_padrao,
)
from invest_ai.agent.schemas import (
    TransactionSchema,
    BrokerageNoteSchema,
    CorporateEventSchema,
    TipoEventoCorporativo,
)
from invest_ai.services.excel_handler import (
    DEFAULT_EXCEL_PATH,
    save_transaction_to_excel,
    save_transactions_batch_to_excel,
    normalizar_todas_datas_planilha,
)
from invest_ai.services.pdf_extractor import extrair_texto_pdf
from invest_ai.services.irpf_exporter import exportar_guia_irpf_txt


# Tokens de design alinhados com base_window.py (UI_COLORS / UI_FONTS)
COPILOT_COLORS = {
    "bg_app": ("#f8fafc", "#0f172a"),
    "bg_sidebar": ("#ffffff", "#111827"),
    "bg_surface": ("#ffffff", "#1e293b"),
    "bg_surface_alt": ("#f1f5f9", "#243044"),
    "bg_hover": ("#e2e8f0", "#334155"),
    "border": ("#e2e8f0", "#334155"),
    "border_subtle": ("#cbd5e1", "#475569"),
    "text_primary": ("#0f172a", "#f8fafc"),
    "text_secondary": ("#475569", "#94a3b8"),
    "text_muted": "#64748b",
    "primary": "#6366f1",
    "primary_hover": "#4f46e5",
    "primary_tint": ("#eef2ff", "#1e1b4b"),
    "primary_border": ("#c7d2fe", "#4338ca"),
    "primary_text": ("#4f46e5", "#a5b4fc"),
    "blue": "#3b82f6",
    "blue_hover": "#2563eb",
    "teal": "#0d9488",
    "teal_hover": "#0f766e",
    "purple": "#8b5cf6",
    "purple_hover": "#7c3aed",
    "purple_tint": ("#f5f3ff", "#2e1065"),
    "purple_text": ("#7c3aed", "#c4b5fd"),
    "success": "#10b981",
    "success_hover": "#059669",
    "success_text": ("#059669", "#34d399"),
    "success_tint": ("#ecfdf5", "#064e3b"),
    "danger": "#ef4444",
    "danger_text": ("#dc2626", "#f87171"),
    "danger_tint": ("#fef2f2", "#450a0a"),
    "warning": "#f59e0b",
    "warning_text": ("#d97706", "#fbbf24"),
    "warning_tint": "#451a03",
    "info_tint": ("#eff6ff", "#172554"),
    "info_text": ("#2563eb", "#60a5fa"),
}


def _sanitize_markdown(text: str) -> str:
    """Remove marcações Markdown para exibição limpa em componentes CTkLabel."""
    if not text:
        return ""
    cleaned = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
    cleaned = re.sub(r"`(.*?)`", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[-*]\s+", "• ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


class InvestAIApp(InvestApp):
    """
    Aplicativo Desktop Invest.AI estendido com aba do Copiloto PydanticAI.
    """

    def __init__(self):
        super().__init__()
        self.title("Invest.AI • Copiloto de Investimentos & DARF (B3)")

        # Contexto compartilhado para o agente PydanticAI
        self.ai_context = InvestContext(
            excel_path=DEFAULT_EXCEL_PATH,
            engine=self.engine,
        )
        self.ai_context._carteira_carregada = True

        self._thinking_card = None
        self._thinking_after_id = None
        self._thinking_dots = 0
        self._is_processing_ai = False

        self._reorganize_sidebar_for_ai()
        self._add_copiloto_view()

        # Higieniza datas antigas YYYY-MM-DD na planilha para DD/MM/AAAA se houver
        corrigidas = normalizar_todas_datas_planilha(DEFAULT_EXCEL_PATH)
        if corrigidas > 0:
            self.load_data()

        # Abre diretamente na tela do Copiloto IA por padrão
        self.show_view("copiloto")

    def _font(self, size: int, weight: str = "normal", slant: str = "roman") -> ctk.CTkFont:
        return ctk.CTkFont(family="Segoe UI", size=size, weight=weight, slant=slant)

    def _reorganize_sidebar_for_ai(self):
        """Atualiza a barra lateral para incluir o botão do Copiloto IA no topo."""
        for child in self.sidebar_frame.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                txt = str(child.cget("text") or "")
                if "InvestDARF" in txt or "Invest" in txt:
                    child.configure(text="🤖 Invest.AI")
                    break

        self.btn_nav_copiloto = ctk.CTkButton(
            self.sidebar_frame,
            text="🤖 Copiloto IA",
            command=lambda: self.show_view("copiloto"),
            height=40,
            corner_radius=8,
            anchor="w",
            font=self._font(13, "bold"),
            fg_color=COPILOT_COLORS["primary"],
            hover_color=COPILOT_COLORS["primary_hover"],
            text_color="#ffffff",
        )
        self.btn_nav_copiloto.grid(row=1, column=0, padx=16, pady=(0, 6), sticky="ew")

        nav_buttons = [
            self.btn_nav_carteira,
            self.btn_nav_vendas,
            self.btn_nav_proventos,
            self.btn_nav_rentabilidade,
            self.btn_nav_nova,
            self.btn_nav_historico,
        ]
        for idx, btn in enumerate(nav_buttons, start=2):
            btn.grid(row=idx, column=0, padx=16, pady=4, sticky="ew")

    def show_view(self, name: str):
        """Alterna entre as telas e mantém o destaque visual do botão Copiloto IA."""
        super().show_view(name)
        if hasattr(self, "btn_nav_copiloto"):
            if name == "copiloto":
                self.btn_nav_copiloto.configure(
                    fg_color=COPILOT_COLORS["primary"],
                    hover_color=COPILOT_COLORS["primary_hover"],
                    text_color="#ffffff",
                )
            else:
                self.btn_nav_copiloto.configure(
                    fg_color="transparent",
                    hover_color=COPILOT_COLORS["bg_hover"],
                    text_color=COPILOT_COLORS["text_primary"],
                )

    def _add_copiloto_view(self):
        """Cria e adiciona a view do Copiloto IA ao dicionário de views."""
        self.copiloto_view = self._create_copiloto_view()
        self.views["copiloto"] = self.copiloto_view

    def _create_copiloto_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        # Cabeçalho do Copiloto IA
        header_frame = ctk.CTkFrame(
            frame,
            fg_color=COPILOT_COLORS["bg_surface"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=12,
        )
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header_frame.grid_columnconfigure(0, weight=1)

        modelo = resolver_modelo_padrao()
        nome_mod = modelo if isinstance(modelo, str) else getattr(modelo, "model_name", type(modelo).__name__)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🤖 Copiloto Invest.AI",
            font=self._font(20, "bold"),
            text_color=COPILOT_COLORS["text_primary"],
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, sticky="w", padx=(16, 8), pady=(12, 0))

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text=f"PydanticAI • {nome_mod}",
            font=self._font(11),
            text_color=COPILOT_COLORS["text_secondary"],
            anchor="w",
        )
        subtitle_lbl.grid(row=1, column=0, sticky="w", padx=(16, 8), pady=(2, 12))

        actions_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=1, rowspan=2, padx=(8, 16), pady=12, sticky="e")

        self.btn_clear_chat = ctk.CTkButton(
            actions_frame,
            text="🗑️ Limpar",
            font=self._font(12, "bold"),
            fg_color=COPILOT_COLORS["bg_surface_alt"],
            hover_color=COPILOT_COLORS["bg_hover"],
            text_color=COPILOT_COLORS["text_secondary"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            height=36,
            width=88,
            corner_radius=8,
            command=self._clear_chat,
        )
        self.btn_clear_chat.pack(side="left", padx=(0, 8))

        self.btn_export_irpf = ctk.CTkButton(
            actions_frame,
            text="💾 Exportar IRPF (.txt)",
            font=self._font(12, "bold"),
            fg_color=COPILOT_COLORS["teal"],
            hover_color=COPILOT_COLORS["teal_hover"],
            text_color="#ffffff",
            height=36,
            corner_radius=8,
            command=self._on_export_irpf_txt,
        )
        self.btn_export_irpf.pack(side="left", padx=(0, 8))

        self.btn_import_pdf = ctk.CTkButton(
            actions_frame,
            text="📄 Importar Nota (PDF)",
            font=self._font(12, "bold"),
            fg_color=COPILOT_COLORS["blue"],
            hover_color=COPILOT_COLORS["blue_hover"],
            text_color="#ffffff",
            height=36,
            corner_radius=8,
            command=self._on_import_brokerage_note,
        )
        self.btn_import_pdf.pack(side="left")

        # Área de mensagens do chat
        self.chat_scroll = ctk.CTkScrollableFrame(
            frame,
            corner_radius=12,
            fg_color=COPILOT_COLORS["bg_surface"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
        )
        self.chat_scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        self._add_welcome_message()

        # Sugestões rápidas em duas linhas para evitar corte em janelas menores
        chips_section = ctk.CTkFrame(frame, fg_color="transparent")
        chips_section.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        row1 = ctk.CTkFrame(chips_section, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))
        row2 = ctk.CTkFrame(chips_section, fg_color="transparent")
        row2.pack(fill="x")

        sugestoes = [
            ("Comprei 100 MXRF11 a 9,45", "Comprei 100 MXRF11 a 9,45", False, row1),
            ("Se eu vender 20 PETR4 pago DARF?", "Se eu vender 20 PETR4 pago DARF?", False, row1),
            ("Qual o meu preço médio de MXRF11?", "Qual o meu preço médio de MXRF11?", False, row1),
            ("Quais ações eu tenho na carteira?", "Quais ações eu tenho na carteira?", False, row2),
            ("📋 Guia IRPF (Ano Anterior)", "Como devo declarar meus ativos no IRPF do ano passado?", True, row2),
        ]
        for label, prompt_text, auto_send, target_row in sugestoes:
            cmd = (
                (lambda p=prompt_text: self._enviar_sugestao_rapida(p))
                if auto_send
                else (lambda p=prompt_text: self._set_input_text(p))
            )
            btn_chip = ctk.CTkButton(
                target_row,
                text=label,
                height=28,
                corner_radius=14,
                font=self._font(11),
                fg_color=COPILOT_COLORS["bg_surface_alt"],
                hover_color=COPILOT_COLORS["bg_hover"],
                text_color=COPILOT_COLORS["text_primary"],
                border_width=1,
                border_color=COPILOT_COLORS["border"],
                command=cmd,
            )
            btn_chip.pack(side="left", padx=(0, 8))

        # Barra de entrada moderna
        input_frame = ctk.CTkFrame(
            frame,
            fg_color=COPILOT_COLORS["bg_surface"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=12,
        )
        input_frame.grid(row=3, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry_ai_prompt = ctk.CTkEntry(
            input_frame,
            placeholder_text="Digite sua operação ou dúvida (ex: 'Comprei 50 ações de PETR4 a 38,50')...",
            height=44,
            border_width=0,
            fg_color="transparent",
            text_color=COPILOT_COLORS["text_primary"],
            placeholder_text_color=COPILOT_COLORS["text_muted"],
            font=self._font(13),
        )
        self.entry_ai_prompt.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=4)
        self.entry_ai_prompt.bind("<Return>", lambda e: self._on_send_prompt())

        self.btn_send_prompt = ctk.CTkButton(
            input_frame,
            text="Enviar 🚀",
            width=112,
            height=36,
            corner_radius=8,
            font=self._font(13, "bold"),
            fg_color=COPILOT_COLORS["primary"],
            hover_color=COPILOT_COLORS["primary_hover"],
            text_color="#ffffff",
            command=self._on_send_prompt,
        )
        self.btn_send_prompt.grid(row=0, column=1, padx=(0, 8), pady=4)

        return frame

    def _add_welcome_message(self):
        self._add_bot_message(
            "Olá! Eu sou o seu Copiloto Invest.AI.\n\n"
            "• Importar Notas: Clique em '📄 Importar Nota (PDF)' no topo para ler notas da B3.\n"
            "• Registrar Aporte: Digite algo como 'Comprei 100 cotas de MXRF11 a 9,45 hoje na XP'.\n"
            "• Simular DARF: Pergunte 'Se eu vender 30 ações de PETR4 a R$ 45,00 pago imposto?'.\n"
            "• Consultar Carteira: Pergunte 'Qual é o meu preço médio em PETR4?'."
        )

    def _clear_chat(self):
        """Limpa o histórico visual do chat e restaura a mensagem de boas-vindas."""
        self._hide_thinking_indicator()
        for child in list(self.chat_scroll.winfo_children()):
            child.destroy()
        self._add_welcome_message()

    def _set_input_text(self, text: str):
        self.entry_ai_prompt.delete(0, tk.END)
        self.entry_ai_prompt.insert(0, text)
        self.entry_ai_prompt.focus()

    def _enviar_sugestao_rapida(self, text: str):
        """Preenche o campo de entrada e envia automaticamente a pergunta."""
        self._set_input_text(text)
        self._on_send_prompt()

    def _scroll_chat_to_bottom(self):
        self.chat_scroll.after(
            80,
            lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0)
            if self.chat_scroll.winfo_exists()
            else None,
        )

    def _add_user_message(self, text: str):
        """Adiciona bolha de mensagem do usuário alinhada à direita."""
        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)

        card = ctk.CTkFrame(
            row,
            fg_color=COPILOT_COLORS["primary_tint"],
            border_width=1,
            border_color=COPILOT_COLORS["primary_border"],
            corner_radius=12,
        )
        card.pack(side="right", anchor="e", padx=(60, 0))

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(10, 4))

        lbl_user = ctk.CTkLabel(
            top_row,
            text="Você",
            font=self._font(11, "bold"),
            text_color=COPILOT_COLORS["primary_text"],
        )
        lbl_user.pack(side="left")

        lbl_time = ctk.CTkLabel(
            top_row,
            text=datetime.now().strftime("%H:%M"),
            font=self._font(10),
            text_color=COPILOT_COLORS["text_muted"],
        )
        lbl_time.pack(side="right", padx=(12, 0))

        lbl_msg = ctk.CTkLabel(
            card,
            text=text,
            font=self._font(13),
            text_color=COPILOT_COLORS["text_primary"],
            wraplength=620,
            justify="left",
        )
        lbl_msg.pack(anchor="w", padx=14, pady=(0, 10))

        self._scroll_chat_to_bottom()

    def _add_bot_message(self, text: str):
        """Adiciona bolha de mensagem do assistente em texto limpo e legível."""
        texto_limpo = _sanitize_markdown(text)

        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)

        card = ctk.CTkFrame(
            row,
            fg_color=COPILOT_COLORS["bg_surface_alt"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=12,
        )
        card.pack(side="left", anchor="w", fill="x", expand=True, padx=(0, 48))

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(10, 4))

        lbl_bot = ctk.CTkLabel(
            top_row,
            text="🤖 Invest.AI",
            font=self._font(11, "bold"),
            text_color=COPILOT_COLORS["success_text"],
        )
        lbl_bot.pack(side="left")

        lbl_time = ctk.CTkLabel(
            top_row,
            text=datetime.now().strftime("%H:%M"),
            font=self._font(10),
            text_color=COPILOT_COLORS["text_muted"],
        )
        lbl_time.pack(side="left", padx=(8, 0))

        if len(texto_limpo) > 300:
            btn_copy = ctk.CTkButton(
                top_row,
                text="📋 Copiar texto",
                font=self._font(11),
                fg_color=COPILOT_COLORS["bg_surface"],
                hover_color=COPILOT_COLORS["bg_hover"],
                text_color=COPILOT_COLORS["text_secondary"],
                border_width=1,
                border_color=COPILOT_COLORS["border"],
                height=24,
                width=110,
                corner_radius=6,
            )
            btn_copy.configure(
                command=lambda t=texto_limpo, b=btn_copy: self._copy_to_clipboard(t, b)
            )
            btn_copy.pack(side="right")

        lbl_msg = ctk.CTkLabel(
            card,
            text=texto_limpo,
            font=self._font(13),
            text_color=COPILOT_COLORS["text_primary"],
            wraplength=660,
            justify="left",
        )
        lbl_msg.pack(anchor="w", padx=14, pady=(0, 10))

        self._scroll_chat_to_bottom()

    def _show_thinking_indicator(self, base_text: str = "Analisando sua solicitação"):
        """Exibe indicador animado de processamento no chat."""
        self._hide_thinking_indicator()
        self._thinking_dots = 1

        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)

        card = ctk.CTkFrame(
            row,
            fg_color=COPILOT_COLORS["bg_surface_alt"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=12,
        )
        card.pack(side="left", anchor="w")

        lbl = ctk.CTkLabel(
            card,
            text=f"⏳ {base_text}.",
            font=self._font(12, slant="italic"),
            text_color=COPILOT_COLORS["text_secondary"],
        )
        lbl.pack(padx=14, pady=10)

        self._thinking_card = row
        self._thinking_label = lbl
        self._thinking_base_text = base_text
        self._scroll_chat_to_bottom()
        self._thinking_after_id = self.after(380, self._animate_thinking_indicator)

    def _animate_thinking_indicator(self):
        if not self._thinking_card or not self._thinking_card.winfo_exists():
            return
        self._thinking_dots = (self._thinking_dots % 3) + 1
        dots = "." * self._thinking_dots
        if self._thinking_label.winfo_exists():
            self._thinking_label.configure(text=f"⏳ {self._thinking_base_text}{dots}")
        self._thinking_after_id = self.after(380, self._animate_thinking_indicator)

    def _hide_thinking_indicator(self):
        """Remove o indicador de pensamento do chat, se ativo."""
        if self._thinking_after_id is not None:
            try:
                self.after_cancel(self._thinking_after_id)
            except Exception:
                pass
            self._thinking_after_id = None
        if self._thinking_card is not None:
            try:
                if self._thinking_card.winfo_exists():
                    self._thinking_card.destroy()
            except Exception:
                pass
            self._thinking_card = None

    def _copy_to_clipboard(self, texto: str, button: ctk.CTkButton):
        """Copia o texto da bolha para a área de transferência e exibe feedback breve."""
        self.clipboard_clear()
        self.clipboard_append(texto)
        button.configure(text="✓ Copiado!")
        self.after(
            2000,
            lambda: button.configure(text="📋 Copiar texto") if button.winfo_exists() else None,
        )

    def _create_hitl_card_shell(
        self,
        border_color: str,
        border_width: int,
        title_text: str,
        title_color,
        badge_text: str,
        badge_fg,
        badge_text_color,
    ) -> ctk.CTkFrame:
        """Cria o container padrão e cabeçalho com badge de status para cards Human-in-the-Loop."""
        card = ctk.CTkFrame(
            self.chat_scroll,
            fg_color=COPILOT_COLORS["bg_surface"],
            border_color=border_color,
            border_width=border_width,
            corner_radius=12,
        )
        card.pack(fill="x", padx=12, pady=8)

        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=16, pady=(14, 8))

        lbl_title = ctk.CTkLabel(
            header_row,
            text=title_text,
            font=self._font(14, "bold"),
            text_color=title_color,
            anchor="w",
        )
        lbl_title.pack(side="left", fill="x", expand=True)

        badge = ctk.CTkFrame(
            header_row,
            fg_color=badge_fg,
            corner_radius=6,
        )
        badge.pack(side="right", padx=(8, 0))

        lbl_badge = ctk.CTkLabel(
            badge,
            text=badge_text,
            font=self._font(10, "bold"),
            text_color=badge_text_color,
        )
        lbl_badge.pack(padx=8, pady=3)

        return card

    def _populate_kv_grid(self, parent: ctk.CTkFrame, rows: list[tuple[str, str, str | None]]):
        """Popula uma grade estruturada de pares chave/valor dentro de um card."""
        grid_box = ctk.CTkFrame(
            parent,
            fg_color=COPILOT_COLORS["bg_surface_alt"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=8,
        )
        grid_box.pack(fill="x", padx=16, pady=(0, 12))
        grid_box.grid_columnconfigure(1, weight=1)

        for idx, (label, value, value_color) in enumerate(rows):
            pad_top = 10 if idx == 0 else 3
            pad_bot = 10 if idx == len(rows) - 1 else 3

            lbl_k = ctk.CTkLabel(
                grid_box,
                text=label,
                font=self._font(12),
                text_color=COPILOT_COLORS["text_secondary"],
                anchor="w",
            )
            lbl_k.grid(row=idx, column=0, sticky="w", padx=(12, 16), pady=(pad_top, pad_bot))

            lbl_v = ctk.CTkLabel(
                grid_box,
                text=value,
                font=self._font(13, "bold"),
                text_color=value_color or COPILOT_COLORS["text_primary"],
                anchor="w",
                justify="left",
                wraplength=460,
            )
            lbl_v.grid(row=idx, column=1, sticky="w", padx=(0, 12), pady=(pad_top, pad_bot))

    def _add_card_action_buttons(
        self,
        card: ctk.CTkFrame,
        confirm_text: str,
        confirm_fg: str,
        confirm_hover: str,
        on_confirm,
        cancel_text: str = "✖ Cancelar",
    ):
        """Adiciona os botões de confirmação e cancelamento no rodapé do card."""
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 14))

        btn_confirmar = ctk.CTkButton(
            btn_frame,
            text=confirm_text,
            font=self._font(12, "bold"),
            fg_color=confirm_fg,
            hover_color=confirm_hover,
            text_color="#ffffff",
            height=34,
            corner_radius=8,
            command=on_confirm,
        )
        btn_confirmar.pack(side="left", padx=(0, 10))

        btn_descartar = ctk.CTkButton(
            btn_frame,
            text=cancel_text,
            font=self._font(12),
            fg_color="transparent",
            hover_color=COPILOT_COLORS["bg_hover"],
            text_color=COPILOT_COLORS["text_secondary"],
            border_width=1,
            border_color=COPILOT_COLORS["border_subtle"],
            height=34,
            corner_radius=8,
            command=lambda c=card: c.destroy(),
        )
        btn_descartar.pack(side="left")

    def _add_transaction_card(self, tx: TransactionSchema):
        """Adiciona card estruturado para confirmação de transação com Human-in-the-Loop."""
        has_alerta = bool(tx.alerta_discrepancia)
        border_color = COPILOT_COLORS["warning"] if has_alerta else COPILOT_COLORS["blue"]
        border_width = 2 if has_alerta else 1
        op_color = COPILOT_COLORS["success"] if tx.operacao.value == "compra" else COPILOT_COLORS["danger"]

        badge_text = "⚠️ REVISÃO DE PREÇO" if has_alerta else "AGUARDANDO CONFIRMAÇÃO"
        badge_fg = COPILOT_COLORS["warning_tint"] if has_alerta else COPILOT_COLORS["info_tint"]
        badge_txt_color = "#fef3c7" if has_alerta else COPILOT_COLORS["info_text"]

        card = self._create_hitl_card_shell(
            border_color=border_color,
            border_width=border_width,
            title_text=f"📝 Operação Identificada: {tx.operacao.value.upper()}",
            title_color=op_color,
            badge_text=badge_text,
            badge_fg=badge_fg,
            badge_text_color=badge_txt_color,
        )

        rows = [
            ("Ativo", f"{tx.ticker} ({tx.tipo_ativo.value.upper()})", None),
            ("Quantidade", f"{tx.quantidade:.2f} cotas/ações", None),
            ("Preço Unitário", f"R$ {tx.valor_unitario:.2f}", None),
            ("Valor Total", f"R$ {tx.valor_total:.2f}", op_color),
            ("Data", str(tx.data), None),
        ]
        if tx.cotacao_mercado is not None:
            rows.append(("Cotação Ref. B3", f"R$ {tx.cotacao_mercado:.2f}", None))
        if tx.corretora:
            rows.append(("Corretora", tx.corretora, None))

        self._populate_kv_grid(card, rows)

        if has_alerta:
            alerta_frame = ctk.CTkFrame(
                card,
                fg_color="#451a03",
                border_color="#f59e0b",
                border_width=1,
                corner_radius=8,
            )
            alerta_frame.pack(fill="x", padx=16, pady=(0, 12))

            lbl_alerta = ctk.CTkLabel(
                alerta_frame,
                text=_sanitize_markdown(tx.alerta_discrepancia),
                font=self._font(12, "bold"),
                text_color="#fef3c7",
                wraplength=520,
                justify="left",
            )
            lbl_alerta.pack(anchor="w", padx=12, pady=10)

        self._add_card_action_buttons(
            card=card,
            confirm_text="✔ Confirmar e Gravar na Planilha",
            confirm_fg=COPILOT_COLORS["success"],
            confirm_hover=COPILOT_COLORS["success_hover"],
            on_confirm=lambda c=card, t=tx: self._confirm_and_save_transaction(c, t),
            cancel_text="✖ Cancelar",
        )

        self._scroll_chat_to_bottom()

    def _confirm_and_save_transaction(self, card_widget, tx: TransactionSchema):
        """Salva a transação confirmada pelo usuário no Excel e atualiza a carteira."""
        try:
            engine_tx = tx.to_engine_transaction()
            foi_salvo = save_transaction_to_excel(engine_tx, DEFAULT_EXCEL_PATH, prevent_duplicates=True)

            card_widget.destroy()

            if not foi_salvo:
                self._add_bot_message(
                    f"⚠️ Operação NÃO gravada pois já existe uma movimentação idêntica na planilha:\n\n"
                    f"• {tx.operacao.value.upper()} de {tx.quantidade:g} {tx.ticker} em {tx.data} no valor de R$ {tx.valor_total:.2f}.\n\n"
                    f"Linhas duplicadas são bloqueadas para manter a apuração fiscal e o preço médio corretos."
                )
                return

            self.load_data()
            self.refresh_quotes_async()

            self._add_bot_message(
                f"OK! Operação registrada com sucesso!\n\n"
                f"Foram gravadas {tx.quantidade:g} de {tx.ticker} na sua planilha (Data: {tx.data}).\n"
                f"Sua carteira e preço médio já foram atualizados. Visite a aba Carteira Atual para conferir!"
            )
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível gravar a operação:\n{e}")

    def _add_corporate_event_card(self, ev: CorporateEventSchema):
        """Adiciona card estruturado para confirmação de Evento Corporativo (Human-in-the-Loop)."""
        titulos = {
            TipoEventoCorporativo.DESDOBRAMENTO: "DESDOBRAMENTO (SPLIT)",
            TipoEventoCorporativo.AGRUPAMENTO: "AGRUPAMENTO (INPLIT)",
            TipoEventoCorporativo.CONVERSAO: "CONVERSÃO / INCORPORAÇÃO DE TICKER",
        }

        card = self._create_hitl_card_shell(
            border_color=COPILOT_COLORS["purple"],
            border_width=1,
            title_text=f"🔄 Evento Corporativo: {titulos.get(ev.tipo_evento, ev.tipo_evento.value.upper())}",
            title_color=COPILOT_COLORS["purple_text"],
            badge_text="EVENTO CORPORATIVO",
            badge_fg=COPILOT_COLORS["purple_tint"],
            badge_text_color=COPILOT_COLORS["purple_text"],
        )

        if ev.tipo_evento == TipoEventoCorporativo.CONVERSAO:
            alvo_label = "Origem -> Destino"
            alvo_val = f"{ev.ticker_origem} -> {ev.ticker_destino} ({ev.tipo_ativo.value.upper()})"
        else:
            alvo_label = "Ativo"
            alvo_val = f"{ev.ticker_origem} ({ev.tipo_ativo.value.upper()})"

        rows = [
            (alvo_label, alvo_val, None),
            ("Fator de Multiplicação", f"{ev.fator:g}x", COPILOT_COLORS["purple_text"]),
            ("Data do Evento", str(ev.data), None),
            ("Impacto Fiscal (DARF)", "Isento (custo total de aquisição preservado)", COPILOT_COLORS["success_text"]),
        ]
        if ev.observacao:
            rows.append(("Observação", _sanitize_markdown(ev.observacao), None))

        self._populate_kv_grid(card, rows)

        self._add_card_action_buttons(
            card=card,
            confirm_text="✔ Confirmar e Gravar na Planilha",
            confirm_fg=COPILOT_COLORS["purple"],
            confirm_hover=COPILOT_COLORS["purple_hover"],
            on_confirm=lambda c=card, e=ev: self._confirm_and_save_corporate_event(c, e),
            cancel_text="✖ Cancelar",
        )

        self._scroll_chat_to_bottom()

    def _confirm_and_save_corporate_event(self, card_widget, ev: CorporateEventSchema):
        """Salva o evento corporativo confirmado pelo usuário no Excel e atualiza a carteira."""
        try:
            engine_tx = ev.to_engine_transaction()
            foi_salvo = save_transaction_to_excel(engine_tx, DEFAULT_EXCEL_PATH, prevent_duplicates=True)

            card_widget.destroy()

            if not foi_salvo:
                self._add_bot_message(
                    f"⚠️ Evento corporativo NÃO gravado pois já existe um registro idêntico na planilha:\n\n"
                    f"• {engine_tx.operacao.upper()} de {engine_tx.ticker} (fator {ev.fator:g}x) em {ev.data}."
                )
                return

            self.load_data()
            self.refresh_quotes_async()

            self._add_bot_message(
                f"OK! Evento corporativo registrado com sucesso!\n\n"
                f"• {engine_tx.operacao.upper()}: {engine_tx.ticker} (Fator: {ev.fator:g}x | Data: {ev.data}).\n"
                f"Sua custódia e preço médio já foram recalculados mantendo o custo total de aquisição."
            )
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível gravar o evento corporativo:\n{e}")

    def _add_batch_brokerage_note_card(self, nota: BrokerageNoteSchema):
        """Adiciona card estruturado para confirmação em lote de Nota de Corretagem (Human-in-the-Loop)."""
        card = self._create_hitl_card_shell(
            border_color=COPILOT_COLORS["blue"],
            border_width=2,
            title_text="📄 Nota de Corretagem B3 (Confirmação em Lote)",
            title_color=COPILOT_COLORS["info_text"],
            badge_text=f"{len(nota.transacoes)} OPERAÇÕES",
            badge_fg=COPILOT_COLORS["info_tint"],
            badge_text_color=COPILOT_COLORS["info_text"],
        )

        rows = [
            ("Corretora", nota.corretora or "Não identificada", None),
            ("Data Pregão", str(nota.data_pregao), None),
            ("Nr. Nota", nota.numero_nota or "N/A", None),
            ("Custos e Emolumentos", f"R$ {nota.total_custos_emolumentos:.2f}", None),
        ]
        self._populate_kv_grid(card, rows)

        if nota.total_custos_emolumentos > 0:
            valor_fmt = f"{nota.total_custos_emolumentos:.2f}".replace(".", ",")
            rateio_banner = ctk.CTkFrame(
                card,
                fg_color="#451a03",
                border_color=COPILOT_COLORS["warning"],
                border_width=1,
                corner_radius=8,
            )
            rateio_banner.pack(fill="x", padx=16, pady=(0, 12))

            lbl_rateio = ctk.CTkLabel(
                rateio_banner,
                text=(
                    f"Custos de R$ {valor_fmt} serão rateados proporcionalmente "
                    f"(soma nas compras / deduz nas vendas conforme RFB)."
                ),
                font=self._font(11, "bold"),
                text_color="#fef3c7",
                justify="left",
                wraplength=520,
            )
            lbl_rateio.pack(anchor="w", padx=12, pady=8)

        # Lista compacta com as operações encontradas
        ops_container = ctk.CTkFrame(
            card,
            fg_color=COPILOT_COLORS["bg_surface_alt"],
            border_width=1,
            border_color=COPILOT_COLORS["border"],
            corner_radius=8,
        )
        ops_container.pack(fill="x", padx=16, pady=(0, 12))

        lbl_ops_title = ctk.CTkLabel(
            ops_container,
            text=f"Operações Identificadas ({len(nota.transacoes)}):",
            font=self._font(12, "bold"),
            text_color=COPILOT_COLORS["text_secondary"],
        )
        lbl_ops_title.pack(anchor="w", padx=12, pady=(10, 6))

        for tx in nota.transacoes:
            is_compra = tx.operacao.value == "compra"
            op_cor = COPILOT_COLORS["success_text"] if is_compra else COPILOT_COLORS["danger_text"]
            op_bg = COPILOT_COLORS["success_tint"] if is_compra else COPILOT_COLORS["danger_tint"]

            linha_frame = ctk.CTkFrame(ops_container, fg_color="transparent")
            linha_frame.pack(fill="x", padx=12, pady=3)

            badge_op = ctk.CTkFrame(linha_frame, fg_color=op_bg, corner_radius=5)
            badge_op.pack(side="left")

            lbl_badge = ctk.CTkLabel(
                badge_op,
                text=tx.operacao.value.upper(),
                font=self._font(10, "bold"),
                text_color=op_cor,
                width=58,
            )
            lbl_badge.pack(padx=6, pady=2)

            detalhe_op = (
                f"{tx.quantidade:g} {tx.ticker} ({tx.tipo_ativo.value.upper()}) @ "
                f"R$ {tx.valor_unitario:.2f}  →  Total: R$ {tx.valor_total:.2f}"
            )
            lbl_detalhe = ctk.CTkLabel(
                linha_frame,
                text=detalhe_op,
                font=self._font(12),
                text_color=COPILOT_COLORS["text_primary"],
                anchor="w",
            )
            lbl_detalhe.pack(side="left", padx=(10, 0))

        ctk.CTkFrame(ops_container, height=8, fg_color="transparent").pack()

        self._add_card_action_buttons(
            card=card,
            confirm_text=f"✔ Confirmar e Gravar Todas na Planilha ({len(nota.transacoes)})",
            confirm_fg=COPILOT_COLORS["success"],
            confirm_hover=COPILOT_COLORS["success_hover"],
            on_confirm=lambda c=card, n=nota: self._confirm_and_save_brokerage_note(c, n),
            cancel_text="✖ Descartar",
        )

        self._scroll_chat_to_bottom()

    def _confirm_and_save_brokerage_note(self, card_widget, nota: BrokerageNoteSchema):
        """Salva as transações da nota de corretagem no Excel sem duplicar e atualiza a carteira."""
        try:
            transacoes_rateadas = nota.aplicar_rateio_custos()
            engine_txs = [tx.to_engine_transaction() for tx in transacoes_rateadas]
            salvas, ignoradas = save_transactions_batch_to_excel(
                engine_txs,
                DEFAULT_EXCEL_PATH,
                prevent_duplicates=True,
            )

            self.load_data()
            self.refresh_quotes_async()

            card_widget.destroy()

            if salvas == 0:
                self._add_bot_message(
                    f"ℹ️ Nenhuma nova operação foi gravada:\n\n"
                    f"Todas as {len(transacoes_rateadas)} operações desta nota (Pregão: {nota.data_pregao}) "
                    f"já constavam na planilha. A duplicação de dados foi evitada!"
                )
                return

            resumo_linhas = "\n".join(
                f"• [{t.operacao.value.upper()}] {t.quantidade:g} {t.ticker} @ R$ {t.valor_unitario:.2f}"
                for t in transacoes_rateadas
            )
            msg_sucesso = (
                f"OK! Nota de corretagem processada com sucesso!\n\n"
                f"• Corretora: {nota.corretora or 'Não informada'}\n"
                f"• Data do Pregão: {nota.data_pregao}\n"
                f"• Operações novas gravadas: {salvas}\n"
            )
            if ignoradas > 0:
                msg_sucesso += f"• Operações duplicadas ignoradas: {ignoradas}\n"
            msg_sucesso += (
                f"• Total de Custos/Taxas: R$ {nota.total_custos_emolumentos:.2f}\n"
                f"• Operações da nota:\n{resumo_linhas}\n\n"
                f"Sua carteira e preços médios foram recalculados. Confira na aba 'Carteira Atual'!"
            )
            self._add_bot_message(msg_sucesso)
        except Exception as e:
            messagebox.showerror("Erro ao Salvar Nota", f"Não foi possível gravar as operações da nota:\n{e}")

    def _on_send_prompt(self):
        if self._is_processing_ai:
            return
        prompt = self.entry_ai_prompt.get().strip()
        if not prompt:
            return

        self._is_processing_ai = True
        self.entry_ai_prompt.delete(0, tk.END)
        self._add_user_message(prompt)
        self._show_thinking_indicator("Analisando sua solicitação")

        self.btn_send_prompt.configure(state="disabled", text="Pensando...")
        threading.Thread(target=self._process_ai_thread, args=(prompt,), daemon=True).start()

    def _format_ai_error(self, e: Exception) -> str:
        err_str = str(e)
        if "503" in err_str or "high demand" in err_str.lower() or "ModelUnavailableError" in str(type(e)):
            return (
                "⚠️ Os servidores do Google Gemini estão com alta demanda temporária no momento (Erro 503).\n\n"
                "Como você está utilizando a cota gratuita do Google AI Studio, picos de acesso momentâneos "
                "geram fila no processador do Google.\n\n"
                "Dica: Aguarde de 5 a 10 segundos e tente enviar sua mensagem novamente!"
            )
        return f"❌ Ocorreu um erro ao processar sua solicitação:\n{err_str}"

    def _deliver_ai_result(self, callback):
        """Remove indicador de carregamento e executa o callback de resultado na thread da UI."""
        self._hide_thinking_indicator()
        callback()

    def _finish_ai_prompt(self):
        self._is_processing_ai = False
        self._hide_thinking_indicator()
        if hasattr(self, "btn_send_prompt") and self.btn_send_prompt.winfo_exists():
            self.btn_send_prompt.configure(state="normal", text="Enviar 🚀")

    def _process_ai_thread(self, prompt: str):
        try:
            prompt_lower = prompt.lower()
            palavras_evento = [
                "desdobramento", "split", "agrupamento", "inplit",
                "virou", "converteu", "conversão", "conversao",
                "incorporou", "mudou para", "incorporação", "incorporacao",
            ]
            is_evento_corporativo = any(p in prompt_lower for p in palavras_evento)

            palavras_transacao = ["comprei", "vendi", "compra", "venda", "aporte", "adicionar"]
            primeira_palavra = prompt_lower.split()[0] if prompt_lower.split() else ""
            is_transacao = (
                not is_evento_corporativo
                and (primeira_palavra in palavras_transacao or any(prompt_lower.startswith(p) for p in palavras_transacao))
            )

            max_tentativas = 2
            ultimo_erro = None

            for tentativa in range(max_tentativas):
                try:
                    if is_evento_corporativo:
                        res = corporate_event_agent.run_sync(prompt)
                        ev_schema: CorporateEventSchema = res.output
                        self.after(0, lambda e=ev_schema: self._deliver_ai_result(lambda: self._add_corporate_event_card(e)))
                        return
                    elif is_transacao:
                        res = transaction_agent.run_sync(prompt, deps=self.ai_context)
                        tx_schema: TransactionSchema = res.output
                        self.after(0, lambda t=tx_schema: self._deliver_ai_result(lambda: self._add_transaction_card(t)))
                        return
                    else:
                        res = assistant_agent.run_sync(prompt, deps=self.ai_context)
                        resposta_texto = res.output
                        self.after(0, lambda r=resposta_texto: self._deliver_ai_result(lambda: self._add_bot_message(r)))
                        return
                except Exception as e:
                    ultimo_erro = e
                    err_text = str(e)
                    # Se for pico 503 da Google, aguarda 2s e tenta mais uma vez antes de desistir
                    if ("503" in err_text or "high demand" in err_text.lower() or "ModelUnavailableError" in str(type(e))) and tentativa < max_tentativas - 1:
                        time.sleep(2.0)
                        continue
                    break

            if ultimo_erro:
                err_msg = self._format_ai_error(ultimo_erro)
                self.after(0, lambda m=err_msg: self._deliver_ai_result(lambda: self._add_bot_message(m)))

        except Exception as e:
            err_msg = self._format_ai_error(e)
            self.after(0, lambda m=err_msg: self._deliver_ai_result(lambda: self._add_bot_message(m)))

        finally:
            self.after(0, self._finish_ai_prompt)

    def _on_import_brokerage_note(self):
        """Abre diálogo para seleção de nota de corretagem em PDF e inicia processamento assíncrono."""
        caminho_pdf = filedialog.askopenfilename(
            title="Selecione a Nota de Corretagem (PDF)",
            filetypes=[("Arquivos PDF (*.pdf)", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not caminho_pdf:
            return

        nome_arquivo = os.path.basename(caminho_pdf)
        self._add_user_message(f"📄 Importando Nota de Corretagem: {nome_arquivo}")
        self._show_thinking_indicator("Lendo e analisando nota de corretagem")

        self.btn_import_pdf.configure(state="disabled", text="Lendo PDF...")
        threading.Thread(
            target=self._process_brokerage_note_thread,
            args=(caminho_pdf,),
            daemon=True,
        ).start()

    def _process_brokerage_note_thread(self, caminho_pdf: str):
        """Thread em background para extrair texto do PDF e decodificar layout B3/SINACOR via IA."""
        try:
            texto_pdf = extrair_texto_pdf(caminho_pdf)
            prompt = (
                f"Analise o texto a seguir extraído de uma nota de corretagem da B3 e extraia "
                f"todos os dados estruturados de acordo com o schema:\n\n{texto_pdf}"
            )

            max_tentativas = 2
            ultimo_erro = None

            for tentativa in range(max_tentativas):
                try:
                    res = brokerage_note_agent.run_sync(prompt)
                    nota: BrokerageNoteSchema = res.output

                    if not nota.transacoes:
                        msg_vazia = (
                            f"⚠️ O documento foi lido, mas nenhuma operação de compra ou venda "
                            f"foi encontrada na nota (Pregão: {nota.data_pregao})."
                        )
                        self.after(0, lambda m=msg_vazia: self._deliver_ai_result(lambda: self._add_bot_message(m)))
                        return

                    self.after(0, lambda n=nota: self._deliver_ai_result(lambda: self._add_batch_brokerage_note_card(n)))
                    return
                except Exception as e:
                    ultimo_erro = e
                    err_text = str(e)
                    if ("503" in err_text or "high demand" in err_text.lower() or "ModelUnavailableError" in str(type(e))) and tentativa < max_tentativas - 1:
                        time.sleep(2.0)
                        continue
                    break

            if ultimo_erro:
                err_msg = self._format_ai_error(ultimo_erro)
                self.after(0, lambda m=err_msg: self._deliver_ai_result(lambda: self._add_bot_message(m)))

        except Exception as e:
            err_msg = f"❌ Erro ao ler nota de corretagem:\n{e}"
            self.after(0, lambda m=err_msg: self._deliver_ai_result(lambda: self._add_bot_message(m)))

        finally:
            self.after(
                0,
                lambda: self.btn_import_pdf.configure(
                    state="normal",
                    text="📄 Importar Nota (PDF)",
                )
                if self.btn_import_pdf.winfo_exists()
                else None,
            )

    def _on_export_irpf_txt(self):
        """Solicita o ano-calendário e o destino do arquivo .txt para exportar o Guia IRPF."""
        ano = simpledialog.askinteger(
            "Exportar Guia IRPF (.txt)",
            "Informe o ano-calendário da declaração:",
            initialvalue=datetime.now().year - 1,
            minvalue=2015,
            maxvalue=2035,
            parent=self,
        )
        if ano is None:
            return

        caminho_arquivo = filedialog.asksaveasfilename(
            title=f"Salvar Guia IRPF {ano}",
            defaultextension=".txt",
            initialfile=f"guia_irpf_{ano}.txt",
            filetypes=[("Arquivos de Texto (*.txt)", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if not caminho_arquivo:
            return

        self.btn_export_irpf.configure(state="disabled", text="Exportando...")
        threading.Thread(
            target=self._export_irpf_thread,
            args=(ano, caminho_arquivo),
            daemon=True,
        ).start()

    def _export_irpf_thread(self, ano: int, caminho_arquivo: str):
        """Thread em background para gerar e gravar o Guia IRPF em arquivo texto UTF-8."""
        try:
            salvo_em = exportar_guia_irpf_txt(self.ai_context, ano, caminho_arquivo)
            self.after(
                0,
                lambda s=salvo_em: self._on_export_irpf_success(ano, s),
            )
        except Exception as e:
            err_msg = f"❌ Erro ao exportar Guia IRPF {ano}:\n{e}"
            self.after(0, lambda m=err_msg: self._on_export_irpf_error(m))
        finally:
            self.after(
                0,
                lambda: self.btn_export_irpf.configure(
                    state="normal",
                    text="💾 Exportar IRPF (.txt)",
                )
                if self.btn_export_irpf.winfo_exists()
                else None,
            )

    def _on_export_irpf_success(self, ano: int, salvo_em: str):
        """Notifica no chat e via diálogo após exportar o Guia IRPF."""
        self._add_bot_message(f"✅ Guia IRPF {ano} exportado com sucesso para:\n{salvo_em}")
        messagebox.showinfo("Guia IRPF Exportado", f"Arquivo salvo com sucesso em:\n{salvo_em}")

    def _on_export_irpf_error(self, err_msg: str):
        """Notifica erro no chat e via diálogo caso a exportação falhe."""
        self._add_bot_message(err_msg)
        messagebox.showerror("Erro na Exportação", err_msg)


if __name__ == "__main__":
    app = InvestAIApp()
    app.mainloop()
