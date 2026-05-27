import os
import glob
from datetime import datetime
import re
import logging
import config

logger = logging.getLogger("Prim.Memory")

class MemoryManager:
    def __init__(self, memory_dir=None):
        self.memory_dir = memory_dir if memory_dir is not None else config.MEMORY_DIR
        os.makedirs(self.memory_dir, exist_ok=True)
        self.current_file = os.path.join(self.memory_dir, f"{datetime.now().strftime('%Y-%m-%d')}.md")
        self._init_current_file()

    def _init_current_file(self):
        """Initializes the daily memory file with structure if it doesn't exist."""
        if not os.path.exists(self.current_file):
            try:
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(f"# Session Log - {datetime.now().strftime('%Y-%m-%d')}\n\n")
                    f.write("## Conversation\n\n")
                    f.write("## User Preferences / Learnings\n")
                    f.write("- (No preferences learned yet today)\n\n")
                logger.info(f"Initialized new daily log: {self.current_file}")
            except Exception as e:
                logger.error(f"Error initializing memory file: {e}")

    def load_preferences(self) -> str:
        """
        Parses all markdown files in the memory directory to extract user preferences and learnings.
        Looks under the '## User Preferences / Learnings' section.
        """
        preferences = []
        pattern = re.compile(r"## User Preferences / Learnings\s*\n(.*?)(?=\n##|\Z)", re.DOTALL)
        
        # Get all markdown files in chronological order
        md_files = sorted(glob.glob(os.path.join(self.memory_dir, "*.md")))
        
        for file_path in md_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                match = pattern.search(content)
                if match:
                    section = match.group(1).strip()
                    # Split by bullet points and clean up
                    for line in section.split("\n"):
                        line = line.strip()
                        if line.startswith("-") and "(No preferences learned yet today)" not in line:
                            pref = line.lstrip("- ").strip()
                            if pref and pref not in preferences:
                                preferences.append(pref)
            except Exception as e:
                logger.error(f"Error reading file {file_path} for preferences: {e}")
        
        if preferences:
            return "### User Preferences / Learnings:\n" + "\n".join(f"- {p}" for p in preferences)
        return ""

    def load_recent_context(self, limit=10) -> list:
        """
        Loads the last 'limit' messages from the current or previous log files for context insertion,
        maintaining chronological order (oldest turns first, newest turns last).
        """
        turns = []
        md_files = sorted(glob.glob(os.path.join(self.memory_dir, "*.md")))
        if not md_files:
            return turns

        # Read backward from the latest files (most recent day first)
        for file_path in reversed(md_files):
            if len(turns) >= limit:
                break
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                # Extract conversation turns from the file
                # In each file, turns are prepended (newest at the top of ## Conversation)
                in_conversation = False
                turns_list = []  # list of lists of messages
                current_turn = []
                
                for line in lines:
                    line = line.strip()
                    if line.startswith("## Conversation"):
                        in_conversation = True
                        continue
                    elif line.startswith("## "):
                        in_conversation = False
                        continue
                    
                    if in_conversation:
                        user_match = re.match(r"^-\s*\*\*(User)\*\*:\s*(.*)$", line)
                        tool_call_match = re.match(r"^-\s*\*\*(Prim \(Tool Call\))\*\*:\s*(.*)$", line)
                        tool_result_match = re.match(r"^-\s*\*\*(Tool Result)\*\*:\s*(.*)$", line)
                        prim_match = re.match(r"^-\s*\*\*(Prim|Prim \(Interrupted\))\*\*:\s*(.*)$", line)
                        
                        msg = None
                        is_user = False
                        if user_match:
                            msg = {"role": "user", "content": user_match.group(2).strip()}
                            is_user = True
                        elif tool_call_match:
                            tc_text = tool_call_match.group(3).strip()
                            try:
                                import json
                                tc_data = json.loads(tc_text)
                                tool_calls = [{
                                    "function": {
                                        "name": tc_data.get("name"),
                                        "arguments": tc_data.get("arguments", {})
                                    }
                                }]
                            except Exception:
                                tool_calls = []
                            msg = {"role": "assistant", "content": "", "tool_calls": tool_calls}
                        elif tool_result_match:
                            msg = {"role": "tool", "content": tool_result_match.group(2).strip()}
                        elif prim_match:
                            msg = {"role": "assistant", "content": prim_match.group(2).strip()}
                            
                        if msg:
                            if is_user:
                                if current_turn:
                                    turns_list.append(current_turn)
                                current_turn = [msg]
                            else:
                                current_turn.append(msg)
                
                if current_turn:
                    turns_list.append(current_turn)
                
                # We want the newest turns first (which are at the start of turns_list)
                # up to the remaining limit.
                selected_turns = []
                count = 0
                for turn in turns_list:
                    needed = limit - len(turns)
                    if count + len(turn) <= needed:
                        selected_turns.append(turn)
                        count += len(turn)
                    else:
                        break
                
                # Convert the selected turns back to chronological order (oldest of selected turns first)
                flat_msgs = []
                for turn in reversed(selected_turns):
                    flat_msgs.extend(turn)
                
                # Prepend the older file's turns before the newer ones
                turns = flat_msgs + turns
            except Exception as e:
                logger.error(f"Error reading context from {file_path}: {e}")

        return turns

    def save_turn_messages(self, turn_messages: list):
        """Saves a complete conversation turn, including any intermediate tool calls and tool results, to the markdown file."""
        self._init_current_file()  # Ensure file exists
        if not turn_messages:
            return
            
        try:
            # Read current content
            with open(self.current_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find '## Conversation' and inject the turn right after it
            conv_header = "## Conversation\n"
            idx = content.find(conv_header)
            if idx != -1:
                insert_pos = idx + len(conv_header)
                
                # Format each message in the turn
                formatted_lines = []
                for msg in turn_messages:
                    role = msg.get("role")
                    content_str = msg.get("content", "")
                    
                    if role == "user":
                        formatted_lines.append(f"- **User**: {content_str}")
                    elif role == "tool":
                        formatted_lines.append(f"- **Tool Result**: {content_str}")
                    elif role == "assistant":
                        tool_calls = msg.get("tool_calls", [])
                        if tool_calls:
                            # Save first tool call's name and arguments as a simple JSON string
                            import json
                            tc = tool_calls[0]
                            tc_func = tc.get("function", {})
                            tc_data = {
                                "name": tc_func.get("name"),
                                "arguments": tc_func.get("arguments", {})
                            }
                            formatted_lines.append(f"- **Prim (Tool Call)**: {json.dumps(tc_data)}")
                        elif content_str.strip():
                            formatted_lines.append(f"- **Prim**: {content_str.strip()}")
                
                new_turn = "\n".join(formatted_lines) + "\n"
                updated_content = content[:insert_pos] + new_turn + content[insert_pos:]
                
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                logger.info("Saved complete turn (with tool messages) to memory.")
            else:
                # Appending fallback
                with open(self.current_file, "a", encoding="utf-8") as f:
                    for msg in turn_messages:
                        role = msg.get("role")
                        content_str = msg.get("content", "")
                        if role == "user":
                            f.write(f"- **User**: {content_str}\n")
                        elif role == "tool":
                            f.write(f"- **Tool Result**: {content_str}\n")
                        elif role == "assistant":
                            tool_calls = msg.get("tool_calls", [])
                            if tool_calls:
                                import json
                                tc = tool_calls[0]
                                tc_func = tc.get("function", {})
                                tc_data = {
                                    "name": tc_func.get("name"),
                                    "arguments": tc_func.get("arguments", {})
                                }
                                f.write(f"- **Prim (Tool Call)**: {json.dumps(tc_data)}\n")
                            elif content_str.strip():
                                f.write(f"- **Prim**: {content_str.strip()}\n")
        except Exception as e:
            logger.error(f"Error saving turn messages: {e}")

    def save_turn(self, user_text: str, assistant_text: str):
        """Saves a standard conversation turn to the markdown file."""
        self._init_current_file()  # Ensure file exists
        try:
            # Read current content
            with open(self.current_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find '## Conversation' and inject the turn right after it
            conv_header = "## Conversation\n"
            idx = content.find(conv_header)
            if idx != -1:
                insert_pos = idx + len(conv_header)
                new_turn = f"- **User**: {user_text}\n- **Prim**: {assistant_text}\n"
                updated_content = content[:insert_pos] + new_turn + content[insert_pos:]
                
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                logger.info("Saved turn to memory.")
            else:
                # Appending fallback
                with open(self.current_file, "a", encoding="utf-8") as f:
                    f.write(f"- **User**: {user_text}\n- **Prim**: {assistant_text}\n")
        except Exception as e:
            logger.error(f"Error saving turn: {e}")

    def save_interrupted_turn(self, user_text: str, truncated_assistant_text: str):
        """Saves a turn that was cut off by user interruption."""
        self._init_current_file()
        try:
            with open(self.current_file, "r", encoding="utf-8") as f:
                content = f.read()

            conv_header = "## Conversation\n"
            idx = content.find(conv_header)
            if idx != -1:
                insert_pos = idx + len(conv_header)
                new_turn = f"- **User**: {user_text}\n- **Prim (Interrupted)**: {truncated_assistant_text}...\n"
                updated_content = content[:insert_pos] + new_turn + content[insert_pos:]
                
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                logger.info("Saved interrupted turn to memory.")
            else:
                with open(self.current_file, "a", encoding="utf-8") as f:
                    f.write(f"- **User**: {user_text}\n- **Prim (Interrupted)**: {truncated_assistant_text}...\n")
        except Exception as e:
            logger.error(f"Error saving interrupted turn: {e}")

    def learn_preference(self, preference: str):
        """Appends a newly discovered user preference to the current file."""
        self._init_current_file()
        try:
            with open(self.current_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Find '## User Preferences / Learnings'
            pref_header = "## User Preferences / Learnings\n"
            idx = content.find(pref_header)
            if idx != -1:
                insert_pos = idx + len(pref_header)
                
                # Check if "No preferences learned yet today" is there, remove it
                section = content[insert_pos:]
                no_pref_str = "- (No preferences learned yet today)\n"
                if section.startswith(no_pref_str):
                    content = content[:insert_pos] + section[len(no_pref_str):]
                
                updated_content = content[:insert_pos] + f"- {preference}\n" + content[insert_pos:]
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                logger.info(f"Learned preference: {preference}")
        except Exception as e:
            logger.error(f"Error saving learned preference: {e}")
