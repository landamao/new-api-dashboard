#!/usr/bin/env python3
"""New API Dashboard - A beautiful stats dashboard for New API"""
import http.server
import json
import sqlite3
import os
import urllib.parse
import time
import secrets
import bcrypt
from datetime import timezone, timedelta

DB_PATH = os.environ.get("DASHBOARD_DB_PATH", "./data/one-api.db")
PORT = int(os.environ.get("DASHBOARD_PORT", "6650"))
API_BASE = os.environ.get("DASHBOARD_API_BASE", "http://localhost:3000")
CST = timezone(timedelta(hours=8))

# quota 单位: New API 默认 $1 = 500000
QUOTA_PER_UNIT = 500000

# Session 存储 (内存中，重启失效)
sessions = {}  # token -> {user_id, username, role, created_at}
SESSION_EXPIRE = 86400  # 24小时过期


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def verify_password(username, password):
    """验证用户名密码，返回用户信息或 None"""
    db = get_db()
    user = db.execute(
        "SELECT id, username, role, status, password FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    db.close()
    
    if not user:
        return None
    if user['status'] != 1:  # 被禁用
        return None
    
    try:
        stored_hash = user['password']
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            return {
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role']
            }
    except Exception:
        pass
    return None


def create_session(user_info):
    """创建 session，返回 token"""
    token = secrets.token_hex(32)
    sessions[token] = {
        **user_info,
        'created_at': time.time()
    }
    return token


def check_session(token):
    """检查 session 是否有效"""
    if not token or token not in sessions:
        return None
    session = sessions[token]
    if time.time() - session['created_at'] > SESSION_EXPIRE:
        del sessions[token]
        return None
    return session


def cleanup_sessions():
    """清理过期 session"""
    now = time.time()
    expired = [t for t, s in sessions.items() if now - s['created_at'] > SESSION_EXPIRE]
    for t in expired:
        del sessions[t]


def query_logs(model=None, username=None, start_time=None, end_time=None, 
               page=1, per_page=50, current_user=None):
    """查询日志，支持筛选"""
    db = get_db()
    conditions = ["type = 2"]  # 只看 API 调用日志
    params = []
    
    # 权限控制：非管理员只能看自己的数据
    if current_user and current_user.get('role') != 100:
        conditions.append("username = ?")
        params.append(current_user['username'])
    elif username:
        conditions.append("username = ?")
        params.append(username)
    
    if model:
        conditions.append("model_name = ?")
        params.append(model)
    if username:
        conditions.append("username = ?")
        params.append(username)
    if start_time:
        conditions.append("created_at >= ?")
        params.append(int(start_time))
    if end_time:
        conditions.append("created_at <= ?")
        params.append(int(end_time))
    
    where = " AND ".join(conditions) if conditions else "1=1"
    
    # 获取总数
    count_sql = f"SELECT COUNT(*) as total FROM logs WHERE {where}"
    total = db.execute(count_sql, params).fetchone()['total']
    
    # 获取数据
    offset = (page - 1) * per_page
    data_sql = f"""
        SELECT id, user_id, created_at, username, token_name, model_name,
               quota, prompt_tokens, completion_tokens, use_time, 
               channel_id, channel_name, ip, `group` as user_group, other
        FROM logs 
        WHERE {where}
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    """
    rows = db.execute(data_sql, params + [per_page, offset]).fetchall()
    db.close()
    
    import json as _json
    logs = []
    for r in rows:
        # 从 other 字段提取 cache_tokens
        cache_tokens = 0
        if r['other']:
            try:
                other = _json.loads(r['other'])
                cache_tokens = other.get('cache_tokens', 0) or 0
            except:
                pass
        
        logs.append({
            'id': r['id'],
            'user_id': r['user_id'],
            'created_at': r['created_at'],
            'username': r['username'],
            'token_name': r['token_name'],
            'model_name': r['model_name'],
            'quota': r['quota'],
            'prompt_tokens': r['prompt_tokens'],
            'completion_tokens': r['completion_tokens'],
            'cache_tokens': cache_tokens,
            'use_time': r['use_time'],
            'channel_id': r['channel_id'],
            'channel_name': r['channel_name'],
            'ip': r['ip'],
            'user_group': r['user_group'],
        })
    
    return {'total': total, 'page': page, 'per_page': per_page, 'logs': logs}


def get_stats(model=None, username=None, start_time=None, end_time=None,
              group_by='day', current_user=None):
    """获取统计数据"""
    db = get_db()
    conditions = ["type = 2"]
    params = []
    
    # 权限控制：非管理员只能看自己的数据
    if current_user and current_user.get('role') != 100:
        conditions.append("username = ?")
        params.append(current_user['username'])
    elif username:
        conditions.append("username = ?")
        params.append(username)
    if model:
        conditions.append("model_name = ?")
        params.append(model)
    if username:
        conditions.append("username = ?")
        params.append(username)
    if start_time:
        conditions.append("created_at >= ?")
        params.append(int(start_time))
    if end_time:
        conditions.append("created_at <= ?")
        params.append(int(end_time))
    
    where = " AND ".join(conditions) if conditions else "1=1"
    
    # 总量统计
    total_sql = f"""
        SELECT COUNT(*) as call_count,
               COALESCE(SUM(prompt_tokens), 0) as total_prompt,
               COALESCE(SUM(completion_tokens), 0) as total_completion,
               COALESCE(SUM(quota), 0) as total_quota
        FROM logs WHERE {where}
    """
    totals = db.execute(total_sql, params).fetchone()
    
    # 按时间段分组统计
    if group_by == 'hour':
        time_expr = "created_at - (created_at % 3600)"
    else:
        time_expr = "created_at - (created_at % 86400)"
    
    time_sql = f"""
        SELECT {time_expr} as time_bucket,
               COUNT(*) as call_count,
               COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) as completion_tokens,
               COALESCE(SUM(quota), 0) as quota
        FROM logs WHERE {where}
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
    """
    time_data = db.execute(time_sql, params).fetchall()
    
    # 按模型统计
    model_sql = f"""
        SELECT model_name,
               COUNT(*) as call_count,
               COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) as completion_tokens,
               COALESCE(SUM(quota), 0) as quota
        FROM logs WHERE {where}
        GROUP BY model_name
        ORDER BY quota DESC
    """
    model_data = db.execute(model_sql, params).fetchall()
    
    # 按用户统计
    user_sql = f"""
        SELECT username,
               COUNT(*) as call_count,
               COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) as completion_tokens,
               COALESCE(SUM(quota), 0) as quota
        FROM logs WHERE {where}
        GROUP BY username
        ORDER BY quota DESC
    """
    user_data = db.execute(user_sql, params).fetchall()
    db.close()
    
    return {
        'totals': {
            'call_count': totals['call_count'],
            'prompt_tokens': totals['total_prompt'],
            'completion_tokens': totals['total_completion'],
            'total_tokens': totals['total_prompt'] + totals['total_completion'],
            'total_quota': totals['total_quota'],
            'total_usd': round(totals['total_quota'] / QUOTA_PER_UNIT, 4)
        },
        'time_series': [{
            'time': r['time_bucket'],
            'call_count': r['call_count'],
            'prompt_tokens': r['prompt_tokens'],
            'completion_tokens': r['completion_tokens'],
            'total_tokens': r['prompt_tokens'] + r['completion_tokens'],
            'quota': r['quota'],
            'usd': round(r['quota'] / QUOTA_PER_UNIT, 4)
        } for r in time_data],
        'by_model': [{
            'model_name': r['model_name'],
            'call_count': r['call_count'],
            'prompt_tokens': r['prompt_tokens'],
            'completion_tokens': r['completion_tokens'],
            'total_tokens': r['prompt_tokens'] + r['completion_tokens'],
            'quota': r['quota'],
            'usd': round(r['quota'] / QUOTA_PER_UNIT, 4)
        } for r in model_data],
        'by_user': [{
            'username': r['username'],
            'call_count': r['call_count'],
            'prompt_tokens': r['prompt_tokens'],
            'completion_tokens': r['completion_tokens'],
            'total_tokens': r['prompt_tokens'] + r['completion_tokens'],
            'quota': r['quota'],
            'usd': round(r['quota'] / QUOTA_PER_UNIT, 4)
        } for r in user_data]
    }


def get_filter_options(current_user=None):
    """获取筛选选项"""
    db = get_db()
    
    # 权限控制：非管理员只能看到自己使用过的模型
    if current_user and current_user.get('role') != 100:
        models = [r[0] for r in db.execute(
            "SELECT DISTINCT model_name FROM logs WHERE type=2 AND model_name != '' AND username = ? ORDER BY model_name",
            (current_user['username'],)
        ).fetchall()]
        users = [current_user['username']]  # 普通用户只能看到自己
    else:
        models = [r[0] for r in db.execute(
            "SELECT DISTINCT model_name FROM logs WHERE type=2 AND model_name != '' ORDER BY model_name"
        ).fetchall()]
        users = [r[0] for r in db.execute(
            "SELECT DISTINCT username FROM logs WHERE type=2 AND username != '' ORDER BY username"
        ).fetchall()]
    
    db.close()
    return {'models': models, 'users': users, 'is_admin': current_user.get('role') == 100 if current_user else False}


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def get_cookie(self, name):
        """从 Cookie 中获取值"""
        cookie_str = self.headers.get('Cookie', '')
        for part in cookie_str.split(';'):
            part = part.strip()
            if part.startswith(f'{name}='):
                return part[len(name)+1:]
        return None
    
    def set_cookie(self, name, value, max_age=86400):
        """设置 Cookie"""
        self.send_header('Set-Cookie', f'{name}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}')
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.end_headers()
    
    def get_session(self):
        """获取当前 session"""
        token = self.get_cookie('dashboard_session')
        return check_session(token)
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        
        def get_param(key, default=None):
            return params.get(key, [default])[0]
        
        # 登录页面
        if path == '/login':
            html_path = os.path.join(os.path.dirname(__file__), 'login.html')
            with open(html_path, 'r', encoding='utf-8') as f:
                html = f.read()
                # 注入 API_BASE 配置
                html = html.replace(
                    "window.__API_BASE__ || 'http://localhost:3000'",
                    f"'{API_BASE}'"
                )
                self.send_html(html)
            return
        
        # 登出
        if path == '/logout':
            token = self.get_cookie('dashboard_session')
            if token and token in sessions:
                del sessions[token]
            self.send_response(302)
            self.set_cookie('dashboard_session', '', max_age=0)
            self.send_header('Location', '/login')
            self.end_headers()
            return
        
        # 网站图标（无需鉴权，浏览器会自动请求）
        if path == '/icon.jpg' or path == '/favicon.ico':
            icon_path = os.path.join(os.path.dirname(__file__), 'icon.jpg')
            if os.path.exists(icon_path):
                with open(icon_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_json({'error': 'Not found'}, 404)
            return
        
        # 静态资源（如果有的话）
        if path.startswith('/static/'):
            file_path = os.path.join(os.path.dirname(__file__), path.lstrip('/'))
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                if path.endswith('.css'):
                    self.send_header('Content-Type', 'text/css')
                elif path.endswith('.js'):
                    self.send_header('Content-Type', 'application/javascript')
                else:
                    self.send_header('Content-Type', 'application/octet-stream')
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_json({'error': 'Not found'}, 404)
            return
        
        # API 接口需要鉴权
        if path.startswith('/api/'):
            session = self.get_session()
            if not session:
                self.send_json({'error': 'Unauthorized', 'message': '请先登录'}, 401)
                return
            
            # 定期清理过期 session
            cleanup_sessions()
            
            if path == '/api/stats':
                data = get_stats(
                    model=get_param('model'),
                    username=get_param('username'),
                    start_time=get_param('start_time'),
                    end_time=get_param('end_time'),
                    group_by=get_param('group_by', 'day'),
                    current_user=session
                )
                self.send_json(data)
            
            elif path == '/api/logs':
                data = query_logs(
                    model=get_param('model'),
                    username=get_param('username'),
                    start_time=get_param('start_time'),
                    end_time=get_param('end_time'),
                    page=int(get_param('page', 1)),
                    per_page=int(get_param('per_page', 50)),
                    current_user=session
                )
                self.send_json(data)
            
            elif path == '/api/filters':
                data = get_filter_options(current_user=session)
                self.send_json(data)
            
            elif path == '/api/me':
                self.send_json({
                    'user_id': session['user_id'],
                    'username': session['username'],
                    'role': session['role']
                })
            
            else:
                self.send_json({'error': 'Not found'}, 404)
            return
        
        # 主页面需要鉴权
        if path == '/' or path == '/index.html':
            session = self.get_session()
            if not session:
                self.redirect('/login')
                return
            html_path = os.path.join(os.path.dirname(__file__), 'index.html')
            with open(html_path, 'r', encoding='utf-8') as f:
                self.send_html(f.read())
            return
        
        # 其他路径重定向到登录
        self.redirect('/login')
    
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        # 读取 POST body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        if path == '/api/login':
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {}
            
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json({'success': False, 'message': '请输入用户名和密码'}, 400)
                return
            
            user_info = verify_password(username, password)
            if user_info:
                token = create_session(user_info)
                self.send_response(200)
                self.set_cookie('dashboard_session', token, max_age=SESSION_EXPIRE)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'message': '登录成功',
                    'user': {
                        'user_id': user_info['user_id'],
                        'username': user_info['username'],
                        'role': user_info['role']
                    }
                }, ensure_ascii=False).encode())
            else:
                self.send_json({'success': False, 'message': '用户名或密码错误'}, 401)
            return
        
        self.send_json({'error': 'Not found'}, 404)


if __name__ == '__main__':
    print(f"🚀 New API Dashboard 启动中... 端口 {PORT}")
    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), DashboardHandler)
    server.serve_forever()
