# New API Dashboard

一个清晰美观易读的独立 [New API](https://github.com/Calcium-Ion/new-api) 数据看板，支持用户认证、使用日志、模型统计等功能。

<p align="center">
  <img src="icon.jpg" width="120" alt="logo">
</p>

## ✨ 功能特性

- 📊 总览统计（调用次数、Token 用量、花费）
- 📈 时间趋势图表（按小时/天）
- 🏷️ 按模型统计
- 👤 按用户统计
- 📋 详细使用日志（含 IP 地址显示）
- 🔐 用户认证（复用 New API 用户系统）
- 🎨 美丽舒适的 UI 布局

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/landamao/new-api-dashboard.git
cd new-api-dashboard
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

复制 `.env.example` 为 `.env` 并编辑：

```bash
cp .env.example .env
```

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DASHBOARD_DB_PATH` | `./data/one-api.db` | New API 数据库路径 |
| `DASHBOARD_PORT` | `6650` | 看板服务端口 |
| `DASHBOARD_API_BASE` | `http://localhost:3000` | New API 服务地址 |

### 4. 启动

```bash
python server.py
```

访问 `http://localhost:6650` 即可。

## 🧪 测试

项目提供了测试数据生成脚本，可以快速体验看板功能：

```bash
# 生成测试数据库（含 4 个用户、500 条日志）
python test_data.py

# 用测试数据启动看板（指定端口）
DASHBOARD_PORT=6660 DASHBOARD_DB_PATH=./data/one-api.db python server.py
```

测试账号：

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `admin123` | 管理员（可看所有用户数据） |
| `testuser` | `test123` | 普通用户（只能看自己数据） |
| `alice` | `alice123` | 普通用户 |
| `bob` | `bob123` | 普通用户 |

## ⚙️ systemd 部署

```ini
[Unit]
Description=New API Dashboard
After=network.target

[Service]
WorkingDirectory=/path/to/new-api-dashboard
ExecStart=/usr/bin/python3 server.py
Environment=DASHBOARD_DB_PATH=/path/to/new-api/data/one-api.db
Environment=DASHBOARD_PORT=6650
Environment=DASHBOARD_API_BASE=http://your-api-address:3000
Restart=always

[Install]
WantedBy=multi-user.target
```

## 📍 IP 地址显示

看板会在日志的「用户」列下方显示请求来源 IP。

需要用户在 New API 个人设置 → 其他设置 → 隐私设置中开启「记录 IP」。

管理员可通过数据库批量开启：

```sql
-- 为所有用户开启 IP 记录
UPDATE users SET setting = json_set(
  COALESCE(setting, '{}'),
  '$.record_ip_log', json('true')
) WHERE deleted_at IS NULL;
```

## 📁 项目结构

```
├── server.py          # 后端服务
├── index.html         # 主页面
├── login.html         # 登录页面
├── test_data.py       # 测试数据生成脚本
├── icon.jpg           # 图标
├── .env.example       # 环境变量示例
├── requirements.txt   # Python 依赖
├── .gitignore         # Git 忽略规则
├── LICENSE            # MIT 许可证
└── README.md          # 项目说明
```

## 🛠️ 技术栈

- Python 3 + http.server（零框架依赖）
- SQLite（直接读取 New API 数据库）
- Chart.js（图表渲染）
- bcrypt（密码验证）

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

[MIT License](LICENSE)
