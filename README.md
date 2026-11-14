# 📁 Python Modern File Server v2.0 (Enterprise Edition)

Un servidor de archivos web completo, moderno, ligero y autónomo escrito en **Python 3** (100% librería estándar, con base de datos `SQLite` integrada y sin dependencias externas).

## ✨ Características Principales (v2.0)

1. **🔗 Enlaces Públicos para Compartir (`/s/<token>`)**:
   - Comparte cualquier archivo o carpeta mediante un enlace público sin revelar tus credenciales.
   - Configura **tiempo de expiración (horas)**, **límite máximo de descargas** y **contraseña opcional**.
2. **👥 Multi-usuario y Permisos por Roles (`SQLite` + `PBKDF2-HMAC-SHA256`)**:
   - **Administrador (`admin`)**: Control total, gestión de usuarios, vaciado de papelera y registro de auditoría.
   - **Editor (`editor`)**: Puede subir archivos, crear carpetas, editar texto, descomprimir y compartir enlaces.
   - **Lector (`viewer`)**: Acceso de solo lectura y descarga.
3. **🗑️ Papelera de Reciclaje (`.trash`)**:
   - Los archivos eliminados se mueven primero a la papelera, permitiendo **restaurarlos** con un clic o vaciar la papelera definitivamente.
4. **⚡ Operaciones Masivas, Descompresión y Editor de Código**:
   - **Selección múltiple**: Descarga varios archivos/carpetas juntos en un `.zip`, muévelos de carpeta o envíalos a la papelera en bloque.
   - **Descompresión en el servidor**: Extrae archivos `.zip`, `.tar.gz`, `.tgz` y `.tar` directamente desde el navegador (con protección contra *Zip Slip*).
   - **Editor de texto/código integrado**: Crea y edita archivos `.txt`, `.md`, `.json`, `.py`, `.js`, `.sh`, `.html`, etc. sin salir del navegador.
5. **🖼️ Vista de Galería, Visor PDF y Streaming con `HTTP Range`**:
   - Alterna entre **Vista de Tabla** y **Vista de Cuadrícula (Grid View)** con miniaturas de imágenes.
   - Soporte `HTTP 206 Partial Content (Range)` para adelantar/atrasar videos y audios largos al instante.
   - Visor de documentos **PDF** integrado en el modal de vista previa.
6. **🛡️ Seguridad Avanzada**:
   - **Rate Limiting**: Bloqueo temporal automático por IP tras 5 intentos fallidos de inicio de sesión.
   - **Registro de Auditoría (Audit Logs)**: Historial detallado de inicios de sesión, subidas, descargas, ediciones y enlaces compartidos con dirección IP y fecha.
   - **Soporte HTTPS/SSL nativo**: Permite cargar certificados TLS (`--ssl-cert` y `--ssl-key`).

---

## 🚀 Ejecución Rápida

```bash
python3 server.py
```

- **URL**: `http://localhost:8000`
- **Usuario administrador inicial**: `admin`
- **Contraseña inicial**: `admin123`

### Opciones por Línea de Comandos

```bash
python3 server.py --port 8000 --dir ./storage --ssl-cert cert.pem --ssl-key key.pem
```
