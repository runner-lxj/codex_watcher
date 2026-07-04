# -*- coding: utf-8 -*-
"""
Codex Watcher - 主机端监控脚本

状态检测逻辑:
- RUNNING:  调用模型/执行工具中 (绿灯常亮)
- WAITING:  需要用户授权 (黄灯闪烁，持续到用户响应)
- DONE:     交互完成，等待新命令 (红灯常亮)
- ERROR:    超时/网络错误/进程崩溃 (全灯闪烁)

数据源: ~/.codex/logs_2.sqlite (事件日志)
        ~/.codex/state_5.sqlite (会话元数据)

WAITING 检测说明:
  基于 sandbox_permissions 关键词匹配，会存在一定误判（每次含工具调用的响应都可能触发）。
  通过5秒暂停阈值 + 30秒冷却期 + 15秒超时来减少误判影响。
"""

import serial
import serial.tools.list_ports
import time
import sys
import os
import argparse
import sqlite3
import subprocess


CODEX_HOME = os.path.join(os.path.expanduser("~"), ".codex")
CODEX_LOGS_DB = os.path.join(CODEX_HOME, "logs_2.sqlite")
CODEX_STATE_DB = os.path.join(CODEX_HOME, "state_5.sqlite")

POLL_INTERVAL = 0.5
IDLE_TIMEOUT = 300
WATCHDOG_TIMEOUT = 15
STATE_DEBOUNCE = 0.5
TOKEN_CHECK_INTERVAL = 2.5
WAITING_PAUSE_THRESHOLD = 5
WAITING_EXIT_TIMEOUT = 15
WAITING_COOLDOWN = 30


def find_esp32_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        if "cp210" in desc or "ch340" in desc or "usb-serial" in desc or "usb" in desc:
            return p.device
    if ports:
        return ports[0].device
    return None


def connect_serial(port, baud=115200):
    if not port:
        port = find_esp32_port()
    if not port:
        print("错误: 未找到 ESP32 串口")
        sys.exit(1)
    print(f"连接串口: {port} @ {baud} baud")
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)
    while ser.in_waiting:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(f"  ESP32: {line}")
    return ser


def send_command(ser, cmd):
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.1)
    response = ""
    while ser.in_waiting:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            response += line + " "
    return response.strip()


def is_codex_running():
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq codex.exe", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        return "codex.exe" in result.stdout
    except Exception:
        return False


def _query_db_row(db_path, sql, params=(), default=None):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        cur = conn.cursor()
        cur.execute(sql, params)
        result = cur.fetchone()
        conn.close()
        return result if result else default
    except Exception:
        return default


def _query_db_scalar(db_path, sql, params=(), default=None):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        cur = conn.cursor()
        cur.execute(sql, params)
        result = cur.fetchone()
        conn.close()
        return result[0] if result else default
    except Exception:
        return default


def get_log_timestamps(now, window=300):
    cutoff = int(now) - window
    sql = """
    SELECT
        MAX(CASE WHEN feedback_log_body LIKE '%op.dispatch.user_input%' THEN ts END),
        MAX(CASE WHEN feedback_log_body LIKE '%response.created%' THEN ts END),
        MAX(CASE WHEN feedback_log_body LIKE '%response.completed%' THEN ts END),
        MAX(CASE WHEN feedback_log_body LIKE '%response.output_item.done%'
                  AND feedback_log_body LIKE '%"type":"function_call"%'
                  AND feedback_log_body LIKE '%sandbox_permissions%' THEN ts END),
        MAX(ts)
    FROM logs WHERE ts > ?
    """
    result = _query_db_row(CODEX_LOGS_DB, sql, (cutoff,))
    if result:
        return {
            "user_input": result[0] or 0,
            "response_created": result[1] or 0,
            "response_completed": result[2] or 0,
            "permission": result[3] or 0,
            "last_activity": result[4] or 0,
        }
    return dict(user_input=0, response_created=0, response_completed=0,
                permission=0, last_activity=0)


def get_approval_mode():
    sql = ("SELECT approval_mode FROM threads "
           "WHERE archived = 0 ORDER BY updated_at DESC LIMIT 1")
    return _query_db_scalar(CODEX_STATE_DB, sql, default="never") or "never"


