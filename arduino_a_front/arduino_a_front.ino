/*
 * arduino_a_front.ino — Front Wheel Controller (Merged with ROS 2 Driver Protocol)
 * =============================================================================
 * This version is compatible with the diffdrive_arduino ROS 2 driver.
 * It preserves OLED and INA226 functionality.
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
const unsigned long POWER_INTERVAL_MS   = 1000;
const unsigned long DISPLAY_INTERVAL_MS = 200;

unsigned long lastPower   = 0;
unsigned long lastDisplay = 0;

// ── Encoder state ───────────────────────────────────────────────────────────────
volatile long fl_ticks = 0;
volatile long fr_ticks = 0;

// ── Cached power readings ─────────────────────────────────────────────────────
float cachedVoltage_V  = 0.0f;
float cachedCurrent_mA = 0.0f;
float cachedPower_mW   = 0.0f;

// ── Motion state ──────────────────────────────────────────────────────────────
char motionLabel[12] = "STOP";

// ═════════════════════════════════════════════════════════════════════════════
// Encoder ISRs
// ═════════════════════════════════════════════════════════════════════════════
void ISR_fl_enc() {
  if (digitalRead(FL_ENC_B) == HIGH) { fl_ticks++; } else { fl_ticks--; }
}

void ISR_fr_enc() {
  // Mirrored on the right because orientation is backwards
  if (digitalRead(FR_ENC_B) == HIGH) { fr_ticks--; } else { fr_ticks++; }
}

// ═════════════════════════════════════════════════════════════════════════════
// Motor Control (Simplified for ROS 2 Driver)
// ═════════════════════════════════════════════════════════════════════════════
void setMotors(int left_val, int right_val) {
  // Left Motor
  if (left_val > 0) {
    digitalWrite(FL_FWD, HIGH); digitalWrite(FL_BWD, LOW);
  } else if (left_val < 0) {
    digitalWrite(FL_FWD, LOW); digitalWrite(FL_BWD, HIGH);
  } else {
    digitalWrite(FL_FWD, LOW); digitalWrite(FL_BWD, LOW);
  }

  // Right Motor
  if (right_val > 0) {
    digitalWrite(FR_FWD, HIGH); digitalWrite(FR_BWD, LOW);
  } else if (right_val < 0) {
    digitalWrite(FR_FWD, LOW); digitalWrite(FR_BWD, HIGH);
  } else {
    digitalWrite(FR_FWD, LOW); digitalWrite(FR_BWD, LOW);
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
      Serial.print(fl_ticks);
      Serial.print(" ");
      Serial.println(fr_ticks);
    } 
    else if (cmd == 'm') {
      // Expects: " m val1 val2\r"
      int left_val = Serial.parseInt();
      int right_val = Serial.parseInt();
      setMotors(left_val, right_val);
    }
    else if (cmd == 'u') {
      // PID command - ignore for now as we use digital
      while(Serial.available() > 0 && Serial.read() != '\r');
    }
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Setup
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(57600); // MUST be 57600 for diffdrive_arduino driver
  Wire.begin();

  const int motorPins[] = {FR_FWD, FR_BWD, FL_FWD, FL_BWD};
  for (int i = 0; i < 4; i++) {
    pinMode(motorPins[i], OUTPUT);
    digitalWrite(motorPins[i], LOW);
  }

  pinMode(FL_ENC_A, INPUT_PULLUP);
  pinMode(FL_ENC_B, INPUT_PULLUP);
  pinMode(FR_ENC_A, INPUT_PULLUP);
  pinMode(FR_ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FL_ENC_A), ISR_fl_enc, RISING);
  attachInterrupt(digitalPinToInterrupt(FR_ENC_A), ISR_fr_enc, RISING);

  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    display.setTextColor(SSD1306_WHITE);
    showSplash();
  }

  if (ina226.init()) {
    ina226.setResistorRange(SHUNT_RESISTANCE_OHMS, MAX_CURRENT_A);
    ina226.setAverage(INA226_AVERAGE_1);
    ina226.setConversionTime(INA226_CONV_TIME_140);
    ina226.setMeasureMode(INA226_CONTINUOUS);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Loop
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  processDriverCommand();

  unsigned long now = millis();

  if (now - lastPower >= POWER_INTERVAL_MS) {
    lastPower = now;
    cachedVoltage_V  = ina226.getBusVoltage_V();
    cachedCurrent_mA = ina226.getCurrent_mA();
    cachedPower_mW = ina226.getBusPower();
  }

  if (now - lastDisplay >= DISPLAY_INTERVAL_MS) {
    lastDisplay = now;
    updateDisplay();
  }
}

void updateDisplay() {
  display.clearDisplay();
  display.fillRect(0, 0, SCREEN_WIDTH, 11, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(18, 2);
  display.print(F("FRONT CONTROLLER"));
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 13);
  display.print(F("Motion: ")); display.print(motionLabel);
  display.setCursor(0, 25);
  display.print(F("FL: ")); display.print(fl_ticks);
  display.setCursor(66, 25);
  display.print(F("FR: ")); display.print(fr_ticks);
  display.drawFastVLine(64, 24, 10, SSD1306_WHITE);
  display.drawFastHLine(0, 36, SCREEN_WIDTH, SSD1306_WHITE);
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
  display.setCursor(10, 38); display.print(F("ROS 2 Compatible"));
  display.setCursor(10, 52); display.print(F("Initializing..."));
  display.display();
  delay(1500);
}
