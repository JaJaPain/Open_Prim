from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseSkill(ABC):
    """Abstract base class for all Prim skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique function name used in tool calls (e.g. 'fetch_weather')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for the LLM to understand when to call this skill."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema dict describing the function parameters for Ollama's tools API."""
        pass

    @property
    def filler_keywords(self) -> List[str]:
        """Optional list of keywords that trigger a thinking filler before this skill runs.
        Return an empty list if no filler is needed."""
        return []

    @property
    def filler_phrases(self) -> List[str]:
        """Optional list of filler phrases to play while this skill executes.
        Return an empty list to use no filler."""
        return []

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the skill with the given arguments. Must return a string result."""
        pass

    def to_ollama_tool(self) -> dict:
        """Converts this skill into the Ollama tool-calling JSON schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
