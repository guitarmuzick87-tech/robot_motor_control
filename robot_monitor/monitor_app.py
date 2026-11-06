import pygame
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image, CompressedImage
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import Twist, TwistStamped
from std_srvs.srv import Trigger
from cv_bridge import CvBridge
import cv2
import numpy as np
import threading
import time
from config import *

class RobotMonitorNode(Node):
    def __init__(self):
        super().__init__('robot_monitor_node')
        
        # Publishers
        self.speech_pub = self.create_publisher(String, TOPIC_SPEECH, 10)
        # Changed to TwistStamped to match teleop_twist_keyboard (stamped:=true)
        self.vel_pub = self.create_publisher(TwistStamped, TOPIC_CMD_VEL, 10)
        
        # Subscribers
        self.bridge = CvBridge()
        self.latest_frame = None
        self.latest_map = None
        
        self.create_subscription(CompressedImage, TOPIC_CAMERA, self.camera_callback, 10)
        self.create_subscription(OccupancyGrid, TOPIC_MAP, self.map_callback, 10)
        
    def camera_callback(self, msg):
        try:
            # Convert ROS CompressedImage to OpenCV
            cv_img = self.bridge.compressed_imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.latest_frame = cv_img
        except Exception as e:
            self.get_logger().error(f"Camera callback error: {e}")

    def map_callback(self, msg):
        self.latest_map = msg

    def send_speech(self, text):
        msg = String()
        msg.data = text
        self.speech_pub.publish(msg)
        self.get_logger().info(f"Published to {TOPIC_SPEECH}: {text}")

    def send_velocity(self, linear_x=0.0, angular_z=0.0):
        msg = TwistStamped()
        # Add timestamp to the header
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        
        msg.twist.linear.x = linear_x
        msg.twist.angular.z = angular_z
        self.vel_pub.publish(msg)

    def call_service(self, service_name, srv_type='std_srvs/srv/Empty', data=None):
        """General purpose service caller for Empty or SetBool services."""
        from std_srvs.srv import Empty, SetBool
        
        # Map string type to actual ROS 2 service class
        type_map = {
            'std_srvs/srv/Empty': Empty,
            'std_srvs/srv/SetBool': SetBool
        }
        SrvClass = type_map.get(srv_type, Empty)
        
        self.get_logger().info(f"Calling service: {service_name} ({srv_type}) with data: {data}")
        
        client = self.create_client(SrvClass, service_name)
        
        if not client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error(f"Service {service_name} not available")
            return
        
        req = SrvClass.Request()
        if srv_type == 'std_srvs/srv/SetBool':
            req.data = data
            
        future = client.call_async(req)
        
        def callback(f):
            try:
                response = f.result()
                self.get_logger().info(f"Service {service_name} call completed.")
            except Exception as e:
                self.get_logger().error(f"Service call failed: {e}")
            finally:
                self.destroy_client(client)
        
        future.add_done_callback(callback)

