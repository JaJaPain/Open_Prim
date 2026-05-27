import logging
from skills.base_skill import BaseSkill

logger = logging.getLogger("Prim.Skills.Memory")

class MemorySkill(BaseSkill):

    @property
    def name(self) -> str:
        return "save_preference"

    @property
    def description(self) -> str:
        return "Saves a user preference, habit, or fact (e.g. location, favorite team) to memory so you remember it in future turns."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "preference": {
                    "type": "string",
                    "description": "The preference or fact to remember, e.g. 'User lives in Kokomo, Indiana' or 'User's name is John'"
                }
            },
            "required": ["preference"]
        }

    @property
    def filler_keywords(self) -> list:
        return ["remember", "save", "learn", "forget"]

    @property
    def filler_phrases(self) -> list:
        return [
            "Got it, saving that to memory.",
            "Writing that down for you.",
            "One moment, remembering that."
        ]

    def execute(self, preference: str) -> str:
        logger.info(f"Saving user preference: {preference}")
        try:
            from brain.memory_manager import MemoryManager
            mgr = MemoryManager()
            mgr.learn_preference(preference)
            return f"Successfully saved user preference: '{preference}'"
        except Exception as e:
            logger.error(f"Error saving user preference: {e}")
            return f"Error saving user preference: {str(e)}"
