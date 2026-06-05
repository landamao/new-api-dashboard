#!/usr/bin/env python3
"""生成测试数据，用于体验 New API Dashboard"""
import sqlite3
import time
import random
import json
import os

try:
    import bcrypt
except ImportError:
    print("请先安装 bcrypt: pip install bcrypt")
    exit(1)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "one-api.db")


def create_test_data():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 删除旧数据库
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # users 表
    c.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role INTEGER DEFAULT 1,
            status INTEGER DEFAULT 1,
            setting TEXT,
            deleted_at INTEGER DEFAULT 0
        )
    """)

    # logs 表
    c.execute("""
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at INTEGER,
            username TEXT,
            token_name TEXT,
            model_name TEXT,
            quota INTEGER,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            use_time REAL,
            channel_id INTEGER,
            channel_name TEXT,
            ip TEXT,
            `group` TEXT,
            type INTEGER DEFAULT 2,
            other TEXT
        )
    """)

    # 创建测试用户
    users = [
        ("admin", bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(), 100),
        ("testuser", bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(), 1),
        ("alice", bcrypt.hashpw(b"alice123", bcrypt.gensalt()).decode(), 1),
        ("bob", bcrypt.hashpw(b"bob123", bcrypt.gensalt()).decode(), 1),
    ]
    for u in users:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", u)

    # 模拟数据
    models = [
        "gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet", "claude-3-haiku",
        "deepseek-chat", "deepseek-reasoner", "gemini-2.0-flash",
        "qwen-max", "gpt-3.5-turbo",
    ]
    channels = [
        (1, "OpenAI官方"), (2, "Anthropic官方"), (3, "DeepSeek"),
        (4, "中转站A"), (5, "中转站B"),
    ]
    usernames = ["admin", "testuser", "alice", "bob"]
    ips = ["192.168.1.100", "10.0.0.55", "172.16.0.88", "203.0.113.42", "198.51.100.7"]

    now = int(time.time())
    logs = []
    for _ in range(500):
        ts = now - random.randint(0, 30 * 86400)
        user = random.choice(usernames)
        model = random.choice(models)
        ch = random.choice(channels)
        prompt = random.randint(100, 8000)
        completion = random.randint(50, 4000)
        cache = random.randint(0, prompt // 3) if random.random() > 0.7 else 0
        quota = int((prompt + completion) * random.uniform(0.5, 5.0))
        use_time = round(random.uniform(0.5, 30.0), 2)
        ip = random.choice(ips)
        other = json.dumps({"cache_tokens": cache}) if cache > 0 else None

        logs.append((
            2, ts, user, f"sk-{user[:4]}...", model, quota,
            prompt, completion, use_time, ch[0], ch[1], ip, "", other,
        ))

    c.executemany("""
        INSERT INTO logs (type, created_at, username, token_name, model_name, quota,
                          prompt_tokens, completion_tokens, use_time, channel_id,
                          channel_name, ip, `group`, other)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, logs)

    conn.commit()
    conn.close()

    print(f"✅ 测试数据已生成: {DB_PATH}")
    print(f"   - 用户: {len(users)} 个 (admin/testuser/alice/bob)")
    print(f"   - 日志: {len(logs)} 条 (过去 30 天)")
    print()
    print("启动命令:")
    print(f"  DASHBOARD_PORT=6660 DASHBOARD_DB_PATH={DB_PATH} python server.py")
    print()
    print("测试账号:")
    print("  管理员: admin / admin123")
    print("  普通用户: testuser / test123")


if __name__ == "__main__":
    create_test_data()
