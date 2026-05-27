# Modular Skill System — Implementation Plan

> **Purpose**: This document is a self-contained implementation plan for converting the current
> hardcoded tool system in Project Prim into a modular, extensible Skill System.
> It is designed to be executed step-by-step by an AI coding assistant (Gemini 3.5 Flash).
>
> **CRITICAL RULE**: Do NOT overwrite or break the existing fast-whisper audio loop,
> wake-word detection, TTS playback logic, text input field, or the orchestration state machine
> in `main.py`. All audio pipeline code must remain untouched.

---

## 1. Architectural Review — Current Pipeline

### 1.1 File Map

| File | Purpose |
|---|---|
| `main.py` | Orchestration state machine: SLEEPING → LISTENING → THINKING → SPEAKING. Also handles typed text input via `_process_typed_input()`. **DO NOT MODIFY the audio loop, state machine, wake word, VAD, or TTS logic.** |
| `brain/llm_client.py` | Sends messages to Ollama, streams tokens, detects tool calls (native API + JSON text fallback), executes tools, re-queries LLM with results. **This is the primary file to modify.** |
| `brain/tools.py` | Contains 4 hardcoded tool functions (`fetch_weather`, `fetch_news_headlines`, `fetch_stock_ticker`, `save_preference`) plus `TOOLS_REGISTRY` (dict) and `OLLAMA_TOOLS` (JSON schema list). **This file will be replaced by the skill loader.** |
| `brain/memory_manager.py` | Manages daily `.md` session logs, preferences, and context loading. **Leave unchanged.** |
| `config.py` | All configuration constants including `LLM_SYSTEM_PROMPT` with hardcoded tool examples. **Must be updated to dynamically inject skill descriptions.** |
| `audio/*` | Wake word, VAD, Whisper transcriber, Kokoro synthesizer. **DO NOT TOUCH.** |
| `ui/dashboard.py` | CustomTkinter dashboard with text input field. **Leave unchanged.** |

### 1.2 Tool Call Interception Point

The tool calling pipeline is entirely inside `brain/llm_client.py` in the `chat_stream()` method. Here is the exact flow:

```
User query → build_messages() → chat_stream() → Ollama API (with tools= parameter)
                                       │
                                       ├── Streams tokens back to caller (main.py speaks them via TTS)
                                       │
                                       ├── If Ollama returns tool_calls in the stream:
                                       │       → Looks up function in TOOLS_REGISTRY dict
                                       │       → Calls function(**arguments)
                                       │       → Appends tool result to messages
                                       │       → Recursively calls chat_stream() for final spoken answer
                                       │
                                       └── If Ollama embeds JSON in text (fallback):
                                               → parse_tool_call_from_text() extracts it
                                               → Same execution path as above
```

**Key locations in `brain/llm_client.py`**:
- **Line 3**: `from brain.tools import OLLAMA_TOOLS, TOOLS_REGISTRY` — this is the import to change
- **Line 118**: `tools=OLLAMA_TOOLS` — passed to the Ollama chat API
- **Line 174**: `if func_name in TOOLS_REGISTRY:` — tool dispatch lookup
- **Line 175**: `tool_func = TOOLS_REGISTRY[func_name]` — tool function retrieval

**Key locations in `config.py`**:
- **Lines 79–101**: `LLM_SYSTEM_PROMPT` — contains hardcoded tool names, descriptions, and examples. This must become dynamic.

### 1.3 What Must NOT Change

- `main.py`: The `_orchestration_loop()`, `_process_typed_input()`, `_play_thinking_filler()`, `_mic_callback()`, `_handle_interruption()` methods, and the entire SLEEPING/LISTENING/THINKING/SPEAKING state machine
- `audio/*`: All files in the audio directory
- `ui/dashboard.py`: The dashboard UI
- `brain/memory_manager.py`: The memory system
- The signature of `chat_stream(messages)` — it must continue to yield text tokens
- The signature of `build_messages(user_query, memory_manager)` — it must continue to return a list of message dicts

---

## 2. Skill Interface Design

### 2.1 Directory Structure

Create a new `skills/` directory at the project root:

