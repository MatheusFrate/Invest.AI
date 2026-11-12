"""
Testes automatizados para o importador de Notas de Corretagem SINACOR/B3 em PDF.
Cobre:
- Extração segura de texto de PDF (pypdf)
- Validação e sincronização de dados no BrokerageNoteSchema
- Agente PydanticAI (brokerage_note_agent) com TestModel (100% offline e zero tokens)
"""

import pytest
from pypdf import PdfWriter

from invest_ai.services.pdf_extractor import extrair_texto_pdf
from invest_ai.agent.schemas import BrokerageNoteSchema, TransactionSchema, TipoAtivo, TipoOperacao
from invest_ai.agent.agent import criar_agente_nota_corretagem
from pydantic_ai.models.test import TestModel
from datetime import date, datetime
import openpyxl
from invest_ai.core.engine import Transaction
from invest_ai.services.excel_handler import (
    normalizar_data_br,
    is_duplicate_transaction,
    save_transaction_to_excel,
    save_transactions_batch_to_excel,
    normalizar_todas_datas_planilha,
    load_transactions_from_excel,
)


def test_extrair_texto_pdf_sucesso(tmp_path):
    """Gera um PDF sintético válido com fonte Type1 e testa a extração textual."""
    caminho = tmp_path / "nota_teste.pdf"
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 61 >>\nstream\n"
        b"BT\n/F1 12 Tf\n100 200 Td\n(NOTA DE CORRETAGEM XP INVESTIMENTOS B3) Tj\nET\n"
        b"endstream\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
    )
    caminho.write_bytes(pdf_bytes)

    texto = extrair_texto_pdf(str(caminho))
    assert "NOTA DE CORRETAGEM XP INVESTIMENTOS B3" in texto


def test_extrair_texto_pdf_arquivo_inexistente():
    with pytest.raises(FileNotFoundError) as exc_info:
        extrair_texto_pdf("arquivo_que_nao_existe_12345.pdf")
    assert "não encontrado" in str(exc_info.value)


def test_extrair_texto_pdf_corrompido(tmp_path):
    caminho = tmp_path / "corrompido.pdf"
    caminho.write_bytes(b"%PDF-1.4 LIXO_BINARIO_CORROMPIDO")
    with pytest.raises(ValueError) as exc_info:
        extrair_texto_pdf(str(caminho))
    assert "corrompido" in str(exc_info.value).lower() or "abrir" in str(exc_info.value).lower()


def test_extrair_texto_pdf_criptografado_com_senha(tmp_path):
    caminho = tmp_path / "protegido.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("senha_secreta_123")
    with open(caminho, "wb") as f:
        writer.write(f)

    with pytest.raises(ValueError) as exc_info:
        extrair_texto_pdf(str(caminho))
    assert "protegido por senha" in str(exc_info.value).lower()


def test_extrair_texto_pdf_vazio(tmp_path):
    caminho = tmp_path / "vazio.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(caminho, "wb") as f:
        writer.write(f)

    with pytest.raises(ValueError) as exc_info:
        extrair_texto_pdf(str(caminho))
    assert "vazio ou conter apenas imagens" in str(exc_info.value).lower()


def test_brokerage_note_schema_validacao_e_sincronizacao():
    """Valida o schema da nota e a sincronização automática de corretora e data nas transações."""
    dados_nota = {
        "numero_nota": "123456",
        "data_pregao": "04/11/2026",
        "corretora": "XP Investimentos",
        "total_custos_emolumentos": 4.50,
        "transacoes": [
            {
                "ticker": "PETR4",
                "operacao": "compra",
                "quantidade": 100,
                "valor_unitario": 38.50,
                "valor_total": 3850.00
            },
            {
                "ticker": "MXRF11",
                "operacao": "venda",
                "quantidade": 50,
                "valor_unitario": 10.20,
                "valor_total": 510.00
            }
        ]
    }

    nota = BrokerageNoteSchema(**dados_nota)
    assert nota.numero_nota == "123456"
    assert nota.data_pregao == "04/11/2026"
    assert nota.corretora == "XP Investimentos"
    assert nota.total_custos_emolumentos == 4.50
    assert len(nota.transacoes) == 2

    # Verifica se herdaram corretora e data da nota no formato DD/MM/AAAA
    tx1 = nota.transacoes[0]
    assert tx1.ticker == "PETR4"
    assert tx1.corretora == "XP Investimentos"
    assert tx1.data == "04/11/2026"
    assert tx1.tipo_ativo == TipoAtivo.ACAO
    assert tx1.operacao == TipoOperacao.COMPRA

    tx2 = nota.transacoes[1]
    assert tx2.ticker == "MXRF11"
    assert tx2.corretora == "XP Investimentos"
    assert tx2.data == "04/11/2026"
    assert tx2.tipo_ativo == TipoAtivo.FII
    assert tx2.operacao == TipoOperacao.VENDA

    # Verifica conversão para dataclass de engine mantendo data DD/MM/AAAA
    engine_tx1 = tx1.to_engine_transaction()
    assert engine_tx1.ticker == "PETR4"
    assert engine_tx1.quantidade == 100.0
    assert engine_tx1.valor_total == 3850.00
    assert engine_tx1.data == "04/11/2026"


