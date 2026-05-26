import json
import logging
import requests
import xml.etree.ElementTree as ET
import urllib.parse

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

logger = logging.getLogger("Prim.Tools")

def fetch_weather(location: str) -> str:
    """
    Fetches the weather forecast for a given location.
    Primary: Open-Meteo API.
    Fallback: DuckDuckGo search.
    """
    logger.info(f"Fetching weather for: {location}")
    
    # 1. Try Open-Meteo API
    try:
        US_STATES = {
            'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
            'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
            'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
            'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
            'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
            'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
            'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
            'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
            'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
            'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
        }
        clean_loc = location.strip()
        state_filter = None
        
        parts = [p.strip() for p in clean_loc.split(",")]
        if len(parts) > 1:
            clean_loc = parts[0]
            state_filter = parts[-1]
        else:
            words = clean_loc.split()
            if len(words) > 1 and words[-1].upper() in US_STATES:
                clean_loc = " ".join(words[:-1])
                state_filter = words[-1]
                
        # Geocoding - query 10 results to filter by state if needed
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(clean_loc)}&count=10&language=en&format=json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        geo_res = requests.get(geo_url, headers=headers, timeout=5)
        if geo_res.status_code == 200:
            geo_data = geo_res.json()
            results = geo_data.get("results", [])
            if results:
                place = results[0]
                if state_filter:
                    sf_upper = state_filter.upper()
                    for r in results:
                        admin = r.get("admin1", "")
                        if (admin.upper() == sf_upper or 
                            (sf_upper in US_STATES and admin.lower() == US_STATES[sf_upper].lower())):
                            place = r
                            break
                lat = place["latitude"]
                lon = place["longitude"]
                name = place.get("name", location)
                country = place.get("country", "")
                admin1 = place.get("admin1", "")
                
                # Weather Forecast
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,wind_speed_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=auto"
                weather_res = requests.get(weather_url, headers=headers, timeout=5)
                if weather_res.status_code == 200:
                    w_data = weather_res.json()
                    current = w_data.get("current", {})
                    temp = current.get("temperature_2m")
                    app_temp = current.get("apparent_temperature")
                    humidity = current.get("relative_humidity_2m")
                    wind = current.get("wind_speed_10m")
                    
                    wmo_codes = {
                        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                        45: "Fog", 48: "Depositing rime fog",
                        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
                        56: "Light freezing drizzle", 57: "Dense freezing drizzle",
                        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                        66: "Light freezing rain", 67: "Heavy freezing rain",
                        71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
                        77: "Snow grains",
                        80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
                        85: "Slight snow showers", 86: "Heavy snow showers",
                        95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
                    }
                    code = current.get("weather_code", 0)
                    condition = wmo_codes.get(code, "Unknown condition")
                    
                    loc_str = f"{name}"
                    if admin1:
                        loc_str += f", {admin1}"
                    if country:
                        loc_str += f" ({country})"
                        
                    return (
                        f"Weather for {loc_str}:\n"
                        f"Condition: {condition}\n"
                        f"Temperature: {temp}°F (Feels like: {app_temp}°F)\n"
                        f"Humidity: {humidity}%\n"
                        f"Wind Speed: {wind} mph"
                    )
            else:
                logger.warning(f"Open-Meteo geocoding returned no results for: {location}")
        else:
            logger.warning(f"Open-Meteo geocoding failed with status: {geo_res.status_code}")
    except Exception as e:
        logger.error(f"Error calling Open-Meteo API for weather, falling back: {e}")

    # 2. Fallback: DuckDuckGo Search
    logger.info(f"Falling back to DuckDuckGo search for weather: {location}")
    query = f"{location} weather forecast"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return f"Could not find weather details for '{location}'."
            
            snippets = [r.get("body", "") for r in results]
            return f"Weather search results (fallback) for {location}:\n" + "\n---\n".join(snippets)
    except Exception as e:
        logger.error(f"Error fetching weather fallback: {e}")
        return f"Error querying weather for {location}: {str(e)}"

def fetch_news_headlines(query: str = "world news headlines") -> str:
    """
    Queries current news headlines.
    Primary: Google News RSS.
    Fallback: DuckDuckGo News search.
    """
    logger.info(f"Fetching news for query: {query}")
    
    # 1. Try Google News RSS
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            news_items = []
            for i, item in enumerate(items[:5], 1):
                title = item.find("title").text
                source_el = item.find("source")
                source = source_el.text if source_el is not None else "News"
                pub_date = item.find("pubDate").text
                news_items.append(f"{i}. [{source}] {title}\n   Published: {pub_date}")
            
            if news_items:
                return f"Latest headlines for '{query}':\n" + "\n\n".join(news_items)
            else:
                logger.warning(f"Google News RSS returned no items for query: {query}")
        else:
            logger.warning(f"Google News RSS failed with status code: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching Google News RSS, falling back: {e}")

    # 2. Fallback: DuckDuckGo News
    logger.info(f"Falling back to DuckDuckGo search for news: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
            if not results:
                results = list(ddgs.text(query, max_results=4))
            
            if not results:
                return "No news headlines found matching that query."
            
            news_items = []
            for i, r in enumerate(results, 1):
                title = r.get("title", r.get("body", "")[:60] + "...")
                source = r.get("source", "Web")
                body = r.get("body", "")
                news_items.append(f"{i}. [{source}] {title}: {body}")
            
            return f"Latest headlines for '{query}' (fallback):\n" + "\n\n".join(news_items)
    except Exception as e:
        logger.error(f"Error fetching news fallback: {e}")
        return f"Error fetching news: {str(e)}"

def fetch_stock_ticker(symbol: str) -> str:
    """
    Queries the active trading price and market summary for a stock symbol.
    Primary: Yahoo Finance API.
    Fallback: DuckDuckGo search.
    """
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

# Registry of tools to make them accessible to the LLM Client
def save_preference(preference: str) -> str:
    """
    Saves a user preference, habit, or fact (e.g. location, favorite team) to memory.
    """
    logger.info(f"Saving user preference: {preference}")
    try:
        from brain.memory_manager import MemoryManager
        mgr = MemoryManager()
        mgr.learn_preference(preference)
        return f"Successfully saved user preference: '{preference}'"
    except Exception as e:
        logger.error(f"Error saving user preference: {e}")
        return f"Error saving user preference: {str(e)}"

TOOLS_REGISTRY = {
    "fetch_weather": fetch_weather,
    "fetch_news_headlines": fetch_news_headlines,
    "fetch_stock_ticker": fetch_stock_ticker,
    "save_preference": save_preference
}

# JSON tool declarations for Ollama function calling
OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_weather",
            "description": "Fetch the weather details, temperature, and forecast for a specific location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state/country, e.g. 'New York City, NY'. If not specified in the query, check the user's preferences to find their location (e.g. 'Kokomo, Indiana') and pass it."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_news_headlines",
            "description": "Fetch latest news headlines or world news updates based on a search topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search topic for news, e.g. 'tech startups' or 'global headlines'"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_stock_ticker",
            "description": "Fetch current stock price and financial market indicators for a ticker symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The ticker symbol to query, e.g. 'AAPL' or 'GOOGL'"
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_preference",
            "description": "Saves a user preference, habit, or fact (e.g. location, favorite team) to memory so you remember it in future turns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preference": {
                        "type": "string",
                        "description": "The preference or fact to remember, e.g. 'User lives in Kokomo, Indiana' or 'User's name is John'"
                    }
                },
                "required": ["preference"]
            }
        }
    }
]
