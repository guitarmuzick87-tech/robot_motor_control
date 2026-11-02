import pygame
import sys
import threading
import random
import time
import numpy as np
import os
import subprocess
from config import *
from pydub import AudioSegment

class SpeechManager:
    def __init__(self, face):
        self.face = face
        self.is_talking = False
        self.current_word = ""
        self.full_text = ""
        self._lock = threading.Lock()
        
        # Platform detection
        self.platform = sys.platform
        if self.platform == "darwin": # macOS
            self.temp_file = "speech_temp.aiff"
            self.processed_file = "speech_processed.aiff"
            self.save_cmd = ['say', '-o']
            self.play_cmd = ['/usr/bin/afplay']
        elif self.platform == "linux": # Ubuntu/Raspberry Pi
            self.temp_file = "speech_temp.wav"
            self.processed_file = "speech_processed.wav"
            self.save_cmd = ['espeak', '-w']
            self.play_cmd = ['aplay']
        else:
            self.temp_file = "speech_temp.wav"
            self.processed_file = "speech_processed.wav"
            self.save_cmd = None
            self.play_cmd = None
            print(f"[Speech] Warning: Unsupported platform {self.platform}. Speech may not work.")

        self.start_time = 0
        self.duration = 0
        self.amplitude_map = [] # List of (time, volume) tuples

    def _analyze_audio(self, file_path):
        """Analyze the generated audio file to create a volume map for the mouth."""
        try:
            audio = AudioSegment.from_file(file_path)
            self.duration = audio.duration_seconds
            
            sample_rate_ms = 50 
            amplitudes = []
            for i in range(0, int(audio.duration_seconds * 1000), sample_rate_ms):
                chunk = audio[i : i + sample_rate_ms]
                vol = chunk.dBFS if chunk.dBFS != float('-inf') else -100
                amplitudes.append(vol)
            
            self.amplitude_map = amplitudes
            print(f"[Speech] Audio analyzed: {self.duration:.2f}s, {len(amplitudes)} samples")
        except Exception as e:
            print(f"[Speech] Analysis error: {e}")
            self.duration = len(self.full_text.split()) / 2.5
            self.amplitude_map = []

    def _apply_voice_profile(self, input_file, output_file):
        """Apply FFmpeg filters based on the selected voice profile."""
        profile = VOICE_PROFILES.get(CURRENT_VOICE_PROFILE)
        if not profile:
            # Just copy the file if no profile is set
            subprocess.run(['cp', input_file, output_file], check=True)
            return True
        
        try:
            # Use FFmpeg to apply the filter chain
            # We add a volume boost at the start to ensure the signal is strong enough for the filters
            cmd = ['ffmpeg', '-y', '-i', input_file, '-af', f"volume=2.0,{profile}", output_file]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[Speech] Profile error: {e}")
            # Fallback to original
            subprocess.run(['cp', input_file, output_file], check=True)
            return False

    def _speak_internal(self, text):
        if not self.save_cmd or not self.play_cmd:
            print("[Speech] Error: Speech commands not configured for this platform.")
            return

        try:
            with self._lock:
                # 1. Save TTS to temporary file
                try:
                    # Build command: [cmd, arg, filename]
                    # Add voice flag if VOICE_NAME is configured
                    cmd = self.save_cmd + [self.temp_file]
                    if VOICE_NAME:
                        cmd = cmd + ['-v', VOICE_NAME]
                    cmd = cmd + [text]
                    
                    subprocess.run(cmd, check=True)
                    time.sleep(0.2) 
                except Exception as tts_e:
                    print(f"[Speech] Generation error: {tts_e}")
                    return

                # 2. Apply Voice Profile (Grievous, etc.)
                self._apply_voice_profile(self.temp_file, self.processed_file)

                # 3. Analyze the PROCESSED audio for mouth sync
                self.full_text = text
                self._analyze_audio(self.processed_file)

                # 4. Playback
                try:
                    if not os.path.exists(self.processed_file):
                        print(f"[Speech] Error: File {self.processed_file} not found!")
                        return

                    abs_load_file = os.path.abspath(self.processed_file)
                    
                    self.is_talking = True
                    self.start_time = time.time()
                    
                    process = subprocess.Popen(
                        self.play_cmd + [abs_load_file], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL
                    )
                    
                    while process.poll() is None:
                        time.sleep(0.1)
                        
                except Exception as e:
                    print(f"[Speech] Playback error: {e}")
        except Exception as e:
            print(f"[Speech] Unexpected system error: {e}")
        finally:
            self.is_talking = False
            self.current_word = ""

    def say(self, text):
        if self.is_talking:
            return
        threading.Thread(target=self._speak_internal, args=(text,), daemon=True).start()

    def update(self):
        if not self.is_talking:
            self.face.set_mouth(MOUTH_CLOSED)
            return

        elapsed = time.time() - self.start_time
        if elapsed > self.duration:
            self.is_talking = False
            self.face.set_mouth(MOUTH_CLOSED)
            return

        if self.amplitude_map:
            idx = int((elapsed * 1000) / 50)
            if idx < len(self.amplitude_map):
                vol = self.amplitude_map[idx]
                if vol > -20:
                    self.face.set_mouth(MOUTH_OPEN)
                elif vol > -40:
                    self.face.set_mouth(MOUTH_MID)
                else:
                    self.face.set_mouth(MOUTH_CLOSED)
            else:
                self.face.set_mouth(MOUTH_CLOSED)
        else:
            import math
            cycle = math.sin(elapsed * (2 * math.pi / 0.15))
            if cycle > 0.5:
                self.face.set_mouth(MOUTH_OPEN)
            elif cycle > -0.5:
                self.face.set_mouth(MOUTH_MID)
            else:
                self.face.set_mouth(MOUTH_CLOSED)

        words = self.full_text.split()
        if words:
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
        self.eye_offset = 0

    def set_mouth(self, state):
        self.mouth_state = state

    def update(self, is_speaking=False):
        self.blink_timer += 1
        if self.blink_timer > 200:
            self.eye_blink = True
            if self.blink_timer > 210:
                self.eye_blink = False
                self.blink_timer = 0
        
        if is_speaking:
            self.eye_offset = 0
        else:
            if random.random() < EYE_IDLE_CHANCE:
                self.eye_offset = random.choice([-1, 0, 1])

    def draw(self, screen):
        w, h = screen.get_size()
        cx, cy = w // 2, h // 2
        scale = min(w, h) // 10 
        offset_px = self.eye_offset * scale * EYE_LOOK_DISTANCE
        eye_w = scale * 2
        eye_h = scale * 2 if not self.eye_blink else scale // 4
        eye_y_offset = scale if self.eye_blink else 0
        pygame.draw.rect(screen, COLOR_EYE, (cx - scale * 3 + offset_px, cy - scale * 2 + eye_y_offset, eye_w, eye_h))
        pygame.draw.rect(screen, COLOR_EYE, (cx + scale + offset_px, cy - scale * 2 + eye_y_offset, eye_w, eye_h))
        mouth_x = cx - scale * 2
        mouth_y = cy + scale
        mouth_w = scale * 4
        if self.mouth_state == MOUTH_CLOSED:
            mouth_h = scale * MOUTH_CLOSED_HEIGHT
        elif self.mouth_state == MOUTH_MID:
            mouth_h = scale * MOUTH_MID_HEIGHT
        else: # MOUTH_OPEN
            mouth_h = scale * MOUTH_OPEN_HEIGHT
        pygame.draw.rect(screen, COLOR_MOUTH, (mouth_x, mouth_y, mouth_w, mouth_h))

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
        self.face.update(is_speaking=self.speech.is_talking)
        self.speech.update()

    def draw(self):
        self.screen.fill(COLOR_BG)
        self.face.draw(self.screen)
        if self.speech.is_talking:
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
