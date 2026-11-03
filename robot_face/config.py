# --- Robot Face Configuration ---

# Colors (Pixel Art Palette)
COLOR_BG = (20, 20, 25)      # Dark Navy/Black
COLOR_FACE = (50, 50, 70)    # Slate Gray
COLOR_EYE = (255, 50, 100)    # Pink/Red
COLOR_MOUTH = (255, 50, 100) # Pink/Red

# Mouth States
MOUTH_CLOSED = 0
MOUTH_MID = 1
MOUTH_OPEN = 2

# Eye Configuration
EYE_IDLE_CHANCE = 0.01      # Chance to change eye position per frame
EYE_LOOK_DISTANCE = 0.5   # Offset multiplier for looking left/right

# Voice Configuration
# Mapping of platform to voice name. Leave as None to use system default.
# Linux (espeak-ng): 'en-us', 'en-gb', etc.
# macOS (say): 'Samantha', 'Alex', 'Victoria', 'Daniel', 'Fred'
VOICE_NAMES = {
    'linux': 'en-us',
    'darwin': 'Daniel'
}

# Voice Speed (Rate of speaking)
# Linux (espeak-ng): Words per minute (e.g., 175 is default)
# macOS (say): Words per minute (e.g., 175 is default)
VOICE_RATES = {
    'linux': 115,
    'darwin': 115
}

# Voice Profiles
# Options: 'normal', 'grievous'
CURRENT_VOICE_PROFILE = 'normal'

VOICE_PROFILES = {
    'normal': None, # No filter
    'grievous': "asetrate=44100*0.7,atempo=1.2,aecho=0.8:0.02:20:0.3,highpass=f=400,lowpass=f=2500,volume=2.0"
}

# Mouth Size Configuration
MOUTH_CLOSED_HEIGHT = 0.5   # Multiplier for scale (half scale)
MOUTH_MID_HEIGHT = 1.0      # Multiplier for scale (2x scale)
MOUTH_OPEN_HEIGHT = 1.3     # Multiplier for scale (4x scale)