```
LocalChatBot/
├── skills/
│   ├── __init__.py          ← Skill loader + registry builder
│   ├── base_skill.py        ← Abstract base class
│   ├── weather_skill.py     ← Migrated from brain/tools.py fetch_weather
│   ├── news_skill.py        ← Migrated from brain/tools.py fetch_news_headlines
│   ├── stock_skill.py       ← Migrated from brain/tools.py fetch_stock_ticker
│   └── memory_skill.py      ← Migrated from brain/tools.py save_preference
├── brain/
│   ├── llm_client.py        ← Modified to import from skills/ instead of brain/tools.py
│   ├── tools.py             ← DEPRECATED — keep file but redirect imports (backward compat)
│   └── memory_manager.py    ← Unchanged
├── main.py                  ← Unchanged (audio/state machine) except filler keywords
├── config.py                ← Modified: system prompt becomes a template
└── ...
```

### 2.2 Base Skill Class (`skills/base_skill.py`)

```python
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
```

### 2.3 Example Skill Implementation (`skills/weather_skill.py`)

```python
from skills.base_skill import BaseSkill

class WeatherSkill(BaseSkill):

    @property
    def name(self):
        return "fetch_weather"

    @property
    def description(self):
        return "Fetch the weather details, temperature, and forecast for a specific location."

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state/country, e.g. 'Kokomo, Indiana'."
                }
            },
            "required": ["location"]
        }

    @property
    def filler_keywords(self):
        return ["weather", "forecast", "rain", "temperature", "temp", "snow"]

    @property
    def filler_phrases(self):
        return [
            "Checking the weather for you.",
            "Let me check the weather forecast.",
            "One second, checking the weather conditions."
        ]

    def execute(self, location: str) -> str:
        # Move the entire fetch_weather() function body from brain/tools.py here
        ...
```

### 2.4 Skill Loader (`skills/__init__.py`)

```python
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
```

---

## 3. Local Function Calling Strategy

### 3.1 Keep Ollama's Native Tool-Calling API (Recommended — Already Working)

The current system already uses Ollama's native `tools=` parameter in `client.chat()`. This is the safest and most reliable approach because:

1. Ollama handles the structured output formatting internally
2. Tool calls arrive in `msg["tool_calls"]` with properly parsed function names and arguments
3. No need to parse raw JSON from text (the fallback parser handles edge cases where the model emits JSON in text instead)

**Do NOT change the tool-calling strategy.** Keep the existing dual approach:
- **Primary**: Ollama native `tools=` parameter → `msg["tool_calls"]`
- **Fallback**: `parse_tool_call_from_text()` for when the model embeds JSON in its text response

### 3.2 What Changes in `llm_client.py`

Only the **import source** changes. Instead of:
```python
from brain.tools import OLLAMA_TOOLS, TOOLS_REGISTRY
```
Change to:
```python
from skills import OLLAMA_TOOLS, TOOLS_REGISTRY
```

Everything else in `chat_stream()` stays exactly the same. The `TOOLS_REGISTRY` dict and `OLLAMA_TOOLS` list have the same shape as before — they are just built dynamically by the skill loader now.

### 3.3 Dynamic System Prompt

The `LLM_SYSTEM_PROMPT` in `config.py` currently hardcodes the 4 tool names and examples. This must become a template that gets filled in dynamically.

**In `config.py`**, replace the hardcoded tool list with a `{tool_descriptions}` placeholder:

```python
LLM_SYSTEM_PROMPT_TEMPLATE = """You are Prim, a helpful, ultra-low latency local voice assistant.
...
TOOL USAGE RULES:
You have access to the following tools and MUST use them when appropriate:
{tool_descriptions}

CRITICAL:
- You MUST call a tool for any query about weather, news, stocks, or current/real-time events.
...
"""
```

**In `llm_client.py`** `build_messages()`, generate the tool descriptions dynamically from `SKILL_INSTANCES`:

```python
from skills import SKILL_INSTANCES

tool_lines = []
for i, skill in enumerate(SKILL_INSTANCES.values(), 1):
    tool_lines.append(f"{i}. '{skill.name}': {skill.description}")
tool_descriptions = "\n".join(tool_lines)

system_prompt = config.LLM_SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=tool_descriptions)
```

### 3.4 Dynamic Thinking Fillers

The `_play_thinking_filler()` method in `main.py` currently hardcodes keyword-to-filler mappings. This should be driven by the skills' `filler_keywords` and `filler_phrases` properties.

**In `main.py`**, modify `_play_thinking_filler()` to import skill instances and iterate their filler data:

