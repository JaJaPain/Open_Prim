import logging
import threading
import sys
from skills.base_skill import BaseSkill

logger = logging.getLogger("Prim.Skills.Timer")

class TimerSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "set_timer"

    @property
    def description(self) -> str:
        return "Set a timer for X amount of time (in minutes) and specify an action to perform upon completion."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "time_minutes": {
                    "type": "number",
                    "description": "The duration of the timer in minutes"
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform when the timer ends (e.g., 'turn off light')"
                }
            },
            "required": ["time_minutes", "action"]
        }

    @property
    def filler_keywords(self) -> list:
        return [
            "timer", 
            "alarm", 
            "set a timer", 
            "start a timer", 
            "create a timer"
        ]

    @property
    def filler_phrases(self) -> list:
        return [
            "Setting a timer for you.",
            "Got it, starting the countdown.",
            "One second, setting the timer."
        ]

    def execute(self, **kwargs) -> str:
        time_minutes = kwargs.get('time_minutes', 0)
        action = kwargs.get('action', '')
        
        if time_minutes <= 0:
            return "Error: Please provide a valid duration greater than zero."

        def alert():
            logger.info(f"Timer done! Action triggered: {action}")
            announcement = f"Timer finished! Action: {action}"
            
            # 1. Play winsound on Windows
            if sys.platform == "win32":
                import winsound
                try:
                    winsound.MessageBeep()
                except Exception:
                    pass
            
            # 2. TTS announcement
            if self.active_synthesizer:
                self.active_synthesizer.generate_and_play(announcement)
                
            # 3. Log and display in UI
            if self.active_dashboard:
                self.active_dashboard.add_transcript("Prim (Timer)", f"({announcement})")
                self.active_dashboard.add_log(f"Timer Finished: {action}")

        # Start timer in background (minutes to seconds)
        timer_thread = threading.Timer(time_minutes * 60, alert)
        timer_thread.start()
        
        return "Timer set for {} minutes. Action: {}".format(time_minutes, action)
