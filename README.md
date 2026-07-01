# Codex Watcher

ESP32 硬件监控器，实时指示 Codex 工作状态。

## 状态对应灯效

| 状态 | 指令 | 绿灯 | 黄灯 | 红灯 | 蜂鸣器 |
|------|------|------|------|------|--------|
| 空闲 | `IDLE` | OFF | OFF | OFF | OFF |
| 执行中 | `RUNNING` | 常亮 | OFF | OFF | OFF |
| 等待权限 | `WAITING` | OFF | 闪烁 | OFF | 间歇响 |
| 工作结束 | `DONE` | OFF | OFF | 常亮 | 长响 |
| 连接异常 | `ERROR` | 闪烁 | 闪烁 | 闪烁 | 快响 |

## 接线（ESP32）

```
绿灯 LED  -> GPIO 2   + 220Ω电阻 -> GND
黄灯 LED  -> GPIO 4   + 220Ω电阻 -> GND
红灯 LED  -> GPIO 16  + 220Ω电阻 -> GND
蜂鸣器    -> GPIO 17  -> GND
电位器    -> 中间脚 GPIO 34, 两端接 3.3V 和 GND
```

## 需要修改的配置

打开 `firmware/src/main.cpp`，找到顶部的配置区域：

```cpp
#define PIN_GREEN_LED     2      // 绿灯接的 GPIO
#define PIN_YELLOW_LED    4      // 黄灯接的 GPIO
#define PIN_RED_LED       16     // 红灯接的 GPIO
#define PIN_BUZZER        17     // 有源蜂鸣器接的 GPIO
#define PIN_POTENTIOMETER 34     // 电位器接的 GPIO（仅 ADC1: 32-39）
```

**只改引脚编号**，改成你实际接线的 GPIO 号即可。

## 刷固件

1. 安装 [PlatformIO](https://platformio.org/install)
2. `cd firmware && pio run -t upload`
3. 串口监控: `pio device monitor`

## 运行主机端脚本

```bash
pip install pyserial

# 手动测试（推荐先用这个验证接线）
python host/codex_monitor.py --port COM3 --mode manual

# 自动监控
python host/codex_monitor.py --port COM3
```

手动模式下可以输入 `running` / `waiting` / `done` / `error` / `idle` / `status` 来测试各种灯效。

## 串口协议

ESP32 以 115200 baud 接收文本指令（行尾 `\n`），响应格式：

- 成功: `OK:STATE_NAME`
- 心跳: 发送 `PING`，收到 `PONG`
- 状态查询: 发送 `STATUS`，收到 `STATE:RUNNING,VOL:75`
- 未知指令: `ERR:UNKNOWN_CMD:xxx`