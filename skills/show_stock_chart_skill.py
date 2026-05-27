
import logging
from skills.base_skill import BaseSkill
import webbrowser

class ShowStockChart(BaseSkill):
    @property
    def name(self) -> str:
        return "show_stock_chart"

    @property
    def description(self) -> str:
        return "Opens the Yahoo Finance quote page for a given stock symbol and provides a summary of the current stock price."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g. 'AAPL')"
                }
            },
            "required": ["symbol"]
        }

    @property
    def filler_keywords(self) -> list:
        return ["stock", "chart"]

    @property
    def filler_phrases(self) -> list:
        return ["Opening the chart now.", "Fetching the data..."]

    def execute(self, **kwargs) -> str:
        try:
            symbol = kwargs.get("symbol")

            if not symbol:
                return "Error: No stock symbol provided."

            # Construct the URL for Yahoo Finance
            url = f"https://finance.yahoo.com/quote/{symbol}?p={symbol}"
            
            # Open the URL in the default web browser
            webbrowser.open(url)
            
            return f"Opening stock chart for {symbol}."
        except Exception as e:
            logging.error(f"Error executing show_stock_chart skill: {e}")
            return f"Error: {e}"
