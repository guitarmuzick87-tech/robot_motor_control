#!/usr/bin/env python3
"""
pi_master.py — Raspberry Pi 5 Robot Brain
==========================================
Connects to two Arduino Unos over USB serial:
  - Arduino A (/dev/ttyUSB0 or /dev/ttyACM0): front wheels + INA226 voltage + front encoders
  - Arduino B (/dev/ttyUSB1 or /dev/ttyACM1): rear wheels + rear encoders

Serial protocol (both directions, newline-terminated, 115200 baud):
  Pi → Arduino:
    CMD:FWD\n          move forward
    CMD:REV\n          move reverse
    CMD:CW\n           rotate clockwise
    CMD:CCW\n          rotate counter-clockwise
    CMD:STOP\n         all stop
    CMD:SPD:xxx\n      set speed (0-255 PWM) — future use

  Arduino A → Pi:
    ENC:L:nnnnn,R:nnnnn\n   front-left and front-right encoder tick counts
    PWR:V:nn.n,I:nnnn,W:nnnn\n  voltage (V), current (mA), power (mW)

  Arduino B → Pi:
    ENC:L:nnnnn,R:nnnnn\n   rear-left and rear-right encoder tick counts

Usage:
  python3 pi_master.py

ROS2 integration note:
  Replace the stub publish_to_ros2() with actual rclpy publishers.
  The encoder dicts front_enc and rear_enc are updated continuously
  and ready to be published as JointState or custom messages.
"""

import serial
import threading
import time
import sys

# ── Port configuration ────────────────────────────────────────────────────────
# Adjust these to match your system. Run `ls /dev/ttyACM* /dev/ttyUSB*` to find them.
# Tip: use udev rules or symlinks to make ports deterministic by Arduino serial number.
ARDUINO_A_PORT = "/dev/ttyUSB0"   # Front: motors + voltage + front encoders
ARDUINO_B_PORT = "/dev/ttyUSB1"   # Rear:  motors + rear encoders
BAUD_RATE      = 115200
SERIAL_TIMEOUT = 0.1               # seconds

# ── Shared robot state (written by reader threads, read by control thread) ────
state_lock = threading.Lock()

robot_state = {
    # Front encoder ticks (signed, accumulated)
    "front_enc_left":  0,
    "front_enc_right": 0,
    # Rear encoder ticks (signed, accumulated)
    "rear_enc_left":   0,
    "rear_enc_right":  0,
    # Power from INA226 on Arduino A
    "voltage_V":   0.0,
    "current_mA":  0.0,
    "power_mW":    0.0,
    # Last motion command sent
    "motion":      "STOP",
    # Diagnostics
    "a_packets": 0,
    "b_packets": 0,
    "a_errors":  0,
    "b_errors":  0,
}

# ── Serial port handles ───────────────────────────────────────────────────────
ser_a: serial.Serial | None = None
ser_b: serial.Serial | None = None


# ═════════════════════════════════════════════════════════════════════════════
# Serial helpers
# ═════════════════════════════════════════════════════════════════════════════

def open_serial(port: str, baud: int) -> serial.Serial | None:
    """Open a serial port; return None on failure."""
    try:
        s = serial.Serial(port, baud, timeout=SERIAL_TIMEOUT)
        time.sleep(2.0)          # wait for Arduino to reset after DTR toggle
        s.reset_input_buffer()
        print(f"[SERIAL] Opened {port} at {baud} baud")
        return s
    except serial.SerialException as e:
        print(f"[ERROR] Cannot open {port}: {e}")
        return None


def send_command(ser: serial.Serial | None, cmd: str) -> bool:
    """Send a newline-terminated command string. Returns True on success."""
    if ser is None or not ser.is_open:
        return False
    try:
        ser.write((cmd + "\n").encode("ascii"))
        return True
    except serial.SerialException as e:
        print(f"[ERROR] Write failed: {e}")
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Message parsers
# ═════════════════════════════════════════════════════════════════════════════

