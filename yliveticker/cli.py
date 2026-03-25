import argparse
import sys
import os
import threading
import time
import csv
from datetime import datetime
from collections import deque
from . import YLiveTicker

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
except ImportError:
    Console = None


class Dashboard:
    def __init__(self, tickers, export_file=None):
        self.tickers = list(tickers)
        self.data = {
            t: {"price": 0.0, "change": 0.0, "percent": 0.0, "history": deque(maxlen=20)}
            for t in tickers
        }
        self.status = "Connecting..."
        self.update_count = 0
        self.start_time = time.time()
        self.export_file = export_file
        self.lock = threading.Lock()
        self.yt = None
        self.stop_event = threading.Event()

    def on_ticker(self, ws, msg):
        with self.lock:
            symbol = msg["id"]
            if symbol not in self.data:
                self.data[symbol] = {
                    "price": 0.0, "change": 0.0, "percent": 0.0, "history": deque(maxlen=20)
                }

            self.data[symbol]["price"] = msg["price"]
            self.data[symbol]["change"] = msg["change"]
            self.data[symbol]["percent"] = msg["changePercent"]
            self.data[symbol]["history"].append(msg["price"])

            self.update_count += 1
            self.status = "● Connected"

            if self.export_file:
                with open(self.export_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        symbol,
                        msg["price"],
                        msg["change"],
                        msg["changePercent"]
                    ])

    def on_error(self, error):
        with self.lock:
            self.status = f"○ Error: {error}"

    def on_close(self):
        with self.lock:
            if not self.stop_event.is_set():
                self.status = "○ Connection Closed (Reconnecting...)"

    def get_sparkline(self, history):
        if len(history) < 2:
            return ""
        chars = " ▂▃▄▅▆▇█"
        h_min, h_max = min(history), max(history)
        if h_min == h_max:
            return "      "
        line = ""
        for v in history:
            idx = int((v - h_min) / (h_max - h_min) * (len(chars) - 1))
            line += chars[idx]
        return line

    def generate_layout(self):
        header = Panel(
            Text(
                f"Yahoo! Finance Live Dashboard | {datetime.now().strftime('%H:%M:%S')}",
                justify="center",
                style="bold cyan"
            ),
            style="blue"
        )
        table = Table(expand=True, border_style="dim")
        table.add_column("Symbol", style="bold yellow")
        table.add_column("Price", justify="right", style="bold green")
        table.add_column("Day Change", justify="right")
        table.add_column("Trend", justify="center", style="magenta")

        with self.lock:
            for symbol in sorted(self.tickers):
                d = self.data.get(symbol, {"price": 0, "change": 0, "percent": 0, "history": []})
                if d["price"] > 0:
                    change_str = f"{d['change']:+,.2f} ({d['percent']:+.2f}%)"
                    price_str = f"{d['price']:,.2f}"
                else:
                    change_str = "---"
                    price_str = "---"

                change_style = "bold green" if d["change"] >= 0 else "bold red"
                spark = self.get_sparkline(list(d["history"]))
                table.add_row(symbol, price_str, Text(change_str, style=change_style), spark)

        footer = Panel(Text.assemble(
            ("Status: ", "white"), (self.status, "green" if "Connected" in self.status else "yellow"),
            (" | Updates: ", "white"), (str(self.update_count), "cyan"),
            (" | Tickers: ", "white"), (str(len(self.tickers)), "cyan"),
            (" | Press Ctrl+C to Quit", "bold magenta")
        ), style="blue")

        layout = Layout()
        layout.split_column(Layout(header, size=3), Layout(table), Layout(footer, size=3))
        return layout

    def run_ws(self, trace):
        while not self.stop_event.is_set():
            try:
                with self.lock:
                    current_tickers = list(self.tickers)
                self.yt = YLiveTicker(
                    on_ticker=self.on_ticker,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    ticker_names=current_tickers,
                    enable_socket_trace=trace
                )
            except Exception as e:
                self.on_error(str(e))
                time.sleep(2)

    def stop(self):
        self.stop_event.set()
        if self.yt:
            self.yt.close()


def run_watch(ticker_names, trace, export_file):
    if Console is None:
        print("Rich not installed. Basic mode.")
        YLiveTicker(ticker_names=ticker_names, enable_socket_trace=trace)
        return

    dashboard = Dashboard(ticker_names, export_file)

    original_stderr = sys.stderr
    sys.stderr = open(os.devnull, 'w')

    ws_thread = threading.Thread(target=dashboard.run_ws, args=(trace,), daemon=True)
    ws_thread.start()

    try:
        with Live(dashboard.generate_layout(), screen=True) as live:
            while not dashboard.stop_event.is_set():
                live.update(dashboard.generate_layout())
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.stop()
        sys.stderr = original_stderr


def main():
    parser = argparse.ArgumentParser(description="yliveticker CLI")
    subparsers = parser.add_subparsers(dest="command")
    watch_parser = subparsers.add_parser("watch")
    watch_parser.add_argument("tickers", nargs="+")
    watch_parser.add_argument("--trace", action="store_true")
    watch_parser.add_argument("--export")
    args = parser.parse_args()
    if args.command == "watch":
        run_watch(args.tickers, args.trace, args.export)


if __name__ == "__main__":
    main()
