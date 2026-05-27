import logging
import config
from skills import OLLAMA_TOOLS, TOOLS_REGISTRY

# Try importing ollama. If not installed yet, handle gracefully.
try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger("Prim.LLM")

class OllamaLLMClient:
    def __init__(self, host=config.OLLAMA_HOST):
        self.host = host
        self.client = None
        if ollama is not None:
            try:
                self.client = ollama.Client(host=self.host)
                logger.info(f"Ollama client initialized at: {self.host}")
            except Exception as e:
                logger.error(f"Failed to connect to Ollama host: {e}")
        else:
            logger.warning("ollama package is not installed. LLM interaction will be disabled.")

    def parse_tool_call_from_text(self, text: str) -> list:
        """
        Attempts to find and parse a JSON tool call inside raw text content.
        Returns a list of dicts formatted as Ollama's msg['tool_calls'] list.
        """
        import json
        text = text.strip()
        if not text:
            return []
            
        # Try parsing the whole text directly as a JSON object
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "name" in data:
                return [{
                    "function": {
                        "name": data["name"],
                        "arguments": data.get("arguments", {})
                    }
                }]
        except Exception:
            pass
            
        # Check for markdown code blocks (e.g. ```json ... ``` or ``` ... ```)
        import re
        code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block_match:
            try:
                data = json.loads(code_block_match.group(1))
                if isinstance(data, dict) and "name" in data:
                    return [{
                        "function": {
                            "name": data["name"],
                            "arguments": data.get("arguments", {})
                        }
                    }]
            except Exception:
                pass
                
        # Try extracting JSON object using regex (handles surrounding conversational text)
        matches = re.findall(r"\{[^{}]*\"name\"\s*:[^{}]*\}", text)
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, dict) and "name" in data:
                    return [{
                        "function": {
                            "name": data["name"],
                            "arguments": data.get("arguments", {})
                        }
                    }]
            except Exception:
                pass
                
        # Find index of first '{' and last '}'
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_candidate = text[start:end+1]
            try:
                data = json.loads(json_candidate)
                if isinstance(data, dict) and "name" in data:
                    return [{
                        "function": {
                            "name": data["name"],
                            "arguments": data.get("arguments", {})
                        }
                    }]
            except Exception:
                pass
                
        return []


    def chat_stream(self, messages: list):
        """
        Sends messages to Ollama and streams the response text.
        If the model requests a tool/function call, runs the function and 
        re-queries the model, yielding the final conversational summary.
        
        Yields text chunks.
        """
        if self.client is None:
            yield "Ollama client is not initialized. Please ensure Ollama is installed and running."
            return

        try:
            logger.debug(f"Sending chat request to Ollama model '{config.LLM_MODEL}'")
            # Call Ollama chat stream
            response = self.client.chat(
                model=config.LLM_MODEL,
                messages=messages,
                tools=OLLAMA_TOOLS,
                stream=True,
                options={"temperature": 0.1}
            )
            
            full_message = {'role': 'assistant', 'content': '', 'tool_calls': []}
            buffering_json = False
            json_buffer = ""
            
            for chunk in response:
                msg = chunk.get("message", {})
                if msg.get("content"):
                    text = msg["content"]
                    full_message["content"] += text
                    
                    if buffering_json:
                        json_buffer += text
                    else:
                        if "{" in text:
                            idx = text.find("{")
                            pre_text = text[:idx]
                            post_text = text[idx:]
                            
                            if pre_text:
                                yield pre_text
                            
                            buffering_json = True
                            json_buffer = post_text
                        else:
                            yield text
                
                if msg.get("tool_calls"):
                    full_message["tool_calls"].extend(msg["tool_calls"])
            
            # If we were buffering JSON, check if it's a valid tool call
            if buffering_json and not full_message["tool_calls"]:
                parsed_calls = self.parse_tool_call_from_text(json_buffer)
                if parsed_calls:
                    logger.info(f"Successfully parsed raw JSON tool call from buffered text: {parsed_calls}")
                    full_message["tool_calls"] = parsed_calls
                else:
                    # If it wasn't a valid tool call, yield the buffered text so the user can hear it
                    logger.debug(f"Buffered text was not a tool call, yielding: {json_buffer}")
                    yield json_buffer
            
            # If the model requested tool calls, execute them and recursively get final conversation response
            if full_message["tool_calls"]:
                logger.info(f"Executing {len(full_message['tool_calls'])} tool calls...")
                # Append the assistant's tool-call request to the conversation history
                messages.append(full_message)
                
                for tool_call in full_message["tool_calls"]:
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"].get("arguments", {})
                    logger.info(f"Invoking tool: {func_name}({func_args})")
                    
                    if func_name in TOOLS_REGISTRY:
                        tool_func = TOOLS_REGISTRY[func_name]
                        try:
                            # Invoke tool function
                            result = tool_func(**func_args)
                        except Exception as tool_err:
                            result = f"Error executing tool: {tool_err}"
                    else:
                        result = f"Error: Tool '{func_name}' is not registered."
                    
                    logger.debug(f"Tool {func_name} output: {result[:200]}")
                    
                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "content": str(result)
                    })
                
                # Recursive call to stream final summary
                yield from self.chat_stream(messages)
                
        except Exception as e:
            logger.error(f"Error during Ollama chat: {e}")
            yield f"Error in LLM: {str(e)}"

    def build_messages(self, user_query: str, memory_manager) -> list:
        """
        Builds the message list including system prompts,
        loaded preferences, and conversation history.
        """
        from skills import SKILL_INSTANCES
        import json

        # Load learned preferences from daily memory files
        preferences = memory_manager.load_preferences()
        
        # Build tool descriptions dynamically with mock JSON examples
        tool_lines = []
        for i, skill in enumerate(SKILL_INSTANCES.values(), 1):
            mock_args = {}
            if skill.parameters and "properties" in skill.parameters:
                props = skill.parameters["properties"]
                # Use required fields, or fallback to first 2 properties if none required
                required_fields = skill.parameters.get("required", list(props.keys())[:2])
                for field in required_fields:
                    if field in props:
                        p_type = props[field].get("type", "string")
                        if p_type in ["integer", "number"]:
                            mock_args[field] = 5
                        elif p_type == "boolean":
                            mock_args[field] = True
                        else:
                            # Try to extract a clean string example from description
                            if "location" in field:
                                mock_args[field] = "Kokomo, Indiana"
                            elif "symbol" in field or "ticker" in field:
                                mock_args[field] = "PLTR"
                            elif "query" in field:
                                mock_args[field] = "Palantir"
                            elif "preference" in field:
                                mock_args[field] = "User lives in Kokomo, Indiana"
                            else:
                                mock_args[field] = "example_value"
            
            example_json = {
                "name": skill.name,
                "arguments": mock_args
            }
            example_str = json.dumps(example_json)
            
            tool_lines.append(
                f"{i}. '{skill.name}': {skill.description}\n"
                f"   Example: {example_str}"
            )
            
        tool_descriptions = "\n".join(tool_lines)
        
        # Build critical rules dynamically for each loaded skill
        critical_lines = []
        for skill in SKILL_INSTANCES.values():
            if skill.name == "save_preference":
                critical_lines.append("- If the user shares a fact about themselves, you MUST use 'save_preference' to store it. Do not just say 'I will remember that' conversationally; output the JSON tool call block.")
            elif skill.name == "fetch_weather":
                critical_lines.append("- You MUST call 'fetch_weather' for any query about weather. Never claim you don't have access to weather data.")
            elif skill.name == "fetch_news_headlines":
                critical_lines.append("- You MUST call 'fetch_news_headlines' for any query, question, or updates about news, headlines, or current events. Never claim you don't have access to news updates.")
            elif skill.name == "fetch_stock_ticker":
                critical_lines.append("- You MUST call 'fetch_stock_ticker' for any query about stock prices, tickers, or financial markets.")
            else:
                # Dynamic rule for custom/user created skills
                critical_lines.append(f"- You MUST call '{skill.name}' for any query or instruction related to: {skill.description}. Never say you performed the action or respond conversationally without outputting the JSON tool call.")
        
        # Add real-time event check general rule
        critical_lines.append("- You MUST call a tool for any query about current/real-time events or requests requiring external information. Never claim you don't have access to real-time information.")
        critical_rules = "\n".join(critical_lines)
        
        # Format the system prompt template
        system_prompt = config.LLM_SYSTEM_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_descriptions,
            critical_rules=critical_rules
        )
        if preferences:
            system_prompt += f"\n{preferences}"
            
        messages = [{"role": "system", "content": system_prompt}]
        
        # Load last N turns of recent conversation history
        recent_turns = memory_manager.load_recent_context(limit=10)
        messages.extend(recent_turns)
        
        # Append the new user query
        messages.append({"role": "user", "content": user_query})
        return messages
