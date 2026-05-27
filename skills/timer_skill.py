
import logging
from skills.base_skill import BaseSkill
import threading
import time

class TimerSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "set_timer"

    @property
    def description(self) -> str:
        return "Set a timer for a specified duration. For example, 'Set timer for 5 minutes and 30 seconds'."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "duration_minutes": {
                    "type": "number",
                    "description": "The duration of the timer in minutes"
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "The duration of the timer in seconds (optional)"
                }
            },
            "required": ["duration_minutes"]
        }

    @property
    def filler_keywords(self) -> list:
        return ["timer", "set timer"]

    @property
    def filler_phrases(self) -> list:
        return ["Setting that up.", "Timer started."]

    def execute(self, **kwargs) -> str:
        duration_minutes = kwargs.get("duration_minutes")
        duration_seconds = kwargs.get("duration_seconds")

        try:
            duration_minutes = float(duration_minutes) if duration_minutes is not None else 0.0
            duration_seconds = float(duration_seconds) if duration_seconds is not None else 0.0
        except (ValueError, TypeError):
            return "Invalid duration. Please provide valid numbers of minutes and seconds."

        if duration_minutes == 0.0 and duration_seconds == 0.0:
            return "Please specify a duration greater than zero."

        total_duration = duration_minutes * 60 + duration_seconds

        announcement = f"Timer set for {duration_minutes} minutes and {duration_seconds} seconds."
        self.active_synthesizer.generate_and_play(announcement)
        self.active_dashboard.add_transcript("Prim (Timer)", f"({announcement})")

        def alert():
            finish_time = time.strftime("%H:%M", time.localtime())
            announcement = f"Timer finished! It will be done at {finish_time}."
            if self.active_synthesizer:
                self.active_synthesizer.generate_and_play(announcement)
            if self.active_dashboard:
                self.active_dashboard.add_transcript("Prim (Timer)", f"({announcement})")
                self.active_dashboard.add_log(announcement)

        timer_thread = threading.Timer(total_duration, alert)
        timer_thread.start()

        return "Timer started. You will be notified when it's done."
