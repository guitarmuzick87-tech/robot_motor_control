import pygame
import sys
import pyttsx3
import threading
import random
import time

# --- Configuration ---
COLOR_BG = (20, 20, 25)
COLOR_FACE = (50, 50, 70)
COLOR_EYE = (255, 50, 100)
COLOR_MOUTH = (255, 50, 100)

MOUTH_CLOSED = 0
MOUTH_MID = 1
MOUTH_OPEN = 2

class SpeechManager:
    def __init__(self, face):
        self.face = face
        self.engine = pyttsx3.init()
        self.is_talking = False
        self._lock = threading.Lock()
        
        # Configure voice
        voices = self.engine.getProperty('voices')
        # Try to find a more "robotic" or clear voice if available
        self.engine.setProperty('rate', 150) 
        self.engine.setProperty('volume', 1.0)

    def _speak_internal(self, text):
        with self._lock:
            self.is_talking = True
            self.engine.say(text)
            self.engine.runAndWait()
            self.is_talking = False

    def say(self, text):
        # Run in a separate thread to avoid blocking Pygame
        threading.Thread(target=self._speak_internal, args=(text,), daemon=True).start()

    def update(self):
        # If talking, randomize mouth movement for a "chattering" effect
        if self.is_talking:
            self.face.set_mouth(random.choice([MOUTH_MID, MOUTH_OPEN]))
        else:
            self.face.set_mouth(MOUTH_CLOSED)

class RobotFace:
    def __init__(self):
        self.mouth_state = MOUTH_CLOSED
        self.eye_blink = False
        self.blink_timer = 0

    def set_mouth(self, state):
        self.mouth_state = state

    def update(self):
        self.blink_timer += 1
        if self.blink_timer > 200:
            self.eye_blink = True
            if self.blink_timer > 210:
                self.eye_blink = False
                self.blink_timer = 0

    def draw(self, screen):
        w, h = screen.get_size()
        cx, cy = w // 2, h // 2
        scale = min(w, h) // 10 
        
        # --- DRAW EYES ---
        eye_w = scale * 2
        eye_h = scale * 2 if not self.eye_blink else scale // 4
        eye_y_offset = scale if self.eye_blink else 0
        
        pygame.draw.rect(screen, COLOR_EYE, 
                         (cx - scale * 3, cy - scale * 2 + eye_y_offset, eye_w, eye_h))
        pygame.draw.rect(screen, COLOR_EYE, 
                         (cx + scale, cy - scale * 2 + eye_y_offset, eye_w, eye_h))

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

def main():
    pygame.init()
    
    screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
    pygame.display.set_caption("Robot Face")
    clock = pygame.time.Clock()
    
    face = RobotFace()
    speech = SpeechManager(face)
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                
                # Test Speech
                if event.key == pygame.K_t:
                    speech.say("Hello! I am your robot assistant. I can see you through the screen.")
                
                # Manual mouth test
                if event.key == pygame.K_1:
                    face.set_mouth(MOUTH_CLOSED)
                if event.key == pygame.K_2:
                    face.set_mouth(MOUTH_MID)
                if event.key == pygame.K_3:
                    face.set_mouth(MOUTH_OPEN)

        # Logic
        face.update()
        speech.update() # Synchronize mouth with speech state
        
        # Render
        screen.fill(COLOR_BG)
        face.draw(screen)
        
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
