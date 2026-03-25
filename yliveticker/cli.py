import argparse
import sys
from . import YLiveTicker

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
except ImportError:
    Console = None


def main():
    parser = argparse.ArgumentParser(description="yliveticker CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch live ticker updates")
    watch_parser.add_argument("tickers", nargs="+", help="Ticker symbols to watch")
    watch_parser.add_argument("--trace", action="store_true", help="Enable socket trace")

    args = parser.parse_args()

    if args.command == "watch":
        run_watch(args.tickers, args.trace)
    else:
        parser.print_help()


def run_watch(ticker_names, trace):
    if Console is None:
        # Fallback to basic print if rich is not installed
        print(f"Watching {ticker_names} (install 'rich' for a better experience)")
        YLiveTicker(ticker_names=ticker_names, enable_socket_trace=trace)
        return

    console = Console()
    data_store = {ticker: {"price": "---", "change": "---"} for ticker in ticker_names}

    def generate_table():
        table = Table(title="Yahoo! Finance Live Ticker")
        table.add_column("Symbol", style="cyan")
        table.add_column("Price", justify="right", style="green")
        table.add_column("Change", justify="right")

        for symbol, data in data_store.items():
            change = str(data["change"])
            change_style = "green" if "-" not in change and change != "---" else "red"
            table.add_row(symbol, str(data["price"]), change, style=change_style)
        return table

    def on_ticker(ws, msg):
        symbol = msg["id"]
        data_store[symbol] = {
            "price": msg["price"],
            "change": f"{msg['change']} ({msg['changePercent']:.2f}%)"
        }

    with Live(generate_table(), refresh_per_second=4) as live:
        # We need a custom on_ticker that updates the live display
        def on_ticker_rich(ws, msg):
            on_ticker(ws, msg)
            live.update(generate_table())

        try:
            YLiveTicker(
                on_ticker=on_ticker_rich,
                ticker_names=ticker_names,
                enable_socket_trace=trace
            )
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
