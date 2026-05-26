import sys
import threading
import queue
from datetime import datetime
import logging
import config

try:
    import customtkinter as ctk
except ImportError:
    ctk = None

logger = logging.getLogger("Prim.UI")

# Set theme and appearance
if ctk is not None:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

class PrimDashboard:
    def __init__(self, interrupt_callback=None, close_callback=None):
        self.interrupt_callback = interrupt_callback
        self.close_callback = close_callback
        self.root = None
        
        # State Colors
        self.status_colors = {
            "SLEEPING": "#4A5568",  # Dim slate grey
            "LISTENING": "#38A169", # Emerald green
            "THINKING": "#805AD5",  # Purple
            "SPEAKING": "#DD6B20"   # Warm orange/coral
        }
        
        if ctk is None:
            logger.warning("customtkinter is not installed. Running in headless mode.")
            return

    def start(self):
        """Initializes and runs the CustomTkinter GUI loop."""
        if ctk is None:
            return

        # Initialize main window
        self.root = ctk.CTk()
        self.root.title("Project Prim - Local Voice Assistant")
        self.root.geometry("900x650")
        self.root.minsize(750, 500)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Style layout grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=3)
        self.root.grid_rowconfigure(0, weight=1)
        
        # ----------------- SIDEBAR PANEL (Status) -----------------
        self.sidebar = ctk.CTkFrame(self.root, width=220, corner_radius=15, fg_color="#131317")
        self.sidebar.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)
        
        # Title
        self.title_label = ctk.CTkLabel(
            self.sidebar, 
            text="PRIM", 
            font=ctk.CTkFont(family="Helvetica", size=32, weight="bold"),
            text_color="#00B4D8"
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(30, 10))
        
        self.subtitle_label = ctk.CTkLabel(
            self.sidebar, 
            text="Local Voice Engine v1.0", 
            font=ctk.CTkFont(family="Helvetica", size=11),
            text_color="#718096"
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 30))
        
        # Status Card Box
        self.status_card = ctk.CTkFrame(self.sidebar, corner_radius=10, fg_color="#1E1E24")
        self.status_card.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        self.status_lbl_title = ctk.CTkLabel(
            self.status_card, 
            text="ENGINE STATE", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A0AEC0"
        )
        self.status_lbl_title.pack(padx=10, pady=(10, 2))
        
        self.status_text_var = ctk.StringVar(value="SLEEPING")
        self.status_label = ctk.CTkLabel(
            self.status_card, 
            textvariable=self.status_text_var, 
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.status_colors["SLEEPING"]
        )
        self.status_label.pack(padx=10, pady=(0, 12))
        
        # Interrupt Button
        self.interrupt_btn = ctk.CTkButton(
            self.sidebar,
            text="INTERRUPT",
            command=self._on_interrupt_click,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#E53E3E",
            hover_color="#C53030",
            corner_radius=10,
            height=40
        )
        self.interrupt_btn.grid(row=3, column=0, padx=15, pady=20, sticky="ew")
        
        # Audio input indicator placeholder
        self.vad_label = ctk.CTkLabel(
            self.sidebar,
            text="Speech Prob: 0.00",
            font=ctk.CTkFont(family="Courier", size=12),
            text_color="#718096"
        )
        self.vad_label.grid(row=5, column=0, padx=10, pady=20, sticky="s")
        
        # ----------------- MAIN CONTENT AREA -----------------
        self.main_area = ctk.CTkFrame(self.root, corner_radius=15, fg_color="#0F0F11")
        self.main_area.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(1, weight=3) # Console log
        self.main_area.grid_rowconfigure(3, weight=2) # Conversation block
        
        # Console Log Label
        self.console_label = ctk.CTkLabel(
            self.main_area, 
            text="SYSTEM CONSOLE LOG", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#A0AEC0"
        )
        self.console_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        
        # System Log Box
        self.console_textbox = ctk.CTkTextbox(
            self.main_area, 
            corner_radius=10, 
            fg_color="#1E1E24", 
            text_color="#E2E8F0",
            font=ctk.CTkFont(family="Courier", size=11)
        )
        self.console_textbox.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="nsew")
        self.console_textbox.configure(state="disabled")
        
        # Transcript Label
        self.transcript_label = ctk.CTkLabel(
            self.main_area, 
            text="CONVERSATION DIALOGUE", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#A0AEC0"
        )
        self.transcript_label.grid(row=2, column=0, padx=20, pady=(5, 5), sticky="w")
        
        # Conversation Dialogue Box
        self.transcript_textbox = ctk.CTkTextbox(
            self.main_area, 
            corner_radius=10, 
            fg_color="#1E1E24", 
            text_color="#F7FAFC",
            font=ctk.CTkFont(size=13)
        )
        self.transcript_textbox.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.transcript_textbox.configure(state="disabled")
        
        # Log opening message
        self.add_log("Dashboard UI started. Connecting to background voice services...")
        
        # Run main thread loop
        self.root.mainloop()

    def _on_interrupt_click(self):
        """Dispatches click event to interrupt callback."""
        logger.info("Interrupt button clicked on dashboard GUI.")
        if self.interrupt_callback:
            self.interrupt_callback()

    def _on_closing(self):
        """Cleans up threads when closing the window."""
        logger.info("Closing dashboard...")
        if self.close_callback:
            self.close_callback()
        if self.root:
            self.root.destroy()
            sys.exit(0)

    # ----------------- Thread-Safe UI Update Hooks -----------------
    
    def set_status(self, status: str):
        """Thread-safe update of assistant state."""
        if self.root is None:
            return
        self.root.after(0, self._update_status_gui, status)

    def _update_status_gui(self, status: str):
        if status in self.status_colors:
            self.status_text_var.set(status)
            self.status_label.configure(text_color=self.status_colors[status])
            
            # Pulse the status card background slightly to draw attention
            flash_color = self.status_colors[status]
            # Convert hex to RGB roughly, mix with background
            self.status_card.configure(fg_color="#2D3748" if status != "SLEEPING" else "#1E1E24")

    def set_vad_probability(self, prob: float):
        """Thread-safe update of VAD metric indicator."""
        if self.root is None:
            return
        self.root.after(0, lambda: self.vad_label.configure(text=f"Speech Prob: {prob:.2f}"))

    def add_log(self, message: str):
        """Thread-safe append to system logs console."""
        if self.root is None:
            print(f"[LOG] {message}")
            return
        self.root.after(0, self._append_log_gui, message)

    def _append_log_gui(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console_textbox.configure(state="normal")
        self.console_textbox.insert("end", f"[{timestamp}] {message}\n")
        self.console_textbox.see("end")
        self.console_textbox.configure(state="disabled")

    def add_transcript(self, speaker: str, text: str):
        """Thread-safe append to conversation transcript window."""
        if self.root is None:
            print(f"{speaker}: {text}")
            return
        self.root.after(0, self._append_transcript_gui, speaker, text)

    def _append_transcript_gui(self, speaker: str, text: str):
        self.transcript_textbox.configure(state="normal")
        if speaker.lower() == "user":
            self.transcript_textbox.insert("end", f"User: {text}\n\n", "user_tag")
        else:
            self.transcript_textbox.insert("end", f"Prim: {text}\n\n", "prim_tag")
        self.transcript_textbox.see("end")
        self.transcript_textbox.configure(state="disabled")
