#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray
import subprocess

class AudioPublisher(Node):
    def __init__(self):
        super().__init__('audio_publisher')
        self.publisher_ = self.create_publisher(UInt8MultiArray, '/robot/audio', 10)
        
        # Audio settings
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        
        # Use arecord to capture raw PCM audio from the webcam
        # Card 2, Device 0 is the C920 Webcam based on arecord -l
        self.cmd = [
            'arecord', 
            '-D', 'hw:2,0', 
            '-f', 'S16_LE', 
            '-r', str(self.sample_rate), 
            '-c', str(self.channels), 
            '-t', 'raw', 
            '-q'
        ]
        
        self.get_logger().info(f"Starting audio capture with command: {' '.join(self.cmd)}")
        
        try:
            self.process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                bufsize=0
            )
        except Exception as e:
            self.get_logger().error(f"Failed to start arecord: {e}")
            raise e

        # Timer to read from arecord stdout
        self.timer = self.create_timer(0.05, self.publish_audio)

    def publish_audio(self):
        try:
            # Read a chunk of bytes from arecord
            data = self.process.stdout.read(self.chunk_size * 2) # S16_LE is 2 bytes per sample
            if data:
                msg = UInt8MultiArray()
                msg.data = list(data)
                self.publisher_.publish(msg)
        except Exception as e:
            self.get_logger().error(f"Error reading audio data: {e}")

    def destroy_node(self):
        if hasattr(self, 'process'):
            self.process.terminate()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = AudioPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
