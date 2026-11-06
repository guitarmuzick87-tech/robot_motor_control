# --- Robot Face Configuration ---

# Colors (Cute Robot Palette)
COLOR_BG = (10, 15, 30)      # Deep Space Navy (Visor background)
COLOR_EYE = (0, 255, 255)    # Glowing Cyan
COLOR_MOUTH = (0, 255, 255)  # Glowing Cyan
COLOR_BROW = (0, 200, 200)   # Slightly darker Cyan for brows

# Mouth States
MOUTH_CLOSED = 0
MOUTH_MID = 1
MOUTH_OPEN = 2

# Eye Configuration
EYE_IDLE_CHANCE = 0.01      # Chance to change eye position per frame
EYE_LOOK_DISTANCE = 0.3     # Offset multiplier for looking left/right

# Voice Settings
VOICE_NAME = "en-US-AndrewNeural"
CURRENT_VOICE_PROFILE = 'raspy'

VOICE_PROFILES = {
    'normal': None, 
    'grievous': "asetrate=44100*0.7,atempo=1.2,aecho=0.8:0.02:20:0.3,highpass=f=400,lowpass=f=2500,volume=2.0"
}

# Mouth Size Configuration (Arc depth/height)
MOUTH_CLOSED_HEIGHT = 5     # Slight curve
MOUTH_MID_HEIGHT = 15       # Noticeable smile
MOUTH_OPEN_HEIGHT = 30      # Deep smile
