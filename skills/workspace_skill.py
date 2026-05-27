import os
import logging
from skills.base_skill import BaseSkill

logger = logging.getLogger("Prim.Skills.Workspace")

class ListWorkspaceFiles(BaseSkill):
    @property
    def name(self) -> str:
        return "list_workspace_files"

    @property
    def description(self) -> str:
        return "List all files recursively in the active coding workspace."

    @property
    def parameters(self) -> dict:
        return {}

    def execute(self, **kwargs) -> str:
        workspace = BaseSkill.active_workspace
        if not workspace:
            return "Error: No active workspace folder selected. Please select a workspace first."

        try:
            file_list = []
            for root, dirs, files in os.walk(workspace):
                # Ignore common folders to prevent token bloat
                if any(ignored in root for ignored in [".git", "venv", "__pycache__", "venv\\", ".idea", "storage", "brain"]):
                    continue
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), workspace)
                    rel_path = rel_path.replace("\\", "/")
                    file_list.append(rel_path)
            
            if not file_list:
                return "The workspace directory is empty."
            return "Workspace Files:\n" + "\n".join(f"- {f}" for f in file_list)
        except Exception as e:
            return f"Error listing workspace files: {e}"


class ReadWorkspaceFile(BaseSkill):
    @property
    def name(self) -> str:
        return "read_workspace_file"

    @property
    def description(self) -> str:
        return "Read and return the complete text contents of a specific file inside the active workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The relative path to the file inside the workspace (e.g. 'src/main.py')"
                }
            },
            "required": ["filepath"]
        }

    def execute(self, **kwargs) -> str:
        workspace = BaseSkill.active_workspace
        if not workspace:
            return "Error: No active workspace folder selected. Please select a workspace first."

        filepath = kwargs.get("filepath")
        if not filepath:
            return "Error: No filepath parameter provided."

        try:
            full_path = os.path.abspath(os.path.join(workspace, filepath))
            if not full_path.startswith(os.path.abspath(workspace)):
                return "Error: Access denied. Targeted file path is outside the active workspace."

            if not os.path.exists(full_path):
                return f"Error: File '{filepath}' does not exist."

            if os.path.isdir(full_path):
                return f"Error: '{filepath}' is a directory, not a file."

            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return f"--- Content of '{filepath}' ---\n{content}"
        except Exception as e:
            return f"Error reading file '{filepath}': {e}"


class WriteWorkspaceFile(BaseSkill):
    @property
    def name(self) -> str:
        return "write_workspace_file"

    @property
    def description(self) -> str:
        return "Create a new file or overwrite an existing file with new text content inside the active workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "The relative path to the file inside the workspace (e.g. 'src/utils.py')"
                },
                "content": {
                    "type": "string",
                    "description": "The complete source code/text content to write to the file."
                }
            },
            "required": ["filepath", "content"]
        }

    def execute(self, **kwargs) -> str:
        workspace = BaseSkill.active_workspace
        if not workspace:
            return "Error: No active workspace folder selected. Please select a workspace first."

        filepath = kwargs.get("filepath")
        content = kwargs.get("content")

        if not filepath or content is None:
            return "Error: Missing required parameters 'filepath' or 'content'."

        try:
            full_path = os.path.abspath(os.path.join(workspace, filepath))
            if not full_path.startswith(os.path.abspath(workspace)):
                return "Error: Access denied. Targeted file path is outside the active workspace."

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            logger.info(f"Workspace file written successfully: {filepath}")
            if self.active_dashboard:
                self.active_dashboard.add_log(f"Agent modified workspace file: {filepath}")
                
            return f"Successfully wrote/updated '{filepath}' in workspace."
        except Exception as e:
            return f"Error writing file '{filepath}': {e}"
