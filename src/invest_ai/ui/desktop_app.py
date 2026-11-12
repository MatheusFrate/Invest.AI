"""
Invest.AI • Interface Gráfica Moderna com Copiloto PydanticAI Integrado.
Extensão do aplicativo de investimentos desktop com suporte a linguagem natural,
extração estruturada e simulação fiscal da B3.
"""

import os
import re
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk

from invest_ai.ui.base_window import InvestApp
from invest_ai.agent.deps import InvestContext
from invest_ai.agent.agent import transaction_agent, assistant_agent, brokerage_note_agent, resolver_modelo_padrao
from invest_ai.agent.schemas import TransactionSchema, BrokerageNoteSchema
from invest_ai.services.excel_handler import (
    DEFAULT_EXCEL_PATH,
    save_transaction_to_excel,
    save_transactions_batch_to_excel,
    normalizar_todas_datas_planilha
)
from invest_ai.services.pdf_extractor import extrair_texto_pdf


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
            engine=self.engine
        )
        self.ai_context._carteira_carregada = True

        self._reorganize_sidebar_for_ai()
        self._add_copiloto_view()

        # Higieniza datas antigas YYYY-MM-DD na planilha para DD/MM/AAAA se houver
        corrigidas = normalizar_todas_datas_planilha(DEFAULT_EXCEL_PATH)
        if corrigidas > 0:
            self.load_data()

        # Abre diretamente na tela do Copiloto IA por padrão
        self.show_view("copiloto")

    def _reorganize_sidebar_for_ai(self):
        """Atualiza a barra lateral para incluir o botão do Copiloto IA no topo."""
        for child in self.sidebar_frame.winfo_children():
            if isinstance(child, ctk.CTkLabel) and "InvestDARF" in child.cget("text"):
                child.configure(text="🤖 Invest.AI")

        self.btn_nav_copiloto = ctk.CTkButton(
            self.sidebar_frame,
            text="🤖 Copiloto IA",
            command=lambda: self.show_view("copiloto"),
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#6366f1",
            hover_color="#4f46e5"
        )
        self.btn_nav_copiloto.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")

        self.btn_nav_carteira.grid(row=2, column=0, padx=20, pady=6, sticky="ew")
        self.btn_nav_vendas.grid(row=3, column=0, padx=20, pady=6, sticky="ew")
        self.btn_nav_proventos.grid(row=4, column=0, padx=20, pady=6, sticky="ew")
        self.btn_nav_nova.grid(row=5, column=0, padx=20, pady=6, sticky="ew")
        self.btn_nav_historico.grid(row=6, column=0, padx=20, pady=6, sticky="ew")

    def _add_copiloto_view(self):
        """Cria e adiciona a view do Copiloto IA ao dicionário de views."""
        self.copiloto_view = self._create_copiloto_view()
        self.views["copiloto"] = self.copiloto_view

    def _create_copiloto_view(self):
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.grid_columnconfigure(0, weight=1)

        modelo = resolver_modelo_padrao()
        nome_mod = modelo if isinstance(modelo, str) else getattr(modelo, "model_name", type(modelo).__name__)

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🤖 Copiloto Inteligente de Investimentos",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text=f"Processamento por PydanticAI • Modelo ativo: {nome_mod}",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        subtitle_lbl.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.btn_import_pdf = ctk.CTkButton(
            header_frame,
            text="📄 Importar Nota de Corretagem (PDF)",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=38,
            command=self._on_import_brokerage_note
        )
        self.btn_import_pdf.grid(row=0, column=1, rowspan=2, padx=(10, 0), sticky="e")

        self.chat_scroll = ctk.CTkScrollableFrame(frame, corner_radius=10, fg_color="#18181b")
        self.chat_scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 15))
        self.chat_scroll.grid_columnconfigure(0, weight=1)

        self._add_bot_message(
            "Olá! Eu sou o seu Copiloto Invest.AI.\n\n"
            "• Importar Notas: Clique no botão '📄 Importar Nota de Corretagem (PDF)' no topo para ler notas da B3.\n"
            "• Registrar Aporte: Digite algo como 'Comprei 100 cotas de MXRF11 a 9,45 hoje na XP'.\n"
            "• Simular DARF: Pergunte 'Se eu vender 30 ações de PETR4 a R$ 45,00 pago imposto?'.\n"
            "• Consultar Carteira: Pergunte 'Qual é o meu preço médio em PETR4?'."
        )

        chips_frame = ctk.CTkFrame(frame, fg_color="transparent")
        chips_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        sugestoes = [
            ("Comprei 100 MXRF11 a 9,45", "Comprei 100 MXRF11 a 9,45", False),
            ("Se eu vender 20 PETR4 pago DARF?", "Se eu vender 20 PETR4 pago DARF?", False),
            ("Qual o meu preço médio de MXRF11?", "Qual o meu preço médio de MXRF11?", False),
            ("Quais ações eu tenho na carteira?", "Quais ações eu tenho na carteira?", False),
            ("📋 Guia IRPF (Ano Anterior)", "Como devo declarar meus ativos no IRPF do ano passado?", True),
        ]
        for label, prompt_text, auto_send in sugestoes:
            cmd = (
                (lambda p=prompt_text: self._enviar_sugestao_rapida(p))
                if auto_send
                else (lambda p=prompt_text: self._set_input_text(p))
            )
            btn_chip = ctk.CTkButton(
                chips_frame,
                text=label,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#27272a",
                hover_color="#3f3f46",
                command=cmd,
            )
            btn_chip.pack(side="left", padx=(0, 8))

        input_frame = ctk.CTkFrame(frame, fg_color="transparent")
        input_frame.grid(row=3, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry_ai_prompt = ctk.CTkEntry(
            input_frame,
            placeholder_text="Digite sua operação ou dúvida (ex: 'Comprei 50 ações de PETR4 a 38,50')...",
            height=44,
            font=ctk.CTkFont(size=13)
        )
        self.entry_ai_prompt.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry_ai_prompt.bind("<Return>", lambda e: self._on_send_prompt())

        self.btn_send_prompt = ctk.CTkButton(
            input_frame,
            text="Enviar 🚀",
            width=110,
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._on_send_prompt
        )
        self.btn_send_prompt.grid(row=0, column=1)

        return frame

    def _set_input_text(self, text: str):
        self.entry_ai_prompt.delete(0, tk.END)
        self.entry_ai_prompt.insert(0, text)
        self.entry_ai_prompt.focus()

    def _enviar_sugestao_rapida(self, text: str):
        """Preenche o campo de entrada e envia automaticamente a pergunta."""
        self._set_input_text(text)
        self._on_send_prompt()

    def _add_user_message(self, text: str):
        """Adiciona bolha de mensagem do usuário."""
        card = ctk.CTkFrame(self.chat_scroll, fg_color="#27272a", corner_radius=10)
        card.pack(fill="x", padx=10, pady=6, anchor="e")

        lbl_user = ctk.CTkLabel(
            card,
            text="Você",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#818cf8"
        )
        lbl_user.pack(anchor="w", padx=12, pady=(8, 2))

        lbl_msg = ctk.CTkLabel(
            card,
            text=text,
            font=ctk.CTkFont(size=13),
            wraplength=700,
            justify="left"
        )
        lbl_msg.pack(anchor="w", padx=12, pady=(0, 8))

        self.chat_scroll.after(100, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _add_bot_message(self, text: str):
        """Adiciona bolha de mensagem do assistente em texto limpo e legível."""
        texto_limpo = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        texto_limpo = re.sub(r'__(.*?)__', r'\1', texto_limpo)
        texto_limpo = re.sub(r'\*(.*?)\*', r'\1', texto_limpo)
        texto_limpo = re.sub(r'`(.*?)`', r'\1', texto_limpo)
        texto_limpo = re.sub(r'^\*\s+', '• ', texto_limpo, flags=re.MULTILINE)
        texto_limpo = re.sub(r'^#+\s*', '', texto_limpo, flags=re.MULTILINE).strip()

        card = ctk.CTkFrame(self.chat_scroll, fg_color="#1e1e24", corner_radius=10)
        card.pack(fill="x", padx=10, pady=6, anchor="w")

        lbl_bot = ctk.CTkLabel(
            card,
            text="🤖 Invest.AI",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#34d399"
        )
        lbl_bot.pack(anchor="w", padx=12, pady=(8, 2))

        lbl_msg = ctk.CTkLabel(
            card,
            text=texto_limpo,
            font=ctk.CTkFont(size=13),
            wraplength=700,
            justify="left"
        )
        lbl_msg.pack(anchor="w", padx=12, pady=(0, 8))

        self.chat_scroll.after(100, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _add_transaction_card(self, tx: TransactionSchema):
        """Adiciona card estruturado para confirmação de transação com Human-in-the-Loop."""
        has_alerta = bool(tx.alerta_discrepancia)
        border_color = "#f59e0b" if has_alerta else "#3b82f6"
        border_width = 2 if has_alerta else 1

        card = ctk.CTkFrame(
            self.chat_scroll,
            fg_color="#1f2937",
            border_color=border_color,
            border_width=border_width,
            corner_radius=12
        )
        card.pack(fill="x", padx=10, pady=8)

        op_color = "#10b981" if tx.operacao.value == "compra" else "#ef4444"
        lbl_title = ctk.CTkLabel(
            card,
            text=f"📝 Operação Identificada: {tx.operacao.value.upper()}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=op_color
        )
        lbl_title.pack(anchor="w", padx=15, pady=(12, 6))

        detalhes = (
            f"• Ativo: {tx.ticker} ({tx.tipo_ativo.value.upper()})\n"
            f"• Quantidade: {tx.quantidade:.2f} cotas/ações\n"
            f"• Preço Unitário: R$ {tx.valor_unitario:.2f}\n"
            f"• Valor Total: R$ {tx.valor_total:.2f}\n"
            f"• Data: {tx.data}"
        )
        if tx.cotacao_mercado is not None:
            detalhes += f"\n• Cotação Ref. B3: R$ {tx.cotacao_mercado:.2f}"
        if tx.corretora:
            detalhes += f"  |  Corretora: {tx.corretora}"

        lbl_details = ctk.CTkLabel(
            card,
            text=detalhes,
            font=ctk.CTkFont(size=13),
            justify="left"
        )
        lbl_details.pack(anchor="w", padx=15, pady=(0, 10))

        if has_alerta:
            alerta_frame = ctk.CTkFrame(
                card,
                fg_color="#451a03",
                border_color="#f59e0b",
                border_width=1,
                corner_radius=8
            )
            alerta_frame.pack(fill="x", padx=15, pady=(0, 12))

            lbl_alerta = ctk.CTkLabel(
                alerta_frame,
                text=tx.alerta_discrepancia,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#fef3c7",
                wraplength=480,
                justify="left"
            )
            lbl_alerta.pack(anchor="w", padx=12, pady=10)

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(0, 12))

        btn_confirmar = ctk.CTkButton(
            btn_frame,
            text="✔ Confirmar e Gravar na Planilha",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            height=32,
            command=lambda c=card, t=tx: self._confirm_and_save_transaction(c, t)
        )
        btn_confirmar.pack(side="left", padx=(0, 10))

        btn_descartar = ctk.CTkButton(
            btn_frame,
            text="✖ Cancelar",
            font=ctk.CTkFont(size=12),
            fg_color="#4b5563",
            hover_color="#374151",
            height=32,
            command=lambda c=card: c.destroy()
        )
        btn_descartar.pack(side="left")

        self.chat_scroll.after(100, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

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

    def _add_batch_brokerage_note_card(self, nota: BrokerageNoteSchema):
        """Adiciona card estruturado para confirmação em lote de Nota de Corretagem (Human-in-the-Loop)."""
        card = ctk.CTkFrame(
            self.chat_scroll,
            fg_color="#182234",
            border_color="#3b82f6",
            border_width=2,
            corner_radius=12
        )
        card.pack(fill="x", padx=10, pady=10)

        # Cabeçalho do Card da Nota
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(12, 6))

        lbl_title = ctk.CTkLabel(
            header_frame,
            text="📄 Nota de Corretagem B3 (Confirmação em Lote)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#60a5fa"
        )
        lbl_title.pack(anchor="w")

        info_header = (
            f"• Corretora: {nota.corretora or 'Não identificada'}   |   "
            f"Data Pregão: {nota.data_pregao}   |   "
            f"Nr. Nota: {nota.numero_nota or 'N/A'}\n"
            f"• Total Custos e Emolumentos: R$ {nota.total_custos_emolumentos:.2f}"
        )
        lbl_info = ctk.CTkLabel(
            header_frame,
            text=info_header,
            font=ctk.CTkFont(size=12),
            text_color="gray80",
            justify="left"
        )
        lbl_info.pack(anchor="w", pady=(4, 6))

        # Tabela / Lista compacta com as operações encontradas
        ops_container = ctk.CTkFrame(card, fg_color="#0f172a", corner_radius=8)
        ops_container.pack(fill="x", padx=15, pady=(0, 10))

        lbl_ops_title = ctk.CTkLabel(
            ops_container,
            text=f"Operações Identificadas ({len(nota.transacoes)}):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8"
        )
        lbl_ops_title.pack(anchor="w", padx=12, pady=(8, 4))

        for tx in nota.transacoes:
            op_cor = "#10b981" if tx.operacao.value == "compra" else "#ef4444"
            linha_frame = ctk.CTkFrame(ops_container, fg_color="transparent")
            linha_frame.pack(fill="x", padx=12, pady=2)

            lbl_badge = ctk.CTkLabel(
                linha_frame,
                text=f"[{tx.operacao.value.upper()}]",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=op_cor,
                width=70,
                anchor="w"
            )
            lbl_badge.pack(side="left")

            detalhe_op = (
                f"{tx.quantidade:g} {tx.ticker} ({tx.tipo_ativo.value.upper()}) @ "
                f"R$ {tx.valor_unitario:.2f}  →  Total: R$ {tx.valor_total:.2f}"
            )
            lbl_detalhe = ctk.CTkLabel(
                linha_frame,
                text=detalhe_op,
                font=ctk.CTkFont(size=12),
                anchor="w"
            )
            lbl_detalhe.pack(side="left", padx=(6, 0))

        ctk.CTkFrame(ops_container, height=6, fg_color="transparent").pack()

        # Botões de Ação Human-in-the-Loop
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(4, 12))

        btn_confirmar = ctk.CTkButton(
            btn_frame,
            text=f"✔ Confirmar e Gravar Todas na Planilha ({len(nota.transacoes)})",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            height=34,
            command=lambda c=card, n=nota: self._confirm_and_save_brokerage_note(c, n)
        )
        btn_confirmar.pack(side="left", padx=(0, 10))

        btn_descartar = ctk.CTkButton(
            btn_frame,
            text="✖ Descartar",
            font=ctk.CTkFont(size=12),
            fg_color="#4b5563",
            hover_color="#374151",
            height=34,
            command=lambda c=card: c.destroy()
        )
        btn_descartar.pack(side="left")

        self.chat_scroll.after(100, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _confirm_and_save_brokerage_note(self, card_widget, nota: BrokerageNoteSchema):
        """Salva as transações da nota de corretagem no Excel sem duplicar e atualiza a carteira."""
        try:
            engine_txs = [tx.to_engine_transaction() for tx in nota.transacoes]
            salvas, ignoradas = save_transactions_batch_to_excel(
                engine_txs,
                DEFAULT_EXCEL_PATH,
                prevent_duplicates=True
            )

            self.load_data()
            self.refresh_quotes_async()

            card_widget.destroy()

            if salvas == 0:
                self._add_bot_message(
                    f"ℹ️ Nenhuma nova operação foi gravada:\n\n"
                    f"Todas as {len(nota.transacoes)} operações desta nota (Pregão: {nota.data_pregao}) "
                    f"já constavam na planilha. A duplicação de dados foi evitada!"
                )
                return

            resumo_linhas = "\n".join(
                f"• [{t.operacao.value.upper()}] {t.quantidade:g} {t.ticker} @ R$ {t.valor_unitario:.2f}"
                for t in nota.transacoes
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
        prompt = self.entry_ai_prompt.get().strip()
        if not prompt:
            return

        self.entry_ai_prompt.delete(0, tk.END)
        self._add_user_message(prompt)

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

    def _process_ai_thread(self, prompt: str):
        try:
            palavras_transacao = ["comprei", "vendi", "compra", "venda", "aporte", "adicionar"]
            primeira_palavra = prompt.lower().split()[0] if prompt.split() else ""
            is_transacao = primeira_palavra in palavras_transacao or any(prompt.lower().startswith(p) for p in palavras_transacao)

            max_tentativas = 2
            ultimo_erro = None

            for tentativa in range(max_tentativas):
                try:
                    if is_transacao:
                        res = transaction_agent.run_sync(prompt, deps=self.ai_context)
                        tx_schema: TransactionSchema = res.output
                        self.after(0, lambda: self._add_transaction_card(tx_schema))
                        return
                    else:
                        res = assistant_agent.run_sync(prompt, deps=self.ai_context)
                        resposta_texto = res.output
                        self.after(0, lambda: self._add_bot_message(resposta_texto))
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
                self.after(0, lambda: self._add_bot_message(err_msg))

        except Exception as e:
            err_msg = self._format_ai_error(e)
            self.after(0, lambda: self._add_bot_message(err_msg))

        finally:
            self.after(0, lambda: self.btn_send_prompt.configure(state="normal", text="Enviar 🚀"))

    def _on_import_brokerage_note(self):
        """Abre diálogo para seleção de nota de corretagem em PDF e inicia processamento assíncrono."""
        caminho_pdf = filedialog.askopenfilename(
            title="Selecione a Nota de Corretagem (PDF)",
            filetypes=[("Arquivos PDF (*.pdf)", "*.pdf"), ("Todos os arquivos", "*.*")]
        )
        if not caminho_pdf:
            return

        nome_arquivo = os.path.basename(caminho_pdf)
        self._add_user_message(f"📄 Importando Nota de Corretagem: {nome_arquivo}")
        self._add_bot_message("Lendo e analisando nota de corretagem... Por favor, aguarde alguns instantes.")

        self.btn_import_pdf.configure(state="disabled", text="Lendo PDF...")
        threading.Thread(
            target=self._process_brokerage_note_thread,
            args=(caminho_pdf,),
            daemon=True
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
                        self.after(
                            0,
                            lambda: self._add_bot_message(
                                f"⚠️ O documento foi lido, mas nenhuma operação de compra ou venda "
                                f"foi encontrada na nota (Pregão: {nota.data_pregao})."
                            )
                        )
                        return

                    self.after(0, lambda: self._add_batch_brokerage_note_card(nota))
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
                self.after(0, lambda: self._add_bot_message(err_msg))

        except Exception as e:
            err_msg = f"❌ Erro ao ler nota de corretagem:\n{e}"
            self.after(0, lambda: self._add_bot_message(err_msg))

        finally:
            self.after(
                0,
                lambda: self.btn_import_pdf.configure(
                    state="normal",
                    text="📄 Importar Nota de Corretagem (PDF)"
                )
            )


if __name__ == "__main__":
    app = InvestAIApp()
    app.mainloop()
