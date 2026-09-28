/*
 * arduino_b_rear.ino — Rear Wheel Controller (Merged with ROS 2 Driver Protocol)
 * =============================================================================
 * This version is compatible with the diffdrive_arduino ROS 2 driver.
 * It preserves the original pinouts and encoder mirroring.
 */

// ── Motor pins ────────────────────────────────────────────────────────────────
#define RR_FWD  12
#define RR_BWD  11
#define RL_FWD  10
#define RL_BWD  9

// ── Encoder pins ──────────────────────────────────────────────────────────────
#define RL_ENC_A 2    // INT0
#define RL_ENC_B 4
#define RR_ENC_A 3    // INT1
#define RR_ENC_B 5

// ── Timing ────────────────────────────────────────────────────────────────────
const unsigned long REPORT_INTERVAL_MS = 50;

unsigned long lastReport = 0;

// ── Encoder state ───────────────────────────────────────────────────────────────
volatile long rl_ticks = 0;
volatile long rr_ticks = 0;

// ── Motion state ──────────────────────────────────────────────────────────────
char motionLabel[12] = "STOP";

// ═════════════════════════════════════════════════════════════════════════════
// Encoder ISRs
// ═════════════════════════════════════════════════════════════════════════════
void ISR_rl_enc() {
  if (digitalRead(RL_ENC_B) == HIGH) { rl_ticks++; } else { rl_ticks--; }
}

void ISR_rr_enc() {
  // Mirrored because the wheel rotation is technically backwards
  if (digitalRead(RR_ENC_B) == HIGH) { rr_ticks--; } else { rr_ticks++; }
}

// ═════════════════════════════════════════════════════════════════════════════
// Motor Control (Simplified for ROS 2 Driver)
// ═════════════════════════════════════════════════════════════════════════════
void setMotors(int left_val, int right_val) {
  // Left Motor
  if (left_val > 0) {
    digitalWrite(RL_FWD, HIGH); digitalWrite(RL_BWD, LOW);
  } else if (left_val < 0) {
    digitalWrite(RL_FWD, LOW); digitalWrite(RL_BWD, HIGH);
  } else {
    digitalWrite(RL_FWD, LOW); digitalWrite(RL_BWD, LOW);
  }

  // Right Motor
  if (right_val > 0) {
    digitalWrite(RR_FWD, HIGH); digitalWrite(RR_BWD, LOW);
  } else if (right_val < 0) {
    digitalWrite(RR_FWD, LOW); digitalWrite(RR_BWD, HIGH);
  } else {
    digitalWrite(RR_FWD, LOW); digitalWrite(RR_BWD, LOW);
  }

  if (left_val == 0 && right_val == 0) strcpy(motionLabel, "STOP");
  else strcpy(motionLabel, "MOVING");
}

// ═════════════════════════════════════════════════════════════════════════════
// Serial Communication (ROS 2 diffdrive_arduino Protocol)
// ═════════════════════════════════════════════════════════════════════════════
void processDriverCommand() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'e') {
      // Response format: "L_ticks R_ticks\n"
      Serial.print(rl_ticks);
      Serial.print(" ");
      Serial.println(rr_ticks);
    } 
    else if (cmd == 'm') {
      // Expects: " m val1 val2\r"
      int left_val = Serial.parseInt();
      int right_val = Serial.parseInt();
      setMotors(left_val, right_val);
    }
    else if (cmd == 'u') {
      // PID command - ignore for now
      while(Serial.available() > 0 && Serial.read() != '\r');
    }
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Setup
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(57600); // MUST be 57600 for diffdrive_arduino driver

  const int motorPins[] = {RR_FWD, RR_BWD, RL_FWD, RL_BWD};
  for (int i = 0; i < 4; i++) {
    pinMode(motorPins[i], OUTPUT);
    digitalWrite(motorPins[i], LOW);
  }

  pinMode(RL_ENC_A, INPUT_PULLUP);
  pinMode(RL_ENC_B, INPUT_PULLUP);
  pinMode(RR_ENC_A, INPUT_PULLUP);
  pinMode(RR_ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(RL_ENC_A), ISR_rl_enc, RISING);
  attachInterrupt(digitalPinToInterrupt(RR_ENC_A), ISR_rr_enc, RISING);

  Serial.println(F("ARDUINO_B:READY"));
}

// ═════════════════════════════════════════════════════════════════════════════
// Loop
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  processDriverCommand();
}
