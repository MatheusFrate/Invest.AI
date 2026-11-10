"""
Serviço de extração de texto de documentos PDF (Notas de Corretagem SINACOR/B3).
Utiliza pypdf de forma segura e resiliente, tratando arquivos protegidos por senha e corrompidos.
"""

import os
from pypdf import PdfReader
from pypdf.errors import PdfReadError, FileNotDecryptedError


def extrair_texto_pdf(caminho_pdf: str) -> str:
    """
    Lê um arquivo PDF e extrai todo o conteúdo textual de suas páginas.

    Args:
        caminho_pdf: Caminho completo ou relativo para o arquivo PDF.

    Returns:
        String contendo o texto extraído de todas as páginas.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se o arquivo estiver protegido por senha, corrompido ou sem texto legível.
    """
    if not os.path.exists(caminho_pdf):
        raise FileNotFoundError(f"Arquivo PDF não encontrado: '{caminho_pdf}'.")

    try:
        reader = PdfReader(caminho_pdf)
    except (PdfReadError, Exception) as e:
        raise ValueError(f"Não foi possível abrir o arquivo PDF. Arquivo possivelmente corrompido: {e}")

    # Tratamento de senha / criptografia
    if getattr(reader, "is_encrypted", False):
        try:
            decrypt_result = reader.decrypt("")
            # 0 indica falha de decriptografia com senha vazia
            if decrypt_result == 0 or getattr(reader, "is_encrypted", False):
                raise ValueError("O arquivo PDF está protegido por senha.")
        except (FileNotDecryptedError, Exception):
            raise ValueError("O arquivo PDF está protegido por senha.")

    textos_paginas = []
    try:
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                textos_paginas.append(page_text.strip())
    except Exception as e:
        raise ValueError(f"Erro ao processar conteúdo das páginas do PDF: {e}")

    texto_completo = "\n\n".join(textos_paginas).strip()

    if not texto_completo:
        raise ValueError(
            "Não foi possível extrair texto do PDF. O arquivo pode estar vazio ou "
            "conter apenas imagens digitalizadas/escaneadas (sem camada de texto OCR)."
        )

    return texto_completo
