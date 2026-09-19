from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():

    return LaunchDescription([
        DeclareLaunchArgument(
            'video_device',
            default_value='/dev/video0',
            description='Video device to use'
        ),
        Node(
            package='usb_cam',
            executable='usb_cam_node_exe',
            namespace='camera',
            output='screen',
            parameters=[{
                'video_device': LaunchConfiguration('video_device'),
                'frame_id': 'camera_link_optical',
                'image_width': 640,
                'image_height': 480
            }]
        )
    ])