```python
from skills import SKILL_INSTANCES

def _play_thinking_filler(self, user_text):
    import random
    user_text_lower = user_text.lower()
    filler = None
    for skill in SKILL_INSTANCES.values():
        if skill.filler_keywords and any(w in user_text_lower for w in skill.filler_keywords):
            if skill.filler_phrases:
                filler = random.choice(skill.filler_phrases)
                break
    if filler:
        logger.info(f"Playing thinking filler: '{filler}'")
        self.dashboard.add_transcript("Prim (Thinking)", f"({filler})")
        self.synthesizer.generate_and_play(filler)
```

---

## 4. Step-by-Step Implementation Checklist

> Execute these steps **in order**. Check each box as you complete it.
> Test after each major section before moving on.

### Phase 1: Create the Skill Framework (No Existing Code Broken)

- `[ ]` **Create `skills/` directory** at `c:\CodingProjects\LocalChatBot\skills\`
- `[ ]` **Create `skills/base_skill.py`** with the `BaseSkill` abstract class as defined in Section 2.2 above. Include all properties (`name`, `description`, `parameters`, `filler_keywords`, `filler_phrases`), the `execute()` abstract method, and the `to_ollama_tool()` helper.
- `[ ]` **Create `skills/__init__.py`** with the `discover_skills()` auto-loader and the module-level `SKILL_INSTANCES`, `TOOLS_REGISTRY`, and `OLLAMA_TOOLS` singletons as defined in Section 2.4.
- `[ ]` **Verify** the framework imports without error:
  ```bash
  venv\Scripts\python.exe -c "from skills.base_skill import BaseSkill; print('OK')"
  ```

### Phase 2: Migrate Existing Tools to Skills

For each skill below, create a new file in `skills/`. Move the **function body** from `brain/tools.py` into the skill's `execute()` method. Keep all the existing logic, imports, error handling, and fallback behavior exactly as-is.

- `[ ]` **Create `skills/weather_skill.py`** — Migrate `fetch_weather()` from `brain/tools.py` (lines 26–146). The class should be named `WeatherSkill`. Include the `filler_keywords` and `filler_phrases` properties using the weather fillers currently hardcoded in `main.py` `_play_thinking_filler()` (lines 161–165 area). Make sure to include all imports the function needs (`requests`, `urllib.parse`, `DDGS`, etc.) at the top of the skill file.
- `[ ]` **Create `skills/news_skill.py`** — Migrate `fetch_news_headlines()` from `brain/tools.py` (lines 148–205). Class name: `NewsSkill`. Include news filler keywords/phrases from `main.py`.
- `[ ]` **Create `skills/stock_skill.py`** — Migrate `fetch_stock_ticker()` from `brain/tools.py` (lines 207–270). Class name: `StockSkill`. Include stock filler keywords/phrases from `main.py`.
- `[ ]` **Create `skills/memory_skill.py`** — Migrate `save_preference()` from `brain/tools.py` (lines 273–285). Class name: `MemorySkill`. Include memory filler keywords/phrases from `main.py`.
- `[ ]` **Verify** all skills load correctly:
  ```bash
  venv\Scripts\python.exe -c "from skills import SKILL_INSTANCES, TOOLS_REGISTRY, OLLAMA_TOOLS; print(f'Loaded {len(SKILL_INSTANCES)} skills: {list(SKILL_INSTANCES.keys())}'); print(f'Registry has {len(TOOLS_REGISTRY)} entries'); print(f'Ollama tools has {len(OLLAMA_TOOLS)} entries')"
  ```
  Expected output: `Loaded 4 skills: ['fetch_weather', 'fetch_news_headlines', 'fetch_stock_ticker', 'save_preference']`

### Phase 3: Wire the Skill System into the LLM Client

- `[ ]` **Modify `brain/llm_client.py` line 3**: Change the import from:
  ```python
  from brain.tools import OLLAMA_TOOLS, TOOLS_REGISTRY
  ```
  to:
  ```python
  from skills import OLLAMA_TOOLS, TOOLS_REGISTRY
  ```
  **Do NOT change anything else in this file.** The `chat_stream()` method, `parse_tool_call_from_text()`, and `build_messages()` must remain exactly as they are (except the system prompt change below).

- `[ ]` **Modify `config.py`**: Rename `LLM_SYSTEM_PROMPT` to `LLM_SYSTEM_PROMPT_TEMPLATE` and replace the hardcoded tool list (lines 86–100) with a `{tool_descriptions}` placeholder. Keep the surrounding text (personality instructions and CRITICAL rules) exactly the same. The template should look like:
  ```python
  LLM_SYSTEM_PROMPT_TEMPLATE = """You are Prim, a helpful, ultra-low latency local voice assistant.
  Respond conversationally, concisely, and naturally. Since you are speaking to the user:
  - Keep your answers short, ideally 1-3 sentences, unless the user asks for a detailed explanation.
  - Do not output markdown lists, code blocks, or formatting tags unless specifically asked, as they are hard to read aloud.
  - Use natural pauses and phrasing.
  - If you call a tool, weave the tool output naturally into your spoken response.

  TOOL USAGE RULES:
  You have access to the following tools and MUST use them when appropriate:
  {tool_descriptions}

  CRITICAL:
  - You MUST call a tool for any query about weather, news, stocks, or current/real-time events. Never claim you don't have access to real-time information.
  - You MUST NOT ask the user for clarification. Immediately make the tool call using the best arguments extracted from their query.
  - If the user shares a fact about themselves, you MUST use 'save_preference' to store it.
  """
  ```

- `[ ]` **Modify `brain/llm_client.py` `build_messages()`** to dynamically generate the system prompt from the template. Change the method to:
  1. Import `SKILL_INSTANCES` from `skills`
  2. Build a numbered tool description string from each skill's `name` and `description`
  3. Format the template with `config.LLM_SYSTEM_PROMPT_TEMPLATE.format(tool_descriptions=...)`
  4. Append preferences after the formatted prompt (this part already works)

- `[ ]` **Verify** the system prompt generates correctly:
  ```bash
  venv\Scripts\python.exe -c "from brain.llm_client import OllamaLLMClient; from brain.memory_manager import MemoryManager; c = OllamaLLMClient(); msgs = c.build_messages('test', MemoryManager()); print(msgs[0]['content'])"
  ```
  Should show the full system prompt with dynamically listed tools.

### Phase 4: Dynamic Thinking Fillers

- `[ ]` **Modify `main.py` `_play_thinking_filler()`**: Replace the hardcoded keyword/filler dictionaries with a dynamic loop over `SKILL_INSTANCES`. Add `from skills import SKILL_INSTANCES` at the top of the method (or at file level). The method should iterate through each skill, check if any of its `filler_keywords` appear in the user text, and if so, pick a random phrase from its `filler_phrases`. **Do not change any other method in main.py.**

- `[ ]` **Verify** the filler system works by inspecting the output:
  ```bash
  venv\Scripts\python.exe -c "from skills import SKILL_INSTANCES; [print(f'{s.name}: keywords={s.filler_keywords}, phrases={s.filler_phrases}') for s in SKILL_INSTANCES.values()]"
  ```

### Phase 5: Backward Compatibility & Cleanup

- `[ ]` **Update `brain/tools.py`** to be a thin backward-compatibility shim. Replace its contents with:
  ```python
  """DEPRECATED: Tools have been migrated to the skills/ directory.
  This file exists for backward compatibility only."""
  from skills import TOOLS_REGISTRY, OLLAMA_TOOLS
  ```
  This ensures any other code that imports from `brain.tools` still works.

- `[ ]` **Verify** backward compatibility:
  ```bash
  venv\Scripts\python.exe -c "from brain.tools import TOOLS_REGISTRY, OLLAMA_TOOLS; print(f'Registry: {len(TOOLS_REGISTRY)} tools, Ollama: {len(OLLAMA_TOOLS)} tools')"
  ```

### Phase 6: End-to-End Testing

- `[ ]` **Syntax check all modified files**:
  ```bash
  venv\Scripts\python.exe -m py_compile main.py
  venv\Scripts\python.exe -m py_compile brain\llm_client.py
  venv\Scripts\python.exe -m py_compile brain\tools.py
  venv\Scripts\python.exe -m py_compile config.py
  venv\Scripts\python.exe -m py_compile skills\__init__.py
  venv\Scripts\python.exe -m py_compile skills\base_skill.py
  venv\Scripts\python.exe -m py_compile skills\weather_skill.py
  venv\Scripts\python.exe -m py_compile skills\news_skill.py
  venv\Scripts\python.exe -m py_compile skills\stock_skill.py
  venv\Scripts\python.exe -m py_compile skills\memory_skill.py
  ```

- `[ ]` **Test weather tool call end-to-end** (no voice needed):
  ```bash
  venv\Scripts\python.exe -c "
  from brain.llm_client import OllamaLLMClient
  from brain.memory_manager import MemoryManager
  c = OllamaLLMClient()
  msgs = c.build_messages('What is the weather in Seattle?', MemoryManager())
  for chunk in c.chat_stream(msgs):
      print(chunk, end='', flush=True)
  print()
  "
  ```
  Should invoke `fetch_weather` and print a natural weather summary.

- `[ ]` **Test stock tool call end-to-end**:
  ```bash
  venv\Scripts\python.exe -c "
  from brain.llm_client import OllamaLLMClient
  from brain.memory_manager import MemoryManager
  c = OllamaLLMClient()
  msgs = c.build_messages('What is the price of AAPL?', MemoryManager())
  for chunk in c.chat_stream(msgs):
      print(chunk, end='', flush=True)
  print()
  "
  ```

- `[ ]` **Launch the full voice assistant** via `start.bat` and verify:
  - `[ ]` Wake word detection still works (say "Prim")
  - `[ ]` Voice weather query works ("Prim, what's the weather?")
  - `[ ]` Typed text input works (type "What is the weather?" in the text field)
  - `[ ]` Thinking fillers still play before tool calls
  - `[ ]` Memory/preference saving works ("Remember my name is John")

- `[ ]` **Git commit**:
  ```bash
  git add .
  git commit -m "Migrate to modular skill system with auto-discovery"
  ```

---

## 5. Adding a New Skill (Future Reference)

Once the system is in place, adding a new skill is a 3-step process:

1. **Create a new file** in `skills/`, e.g. `skills/timer_skill.py`
2. **Define a class** inheriting from `BaseSkill` with `name`, `description`, `parameters`, and `execute()`
3. **Restart the assistant** — the auto-discovery loader picks it up automatically

No changes to `llm_client.py`, `config.py`, or `main.py` are needed. The skill loader, Ollama tool schema, system prompt, and thinking fillers all update automatically.

### Example: Timer Skill

```python
# skills/timer_skill.py
import time
import threading
from skills.base_skill import BaseSkill

