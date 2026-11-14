#!/usr/bin/env python3
"""
Python Modern File Server v2.0 (Enterprise Edition)
Servidor de archivos web moderno y autónomo en Python (100% librería estándar).
Incluye:
1. Enlaces públicos para compartir archivos/carpetas (con expiración, límite de descargas y contraseña opcional)
2. Sistema Multi-usuario con Roles (admin, editor, viewer) en SQLite
3. Papelera de reciclaje (.trash) con restauración y vaciado
4. Operaciones masivas (selección múltiple: eliminar, mover, comprimir ZIP), extracción de archivos (.zip/.tar.gz) y editor de texto/código integrado
5. Vista de Cuadrícula (Grid View), Visor PDF integrado y Streaming de Video/Audio con soporte HTTP Range (206 Partial Content)
6. Seguridad avanzada: Rate Limiting contra fuerza bruta, Registro de Auditoría (Audit Logs) y soporte HTTPS/SSL nativo
"""

import argparse
import base64
import datetime
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import stat
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def load_dotenv(dotenv_path: Path):
    if not dotenv_path.is_file():
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


load_dotenv(Path(__file__).parent / ".env")


def hash_password(password: str, salt: str = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        if "$" not in stored_hash:
            return hmac.compare_digest(password, stored_hash)
        salt, _ = stored_hash.split("$", 1)
        return hmac.compare_digest(hash_password(password, salt), stored_hash)
    except Exception:
        return False


class DatabaseManager:
    """Gestiona usuarios, enlaces compartidos, papelera y auditoría en SQLite."""

    def __init__(self, db_path: Path, default_user: str, default_pass: str):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db(default_user, default_pass)

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self, default_user: str, default_pass: str):
        with self.lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'admin',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shares (
                    token TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    max_downloads INTEGER,
                    downloads INTEGER NOT NULL DEFAULT 0,
                    password_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS trash (
                    id TEXT PRIMARY KEY,
                    orig_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    is_dir INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    deleted_by TEXT NOT NULL,
                    deleted_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    details TEXT
                );
            """)
            cur = conn.execute("SELECT COUNT(*) as cnt FROM users")
            if cur.fetchone()["cnt"] == 0:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                    (default_user, hash_password(default_pass), int(time.time())),
                )
            conn.commit()

    # --- Usuarios ---
    def authenticate_user(self, username: str, password: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if row and verify_password(password, row["password_hash"]):
                return {"username": row["username"], "role": row["role"], "created_at": row["created_at"]}
            return None

    def get_user(self, username: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT username, role, created_at FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT username, role, created_at FROM users ORDER BY created_at ASC").fetchall()
            return [dict(r) for r in rows]

    def create_or_update_user(self, username: str, password: str, role: str):
        if role not in ("admin", "editor", "viewer"):
            raise ValueError("Rol inválido. Usa: admin, editor o viewer.")
        with self.lock, self._connect() as conn:
            existing = conn.execute("SELECT username FROM users WHERE username = ?", (username,)).fetchone()
            if existing:
                if password:
                    conn.execute("UPDATE users SET password_hash = ?, role = ? WHERE username = ?", (hash_password(password), role, username))
                else:
                    conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
            else:
                if not password:
                    raise ValueError("Se requiere contraseña para crear un usuario.")
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, hash_password(password), role, int(time.time())),
                )
            conn.commit()

    def delete_user(self, username: str):
        with self.lock, self._connect() as conn:
            admins = conn.execute("SELECT username FROM users WHERE role = 'admin'").fetchall()
            if len(admins) <= 1 and any(a["username"] == username for a in admins):
                raise ValueError("No puedes eliminar al único administrador del sistema.")
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()

    # --- Enlaces Compartidos (Shares) ---
    def create_share(self, path: str, created_by: str, expires_hours: float = None, max_downloads: int = None, password: str = None) -> dict:
        token = secrets.token_urlsafe(12)
        now = int(time.time())
        expires_at = int(now + expires_hours * 3600) if expires_hours and expires_hours > 0 else None
        max_dl = int(max_downloads) if max_downloads and int(max_downloads) > 0 else None
        pw_hash = hash_password(password) if password else None

        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO shares (token, path, created_by, created_at, expires_at, max_downloads, downloads, password_hash) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (token, path, created_by, now, expires_at, max_dl, pw_hash),
            )
            conn.commit()
        return self.get_share(token)

    def get_share(self, token: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM shares WHERE token = ?", (token,)).fetchone()
            return dict(row) if row else None

    def increment_share_download(self, token: str):
        with self.lock, self._connect() as conn:
            conn.execute("UPDATE shares SET downloads = downloads + 1 WHERE token = ?", (token,))
            conn.commit()

    def list_shares(self) -> list:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT token, path, created_by, created_at, expires_at, max_downloads, downloads, (password_hash IS NOT NULL) as has_password FROM shares ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def delete_share(self, token: str):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM shares WHERE token = ?", (token,))
            conn.commit()

    # --- Papelera (Trash) ---
    def add_trash_item(self, item_id: str, orig_path: str, name: str, is_dir: bool, size: int, deleted_by: str):
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO trash (id, orig_path, name, is_dir, size, deleted_by, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item_id, orig_path, name, 1 if is_dir else 0, size, deleted_by, int(time.time())),
            )
            conn.commit()

    def list_trash(self) -> list:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM trash ORDER BY deleted_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_trash_item(self, item_id: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM trash WHERE id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

    def remove_trash_item(self, item_id: str):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM trash WHERE id = ?", (item_id,))
            conn.commit()

    def clear_trash(self):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM trash")
            conn.commit()

    # --- Auditoría ---
    def log_audit(self, username: str, ip: str, action: str, target: str, details: str = ""):
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_logs (timestamp, username, ip, action, target, details) VALUES (?, ?, ?, ?, ?, ?)",
                (int(time.time()), username or "anónimo", ip, action, target, details),
            )
            conn.commit()

    def list_audit_logs(self, limit: int = 150) -> list:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]


class RateLimiter:
    """Protección contra ataques de fuerza bruta por IP."""

    def __init__(self, max_attempts: int = 5, window_sec: int = 300, lockout_sec: int = 300):
        self.max_attempts = max_attempts
        self.window_sec = window_sec
        self.lockout_sec = lockout_sec
        self.attempts = {}
        self.lockouts = {}
        self.lock = threading.Lock()

    def is_blocked(self, ip: str) -> int:
        with self.lock:
            now = time.time()
            if ip in self.lockouts:
                remaining = int(self.lockouts[ip] - now)
                if remaining > 0:
                    return remaining
                del self.lockouts[ip]
            return 0

    def record_failure(self, ip: str):
        with self.lock:
            now = time.time()
            history = [t for t in self.attempts.get(ip, []) if now - t < self.window_sec]
            history.append(now)
            self.attempts[ip] = history
            if len(history) >= self.max_attempts:
                self.lockouts[ip] = now + self.lockout_sec
                self.attempts[ip] = []

    def record_success(self, ip: str):
        with self.lock:
            self.attempts.pop(ip, None)
            self.lockouts.pop(ip, None)


class ServerConfig:
    def __init__(self, host: str, port: int, storage_dir: Path, username: str, password: str, secret_key: str, auth_enabled: bool = True, db_path: Path = None):
        self.host = host
        self.port = port
        self.storage_dir = storage_dir.resolve()
        self.trash_dir = self.storage_dir / ".trash"
        self.secret_key = secret_key.encode("utf-8")
        self.auth_enabled = auth_enabled
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        if db_path is None:
            db_path = Path(__file__).parent / "fileserver.db"
        self.db = DatabaseManager(db_path, username, password)
        self.rate_limiter = RateLimiter()

    def create_session_token(self, username: str) -> str:
        timestamp = str(int(time.time()))
        payload = f"{username}:{timestamp}"
        sig = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def verify_session_token(self, token: str, max_age: int = 86400 * 7) -> dict:
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return None
            username, timestamp_str, sig = parts
            payload = f"{username}:{timestamp_str}"
            expected_sig = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            if int(time.time()) - int(timestamp_str) > max_age:
                return None
            return self.db.get_user(username)
        except Exception:
            return None


class FileServerHandler(BaseHTTPRequestHandler):
    config: ServerConfig = None
    static_dir: Path = Path(__file__).parent / "static"
    templates_dir: Path = Path(__file__).parent / "templates"

    def log_message(self, format_str, *args):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout.write(f"[{timestamp}] {self.client_address[0]} - {format_str % args}\n")

    def get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    # --- Helpers de Respuesta ---
    def send_json(self, data: dict, status: int = HTTPStatus.OK, extra_headers: dict = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_html_file(self, filename: str, status: int = HTTPStatus.OK):
        file_path = self.templates_dir / filename
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Template not found")
            return
        content = file_path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # --- Autenticación y Permisos ---
    def get_current_user(self) -> dict:
        if not self.config.auth_enabled:
            return {"username": "admin", "role": "admin"}

        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookies = http.cookies.SimpleCookie()
            try:
                cookies.load(cookie_header)
                if "fs_session" in cookies:
                    token = cookies["fs_session"].value
                    user = self.config.verify_session_token(token)
                    if user:
                        return user
            except Exception:
                pass

        auth_header = self.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                encoded = auth_header.split(" ", 1)[1].strip()
                decoded = base64.b64decode(encoded).decode("utf-8")
                if ":" in decoded:
                    username, pw = decoded.split(":", 1)
                    user = self.config.db.authenticate_user(username, pw)
                    if user:
                        return user
            except Exception:
                pass

        return None

    def require_role(self, user: dict, allowed_roles: tuple) -> bool:
        if not user or user.get("role") not in allowed_roles:
            self.send_json({"error": "No tienes permisos suficientes para realizar esta acción."}, status=HTTPStatus.FORBIDDEN)
            return False
        return True

    # --- Seguridad de Rutas ---
    def resolve_storage_path(self, rel_path: str) -> Path:
        cleaned = (rel_path or "").strip().lstrip("/").lstrip("\\")
        target = (self.config.storage_dir / cleaned).resolve()
        base = self.config.storage_dir.resolve()
        if target != base and base not in target.parents:
            raise PermissionError("Acceso denegado: ruta fuera del directorio permitido.")
        # Bloquear acceso directo a .trash por API de archivos normales
        if target == self.config.trash_dir or self.config.trash_dir in target.parents:
            raise PermissionError("Acceso directo a la papelera no permitido.")
        return target

    def sanitize_filename(self, name: str) -> str:
        name = os.path.basename(name.strip().replace("\\", "/"))
        if name in ("", ".", "..", ".trash", ".gitkeep"):
            raise ValueError("Nombre de archivo o carpeta inválido.")
        return name

    # --- Enrutamiento HTTP ---
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route.startswith("/static/"):
            self.handle_static(route[len("/static/"):])
            return

        # Enlaces compartidos públicos (/s/<token>)
        if route.startswith("/s/"):
            token = route[len("/s/"):].strip("/")
            self.handle_public_share(token, query)
            return

        user = self.get_current_user()

        if route == "/login":
            if user:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.send_html_file("login.html")
            return

        if route == "/api/auth/status":
            self.send_json({
                "authenticated": user is not None,
                "auth_enabled": self.config.auth_enabled,
                "username": user["username"] if user else None,
                "role": user["role"] if user else None,
            })
            return

        if not user:
            if route.startswith("/api/"):
                self.send_json({"error": "No autorizado. Inicia sesión primero."}, status=HTTPStatus.UNAUTHORIZED)
            else:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/login")
                self.end_headers()
            return

        if route == "/":
            self.send_html_file("index.html")
        elif route == "/api/files":
            rel_path = query.get("path", [""])[0]
            search_q = query.get("search", [""])[0].strip()
            self.handle_list_files(rel_path, search_q)
        elif route == "/api/download":
            rel_path = query.get("path", [""])[0]
            inline = query.get("inline", ["0"])[0] == "1"
            self.handle_download(rel_path, inline=inline, user=user)
        elif route == "/api/zip":
            rel_path = query.get("path", [""])[0]
            self.handle_download_zip(rel_path, user=user)
        elif route == "/api/trash":
            self.send_json({"items": self.config.db.list_trash()})
        elif route == "/api/shares":
            if self.require_role(user, ("admin", "editor")):
                self.send_json({"items": self.config.db.list_shares()})
        elif route == "/api/users":
            if self.require_role(user, ("admin",)):
                self.send_json({"items": self.config.db.list_users()})
        elif route == "/api/audit":
            if self.require_role(user, ("admin",)):
                self.send_json({"items": self.config.db.list_audit_logs()})
        else:
            self.send_json({"error": "Ruta no encontrada"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route == "/api/login":
            self.handle_login()
            return

        if route == "/api/logout":
            self.handle_logout()
            return

        user = self.get_current_user()
        if not user:
            self.send_json({"error": "No autorizado. Inicia sesión primero."}, status=HTTPStatus.UNAUTHORIZED)
            return

        if route == "/api/mkdir":
            if self.require_role(user, ("admin", "editor")):
                self.handle_mkdir(user)
        elif route == "/api/rename":
            if self.require_role(user, ("admin", "editor")):
                self.handle_rename(user)
        elif route == "/api/delete":
            if self.require_role(user, ("admin",)):
                self.handle_delete(user)
        elif route == "/api/upload":
            if self.require_role(user, ("admin", "editor")):
                self.handle_upload(query, user)
        elif route == "/api/save-text":
            if self.require_role(user, ("admin", "editor")):
                self.handle_save_text(user)
        elif route == "/api/extract":
            if self.require_role(user, ("admin", "editor")):
                self.handle_extract(user)
        elif route == "/api/bulk/delete":
            if self.require_role(user, ("admin",)):
                self.handle_bulk_delete(user)
        elif route == "/api/bulk/move":
            if self.require_role(user, ("admin", "editor")):
                self.handle_bulk_move(user)
        elif route == "/api/bulk/zip":
            self.handle_bulk_zip(user)
        elif route == "/api/trash/restore":
            if self.require_role(user, ("admin", "editor")):
                self.handle_trash_restore(user)
        elif route == "/api/trash/empty":
            if self.require_role(user, ("admin",)):
                self.handle_trash_empty(user)
        elif route == "/api/shares/create":
            if self.require_role(user, ("admin", "editor")):
                self.handle_share_create(user)
        elif route == "/api/shares/delete":
            if self.require_role(user, ("admin", "editor")):
                self.handle_share_delete(user)
        elif route == "/api/users/save":
            if self.require_role(user, ("admin",)):
                self.handle_user_save(user)
        elif route == "/api/users/delete":
            if self.require_role(user, ("admin",)):
                self.handle_user_delete(user)
        else:
            self.send_json({"error": "Ruta no encontrada"}, status=HTTPStatus.NOT_FOUND)

    # --- Controladores Estáticos y Login ---
    def handle_static(self, rel_static: str):
        try:
            base = self.static_dir.resolve()
            target = (base / rel_static.lstrip("/")).resolve()
            if target != base and base not in target.parents or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
                return
            mime, _ = mimetypes.guess_type(str(target))
            content = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def handle_login(self):
        ip = self.get_client_ip()
        blocked_sec = self.config.rate_limiter.is_blocked(ip)
        if blocked_sec > 0:
            self.send_json(
                {"error": f"Demasiados intentos fallidos. Intenta nuevamente en {blocked_sec} segundos."},
                status=HTTPStatus.TOO_MANY_REQUESTS,
            )
            return

        try:
            body = self.read_json_body()
            username = body.get("username", "").strip()
            password = body.get("password", "")

            user = self.config.db.authenticate_user(username, password)
            if user:
                self.config.rate_limiter.record_success(ip)
                token = self.config.create_session_token(username)
                cookie = f"fs_session={token}; HttpOnly; Path=/; Max-Age={86400 * 7}; SameSite=Lax"
                self.config.db.log_audit(username, ip, "LOGIN", "Sesión iniciada", f"Rol: {user['role']}")
                self.send_json({"ok": True, "username": username, "role": user["role"]}, extra_headers={"Set-Cookie": cookie})
            else:
                self.config.rate_limiter.record_failure(ip)
                self.config.db.log_audit(username or "desconocido", ip, "LOGIN_FAILED", "Intento fallido", "")
                self.send_json({"error": "Usuario o contraseña incorrectos."}, status=HTTPStatus.UNAUTHORIZED)
        except Exception as e:
            self.send_json({"error": f"Error en solicitud de login: {e}"}, status=HTTPStatus.BAD_REQUEST)

    def handle_logout(self):
        user = self.get_current_user()
        if user:
            self.config.db.log_audit(user["username"], self.get_client_ip(), "LOGOUT", "Sesión cerrada", "")
        cookie = "fs_session=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax"
        self.send_json({"ok": True}, extra_headers={"Set-Cookie": cookie})

    # --- Archivos y Carpetas ---
    def get_file_info(self, item: Path) -> dict:
        st = item.stat()
        is_dir = stat.S_ISDIR(st.st_mode)
        rel = item.relative_to(self.config.storage_dir).as_posix()
        mime, _ = mimetypes.guess_type(item.name) if not is_dir else (None, None)
        return {
            "name": item.name,
            "path": rel,
            "is_dir": is_dir,
            "size": 0 if is_dir else st.st_size,
            "mtime": int(st.st_mtime),
            "mime": mime or ("inode/directory" if is_dir else "application/octet-stream"),
        }

    def _calc_dir_size(self, path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for r, _, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(r) / f).stat().st_size
                except Exception:
                    pass
        return total

    def handle_list_files(self, rel_path: str, search_query: str = ""):
        try:
            target_dir = self.resolve_storage_path(rel_path)
            if not target_dir.exists():
                self.send_json({"error": "El directorio no existe."}, status=HTTPStatus.NOT_FOUND)
                return
            if not target_dir.is_dir():
                self.send_json({"error": "La ruta especificada no es un directorio."}, status=HTTPStatus.BAD_REQUEST)
                return

            items = []
            if search_query:
                q_lower = search_query.lower()
                for root, dirs, files in os.walk(target_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    root_path = Path(root)
                    for d in dirs:
                        if q_lower in d.lower():
                            items.append(self.get_file_info(root_path / d))
                    for f in files:
                        if f in (".gitkeep",):
                            continue
                        if q_lower in f.lower():
                            items.append(self.get_file_info(root_path / f))
            else:
                for entry in target_dir.iterdir():
                    if entry.name in (".gitkeep", ".trash"):
                        continue
                    items.append(self.get_file_info(entry))

            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            usage = shutil.disk_usage(self.config.storage_dir)
            current_rel = "" if target_dir == self.config.storage_dir else target_dir.relative_to(self.config.storage_dir).as_posix()

            self.send_json({
                "current_path": current_rel,
                "items": items,
                "disk": {"total": usage.total, "used": usage.used, "free": usage.free},
            })
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"Error al listar archivos: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_mkdir(self, user: dict):
        try:
            body = self.read_json_body()
            parent_rel = body.get("path", "")
            folder_name = self.sanitize_filename(body.get("name", ""))
            parent_dir = self.resolve_storage_path(parent_rel)
            if not parent_dir.is_dir():
                self.send_json({"error": "El directorio padre no existe."}, status=HTTPStatus.BAD_REQUEST)
                return

            new_dir = self.resolve_storage_path(f"{parent_rel}/{folder_name}")
            if new_dir.exists():
                self.send_json({"error": "Ya existe un archivo o carpeta con ese nombre."}, status=HTTPStatus.CONFLICT)
                return

            new_dir.mkdir(parents=False, exist_ok=False)
            rel_created = new_dir.relative_to(self.config.storage_dir).as_posix()
            self.config.db.log_audit(user["username"], self.get_client_ip(), "MKDIR", rel_created)
            self.send_json({"ok": True, "item": self.get_file_info(new_dir)}, status=HTTPStatus.CREATED)
        except (ValueError, PermissionError) as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self.send_json({"error": f"No se pudo crear la carpeta: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_rename(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")
            new_name = self.sanitize_filename(body.get("new_name", ""))
            target = self.resolve_storage_path(rel_path)
            if target == self.config.storage_dir:
                self.send_json({"error": "No se puede renombrar el directorio raíz."}, status=HTTPStatus.BAD_REQUEST)
                return
            if not target.exists():
                self.send_json({"error": "El archivo o carpeta no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            dest = target.parent / new_name
            if dest.exists():
                self.send_json({"error": "Ya existe un elemento con ese nombre."}, status=HTTPStatus.CONFLICT)
                return

            target.rename(dest)
            self.config.db.log_audit(user["username"], self.get_client_ip(), "RENAME", rel_path, f"Nuevo nombre: {new_name}")
            self.send_json({"ok": True, "item": self.get_file_info(dest)})
        except (ValueError, PermissionError) as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self.send_json({"error": f"No se pudo renombrar: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _move_to_trash(self, target: Path, username: str):
        orig_rel = target.relative_to(self.config.storage_dir).as_posix()
        item_id = f"{int(time.time())}_{secrets.token_hex(4)}"
        is_dir = target.is_dir()
        size = self._calc_dir_size(target)
        trash_dest = self.config.trash_dir / item_id
        shutil.move(str(target), str(trash_dest))
        self.config.db.add_trash_item(item_id, orig_rel, target.name, is_dir, size, username)

    def handle_delete(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")
            permanent = bool(body.get("permanent", False))
            target = self.resolve_storage_path(rel_path)
            if target == self.config.storage_dir:
                self.send_json({"error": "No se puede eliminar el directorio raíz."}, status=HTTPStatus.BAD_REQUEST)
                return
            if not target.exists():
                self.send_json({"error": "El archivo o carpeta no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            if permanent:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                self.config.db.log_audit(user["username"], self.get_client_ip(), "DELETE_PERM", rel_path)
            else:
                self._move_to_trash(target, user["username"])
                self.config.db.log_audit(user["username"], self.get_client_ip(), "TRASH", rel_path)

            self.send_json({"ok": True})
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"No se pudo eliminar: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_upload(self, query: dict, user: dict):
        try:
            rel_dir = query.get("path", [""])[0]
            raw_filename = self.headers.get("X-File-Name")
            if raw_filename:
                raw_filename = urllib.parse.unquote(raw_filename)
            else:
                raw_filename = query.get("filename", [""])[0]

            rel_subpath = raw_filename.strip().replace("\\", "/").lstrip("/")
            if not rel_subpath:
                self.send_json({"error": "Nombre de archivo no especificado."}, status=HTTPStatus.BAD_REQUEST)
                return

            base_dir = self.resolve_storage_path(rel_dir)
            if not base_dir.is_dir():
                self.send_json({"error": "El directorio destino no existe."}, status=HTTPStatus.BAD_REQUEST)
                return

            dest_path = self.resolve_storage_path(f"{rel_dir}/{rel_subpath}")
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            overwrite = query.get("overwrite", ["1"])[0] == "1"
            if dest_path.exists() and dest_path.is_dir():
                self.send_json({"error": "Existe una carpeta con el mismo nombre."}, status=HTTPStatus.CONFLICT)
                return
            if dest_path.exists() and not overwrite:
                stem, suffix = dest_path.stem, dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = dest_path.parent / f"{stem} ({counter}){suffix}"
                    counter += 1

            content_length = int(self.headers.get("Content-Length", 0))
            remaining = content_length
            chunk_size = 64 * 1024

            with open(dest_path, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            rel_uploaded = dest_path.relative_to(self.config.storage_dir).as_posix()
            self.config.db.log_audit(user["username"], self.get_client_ip(), "UPLOAD", rel_uploaded, f"{content_length} bytes")
            self.send_json({"ok": True, "item": self.get_file_info(dest_path)}, status=HTTPStatus.CREATED)
        except (ValueError, PermissionError) as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self.send_json({"error": f"Error al subir archivo: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # --- Editor de Texto y Descompresión ---
    def handle_save_text(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")
            content = body.get("content", "")
            target = self.resolve_storage_path(rel_path)
            if target.is_dir():
                self.send_json({"error": "No se puede sobrescribir una carpeta como texto."}, status=HTTPStatus.BAD_REQUEST)
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            self.config.db.log_audit(user["username"], self.get_client_ip(), "EDIT_FILE", rel_path)
            self.send_json({"ok": True, "item": self.get_file_info(target)})
        except Exception as e:
            self.send_json({"error": f"No se pudo guardar el archivo: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_extract(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")
            target = self.resolve_storage_path(rel_path)
            if not target.is_file():
                self.send_json({"error": "El archivo comprimido no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            extract_dir = target.parent / target.stem
            if extract_dir.name.endswith(".tar"):
                extract_dir = target.parent / extract_dir.stem
            extract_dir.mkdir(parents=True, exist_ok=True)
            base_resolved = extract_dir.resolve()

            name_lower = target.name.lower()
            if name_lower.endswith(".zip"):
                with zipfile.ZipFile(target, "r") as zf:
                    for member in zf.infolist():
                        dest_member = (extract_dir / member.filename).resolve()
                        if dest_member != base_resolved and base_resolved not in dest_member.parents:
                            raise PermissionError("Archivo ZIP contiene rutas inseguras (Zip Slip).")
                    zf.extractall(extract_dir)
            elif name_lower.endswith((".tar.gz", ".tgz", ".tar")):
                with tarfile.open(target, "r:*") as tf:
                    for member in tf.getmembers():
                        dest_member = (extract_dir / member.name).resolve()
                        if dest_member != base_resolved and base_resolved not in dest_member.parents:
                            raise PermissionError("Archivo TAR contiene rutas inseguras.")
                    tf.extractall(extract_dir)
            else:
                self.send_json({"error": "Formato no soportado para extracción (usa .zip, .tar.gz o .tar)."}, status=HTTPStatus.BAD_REQUEST)
                return

            self.config.db.log_audit(user["username"], self.get_client_ip(), "EXTRACT", rel_path, f"Extraído en {extract_dir.name}")
            self.send_json({"ok": True, "extracted_to": extract_dir.relative_to(self.config.storage_dir).as_posix()})
        except Exception as e:
            self.send_json({"error": f"Error al descomprimir: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # --- Operaciones Masivas (Bulk) ---
    def handle_bulk_delete(self, user: dict):
        try:
            body = self.read_json_body()
            paths = body.get("paths", [])
            count = 0
            for p in paths:
                target = self.resolve_storage_path(p)
                if target != self.config.storage_dir and target.exists():
                    self._move_to_trash(target, user["username"])
                    count += 1
            self.config.db.log_audit(user["username"], self.get_client_ip(), "BULK_TRASH", f"{count} elementos", ", ".join(paths[:5]))
            self.send_json({"ok": True, "deleted": count})
        except Exception as e:
            self.send_json({"error": f"Error en eliminación masiva: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_bulk_move(self, user: dict):
        try:
            body = self.read_json_body()
            paths = body.get("paths", [])
            dest_rel = body.get("destination", "")
            dest_dir = self.resolve_storage_path(dest_rel)
            if not dest_dir.exists() or not dest_dir.is_dir():
                self.send_json({"error": "La carpeta de destino no existe."}, status=HTTPStatus.BAD_REQUEST)
                return

            moved = 0
            for p in paths:
                src = self.resolve_storage_path(p)
                if src == self.config.storage_dir or not src.exists():
                    continue
                target_dest = dest_dir / src.name
                if src == target_dest or src in dest_dir.parents:
                    continue
                shutil.move(str(src), str(target_dest))
                moved += 1

            self.config.db.log_audit(user["username"], self.get_client_ip(), "BULK_MOVE", f"{moved} elementos -> /{dest_rel}")
            self.send_json({"ok": True, "moved": moved})
        except Exception as e:
            self.send_json({"error": f"Error al mover elementos: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_bulk_zip(self, user: dict):
        try:
            body = self.read_json_body()
            paths = body.get("paths", [])
            if not paths:
                self.send_json({"error": "No se seleccionaron archivos."}, status=HTTPStatus.BAD_REQUEST)
                return

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths:
                        target = self.resolve_storage_path(p)
                        if not target.exists():
                            continue
                        if target.is_file():
                            zf.write(target, target.name)
                        elif target.is_dir():
                            for root, _, files in os.walk(target):
                                for file in files:
                                    if file == ".gitkeep":
                                        continue
                                    full_p = Path(root) / file
                                    arc = f"{target.name}/{full_p.relative_to(target).as_posix()}"
                                    zf.write(full_p, arc)

                tmp.flush()
                size = os.path.getsize(tmp.name)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", "attachment; filename=\"seleccion.zip\"")
                self.end_headers()
                with open(tmp.name, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, length=64 * 1024)
        except Exception as e:
            self.send_json({"error": f"Error al generar ZIP: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # --- Papelera (Trash) ---
    def handle_trash_restore(self, user: dict):
        try:
            body = self.read_json_body()
            item_id = body.get("id", "")
            item = self.config.db.get_trash_item(item_id)
            if not item:
                self.send_json({"error": "Elemento no encontrado en la papelera."}, status=HTTPStatus.NOT_FOUND)
                return

            trash_file = self.config.trash_dir / item_id
            if not trash_file.exists():
                self.config.db.remove_trash_item(item_id)
                self.send_json({"error": "El archivo físico ya no existe en la papelera."}, status=HTTPStatus.NOT_FOUND)
                return

            dest = self.resolve_storage_path(item["orig_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest.parent / f"{dest.stem}_restaurado{dest.suffix}"

            shutil.move(str(trash_file), str(dest))
            self.config.db.remove_trash_item(item_id)
            self.config.db.log_audit(user["username"], self.get_client_ip(), "TRASH_RESTORE", item["orig_path"])
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": f"No se pudo restaurar: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_trash_empty(self, user: dict):
        try:
            for child in self.config.trash_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            self.config.db.clear_trash()
            self.config.db.log_audit(user["username"], self.get_client_ip(), "TRASH_EMPTY", "Papelera vaciada")
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": f"No se pudo vaciar la papelera: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # --- Enlaces Públicos (Shares) ---
    def handle_share_create(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")
            target = self.resolve_storage_path(rel_path)
            if not target.exists():
                self.send_json({"error": "El archivo o carpeta no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            expires_hours = body.get("expires_hours")
            max_downloads = body.get("max_downloads")
            password = body.get("password", "").strip() or None

            share = self.config.db.create_share(
                rel_path,
                user["username"],
                float(expires_hours) if expires_hours else None,
                int(max_downloads) if max_downloads else None,
                password,
            )
            self.config.db.log_audit(user["username"], self.get_client_ip(), "SHARE_CREATE", rel_path, f"Token: {share['token']}")
            self.send_json({"ok": True, "share": share})
        except Exception as e:
            self.send_json({"error": f"Error al crear enlace: {e}"}, status=HTTPStatus.BAD_REQUEST)

    def handle_share_delete(self, user: dict):
        body = self.read_json_body()
        token = body.get("token", "")
        self.config.db.delete_share(token)
        self.config.db.log_audit(user["username"], self.get_client_ip(), "SHARE_DELETE", token)
        self.send_json({"ok": True})

    def handle_public_share(self, token: str, query: dict):
        share = self.config.db.get_share(token)
        if not share:
            self.send_error(HTTPStatus.NOT_FOUND, "El enlace compartido no existe o fue eliminado.")
            return

        now = int(time.time())
        if share["expires_at"] and now > share["expires_at"]:
            self.send_error(HTTPStatus.GONE, "Este enlace compartido ha expirado.")
            return

        if share["max_downloads"] and share["downloads"] >= share["max_downloads"]:
            self.send_error(HTTPStatus.GONE, "Se alcanzo el limite maximo de descargas para este enlace.")
            return

        if share["password_hash"]:
            provided_pw = query.get("password", [""])[0]
            if not provided_pw or not verify_password(provided_pw, share["password_hash"]):
                html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Enlace Protegido</title>
                <link rel="stylesheet" href="/static/styles.css"></head><body class="login-body">
                <div class="login-card"><div class="login-header"><h1>🔒 Enlace Protegido</h1><p>Ingresa la contraseña para descargar <b>{os.path.basename(share['path'])}</b></p></div>
                <form method="GET" action="/s/{token}"><div class="form-group"><input type="password" name="password" placeholder="Contraseña" required autofocus></div>
                <button class="btn btn-primary btn-block" type="submit">Descargar</button></form></div></body></html>"""
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        self.config.db.increment_share_download(token)
        self.config.db.log_audit("público", self.get_client_ip(), "SHARE_DOWNLOAD", share["path"], f"Token: {token}")
        target = self.resolve_storage_path(share["path"])
        if target.is_dir():
            self.handle_download_zip(share["path"], user=None)
        else:
            self.handle_download(share["path"], inline=False, user=None)

    # --- Gestión de Usuarios ---
    def handle_user_save(self, user: dict):
        try:
            body = self.read_json_body()
            username = body.get("username", "").strip()
            password = body.get("password", "")
            role = body.get("role", "viewer")
            if not username:
                self.send_json({"error": "Nombre de usuario requerido."}, status=HTTPStatus.BAD_REQUEST)
                return
            self.config.db.create_or_update_user(username, password, role)
            self.config.db.log_audit(user["username"], self.get_client_ip(), "USER_SAVE", username, f"Rol: {role}")
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    def handle_user_delete(self, user: dict):
        try:
            body = self.read_json_body()
            username = body.get("username", "").strip()
            self.config.db.delete_user(username)
            self.config.db.log_audit(user["username"], self.get_client_ip(), "USER_DELETE", username)
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    # --- Descargas y Streaming con HTTP Range ---
    def handle_download(self, rel_path: str, inline: bool = False, user: dict = None):
        try:
            target = self.resolve_storage_path(rel_path)
            if not target.exists() or not target.is_file():
                self.send_json({"error": "Archivo no encontrado."}, status=HTTPStatus.NOT_FOUND)
                return

            mime, _ = mimetypes.guess_type(target.name)
            if not mime:
                mime = "application/octet-stream"

            file_size = target.stat().st_size
            disposition_type = "inline" if inline else "attachment"
            encoded_name = urllib.parse.quote(target.name)

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                m = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else file_size - 1
                    end = min(end, file_size - 1)
                    if start <= end and start < file_size:
                        length = end - start + 1
                        self.send_response(HTTPStatus.PARTIAL_CONTENT)
                        self.send_header("Content-Type", mime)
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                        self.send_header("Content-Length", str(length))
                        self.send_header("Content-Disposition", f"{disposition_type}; filename*=UTF-8''{encoded_name}")
                        self.end_headers()
                        with open(target, "rb") as f:
                            f.seek(start)
                            remaining = length
                            while remaining > 0:
                                chunk = f.read(min(64 * 1024, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return

            if user and not inline:
                self.config.db.log_audit(user["username"], self.get_client_ip(), "DOWNLOAD", rel_path)

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f"{disposition_type}; filename*=UTF-8''{encoded_name}")
            self.end_headers()

            with open(target, "rb") as f:
                shutil.copyfileobj(f, self.wfile, length=64 * 1024)
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.send_json({"error": f"Error al descargar archivo: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_download_zip(self, rel_path: str, user: dict = None):
        try:
            target_dir = self.resolve_storage_path(rel_path)
            if not target_dir.exists() or not target_dir.is_dir():
                self.send_json({"error": "Carpeta no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return

            zip_name = f"{target_dir.name or 'storage'}.zip"
            encoded_name = urllib.parse.quote(zip_name)

            if user:
                self.config.db.log_audit(user["username"], self.get_client_ip(), "DOWNLOAD_ZIP", rel_path or "/")

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(target_dir):
                        dirs[:] = [d for d in dirs if d != ".trash"]
                        for file in files:
                            if file == ".gitkeep":
                                continue
                            full_path = Path(root) / file
                            arcname = full_path.relative_to(target_dir).as_posix()
                            zf.write(full_path, arcname)

                tmp.flush()
                size = os.path.getsize(tmp.name)

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
                self.end_headers()

                with open(tmp.name, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, length=64 * 1024)
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.send_json({"error": f"Error al generar ZIP: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def parse_args():
    parser = argparse.ArgumentParser(description="Servidor de Archivos Web en Python v2.0")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Host de escucha")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Puerto de escucha")
    parser.add_argument("--dir", default=os.environ.get("STORAGE_DIR", "./storage"), help="Directorio a compartir")
    parser.add_argument("--user", default=os.environ.get("AUTH_USER", "admin"), help="Usuario administrador inicial")
    parser.add_argument("--password", default=os.environ.get("AUTH_PASS", "admin123"), help="Contraseña inicial")
    parser.add_argument("--ssl-cert", default=os.environ.get("SSL_CERT", ""), help="Ruta al certificado SSL (.crt/.pem)")
    parser.add_argument("--ssl-key", default=os.environ.get("SSL_KEY", ""), help="Ruta a la llave privada SSL (.key)")
    parser.add_argument("--no-auth", action="store_true", help="Deshabilitar la autenticación")
    return parser.parse_args()


def main():
    args = parse_args()
    secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    config = ServerConfig(
        host=args.host,
        port=args.port,
        storage_dir=Path(args.dir),
        username=args.user,
        password=args.password,
        secret_key=secret_key,
        auth_enabled=not args.no_auth,
    )

    FileServerHandler.config = config
    server = ThreadingHTTPServer((config.host, config.port), FileServerHandler)

    protocol = "http"
    if args.ssl_cert and args.ssl_key and Path(args.ssl_cert).is_file() and Path(args.ssl_key).is_file():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=args.ssl_cert, keyfile=args.ssl_key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        protocol = "https"

    local_ip = get_local_ip()
    print("=" * 64)
    print("  🚀 PYTHON FILE SERVER v2.0 (ENTERPRISE EDITION) INICIADO")
    print("=" * 64)
    print(f"  📁 Directorio : {config.storage_dir}")
    print(f"  🌐 Local      : {protocol}://localhost:{config.port}")
    print(f"  📡 Red Local  : {protocol}://{local_ip}:{config.port}")
    if config.auth_enabled:
        print(f"  🔐 Admin User : {args.user}")
    else:
        print("  🔓 Autenticación deshabilitada (--no-auth)")
    print("=" * 64)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor...")
        server.server_close()


if __name__ == "__main__":
    main()
