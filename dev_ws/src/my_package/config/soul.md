This project is the software powering a mobile robot.
The robot main components are:
1. 4 DC motors with encoders attached in a square configuration with front left, front right, back left, and back right wheels.
2. Motors are controlled via two independent L298N motor controllers. One set controls the front wheels, the other the rear wheels.
3. Each L298N motor controller is controlled via an Arduino Nano. Arduino Nanos are connected via USB
4. A USB webcame
5. A mounted RPLidar module
6. A 3S LiPo battery as power supply that is voltage regulated using a 20amp 5v UBEC
7. Software for this robot is relying heavily on ros2

Arduino software is located at $HOME/robot_motor_control/dev_ws/src/diffdrive_arduino
All other related ros configurations are located at $HOME/robot_motor_control/dev_ws/src/my_package