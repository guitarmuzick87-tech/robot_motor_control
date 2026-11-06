#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool
import subprocess
import signal
import os

class SlamWrapper(Node):
    def __init__(self):
        super().__init__('slam_wrapper')
        self.srv = self.create_service(SetBool, 'toggle_slam', self.handle_toggle_slam)
        self.slam_process = None
        self.get_logger().info('Slam Wrapper Node started. Service: /toggle_slam')

    def handle_toggle_slam(self, request, response):
        if request.data:  # Start SLAM
            if self.slam_process is None or self.slam_process.poll() is not None:
                self.get_logger().info('Starting SLAM Toolbox...')
                try:
                    # Using subprocess.Popen to start the launch file in the background
                    # We use a shell to ensure environment variables are handled or use full path
                    cmd = ['ros2', 'launch', 'slam_toolbox', 'online_async_launch.py']
                    self.slam_process = subprocess.Popen(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        preexec_fn=os.setsid
                    )
                    response.success = True
                    response.message = 'SLAM started successfully'
                except Exception as e:
                    response.success = False
                    response.message = f'Failed to start SLAM: {str(e)}'
            else:
                response.success = True
                response.message = 'SLAM is already running'
        else:  # Stop SLAM
            if self.slam_process is not None:
                self.get_logger().info('Stopping SLAM Toolbox...')
                try:
                    os.killpg(os.getpgid(self.slam_process.pid), signal.SIGINT)
                    self.slam_process = None
                    response.success = True
                    response.message = 'SLAM stopped successfully'
                except Exception as e:
                    response.success = False
                    response.message = f'Failed to stop SLAM: {str(e)}'
            else:
                response.success = True
                response.message = 'SLAM is not running'
        
        return response

def main(args=None):
    rclpy.init(args=args)
    node = SlamWrapper()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.slam_process is not None:
            os.killpg(os.getpgid(node.slam_process.pid), signal.SIGINT)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