def test_brokerage_note_schema_data_invalida():
    with pytest.raises(ValueError):
        BrokerageNoteSchema(
            numero_nota="1",
            data_pregao="data_invalida_99/99",
            corretora="Clear",
            transacoes=[]
        )


def test_extracao_nota_corretagem_com_test_model():
    """Testa a extração pelo agente PydanticAI de forma 100% offline via TestModel."""
    texto_simulado_sinacor = """
    NOTA DE CORRETAGEM - B3 S.A.
    Corretora: XP INVESTIMENTOS CCTVM S.A.
    Nr. nota: 987654
    Data Pregão: 05/11/2026

    Negócios Realizados:
    1-BOVESPA C VISTA PETROBRAS PN 100 38,50 3.850,00 D
    1-BOVESPA V VISTA MAXI RENDA FII 50 10,20 510,00 C

    Resumo Financeiro:
    Taxa de liquidação: 1,20
    Emolumentos: 0,85
    Taxa de corretagem: 0,00
    Total Custos / Despesas: 2,05
    """

    test_model = TestModel(
        custom_output_args={
            "numero_nota": "987654",
            "data_pregao": "2026-11-05",
            "corretora": "XP Investimentos",
            "total_custos_emolumentos": 2.05,
            "transacoes": [
                {
                    "ticker": "PETR4",
                    "operacao": "compra",
                    "quantidade": 100,
                    "valor_unitario": 38.50,
                    "valor_total": 3850.00
                },
                {
                    "ticker": "MXRF11",
                    "operacao": "venda",
                    "quantidade": 50,
                    "valor_unitario": 10.20,
                    "valor_total": 510.00
                }
            ]
        }
    )

    agent = criar_agente_nota_corretagem(model=test_model)
    res = agent.run_sync(f"Extraia os dados desta nota de corretagem:\n{texto_simulado_sinacor}")

    nota_extraida = res.output
    assert isinstance(nota_extraida, BrokerageNoteSchema)
    assert nota_extraida.numero_nota == "987654"
    assert nota_extraida.data_pregao == "05/11/2026"
    assert nota_extraida.corretora == "XP Investimentos"
    assert nota_extraida.total_custos_emolumentos == 2.05
    assert len(nota_extraida.transacoes) == 2

    petr4 = nota_extraida.transacoes[0]
    assert petr4.ticker == "PETR4"
    assert petr4.operacao == TipoOperacao.COMPRA
    assert petr4.quantidade == 100.0
    assert petr4.valor_unitario == 38.50
    assert petr4.valor_total == 3850.00

    mxrf11 = nota_extraida.transacoes[1]
    assert mxrf11.ticker == "MXRF11"
    assert mxrf11.operacao == TipoOperacao.VENDA
    assert mxrf11.quantidade == 50.0
    assert mxrf11.valor_unitario == 10.20
    assert mxrf11.valor_total == 510.00


def test_normalizar_data_br():
    """Testa conversão de diferentes representações de data para DD/MM/AAAA."""
    assert normalizar_data_br("2026-10-19") == "19/10/2026"
    assert normalizar_data_br("19/10/2026") == "19/10/2026"
    assert normalizar_data_br("2026-10-19 15:30:00") == "19/10/2026"
    assert normalizar_data_br(date(2026, 10, 19)) == "19/10/2026"
    assert normalizar_data_br(datetime(2026, 10, 19, 10, 0)) == "19/10/2026"
    assert normalizar_data_br("") == ""
    assert normalizar_data_br(None) == ""