def parse_enc(line: str, prefix_left: str, prefix_right: str) -> tuple[int, int] | None:
    """
    Parse encoder line: "ENC:L:12345,R:67890"
    Returns (left_ticks, right_ticks) or None on failure.
    """
    try:
        # strip leading/trailing whitespace
        line = line.strip()
        if not line.startswith("ENC:"):
            return None
        body = line[4:]              # "L:12345,R:67890"
        parts = body.split(",")
        if len(parts) != 2:
            return None
        l_val = int(parts[0].split(":")[1])
        r_val = int(parts[1].split(":")[1])
        return l_val, r_val
    except (ValueError, IndexError):
        return None


def parse_power(line: str) -> tuple[float, float, float] | None:
    """
    Parse power line: "PWR:V:12.1,I:350,W:4200"
    Returns (voltage_V, current_mA, power_mW) or None on failure.
    """
    try:
        line = line.strip()
        if not line.startswith("PWR:"):
            return None
        body = line[4:]              # "V:12.1,I:350,W:4200"
        parts = body.split(",")
        if len(parts) != 3:
            return None
        v = float(parts[0].split(":")[1])
        i = float(parts[1].split(":")[1])
        w = float(parts[2].split(":")[1])
        return v, i, w
    except (ValueError, IndexError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Reader threads — one per Arduino
# ═════════════════════════════════════════════════════════════════════════════

def reader_thread_a():
    """Continuously reads from Arduino A (front wheels + voltage)."""
    global ser_a
    while True:
        if ser_a is None or not ser_a.is_open:
            time.sleep(1.0)
            continue
        try:
            raw = ser_a.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()

            if line.startswith("ENC:"):
                result = parse_enc(line, "L", "R")
                if result:
                    with state_lock:
                        robot_state["front_enc_left"]  = result[0]
                        robot_state["front_enc_right"] = result[1]
                        robot_state["a_packets"] += 1
                else:
                    with state_lock:
                        robot_state["a_errors"] += 1

            elif line.startswith("PWR:"):
                result = parse_power(line)
                if result:
                    with state_lock:
                        robot_state["voltage_V"]  = result[0]
                        robot_state["current_mA"] = result[1]
                        robot_state["power_mW"]   = result[2]

        except serial.SerialException as e:
            print(f"[ERROR] Arduino A read error: {e}")
            time.sleep(1.0)
        except Exception as e:
            print(f"[ERROR] Arduino A unexpected: {e}")


def reader_thread_b():
    """Continuously reads from Arduino B (rear wheels)."""
    global ser_b
    while True:
        if ser_b is None or not ser_b.is_open:
            time.sleep(1.0)
            continue
        try:
            raw = ser_b.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()

            if line.startswith("ENC:"):
                result = parse_enc(line, "L", "R")
                if result:
                    with state_lock:
                        robot_state["rear_enc_left"]  = result[0]
                        robot_state["rear_enc_right"] = result[1]
                        robot_state["b_packets"] += 1
                else:
                    with state_lock:
                        robot_state["b_errors"] += 1

        except serial.SerialException as e:
            print(f"[ERROR] Arduino B read error: {e}")
            time.sleep(1.0)
        except Exception as e:
            print(f"[ERROR] Arduino B unexpected: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# Motion commands — called from your joystick reader or ROS2 subscriber
# ═════════════════════════════════════════════════════════════════════════════

def cmd_forward():
    send_command(ser_a, "CMD:FWD")
    send_command(ser_b, "CMD:FWD")
    with state_lock:
        robot_state["motion"] = "FORWARD"

def cmd_reverse():
    send_command(ser_a, "CMD:REV")
    send_command(ser_b, "CMD:REV")
    with state_lock:
        robot_state["motion"] = "REVERSE"

def cmd_rotate_cw():
    send_command(ser_a, "CMD:CW")
    send_command(ser_b, "CMD:CW")
    with state_lock:
        robot_state["motion"] = "ROT CW"

def cmd_rotate_ccw():
    send_command(ser_a, "CMD:CCW")
    send_command(ser_b, "CMD:CCW")
    with state_lock:
        robot_state["motion"] = "ROT CCW"

def cmd_stop():
    send_command(ser_a, "CMD:STOP")
    send_command(ser_b, "CMD:STOP")
    with state_lock:
        robot_state["motion"] = "STOP"

def cmd_set_speed(speed: int):
    """speed: 0-255 PWM value (future use — requires Arduino firmware update)."""
    speed = max(0, min(255, speed))
    send_command(ser_a, f"CMD:SPD:{speed}")
    send_command(ser_b, f"CMD:SPD:{speed}")


# ═════════════════════════════════════════════════════════════════════════════
# ROS2 stub — replace with real rclpy code
# ═════════════════════════════════════════════════════════════════════════════

def publish_to_ros2(state: dict):
    """
    Stub for ROS2 publishing. Replace this function body with:
      joint_state_msg.position = [state["front_enc_left"], ...]
      publisher.publish(joint_state_msg)
    etc.
    """
    pass  # no-op until ROS2 is wired in


# ═════════════════════════════════════════════════════════════════════════════
# Status printer (runs in main thread)
# ═════════════════════════════════════════════════════════════════════════════

def print_status():
    with state_lock:
        s = dict(robot_state)
    print(
        f"\r[{s['motion']:8s}] "
        f"F-L:{s['front_enc_left']:7d} F-R:{s['front_enc_right']:7d} | "
        f"R-L:{s['rear_enc_left']:7d} R-R:{s['rear_enc_right']:7d} | "
        f"{s['voltage_V']:.1f}V {s['current_mA']:.0f}mA | "
        f"pkts A:{s['a_packets']} B:{s['b_packets']} "
        f"err A:{s['a_errors']} B:{s['b_errors']}",
        end="", flush=True
    )


# ═════════════════════════════════════════════════════════════════════════════
# Demo joystick loop (replace with ROS2 subscriber or real joystick input)
# ═════════════════════════════════════════════════════════════════════════════

JOY_CENTER = 512
DEAD_ZONE  = 100

def joystick_to_command(x: int, y: int):
    """Mirror the logic from the original Arduino firmware."""
    x_off = x - JOY_CENTER
    y_off = y - JOY_CENTER
    abs_x = abs(x_off)
    abs_y = abs(y_off)
    if abs_x <= DEAD_ZONE and abs_y <= DEAD_ZONE:
        cmd_stop()
    elif abs_y >= abs_x:
        if y_off > 0:
            cmd_forward()
        else:
            cmd_reverse()
    else:
        if x_off > 0:
            cmd_rotate_cw()
        else:
            cmd_rotate_ccw()


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    global ser_a, ser_b

    print("=== Robot Pi Master ===")
    ser_a = open_serial(ARDUINO_A_PORT, BAUD_RATE)
    ser_b = open_serial(ARDUINO_B_PORT, BAUD_RATE)

    if ser_a is None and ser_b is None:
        print("[FATAL] Both Arduinos failed to connect. Exiting.")
        sys.exit(1)

    # Start reader threads as daemons so they die with the main process
    threading.Thread(target=reader_thread_a, daemon=True).start()
    threading.Thread(target=reader_thread_b, daemon=True).start()

    print("Reader threads started. Sending STOP.")
    cmd_stop()

    # ── Main loop ─────────────────────────────────────────────────────────────
    # In a real robot this is replaced by a ROS2 node spin.
    # Here we just print status every 200 ms and publish encoder data.
    try:
        while True:
            print_status()
            with state_lock:
                snapshot = dict(robot_state)
            publish_to_ros2(snapshot)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down.")
        cmd_stop()
        if ser_a and ser_a.is_open:
            ser_a.close()
        if ser_b and ser_b.is_open:
            ser_b.close()


if __name__ == "__main__":
    main()
