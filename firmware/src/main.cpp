#include <Arduino.h>

// ======================== 引脚配置 ========================
#define PIN_GREEN_LED   13
#define PIN_YELLOW_LED  12
#define PIN_RED_LED     14

#define BLINK_FAST_MS    200
#define BLINK_SLOW_MS    500

// ======================== 状态定义 ========================
enum State { STATE_IDLE, STATE_RUNNING, STATE_WAITING, STATE_DONE, STATE_ERROR };

volatile State currentState = STATE_IDLE;
unsigned long lastBlinkTime = 0;
bool blinkOn = false;
String inputBuffer = "";

// ======================== LED 控制 ========================
void allLedsOff() {
  digitalWrite(PIN_GREEN_LED, LOW);
  digitalWrite(PIN_YELLOW_LED, LOW);
  digitalWrite(PIN_RED_LED, LOW);
}
void ledGreen(bool on)  { digitalWrite(PIN_GREEN_LED, on ? HIGH : LOW); }
void ledYellow(bool on) { digitalWrite(PIN_YELLOW_LED, on ? HIGH : LOW); }
void ledRed(bool on)    { digitalWrite(PIN_RED_LED, on ? HIGH : LOW); }

// ======================== 状态切换 ========================
void setState(State newState) {
  currentState = newState;
  blinkOn = false;
  lastBlinkTime = millis();
  allLedsOff();
  if (newState == STATE_RUNNING) ledGreen(true);
}

// ======================== 串口指令解析 ========================
void handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "RUNNING")       { setState(STATE_RUNNING); Serial.println("OK:RUNNING"); }
  else if (cmd == "WAITING")  { setState(STATE_WAITING); Serial.println("OK:WAITING"); }
  else if (cmd == "DONE")     { setState(STATE_DONE);    Serial.println("OK:DONE"); }
  else if (cmd == "ERROR")    { setState(STATE_ERROR);   Serial.println("OK:ERROR"); }
  else if (cmd == "IDLE")     { setState(STATE_IDLE);    Serial.println("OK:IDLE"); }
  else if (cmd == "STATUS") {
    String states[] = {"IDLE", "RUNNING", "WAITING", "DONE", "ERROR"};
    Serial.print("STATE:"); Serial.println(states[currentState]);
  } else if (cmd == "PING") { Serial.println("PONG"); }
  else { Serial.print("ERR:UNKNOWN_CMD:"); Serial.println(cmd); }
}

// ======================== Arduino 入口 ========================
void setup() {
  Serial.begin(115200);
  Serial.println("Codex Watcher v1.0 ready");

  pinMode(PIN_GREEN_LED, OUTPUT);
  pinMode(PIN_YELLOW_LED, OUTPUT);
  pinMode(PIN_RED_LED, OUTPUT);

  allLedsOff();
  setState(STATE_IDLE);
}

void loop() {
  unsigned long now = millis();

  switch (currentState) {
    case STATE_IDLE:
      ledRed(true);
      break;
    case STATE_WAITING:
      if (now - lastBlinkTime >= BLINK_FAST_MS) {
        blinkOn = !blinkOn;
        ledYellow(blinkOn);
        lastBlinkTime = now;
      }
      break;
    case STATE_DONE:
      ledRed(true);
      break;
    case STATE_ERROR:
      if (now - lastBlinkTime >= BLINK_FAST_MS) {
        blinkOn = !blinkOn;
        ledGreen(blinkOn);
        ledYellow(blinkOn);
        ledRed(blinkOn);
        lastBlinkTime = now;
      }
      break;
    default:
      break;
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        handleCommand(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
    }
  }
}