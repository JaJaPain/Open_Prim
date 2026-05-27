import logging
import requests
import xml.etree.ElementTree as ET
import urllib.parse
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

logger = logging.getLogger("Prim.Skills.News")

class NewsSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "fetch_news_headlines"

    @property
    def description(self) -> str:
        return "Fetch latest news headlines or world news updates based on a search topic."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search topic for news, e.g. 'tech startups' or 'global headlines'"
                }
            }
        }

    @property
    def filler_keywords(self) -> list:
        return ["news", "headline", "headlines", "article", "update"]

    @property
    def filler_phrases(self) -> list:
        return [
            "Let me check the latest news headlines.",
            "Fetching the latest news updates for you.",
            "Looking up the news."
        ]

    def execute(self, query: str = "world news headlines") -> str:
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
