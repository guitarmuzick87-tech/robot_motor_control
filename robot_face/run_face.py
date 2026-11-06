from face_logic import RobotFaceApp
import sys

def main():
    app = RobotFaceApp()
    
    print("Robot Face Standalone Mode")
    print("Press 'F' for fullscreen, 'QUIT' to exit")
    
    while app.running:
        app.run_once()
    
    app.stop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
