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
    assert nota.data_pregao == "2026-11-04"
    assert nota.corretora == "XP Investimentos"
    assert nota.total_custos_emolumentos == 4.50
    assert len(nota.transacoes) == 2

    # Verifica se herdaram corretora e data da nota
    tx1 = nota.transacoes[0]
    assert tx1.ticker == "PETR4"
    assert tx1.corretora == "XP Investimentos"
    assert tx1.data == "2026-11-04"
    assert tx1.tipo_ativo == TipoAtivo.ACAO
    assert tx1.operacao == TipoOperacao.COMPRA

    tx2 = nota.transacoes[1]
    assert tx2.ticker == "MXRF11"
    assert tx2.corretora == "XP Investimentos"
    assert tx2.data == "2026-11-04"
    assert tx2.tipo_ativo == TipoAtivo.FII
    assert tx2.operacao == TipoOperacao.VENDA

    # Verifica conversão para dataclass de engine
    engine_tx1 = tx1.to_engine_transaction()
    assert engine_tx1.ticker == "PETR4"
    assert engine_tx1.quantidade == 100.0
    assert engine_tx1.valor_total == 3850.00


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
    assert nota_extraida.data_pregao == "2026-11-05"
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
