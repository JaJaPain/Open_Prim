
import logging
from skills.base_skill import BaseSkill
import webbrowser

class PlayMusicSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "play_music"

    @property
    def description(self) -> str:
        return "Opens the default web browser to play a specific YouTube Music playlist."

    @property
    def parameters(self) -> dict:
        return {}

    @property
    def filler_keywords(self) -> list:
        return ["music", "playlist", "songs", "play music"]

    @property
    def filler_phrases(self) -> list:
        return ["Opening your music playlist now.", "Let's play some music.", "Starting your playlist."]

    def execute(self, **kwargs) -> str:
        try:
            # URL of the specific YouTube Music playlist you want to open
            playlist_url = "https://www.youtube.com/watch?v=yuDoflxzuB8&list=PLJwdq99HSFXjwAdk3l6v_8pPS8uqlWMEP"
            webbrowser.open(playlist_url)
            return f"Opened default web browser to {playlist_url} to play your music."
        except Exception as e:
            return f"Error opening browser: {e}"
