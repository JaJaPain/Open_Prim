
import logging
from skills.base_skill import BaseSkill
import requests
import datetime

class CheckStocks(BaseSkill):
    @property
    def name(self) -> str:
        return "check_stocks"

    @property
    def description(self) -> str:
        return "Checks the current status of specified stocks. If no stock symbols are specified, it checks the default watchlist (GOOGL, AMZN, VOO, ROBO, RKLB, NVDA). Optionally fetches historical data for a specified number of days."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "stocks": {
                    "type": "string",
                    "description": "Optional comma-separated list of stock symbols (e.g., AMZN, PLTR). If omitted, defaults to GOOGL, AMZN, VOO, ROBO, RKLB, NVDA."
                },
                "days": {
                    "type": "integer",
                    "description": "Optional number of days for which to fetch historical data. If omitted, only current prices are fetched."
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
            days = kwargs.get("days", 0)

            if not stocks:
                stocks = "GOOGL, AMZN, VOO, ROBO, RKLB, NVDA"

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
                                
                                current_result = f"{stock} is {status} today at ${price:.2f}"
                                results.append(current_result)
                                
                                # Fetch historical data if requested
                                if days > 0:
                                    try:
                                        url_history = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock}?period1={int(time.time() - 24 * 60 * 60 * days)}&period2={int(time.time())}&interval=1d"
                                        response_history = requests.get(url_history, headers=headers, timeout=5)
                                        if response_history.status_code == 200:
                                            data_history = response_history.json()
                                            result_list_history = data_history.get("chart", {}).get("result")
                                            if result_list_history:
                                                history = result_list_history[0].get("indicators", {}).get("quote")[0]
                                                
                                                historical_data = []
                                                for i, h in enumerate(history["open"]):
                                                    date = (datetime.datetime.now() - datetime.timedelta(days=days + 1 - len(history["open"]) + i)).strftime("%Y-%m-%d")
                                                    open_price = f"{h:.2f}"
                                                    high_price = f"{history['high'][i]:.2f}"
                                                    low_price = f"{history['low'][i]:.2f}"
                                                    close_price = f"{history['close'][i]:.2f}"
                                                    historical_data.append(f"{date}: Open {open_price}, High {high_price}, Low {low_price}, Close {close_price}")
                                                
                                                historical_result = "\n".join(historical_data)
                                                results.append(historical_result)
                                            else:
                                                results.append(f"{stock}: Historical data not found")
                                        else:
                                            results.append(f"{stock}: Error fetching historical data (status {response_history.status_code})")
                                    except Exception as e:
                                        results.append(f"{stock}: Error fetching historical data: {e}")
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
