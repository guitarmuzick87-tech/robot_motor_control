/*
 * arduino_a_front.ino — Front Wheel Controller
 * =============================================
 * Handles:
 *   - Front-Left  (FL) and Front-Right (FR) motor drive via L298N
 *   - INA226 voltage / current / power monitoring → sent to Pi
 *   - Front-Left and Front-Right quadrature encoders → tick counts sent to Pi
 *
 * USB Serial (115200 baud) — talks to Raspberry Pi master:
 *
 *   Pi → Arduino (commands, newline-terminated):
 *     CMD:FWD\n      move front wheels forward
 *     CMD:REV\n      move front wheels reverse
 *     CMD:CW\n       rotate CW  (right side back, left side forward)
 *     CMD:CCW\n      rotate CCW (left side back, right side forward)
 *     CMD:STOP\n     all stop
 *     CMD:SPD:xxx\n  set PWM speed 0-255 (applied to analogWrite pins)
 *
 *   Arduino → Pi (sent every REPORT_INTERVAL_MS):
 *     ENC:L:nnnnn,R:nnnnn\n    front-left and front-right encoder tick counts
 *     PWR:V:nn.n,I:nnnn,W:nnnn\n  voltage(V), current(mA), power(mW)
 *
 * Hardware:
 *   Arduino Uno
 *   L298N #1  — FR and FL motors
 *   INA226    — I2C 0x40
 *   SSD1306   — I2C 0x3C  128×64 OLED
 *   Front encoders — interrupt-capable pins
 *
 * Pin map:
 *   Motor:
 *     FR_FWD = 12, FR_BWD = 11   (Front-Right)
 *     FL_FWD = 10, FL_BWD =  9   (Front-Left)
 *   Encoder (quadrature — phase A on interrupt pins):
 *     FL encoder A = pin 2 (INT0), FL encoder B = pin 4
 *     FR encoder A = pin 3 (INT1), FR encoder B = pin 5
 *   I2C: SDA = A4, SCL = A5  (standard Uno)
 *
 * Note: L298N enable pins should be tied HIGH (or to PWM pins if speed control
 * is needed). If you want PWM speed control, move FWD/BWD to enable pins and
 * use analogWrite on EN pins instead of digitalWrite on direction pins.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <INA226_WE.h>

// ── Motor pins ────────────────────────────────────────────────────────────────
#define FR_FWD 12
#define FR_BWD 11
#define FL_FWD 10
#define FL_BWD  9

// ── Encoder pins ──────────────────────────────────────────────────────────────
// Phase A must be on hardware interrupt pins (2 and 3 on Uno)
#define FL_ENC_A 2    // INT0
#define FL_ENC_B 4
#define FR_ENC_A 3    // INT1
#define FR_ENC_B 5

// ── Display ───────────────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_RESET     -1
#define OLED_I2C_ADDR 0x3C
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ── INA226 ────────────────────────────────────────────────────────────────────
#define INA226_I2C_ADDR       0x40
#define SHUNT_RESISTANCE_OHMS 0.1f
#define MAX_CURRENT_A         1.0f
INA226_WE ina226(INA226_I2C_ADDR);

// ── Timing ────────────────────────────────────────────────────────────────────
const unsigned long REPORT_INTERVAL_MS  = 50;    // encoder report to Pi
const unsigned long POWER_INTERVAL_MS   = 1000;  // INA226 read
const unsigned long DISPLAY_INTERVAL_MS = 200;   // OLED refresh

unsigned long lastReport  = 0;
unsigned long lastPower   = 0;
unsigned long lastDisplay = 0;

// ── Encoder state (volatile — modified by ISRs) ───────────────────────────────
volatile long fl_ticks = 0;   // Front-Left
volatile long fr_ticks = 0;   // Front-Right

// ── Cached power readings ─────────────────────────────────────────────────────
float cachedVoltage_V  = 0.0f;
float cachedCurrent_mA = 0.0f;
float cachedPower_mW   = 0.0f;

// ── Motion state ──────────────────────────────────────────────────────────────
char motionLabel[12] = "STOP";
int  currentSpeed    = 255;   // PWM 0-255; 255 = full on (digital)

// ── Serial command buffer ─────────────────────────────────────────────────────
char   cmdBuf[32];
uint8_t cmdLen = 0;

// ═════════════════════════════════════════════════════════════════════════════
// Encoder ISRs
// ═════════════════════════════════════════════════════════════════════════════

void ISR_fl_enc() {
  // Read phase B to determine direction
  if (digitalRead(FL_ENC_B) == HIGH) {
    fl_ticks++;
  } else {
    fl_ticks--;
  }
}

void ISR_fr_enc() {
  if (digitalRead(FR_ENC_B) == HIGH) {
    fr_ticks++;
  } else {
    fr_ticks--;
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Motor helpers
// ═════════════════════════════════════════════════════════════════════════════

void allStop() {
  digitalWrite(FR_FWD, LOW); digitalWrite(FR_BWD, LOW);
  digitalWrite(FL_FWD, LOW); digitalWrite(FL_BWD, LOW);
  strcpy(motionLabel, "STOP");
}

void moveForward() {
  digitalWrite(FR_FWD, HIGH); digitalWrite(FR_BWD, LOW);
  digitalWrite(FL_FWD, HIGH); digitalWrite(FL_BWD, LOW);
  strcpy(motionLabel, "FORWARD");
}

void moveReverse() {
  digitalWrite(FR_FWD, LOW); digitalWrite(FR_BWD, HIGH);
  digitalWrite(FL_FWD, LOW); digitalWrite(FL_BWD, HIGH);
  strcpy(motionLabel, "REVERSE");
}

// CW: left side forward, right side backward
void rotateCW() {
  digitalWrite(FL_FWD, HIGH); digitalWrite(FL_BWD, LOW);
  digitalWrite(FR_FWD, LOW);  digitalWrite(FR_BWD, HIGH);
  strcpy(motionLabel, "ROT CW");
}

// CCW: right side forward, left side backward
void rotateCCW() {
  digitalWrite(FR_FWD, HIGH); digitalWrite(FR_BWD, LOW);
  digitalWrite(FL_FWD, LOW);  digitalWrite(FL_BWD, HIGH);
  strcpy(motionLabel, "ROT CCW");
}

// ═════════════════════════════════════════════════════════════════════════════
// Command parser
// ═════════════════════════════════════════════════════════════════════════════

void processCommand(const char* cmd) {
  if (strcmp(cmd, "CMD:FWD")  == 0) { moveForward(); }
  else if (strcmp(cmd, "CMD:REV")  == 0) { moveReverse(); }
  else if (strcmp(cmd, "CMD:CW")   == 0) { rotateCW();    }
  else if (strcmp(cmd, "CMD:CCW")  == 0) { rotateCCW();   }
  else if (strcmp(cmd, "CMD:STOP") == 0) { allStop();      }
  else if (strncmp(cmd, "CMD:SPD:", 8) == 0) {
    currentSpeed = constrain(atoi(cmd + 8), 0, 255);
    // Speed will take effect on next motor command
    // (Requires EN pins on L298N connected to PWM-capable pins)
  }
  // Unknown commands are silently ignored
}

// ═════════════════════════════════════════════════════════════════════════════
// Setup
// ═════════════════════════════════════════════════════════════════════════════

void setup() {
  Serial.begin(115200);
  Wire.begin();

  // Motor pins
  const int motorPins[] = {FR_FWD, FR_BWD, FL_FWD, FL_BWD};
  for (int i = 0; i < 4; i++) {
    pinMode(motorPins[i], OUTPUT);
    digitalWrite(motorPins[i], LOW);
  }

  // Encoder pins
  pinMode(FL_ENC_A, INPUT_PULLUP);
  pinMode(FL_ENC_B, INPUT_PULLUP);
  pinMode(FR_ENC_A, INPUT_PULLUP);
  pinMode(FR_ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FL_ENC_A), ISR_fl_enc, RISING);
  attachInterrupt(digitalPinToInterrupt(FR_ENC_A), ISR_fr_enc, RISING);

  // OLED
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    display.setTextColor(SSD1306_WHITE);
    showSplash();
  }

  // INA226
  if (ina226.init()) {
    ina226.setResistorRange(SHUNT_RESISTANCE_OHMS, MAX_CURRENT_A);
    ina226.setAverage(INA226_AVERAGE_1);
    ina226.setConversionTime(INA226_CONV_TIME_140);
    ina226.setMeasureMode(INA226_CONTINUOUS);
  }

  Serial.println(F("ARDUINO_A:READY"));
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
    // Atomically snapshot encoder counts
    noInterrupts();
    long fl = fl_ticks;
    long fr = fr_ticks;
    interrupts();
    Serial.print(F("ENC:L:"));
    Serial.print(fl);
    Serial.print(F(",R:"));
    Serial.println(fr);
  }

  // ── 3. Read and report power ───────────────────────────────────────────────
  if (now - lastPower >= POWER_INTERVAL_MS) {
    lastPower = now;
    cachedVoltage_V  = ina226.getBusVoltage_V();
    cachedCurrent_mA = ina226.getCurrent_mA();
    cachedPower_mW   = ina226.getBusPower();
    Serial.print(F("PWR:V:"));
    Serial.print(cachedVoltage_V, 1);
    Serial.print(F(",I:"));
    Serial.print(cachedCurrent_mA, 0);
    Serial.print(F(",W:"));
    Serial.println(cachedPower_mW, 0);
  }

  // ── 4. OLED ───────────────────────────────────────────────────────────────
  if (now - lastDisplay >= DISPLAY_INTERVAL_MS) {
    lastDisplay = now;
    updateDisplay();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// OLED
// ═════════════════════════════════════════════════════════════════════════════

void updateDisplay() {
  display.clearDisplay();

  // Title bar
  display.fillRect(0, 0, SCREEN_WIDTH, 11, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(18, 2);
  display.print(F("FRONT CONTROLLER"));
  display.setTextColor(SSD1306_WHITE);

  // Motion
  display.setCursor(0, 13);
  display.print(F("Motion: ")); display.print(motionLabel);

  // Encoder counts
  display.setCursor(0, 25);
  display.print(F("FL: ")); display.print(fl_ticks);
  display.setCursor(66, 25);
  display.print(F("FR: ")); display.print(fr_ticks);
  display.drawFastVLine(64, 24, 10, SSD1306_WHITE);

  display.drawFastHLine(0, 36, SCREEN_WIDTH, SSD1306_WHITE);

  // Power
  display.setCursor(0, 40);
  display.print(cachedVoltage_V, 1); display.print(F("V"));
  display.setCursor(0, 51);
  display.print(cachedCurrent_mA, 0); display.print(F("mA  "));
  display.print(cachedPower_mW, 0);   display.print(F("mW"));

  display.display();
}

void showSplash() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(10, 10); display.print(F("Arduino A"));
  display.setCursor(10, 24); display.print(F("Front Controller"));
  display.setCursor(10, 38); display.print(F("INA226 + Encoders"));
  display.setCursor(10, 52); display.print(F("Initializing..."));
  display.display();
  delay(1500);
}
