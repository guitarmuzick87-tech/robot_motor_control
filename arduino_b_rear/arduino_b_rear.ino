 /*
 * arduino_b_rear.ino — Rear Wheel Controller
 * ===========================================
 * Handles:
 *   - Rear-Left  (RL) and Rear-Right (RR) motor drive via L298N
 *   - Rear-Left and Rear-Right quadrature encoders → tick counts sent to Pi
 *
 * USB Serial (115200 baud) — talks to Raspberry Pi master:
 *
 *   Pi → Arduino (commands, newline-terminated):
 *     CMD:FWD\n      move rear wheels forward
 *     CMD:REV\n      move rear wheels reverse
 *     CMD:CW\n       rotate CW  (right side back, left side forward)
 *     CMD:CCW\n      rotate CCW (left side back, right side forward)
 *     CMD:STOP\n     all stop
 *     CMD:SPD:xxx\n  set PWM speed 0-255 (future use)
 *
 *   Arduino → Pi (sent every REPORT_INTERVAL_MS):
 *     ENC:L:nnnnn,R:nnnnn\n    rear-left and rear-right encoder tick counts
 *
 * Hardware:
 *   Arduino Uno
 *   L298N #2  — RL and RR motors
 *   Rear encoders — interrupt-capable pins
 *
 * Pin map:
 *   Motor:
 *     RR_FWD =  6, RR_BWD =  5   (Rear-Right)
 *     RL_FWD =  8, RL_BWD =  7   (Rear-Left)
 *   Encoder (quadrature — phase A on interrupt pins):
 *     RL encoder A = pin 2 (INT0), RL encoder B = pin 4
 *     RR encoder A = pin 3 (INT1), RR encoder B = pin 5
 *
 * Note: Arduino B has no OLED and no INA226. It is a lean motor + encoder node.
 * The Serial TX LED will blink rapidly as encoder data is streamed — this is normal.
 */

// ── Motor pins ────────────────────────────────────────────────────────────────
#define RR_FWD  12
#define RR_BWD  11
#define RL_FWD  10
#define RL_BWD  9

// ── Encoder pins ──────────────────────────────────────────────────────────────
// Phase A must be on hardware interrupt pins (2 and 3 on Uno)
#define RL_ENC_A 2    // INT0
#define RL_ENC_B 4
#define RR_ENC_A 3    // INT1
#define RR_ENC_B 5

// ── Timing ────────────────────────────────────────────────────────────────────
const unsigned long REPORT_INTERVAL_MS = 50;   // encoder report to Pi (20 Hz)

unsigned long lastReport = 0;

// ── Encoder state (volatile — modified by ISRs) ───────────────────────────────
volatile long rl_ticks = 0;   // Rear-Left
volatile long rr_ticks = 0;   // Rear-Right

// ── Motion state ──────────────────────────────────────────────────────────────
int currentSpeed = 255;   // PWM 0-255; 255 = full on (digital mode)

// ── Serial command buffer ─────────────────────────────────────────────────────
char    cmdBuf[32];
uint8_t cmdLen = 0;

// ═════════════════════════════════════════════════════════════════════════════
// Encoder ISRs
// ═════════════════════════════════════════════════════════════════════════════

void ISR_rl_enc() {
  if (digitalRead(RL_ENC_B) == HIGH) {
    rl_ticks++;
  } else {
    rl_ticks--;
  }
}

void ISR_rr_enc() {
  if (digitalRead(RR_ENC_B) == HIGH) {
    rr_ticks--; //Mirrored because the wheel rotation is technically backwards
  } else {
    rr_ticks++;
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Motor helpers
// ═════════════════════════════════════════════════════════════════════════════

void allStop() {
  digitalWrite(RR_FWD, LOW); digitalWrite(RR_BWD, LOW);
  digitalWrite(RL_FWD, LOW); digitalWrite(RL_BWD, LOW);
}

void moveForward() {
  digitalWrite(RR_FWD, HIGH); digitalWrite(RR_BWD, LOW);
  digitalWrite(RL_FWD, HIGH); digitalWrite(RL_BWD, LOW);
}

void moveReverse() {
  digitalWrite(RR_FWD, LOW); digitalWrite(RR_BWD, HIGH);
  digitalWrite(RL_FWD, LOW); digitalWrite(RL_BWD, HIGH);
}

// CW: left side forward, right side backward
void rotateCW() {
  digitalWrite(RL_FWD, HIGH); digitalWrite(RL_BWD, LOW);
  digitalWrite(RR_FWD, LOW);  digitalWrite(RR_BWD, HIGH);
}

// CCW: right side forward, left side backward
void rotateCCW() {
  digitalWrite(RR_FWD, HIGH); digitalWrite(RR_BWD, LOW);
  digitalWrite(RL_FWD, LOW);  digitalWrite(RL_BWD, HIGH);
}

// ═════════════════════════════════════════════════════════════════════════════
// Command parser
// ═════════════════════════════════════════════════════════════════════════════

void processCommand(const char* cmd) {
  if      (strcmp(cmd, "CMD:FWD")  == 0) { moveForward(); }
  else if (strcmp(cmd, "CMD:REV")  == 0) { moveReverse(); }
  else if (strcmp(cmd, "CMD:CW")   == 0) { rotateCW();    }
  else if (strcmp(cmd, "CMD:CCW")  == 0) { rotateCCW();   }
  else if (strcmp(cmd, "CMD:STOP") == 0) { allStop();      }
  else if (strncmp(cmd, "CMD:SPD:", 8) == 0) {
    currentSpeed = constrain(atoi(cmd + 8), 0, 255);
  }
  // Unknown commands silently ignored
}

// ═════════════════════════════════════════════════════════════════════════════
// Setup
// ═════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);

  // Motor pins
  const int motorPins[] = {RR_FWD, RR_BWD, RL_FWD, RL_BWD};
  for (int i = 0; i < 4; i++) {
    pinMode(motorPins[i], OUTPUT);
    digitalWrite(motorPins[i], LOW);
  }

  // Encoder pins
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
  // ── 1. Read commands from Pi ───────────────────────────────────────────────
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdLen > 0) {
        cmdBuf[cmdLen] = '\0';
        processCommand(cmdBuf);
        cmdLen = 0;
      }
    } else {
      if (cmdLen < 31) {
        cmdBuf[cmdLen++] = c;
      } else {
        cmdLen = 0;  // overflow, reset
      }
    }
  }

  unsigned long now = millis();

  // ── 2. Report encoders to Pi ───────────────────────────────────────────────
  if (now - lastReport >= REPORT_INTERVAL_MS) {
    lastReport = now;
    noInterrupts();
    long rl = rl_ticks;
    long rr = rr_ticks;
    interrupts();
    Serial.print(F("ENC:L:"));
    Serial.print(rl);
    Serial.print(F(",R:"));
    Serial.println(rr);
  }
}
