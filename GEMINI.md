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

## 2. Arquitectura y Funciones Actuales (`v3.0 Enterprise Edition`)
- **Archivo principal:** [server.py](file:///home/ccalderon/Documentos/Proyectos/File%20Server/server.py) (Servidor HTTP/HTTPS en Python puro con `ThreadingHTTPServer` y base de datos SQLite en `fileserver.db`, sin dependencias externas obligatorias).
- **Plantillas y estilos:** [templates/index.html](file:///home/ccalderon/Documentos/Proyectos/File%20Server/templates/index.html), [templates/login.html](file:///home/ccalderon/Documentos/Proyectos/File%20Server/templates/login.html), [static/styles.css](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/styles.css), [static/app.js](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/app.js).
- **Librerías locales Offline para Visor Office:** [static/vendor/xlsx.full.min.js](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/vendor/xlsx.full.min.js) (SheetJS) y [static/vendor/mammoth.browser.min.js](file:///home/ccalderon/Documentos/Proyectos/File%20Server/static/vendor/mammoth.browser.min.js) (Mammoth.js).
- **Script de aprovisionamiento automático:** [deploy/setup_server.sh](file:///home/ccalderon/Documentos/Proyectos/File%20Server/deploy/setup_server.sh) (instala y configura `systemd`, `nginx`, `avahi-daemon`, `avahi-alias-fileserver.service` y `dnsmasq`).
- **Funciones implementadas:**
  1. **Enlaces Públicos Compartibles (`/s/<token>`)**: Con expiración por horas, límite de descargas y contraseña opcional.
  2. **Multi-usuario y Roles (RBAC)**: Roles `admin` (control total), `editor` (subir/crear/editar sin borrar) y `viewer` (solo lectura/descarga), con contraseñas cifradas (`PBKDF2-HMAC-SHA256`).
  3. **Papelera de Reciclaje con Purga Automática a los 30 Días (`.trash`)**: Eliminación suave con restauración a ruta original, contador de días restantes (`⏳ En X días`), eliminación definitiva individual (`/api/trash/delete`), vaciado total y purga automática permanente a los **30 días** (`purge_expired_trash`, configurable vía `TRASH_RETENTION_DAYS`).
  4. **Operaciones en Lote, Descompresión y Editor**: Selección múltiple (ZIP, copiar, mover, borrar), extracción directa de `.zip`/`.tar.gz` y editor de texto/código integrado.
  5. **Vista Galería / Tabla, Visor PDF y Streaming**: Soporte `HTTP 206 Partial Content` (`Range`) para adelantar/atrasar video y audio, vista de miniaturas y visor PDF integrado con botón para abrir en pestaña nueva.
  6. **Seguridad y Auditoría**: Protección contra fuerza bruta (*Rate Limiting* por IP), soporte SSL (`--ssl-cert`, `--ssl-key`) y registro de auditoría en tiempo real (`audit_logs`).
  7. **Historial de Versiones (`.versions`)**: Respaldo automático cada vez que se sobrescribe o edita un archivo, con descarga y restauración de versiones previas.
  8. **Etiquetas Institucionales, Notas y Favoritos (⭐)**: Etiquetas predefinidas (`Contabilidad`, `Tesorería`, `Actas`, `Secretaría`, `Directiva`, `Aprobado`, `Pendiente`, `Urgente`) y personalizadas, notas por archivo y filtro de favoritos por usuario.
  9. **Visor Integrado de Excel (`.xlsx`, `.xls`, `.csv`, `.tsv`, `.ods`) y Word (`.docx`, `.doc`, `.rtf`)**: Lector 100% autónomo offline (SheetJS + Mammoth.js + fallback en Python `/api/office-preview`) con pestañas de hojas, buscador de filas, botón `👁️` de vista previa rápida e impresión.
  10. **Ordenamiento por Columnas, Menú Contextual (Clic Derecho) y Dashboard de Estadísticas**: Ordenamiento por nombre/tamaño/fecha, menú flotante con clic derecho, pestaña `Estadísticas` con desglose por categoría y top 10 archivos más pesados, y prevención de cursor de texto (`caret-color: transparent` / `user-select: none`) en elementos de interfaz.
  11. **Carpetas Privadas / Restringidas (ACL por Rol y Usuario)**: Control de acceso por carpeta con herencia a subcarpetas (`folder_permissions`).
  12. **Detector de Archivos Duplicados (SHA-256) (`/api/duplicates`)**: Escaneo inteligente por tamaño y huella `SHA-256` en la pestaña `Estadísticas`, con limpieza en 1 clic de copias redundantes.
  13. **Respaldo Institucional Completo en 1 Clic (`/api/backup`)**: Exportación `.ZIP` de la base de datos `fileserver.db` (en caliente vía `sqlite3.backup`) junto con todos los archivos y versiones de `storage/`.
  14. **Mi Perfil (Cambio de Contraseña Personal) (`/api/profile/password`)**: Cualquier usuario puede actualizar su propia contraseña haciendo clic en su insignia de usuario en la barra superior (`#profileModal`).
  15. **Navegación tipo Presentación en Vista Previa (`◀` `▶`)**: Botones Anterior/Siguiente, contador `X / N` y soporte de teclado (`Flecha Izquierda` / `Flecha Derecha`) sin salir del visor.
  16. **Copiar / Duplicar Elementos (`/api/copy`, `/api/bulk/copy`) y Subida de Carpetas Completas**: Botón `Subir Carpeta` (`webkitdirectory`), duplicación rápida (`- copia`) y copia masiva a otra carpeta.

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
