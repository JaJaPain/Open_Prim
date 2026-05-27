import os
import importlib
import inspect
import logging
from skills.base_skill import BaseSkill

logger = logging.getLogger("Prim.Skills")

def discover_skills() -> dict:
    """Auto-discovers all BaseSkill subclasses in the skills/ directory.
    Returns a dict: { skill_name: skill_instance }
    """
    skills = {}
    skills_dir = os.path.dirname(__file__)

    for filename in os.listdir(skills_dir):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        if filename == "base_skill.py":
            continue

        module_name = f"skills.{filename[:-3]}"
        try:
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (inspect.isclass(attr)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill):
                    instance = attr()
                    skills[instance.name] = instance
                    logger.info(f"Loaded skill: '{instance.name}' from {filename}")
        except Exception as e:
            logger.error(f"Failed to load skill from {filename}: {e}")

    return skills


# Module-level singletons built on first import
SKILL_INSTANCES = discover_skills()
TOOLS_REGISTRY = {name: skill.execute for name, skill in SKILL_INSTANCES.items()}
OLLAMA_TOOLS = [skill.to_ollama_tool() for skill in SKILL_INSTANCES.values()]