def test_is_duplicate_transaction():
    """Testa a lógica de detecção de transações duplicadas."""
    existente = Transaction(
        ticker="PETR4",
        operacao="compra",
        tipo_ativo="ação",
        quantidade=100.0,
        valor_unitario=38.50,
        valor_total=3850.00,
        data="19/10/2026"
    )
    lista_existentes = [existente]

    # Mesmo papel, mesma data em formato ISO YYYY-MM-DD -> deve detectar como duplicata
    nova_mesma = Transaction(
        ticker="PETR4",
        operacao="compra",
        tipo_ativo="ação",
        quantidade=100.0,
        valor_unitario=38.50,
        valor_total=3850.00,
        data="2026-10-19"
    )
    assert is_duplicate_transaction(nova_mesma, lista_existentes) is True

    # Papel diferente
    nova_outro_ticker = Transaction(
        ticker="VALE3",
        operacao="compra",
        quantidade=100.0,
        valor_total=3850.00,
        valor_unitario=38.50,
        data="19/10/2026"
    )
    assert is_duplicate_transaction(nova_outro_ticker, lista_existentes) is False

    # Quantidade diferente
    nova_outra_qtd = Transaction(
        ticker="PETR4",
        operacao="compra",
        quantidade=50.0,
        valor_total=1925.00,
        valor_unitario=38.50,
        data="19/10/2026"
    )
    assert is_duplicate_transaction(nova_outra_qtd, lista_existentes) is False

    # Operação diferente (venda vs compra)
    nova_venda = Transaction(
        ticker="PETR4",
        operacao="venda",
        quantidade=100.0,
        valor_total=3850.00,
        valor_unitario=38.50,
        data="19/10/2026"
    )
    assert is_duplicate_transaction(nova_venda, lista_existentes) is False

    # Diferença real de R$ 0,01 não deve ser tratada como duplicata
    venda_6681 = Transaction(
        ticker="IRIM11",
        operacao="venda",
        tipo_ativo="fii",
        quantidade=1.0,
        valor_unitario=66.81,
        valor_total=66.81,
        data="19/10/2026"
    )
    venda_6682 = Transaction(
        ticker="IRIM11",
        operacao="venda",
        tipo_ativo="fii",
        quantidade=1.0,
        valor_unitario=66.82,
        valor_total=66.82,
        data="19/10/2026"
    )
    assert is_duplicate_transaction(venda_6682, [venda_6681]) is False


def test_prevencao_duplicidade_ao_salvar_excel(tmp_path):
    """Testa bloqueio de duplicatas ao gravar na planilha individualmente."""
    caminho = tmp_path / "planilha_teste.xlsx"
    tx1 = Transaction(
        ticker="MXRF11",
        operacao="compra",
        tipo_ativo="fii",
        quantidade=10.0,
        valor_unitario=10.20,
        valor_total=102.00,
        data="15/10/2026"
    )

    # Primeira gravação deve ser bem-sucedida
    assert save_transaction_to_excel(tx1, str(caminho), prevent_duplicates=True) is True

    # Segunda gravação da mesma transação deve ser bloqueada
    assert save_transaction_to_excel(tx1, str(caminho), prevent_duplicates=True) is False

    # Carrega e valida que só tem 1 linha e formato está DD/MM/AAAA
    carregadas = load_transactions_from_excel(str(caminho))
    assert len(carregadas) == 1
    assert carregadas[0].data == "15/10/2026"


def test_salvar_lote_com_prevencao_duplicidade(tmp_path):
    """Testa salvamento em lote ignorando operações que já constam na planilha."""
    caminho = tmp_path / "planilha_lote.xlsx"
    tx_base = Transaction(
        ticker="PETR4",
        operacao="compra",
        quantidade=50.0,
        valor_unitario=38.00,
        valor_total=1900.00,
        data="10/10/2026"
    )
    save_transaction_to_excel(tx_base, str(caminho))

    lote = [
        # Duplicata da já existente
        Transaction(
            ticker="PETR4",
            operacao="compra",
            quantidade=50.0,
            valor_unitario=38.00,
            valor_total=1900.00,
            data="2026-10-10"  # ISO
        ),
        # Nova operação 1
        Transaction(
            ticker="VALE3",
            operacao="compra",
            quantidade=20.0,
            valor_unitario=60.00,
            valor_total=1200.00,
            data="10/10/2026"
        ),
        # Nova operação 2
        Transaction(
            ticker="MXRF11",
            operacao="compra",
            quantidade=100.0,
            valor_unitario=9.50,
            valor_total=950.00,
            data="10/10/2026"
        ),
    ]

    salvas, ignoradas = save_transactions_batch_to_excel(lote, str(caminho), prevent_duplicates=True)
    assert salvas == 2
    assert ignoradas == 1

    todas = load_transactions_from_excel(str(caminho))
    assert len(todas) == 3
    # Todas devem ter datas DD/MM/AAAA
    for t in todas:
        assert "/" in t.data


