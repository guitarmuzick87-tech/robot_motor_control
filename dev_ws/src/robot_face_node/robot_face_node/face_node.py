import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import threading
import pygame

# We need to import the App logic from the relative project directory
import sys
import os

# Get the directory where face_node.py is located
current_dir = os.path.dirname(os.path.abspath(__file__))
# Move up to the root of the project (robot_motor_control) and into robot_face
# Path: .../dev_ws/src/robot_face_node/robot_face_node/ -> .../robot_motor_control/robot_face
project_root_logic = os.path.abspath(os.path.join(current_dir, "../../../../robot_face"))
sys.path.append(project_root_logic)

from face_logic import RobotFaceApp

class RobotFaceNode(Node):
    def __init__(self):
        super().__init__('robot_face_node')
        
        # Initialize the Pygame App
        self.app = RobotFaceApp()
        
        # Subscriber for speaking
        self.subscription = self.create_subscription(
            String,
            'robot_face/speak',
            self.listener_callback,
            10
        )
        
        self.get_logger().info('Robot Face Node started. Listening on /robot_face/speak')

    def listener_callback(self, msg):
        self.get_logger().info(f'Speaking: {msg.data}')
        self.app.speech.say(msg.data)

    def spin_once(self):
        # Integration loop
        self.app.run_once()
        if not self.app.running:
            # This allows the 'X' button to actually stop the ROS node
            rclpy.shutdown()
        else:
            rclpy.spin_once(self, timeout_sec=0)

def main(args=None):
    rclpy.init(args=args)
    node = RobotFaceNode()
    
    try:
        while rclpy.ok():
            node.spin_once()
    except KeyboardInterrupt:
        pass
    finally:
        node.app.stop()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
