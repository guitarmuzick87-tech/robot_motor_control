
import pyttsx3
import pygame
import os

engine = pyttsx3.init()
temp_file = "debug_speech.wav"
engine.save_to_file("Hello world", temp_file)
engine.runAndWait()

print(f"File created: {os.path.exists(temp_file)}")
try:
    pygame.init()
    sound = pygame.mixer.Sound(temp_file)
    print("Pygame loaded it successfully")
except Exception as e:
    print(f"Pygame error: {e}")
