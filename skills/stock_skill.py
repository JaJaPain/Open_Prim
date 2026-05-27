import logging
import requests
from skills.base_skill import BaseSkill

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        # Fallback dummy class if both are missing during environment setup
        class DDGS:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
            def text(self, *args, **kwargs):
                return [{"body": "DuckDuckGo search library is not installed."}]
            def news(self, *args, **kwargs):
                return [{"body": "DuckDuckGo search library is not installed."}]

logger = logging.getLogger("Prim.Skills.Stock")

class StockSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "fetch_stock_ticker"

    @property
    def description(self) -> str:
        return "Fetch current stock price and financial market indicators for a ticker symbol."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The ticker symbol to query, e.g. 'AAPL' or 'GOOGL'"
                }
            },
            "required": ["symbol"]
        }

    @property
    def filler_keywords(self) -> list:
        return ["stock", "share", "price", "ticker", "market"]

    @property
    def filler_phrases(self) -> list:
        return [
            "Checking that stock price now.",
            "Let me fetch the latest market price.",
            "Looking up the stock details."
        ]

    def execute(self, symbol: str) -> str:
        logger.info(f"Fetching stock price for: {symbol}")
        
        # 1. Try Yahoo Finance API
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result")
                if result:
                    meta = result[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    currency = meta.get("currency", "USD")
                    long_name = meta.get("longName", symbol)
                    prev_close = meta.get("previousClose")
                    day_low = meta.get("regularMarketDayLow")
                    day_high = meta.get("regularMarketDayHigh")
                    
                    if price is not None:
                        change = price - prev_close if prev_close else 0.0
                        change_pct = (change / prev_close) * 100 if prev_close else 0.0
                        sign = "+" if change >= 0 else ""
                        
                        day_low_str = f"{day_low:.2f}" if day_low is not None else "N/A"
                        day_high_str = f"{day_high:.2f}" if day_high is not None else "N/A"
                        prev_close_str = f"{prev_close:.2f}" if prev_close is not None else "N/A"
                        
                        return (
                            f"Stock: {long_name} ({symbol.upper()})\n"
                            f"Price: {price:.2f} {currency}\n"
                            f"Change: {sign}{change:.2f} ({sign}{change_pct:.2f}%)\n"
                            f"Day Low: {day_low_str} | Day High: {day_high_str}\n"
                            f"Previous Close: {prev_close_str}"
                        )
                else:
                    logger.warning(f"Yahoo Finance returned no result list for symbol: {symbol}")
            else:
                logger.warning(f"Yahoo Finance failed with status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching stock from Yahoo Finance, falling back: {e}")

        # 2. Fallback: DuckDuckGo Search
        logger.info(f"Falling back to DuckDuckGo search for stock: {symbol}")
        query = f"{symbol} stock yahoo finance"
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                if not results:
                    return f"Could not find stock details for ticker symbol '{symbol}'."
                
                snippets = [r.get("body", "") for r in results]
                return f"Stock ticker results (fallback) for {symbol}:\n" + "\n---\n".join(snippets)
        except Exception as e:
            logger.error(f"Error fetching stock ticker fallback: {e}")
            return f"Error fetching stock ticker: {str(e)}"
