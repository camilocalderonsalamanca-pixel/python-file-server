# Memoria y Reglas del Proyecto — File Server ICFD

## 1. Identidad Institucional y Diseño (ERP ICFD)
- **Organización:** Corporación · Iglesia Cristiana Internacional Familia de Dios (**ICFD**).
- **Referencia visual:** Basado en el portal `https://api-icfd.tail90e687.ts.net/login?next=/`.
- **Logo oficial:** [static/img/logo.png](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/img/logo.png).
- **Paleta de colores oficial (mantener siempre):**
  - Azul Marino ICFD: `--icfd-navy-800: #14213D`, `--icfd-navy-900: #111D35`, `--icfd-navy-950: #0B1324`, `--icfd-navy-700: #1D2E52`.
  - Dorado Institucional: `--icfd-gold: #B08D57`, `--icfd-gold-light: #D9C49A`, `--icfd-gold-dark: #8F6F3E`.
  - Fondos y Superficies: `--icfd-ivory: #F7F5F0`, `--icfd-paper: #FFFFFF`, `--icfd-ink: #1B2432`.
- **Estilo visual:** Acabado **Glossy / Glassmorphism** (reflejos especulares en barra superior, encabezados y botones, más desenfoque de cristal `backdrop-filter: blur(18px)` en tarjetas y modales) conservando estrictamente los colores institucionales de ICFD.
- **Tipografías:** `Cormorant Garamond` (títulos y encabezados formales) y `Source Sans 3` (interfaz, tablas y controles), más iconos de **Font Awesome 6**.

## 2. Arquitectura y Funciones Actuales (`v2.0 Enterprise Edition`)
- **Archivo principal:** [server.py](file:///home/ccalderon/Documentos/Proyectos/File%20Server/server.py) (Servidor HTTP/HTTPS en Python puro con `ThreadingHTTPServer` y base de datos SQLite en `fileserver.db`, sin dependencias externas obligatorias).
- **Plantillas y estilos:** [templates/index.html](file:///home/ccalderon/Documentos/Proyectos/File%20Server/templates/index.html), [templates/login.html](file:///home/ccalderon/Documentos/Proyectos/File%20Server/templates/login.html), [static/styles.css](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/styles.css), [static/app.js](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/app.js).
- **Funciones implementadas:**
  1. **Enlaces Públicos Compartibles (`/s/<token>`)**: Con expiración por horas, límite de descargas y contraseña opcional.
  2. **Multi-usuario y Roles (RBAC)**: Roles `admin` (control total), `editor` (subir/crear/editar sin borrar) y `viewer` (solo lectura/descarga), con contraseñas cifradas (`PBKDF2-HMAC-SHA256`).
  3. **Papelera de Reciclaje (`.trash`)**: Eliminación suave con restauración a ruta original o vaciado definitivo.
  4. **Operaciones en Lote, Descompresión y Editor**: Selección múltiple (ZIP, mover, borrar), extracción directa de `.zip`/`.tar.gz` y editor de texto/código integrado.
  5. **Vista Galería / Tabla, Visor PDF y Streaming**: Soporte `HTTP 206 Partial Content` (`Range`) para adelantar/atrasar video y audio, vista de miniaturas y visor PDF.
  6. **Seguridad y Auditoría**: Protección contra fuerza bruta (*Rate Limiting* por IP), soporte SSL (`--ssl-cert`, `--ssl-key`) y registro de auditoría en tiempo real (`audit_logs`).

## 3. Repositorio en GitHub
- **Cuenta de GitHub:** `camilocalderonsalamanca-pixel`
- **Repositorio:** `https://github.com/camilocalderonsalamanca-pixel/python-file-server.git` (rama `main`).
- **Archivos ignorados (`.gitignore`):** `fileserver.db`, `storage/`, `.env` (nunca subir la base de datos ni los archivos almacenados al repositorio).

## 4. Servidor de Producción (`fileserver-icfd`) y Entorno Local
- **Servidor Ubuntu 26.10:** `fileserver-icfd`
  - **URLs Plug & Play (mDNS / Avahi / LLMNR, sin configurar router):**
    - `http://fileserver.local` (publicado automáticamente por `avahi-alias-fileserver.service` con la IP actual del equipo)
    - `http://fileserver-icfd.local` (anuncio nativo `avahi-daemon`)
    - `http://fileserver-icfd` (vía LLMNR en equipos Windows de la misma red)
  - **IP / URL sin puerto (vía Nginx + DNS local `dnsmasq`):** `http://fileserver.icfd.cl` y `http://192.168.1.134` (proxy inverso Nginx en puerto `80` hacia `127.0.0.1:8000`).
  - **Servidor DNS interno (`dnsmasq`):** Activo en `192.168.1.134:53` (`/etc/dnsmasq.d/icfd.conf`), resuelve `fileserver.icfd.cl`, `fileserver.local` y `fileserver-icfd.local` a `192.168.1.134`.
  - **Configuración Nginx en servidor:** `/etc/nginx/sites-available/fileserver.icfd.cl` (con `client_max_body_size 0;`, streaming `Range` y sin buffering de subida).
  - **URL directa al backend Python:** `http://192.168.1.134:8000`
  - **Usuario SSH:** `adminicfd` (contraseña configurada en sesión previa: `Icfd-*2026`).
  - **Ruta de instalación:** `/opt/python-file-server` (almacenamiento en `/opt/python-file-server/storage`).
  - **Servicio Systemd:** `python-file-server.service` (activo 24/7 con arranque automático).
  - **Credenciales web iniciales:** Usuario `admin` / Contraseña `admin123`.
  - **Comandos de actualización en el servidor:**
    ```bash
    cd /opt/python-file-server && git pull origin main && sudo systemctl restart python-file-server
    ```
- **Entorno Local:** `http://localhost:8000` (ejecutándose desde `/home/ccalderon/Documentos/Proyectos/File Server/server.py`).
