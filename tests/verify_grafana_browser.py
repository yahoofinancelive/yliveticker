"""Check an empty-start dashboard in a real browser (requires Playwright)."""

import argparse
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).parents[1]


def main():
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-collector", action="store_true")
    parser.add_argument("--screenshot", default="junit/grafana-dashboard.png")
    args = parser.parse_args()
    url = os.getenv("GRAFANA_URL", "http://localhost:3000")
    with sync_playwright() as playwright:
        executable = os.getenv("CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(
            executable_path=executable, args=["--no-sandbox"],
        )
        pages = []
        errors = []
        queries = []
        for path in ("/", "/d/yliveticker-dashboard"):
            page = browser.new_page(viewport={"width": 1440, "height": 1300})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def record(request):
                if "/api/ds/query" in request.url:
                    queries.extend(request.post_data_json.get("queries", []))

            page.on("request", record)
            page.goto(url + path, wait_until="domcontentloaded")
            page.get_by_text("Stored ticks (selected range)", exact=True).wait_for()
            page.get_by_text("Waiting for ticks", exact=True).wait_for()
            body = page.locator("body").inner_text()
            assert "Waiting for ticks" in body, "This test must open before the first collector tick"
            # Grafana lazily renders repeated panels. Scroll once to prove that a
            # configured sleeping ticker exists as an intentional empty chart.
            page.mouse.wheel(0, 10000)
            page.get_by_role("heading", name="SYNTH-NVDA · Synthetic test · United States: price", exact=True).wait_for()
            body = page.locator("body").inner_text()
            assert "SYNTH-NVDA · Synthetic test · United States: price" in body and "No data" in body, body
            assert "Latest price" not in body, body
            titles = page.get_by_role("heading").all_text_contents()
            prices = [title for title in titles if title.endswith(": price")]
            assert prices[:2] == ["SYNTH-FPH.NZ · Synthetic test · New Zealand: price",
                                  "SYNTH-D05.SI · Synthetic test · Singapore: price"], prices
            nvda_panel = page.get_by_role("region").filter(
                has=page.get_by_role("heading", name="SYNTH-NVDA · Synthetic test · United States: price"),
            )
            nvda_panel.locator('[data-testid="icon-info-circle"]').hover()
            page.get_by_text(
                "14:30–21:00 UTC (January offset); 13:30–20:00 UTC (July offset)",
                exact=False,
            ).wait_for()
            page.mouse.wheel(0, -10000)
            pages.append(page)
        print("PASS: empty charts keep Asia-Pacific first, before US and global assets", flush=True)

        if args.start_collector:
            subprocess.run([
                "docker", "compose", "-f", "docker/docker-compose.yml", "up", "--build",
                "-d", "collector",
            ], cwd=ROOT, check=True)
            subprocess.run(["sh", "docker/wait-for-stack.sh"], cwd=ROOT, check=True)

        for page in pages:
            # Stay on the same page: no reload, variable selection or manual refresh.
            # Scroll to materialize all lazy repeated panels as their variables update.
            deadline = time.monotonic() + 90
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(250)
                body = page.locator("body").inner_text()
                if ("Synthetic test feed" in body
                        and "SYNTH-BTC-USD · Synthetic test · Global crypto: price" in body
                        and "SYNTH-BTC-USD · Synthetic test · Global crypto: reported session volume (cumulative)" in body
                        and "SYNTH-BTC-USD · USD" in body
                        and "SYNTH-NVDA · Synthetic test · United States: price" in body
                        and "Received ticks/min (last 60s)" in body
                        and "Received ticks per minute" in body
                        and "No data" in body
                        and "Waiting for ticks" not in body):
                    break
                if time.monotonic() >= deadline:
                    raise AssertionError("Dashboard did not populate automatically:\n" + body)
                page.wait_for_timeout(1000)
            for title in (
                "SYNTH-BTC-USD · Synthetic test · Global crypto: price",
                "SYNTH-BTC-USD · Synthetic test · Global crypto: reported session volume (cumulative)",
            ):
                panel = page.get_by_role("region").filter(
                    has=page.get_by_role("heading", name=title),
                )
                assert "SYNTH-BTC-USD · USD" in panel.inner_text(), panel.inner_text()
            page.mouse.wheel(0, -10000)
            page.wait_for_timeout(500)
            age_panel = page.get_by_role("region").filter(
                has=page.get_by_role("heading", name="Time since last tick"),
            )
            expected_state = ("Receiving delayed quotes" if float(os.getenv(
                "TICKER_SYNTHETIC_DELAY_SECONDS", "0")) > 60 else "Receiving")
            age_panel.get_by_role("gridcell", name=expected_state, exact=True).first.wait_for()
            age_table = age_panel.inner_text()
            assert all(value in age_table for value in ("Symbol", "Receipt age", "Newest quote age", "Session",
                "Regular schedule", "Received since restart", "Written since restart", "SYNTH-BTC-USD", "SYNTH-NVDA")), age_table
            if float(os.getenv("TICKER_SYNTHETIC_DELAY_SECONDS", "0")) > 60:
                assert "Receiving delayed quotes" in age_table, age_table
            print("PASS: data populated and sleeping default symbols stayed visible:",
                  page.url, flush=True)

        # Restrict Symbols to the silent ticker: no BTC volume series may remain.
        from urllib.parse import urlencode
        pages[0].goto(url + "/d/yliveticker-dashboard?" + urlencode({
            "var-symbol": "SYNTH-NVDA · Synthetic test · United States",
            "from": "now-1h", "to": "now", "refresh": "5s",
        }), wait_until="domcontentloaded")
        pages[0].get_by_role("heading", name="SYNTH-NVDA · Synthetic test · United States: price", exact=True).wait_for()
        assert pages[0].get_by_role("heading", name="SYNTH-BTC-USD · Synthetic test · Global crypto: price", exact=True).count() == 0
        print("PASS: selection keeps silent price chart and excludes unselected symbols", flush=True)

        assert queries, "Browser did not issue datasource queries"
        assert all(query.get("datasource", {}).get("uid") == "yliveticker-influxdb"
                   for query in queries), queries
        assert not errors, errors
        screenshot = Path(args.screenshot)
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        # Show a useful slice of actual collected history in the documentation image.
        pages[1].wait_for_timeout(15000)
        pages[1].goto(url + "/d/yliveticker-dashboard?from=now-1h&to=now", wait_until="domcontentloaded")
        pages[1].wait_for_timeout(5000)
        pages[1].screenshot(path=str(screenshot), full_page=True)
        print("PASS: browser queries use InfluxDB exclusively; no browser errors", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