def test_salvar_lote_vendas_parciais_diferenca_um_centavo(tmp_path):
    """Vendas parciais no mesmo dia e quantidade com R$ 0,01 de diferença devem ser todas salvas."""
    caminho = tmp_path / "planilha_centavo.xlsx"
    lote = [
        Transaction(
            ticker="IRIM11",
            operacao="venda",
            tipo_ativo="fii",
            quantidade=1.0,
            valor_unitario=66.81,
            valor_total=66.81,
            data="19/10/2026",
        ),
        Transaction(
            ticker="IRIM11",
            operacao="venda",
            tipo_ativo="fii",
            quantidade=1.0,
            valor_unitario=66.82,
            valor_total=66.82,
            data="19/10/2026",
        ),
    ]

    salvas, duplicadas = save_transactions_batch_to_excel(lote, str(caminho), prevent_duplicates=True)
    assert salvas == 2
    assert duplicadas == 0

    todas = load_transactions_from_excel(str(caminho))
    assert len(todas) == 2


def test_salvar_lote_execucoes_parciais_identicas_e_reimportacao(tmp_path):
    """
    Duas execuções parciais idênticas na mesma nota devem ser salvas na 1ª importação,
    mas bloqueadas 1-para-1 se o mesmo lote for reimportado.
    """
    caminho = tmp_path / "planilha_parciais_identicas.xlsx"
    lote = [
        Transaction(
            ticker="IRIM11",
            operacao="venda",
            tipo_ativo="fii",
            quantidade=1.0,
            valor_unitario=66.81,
            valor_total=66.81,
            data="19/10/2026",
        ),
        Transaction(
            ticker="IRIM11",
            operacao="venda",
            tipo_ativo="fii",
            quantidade=1.0,
            valor_unitario=66.81,
            valor_total=66.81,
            data="19/10/2026",
        ),
    ]

    # 1ª importação: ambas as execuções parciais são salvas
    salvas1, duplicadas1 = save_transactions_batch_to_excel(lote, str(caminho), prevent_duplicates=True)
    assert salvas1 == 2
    assert duplicadas1 == 0

    # 2ª importação do mesmo lote: ambas dão match 1-para-1 e são bloqueadas
    salvas2, duplicadas2 = save_transactions_batch_to_excel(lote, str(caminho), prevent_duplicates=True)
    assert salvas2 == 0
    assert duplicadas2 == 2

    todas = load_transactions_from_excel(str(caminho))
    assert len(todas) == 2


def test_normalizar_todas_datas_planilha(tmp_path):
    """Testa higienização retroativa de linhas com datas no formato YYYY-MM-DD."""
    caminho = tmp_path / "planilha_antiga.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "movimentações"
    ws.append(["Cota", "quantidade", "valor total", "valor da cota", "tag", "operação", "data"])
    ws.append(["mxrf11", 10, 100.0, 10.0, "fii", "compra", "2026-10-19"])
    ws.append(["petr4", 5, 200.0, 40.0, "ação", "compra", "15/10/2026"])
    ws.append(["vale3", 2, 120.0, 60.0, "ação", "compra", "2026-08-11"])
    wb.save(str(caminho))

    corrigidas = normalizar_todas_datas_planilha(str(caminho))
    assert corrigidas == 2

    # Verifica se os valores nas células foram alterados para DD/MM/AAAA
    wb2 = openpyxl.load_workbook(str(caminho), data_only=True)
    ws2 = wb2["movimentações"]
    assert ws2.cell(row=2, column=7).value == "19/10/2026"
    assert ws2.cell(row=3, column=7).value == "15/10/2026"
    assert ws2.cell(row=4, column=7).value == "11/08/2026"


def test_rateio_compra_unica_soma_custo():
    """Compra única com taxa deve somar os emolumentos ao custo total e recalcular preço unitário."""
    nota = BrokerageNoteSchema(
        numero_nota="1001",
        data_pregao="04/11/2026",
        corretora="XP",
        total_custos_emolumentos=2.50,
        transacoes=[
            TransactionSchema(
                ticker="PETR4",
                operacao="compra",
                quantidade=100,
                valor_unitario=35.00,
                valor_total=3500.00,
            )
        ],
    )

    rateadas = nota.aplicar_rateio_custos()
    assert len(rateadas) == 1
    assert rateadas[0].valor_total == 3502.50
    assert rateadas[0].valor_unitario == 35.025
    assert "Taxa rateada: R$ 2.50" in (rateadas[0].observacao or "")
    # Garante que a nota original não foi mutada
    assert nota.transacoes[0].valor_total == 3500.00


