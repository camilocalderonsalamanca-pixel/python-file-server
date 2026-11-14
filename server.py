#!/usr/bin/env python3
"""
Python Modern File Server
Servidor de archivos web moderno y autónomo en Python (sin dependencias externas).
Incluye:
- Interfaz web moderna con Drag & Drop y modo oscuro/claro
- Navegación por carpetas y creación de directorios
- Subida y descarga de archivos (streaming por bloques) y carpetas como ZIP
- Renombrado y eliminación de archivos/carpetas
- Vista previa de archivos (imágenes, texto, audio, video, PDF)
- Autenticación (sesión web + HTTP Basic Auth para clientes CLI como curl)
"""

import argparse
import base64
import datetime
import hmac
import hashlib
import http.cookies
import io
import json
import mimetypes
import os
import secrets
import shutil
import socket
import stat
import sys
import tempfile
import time
import urllib.parse
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def load_dotenv(dotenv_path: Path):
    """Carga variables desde un archivo .env si existe."""
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


class ServerConfig:
    def __init__(self, host: str, port: int, storage_dir: Path, username: str, password: str, secret_key: str, auth_enabled: bool = True):
        self.host = host
        self.port = port
        self.storage_dir = storage_dir.resolve()
        self.username = username
        self.password = password
        self.secret_key = secret_key.encode("utf-8")
        self.auth_enabled = auth_enabled
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_session_token(self, username: str) -> str:
        timestamp = str(int(time.time()))
        payload = f"{username}:{timestamp}"
        sig = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def verify_session_token(self, token: str, max_age: int = 86400 * 7) -> bool:
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return False
            username, timestamp_str, sig = parts
            payload = f"{username}:{timestamp_str}"
            expected_sig = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return False
            if not hmac.compare_digest(username, self.username):
                return False
            if int(time.time()) - int(timestamp_str) > max_age:
                return False
            return True
        except Exception:
            return False


