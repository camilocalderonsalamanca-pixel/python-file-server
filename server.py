#!/usr/bin/env python3
"""
Python Modern File Server v3.0 (Enterprise Edition — ICFD)
Servidor de archivos web moderno y autónomo en Python (100% librería estándar).
Incluye:
1. Enlaces públicos para compartir archivos/carpetas (con expiración, límite de descargas y contraseña opcional)
2. Sistema Multi-usuario con Roles (admin, editor, viewer) en SQLite
3. Papelera de reciclaje (.trash) con restauración y vaciado
4. Operaciones masivas (selección múltiple: eliminar, mover, comprimir ZIP), extracción de archivos (.zip/.tar.gz) y editor de texto/código integrado
5. Vista de Cuadrícula (Grid View), Visor PDF integrado y Streaming de Video/Audio con soporte HTTP Range (206 Partial Content)
6. Seguridad avanzada: Rate Limiting contra fuerza bruta, Registro de Auditoría (Audit Logs) y soporte HTTPS/SSL nativo
7. Historial de Versiones (.versions) automático al sobrescribir o editar archivos, con descarga y restauración
8. Etiquetas Institucionales, Notas/Observaciones y Favoritos (⭐) por usuario
9. Visor integrado de Excel (.xlsx, .csv, .tsv) y Word (.docx) 100% autónomo sin depender de internet
10. Ordenamiento por columnas, Menú Contextual (clic derecho) y Dashboard de Estadísticas de Almacenamiento
11. Carpetas Privadas / Restringidas por Rol o por Usuario específico (ACL con herencia de subcarpetas)
"""

import argparse
import base64
import csv
import datetime
import hashlib
import hmac
import http.cookies
import io
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
import xml.etree.ElementTree as ET
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


def parse_xlsx_preview(file_path: Path, max_rows: int = 300) -> dict:
    """Extrae hojas y celdas de un archivo .xlsx usando sólo la librería estándar de Python."""
    sheets_out = []
    with zipfile.ZipFile(file_path, "r") as zf:
        namelist = set(zf.namelist())
        shared_strings = []
        if "xl/sharedStrings.xml" in namelist:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.iter():
                if si.tag.endswith("}si") or si.tag == "si":
                    texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                    shared_strings.append("".join(texts))

        # Mapear nombres de hojas y sus rutas
        sheet_Defs = []
        rels_map = {}
        if "xl/_rels/workbook.xml.rels" in namelist:
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            for rel in rels_root.iter():
                if rel.tag.endswith("}Relationship") or rel.tag == "Relationship":
                    r_id = rel.attrib.get("Id", "")
                    target = rel.attrib.get("Target", "").lstrip("/")
                    if not target.startswith("xl/"):
                        target = f"xl/{target}"
                    rels_map[r_id] = target

        if "xl/workbook.xml" in namelist:
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            for sh in wb_root.iter():
                if sh.tag.endswith("}sheet") or sh.tag == "sheet":
                    name = sh.attrib.get("name", "Hoja")
                    r_id = None
                    for k, v in sh.attrib.items():
                        if k.endswith("}id") or k == "r:id":
                            r_id = v
                            break
                    target = rels_map.get(r_id, "")
                    if target in namelist:
                        sheet_Defs.append((name, target))

        if not sheet_Defs:
            for n in sorted(namelist):
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"):
                    sheet_Defs.append((Path(n).stem.capitalize(), n))

        def col_to_idx(col_str: str) -> int:
            idx = 0
            for ch in col_str:
                if "A" <= ch <= "Z":
                    idx = idx * 26 + (ord(ch) - ord("A") + 1)
            return max(0, idx - 1)

        for sheet_name, sheet_xml_path in sheet_Defs[:10]:
            sh_root = ET.fromstring(zf.read(sheet_xml_path))
            rows_data = []
            max_col = 0
            for row_el in sh_root.iter():
                if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                    continue
                if len(rows_data) >= max_rows:
                    break
                row_dict = {}
                for c_el in row_el:
                    if not (c_el.tag.endswith("}c") or c_el.tag == "c"):
                        continue
                    ref = c_el.attrib.get("r", "")
                    col_letters = "".join(ch for ch in ref if ch.isalpha())
                    c_idx = col_to_idx(col_letters) if col_letters else len(row_dict)
                    c_type = c_el.attrib.get("t", "")
                    val_str = ""
                    if c_type == "inlineStr":
                        texts = [t.text or "" for t in c_el.iter() if t.tag.endswith("}t") or t.tag == "t"]
                        val_str = "".join(texts)
                    else:
                        v_el = next((ch for ch in c_el if ch.tag.endswith("}v") or ch.tag == "v"), None)
                        raw_v = v_el.text if (v_el is not None and v_el.text is not None) else ""
                        if c_type == "s":
                            try:
                                s_idx = int(raw_v)
                                val_str = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else raw_v
                            except Exception:
                                val_str = raw_v
                        elif c_type == "b":
                            val_str = "VERDADERO" if raw_v == "1" else "FALSO"
                        else:
                            val_str = raw_v
                    row_dict[c_idx] = val_str
                    if c_idx + 1 > max_col:
                        max_col = min(c_idx + 1, 50)
                if row_dict:
                    rows_data.append(row_dict)

            matrix = []
            for r_dict in rows_data:
                matrix.append([r_dict.get(i, "") for i in range(max_col)])
            sheets_out.append({"name": sheet_name, "rows": matrix})

    return {"type": "spreadsheet", "sheets": sheets_out}


