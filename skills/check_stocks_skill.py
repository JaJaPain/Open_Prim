import logging
from skills.base_skill import BaseSkill
import requests

class CheckStocks(BaseSkill):
    @property
    def name(self) -> str:
        return "check_stocks"

    @property
    def description(self) -> str:
        return "Checks the current status of specified stocks. If no stock symbols are specified, it checks the default watchlist (SOFI, PLTR)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "stocks": {
                    "type": "string",
                    "description": "Optional comma-separated list of stock symbols (e.g., AMZN, PLTR). If omitted, defaults to SOFI, PLTR."
                }
            }
        }

    @property
    def filler_keywords(self) -> list:
        return ["stock", "market"]

    @property
    def filler_phrases(self) -> list:
        return ["Fetching stock data now.", "Just a moment please."]

    def execute(self, **kwargs) -> str:
        try:
            stocks = kwargs.get("stocks")
            if not stocks:
                stocks = "SOFI, PLTR"

            stock_list = [stock.strip().upper() for stock in stocks.split(",")]
            base_url = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            results = []

            for stock in stock_list:
                try:
                    url = base_url.format(stock)
                    response = requests.get(url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        result_list = data.get("chart", {}).get("result")
                        if result_list:
                            meta = result_list[0].get("meta", {})
                            price = meta.get("regularMarketPrice")
                            prev_close = meta.get("previousClose")
                            
                            if price is not None:
                                change = price - prev_close if prev_close else 0.0
                                if change > 0:
                                    status = "up"
                                elif change < 0:
                                    status = "down"
                                else:
                                    status = "unchanged"
                                results.append(f"{stock} is {status} today at ${price:.2f}")
                            else:
                                results.append(f"{stock}: Price not available")
                        else:
                            results.append(f"{stock}: Stock not found")
                    else:
                        results.append(f"{stock}: Error fetching data (status {response.status_code})")
                except Exception as e:
                    results.append(f"{stock}: Error: {e}")

            return "\n".join(results)
        except Exception as e:
            return f"Error: {e}"
