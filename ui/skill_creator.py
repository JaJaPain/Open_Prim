import sys
import os
import threading
import logging
import inspect
import tkinter.messagebox as messagebox
from datetime import datetime
import config

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

from brain.skill_creator_engine import extract_and_write_skill, delete_skill

logger = logging.getLogger("Prim.SkillCreatorUI")

class SkillCreatorWindow(ctk.CTkToplevel):
    def __init__(self, parent, llm_client, refresh_callback=None):
        super().__init__(parent)
        self.llm_client = llm_client
        self.refresh_callback = refresh_callback
        
        self.selected_skill = None
        self.skill_buttons = {}
        self.chat_history = [{"role": "system", "content": config.SKILL_CREATOR_SYSTEM_PROMPT}]
        
        self.title("Prim Skill Creator Studio")
        self.geometry("1000x700")
        self.minsize(800, 600)
        
        # Style layout grid
        self.grid_columnconfigure(0, weight=1)  # Left list
        self.grid_columnconfigure(1, weight=3)  # Right chat
        self.grid_rowconfigure(0, weight=1)
        
        self._build_ui()
        self._refresh_skills_list()
        
        # Grab keyboard focus
        self.after(100, self.lift)
        self.after(200, self.focus_force)

    def _build_ui(self):
        # ----------------- LEFT SIDEBAR (Skills List) -----------------
        self.sidebar = ctk.CTkFrame(self, corner_radius=15, fg_color="#131317")
        self.sidebar.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(2, weight=1)  # List area stretches
        
        # Title
        self.list_title = ctk.CTkLabel(
            self.sidebar,
            text="ACTIVE SKILLS",
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            text_color="#00B4D8"
        )
        self.list_title.grid(row=0, column=0, padx=15, pady=(20, 5), sticky="w")
        
        self.list_subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Click a skill to alter or delete it",
            font=ctk.CTkFont(family="Helvetica", size=11),
            text_color="#718096"
        )
        self.list_subtitle.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        
        # Scrollable list of skills
        self.skills_list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="#1E1E24", corner_radius=10)
        self.skills_list_frame.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        
        # Skill Preview Info Box
        self.skill_info_textbox = ctk.CTkTextbox(
            self.sidebar,
            height=120,
            corner_radius=10,
            fg_color="#1E1E24",
            text_color="#A0AEC0",
            font=ctk.CTkFont(size=12)
        )
        self.skill_info_textbox.grid(row=3, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.skill_info_textbox.insert("1.0", "Select a skill from the list above to view details.")
        self.skill_info_textbox.configure(state="disabled")
        
        # Actions Panel (Alter & Delete buttons)
        self.actions_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.actions_frame.grid(row=4, column=0, padx=15, pady=(0, 20), sticky="ew")
        self.actions_frame.grid_columnconfigure(0, weight=1)
        self.actions_frame.grid_columnconfigure(1, weight=1)
        
        self.alter_btn = ctk.CTkButton(
            self.actions_frame,
            text="ALTER",
            command=self._on_alter_click,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2D3748",
            hover_color="#4A5568",
            state="disabled",
            corner_radius=8,
            height=34
        )
        self.alter_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.delete_btn = ctk.CTkButton(
            self.actions_frame,
            text="DELETE",
            command=self._on_delete_click,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#E53E3E",
            hover_color="#C53030",
            state="disabled",
            corner_radius=8,
            height=34
        )
        self.delete_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # ----------------- RIGHT PANEL (Chat Interface) -----------------
        self.chat_area = ctk.CTkFrame(self, corner_radius=15, fg_color="#0F0F11")
        self.chat_area.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="nsew")
        self.chat_area.grid_columnconfigure(0, weight=1)
        self.chat_area.grid_rowconfigure(1, weight=1)  # Chat log stretches
        
        # Header title
        self.chat_title = ctk.CTkLabel(
            self.chat_area,
            text="SKILL GENERATOR CHAT",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#A0AEC0"
        )
        self.chat_title.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        
        # Chat dialogue history textbox
        self.chat_textbox = ctk.CTkTextbox(
            self.chat_area,
            corner_radius=10,
            fg_color="#1E1E24",
            text_color="#F7FAFC",
            font=ctk.CTkFont(size=13)
        )
        self.chat_textbox.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="nsew")
        self.chat_textbox.configure(state="disabled")
        
        # Opening welcome message
        self._append_message("System", "Welcome to the Prim Skill Creator Studio! Describe what custom task, API, or command you'd like Prim to execute. I will automatically design the code structure, test compile it, and install it into the voice assistant for you.")
        
        # Chat input frame
        self.input_frame = ctk.CTkFrame(self.chat_area, corner_radius=10, fg_color="#1E1E24")
        self.input_frame.grid(row=2, column=0, padx=20, pady=(0, 5), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.chat_entry = ctk.CTkTextbox(
            self.input_frame,
            font=ctk.CTkFont(size=13),
            fg_color="#2D3748",
            text_color="#F7FAFC",
            border_color="#4A5568",
            border_width=1,
            corner_radius=8,
            height=70,
            wrap="word"
        )
        self.chat_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")
        self.chat_entry.bind("<Return>", self._on_send_click)
        
        # Placeholder behavior
        self.placeholder = "Tell the developer assistant what skill you want to create..."
        self.chat_entry.insert("1.0", self.placeholder)
        self.chat_entry.configure(text_color="#718096")
        
        self.chat_entry.bind("<FocusIn>", self._on_focus_in)
        self.chat_entry.bind("<FocusOut>", self._on_focus_out)
        
        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Send",
            command=self._on_send_click,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#00B4D8",
            hover_color="#0096B7",
            corner_radius=8,
            width=70,
            height=38
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 10), pady=10)
        
        # Status Bar
        self.status_label = ctk.CTkLabel(
            self.chat_area,
            text="Status: Ready",
            font=ctk.CTkFont(family="Courier", size=11),
            text_color="#718096"
        )
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="w")

    def _refresh_skills_list(self):
        """Clears and re-populates the sidebar scrollable list of skills."""
        for widget in self.skills_list_frame.winfo_children():
            widget.destroy()
            
        from skills import SKILL_INSTANCES
        self.skill_buttons = {}
        
        for name, skill in SKILL_INSTANCES.items():
            btn = ctk.CTkButton(
                self.skills_list_frame,
                text=name,
                command=lambda n=name: self._on_skill_selected(n),
                anchor="w",
                fg_color="transparent",
                text_color="#E2E8F0",
                hover_color="#2D3748",
                height=30
            )
            btn.pack(fill="x", padx=5, pady=2)
            self.skill_buttons[name] = btn
            
        self.selected_skill = None
        self.alter_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        
        self.skill_info_textbox.configure(state="normal")
        self.skill_info_textbox.delete("1.0", "end")
        self.skill_info_textbox.insert("1.0", "Select a skill from the list above to view details.")
        self.skill_info_textbox.configure(state="disabled")

    def _on_skill_selected(self, name):
        self.selected_skill = name
        
        # Update colors
        for btn_name, btn in self.skill_buttons.items():
            if btn_name == name:
                btn.configure(fg_color="#00B4D8", text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#E2E8F0")
                
        self.alter_btn.configure(state="normal")
        self.delete_btn.configure(state="normal")
        
        from skills import SKILL_INSTANCES
        skill = SKILL_INSTANCES.get(name)
        if skill:
            try:
                file_path = inspect.getfile(skill.__class__)
                filename = os.path.basename(file_path)
            except Exception:
                filename = "Unknown"
                
            info = f"File: {filename}\nName: {skill.name}\nDescription: {skill.description}\n"
            if skill.filler_keywords:
                info += f"Keywords: {', '.join(skill.filler_keywords)}\n"
            self.skill_info_textbox.configure(state="normal")
            self.skill_info_textbox.delete("1.0", "end")
            self.skill_info_textbox.insert("1.0", info)
            self.skill_info_textbox.configure(state="disabled")

    def _on_alter_click(self):
        """Pre-loads the selected skill's source code and sends it to the chat context."""
        if not self.selected_skill:
            return
            
        from skills import SKILL_INSTANCES
        skill = SKILL_INSTANCES.get(self.selected_skill)
        if not skill:
            return
            
        try:
            file_path = inspect.getfile(skill.__class__)
            filename = os.path.basename(file_path)
            
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
                
            prompt = f"I want to alter the existing skill '{self.selected_skill}'. Here is its current source code in '{filename}':\n\n```python\n{code}\n```\n\nPlease help me modify this skill. What changes would you like to make?"
            
            self.chat_history.append({"role": "user", "content": prompt})
            self._append_message("You (Alter)", f"Requested modifications to '{self.selected_skill}' skill.")
            
            self._send_chat_to_llm()
        except Exception as e:
            logger.error(f"Error loading source for altering: {e}")
            self._append_message("System", f"Failed to load source code for altering: {e}")

    def _on_delete_click(self):
        if not self.selected_skill:
            return
            
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to permanently delete the skill '{self.selected_skill}'? This will delete the python source file from the disk.",
            parent=self
        )
        if confirm:
            self._update_status("Deleting skill...")
            res = delete_skill(self.selected_skill)
            if res.get("success"):
                self._update_status("Skill deleted successfully.")
                self._append_message("System", f"Successfully deleted skill file '{res.get('filename')}' and reloaded registry.")
                self._refresh_skills_list()
                if self.refresh_callback:
                    self.refresh_callback()
            else:
                self._update_status("Deletion failed.")
                messagebox.showerror("Deletion Error", res.get("error", "Unknown error occurred."), parent=self)

    def _on_focus_in(self, event):
        val = self.chat_entry.get("1.0", "end-1c").strip()
        if val == self.placeholder:
            self.chat_entry.delete("1.0", "end")
            self.chat_entry.configure(text_color="#F7FAFC")

    def _on_focus_out(self, event):
        val = self.chat_entry.get("1.0", "end-1c").strip()
        if not val:
            self.chat_entry.insert("1.0", self.placeholder)
            self.chat_entry.configure(text_color="#718096")

    def _on_send_click(self, event=None):
        text = self.chat_entry.get("1.0", "end-1c").strip()
        if not text or text == self.placeholder:
            return "break" if event else None
            
        self.chat_entry.delete("1.0", "end")
        self._append_message("You", text)
        self.chat_history.append({"role": "user", "content": text})
        
        self._send_chat_to_llm()
        return "break" if event else None

    def _send_chat_to_llm(self):
        """Starts a background thread to call Ollama chat stream to keep the GUI responsive."""
        if not self.llm_client or not self.llm_client.client:
            self._append_message("System", "Ollama client is not running. Please ensure Ollama is active.")
            return
            
        self.send_btn.configure(state="disabled")
        self.chat_entry.configure(state="disabled")
        self._update_status("Thinking...")
        
        threading.Thread(target=self._query_llm_thread, daemon=True).start()

    def _query_llm_thread(self):
        try:
            # Query Ollama directly without structured tool bindings (straight conversational code generation)
            response = self.llm_client.client.chat(
                model=config.LLM_MODEL,
                messages=self.chat_history,
                stream=True,
                options={"temperature": 0.5}
            )
            
            # Start streaming UI representation
            self.after(0, lambda: self._start_streaming_gui("Developer Assistant"))
            
            assistant_response = ""
            for chunk in response:
                msg = chunk.get("message", {})
                if msg.get("content"):
                    token = msg["content"]
                    assistant_response += token
                    self.after(0, lambda t=token: self._update_stream_gui(t))
                    
            self.after(0, self._finalize_stream_gui)
            self.chat_history.append({"role": "assistant", "content": assistant_response})
            
            # Check if code block resides in the response
            if "<skill_code>" in assistant_response and "<filename>" in assistant_response:
                self.after(0, lambda: self._update_status("Compiling skill code..."))
                
                # Write and compile skill
                res = extract_and_write_skill(assistant_response)
                
                if res.get("success"):
                    filename = res.get("filename")
                    self.after(0, lambda: self._update_status("Skill installed successfully!"))
                    self.after(0, lambda: self._append_message("System", f"Installed skill '{filename}' and successfully compiled it. Registry reloaded. It is now active!"))
                    self.after(0, self._refresh_skills_list)
                    if self.refresh_callback:
                        self.after(0, self.refresh_callback)
                else:
                    err = res.get("error")
                    self.after(0, lambda: self._update_status("Compilation failed!"))
                    self.after(0, lambda: self._append_message("System", f"COMPILATION ERROR: {err}"))
                    
                    # Feed back compile error automatically to chat history to help LLM correct it
                    auto_correction_prompt = f"The code you generated failed compilation with the following error:\n{err}\n\nPlease analyze the traceback, fix the syntax error, and output the corrected version of the complete code wrapped in <filename> and <skill_code> tags."
                    self.chat_history.append({"role": "user", "content": auto_correction_prompt})
            else:
                self.after(0, lambda: self._update_status("Ready"))
                
        except Exception as e:
            logger.error(f"Error querying Ollama creator thread: {e}")
            self.after(0, lambda: self._append_message("System", f"Error querying local model: {e}"))
            self.after(0, lambda: self._update_status("Ready"))
        finally:
            self.after(0, self._restore_entry_state)

    def _restore_entry_state(self):
        self.send_btn.configure(state="normal")
        self.chat_entry.configure(state="normal")
        val = self.chat_entry.get("1.0", "end-1c").strip()
        if not val:
            self.chat_entry.insert("1.0", self.placeholder)
            self.chat_entry.configure(text_color="#718096")

    # ----------------- Thread-Safe GUI Helpers -----------------
    
    def _append_message(self, speaker, text):
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.insert("end", f"{speaker}: {text}\n\n")
        self.chat_textbox.see("end")
        self.chat_textbox.configure(state="disabled")

    def _start_streaming_gui(self, speaker):
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.insert("end", f"{speaker}: ")
        self.chat_textbox.see("end")
        self.chat_textbox.configure(state="disabled")

    def _update_stream_gui(self, token):
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.insert("end", token)
        self.chat_textbox.see("end")
        self.chat_textbox.configure(state="disabled")

    def _finalize_stream_gui(self):
        self.chat_textbox.configure(state="normal")
        self.chat_textbox.insert("end", "\n\n")
        self.chat_textbox.see("end")
        self.chat_textbox.configure(state="disabled")

    def _update_status(self, text):
        self.status_label.configure(text=f"Status: {text}")
