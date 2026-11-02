import pygame
import sys
import pyttsx3
import threading
import random
import time
import numpy as np
import os
from config import *

class SpeechManager:
    def __init__(self, face):
        self.face = face
        self.engine = pyttsx3.init()
        self.is_talking = False
        self.current_word = ""
        self.full_text = ""
        self._lock = threading.Lock()
        
        self.engine.setProperty('rate', 150) 
        self.engine.setProperty('volume', 1.0)
        
        self.temp_file = "speech_temp.wav"
        self.current_sound = None
        self.sound_array = None
        self.start_time = 0
        self.duration = 0

    def _speak_internal(self, text):
        with self._lock:
            self.full_text = text
            
            # 1. Save TTS to file to analyze it
            self.engine.save_to_file(text, self.temp_file)
            self.engine.runAndWait()
            
            # 2. Load into Pygame
            try:
                self.current_sound = pygame.mixer.Sound(self.temp_file)
                # Get raw samples for volume analysis
                self.sound_array = pygame.sndarray.array(self.current_sound)
                # Calculate duration
                sample_rate = pygame.mixer.get_init()[0]
                self.duration = len(self.sound_array) / sample_rate
                
                # 3. Start playback
                self.current_sound.play()
                self.start_time = time.time()
                self.is_talking = True
                
                # Wait for audio to finish
                while pygame.mixer.get_busy():
                    time.sleep(0.1)
                
            except Exception as e:
                print(f"Audio error: {e}")
            
            self.is_talking = False
            self.current_word = ""

    def say(self, text):
        # Ignore new requests if already talking to prevent queue build-up
        if self.is_talking:
            return
        threading.Thread(target=self._speak_internal, args=(text,), daemon=True).start()

    def update(self):
        if not self.is_talking or self.sound_array is None:
            self.face.set_mouth(MOUTH_CLOSED)
            return

        # Calculate current playback position
        elapsed = time.time() - self.start_time
        if elapsed > self.duration:
            self.is_talking = False
            self.face.set_mouth(MOUTH_CLOSED)
            return

        # 1. MOUTH SYNC: Sample volume at current position
        sample_rate = pygame.mixer.get_init()[0]
        index = int(elapsed * sample_rate)
        
        if index < len(self.sound_array):
            # Handle stereo (2 channels) or mono
            sample = self.sound_array[index]
            volume = np.abs(sample).mean() if isinstance(sample, np.ndarray) else abs(sample)
            
            # Map volume to mouth state
            if volume > 10000: 
                self.face.set_mouth(MOUTH_OPEN)
            elif volume > 2000:
                self.face.set_mouth(MOUTH_MID)
            else:
                self.face.set_mouth(MOUTH_CLOSED)

        # 2. TEXT SYNC: Map elapsed time to words
        words = self.full_text.split()
        if words:
            # Linear mapping of words to time
            word_idx = int((elapsed / self.duration) * len(words))
            if word_idx < len(words):
                self.current_word = words[word_idx]
            else:
                self.current_word = ""

class RobotFace:
    def __init__(self):
        self.mouth_state = MOUTH_CLOSED
        self.eye_blink = False
        self.blink_timer = 0
        self.eye_offset = 0 # 0: center, -1: left, 1: right

    def set_mouth(self, state):
        self.mouth_state = state

    def update(self, is_speaking=False):
        # Blink logic
        self.blink_timer += 1
        if self.blink_timer > 200:
            self.eye_blink = True
            if self.blink_timer > 210:
                self.eye_blink = False
                self.blink_timer = 0
        
        # Eye movement logic
        if is_speaking:
            self.eye_offset = 0 # Always centered when speaking
        else:
            # Randomly change eye position
            if random.random() < EYE_IDLE_CHANCE:
                self.eye_offset = random.choice([-1, 0, 1])

    def draw(self, screen):
        w, h = screen.get_size()
        cx, cy = w // 2, h // 2
        scale = min(w, h) // 10 
        
        # Eye offset calculation
        offset_px = self.eye_offset * scale * EYE_LOOK_DISTANCE
        
        # --- DRAW EYES ---
        eye_w = scale * 2
        eye_h = scale * 2 if not self.eye_blink else scale // 4
        eye_y_offset = scale if self.eye_blink else 0
        
        # Left Eye
        pygame.draw.rect(screen, COLOR_EYE, 
                         (cx - scale * 3 + offset_px, cy - scale * 2 + eye_y_offset, eye_w, eye_h))
        # Right Eye
        pygame.draw.rect(screen, COLOR_EYE, 
                         (cx + scale + offset_px, cy - scale * 2 + eye_y_offset, eye_w, eye_h))

        # --- DRAW MOUTH ---
        mouth_x = cx - scale * 2
        mouth_y = cy + scale
        mouth_w = scale * 4
        
        if self.mouth_state == MOUTH_CLOSED:
            mouth_h = scale // 2
        elif self.mouth_state == MOUTH_MID:
            mouth_h = scale * 2
        else: # MOUTH_OPEN
            mouth_h = scale * 4
            
        pygame.draw.rect(screen, COLOR_MOUTH, 
                         (mouth_x, mouth_y, mouth_w, mouth_h))

class RobotFaceApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        pygame.display.set_caption("Robot Face")
        self.clock = pygame.time.Clock()
        self.face = RobotFace()
        self.speech = SpeechManager(self.face)
        self.running = True

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()

    def update(self):
        # Pass whether we are speaking to the face update logic
        self.face.update(is_speaking=self.speech.is_talking)
        self.speech.update()

    def draw(self):
        self.screen.fill(COLOR_BG)
        self.face.draw(self.screen)
        
        # Draw scrolling text at the bottom
        if self.speech.is_talking:
            # Set up font
            font = pygame.font.SysFont('monospace', 40, bold=True)
            text_surface = font.render(self.speech.current_word, True, COLOR_EYE)
            text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 80))
            self.screen.blit(text_surface, text_rect)
            
        pygame.display.flip()

    def run_once(self):
        self.handle_events()
        self.update()
        self.draw()
        self.clock.tick(60)

    def stop(self):
        pygame.quit()
