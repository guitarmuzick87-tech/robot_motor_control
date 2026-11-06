import pygame
import sys
import threading
import random
import time
import os
import asyncio
import edge_tts
from pydub import AudioSegment
from pydub.playback import play
from config import *

class SpeechManager:
    def __init__(self, face):
        self.face = face
        self.is_talking = False
        self.current_word = ""
        self.full_text = ""
        self._lock = threading.Lock()
        
        self.temp_file = "speech_temp.mp3"
        self.processed_file = "speech_processed.wav"
        self.start_time = 0
        self.duration = 0
        self.amplitude_map = []
        self.word_timings = [] 
        
        self.effect_mode = CURRENT_VOICE_PROFILE if CURRENT_VOICE_PROFILE in ["natural", "raspy", "grievous"] else "natural"

    def _analyze_audio(self, file_path):
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
        except Exception as e:
            print(f"[Speech] Analysis error: {e}")
            self.duration = len(self.full_text.split()) / 2.5
            self.amplitude_map = []

    def _apply_effects(self):
        audio = AudioSegment.from_file(self.temp_file)
        if self.effect_mode == "natural" or self.effect_mode == "normal":
            audio.export(self.processed_file, format="wav")
            return

        if self.effect_mode == "raspy":
            new_sample_rate = int(audio.frame_rate * 0.8)
            audio = audio._spawn(audio.raw_data, overrides={'frame_rate': new_sample_rate})
            audio = audio.set_frame_rate(44100)
        elif self.effect_mode == "grievous":
            low = audio._spawn(audio.raw_data, overrides={'frame_rate': int(audio.frame_rate * 0.7)})
            low = low.set_frame_rate(44100)
            mid = audio._spawn(audio.raw_data, overrides={'frame_rate': int(audio.frame_rate * 0.85)})
            mid = mid.set_frame_rate(44100)
            audio = low.overlay(mid, position=10)

        audio.export(self.processed_file, format="wav")

    async def _generate_speech_with_timings(self, text):
        voice = "en-US-ChristopherNeural"
        communicate = edge_tts.Communicate(text, voice)
        self.word_timings = []
        audio_data = b""
        async for chunk in communicate.stream():
            chunk_type = chunk.get("type")
            if chunk_type == "audio":
                audio_data += chunk.get("data", b"")
            elif chunk_type == "text":
                self.word_timings.append({
                    'start': chunk.get("offset", 0) / 100.0,
                    'text': chunk.get("text", "")
                })
        with open(self.temp_file, "wb") as f:
            f.write(audio_data)

    def _speak_internal(self, text):
        with self._lock:
            try:
                asyncio.run(self._generate_speech_with_timings(text))
                self._apply_effects()
                self.full_text = text
                self._analyze_audio(self.processed_file)
                
                processed_timings = []
                if self.word_timings:
                    last_word_start = self.word_timings[-1]['start']
                    estimated_raw_duration = last_word_start + 0.5 
                    scale_factor = self.duration / max(estimated_raw_duration, 0.1)
                    for i in range(len(self.word_timings)):
                        start = self.word_timings[i]['start'] * scale_factor
                        text = self.word_timings[i]['text']
                        end = self.word_timings[i+1]['start'] * scale_factor if i+1 < len(self.word_timings) else self.duration + 1
                        processed_timings.append((start, end, text))
                self.word_timings = processed_timings

                self.is_talking = True
                self.start_time = time.time()
                audio_segment = AudioSegment.from_file(self.processed_file)
                play(audio_segment)
            except Exception as e:
                print(f"[Speech] Error: {e}")
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

        if self.word_timings:
            for start, end, text in self.word_timings:
                if start <= elapsed <= end:
                    self.current_word = text
                    break
        else:
            words = self.full_text.split()
            if words:
                word_idx = int((elapsed / self.duration) * len(words))
                if word_idx < len(words):
                    self.current_word = words[word_idx]

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
        
        # Draw the "Visor" background
        visor_w = scale * 8
        visor_h = scale * 5
        visor_rect = pygame.Rect(cx - visor_w//2, cy - visor_h//2, visor_w, visor_h)
        pygame.draw.rect(screen, COLOR_BG, visor_rect, border_radius=scale*2)

        offset_px = self.eye_offset * scale * EYE_LOOK_DISTANCE
        
        # Eyes - Rounded when open, rectangles when closed
        eye_spacing = scale * 1.5
        
        if not self.eye_blink:
            # Open: Circles
            eye_radius = scale
            pygame.draw.circle(screen, COLOR_EYE, (cx - eye_spacing + offset_px, cy - scale // 2), eye_radius)
            pygame.draw.circle(screen, COLOR_EYE, (cx + eye_spacing + offset_px, cy - scale // 2), eye_radius)
        else:
            # Closed: Thin rectangles
            eye_w = scale * 2
            eye_h = scale // 6
            # Left Eye Rect
            pygame.draw.rect(screen, COLOR_EYE, 
                             (cx - eye_spacing + offset_px - eye_w // 2, cy - scale // 2 - eye_h // 2, eye_w, eye_h), 
                             border_radius=eye_h // 2)
            # Right Eye Rect
            pygame.draw.rect(screen, COLOR_EYE, 
                             (cx + eye_spacing + offset_px - eye_w // 2, cy - scale // 2 - eye_h // 2, eye_w, eye_h), 
                             border_radius=eye_h // 2)
        
        # Eyebrows - Slightly curved arcs
        brow_w = scale * 0.8
        brow_h = scale * 0.4
        # Left Brow
        pygame.draw.arc(screen, COLOR_BROW, 
                        (cx - eye_spacing - brow_w//2 + offset_px, cy - scale - brow_h, brow_w, brow_h), 
                        0, 3.14159, 4)
        # Right Brow
        pygame.draw.arc(screen, COLOR_BROW, 
                        (cx + eye_spacing - brow_w//2 + offset_px, cy - scale - brow_h, brow_w, brow_h), 
                        0, 3.14159, 4)
        
        # Mouth - Curved Smile
        mouth_w = scale * 2.5
        mouth_h = scale * 1.5
        
        if self.mouth_state == MOUTH_CLOSED:
            depth = MOUTH_CLOSED_HEIGHT
        elif self.mouth_state == MOUTH_MID:
            depth = MOUTH_MID_HEIGHT
        else: # MOUTH_OPEN
            depth = MOUTH_OPEN_HEIGHT
            
        # Draw a smile arc
        # Arc is drawn inside a rect: (x, y, width, height)
        # We want the bottom half of the ellipse to be the smile
        pygame.draw.arc(screen, COLOR_MOUTH, 
                        (cx - mouth_w // 2, cy + 45 + scale // 2 - depth, mouth_w, depth * 2), 
                        3.14159, 6.28318, 6)

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
                # ESC key to exit fullscreen or quit
                if event.key == pygame.K_ESCAPE:
                    pygame.display.toggle_fullscreen()

    def update(self):
        self.face.update(is_speaking=self.speech.is_talking)
        self.speech.update()

    def draw(self):
        self.screen.fill((200, 220, 240))
        self.face.draw(self.screen)
        if self.speech.is_talking:
            font = pygame.font.SysFont('monospace', 40, bold=True)
            text_surface = font.render(self.speech.current_word, True, (50, 50, 80))
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
