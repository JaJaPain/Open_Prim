import logging
import requests
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

logger = logging.getLogger("Prim.Skills.Weather")

class WeatherSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "fetch_weather"

    @property
    def description(self) -> str:
        return "Fetch the weather details, temperature, and forecast for a specific location."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state/country, e.g. 'New York City, NY'. If not specified in the query, check the user's preferences to find their location (e.g. 'Kokomo, Indiana') and pass it."
                }
            },
            "required": ["location"]
        }

    @property
    def filler_keywords(self) -> list:
        return ["weather", "forecast", "rain", "temperature", "temp", "snow"]

    @property
    def filler_phrases(self) -> list:
        return [
            "Checking the weather for you.",
            "Let me check the weather forecast.",
            "One second, checking the weather conditions."
        ]

    def execute(self, location: str) -> str:
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
