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
        prejuizo_acumulado_bdr = 0.0

        for mes in meses_unicos:
            for tipo in ['fii', 'ação', 'etf', 'bdr']:
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
                elif tipo == 'etf':
                    prejuizo_acum = prejuizo_acumulado_etf
                    aliquota = 0.15
                else:  # bdr
                    prejuizo_acum = prejuizo_acumulado_bdr
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
                elif tipo == 'etf':
                    prejuizo_acumulado_etf = prejuizo_acum
                else:
                    prejuizo_acumulado_bdr = prejuizo_acum

                reports.append(rep)

        return reports

    @staticmethod
    def _parse_tx_date(data_str: str) -> Optional[datetime]:
        """Converte string de data (DD/MM/YYYY ou YYYY-MM-DD) para datetime."""
        if not data_str or not isinstance(data_str, str):
            return None
        s = data_str.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _mapear_rfb(tipo_ativo: str) -> Dict[str, str]:
        """Retorna Grupo e Código oficiais da Receita Federal para a ficha Bens e Direitos."""
        tipo = (tipo_ativo or "").strip().lower()
        mapa = {
            "ação": {
                "grupo": "03 - Participações Societárias",
                "codigo": "01 - Ações (inclusive as listadas em bolsa)",
            },
            "acao": {
                "grupo": "03 - Participações Societárias",
                "codigo": "01 - Ações (inclusive as listadas em bolsa)",
            },
            "fii": {
                "grupo": "07 - Fundos",
                "codigo": "03 - Fundos de Investimento Imobiliário (FII)",
            },
            "etf": {
                "grupo": "07 - Fundos",
                "codigo": "09 - Demais Fundos de Índice de Mercado (ETF)",
            },
            "bdr": {
                "grupo": "04 - Aplicações e Investimentos",
                "codigo": "04 - Ativos negociados em bolsa no exterior / BDRs",
            },
        }
        return mapa.get(
            tipo,
            {
                "grupo": "03 - Participações Societárias",
                "codigo": "99 - Outras participações societárias",
            },
        )

    def gerar_snapshot_anual_irpf(self, ano: int) -> Dict:
        """
        Gera o snapshot determinístico para a Declaração Anual de IRPF do ano-calendário `ano`.
        Calcula posições exatas em 31/12/{ano-1} e 31/12/{ano}, resumo mensal de Renda Variável
        do ano e saldo final de prejuízo acumulado a compensar.
        """
        limite_anterior = datetime(ano - 1, 12, 31, 23, 59, 59)
        limite_atual = datetime(ano, 12, 31, 23, 59, 59)

        # Ordena cronologicamente todas as transações com data válida até 31/12/{ano}
        txs_ordenadas = []
        for idx, tx in enumerate(self.transactions):
            dt = self._parse_tx_date(tx.data)
            if dt is not None and dt <= limite_atual:
                txs_ordenadas.append((dt, idx, tx))
        txs_ordenadas.sort(key=lambda x: (x[0], x[1]))

        wallet: Dict[str, Dict] = {}
        wallet_anterior: Optional[Dict[str, Dict]] = None
        sales_ate_ano: List[SaleResult] = []

        for dt, idx, tx in txs_ordenadas:
            if wallet_anterior is None and dt > limite_anterior:
                wallet_anterior = {
                    t: dict(d) for t, d in wallet.items()
                }

            ticker = tx.ticker
            if ticker not in wallet:
                wallet[ticker] = {
                    "quantidade": 0.0,
                    "custo_total": 0.0,
                    "preco_medio": 0.0,
                    "tipo_ativo": tx.tipo_ativo,
                }

            item = wallet[ticker]
            if tx.operacao == "compra":
                item["quantidade"] += tx.quantidade
                item["custo_total"] += tx.valor_total
                if item["quantidade"] > 0:
                    item["preco_medio"] = item["custo_total"] / item["quantidade"]
                item["tipo_ativo"] = tx.tipo_ativo
            elif tx.operacao == "venda":
                qtd_venda = tx.quantidade
                pm = item["preco_medio"]
                custo_venda = qtd_venda * pm
                resultado = tx.valor_total - custo_venda
                mes_ano = f"{dt.month:02d}/{dt.year}"

                sales_ate_ano.append(
                    SaleResult(
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
                        mes_ano=mes_ano,
                    )
                )

                item["quantidade"] -= qtd_venda
                if item["quantidade"] <= 0.0001:
                    item["quantidade"] = 0.0
                    item["custo_total"] = 0.0
                    item["preco_medio"] = 0.0
                else:
                    item["custo_total"] = item["quantidade"] * pm

        if wallet_anterior is None:
            wallet_anterior = {t: dict(d) for t, d in wallet.items()}

        # Ficha Bens e Direitos: ativos com saldo > 0 em 31/12/{ano-1} ou 31/12/{ano}
        todos_tickers = sorted(set(wallet_anterior.keys()) | set(wallet.keys()))
        bens_e_direitos = []
        for ticker in todos_tickers:
            ant = wallet_anterior.get(ticker, {})
            atu = wallet.get(ticker, {})

            qtd_ant = round(ant.get("quantidade", 0.0), 6)
            pm_ant = round(ant.get("preco_medio", 0.0), 6) if qtd_ant > 0 else 0.0
            custo_ant = round(ant.get("custo_total", 0.0), 2) if qtd_ant > 0 else 0.0

            qtd_atu = round(atu.get("quantidade", 0.0), 6)
            pm_atu = round(atu.get("preco_medio", 0.0), 6) if qtd_atu > 0 else 0.0
            custo_atu = round(atu.get("custo_total", 0.0), 2) if qtd_atu > 0 else 0.0

            if qtd_ant <= 0 and qtd_atu <= 0:
                continue

            tipo_ativo = atu.get("tipo_ativo") or ant.get("tipo_ativo") or "ação"
            rfb = self._mapear_rfb(tipo_ativo)
            bens_e_direitos.append(
                {
                    "ticker": ticker,
                    "tipo_ativo": tipo_ativo,
                    "grupo_rfb": rfb["grupo"],
                    "codigo_rfb": rfb["codigo"],
                    "quantidade_ano_anterior": qtd_ant,
                    "preco_medio_ano_anterior": pm_ant,
                    "custo_total_ano_anterior": custo_ant,
                    "quantidade_ano_atual": qtd_atu,
                    "preco_medio_ano_atual": pm_atu,
                    "custo_total_ano_atual": custo_atu,
                }
            )

        # Apuração de Renda Variável acumulada até 31/12/{ano}
        tax_reports = self._calculate_taxes(sales_ate_ano)
        prejuizo_final = {"acao": 0.0, "fii": 0.0, "etf": 0.0, "bdr": 0.0}
        meses_ano: Dict[str, Dict] = {}
        sufixo_ano = f"/{ano}"

        for rep in tax_reports:
            if rep.tipo_ativo in ("ação", "acao"):
                prejuizo_final["acao"] = round(rep.prejuizo_restante_acumulado, 2)
            elif rep.tipo_ativo == "fii":
                prejuizo_final["fii"] = round(rep.prejuizo_restante_acumulado, 2)
            elif rep.tipo_ativo == "etf":
                prejuizo_final["etf"] = round(rep.prejuizo_restante_acumulado, 2)
            elif rep.tipo_ativo == "bdr":
                prejuizo_final["bdr"] = round(rep.prejuizo_restante_acumulado, 2)

            if not rep.mes_ano.endswith(sufixo_ano):
                continue

            if rep.mes_ano not in meses_ano:
                meses_ano[rep.mes_ano] = {
                    "mes_ano": rep.mes_ano,
                    "vendas_acoes": 0.0,
                    "resultado_acoes": 0.0,
                    "lucro_isento_acoes": 0.0,
                    "darf_acoes": 0.0,
                    "vendas_fiis": 0.0,
                    "resultado_fiis": 0.0,
                    "darf_fiis": 0.0,
                    "vendas_etfs": 0.0,
                    "resultado_etfs": 0.0,
                    "darf_etfs": 0.0,
                    "vendas_bdrs": 0.0,
                    "resultado_bdrs": 0.0,
                    "darf_bdrs": 0.0,
                    "darf_total": 0.0,
                }

            entry = meses_ano[rep.mes_ano]
            if rep.tipo_ativo in ("ação", "acao"):
                entry["vendas_acoes"] = round(rep.vendas_total, 2)
                entry["resultado_acoes"] = round(rep.resultado_liquido, 2)
                if rep.isento and rep.resultado_liquido > 0:
                    entry["lucro_isento_acoes"] = round(rep.resultado_liquido, 2)
                entry["darf_acoes"] = round(rep.imposto_devido, 2)
            elif rep.tipo_ativo == "fii":
                entry["vendas_fiis"] = round(rep.vendas_total, 2)
                entry["resultado_fiis"] = round(rep.resultado_liquido, 2)
                entry["darf_fiis"] = round(rep.imposto_devido, 2)
            elif rep.tipo_ativo == "etf":
                entry["vendas_etfs"] = round(rep.vendas_total, 2)
                entry["resultado_etfs"] = round(rep.resultado_liquido, 2)
                entry["darf_etfs"] = round(rep.imposto_devido, 2)
            elif rep.tipo_ativo == "bdr":
                entry["vendas_bdrs"] = round(rep.vendas_total, 2)
                entry["resultado_bdrs"] = round(rep.resultado_liquido, 2)
                entry["darf_bdrs"] = round(rep.imposto_devido, 2)

            entry["darf_total"] = round(
                entry["darf_acoes"] + entry["darf_fiis"] + entry["darf_etfs"] + entry["darf_bdrs"], 2
            )

        return {
            "ano": ano,
            "ano_anterior": ano - 1,
            "bens_e_direitos": bens_e_direitos,
            "renda_variavel": {
                "meses": list(meses_ano.values()),
                "prejuizo_acumulado_final": prejuizo_final,
            },
        }