def get_token_usage():
    sql = "SELECT MAX(tokens_used) FROM threads WHERE archived = 0"
    return _query_db_scalar(CODEX_STATE_DB, sql, default=0) or 0


class StateMachine:
    def __init__(self):
        self.current = "DONE"
        self.last_state_change = 0
        self.prev_tokens = 0
        self.last_token_check = 0
        self.started_at = time.time()
        self.waiting_since = 0
        self.waiting_cooldown_until = 0

    def update(self):
        now = time.time()
        if now - self.last_state_change < STATE_DEBOUNCE:
            return self.current

        if not is_codex_running():
            return self._go("DONE", now)

        ts = get_log_timestamps(now)

        if self._is_error(now, ts):
            return self._go("ERROR", now)
        if self._is_waiting(now, ts):
            return self._go("WAITING", now)
        if self._is_running(now, ts):
            return self._go("RUNNING", now)
        return self._go("DONE", now)

    def _is_error(self, now, ts):
        inp = ts["user_input"]
        act = ts["last_activity"]
        if not inp or (now - inp) > IDLE_TIMEOUT:
            return False
        if not act:
            return False
        return (now - act) > WATCHDOG_TIMEOUT

    def _is_waiting(self, now, ts):
        # DONE 之后不再触发 WAITING
        if self.current == "DONE":
            return False

        perm = ts["permission"]
        if not perm or perm < self.started_at:
            return False

        approval = get_approval_mode()
        if approval != "on-request":
            return False

        inp = ts["user_input"]
        created = ts["response_created"]
        completed = ts["response_completed"]

        if not inp:
            return False

        # 已在 WAITING: 保持直到用户响应或超时
        if self.current == "WAITING":
            if created > self.waiting_since:
                return False
            if completed > self.waiting_since:
                return False
            if (now - self.waiting_since) > WAITING_EXIT_TIMEOUT:
                return False
            return True

        # 首次进入
        if now < self.waiting_cooldown_until:
            return False
        if created > completed:
            return False
        if (now - completed) < WAITING_PAUSE_THRESHOLD:
            return False
        if perm > completed:
            return False
        if (now - inp) > IDLE_TIMEOUT:
            return False

        self.waiting_since = now
        return True

    def _is_running(self, now, ts):
        inp = ts["user_input"]
        if not inp or (now - inp) > IDLE_TIMEOUT:
            return False

        if ts["response_created"] > ts["response_completed"]:
            return True

        if (now - inp) <= 10:
            return True

        if self._check_token_growth(now):
            return True
        return False

    def _check_token_growth(self, now):
        if now - self.last_token_check < TOKEN_CHECK_INTERVAL:
            return False
        self.last_token_check = now
        cur = get_token_usage()
        grew = cur > self.prev_tokens
        self.prev_tokens = cur
        return grew

    def _go(self, state, now):
        if state != self.current:
            if self.current == "WAITING" and state != "WAITING":
                self.waiting_cooldown_until = now + WAITING_COOLDOWN
            self.current = state
            self.last_state_change = now
        return self.current


def manual_mode(ser):
    print("\n=== 手动测试模式 ===")
    print("输入: running / waiting / done / error / idle / status / ping / quit\n")
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


def monitor_loop(ser):
    print("\n=== 自动监控模式 ===")
    print(f"轮询: {POLL_INTERVAL}s | debounce: {STATE_DEBOUNCE}s | watchdog: {WATCHDOG_TIMEOUT}s | pause: {WAITING_PAUSE_THRESHOLD}s")
    print("按 Ctrl+C 停止\n")

    sm = StateMachine()
    last_state = None

    while True:
        try:
            state = sm.update()
            if state != last_state:
                resp = send_command(ser, state)
                print(f"[{time.strftime('%H:%M:%S')}] {last_state or '(启动)'} -> {state}  (ESP32: {resp})")
                last_state = state
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\n已停止监控")
            send_command(ser, "DONE")
            break


def main():
    parser = argparse.ArgumentParser(description="Codex Watcher")
    parser.add_argument("--port", "-p", help="串口号 (如 COM5)")
    parser.add_argument("--mode", "-m", choices=["auto", "manual"], default="auto")
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