class MonitorGUI:
    def __init__(self, ros_node):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Robot Monitor Dashboard")
        self.clock = pygame.time.Clock()
        self.node = ros_node
        self.font = pygame.font.SysFont('monospace', 20)
        self.title_font = pygame.font.SysFont('monospace', 24, bold=True)
        
        self.input_text = ""
        self.running = True
        
        # Motor Control State
        self.motor_active = False
        self.current_vel = (0.0, 0.0) # (linear_x, angular_z)
        
        # Button definitions (x, y, w, h, text, action)
        self.buttons = []
        
        # 1. Speech Send Button - Moved to right of input box
        self.buttons.append({'rect': pygame.Rect(370, 570, 100, 40), 'text': 'SEND', 'action': self.handle_send})
        
        # 2. Control Buttons - Moved to avoid overlapping sound bites
        self.buttons.append({'rect': pygame.Rect(950, 570, 150, 40), 'text': 'LIDAR ON', 'action': lambda: self.node.call_service(SERVICE_LIDAR_ON, 'std_srvs/srv/Empty')})
        self.buttons.append({'rect': pygame.Rect(950, 620, 150, 40), 'text': 'LIDAR OFF', 'action': lambda: self.node.call_service(SERVICE_LIDAR_OFF, 'std_srvs/srv/Empty')})
        self.buttons.append({'rect': pygame.Rect(950, 670, 150, 40), 'text': 'SLAM ON', 'action': lambda: self.node.call_service(SERVICE_SLAM_ON, 'std_srvs/srv/SetBool', True)})
        self.buttons.append({'rect': pygame.Rect(950, 720, 150, 40), 'text': 'SLAM OFF', 'action': lambda: self.node.call_service(SERVICE_SLAM_OFF, 'std_srvs/srv/SetBool', False)})

        # 3. Sound Bite Buttons - Two column layout
        bx_start, by_start = 50, 640
        col_width = 210 
        for i, (label, text) in enumerate(SOUND_BITES.items()):
            col = i % 2
            row = i // 2
            bx = bx_start + (col * col_width)
            by = by_start + (row * 50)
            self.buttons.append({'rect': pygame.Rect(bx, by, 200, 40), 'text': label, 'action': lambda t=text: self.node.send_speech(t)})

        # 4. Motor Control Layout (Arrows) - Repositioned to avoid overlapping with input
        self.motor_buttons = {
            'fwd': {'rect': pygame.Rect(615, 570, 60, 60), 'text': '^', 'vel': (0.2, 0.0)},
            'bwd': {'rect': pygame.Rect(615, 640, 60, 60), 'text': 'v', 'vel': (-0.2, 0.0)},
            'lft': {'rect': pygame.Rect(550, 640, 60, 60), 'text': '<', 'vel': (0.0, 0.5)},
            'rgt': {'rect': pygame.Rect(680, 640, 60, 60), 'text': '>', 'vel': (0.0, -0.5)},
        }

    def handle_send(self):
        if self.input_text:
            self.node.send_speech(self.input_text)
            self.input_text = ""

    def draw_text(self, text, x, y, color=COLOR_TEXT, center=False, font=None):
        f = font if font else self.font
        surf = f.render(text, True, color)
        rect = surf.get_rect(center=(x, y)) if center else surf.get_rect(topleft=(x, y))
        self.screen.blit(surf, rect)

    def draw_map(self):
        map_surf = pygame.Surface((400, 400))
        map_surf.fill((50, 50, 50))
        
        grid = self.node.latest_map
        if grid:
            res = grid.info.resolution
            width = grid.info.width
            height = grid.info.height
            data = np.array(grid.data).reshape((height, width))
            scale_x = 400 / width
            scale_y = 400 / height
            for y in range(height):
                for x in range(width):
                    val = data[y, x]
                    if val == -1: color = (100, 100, 100)
                    elif val > 50: color = (200, 200, 200)
                    else: color = (0, 0, 0)
                    pygame.draw.rect(map_surf, color, (int(x*scale_x), int(y*scale_y), max(1, int(scale_x)), max(1, int(scale_y))))
        self.screen.blit(map_surf, (50, 150))

    def draw_camera(self):
        frame = self.node.latest_frame
        if frame is not None:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = np.rot90(frame)
            frame = np.flipud(frame)
            surf = pygame.surfarray.make_surface(frame)
            surf = pygame.transform.scale(surf, (500, 375))
            self.screen.blit(surf, (550, 150))
        else:
            pygame.draw.rect(self.screen, (20, 20, 20), (550, 150, 500, 375))
            self.draw_text("No Camera Feed", 800, 337, center=True)

    def run(self):
        while self.running:
            self.screen.fill(COLOR_BG)
            
            mouse_pos = pygame.mouse.get_pos()
            mouse_pressed = pygame.mouse.get_pressed()
            
            is_moving = False
            current_vel = (0.0, 0.0)
            for key, btn in self.motor_buttons.items():
                if btn['rect'].collidepoint(mouse_pos) and mouse_pressed[0]:
                    is_moving = True
                    current_vel = btn['vel']
                    break
            
            if is_moving:
                self.node.send_velocity(*current_vel)
            else:
                self.node.send_velocity(0.0, 0.0)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_BACKSPACE:
                        self.input_text = self.input_text[:-1]
                    elif event.key == pygame.K_RETURN:
                        self.handle_send()
                    else:
                        if event.unicode.isprintable():
                            self.input_text += event.unicode
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for btn in self.buttons:
                        if btn['rect'].collidepoint(event.pos):
                            btn['action']()

            self.draw_text("ROBOT MONITOR DASHBOARD", WINDOW_WIDTH//2, 50, center=True, font=self.title_font)
            self.draw_text("LIVE CAMERA", 550, 120, COLOR_ACCENT)
            self.draw_camera()
            self.draw_text("LIVE MAP", 50, 120, COLOR_ACCENT)
            self.draw_map()
            
            # 3. Speech Input - Adjusted Y to 720 to align with SEND button and clear motor controls
            input_rect = pygame.Rect(50, 570, 300, 40)
            pygame.draw.rect(self.screen, COLOR_UI, input_rect, border_radius=5)
            if not self.input_text:
                self.draw_text("Type here...", 70, 580, color=(100, 100, 110))
            else:
                self.draw_text(self.input_text, 70, 580)
            
            # 4. Buttons
            for btn in self.buttons:
                pygame.draw.rect(self.screen, COLOR_UI, btn['rect'], border_radius=5)
                if btn['rect'].collidepoint(mouse_pos):
                    pygame.draw.rect(self.screen, COLOR_ACCENT, btn['rect'], 2, border_radius=5)
                self.draw_text(btn['text'], btn['rect'].centerx, btn['rect'].centery, center=True)

            # 5. Motor Controls
            self.draw_text("MOTOR CONTROL", 550, 540, COLOR_ACCENT)
            for key, btn in self.motor_buttons.items():
                color = COLOR_ACCENT if (btn['rect'].collidepoint(mouse_pos) and mouse_pressed[0]) else COLOR_UI
                pygame.draw.rect(self.screen, color, btn['rect'], border_radius=5)
                self.draw_text(btn['text'], btn['rect'].centerx, btn['rect'].centery, center=True)

            pygame.display.flip()
            self.clock.tick(30)

def main():
    rclpy.init()
    node = RobotMonitorNode()
    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()
    gui = MonitorGUI(node)
    try:
        gui.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
        pygame.quit()

if __name__ == "__main__":
    main()
