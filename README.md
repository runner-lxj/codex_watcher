# Codex Watcher

ESP32 硬件监控器，实时指示 Codex 工作状态。无需蜂鸣器和电位器，仅用 3 颗 LED 即可掌握状态。

## 状态对应灯效

| 状态 | 指令 | 绿灯 | 黄灯 | 红灯 | 触发场景 |
|------|------|------|------|------|----------|
| 执行中 | RUNNING | 常亮 | OFF | OFF | 用户发送命令后，Codex 正在调用模型/执行工具 |
| 等待授权 | WAITING | OFF | 闪烁(200ms) | OFF | Working 过程中需要用户手动授予文件写入权限 |
| 工作结束 | DONE | OFF | OFF | 常亮 | 本轮交互结果已展示给用户，等待新命令 |
| 连接异常 | ERROR | 闪烁 | 闪烁 | 闪烁 | 调用模型超时/网络错误/API错误/进程崩溃 |

## 接线（ESP32）

`
绿灯 LED  -> GPIO 13  + 220ohm电阻 -> GND
黄灯 LED  -> GPIO 12  + 220ohm电阻 -> GND
红灯 LED  -> GPIO 14  + 220ohm电阻 -> GND
`

## 配置

打开 irmware/src/main.cpp，找到顶部的配置区域：

`cpp
#define PIN_GREEN_LED   13     // 绿灯接的 GPIO
#define PIN_YELLOW_LED  12     // 黄灯接的 GPIO
#define PIN_RED_LED     14     // 红灯接的 GPIO
`

**只改引脚编号**，改成你实际接线的 GPIO 号即可。当前默认值 13/12/14 已匹配实际接线。

## 刷固件

1. 安装 [PlatformIO](https://platformio.org/install)
2. cd firmware && pio run -t upload
3. 串口监控: pio device monitor

## 运行主机端脚本

`ash
pip install pyserial

# 自动监控（推荐）
python host/codex_monitor.py --port COM5

# 手动测试（验证接线）
python host/codex_monitor.py --port COM5 --mode manual
`

### 手动模式

输入 unning / waiting / done / error / idle / status / ping 测试各种灯效。

### 自动模式

脚本自动检测 Codex 状态并控制 LED：
- **绿灯**：用户发命令后10秒内，或模型调用进行中
- **红灯**：响应完成，等待下次交互
- **黄灯**：检测到工具调用含权限请求，暂停5秒后触发，持续闪烁直到用户响应或15秒超时
- **三灯闪**：日志超过15秒无更新（watchdog）

## 串口协议

ESP32 以 115200 baud 接收文本指令（行尾 \n），响应格式：

- 成功: OK:STATE_NAME
- 心跳: 发送 PING，收到 PONG
- 状态查询: 发送 STATUS，收到 STATE:RUNNING
- 未知指令: ERR:UNKNOWN_CMD:xxx

## 状态规则

- DONE 之后不再触发 WAITING：红灯亮起后，黄灯不会闪烁
- WAITING 只在 RUNNING 期间触发：模型调用中检测到权限请求才会亮黄灯

## 已知限制

- **WAITING 检测存在误判**：模型每次生成工具调用都带 sandbox_permissions 字段，无法区分"需要授权"和"不需要授权"。通过5秒暂停阈值 + 30秒冷却期减少影响。详见 docs/状态检测设计.md。
- **进程检测仅支持 Windows**：使用 	asklist 命令，跨平台需替换为 psutil 或平台判断。