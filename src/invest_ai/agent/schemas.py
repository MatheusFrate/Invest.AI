"""
Schemas de validação de dados com Pydantic v2 para operações financeiras da B3.
Garante tipagem estrita, coerência matemática e compatibilidade direta com core/engine.py.
"""

from datetime import date, datetime
from enum import Enum
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from invest_ai.core.engine import Transaction


class TipoOperacao(str, Enum):
    COMPRA = "compra"
    VENDA = "venda"


class TipoAtivo(str, Enum):
    ACAO = "ação"
    FII = "fii"
    ETF = "etf"
    BDR = "bdr"


class TransactionSchema(BaseModel):
    """
    Schema estrito para extração e validação de uma transação de investimento na B3.
    """
    ticker: str = Field(
        ...,
        description="Código do ativo na B3 (ex: PETR4, VALE3, MXRF11, IVVB11). Em maiúsculas."
    )
    tipo_ativo: TipoAtivo = Field(
        default=TipoAtivo.ACAO,
        description="Tipo do ativo: 'ação', 'fii', 'etf' ou 'bdr'."
    )
    operacao: TipoOperacao = Field(
        default=TipoOperacao.COMPRA,
        description="Operação realizada: 'compra' ou 'venda'."
    )
    data: str = Field(
        default_factory=lambda: date.today().strftime("%d/%m/%Y"),
        description="Data da transação no formato DD/MM/AAAA."
    )
    quantidade: float = Field(
        ...,
        gt=0,
        description="Quantidade de cotas ou ações negociadas (deve ser maior que zero)."
    )
    valor_unitario: Optional[float] = Field(
        default=None,
        ge=0,
        description="Preço pago por cota/ação individual (R$)."
    )
    valor_total: Optional[float] = Field(
        default=None,
        ge=0,
        description="Valor total financeiro da operação (R$)."
    )
    corretora: Optional[str] = Field(
        default=None,
        description="Nome da corretora ou plataforma utilizada (ex: NuInvest, XP, Rico, Clear)."
    )
    observacao: Optional[str] = Field(
        default=None,
        description="Observações ou notas relevantes da negociação."
    )
    cotacao_mercado: Optional[float] = Field(
        default=None,
        description="Cotação atual do ativo na B3 obtida como referência de mercado."
    )
    alerta_discrepancia: Optional[str] = Field(
        default=None,
        description="Mensagem de alerta caso o preço informado divirja significativamente da cotação de mercado."
    )

    @field_validator("ticker")
    @classmethod
    def validar_e_formatar_ticker(cls, v: str) -> str:
        clean = v.strip().upper()
        if not re.match(r"^[A-Z0-9]{4,6}$", clean):
            raise ValueError(
                f"Ticker '{clean}' inválido. Esperado formato B3 (ex: PETR4, VALE3, MXRF11)."
            )
        return clean

    @field_validator("data")
    @classmethod
    def formatar_data(cls, v: str) -> str:
        v_clean = v.strip()
        if "/" in v_clean:
            try:
                dt = datetime.strptime(v_clean, "%d/%m/%Y")
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass
        try:
            dt = datetime.strptime(v_clean, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            raise ValueError(
                f"Data '{v}' em formato inválido. Use 'DD/MM/AAAA' ou 'YYYY-MM-DD'."
            )

    @model_validator(mode="after")
    def validar_e_completar_matematica(self) -> "TransactionSchema":
        qtd = self.quantidade
        unit = self.valor_unitario
        total = self.valor_total

        if self.ticker.endswith("11") and self.tipo_ativo == TipoAtivo.ACAO:
            self.tipo_ativo = TipoAtivo.FII
        elif self.ticker.endswith("34"):
            self.tipo_ativo = TipoAtivo.BDR

        if unit is None and total is None:
            raise ValueError(
                "É obrigatório informar ao menos o 'valor_unitario' ou o 'valor_total'."
            )

        if total is None and unit is not None:
            self.valor_total = round(qtd * unit, 2)
        elif unit is None and total is not None:
            self.valor_unitario = round(total / qtd, 4)
        elif unit is not None and total is not None:
            calculado = qtd * unit
            if abs(calculado - total) > 0.05:
                raise ValueError(
                    f"Inconsistência matemática detectada: Quantidade ({qtd}) × Unitário (R$ {unit:.2f}) "
                    f"= R$ {calculado:.2f}, mas o valor total informado foi R$ {total:.2f}. "
                    f"Por favor, revise os valores."
                )

        return self

    def to_engine_transaction(self) -> Transaction:
        """
        Converte este schema validado para a dataclass Transaction do core/engine.py.
        """
        return Transaction(
            data=self.data,
            ticker=self.ticker,
            tipo_ativo=self.tipo_ativo.value,
            operacao=self.operacao.value,
            quantidade=self.quantidade,
            valor_total=self.valor_total or 0.0,
            valor_unitario=self.valor_unitario or 0.0
        )


class TaxSimulationResponse(BaseModel):
    """
    Schema de resposta para uma consulta ou simulação fiscal (DARF).
    """
    ticker: str
    quantidade_simulada: float
    preco_venda_unitario: float
    preco_medio_aquisicao: float
    lucro_prejuizo_total: float
    aliquota_ir: float
    imposto_devido: float
    isento: bool
    justificativa: str = Field(
        ...,
        description="Explicação clara das regras tributárias aplicadas (isenção 20k para ações, 20% para FIIs, etc.)."
    )


class BrokerageNoteSchema(BaseModel):
    """
    Schema para leitura e estruturação de Notas de Corretagem da B3 (padrão SINACOR).
    Agrupa os dados do pregão, corretora, taxas da B3/corretagem e operações individuais.
    """
    numero_nota: Optional[str] = Field(
        default=None,
        description="Número da nota de corretagem identificado no cabeçalho."
    )
    data_pregao: str = Field(
        ...,
        description="Data do pregão da nota no formato DD/MM/AAAA."
    )
    corretora: Optional[str] = Field(
        default=None,
        description="Nome ou razão social da corretora emissora (ex: XP, Clear, BTG, NuInvest, Rico)."
    )
    total_custos_emolumentos: float = Field(
        default=0.0,
        ge=0.0,
        description="Soma total das taxas de liquidação, emolumentos B3, taxas de corretagem e tributos (ISS/PIS/COFINS)."
    )
    transacoes: list[TransactionSchema] = Field(
        default_factory=list,
        description="Lista de operações individuais (compra/venda) encontradas na nota."
    )

    @field_validator("data_pregao")
    @classmethod
    def formatar_data_pregao(cls, v: str) -> str:
        v_clean = v.strip()
        if "/" in v_clean:
            try:
                dt = datetime.strptime(v_clean, "%d/%m/%Y")
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass
        try:
            dt = datetime.strptime(v_clean, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            raise ValueError(
                f"Data do pregão '{v}' em formato inválido. Use 'DD/MM/AAAA' ou 'YYYY-MM-DD'."
            )

    @model_validator(mode="after")
    def sincronizar_dados_transacoes(self) -> "BrokerageNoteSchema":
        hoje_br = date.today().strftime("%d/%m/%Y")
        for tx in self.transacoes:
            if not tx.corretora and self.corretora:
                tx.corretora = self.corretora
            if self.data_pregao and (not tx.data or tx.data == hoje_br):
                tx.data = self.data_pregao
        return self

    def aplicar_rateio_custos(self) -> list[TransactionSchema]:
        """
        Rateia proporcionalmente `total_custos_emolumentos` entre as transações da nota
        conforme regra da Receita Federal (soma nas compras, deduz nas vendas).
        """
        if self.total_custos_emolumentos <= 0 or not self.transacoes:
            return [tx.model_copy() for tx in self.transacoes]

        volume_total = sum(tx.valor_total or 0.0 for tx in self.transacoes)
        if volume_total <= 0:
            return [tx.model_copy() for tx in self.transacoes]

        total_custos_centavos = round(self.total_custos_emolumentos * 100)
        restante_centavos = total_custos_centavos
        resultado: list[TransactionSchema] = []

        for idx, tx in enumerate(self.transacoes):
            valor_bruto = tx.valor_total or 0.0
            if idx == len(self.transacoes) - 1:
                taxa_centavos = restante_centavos
            else:
                peso = valor_bruto / volume_total
                taxa_centavos = min(restante_centavos, round(total_custos_centavos * peso))
                restante_centavos -= taxa_centavos

            taxa_rateada = round(taxa_centavos / 100.0, 2)

            if tx.operacao == TipoOperacao.COMPRA:
                novo_valor_total = round(valor_bruto + taxa_rateada, 2)
            else:
                novo_valor_total = round(max(0.0, valor_bruto - taxa_rateada), 2)

            novo_valor_unitario = round(novo_valor_total / tx.quantidade, 4)
            nota_taxa = f"Taxa rateada: R$ {taxa_rateada:.2f}"
            nova_obs = f"{tx.observacao} | {nota_taxa}" if tx.observacao else nota_taxa

            resultado.append(
                tx.model_copy(
                    update={
                        "valor_total": novo_valor_total,
                        "valor_unitario": novo_valor_unitario,
                        "observacao": nova_obs,
                    }
                )
            )

        return resultado

    def to_engine_transactions_com_rateio(self) -> list[Transaction]:
        """Converte as transações da nota para o motor já com o rateio de custos aplicado."""
        return [tx.to_engine_transaction() for tx in self.aplicar_rateio_custos()]


class TipoEventoCorporativo(str, Enum):
    DESDOBRAMENTO = "desdobramento"
    AGRUPAMENTO = "agrupamento"
    CONVERSAO = "conversao"


def _validar_ticker_b3(v: str) -> str:
    clean = v.strip().upper()
    if not re.match(r"^[A-Z0-9]{4,6}$", clean):
        raise ValueError(
            f"Ticker '{clean}' inválido. Esperado formato B3 (ex: PETR4, VALE3, IRDM11)."
        )
    return clean


def _formatar_data_br_schema(v: str) -> str:
    v_clean = v.strip()
    if "/" in v_clean:
        try:
            dt = datetime.strptime(v_clean, "%d/%m/%Y")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    try:
        dt = datetime.strptime(v_clean, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        raise ValueError(
            f"Data '{v}' em formato inválido. Use 'DD/MM/AAAA' ou 'YYYY-MM-DD'."
        )


class CorporateEventSchema(BaseModel):
    """
    Schema estrito para eventos corporativos na B3:
    desdobramento (split), agrupamento (inplit) e conversão/incorporação de ticker.
    """
    tipo_evento: TipoEventoCorporativo = Field(
        ...,
        description="Tipo do evento corporativo: 'desdobramento', 'agrupamento' ou 'conversao'."
    )
    ticker_origem: str = Field(
        ...,
        description="Código do ativo afetado ou ticker de origem na B3 (ex: XPML11, MGLU3, IRDM11)."
    )
    ticker_destino: Optional[str] = Field(
        default=None,
        description="Novo ticker em caso de conversão/incorporação (ex: IRIM11). Nulo para split/inplit."
    )
    fator: float = Field(
        default=1.0,
        gt=0,
        description=(
            "Fator de multiplicação da quantidade (> 0). "
            "Ex: 10.0 para desdobramento 1:10; 0.1 para agrupamento 10:1; 1.0 para conversão 1:1."
        )
    )
    data: str = Field(
        default_factory=lambda: date.today().strftime("%d/%m/%Y"),
        description="Data do evento corporativo no formato DD/MM/AAAA."
    )
    tipo_ativo: TipoAtivo = Field(
        default=TipoAtivo.ACAO,
        description="Tipo do ativo: 'ação', 'fii', 'etf' ou 'bdr'."
    )
    observacao: Optional[str] = Field(
        default=None,
        description="Observações adicionais sobre o evento corporativo."
    )

    @field_validator("ticker_origem")
    @classmethod
    def validar_ticker_origem(cls, v: str) -> str:
        return _validar_ticker_b3(v)

    @field_validator("ticker_destino")
    @classmethod
    def validar_ticker_destino(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        return _validar_ticker_b3(v)

    @field_validator("data")
    @classmethod
    def validar_data_evento(cls, v: str) -> str:
        return _formatar_data_br_schema(v)

    @model_validator(mode="after")
    def validar_regras_evento(self) -> "CorporateEventSchema":
        ticker_ref = self.ticker_destino or self.ticker_origem
        if ticker_ref.endswith("11") and self.tipo_ativo == TipoAtivo.ACAO:
            self.tipo_ativo = TipoAtivo.FII
        elif ticker_ref.endswith("34"):
            self.tipo_ativo = TipoAtivo.BDR

        if self.tipo_evento == TipoEventoCorporativo.CONVERSAO:
            if not self.ticker_destino:
                raise ValueError(
                    "Para eventos de conversão/incorporação, é obrigatório informar o 'ticker_destino'."
                )
            if self.ticker_destino == self.ticker_origem:
                raise ValueError(
                    "O 'ticker_destino' deve ser diferente do 'ticker_origem' em uma conversão."
                )
        return self

    def to_engine_transaction(self) -> Transaction:
        """
        Converte este evento corporativo para a dataclass Transaction compatível com o Excel e engine.py.
        """
        ticker_tx = (
            f"{self.ticker_origem}->{self.ticker_destino}"
            if self.tipo_evento == TipoEventoCorporativo.CONVERSAO
            else self.ticker_origem
        )
        return Transaction(
            data=self.data,
            ticker=ticker_tx,
            tipo_ativo=self.tipo_ativo.value,
            operacao=self.tipo_evento.value,
            quantidade=self.fator,
            valor_total=0.0,
            valor_unitario=0.0,
        )



