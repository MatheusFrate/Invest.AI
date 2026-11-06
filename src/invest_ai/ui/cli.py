"""
Interface de Linha de Comando (CLI) Interativa para o Invest.AI.
Permite registrar movimentações em linguagem natural e simular DARF com confirmação humana.
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown

from invest_ai.config import get_active_excel_path
from invest_ai.agent.deps import InvestContext
from invest_ai.agent.agent import transaction_agent, assistant_agent, resolver_modelo_padrao
from invest_ai.agent.schemas import TransactionSchema
from invest_ai.services.quotes_service import fetch_all_quotes

load_dotenv()
console = Console()


def exibir_banner(context: InvestContext):
    """Exibe o cabeçalho inicial do terminal com status do modelo e da planilha."""
    modelo = resolver_modelo_padrao()
    nome_modelo = modelo if isinstance(modelo, str) else getattr(modelo, "model_name", type(modelo).__name__)

    arquivo_planilha = os.path.basename(context.excel_path)
    existe = "[OK] Encontrada" if os.path.exists(context.excel_path) else "[!] Nova (será criada)"

    banner_text = (
        f"[bold cyan]Invest.AI[/bold cyan] [bold white]• AI Copilot (PydanticAI)[/bold white]\n"
        f"[dim]Modelo ativo: [bold green]{nome_modelo}[/bold green] | "
        f"Planilha: [bold yellow]{arquivo_planilha}[/bold yellow] ({existe})[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def exibir_carteira(context: InvestContext):
    """Exibe uma tabela formatada com os ativos atuais em custódia."""
    posicoes = context.obter_posicoes_carteira()
    if not posicoes:
        console.print("[yellow]Sua carteira está vazia ou a planilha ainda não tem movimentações registradas.[/yellow]")
        return

    table = Table(title="📊 Posições em Carteira (Custódia Atual)", header_style="bold magenta")
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Classe", style="white")
    table.add_column("Quantidade", justify="right", style="green")
    table.add_column("Preço Médio", justify="right", style="yellow")
    table.add_column("Total Investido", justify="right", style="bold white")
    table.add_column("Cotação Atual", justify="right", style="cyan")
    table.add_column("Valor Atual", justify="right", style="bold green")

    tickers = list(posicoes.keys())
    cotacoes = fetch_all_quotes(tickers)

    total_geral_investido = 0.0
    total_geral_atual = 0.0

    for ticker, dados in posicoes.items():
        qtd = dados["quantidade"]
        pm = dados["preco_medio"]
        investido = dados["total_investido"]
        total_geral_investido += investido

        quote = cotacoes.get(ticker, {})
        preco_atual = quote.get("price")

        if preco_atual:
            valor_atual = qtd * preco_atual
            total_geral_atual += valor_atual
            str_preco = f"R$ {preco_atual:.2f}"
            str_atual = f"R$ {valor_atual:.2f}"
        else:
            str_preco = "-"
            str_atual = f"R$ {investido:.2f}"
            total_geral_atual += investido

        table.add_row(
            ticker,
            dados["tipo_ativo"].upper(),
            f"{qtd:.2f}",
            f"R$ {pm:.2f}",
            f"R$ {investido:.2f}",
            str_preco,
            str_atual
        )

    console.print(table)
    lucro_total = total_geral_atual - total_geral_investido
    rentabilidade = (lucro_total / total_geral_investido * 100) if total_geral_investido > 0 else 0.0
    cor_rent = "green" if lucro_total >= 0 else "red"

    resumo = (
        f"[bold]Total Investido:[/bold] R$ {total_geral_investido:.2f}  |  "
        f"[bold]Patrimônio Atual:[/bold] R$ {total_geral_atual:.2f}  |  "
        f"[bold]Saldo Global:[/bold] [{cor_rent}]R$ {lucro_total:+.2f} ({rentabilidade:+.2f}%)[/{cor_rent}]"
    )
    console.print(Panel(resumo, border_style="dim"))


def processar_registro_transacao(texto: str, context: InvestContext):
    """Extrai os dados da transação via transaction_agent e salva com aprovação humana."""
    with console.status("[bold green]Agente PydanticAI analisando e validando transação...[/bold green]", spinner="dots"):
        try:
            resultado = transaction_agent.run_sync(texto, deps=context)
            tx: TransactionSchema = resultado.output
        except Exception as e:
            console.print(f"[bold red]Erro ao processar transação:[/bold red] {e}")
            return

    table = Table(title="📝 Transação Extraída e Validada", header_style="bold cyan")
    table.add_column("Campo", style="bold white")
    table.add_column("Valor Validado", style="green")

    table.add_row("Ticker", tx.ticker)
    table.add_row("Tipo de Ativo", tx.tipo_ativo.value.upper())
    table.add_row("Operação", tx.operacao.value.upper())
    table.add_row("Data", tx.data)
    table.add_row("Quantidade", f"{tx.quantidade:.2f}")
    table.add_row("Preço Unitário", f"R$ {tx.valor_unitario:.2f}" if tx.valor_unitario else "-")
    table.add_row("Valor Total", f"R$ {tx.valor_total:.2f}")
    if tx.corretora:
        table.add_row("Corretora", tx.corretora)

    console.print(table)

    confirmar = Confirm.ask("Deseja confirmar e salvar esta movimentação na planilha?", default=True)
    if confirmar:
        engine_tx = tx.to_engine_transaction()
        sucesso = context.salvar_transacao(engine_tx)
        if sucesso:
            console.print("[bold green][OK] Movimentação gravada com sucesso no Excel e carteira atualizada![/bold green]")
        else:
            console.print("[bold red]Falha ao gravar movimentação no arquivo Excel.[/bold red]")
    else:
        console.print("[yellow]Operação cancelada pelo usuário. Nada foi salvo.[/yellow]")


def _formatar_erro_cli(e: Exception) -> str:
    err_str = str(e)
    if "503" in err_str or "high demand" in err_str.lower():
        return (
            "[yellow]⚠️ Alta demanda nos servidores do Google Gemini (Erro 503).[/yellow]\n"
            "[dim]A camada gratuita do Google AI Studio enfrentou pico momentâneo. Aguarde alguns segundos e tente novamente.[/dim]"
        )
    return f"[bold red]Erro:[/bold red] {err_str}"


def processar_consulta_assistente(pergunta: str, context: InvestContext):
    """Envia pergunta analítica ou simulação fiscal para o assistant_agent."""
    with console.status("[bold blue]Consultor Fiscal analisando carteira e regras da B3...[/bold blue]", spinner="dots"):
        try:
            resultado = assistant_agent.run_sync(pergunta, deps=context)
            resposta = resultado.output
        except Exception as e:
            console.print(_formatar_erro_cli(e))
            return

    console.print(Panel(Markdown(resposta), title="🤖 Resposta do Consultor Fiscal", border_style="blue"))


def main():
    """Loop principal de interação com o usuário."""
    excel_path = get_active_excel_path()
    context = InvestContext(excel_path=excel_path)
    context.carregar_dados()

    console.clear()
    exibir_banner(context)

    console.print("\n[bold white]O que você gostaria de fazer?[/bold white]")
    console.print("  [bold cyan]1[/bold cyan] ou digitar comando direto: Registrar Aporte / Venda (ex: 'Comprei 50 PETR4 a 38,50 hoje')")
    console.print("  [bold cyan]2[/bold cyan] ou fazer pergunta: Consultar Carteira / Simular DARF (ex: 'Se eu vender 30 MXRF11 a 11,00 pago imposto?')")
    console.print("  [bold cyan]3[/bold cyan]: Visualizar Posições em Carteira")
    console.print("  [dim]Digite 'sair' para encerrar.[/dim]\n")

    while True:
        try:
            entrada = Prompt.ask("[bold green]invest-ai[/bold green]").replace("\ufeff", "").replace("ï»¿", "").strip()
            if not entrada:
                continue

            if entrada.lower() in ["sair", "exit", "quit", "q"]:
                console.print("[dim]Encerrando Invest.AI Copilot. Bons investimentos![/dim]")
                break

            elif entrada == "3" or entrada.lower() in ["carteira", "posicoes", "posições"]:
                exibir_carteira(context)

            elif entrada == "1":
                comando = Prompt.ask("[cyan]Digite os detalhes da operação (ex: 'Comprei 100 MXRF11 a 9,50 na XP')[/cyan]").strip()
                if comando:
                    processar_registro_transacao(comando, context)

            elif entrada == "2":
                duvida = Prompt.ask("[blue]Digite sua dúvida ou simulação fiscal (ex: 'Se eu vender 50 PETR4 a 40 pago DARF?')[/blue]").strip()
                if duvida:
                    processar_consulta_assistente(duvida, context)

            else:
                palavras_chave_registro = ["comprei", "vendi", "compra", "venda", "aporte", "adicionar"]
                primeira_palavra = entrada.lower().split()[0] if entrada.split() else ""

                if primeira_palavra in palavras_chave_registro or any(entrada.lower().startswith(p) for p in palavras_chave_registro):
                    processar_registro_transacao(entrada, context)
                else:
                    processar_consulta_assistente(entrada, context)

            console.print()

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Interrompido. Até logo![/dim]")
            break
        except Exception as e:
            console.print(f"[bold red]Ocorreu um erro:[/bold red] {e}")


if __name__ == "__main__":
    main()
