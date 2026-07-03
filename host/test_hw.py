import serial
import time
import sys

ports = ["COM3", "COM4"]
esp_port = None

print("=== 扫描 ESP32 串口 ===")
for port in ports:
    try:
        ser = serial.Serial(port, 115200, timeout=2)
        time.sleep(2)
        # 读取启动信息
        startup = b""
        while ser.in_waiting:
            startup += ser.read(ser.in_waiting)
        text = startup.decode("utf-8", errors="ignore").strip()
        if text:
            print(f"  {port}: {text}")

        # 发送 PING
        ser.write(b"PING\n")
        time.sleep(0.5)
        resp = b""
        while ser.in_waiting:
            resp += ser.read(ser.in_waiting)
        resp_text = resp.decode("utf-8", errors="ignore").strip()
        print(f"  {port} PING -> {resp_text}")

        if "PONG" in resp_text or "ready" in text.lower():
            esp_port = port
            print(f"  >> {port} 是 ESP32!")
        ser.close()
    except Exception as e:
        print(f"  {port}: {e}")

if not esp_port:
    print("\n未找到 ESP32，请检查 USB 连接")
    sys.exit(1)

print(f"\n=== 连接 {esp_port}，开始测试 ===\n")
ser = serial.Serial(esp_port, 115200, timeout=2)
time.sleep(1)

def send(cmd):
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.3)
    resp = b""
    while ser.in_waiting:
        resp += ser.read(ser.in_waiting)
    return resp.decode("utf-8", errors="ignore").strip()

tests = [
    ("PING", "心跳检测"),
    ("STATUS", "状态查询"),
    ("RUNNING", "绿灯常亮"),
    ("STATUS", "确认状态"),
    ("WAITING", "黄灯闪烁+蜂鸣器"),
    ("STATUS", "确认状态"),
    ("DONE", "红灯常亮+蜂鸣器"),
    ("STATUS", "确认状态"),
    ("ERROR", "全灯闪烁+蜂鸣器"),
    ("STATUS", "确认状态"),
    ("IDLE", "全部关闭"),
    ("STATUS", "确认状态"),
]

for cmd, desc in tests:
    resp = send(cmd)
    print(f"  {cmd:10s} -> {resp:30s}  ({desc})")
    if cmd in ("WAITING", "ERROR"):
        input("    按回车继续下一个测试...")
    elif cmd == "DONE":
        input("    按回车关闭红灯...")

ser.close()
print("\n=== 测试完成 ===")