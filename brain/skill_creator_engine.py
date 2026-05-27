import re
import os
import sys
import py_compile
import logging
import inspect
import traceback
from skills import reload_skills, SKILL_INSTANCES

logger = logging.getLogger("Prim.SkillCreatorEngine")

def extract_and_write_skill(llm_response_text: str) -> dict:
    """
    Parses LLM response text for <filename> and <skill_code> tags.
    If found, writes to the skills/ directory, compiles it to check for syntax errors,
    and reloads the skill registry.
    
    Returns a dict with success status and any error/filename details.
    """
    # 1. Search for filename and code tags
    filename_match = re.search(r"<filename>(.*?)</filename>", llm_response_text, re.DOTALL)
    code_match = re.search(r"<skill_code>(.*?)</skill_code>", llm_response_text, re.DOTALL)
    
    if not filename_match or not code_match:
        logger.debug("LLM response did not contain both <filename> and <skill_code> tags.")
        return {
            "success": False,
            "error": "The response did not contain both <filename>filename_here.py</filename> and <skill_code>code_here</skill_code> tags. Please ask the LLM to output the skill using this format."
        }
        
    filename = filename_match.group(1).strip()
    code_content = code_match.group(1)
    
    # Basic filename validation
    filename = os.path.basename(filename)  # Prevent directory traversal
    if not filename.endswith(".py"):
        filename += ".py"
        
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    file_path = os.path.join(skills_dir, filename)
    
    logger.info(f"Extracting skill to: {file_path}")
    
    # 2. Backup existing file content in case compilation fails
    old_content = None
    file_existed = os.path.exists(file_path)
    if file_existed:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception as e:
            logger.warning(f"Could not backup existing file: {e}")
            
    # 3. Write new code content to file
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code_content)
    except Exception as e:
        logger.error(f"Failed to write skill file: {e}")
        return {
            "success": False,
            "error": f"Failed to write skill to disk: {e}"
        }
        
    # 4. Compile the file to verify syntax
    try:
        py_compile.compile(file_path, doraise=True)
        logger.info(f"Successfully compiled {filename}")
    except py_compile.PyCompileError as compile_err:
        logger.error(f"Syntax error compiling generated skill {filename}: {compile_err}")
        
        # Rollback: restore old content or delete if it was a new file
        try:
            if file_existed and old_content is not None:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(old_content)
                logger.info(f"Rolled back changes to {filename} due to compile error.")
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)
                logger.info(f"Removed temporary invalid file {filename} due to compile error.")
        except Exception as rollback_err:
            logger.error(f"Rollback failed: {rollback_err}")
            
        # Clean compile error message to feed back to LLM
        err_msg = str(compile_err)
        # Clean paths for cleaner prompts
        err_msg = err_msg.replace(file_path, filename)
        return {
            "success": False,
            "error": f"Syntax compilation failed:\n{err_msg}\n\nPlease check the syntax and generate the corrected class structure."
        }
        
    # 5. Reload skills in the main app
    try:
        reload_skills()
    except Exception as reload_err:
        logger.error(f"Failed to reload skills registry: {reload_err}")
        return {
            "success": False,
            "error": f"Skill written, but app failed to dynamically load it: {reload_err}"
        }
        
    return {
        "success": True,
        "filename": filename
    }

def delete_skill(skill_name: str) -> dict:
    """
    Deletes the Python file corresponding to a registered skill name,
    and triggers a dynamic skill reload.
    """
    logger.info(f"Requested deletion of skill: '{skill_name}'")
    skill_obj = SKILL_INSTANCES.get(skill_name)
    if not skill_obj:
        return {
            "success": False,
            "error": f"Skill '{skill_name}' is not currently loaded or does not exist."
        }
        
    try:
        # Get absolute file path of the class module
        file_path = inspect.getfile(skill_obj.__class__)
        filename = os.path.basename(file_path)
        
        if filename in ["base_skill.py", "__init__.py"]:
            return {
                "success": False,
                "error": f"Cannot delete core file: {filename}"
            }
            
        if os.path.exists(file_path):
            os.remove(file_path)
            # Remove compiled bytecode if exists
            pyc_path = file_path + "c"
            if os.path.exists(pyc_path):
                os.remove(pyc_path)
            # Check __pycache__ directory as well
            pycache_dir = os.path.join(os.path.dirname(file_path), "__pycache__")
            if os.path.exists(pycache_dir):
                base_no_ext = os.path.splitext(filename)[0]
                for f in os.listdir(pycache_dir):
                    if f.startswith(base_no_ext) and f.endswith(".pyc"):
                        try:
                            os.remove(os.path.join(pycache_dir, f))
                        except Exception:
                            pass
                            
            logger.info(f"Successfully deleted file: {file_path}")
            reload_skills()
            return {"success": True, "filename": filename}
        else:
            return {
                "success": False,
                "error": f"File path '{file_path}' does not exist on disk."
            }
    except Exception as e:
        logger.error(f"Error deleting skill '{skill_name}': {e}")
        return {
            "success": False,
            "error": f"Error during deletion process: {str(e)}"
        }