class TimerSkill(BaseSkill):
    @property
    def name(self):
        return "set_timer"

    @property
    def description(self):
        return "Sets a countdown timer for a specified number of seconds."

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "Number of seconds for the timer"
                }
            },
            "required": ["seconds"]
        }

    @property
    def filler_keywords(self):
        return ["timer", "alarm", "remind", "countdown"]

    @property
    def filler_phrases(self):
        return ["Setting a timer for you.", "Got it, starting the countdown."]

    def execute(self, seconds: int) -> str:
        # In a real implementation, this would integrate with the TTS to announce when done
        return f"Timer set for {seconds} seconds."
```

---

## 6. Files Changed Summary

| Action | File | What Changes |
|---|---|---|
| **NEW** | `skills/__init__.py` | Auto-discovery loader, `SKILL_INSTANCES`, `TOOLS_REGISTRY`, `OLLAMA_TOOLS` |
| **NEW** | `skills/base_skill.py` | Abstract `BaseSkill` class |
| **NEW** | `skills/weather_skill.py` | `WeatherSkill` — migrated from `brain/tools.py` |
| **NEW** | `skills/news_skill.py` | `NewsSkill` — migrated from `brain/tools.py` |
| **NEW** | `skills/stock_skill.py` | `StockSkill` — migrated from `brain/tools.py` |
| **NEW** | `skills/memory_skill.py` | `MemorySkill` — migrated from `brain/tools.py` |
| **MODIFY** | `brain/llm_client.py` | Change import source; dynamic system prompt in `build_messages()` |
| **MODIFY** | `config.py` | Rename `LLM_SYSTEM_PROMPT` → `LLM_SYSTEM_PROMPT_TEMPLATE` with `{tool_descriptions}` placeholder |
| **MODIFY** | `main.py` | Only `_play_thinking_filler()` — replace hardcoded fillers with skill-driven loop |
| **MODIFY** | `brain/tools.py` | Replace contents with backward-compat shim importing from `skills/` |