def test_rateio_venda_unica_deduz_taxa():
    """Venda bruta de R$ 1.069,03 com R$ 0,30 de taxas deve resultar em líquido de R$ 1.068,73."""
    nota = BrokerageNoteSchema(
        numero_nota="1002",
        data_pregao="04/11/2026",
        corretora="Clear",
        total_custos_emolumentos=0.30,
        transacoes=[
            TransactionSchema(
                ticker="MXRF11",
                operacao="venda",
                quantidade=100,
                valor_total=1069.03,
            )
        ],
    )

    rateadas = nota.aplicar_rateio_custos()
    assert len(rateadas) == 1
    assert rateadas[0].valor_total == 1068.73
    assert rateadas[0].valor_unitario == round(1068.73 / 100, 4)
    assert "Taxa rateada: R$ 0.30" in (rateadas[0].observacao or "")


def test_rateio_multiplas_operacoes_proporcional_e_fechamento_centavos():
    """Testa rateio proporcional 25%/75% e fechamento exato de centavos em divisão não exata."""
    nota_prop = BrokerageNoteSchema(
        numero_nota="1003",
        data_pregao="05/11/2026",
        corretora="BTG",
        total_custos_emolumentos=10.00,
        transacoes=[
            TransactionSchema(
                ticker="ITSA4",
                operacao="compra",
                quantidade=25,
                valor_unitario=10.00,
                valor_total=250.00,  # 25% do volume
            ),
            TransactionSchema(
                ticker="VALE3",
                operacao="venda",
                quantidade=15,
                valor_unitario=50.00,
                valor_total=750.00,  # 75% do volume
            ),
        ],
    )

    rateadas = nota_prop.aplicar_rateio_custos()
    assert rateadas[0].valor_total == 252.50  # 250 + 2.50
    assert rateadas[0].valor_unitario == 10.10
    assert rateadas[1].valor_total == 742.50  # 750 - 7.50
    assert rateadas[1].valor_unitario == 49.50

    # Fechamento exato de centavos (3 operações iguais dividindo R$ 1,00 -> 0.33 + 0.33 + 0.34)
    nota_centavos = BrokerageNoteSchema(
        numero_nota="1004",
        data_pregao="05/11/2026",
        total_custos_emolumentos=1.00,
        transacoes=[
            TransactionSchema(ticker="PETR4", operacao="compra", quantidade=10, valor_unitario=10.00, valor_total=100.00),
            TransactionSchema(ticker="BBAS3", operacao="compra", quantidade=10, valor_unitario=10.00, valor_total=100.00),
            TransactionSchema(ticker="WEGE3", operacao="compra", quantidade=10, valor_unitario=10.00, valor_total=100.00),
        ],
    )

    rateadas_c = nota_centavos.aplicar_rateio_custos()
    assert rateadas_c[0].valor_total == 100.33
    assert rateadas_c[1].valor_total == 100.33
    assert rateadas_c[2].valor_total == 100.34
    soma_taxas = sum(round(tx.valor_total - 100.00, 2) for tx in rateadas_c)
    assert round(soma_taxas, 2) == 1.00

    engine_txs = nota_centavos.to_engine_transactions_com_rateio()
    assert len(engine_txs) == 3
    assert engine_txs[2].valor_total == 100.34


def test_rateio_custos_zero_mantem_inalterada():
    """Nota com total_custos_emolumentos == 0.0 deve retornar transações inalteradas."""
    nota = BrokerageNoteSchema(
        numero_nota="1005",
        data_pregao="06/11/2026",
        corretora="Rico",
        total_custos_emolumentos=0.0,
        transacoes=[
            TransactionSchema(
                ticker="HGLG11",
                operacao="compra",
                quantidade=5,
                valor_unitario=160.00,
                valor_total=800.00,
            )
        ],
    )

    rateadas = nota.aplicar_rateio_custos()
    assert len(rateadas) == 1
    assert rateadas[0].valor_total == 800.00
    assert rateadas[0].valor_unitario == 160.00
    assert rateadas[0].observacao is None


