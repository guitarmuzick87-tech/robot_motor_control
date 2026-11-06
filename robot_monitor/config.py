
# --- Robot Monitor Configuration ---

# ROS 2 Topics
TOPIC_SPEECH = "/robot_face/speak"
TOPIC_CAMERA = "/camera/image_raw/compressed"
TOPIC_MAP = "/map"
TOPIC_CMD_VEL = "/cmd_vel"

# ROS 2 Services (for control)

# ROS 2 Services (for control)
SERVICE_LIDAR_ON = "/start_motor"
SERVICE_LIDAR_OFF = "/stop_motor"
SERVICE_SLAM_ON = "/toggle_slam"
SERVICE_SLAM_OFF = "/toggle_slam"

# Sound Bites (Mapping Button Label -> Text to send to robot_face/speak)
SOUND_BITES = {
    "Greeting": "Hello there! How can I help you?",
    "Success": "Mission accomplished!",
    "Warning": "Careful, something is in the way.",
    "Confused": "I am not sure I understand.",
    "Happy": "That is wonderful news!",
    "Goodbye": "Goodbye! See you next time."
}

# GUI Settings
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
COLOR_BG = (30, 30, 35)
COLOR_UI = (60, 60, 70)
COLOR_TEXT = (220, 220, 220)
COLOR_ACCENT = (255, 50, 100)