class FileServerHandler(BaseHTTPRequestHandler):
    config: ServerConfig = None  # Se asigna al iniciar el servidor
    static_dir: Path = Path(__file__).parent / "static"
    templates_dir: Path = Path(__file__).parent / "templates"

    def log_message(self, format_str, *args):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout.write(f"[{timestamp}] {self.address_string()} - {format_str % args}\n")

    # --- Helpers de respuesta ---

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

    # --- Helpers de Autenticación ---

    def is_authenticated(self) -> bool:
        if not self.config.auth_enabled:
            return True

        # 1. Revisar cookie de sesión
        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookies = http.cookies.SimpleCookie()
            try:
                cookies.load(cookie_header)
                if "fs_session" in cookies:
                    token = cookies["fs_session"].value
                    if self.config.verify_session_token(token):
                        return True
            except Exception:
                pass

        # 2. Revisar HTTP Basic Auth (para herramientas CLI o integraciones)
        auth_header = self.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                encoded = auth_header.split(" ", 1)[1].strip()
                decoded = base64.b64decode(encoded).decode("utf-8")
                if ":" in decoded:
                    user, pw = decoded.split(":", 1)
                    user_ok = hmac.compare_digest(user, self.config.username)
                    pass_ok = hmac.compare_digest(pw, self.config.password)
                    if user_ok and pass_ok:
                        return True
            except Exception:
                pass

        return False

    # --- Helpers de Seguridad de Rutas ---

    def resolve_storage_path(self, rel_path: str) -> Path:
        """
        Resuelve una ruta relativa dentro de storage_dir previniendo Path Traversal.
        Lanza PermissionError si la ruta intenta salir de storage_dir.
        """
        cleaned = (rel_path or "").strip().lstrip("/").lstrip("\\")
        target = (self.config.storage_dir / cleaned).resolve()
        base = self.config.storage_dir.resolve()
        if target != base and base not in target.parents:
            raise PermissionError("Acceso denegado: ruta fuera del directorio permitido.")
        return target

    def sanitize_filename(self, name: str) -> str:
        """Limpia un nombre de archivo o carpeta para evitar caracteres inválidos."""
        name = os.path.basename(name.strip().replace("\\", "/"))
        if name in ("", ".", ".."):
            raise ValueError("Nombre de archivo o carpeta inválido.")
        return name

    # --- Métodos HTTP ---

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Archivos estáticos (CSS, JS, iconos)
        if route.startswith("/static/"):
            self.handle_static(route[len("/static/"):])
            return

        # Página de Login
        if route == "/login":
            if self.is_authenticated():
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.send_html_file("login.html")
            return

        # Estado de sesión
        if route == "/api/auth/status":
            self.send_json({
                "authenticated": self.is_authenticated(),
                "auth_enabled": self.config.auth_enabled,
                "username": self.config.username if self.is_authenticated() else None
            })
            return

        # Verificar autenticación para el resto de rutas
        if not self.is_authenticated():
            if route.startswith("/api/"):
                self.send_json({"error": "No autorizado. Inicia sesión primero."}, status=HTTPStatus.UNAUTHORIZED)
            else:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/login")
                self.end_headers()
            return

        # Rutas protegidas
        if route == "/":
            self.send_html_file("index.html")
        elif route == "/api/files":
            rel_path = query.get("path", [""])[0]
            search_q = query.get("search", [""])[0].strip()
            self.handle_list_files(rel_path, search_q)
        elif route == "/api/download":
            rel_path = query.get("path", [""])[0]
            inline = query.get("inline", ["0"])[0] == "1"
            self.handle_download(rel_path, inline=inline)
        elif route == "/api/zip":
            rel_path = query.get("path", [""])[0]
            self.handle_download_zip(rel_path)
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

        if not self.is_authenticated():
            self.send_json({"error": "No autorizado. Inicia sesión primero."}, status=HTTPStatus.UNAUTHORIZED)
            return

        if route == "/api/mkdir":
            self.handle_mkdir()
        elif route == "/api/rename":
            self.handle_rename()
        elif route == "/api/delete":
            self.handle_delete()
        elif route == "/api/upload":
            self.handle_upload(query)
        else:
            self.send_json({"error": "Ruta no encontrada"}, status=HTTPStatus.NOT_FOUND)

    # --- Controladores ---

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
        try:
            body = self.read_json_body()
            username = body.get("username", "")
            password = body.get("password", "")

            user_ok = hmac.compare_digest(username, self.config.username)
            pass_ok = hmac.compare_digest(password, self.config.password)

            if user_ok and pass_ok:
                token = self.config.create_session_token(username)
                cookie = f"fs_session={token}; HttpOnly; Path=/; Max-Age={86400 * 7}; SameSite=Lax"
                self.send_json({"ok": True, "username": username}, extra_headers={"Set-Cookie": cookie})
            else:
                self.send_json({"error": "Usuario o contraseña incorrectos."}, status=HTTPStatus.UNAUTHORIZED)
        except Exception as e:
            self.send_json({"error": f"Error en solicitud de login: {e}"}, status=HTTPStatus.BAD_REQUEST)

    def handle_logout(self):
        cookie = "fs_session=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax"
        self.send_json({"ok": True}, extra_headers={"Set-Cookie": cookie})

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
                    # Omitir archivos ocultos del sistema como .gitkeep
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    root_path = Path(root)
                    for d in dirs:
                        if q_lower in d.lower():
                            items.append(self.get_file_info(root_path / d))
                    for f in files:
                        if f == ".gitkeep":
                            continue
                        if q_lower in f.lower():
                            items.append(self.get_file_info(root_path / f))
            else:
                for entry in target_dir.iterdir():
                    if entry.name == ".gitkeep":
                        continue
                    items.append(self.get_file_info(entry))

            # Ordenar: carpetas primero, luego alfabéticamente
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

            # Estadísticas de disco
            usage = shutil.disk_usage(self.config.storage_dir)
            current_rel = "" if target_dir == self.config.storage_dir else target_dir.relative_to(self.config.storage_dir).as_posix()

            self.send_json({
                "current_path": current_rel,
                "items": items,
                "disk": {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free
                }
            })
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"Error al listar archivos: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_mkdir(self):
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
            self.send_json({"ok": True, "item": self.get_file_info(new_dir)}, status=HTTPStatus.CREATED)
        except ValueError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"No se pudo crear la carpeta: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_rename(self):
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
            self.send_json({"ok": True, "item": self.get_file_info(dest)})
        except ValueError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"No se pudo renombrar: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_delete(self):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "")

            target = self.resolve_storage_path(rel_path)
            if target == self.config.storage_dir:
                self.send_json({"error": "No se puede eliminar el directorio raíz."}, status=HTTPStatus.BAD_REQUEST)
                return
            if not target.exists():
                self.send_json({"error": "El archivo o carpeta no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

            self.send_json({"ok": True})
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"No se pudo eliminar: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_upload(self, query: dict):
        """
        Soporta subida directa por streaming:
        POST /api/upload?path=carpeta&filename=archivo.ext
        Con el contenido binario del archivo en el cuerpo de la petición (application/octet-stream).
        Permite archivos grandes sin cargar todo en RAM.
        """
        try:
            rel_dir = query.get("path", [""])[0]
            raw_filename = self.headers.get("X-File-Name")
            if raw_filename:
                raw_filename = urllib.parse.unquote(raw_filename)
            else:
                raw_filename = query.get("filename", [""])[0]

            # Soportar rutas relativas cuando se arrastran carpetas completas (ej. "subcarpeta/archivo.txt")
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

            # Si el archivo ya existe y no se pide sobrescribir, añadir sufijo único
            overwrite = query.get("overwrite", ["1"])[0] == "1"
            if dest_path.exists() and dest_path.is_dir():
                self.send_json({"error": "Existe una carpeta con el mismo nombre."}, status=HTTPStatus.CONFLICT)
                return
            if dest_path.exists() and not overwrite:
                stem = dest_path.stem
                suffix = dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = dest_path.parent / f"{stem} ({counter}){suffix}"
                    counter += 1

            content_length = int(self.headers.get("Content-Length", 0))
            remaining = content_length
            chunk_size = 64 * 1024  # 64 KB

            with open(dest_path, "wb") as f:
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    chunk = self.rfile.read(read_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            self.send_json({"ok": True, "item": self.get_file_info(dest_path)}, status=HTTPStatus.CREATED)
        except ValueError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
        except PermissionError as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.FORBIDDEN)
        except Exception as e:
            self.send_json({"error": f"Error al subir archivo: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_download(self, rel_path: str, inline: bool = False):
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

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
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

    def handle_download_zip(self, rel_path: str):
        """Comprime y descarga una carpeta completa en formato .zip."""
        try:
            target_dir = self.resolve_storage_path(rel_path)
            if not target_dir.exists() or not target_dir.is_dir():
                self.send_json({"error": "Carpeta no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return

            zip_name = f"{target_dir.name or 'storage'}.zip"
            encoded_name = urllib.parse.quote(zip_name)

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(target_dir):
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
    parser = argparse.ArgumentParser(description="Servidor de Archivos Web en Python")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Host de escucha (por defecto: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Puerto de escucha (por defecto: 8000)")
    parser.add_argument("--dir", default=os.environ.get("STORAGE_DIR", "./storage"), help="Directorio a compartir (por defecto: ./storage)")
    parser.add_argument("--user", default=os.environ.get("AUTH_USER", "admin"), help="Usuario para autenticación (por defecto: admin)")
    parser.add_argument("--password", default=os.environ.get("AUTH_PASS", "admin123"), help="Contraseña para autenticación (por defecto: admin123)")
    parser.add_argument("--no-auth", action="store_true", help="Deshabilitar la autenticación por usuario/contraseña")
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

    local_ip = get_local_ip()
    print("=" * 60)
    print("  🚀 PYTHON FILE SERVER INICIADO")
    print("=" * 60)
    print(f"  📁 Directorio : {config.storage_dir}")
    print(f"  🌐 Local      : http://localhost:{config.port}")
    print(f"  📡 Red Local  : http://{local_ip}:{config.port}")
    if config.auth_enabled:
        print(f"  🔐 Usuario    : {config.username}")
        print(f"  🔑 Contraseña : {config.password}")
    else:
        print("  🔓 Autenticación deshabilitada (--no-auth)")
    print("=" * 60)
    print("  Presiona Ctrl+C para detener el servidor.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor...")
        server.server_close()


if __name__ == "__main__":
    main()
