# Implementation Blueprint: Project Prim Coding Mode & OpenCode Workspace Integration

## 🎯 Objective
Integrate an isolated "Coding Mode" toggle into Project Prim that bypasses conversational voice skills to save context/token overhead. Implement an explicit directory selector workspace UI, allowing the user to target an existing project directory or initialize a fresh repository workspace for agentic multi-file refactoring.

---

## 🛠️ Phase 1: Configuration & Workspace Core Setup (`config.py`)
- [x] **1.1 Add Mode Constants**  
  Define explicit application states at the bottom of `config.py`:
  ```python
  ASSISTANT_MODE = "ASSISTANT"
  CODING_MODE = "CODING"
  ```
- [x] **1.2 Add Coding System Prompt**  
  Add `LLM_CODING_SYSTEM_PROMPT_TEMPLATE` in `config.py` optimized for local code refactoring and workspace multi-file editing.

---

## 🛠️ Phase 2: Create Workspace Skills (`skills/workspace_skill.py`)
- [x] **2.1 Define Workspace Actions**  
  Create a new skill file defining three workspace functions:
  - `list_workspace_files`: returns recursive file list.
  - `read_workspace_file`: reads file content inside active workspace.
  - `write_workspace_file`: writes/overwrites file inside active workspace.
- [x] **2.2 Support Workspace Attribute in BaseSkill**  
  Add `active_workspace` class property to `BaseSkill` in `skills/base_skill.py`.

---

## 🛠️ Phase 3: Dashboard UI Integration (`ui/dashboard.py`)
- [x] **3.1 Add Mode Toggle Switch**  
  Add a switch/button to toggle between ASSISTANT and CODING modes in the sidebar.
- [x] **3.2 Add Workspace Selector Elements**  
  Add a select workspace button and active directory label to the sidebar.
- [x] **3.3 Wire UI Callbacks**  
  Map events to trigger callbacks in `main.py` for mode changes and directory selections.

---

## 🛠️ Phase 4: Main Application & LLM Client Integration
- [x] **4.1 Handle Coding Mode & Workspace in `main.py`**  
  Store current mode and active workspace path. Dynamically set `BaseSkill.active_workspace` upon selection.
- [x] **4.2 Update Message Builder in `llm_client.py`**  
  Update `build_messages` to check current mode. If in `CODING` mode, use `LLM_CODING_SYSTEM_PROMPT_TEMPLATE` and restrict or prioritize workspace tools.
- [x] **4.3 Configure Mode Bypass in Orchestration Loop**  
  Bypass VAD and wake-word recording loops when in `CODING` mode to completely prevent microphone bleed and focus strictly on typed coding inputs.

---

## 🛠️ Phase 5: Verification & Testing
- [x] **5.1 Compile and Syntax Check**  
  Run syntax compilation checks on all modified and new files.
- [x] **5.2 End-to-End Test**  
  Verify selecting a workspace directory, switching to Coding Mode, and submitting a multi-file coding task.