/*
 * Codex Watcher - ESP32 固件
 * 
 * 功能：通过串口接收主机端状态指令，控制 LED 和蜂鸣器
 * 
 * 串口指令协议 (115200 baud):
 *   RUNNING  - codex 执行中，绿灯常亮
 *   WAITING  - codex 等待权限确认，黄灯闪烁 + 蜂鸣器
 *   DONE     - codex 工作结束，红灯常亮 + 警报
 *   ERROR    - 连接异常/超时，全灯闪烁 + 蜂鸣器
 *   STATUS   - 返回当前状态和电位器值
 *   PING     - 心跳检测，返回 PONG
 */

#include <Arduino.h>

// ======================== 引脚配置 ========================
// 如果你的接线和下面不同，只需修改这里的数字
// ESP32 的 GPIO 编号印在开发板上，不是 D0/D1 这种标记
#define PIN_GREEN_LED   2     // 绿灯接的 GPIO
#define PIN_YELLOW_LED  4     // 黄灯接的 GPIO
#define PIN_RED_LED     16    // 红灯接的 GPIO
#define PIN_BUZZER      17    // 有源蜂鸣器接的 GPIO
#define PIN_POTENTIOMETER 34  // 电位器接的 GPIO（仅 ADC1: 32-39）

// ======================== 蜂鸣器配置 ========================
#define BUZZER_CHANNEL   0     // PWM 通道
#define BUZZER_FREQ      2000  // 蜂鸣器频率(Hz)，有源蜂鸣器可忽略此项

// ======================== 闪烁间隔 ========================
#define BLINK_FAST_MS    200   // 快闪间隔(ms)
#define BLINK_SLOW_MS    500   // 慢闪间隔(ms)

// ======================== 状态定义 ========================
enum State {
  STATE_IDLE,     // 空闲，无灯亮
  STATE_RUNNING,  // 执行中，绿灯常亮
  STATE_WAITING,  // 等待确认，黄灯闪烁 + 蜂鸣器
  STATE_DONE,     // 工作结束，红灯常亮 + 警报
  STATE_ERROR     // 连接异常，全灯闪烁 + 蜂鸣器
};

volatile State currentState = STATE_IDLE;
unsigned long lastBlinkTime = 0;
bool blinkOn = false;
String inputBuffer = "";

// ======================== 电位器读取 ========================
// 返回 0~100 的音量百分比
int readVolumePercent() {
  int raw = analogRead(PIN_POTENTIOMETER);  // 0~4095
  return map(raw, 0, 4095, 0, 100);
}

// ======================== LED 控制 ========================
void allLedsOff() {
  digitalWrite(PIN_GREEN_LED, LOW);
  digitalWrite(PIN_YELLOW_LED, LOW);
  digitalWrite(PIN_RED_LED, LOW);
}

void ledGreen(bool on)  { digitalWrite(PIN_GREEN_LED, on ? HIGH : LOW); }
void ledYellow(bool on) { digitalWrite(PIN_YELLOW_LED, on ? HIGH : LOW); }
void ledRed(bool on)    { digitalWrite(PIN_RED_LED, on ? HIGH : LOW); }

// ======================== 蜂鸣器控制 ========================
void buzzerOn() {
  int vol = readVolumePercent();
  int duty = map(vol, 0, 100, 0, 255);
  ledcWrite(PIN_BUZZER, duty);
}

void buzzerOff() {
  ledcWrite(PIN_BUZZER, 0);
}

// ======================== 状态切换 ========================
void setState(State newState) {
  currentState = newState;
  blinkOn = false;
  lastBlinkTime = millis();
  allLedsOff();
  buzzerOff();

  switch (newState) {
    case STATE_IDLE:
      break;
    case STATE_RUNNING:
      ledGreen(true);
      break;
    case STATE_WAITING:
    case STATE_DONE:
    case STATE_ERROR:
      // 初始状态在 loop 里处理闪烁
      break;
  }
}

// ======================== 串口指令解析 ========================
void handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "RUNNING") {
    setState(STATE_RUNNING);
    Serial.println("OK:RUNNING");
  } else if (cmd == "WAITING") {
    setState(STATE_WAITING);
    Serial.println("OK:WAITING");
  } else if (cmd == "DONE") {
    setState(STATE_DONE);
    Serial.println("OK:DONE");
  } else if (cmd == "ERROR") {
    setState(STATE_ERROR);
    Serial.println("OK:ERROR");
  } else if (cmd == "IDLE") {
    setState(STATE_IDLE);
    Serial.println("OK:IDLE");
  } else if (cmd == "STATUS") {
    int vol = readVolumePercent();
    String states[] = {"IDLE", "RUNNING", "WAITING", "DONE", "ERROR"};
    Serial.print("STATE:");
    Serial.print(states[currentState]);
    Serial.print(",VOL:");
    Serial.println(vol);
  } else if (cmd == "PING") {
    Serial.println("PONG");
  } else {
    Serial.print("ERR:UNKNOWN_CMD:");
    Serial.println(cmd);
  }
}

// ======================== Arduino 入口 ========================
void setup() {
  Serial.begin(115200);
  Serial.println("Codex Watcher v1.0 ready");
  Serial.println("Commands: RUNNING|WAITING|DONE|ERROR|IDLE|STATUS|PING");

  // LED 引脚初始化
  pinMode(PIN_GREEN_LED, OUTPUT);
  pinMode(PIN_YELLOW_LED, OUTPUT);
  pinMode(PIN_RED_LED, OUTPUT);
  allLedsOff();

  // 蜂鸣器 PWM 初始化
  ledcAttach(PIN_BUZZER, BUZZER_FREQ, 8);
  buzzerOff();

  // 电位器引脚（ESP32 analogRead 不需要 pinMode）
  // PIN_POTENTIOMETER = 34 是只读 ADC1 引脚

  setState(STATE_IDLE);
}

void loop() {
  unsigned long now = millis();

  // === 闪烁逻辑 ===
  switch (currentState) {
    case STATE_WAITING: {
      // 黄灯闪烁 + 蜂鸣器间歇响
      if (now - lastBlinkTime >= BLINK_FAST_MS) {
        blinkOn = !blinkOn;
        ledYellow(blinkOn);
        if (blinkOn) buzzerOn(); else buzzerOff();
        lastBlinkTime = now;
      }
      break;
    }
    case STATE_DONE: {
      // 红灯常亮 + 蜂鸣器长响
      ledRed(true);
      int vol = readVolumePercent();
      int duty = map(vol, 0, 100, 0, 255);
      ledcWrite(PIN_BUZZER, duty);
      break;
    }
    case STATE_ERROR: {
      // 红黄绿全闪 + 蜂鸣器快响
      if (now - lastBlinkTime >= BLINK_FAST_MS) {
        blinkOn = !blinkOn;
        ledGreen(blinkOn);
        ledYellow(blinkOn);
        ledRed(blinkOn);
        if (blinkOn) buzzerOn(); else buzzerOff();
        lastBlinkTime = now;
      }
      break;
    }
    default:
      break;
  }

  // === 串口读取 ===
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