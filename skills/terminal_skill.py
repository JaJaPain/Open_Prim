import os
import subprocess
import re
import logging
from skills.base_skill import BaseSkill

logger = logging.getLogger("Prim.Skills.Terminal")

def is_unsafe_command(command: str) -> tuple[bool, str]:
    """Scans command string for potentially unsafe or destructive actions."""
    cmd_lower = command.lower().strip()
    
    # Destructive command patterns
    unsafe_patterns = [
        ("format ", "disk formatting operations are blocked"),
        ("diskpart", "disk partition operations are blocked"),
        ("fdisk", "disk partition operations are blocked"),
        ("mkfs", "filesystem creation operations are blocked"),
    ]
    
    for pat, reason in unsafe_patterns:
        if pat in cmd_lower:
            return True, reason
            
    # Match rm -rf / or rm -rf * or similar Unix patterns
    if re.search(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+([/*\\])", cmd_lower):
        return True, "root/wildcard recursive deletion is blocked"
        
    # Match Windows root directory deletions e.g., rmdir /s /q C:\
    if re.search(r"(rmdir|del)\s+.*[c-zC-Z]:[\\/]", cmd_lower):
        return True, "drive-root deletion operations are blocked"
        
    # Match targeting sensitive folders
    sensitive_folders = [
        "windows", "system32", "program files", "program files (x86)",
        "etc", "usr/bin", "bin", "var/run", "lib", "sys", "boot"
    ]
    
    # Check if command mentions any sensitive folders in a way that suggests modification or deletion
    # e.g., rm, del, rmdir, mv, move
    if any(action in cmd_lower for action in ["rm ", "del ", "rmdir ", "mv ", "move "]):
        for folder in sensitive_folders:
            pattern = rf"[\\/]{folder}([\\/]|$|\s)"
            if re.search(pattern, cmd_lower):
                return True, f"modifications/deletions targeting sensitive directory '{folder}' are blocked"
                
    return False, ""


class RunTerminalCommand(BaseSkill):
    @property
    def name(self) -> str:
        return "run_terminal_command"

    @property
    def description(self) -> str:
        return "Execute a shell command inside the active workspace directory. Use this to install dependencies, run scripts, compile code, or run test suites."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command line to run (e.g. 'pip install pygame' or 'python main.py')"
                }
            },
            "required": ["command"]
        }

    def execute(self, **kwargs) -> str:
        workspace = BaseSkill.active_workspace
        if not workspace:
            return "Error: No active workspace folder selected. Please select a workspace first."

        command = kwargs.get("command")
        if not command:
            return "Error: Missing required parameter 'command'."

        # 1. Safety Scan
        is_unsafe, reason = is_unsafe_command(command)
        if is_unsafe:
            logger.warning(f"Blocked unsafe command: {command}. Reason: {reason}")
            return f"Error: Command execution blocked for safety. Reason: {reason}."

        try:
            # 2. Local Environment Isolation (Auto-Venv Creation)
            venv_dir = os.path.join(workspace, "venv")
            env = os.environ.copy()
            
            if not os.path.exists(venv_dir):
                logger.info(f"Local virtual environment 'venv' not found in workspace. Initializing new venv...")
                if self.active_dashboard:
                    self.active_dashboard.add_log("Initializing new local virtual environment (venv) inside workspace...")
                
                # Create the venv
                subprocess.run(
                    ["python", "-m", "venv", "venv"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
            # Confine command to the workspace virtual environment by prefixing Scripts to PATH
            scripts_dir = os.path.abspath(os.path.join(venv_dir, "Scripts"))
            if os.path.exists(scripts_dir):
                env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
                logger.debug(f"Prefixed PATH with workspace venv scripts directory: {scripts_dir}")

            # 3. Subprocess Execution
            logger.info(f"Running terminal command in workspace: {command}")
            if self.active_dashboard:
                self.active_dashboard.add_log(f"Agent executing terminal command: {command}")

            res = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = ""
            if res.stdout:
                output += f"Output:\n{res.stdout}\n"
            if res.stderr:
                output += f"Errors/Warnings:\n{res.stderr}\n"

            status_msg = f"Command completed with exit code {res.returncode}."
            return f"{status_msg}\n{output}"

        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {command}")
            return "Error: Command execution timed out after 120 seconds."
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return f"Error executing command: {e}"
