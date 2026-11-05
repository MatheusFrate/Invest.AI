"""
Módulo de cálculo de investimentos e apuração de Imposto de Renda.
Suporta cálculo de preço médio ponderado, apuração de lucros/prejuízos,
compensação de prejuízos e cálculo do imposto devido (DARF).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class Transaction:
    id: Optional[int] = None
    data: str = ""  # YYYY-MM-DD ou DD/MM/YYYY
    ticker: str = ""
    tipo_ativo: str = "fii"  # 'fii', 'ação', 'etf'
    operacao: str = "compra"  # 'compra' ou 'venda'
    quantidade: float = 0.0
    valor_total: float = 0.0
    valor_unitario: float = 0.0

    def __post_init__(self):
        self.ticker = self.ticker.strip().upper()
        self.tipo_ativo = self.tipo_ativo.strip().lower()
        self.operacao = self.operacao.strip().lower()
        if self.quantidade > 0 and self.valor_unitario == 0.0 and self.valor_total > 0.0:
            self.valor_unitario = self.valor_total / self.quantidade
        elif self.valor_total == 0.0 and self.quantidade > 0 and self.valor_unitario > 0:
            self.valor_total = self.quantidade * self.valor_unitario


@dataclass
class SaleResult:
    id: int
    data: str
    ticker: str
    tipo_ativo: str
    quantidade_vendida: float
    preco_venda_unitario: float
    valor_venda_total: float
    preco_medio_compra: float
    custo_total: float
    lucro_prejuizo: float  # valor_venda_total - custo_total
    mes_ano: str  # MM/YYYY


@dataclass
class MonthlyTaxReport:
    mes_ano: str
    tipo_ativo: str  # 'fii' ou 'ação'
    vendas_total: float = 0.0
    resultado_liquido: float = 0.0  # soma dos lucros e prejuízos do mês
    prejuizo_anterior_compensado: float = 0.0
    base_calculo: float = 0.0  # lucro tributável após abater prejuízos
    aliquota: float = 0.20  # 20% para FIIs, 15% para ações swing trade
    imposto_devido: float = 0.0
    prejuizo_restante_acumulado: float = 0.0
    isento: bool = False  # Para ações com vendas <= R$ 20.000 no mês


class InvestmentEngine:
    def __init__(self):
        self.transactions: List[Transaction] = []

    def set_transactions(self, txs: List[Transaction]):
        self.transactions = txs

    def calculate(self):
        """
        Calcula a carteira atual (preço médio e quantidade),
        o histórico de vendas com lucro/prejuízo,
        e a apuração mensal de IR.
        """
        # Estado atual da carteira: ticker -> {'quantidade': float, 'custo_total': float, 'tipo_ativo': str}
        wallet: Dict[str, Dict] = {}
        sales: List[SaleResult] = []

        for idx, tx in enumerate(self.transactions):
            ticker = tx.ticker
            if ticker not in wallet:
                wallet[ticker] = {
                    'quantidade': 0.0,
                    'custo_total': 0.0,
                    'preco_medio': 0.0,
                    'tipo_ativo': tx.tipo_ativo
                }

            item = wallet[ticker]

            if tx.operacao == 'compra':
                item['quantidade'] += tx.quantidade
                item['custo_total'] += tx.valor_total
                if item['quantidade'] > 0:
                    item['preco_medio'] = item['custo_total'] / item['quantidade']
                item['tipo_ativo'] = tx.tipo_ativo

            elif tx.operacao == 'venda':
                qtd_venda = tx.quantidade
                pm = item['preco_medio']
                custo_venda = qtd_venda * pm
                resultado = tx.valor_total - custo_venda

                # Extrair mês/ano
                mes_ano = "Geral"
                if tx.data:
                    try:
                        # Tenta formatos DD/MM/YYYY ou YYYY-MM-DD
                        if "/" in tx.data:
                            partes = tx.data.split("/")
                            if len(partes) == 3:
                                mes_ano = f"{int(partes[1]):02d}/{partes[2]}"
                        elif "-" in tx.data:
                            partes = tx.data.split("-")
                            if len(partes) == 3:
                                mes_ano = f"{int(partes[1]):02d}/{partes[0]}"
                    except Exception:
                        pass

                sale_res = SaleResult(
                    id=idx + 1,
                    data=tx.data,
                    ticker=ticker,
                    tipo_ativo=tx.tipo_ativo,
                    quantidade_vendida=qtd_venda,
                    preco_venda_unitario=tx.valor_unitario,
                    valor_venda_total=tx.valor_total,
                    preco_medio_compra=pm,
                    custo_total=custo_venda,
                    lucro_prejuizo=resultado,
                    mes_ano=mes_ano
                )
                sales.append(sale_res)

                # Atualiza quantidade restante e custo proporcional
                item['quantidade'] -= qtd_venda
                if item['quantidade'] <= 0.0001:
                    item['quantidade'] = 0.0
                    item['custo_total'] = 0.0
                    # Preço médio pode ser mantido ou zerado
                else:
                    item['custo_total'] = item['quantidade'] * pm

        # Filtra ativos com quantidade > 0 na carteira
        active_positions = {}
        for ticker, data in wallet.items():
            if data['quantidade'] > 0:
                active_positions[ticker] = {
                    'ticker': ticker,
                    'tipo_ativo': data['tipo_ativo'],
                    'quantidade': data['quantidade'],
                    'preco_medio': data['preco_medio'],
                    'total_investido': data['custo_total']
                }

        # Apuração de Imposto (separado por classe de ativo: FIIs e Ações)
        # Regra FII: 20% sobre lucro líquido mensal, compensa prejuízos passados de FII
        # Regra Ação: Vendas até 20k no mês são isentas (exceto day trade), senão 15%
        tax_reports = self._calculate_taxes(sales)

        return {
            'wallet': active_positions,
            'sales': sales,
            'tax_reports': tax_reports
        }

    def _calculate_taxes(self, sales: List[SaleResult]) -> List[MonthlyTaxReport]:
        if not sales:
            return []

        # Agrupar por mes_ano e tipo_ativo
        df_sales = pd.DataFrame([vars(s) for s in sales])
        if df_sales.empty:
            return []

        # Manter ordem cronológica dos meses encontrados
        meses_unicos = df_sales['mes_ano'].unique().tolist()

        reports = []
        prejuizo_acumulado_fii = 0.0
        prejuizo_acumulado_acao = 0.0
        prejuizo_acumulado_etf = 0.0

        for mes in meses_unicos:
            for tipo in ['fii', 'ação', 'etf']:
                subset = df_sales[(df_sales['mes_ano'] == mes) & (df_sales['tipo_ativo'] == tipo)]
                if subset.empty:
                    continue

                total_vendas = subset['valor_venda_total'].sum()
                resultado_mes = subset['lucro_prejuizo'].sum()

                rep = MonthlyTaxReport(
                    mes_ano=mes,
                    tipo_ativo=tipo,
                    vendas_total=total_vendas,
                    resultado_liquido=resultado_mes
                )

                if tipo == 'fii':
                    prejuizo_acum = prejuizo_acumulado_fii
                    aliquota = 0.20
                elif tipo == 'ação':
                    prejuizo_acum = prejuizo_acumulado_acao
                    aliquota = 0.15
                else:  # etf
                    prejuizo_acum = prejuizo_acumulado_etf
                    aliquota = 0.15

                rep.aliquota = aliquota

                if tipo == 'ação' and total_vendas <= 20000 and resultado_mes > 0:
                    # Isenção de 20k exclusiva para ações comuns em swing trade
                    rep.isento = True
                    rep.base_calculo = 0.0
                    rep.imposto_devido = 0.0
                    rep.prejuizo_restante_acumulado = prejuizo_acum
                else:
                    if resultado_mes < 0:
                        # Mês com prejuízo
                        prejuizo_acum += abs(resultado_mes)
                        rep.base_calculo = 0.0
                        rep.imposto_devido = 0.0
                        rep.prejuizo_restante_acumulado = prejuizo_acum
                    else:
                        # Mês com lucro
                        if prejuizo_acum > 0:
                            if resultado_mes >= prejuizo_acum:
                                compensado = prejuizo_acum
                                base = resultado_mes - compensado
                                prejuizo_acum = 0.0
                            else:
                                compensado = resultado_mes
                                base = 0.0
                                prejuizo_acum -= compensado
                            rep.prejuizo_anterior_compensado = compensado
                        else:
                            base = resultado_mes

                        rep.base_calculo = base
                        rep.imposto_devido = base * aliquota
                        rep.prejuizo_restante_acumulado = prejuizo_acum

                if tipo == 'fii':
                    prejuizo_acumulado_fii = prejuizo_acum
                elif tipo == 'ação':
                    prejuizo_acumulado_acao = prejuizo_acum
                else:
                    prejuizo_acumulado_etf = prejuizo_acum

                reports.append(rep)

        return reports
