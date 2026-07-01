"""
Codex Watcher - 主机端监控脚本

功能：检测 Codex 运行状态，通过串口发送指令到 ESP32

用法：
  python codex_monitor.py                          # 自动检测串口
  python codex_monitor.py --port COM3              # 指定串口
  python codex_monitor.py --port COM3 --mode manual # 手动模式测试
"""

import serial
import serial.tools.list_ports
import time
import sys
import argparse


# ======================== 串口连接 ========================

def find_esp32_port():
    """自动查找 ESP32 串口"""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        if "esp32" in desc or "cp210" in desc or "ch340" in desc or "usb-serial" in desc:
            return p.device
    # 如果没找到，返回第一个串口
    if ports:
        return ports[0].device
    return None


def connect_serial(port, baud=115200):
    """连接串口"""
    if not port:
        port = find_esp32_port()
    if not port:
        print("错误：未找到 ESP32 串口，请用 --port 参数指定")
        print("可用串口：")
        for p in serial.tools.list_ports.comports():
            print(f"  {p.device} - {p.description}")
        sys.exit(1)

    print(f"连接串口: {port} @ {baud} baud")
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)  # 等待 ESP32 复位
    # 读取启动信息
    while ser.in_waiting:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"  ESP32: {line}")
    return ser


def send_command(ser, cmd):
    """发送指令到 ESP32 并读取响应"""
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.1)
    response = ""
    while ser.in_waiting:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            response += line + " "
    return response.strip()


# ======================== 状态检测 ========================

# !!! 你需要根据实际日志路径修改这里 !!!
CODEX_LOG_DIR = "E:\\workspace\\codex_logs"  # Codex 日志目录
CODEX_ERROR_KEYWORDS = ["timeout", "error", "connection failed", "rate limit"]
CODEX_PERMISSION_KEYWORDS = ["permission", "approve", "confirm", "allow", "需要权限", "需要确认"]


def detect_codex_state():
    """
    检测 Codex 当前状态，返回状态字符串。

    !!! 重要：这个函数的实现需要根据你的实际环境修改 !!!
    
    以下提供几种检测方案，按你的情况选择：
    """

    # === 方案 A：手动模式（调试用）===
    # 在手动模式下，用户输入状态
    # 在 main() 的 manual 模式中已处理，这里不会被调用

    # === 方案 B：检测 Codex 进程是否在运行 ===
    # import subprocess
    # try:
    #     result = subprocess.run(
    #         ["tasklist", "/FI", "IMAGENAME eq codex.exe"],
    #         capture_output=True, text=True, timeout=5
    #     )
    #     if "codex.exe" in result.stdout:
    #         return "RUNNING"
    # except:
    #     pass

    # === 方案 C：检测日志文件最新内容 ===
    # import os
    # import glob
    # try:
    #     log_files = glob.glob(os.path.join(CODEX_LOG_DIR, "*.log"))
    #     if not log_files:
    #         return "IDLE"
    #     latest = max(log_files, key=os.path.getmtime)
    #     age = time.time() - os.path.getmtime(latest)
    #     with open(latest, "r", encoding="utf-8", errors="ignore") as f:
    #         content = f.read()[-2000:]  # 只读最后 2KB
    #     content_lower = content.lower()
    #     for kw in CODEX_ERROR_KEYWORDS:
    #         if kw in content_lower:
    #             return "ERROR"
    #     for kw in CODEX_PERMISSION_KEYWORDS:
    #         if kw in content_lower:
    #             return "WAITING"
    #     if age < 10:
    #         return "RUNNING"
    #     elif age > 60:
    #         return "DONE"
    # except:
    #     pass

    # 默认返回空闲
    return "IDLE"


# ======================== 手动测试模式 ========================

def manual_mode(ser):
    """手动输入指令测试"""
    print("\n=== 手动测试模式 ===")
    print("输入指令: running / waiting / done / error / idle / status / ping / quit")
    print()
    while True:
        try:
            cmd = input(">>> ").strip().lower()
            if cmd in ("quit", "q", "exit"):
                break
            if not cmd:
                continue
            resp = send_command(ser, cmd.upper())
            print(f"    响应: {resp}")
        except KeyboardInterrupt:
            break
    print("退出手动模式")


# ======================== 主循环 ========================

def monitor_loop(ser):
    """自动监控循环"""
    print("\n=== 自动监控模式 ===")
    print("按 Ctrl+C 停止\n")

    last_state = None
    poll_interval = 2  # 秒

    while True:
        try:
            state = detect_codex_state()

            if state != last_state:
                resp = send_command(ser, state)
                print(f"[{time.strftime('%H:%M:%S')}] 状态变更: {last_state} -> {state}  (响应: {resp})")
                last_state = state

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\n已停止监控")
            send_command(ser, "IDLE")
            break


# ======================== 入口 ========================

def main():
    parser = argparse.ArgumentParser(description="Codex Watcher 主机端监控")
    parser.add_argument("--port", "-p", help="串口号 (如 COM3)")
    parser.add_argument("--mode", "-m", choices=["auto", "manual"], default="auto",
                        help="运行模式: auto=自动监控, manual=手动测试 (默认 auto)")
    args = parser.parse_args()

    ser = connect_serial(args.port)

    if args.mode == "manual":
        manual_mode(ser)
    else:
        monitor_loop(ser)

    ser.close()
    print("串口已关闭")


if __name__ == "__main__":
    main()