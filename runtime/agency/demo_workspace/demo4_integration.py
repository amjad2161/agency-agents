#!/usr/bin/env python3
"""Auto-generated integration for voice synthesis via coqui-ai/TTS."""

# Install: pip install TTS
from TTS.api import TTS

def synthesize(text: str, output_path: str = "output.wav") -> str:
    model = TTS("tts_models/en/ljspeech/tacotron2-DDC")
    model.tts_to_file(text=text, file_path=output_path)
    return output_path

if __name__ == "__main__":
    synthesize("Hello from JARVIS BRAINIAC.")