def parse_csv_preview(file_path: Path, max_rows: int = 300) -> dict:
    """Extrae filas de un archivo .csv o .tsv con detección automática de delimitador."""
    raw_bytes = file_path.read_bytes()[:512 * 1024]
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1", errors="replace")

    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        if "\t" in sample:
            delimiter = "\t"
        elif ";" in sample:
            delimiter = ";"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for idx, row in enumerate(reader):
        if idx >= max_rows:
            break
        rows.append(row[:50])
    return {"type": "spreadsheet", "sheets": [{"name": file_path.name, "rows": rows}]}


def parse_docx_preview(file_path: Path) -> dict:
    """Extrae párrafos, encabezados y tablas de un documento Word (.docx) usando librería estándar."""
    blocks = []
    with zipfile.ZipFile(file_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("El archivo .docx no contiene word/document.xml")
        root = ET.fromstring(zf.read("word/document.xml"))
        body = next((el for el in root.iter() if el.tag.endswith("}body") or el.tag == "body"), root)

        for child in body:
            tag = child.tag.split("}")[-1]
            if tag == "p":
                style_val = ""
                for ppr in child:
                    if ppr.tag.endswith("}pPr") or ppr.tag == "pPr":
                        for st in ppr:
                            if st.tag.endswith("}pStyle") or st.tag == "pStyle":
                                for k, v in st.attrib.items():
                                    if k.endswith("}val") or k == "val":
                                        style_val = v.lower()
                texts = [t.text or "" for t in child.iter() if t.tag.endswith("}t") or t.tag == "t"]
                full_text = "".join(texts).strip()
                if full_text:
                    level = "p"
                    if "heading1" in style_val or "titulo1" in style_val or style_val == "title":
                        level = "h1"
                    elif "heading2" in style_val or "titulo2" in style_val:
                        level = "h2"
                    elif "heading3" in style_val or "titulo3" in style_val:
                        level = "h3"
                    blocks.append({"type": level, "text": full_text})
            elif tag == "tbl":
                table_rows = []
                for tr in child:
                    if not (tr.tag.endswith("}tr") or tr.tag == "tr"):
                        continue
                    row_cells = []
                    for tc in tr:
                        if not (tc.tag.endswith("}tc") or tc.tag == "tc"):
                            continue
                        cell_texts = [t.text or "" for t in tc.iter() if t.tag.endswith("}t") or t.tag == "t"]
                        row_cells.append(" ".join("".join(cell_texts).split()))
                    if row_cells:
                        table_rows.append(row_cells)
                if table_rows:
                    blocks.append({"type": "table", "rows": table_rows})

    return {"type": "document", "blocks": blocks}


class DatabaseManager:
    """Gestiona usuarios, enlaces compartidos, papelera, versiones, metadatos, favoritos, permisos y auditoría en SQLite."""

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
                CREATE TABLE IF NOT EXISTS file_versions (
                    id TEXT PRIMARY KEY,
                    rel_path TEXT NOT NULL,
                    version_file TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    comment TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_versions_path ON file_versions(rel_path);
                CREATE TABLE IF NOT EXISTS file_metadata (
                    rel_path TEXT PRIMARY KEY,
                    tags TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    updated_by TEXT,
                    updated_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS user_favorites (
                    username TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (username, rel_path)
                );
                CREATE TABLE IF NOT EXISTS folder_permissions (
                    rel_path TEXT PRIMARY KEY,
                    is_restricted INTEGER NOT NULL DEFAULT 0,
                    allowed_roles TEXT NOT NULL DEFAULT '["admin"]',
                    allowed_users TEXT NOT NULL DEFAULT '[]',
                    updated_by TEXT,
                    updated_at INTEGER
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
            conn.execute("DELETE FROM user_favorites WHERE username = ?", (username,))
            conn.commit()

    # --- Historial de Versiones ---
    def add_version(self, version_id: str, rel_path: str, version_file: str, size: int, created_by: str, comment: str = ""):
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO file_versions (id, rel_path, version_file, size, created_by, created_at, comment) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, rel_path, version_file, size, created_by, int(time.time()), comment),
            )
            conn.commit()

    def list_versions(self, rel_path: str) -> list:
        with self.lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM file_versions WHERE rel_path = ? ORDER BY created_at DESC",
                (rel_path,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_version(self, version_id: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM file_versions WHERE id = ?", (version_id,)).fetchone()
            return dict(row) if row else None

    def delete_version(self, version_id: str):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM file_versions WHERE id = ?", (version_id,))
            conn.commit()

    def get_version_counts_map(self) -> dict:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT rel_path, COUNT(*) as cnt FROM file_versions GROUP BY rel_path").fetchall()
            return {r["rel_path"]: r["cnt"] for r in rows}

    # --- Etiquetas, Notas y Favoritos ---
    def get_metadata_map(self) -> dict:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM file_metadata").fetchall()
            result = {}
            for r in rows:
                try:
                    tags = json.loads(r["tags"] or "[]")
                except Exception:
                    tags = []
                result[r["rel_path"]] = {
                    "tags": tags,
                    "note": r["note"] or "",
                    "updated_by": r["updated_by"],
                    "updated_at": r["updated_at"],
                }
            return result

    def save_metadata(self, rel_path: str, tags: list, note: str, username: str):
        clean_tags = []
        for t in tags:
            s = str(t).strip()
            if s and s not in clean_tags:
                clean_tags.append(s)
        clean_note = (note or "").strip()
        with self.lock, self._connect() as conn:
            if not clean_tags and not clean_note:
                conn.execute("DELETE FROM file_metadata WHERE rel_path = ?", (rel_path,))
            else:
                conn.execute(
                    """
                    INSERT INTO file_metadata (rel_path, tags, note, updated_by, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(rel_path) DO UPDATE SET
                        tags = excluded.tags,
                        note = excluded.note,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (rel_path, json.dumps(clean_tags, ensure_ascii=False), clean_note, username, int(time.time())),
                )
            conn.commit()
        return {"tags": clean_tags, "note": clean_note}

    def get_user_favorites_set(self, username: str) -> set:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT rel_path FROM user_favorites WHERE username = ?", (username,)).fetchall()
            return {r["rel_path"] for r in rows}

    def toggle_favorite(self, username: str, rel_path: str) -> bool:
        with self.lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM user_favorites WHERE username = ? AND rel_path = ?",
                (username, rel_path),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM user_favorites WHERE username = ? AND rel_path = ?", (username, rel_path))
                conn.commit()
                return False
            else:
                conn.execute(
                    "INSERT INTO user_favorites (username, rel_path, created_at) VALUES (?, ?, ?)",
                    (username, rel_path, int(time.time())),
                )
                conn.commit()
                return True

    # --- Permisos por Carpeta (ACL) ---
    def get_folder_permissions_map(self) -> dict:
        with self.lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM folder_permissions WHERE is_restricted = 1").fetchall()
            result = {}
            for r in rows:
                try:
                    roles = json.loads(r["allowed_roles"] or '["admin"]')
                except Exception:
                    roles = ["admin"]
                try:
                    users = json.loads(r["allowed_users"] or "[]")
                except Exception:
                    users = []
                result[r["rel_path"]] = {
                    "is_restricted": bool(r["is_restricted"]),
                    "allowed_roles": roles,
                    "allowed_users": users,
                    "updated_by": r["updated_by"],
                    "updated_at": r["updated_at"],
                }
            return result

    def get_folder_permission(self, rel_path: str) -> dict:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM folder_permissions WHERE rel_path = ?", (rel_path,)).fetchone()
            if not row:
                return {"rel_path": rel_path, "is_restricted": False, "allowed_roles": ["admin", "editor", "viewer"], "allowed_users": []}
            try:
                roles = json.loads(row["allowed_roles"] or '["admin"]')
            except Exception:
                roles = ["admin"]
            try:
                users = json.loads(row["allowed_users"] or "[]")
            except Exception:
                users = []
            return {
                "rel_path": rel_path,
                "is_restricted": bool(row["is_restricted"]),
                "allowed_roles": roles,
                "allowed_users": users,
            }

    def save_folder_permission(self, rel_path: str, is_restricted: bool, allowed_roles: list, allowed_users: list, username: str):
        roles = list({str(r).strip() for r in (allowed_roles or []) if str(r).strip()} | {"admin"})
        users = list({str(u).strip() for u in (allowed_users or []) if str(u).strip()})
        with self.lock, self._connect() as conn:
            if not is_restricted:
                conn.execute("DELETE FROM folder_permissions WHERE rel_path = ?", (rel_path,))
            else:
                conn.execute(
                    """
                    INSERT INTO folder_permissions (rel_path, is_restricted, allowed_roles, allowed_users, updated_by, updated_at)
                    VALUES (?, 1, ?, ?, ?, ?)
                    ON CONFLICT(rel_path) DO UPDATE SET
                        is_restricted = 1,
                        allowed_roles = excluded.allowed_roles,
                        allowed_users = excluded.allowed_users,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (rel_path, json.dumps(roles), json.dumps(users), username, int(time.time())),
                )
            conn.commit()

    def relocate_path_records(self, old_rel: str, new_rel: str):
        """Actualiza metadatos, favoritos, permisos y versiones cuando se renombra o mueve un archivo/carpeta."""
        with self.lock, self._connect() as conn:
            for table in ("file_metadata", "user_favorites", "folder_permissions", "file_versions"):
                conn.execute(f"UPDATE OR IGNORE {table} SET rel_path = ? WHERE rel_path = ?", (new_rel, old_rel))
                prefix = f"{old_rel}/"
                rows = conn.execute(f"SELECT rowid, rel_path FROM {table} WHERE rel_path LIKE ?", (f"{prefix}%",)).fetchall()
                for r in rows:
                    sub = new_rel + r["rel_path"][len(old_rel):]
                    conn.execute(f"UPDATE OR IGNORE {table} SET rel_path = ? WHERE rowid = ?", (sub, r["rowid"]))
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
        self.versions_dir = self.storage_dir / ".versions"
        self.secret_key = secret_key.encode("utf-8")
        self.auth_enabled = auth_enabled
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
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

    def can_access_path(self, user: dict, rel_path: str, perms_map: dict = None) -> bool:
        """Verifica permisos de carpeta (incluyendo herencia de carpetas padre)."""
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        cleaned = (rel_path or "").strip().strip("/")
        if not cleaned:
            return True
        if perms_map is None:
            perms_map = self.config.db.get_folder_permissions_map()
        if not perms_map:
            return True

        parts = cleaned.split("/")
        acc = ""
        for p in parts:
            acc = f"{acc}/{p}" if acc else p
            rule = perms_map.get(acc)
            if rule and rule.get("is_restricted"):
                allowed_roles = rule.get("allowed_roles") or []
                allowed_users = rule.get("allowed_users") or []
                if user.get("role") not in allowed_roles and user.get("username") not in allowed_users:
                    return False
        return True

    # --- Seguridad de Rutas ---
    def resolve_storage_path(self, rel_path: str) -> Path:
        cleaned = (rel_path or "").strip().lstrip("/").lstrip("\\")
        target = (self.config.storage_dir / cleaned).resolve()
        base = self.config.storage_dir.resolve()
        if target != base and base not in target.parents:
            raise PermissionError("Acceso denegado: ruta fuera del directorio permitido.")
        if target == self.config.trash_dir or self.config.trash_dir in target.parents:
            raise PermissionError("Acceso directo a la papelera no permitido.")
        if target == self.config.versions_dir or self.config.versions_dir in target.parents:
            raise PermissionError("Acceso directo al almacén de versiones no permitido.")
        return target

    def sanitize_filename(self, name: str) -> str:
        name = os.path.basename(name.strip().replace("\\", "/"))
        if name in ("", ".", "..", ".trash", ".versions", ".gitkeep"):
            raise ValueError("Nombre de archivo o carpeta inválido.")
        return name

    # --- Historial de Versiones Interno ---
    def _archive_file_version(self, target_file: Path, username: str, comment: str = ""):
        if not target_file.exists() or not target_file.is_file():
            return
        rel_path = target_file.relative_to(self.config.storage_dir).as_posix()
        version_id = f"v_{int(time.time())}_{secrets.token_hex(4)}"
        ver_filename = f"{version_id}__{target_file.name}"
        ver_dest = self.config.versions_dir / ver_filename
        shutil.copy2(str(target_file), str(ver_dest))
        size = ver_dest.stat().st_size
        self.config.db.add_version(version_id, rel_path, ver_filename, size, username, comment)

    # --- Enrutamiento HTTP ---
    def do_HEAD(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

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
            fav_only = query.get("favorites", ["0"])[0] == "1"
            tag_filter = query.get("tag", [""])[0].strip()
            self.handle_list_files(rel_path, search_q, user, fav_only, tag_filter)
        elif route == "/api/download":
            rel_path = query.get("path", [""])[0]
            inline = query.get("inline", ["0"])[0] == "1"
            self.handle_download(rel_path, inline=inline, user=user)
        elif route == "/api/zip":
            rel_path = query.get("path", [""])[0]
            self.handle_download_zip(rel_path, user=user)
        elif route == "/api/office-preview":
            rel_path = query.get("path", [""])[0]
            self.handle_office_preview(rel_path, user)
        elif route == "/api/versions":
            rel_path = query.get("path", [""])[0]
            self.handle_list_versions(rel_path, user)
        elif route == "/api/versions/download":
            ver_id = query.get("id", [""])[0]
            self.handle_download_version(ver_id, user)
        elif route == "/api/permissions":
            if self.require_role(user, ("admin",)):
                rel_path = query.get("path", [""])[0]
                self.handle_get_permissions(rel_path)
        elif route == "/api/stats":
            self.handle_stats(user)
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
        elif route == "/api/favorites/toggle":
            self.handle_favorite_toggle(user)
        elif route == "/api/metadata/save":
            if self.require_role(user, ("admin", "editor")):
                self.handle_metadata_save(user)
        elif route == "/api/versions/restore":
            if self.require_role(user, ("admin", "editor")):
                self.handle_restore_version(user)
        elif route == "/api/versions/delete":
            if self.require_role(user, ("admin", "editor")):
                self.handle_delete_version(user)
        elif route == "/api/permissions/save":
            if self.require_role(user, ("admin",)):
                self.handle_save_permissions(user)
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
    def get_file_info(self, item: Path, meta_map: dict = None, fav_set: set = None, ver_map: dict = None, perms_map: dict = None) -> dict:
        st = item.stat()
        is_dir = stat.S_ISDIR(st.st_mode)
        rel = item.relative_to(self.config.storage_dir).as_posix()
        mime, _ = mimetypes.guess_type(item.name) if not is_dir else (None, None)
        meta = (meta_map or {}).get(rel, {})
        perm = (perms_map or {}).get(rel, {})
        return {
            "name": item.name,
            "path": rel,
            "is_dir": is_dir,
            "size": 0 if is_dir else st.st_size,
            "mtime": int(st.st_mtime),
            "mime": mime or ("inode/directory" if is_dir else "application/octet-stream"),
            "is_favorite": rel in (fav_set or set()),
            "tags": meta.get("tags", []),
            "note": meta.get("note", ""),
            "versions_count": 0 if is_dir else (ver_map or {}).get(rel, 0),
            "is_restricted": bool(perm.get("is_restricted", False)) if is_dir else False,
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

    def handle_list_files(self, rel_path: str, search_query: str, user: dict, fav_only: bool = False, tag_filter: str = ""):
        try:
            perms_map = self.config.db.get_folder_permissions_map()
            if not self.can_access_path(user, rel_path, perms_map):
                self.send_json({"error": "No tienes permiso para acceder a esta carpeta privada."}, status=HTTPStatus.FORBIDDEN)
                return

            target_dir = self.resolve_storage_path(rel_path)
            if not target_dir.exists():
                self.send_json({"error": "El directorio no existe."}, status=HTTPStatus.NOT_FOUND)
                return
            if not target_dir.is_dir():
                self.send_json({"error": "La ruta especificada no es un directorio."}, status=HTTPStatus.BAD_REQUEST)
                return

            meta_map = self.config.db.get_metadata_map()
            fav_set = self.config.db.get_user_favorites_set(user["username"])
            ver_map = self.config.db.get_version_counts_map()

            items = []
            deep_scan = bool(search_query or fav_only or tag_filter)
            if deep_scan:
                q_lower = search_query.lower()
                scan_base = self.config.storage_dir if (fav_only or tag_filter) and not rel_path else target_dir
                for root, dirs, files in os.walk(scan_base):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    root_path = Path(root)
                    for d in list(dirs):
                        d_path = root_path / d
                        d_rel = d_path.relative_to(self.config.storage_dir).as_posix()
                        if not self.can_access_path(user, d_rel, perms_map):
                            dirs.remove(d)
                            continue
                        info = self.get_file_info(d_path, meta_map, fav_set, ver_map, perms_map)
                        if q_lower and q_lower not in d.lower() and q_lower not in info["note"].lower() and not any(q_lower in t.lower() for t in info["tags"]):
                            continue
                        if fav_only and not info["is_favorite"]:
                            continue
                        if tag_filter and tag_filter not in info["tags"]:
                            continue
                        items.append(info)
                    for f in files:
                        if f in (".gitkeep",):
                            continue
                        f_path = root_path / f
                        f_rel = f_path.relative_to(self.config.storage_dir).as_posix()
                        if not self.can_access_path(user, f_rel, perms_map):
                            continue
                        info = self.get_file_info(f_path, meta_map, fav_set, ver_map, perms_map)
                        if q_lower and q_lower not in f.lower() and q_lower not in info["note"].lower() and not any(q_lower in t.lower() for t in info["tags"]):
                            continue
                        if fav_only and not info["is_favorite"]:
                            continue
                        if tag_filter and tag_filter not in info["tags"]:
                            continue
                        items.append(info)
            else:
                for entry in target_dir.iterdir():
                    if entry.name.startswith(".") or entry.name in (".gitkeep", ".trash", ".versions"):
                        continue
                    e_rel = entry.relative_to(self.config.storage_dir).as_posix()
                    if not self.can_access_path(user, e_rel, perms_map):
                        continue
                    items.append(self.get_file_info(entry, meta_map, fav_set, ver_map, perms_map))

            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            usage = shutil.disk_usage(self.config.storage_dir)
            current_rel = "" if target_dir == self.config.storage_dir else target_dir.relative_to(self.config.storage_dir).as_posix()

            # Recopilar todas las etiquetas disponibles para filtros rápidos
            all_tags = sorted({t for m in meta_map.values() for t in m.get("tags", [])})

            self.send_json({
                "current_path": current_rel,
                "items": items,
                "all_tags": all_tags,
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
            if not self.can_access_path(user, parent_rel):
                self.send_json({"error": "No tienes acceso a esta carpeta."}, status=HTTPStatus.FORBIDDEN)
                return
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
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes acceso a este elemento."}, status=HTTPStatus.FORBIDDEN)
                return
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

            old_rel = target.relative_to(self.config.storage_dir).as_posix()
            target.rename(dest)
            new_rel = dest.relative_to(self.config.storage_dir).as_posix()
            self.config.db.relocate_path_records(old_rel, new_rel)
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
            if not self.can_access_path(user, rel_dir):
                self.send_json({"error": "No tienes permiso para subir archivos en esta carpeta."}, status=HTTPStatus.FORBIDDEN)
                return

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

            if dest_path.exists() and overwrite and dest_path.is_file():
                # Guardar versión histórica antes de sobrescribir
                self._archive_file_version(dest_path, user["username"], "Versión previa antes de subida")
            elif dest_path.exists() and not overwrite:
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
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes permiso para editar en esta ubicación."}, status=HTTPStatus.FORBIDDEN)
                return
            content = body.get("content", "")
            target = self.resolve_storage_path(rel_path)
            if target.is_dir():
                self.send_json({"error": "No se puede sobrescribir una carpeta como texto."}, status=HTTPStatus.BAD_REQUEST)
                return
            if target.exists() and target.is_file():
                self._archive_file_version(target, user["username"], "Versión previa a edición en línea")
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
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "Acceso denegado."}, status=HTTPStatus.FORBIDDEN)
                return
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

    # --- Visor Office (.xlsx, .csv, .tsv, .docx) ---
    def handle_office_preview(self, rel_path: str, user: dict):
        try:
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes permiso para ver este documento."}, status=HTTPStatus.FORBIDDEN)
                return
            target = self.resolve_storage_path(rel_path)
            if not target.is_file():
                self.send_json({"error": "Archivo no encontrado."}, status=HTTPStatus.NOT_FOUND)
                return
            ext = target.suffix.lower()
            if ext == ".xlsx":
                data = parse_xlsx_preview(target)
            elif ext in (".csv", ".tsv"):
                data = parse_csv_preview(target)
            elif ext == ".docx":
                data = parse_docx_preview(target)
            else:
                self.send_json({"error": "Formato Office no soportado para vista previa directa."}, status=HTTPStatus.BAD_REQUEST)
                return
            self.send_json({"ok": True, **data})
        except Exception as e:
            self.send_json({"error": f"No se pudo procesar la vista previa del documento: {e}"}, status=HTTPStatus.BAD_REQUEST)

    # --- Historial de Versiones (API) ---
    def handle_list_versions(self, rel_path: str, user: dict):
        try:
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "Acceso denegado."}, status=HTTPStatus.FORBIDDEN)
                return
            self.resolve_storage_path(rel_path)
            versions = self.config.db.list_versions(rel_path)
            self.send_json({"ok": True, "path": rel_path, "versions": versions})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    def handle_download_version(self, version_id: str, user: dict):
        try:
            ver = self.config.db.get_version(version_id)
            if not ver:
                self.send_json({"error": "Versión no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return
            if not self.can_access_path(user, ver["rel_path"]):
                self.send_json({"error": "Acceso denegado."}, status=HTTPStatus.FORBIDDEN)
                return
            ver_path = self.config.versions_dir / ver["version_file"]
            if not ver_path.is_file():
                self.send_json({"error": "El archivo físico de esta versión no existe."}, status=HTTPStatus.NOT_FOUND)
                return
            orig_name = os.path.basename(ver["rel_path"])
            ts_str = datetime.datetime.fromtimestamp(ver["created_at"]).strftime("%Y%m%d_%H%M%S")
            dl_name = urllib.parse.quote(f"{ts_str}_{orig_name}")
            size = ver_path.stat().st_size
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{dl_name}")
            self.end_headers()
            with open(ver_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, length=64 * 1024)
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_restore_version(self, user: dict):
        try:
            body = self.read_json_body()
            version_id = body.get("id", "")
            ver = self.config.db.get_version(version_id)
            if not ver:
                self.send_json({"error": "Versión no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return
            rel_path = ver["rel_path"]
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "Acceso denegado."}, status=HTTPStatus.FORBIDDEN)
                return
            ver_path = self.config.versions_dir / ver["version_file"]
            if not ver_path.is_file():
                self.send_json({"error": "El archivo físico de esta versión no existe."}, status=HTTPStatus.NOT_FOUND)
                return

            target = self.resolve_storage_path(rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.is_file():
                self._archive_file_version(target, user["username"], f"Respaldo automático antes de restaurar {version_id}")

            shutil.copy2(str(ver_path), str(target))
            self.config.db.log_audit(user["username"], self.get_client_ip(), "VERSION_RESTORE", rel_path, f"Versión: {version_id}")
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": f"No se pudo restaurar la versión: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_delete_version(self, user: dict):
        try:
            body = self.read_json_body()
            version_id = body.get("id", "")
            ver = self.config.db.get_version(version_id)
            if not ver:
                self.send_json({"error": "Versión no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return
            ver_path = self.config.versions_dir / ver["version_file"]
            if ver_path.is_file():
                ver_path.unlink()
            self.config.db.delete_version(version_id)
            self.config.db.log_audit(user["username"], self.get_client_ip(), "VERSION_DELETE", ver["rel_path"], f"Versión: {version_id}")
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    # --- Favoritos, Etiquetas y Notas (API) ---
    def handle_favorite_toggle(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "").strip().strip("/")
            if not rel_path:
                self.send_json({"error": "Ruta inválida."}, status=HTTPStatus.BAD_REQUEST)
                return
            self.resolve_storage_path(rel_path)
            is_fav = self.config.db.toggle_favorite(user["username"], rel_path)
            self.send_json({"ok": True, "path": rel_path, "is_favorite": is_fav})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    def handle_metadata_save(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = body.get("path", "").strip().strip("/")
            if not rel_path:
                self.send_json({"error": "Ruta inválida."}, status=HTTPStatus.BAD_REQUEST)
                return
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "Acceso denegado."}, status=HTTPStatus.FORBIDDEN)
                return
            self.resolve_storage_path(rel_path)
            tags = body.get("tags", [])
            note = body.get("note", "")
            saved = self.config.db.save_metadata(rel_path, tags, note, user["username"])
            self.config.db.log_audit(
                user["username"],
                self.get_client_ip(),
                "METADATA_SAVE",
                rel_path,
                f"Etiquetas: {', '.join(saved['tags']) or 'ninguna'}",
            )
            self.send_json({"ok": True, "path": rel_path, **saved})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    # --- Permisos de Carpeta (API) ---
    def handle_get_permissions(self, rel_path: str):
        try:
            cleaned = (rel_path or "").strip().strip("/")
            self.resolve_storage_path(cleaned)
            perm = self.config.db.get_folder_permission(cleaned)
            users = self.config.db.list_users()
            self.send_json({"ok": True, "permission": perm, "users": [u["username"] for u in users]})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    def handle_save_permissions(self, user: dict):
        try:
            body = self.read_json_body()
            rel_path = (body.get("path", "") or "").strip().strip("/")
            if not rel_path:
                self.send_json({"error": "No se puede restringir el directorio raíz completo."}, status=HTTPStatus.BAD_REQUEST)
                return
            target = self.resolve_storage_path(rel_path)
            if not target.is_dir():
                self.send_json({"error": "Los permisos de acceso solo se aplican a carpetas."}, status=HTTPStatus.BAD_REQUEST)
                return
            is_restricted = bool(body.get("is_restricted", False))
            allowed_roles = body.get("allowed_roles", ["admin"])
            allowed_users = body.get("allowed_users", [])
            self.config.db.save_folder_permission(rel_path, is_restricted, allowed_roles, allowed_users, user["username"])
            self.config.db.log_audit(
                user["username"],
                self.get_client_ip(),
                "FOLDER_ACL",
                rel_path,
                f"Restringida: {'Sí' if is_restricted else 'No'} | Roles: {','.join(allowed_roles)} | Usuarios: {','.join(allowed_users)}",
            )
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    # --- Dashboard de Estadísticas ---
    def handle_stats(self, user: dict):
        try:
            perms_map = self.config.db.get_folder_permissions_map()
            categories = {
                "documents": {"label": "Documentos y Office", "bytes": 0, "count": 0},
                "images": {"label": "Imágenes y Diseño", "bytes": 0, "count": 0},
                "videos": {"label": "Videos Multimedia", "bytes": 0, "count": 0},
                "audio": {"label": "Audio y Grabaciones", "bytes": 0, "count": 0},
                "archives": {"label": "Comprimidos y Respaldos", "bytes": 0, "count": 0},
                "others": {"label": "Otros Archivos", "bytes": 0, "count": 0},
            }
            doc_exts = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".tsv", ".ppt", ".pptx", ".txt", ".md", ".rtf", ".odt", ".ods"}
            arc_exts = {".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".bz2", ".sql", ".db"}

            total_files = 0
            total_dirs = 0
            total_bytes = 0
            largest_files = []

            for root, dirs, files in os.walk(self.config.storage_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (".trash", ".versions")]
                root_path = Path(root)
                for d in list(dirs):
                    d_rel = (root_path / d).relative_to(self.config.storage_dir).as_posix()
                    if not self.can_access_path(user, d_rel, perms_map):
                        dirs.remove(d)
                        continue
                    total_dirs += 1

                for f in files:
                    if f.startswith(".") or f == ".gitkeep":
                        continue
                    f_path = root_path / f
                    f_rel = f_path.relative_to(self.config.storage_dir).as_posix()
                    if not self.can_access_path(user, f_rel, perms_map):
                        continue
                    try:
                        st = f_path.stat()
                    except Exception:
                        continue
                    sz = st.st_size
                    total_files += 1
                    total_bytes += sz
                    ext = f_path.suffix.lower()
                    mime, _ = mimetypes.guess_type(f_path.name)
                    mime = mime or ""

                    if ext in doc_exts or mime.startswith("text/"):
                        cat = "documents"
                    elif mime.startswith("image/"):
                        cat = "images"
                    elif mime.startswith("video/"):
                        cat = "videos"
                    elif mime.startswith("audio/"):
                        cat = "audio"
                    elif ext in arc_exts:
                        cat = "archives"
                    else:
                        cat = "others"

                    categories[cat]["bytes"] += sz
                    categories[cat]["count"] += 1
                    largest_files.append({"name": f, "path": f_rel, "size": sz, "mtime": int(st.st_mtime)})

            largest_files.sort(key=lambda x: x["size"], reverse=True)
            usage = shutil.disk_usage(self.config.storage_dir)
            versions_size = self._calc_dir_size(self.config.versions_dir)
            trash_size = self._calc_dir_size(self.config.trash_dir)

            self.send_json({
                "ok": True,
                "total_files": total_files,
                "total_dirs": total_dirs,
                "total_bytes": total_bytes,
                "versions_bytes": versions_size,
                "trash_bytes": trash_size,
                "disk": {"total": usage.total, "used": usage.used, "free": usage.free},
                "categories": categories,
                "largest_files": largest_files[:10],
            })
        except Exception as e:
            self.send_json({"error": f"Error al calcular estadísticas: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

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
            if not self.can_access_path(user, dest_rel):
                self.send_json({"error": "No tienes acceso a la carpeta destino."}, status=HTTPStatus.FORBIDDEN)
                return
            dest_dir = self.resolve_storage_path(dest_rel)
            if not dest_dir.exists() or not dest_dir.is_dir():
                self.send_json({"error": "La carpeta de destino no existe."}, status=HTTPStatus.BAD_REQUEST)
                return

            moved = 0
            for p in paths:
                if not self.can_access_path(user, p):
                    continue
                src = self.resolve_storage_path(p)
                if src == self.config.storage_dir or not src.exists():
                    continue
                target_dest = dest_dir / src.name
                if src == target_dest or src in dest_dir.parents:
                    continue
                old_rel = src.relative_to(self.config.storage_dir).as_posix()
                shutil.move(str(src), str(target_dest))
                new_rel = target_dest.relative_to(self.config.storage_dir).as_posix()
                self.config.db.relocate_path_records(old_rel, new_rel)
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
                        if not self.can_access_path(user, p):
                            continue
                        target = self.resolve_storage_path(p)
                        if not target.exists():
                            continue
                        if target.is_file():
                            zf.write(target, target.name)
                        elif target.is_dir():
                            for root, dirs, files in os.walk(target):
                                dirs[:] = [d for d in dirs if not d.startswith(".")]
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
            if not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes acceso a este elemento."}, status=HTTPStatus.FORBIDDEN)
                return
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
                html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Enlace Protegido · Archivos ICFD</title>
                <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,600;1,700&family=Source+Sans+3:wght@400;500;600;700&display=swap" rel="stylesheet">
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
                <link rel="stylesheet" href="/static/styles.css"></head><body class="login-body">
                <div class="login-wrapper" style="max-width:480px;"><div class="login-card-split" style="min-height:auto; flex-direction:column;">
                <div class="hero-panel" style="padding:28px;"><div class="hero-seal" style="width:86px;height:86px;margin-bottom:1rem;"><img src="/static/img/logo.png" alt="Logo ICFD"></div>
                <div class="hero-eyebrow">Enlace Protegido</div><h1 class="hero-title" style="font-size:1.5rem;">{os.path.basename(share['path'])}</h1></div>
                <div class="form-panel" style="padding:28px;"><form method="GET" action="/s/{token}">
                <div class="form-group"><label class="form-label">Contraseña de descarga</label>
                <div class="input-group-custom"><i class="fas fa-lock input-icon"></i><input type="password" name="password" class="form-control-icfd" placeholder="Ingrese contraseña" required autofocus></div></div>
                <button class="btn-login" type="submit">Descargar Archivo</button></form></div></div></div></body></html>"""
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
            if user and not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes permiso para descargar este archivo."}, status=HTTPStatus.FORBIDDEN)
                return

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
            if user and not self.can_access_path(user, rel_path):
                self.send_json({"error": "No tienes permiso para descargar esta carpeta."}, status=HTTPStatus.FORBIDDEN)
                return

            target_dir = self.resolve_storage_path(rel_path)
            if not target_dir.exists() or not target_dir.is_dir():
                self.send_json({"error": "Carpeta no encontrada."}, status=HTTPStatus.NOT_FOUND)
                return

            zip_name = f"{target_dir.name or 'storage'}.zip"
            encoded_name = urllib.parse.quote(zip_name)
            perms_map = self.config.db.get_folder_permissions_map() if user else {}

            if user:
                self.config.db.log_audit(user["username"], self.get_client_ip(), "DOWNLOAD_ZIP", rel_path or "/")

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=True) as tmp:
                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(target_dir):
                        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (".trash", ".versions")]
                        if user:
                            for d in list(dirs):
                                d_rel = (Path(root) / d).relative_to(self.config.storage_dir).as_posix()
                                if not self.can_access_path(user, d_rel, perms_map):
                                    dirs.remove(d)
                        for file in files:
                            if file == ".gitkeep" or file.startswith("."):
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
    parser = argparse.ArgumentParser(description="Servidor de Archivos Web en Python v3.0")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Host de escucha")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Puerto de escucha")
    parser.add_argument("--dir", "--storage", dest="dir", default=os.environ.get("STORAGE_DIR", "./storage"), help="Directorio a compartir")
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
    print("  🚀 PYTHON FILE SERVER v3.0 (ICFD ENTERPRISE EDITION) INICIADO")
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
