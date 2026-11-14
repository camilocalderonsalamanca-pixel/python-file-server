# 📁 Python Modern File Server

Un servidor de archivos web moderno, ligero y autónomo escrito en **Python 3**, sin necesidad de instalar librerías externas (100% librería estándar).

## ✨ Características Principales

- **Interfaz Web Moderna**: Diseño limpio y responsivo con soporte para **Modo Claro / Oscuro** y barra de uso de disco en tiempo real.
- **Navegación por Directorios**: Exploración mediante *breadcrumbs* (migas de pan), creación de carpetas y buscador integrado.
- **Subida con Drag & Drop**: Arrastra y suelta múltiples archivos en cualquier lugar de la pantalla con barra de progreso en tiempo real (streaming directo a disco sin saturar la memoria RAM).
- **Descarga de Archivos y Carpetas (ZIP)**: Descarga archivos individuales o comprime carpetas enteras al vuelo en formato `.zip`.
- **Gestión Completa**: Renombra y elimina archivos o directorios directamente desde el navegador.
- **Vista Previa Integrada**: Visualiza imágenes, videos, audios y archivos de texto/código sin necesidad de descargarlos.
- **Autenticación Integrada**: Inicio de sesión seguro con cookies firmadas (`HMAC-SHA256`) y soporte para `HTTP Basic Auth` (ideal para usar con `curl` o scripts).
- **Seguridad**: Protección contra vulnerabilidades de *Path Traversal* (`../`).

---

## 🚀 Requisitos e Instalación

Solo necesitas **Python 3.8 o superior**. No requiere `pip install` de paquetes externos.

```bash
git clone https://github.com/camilocalderonsalamanca-pixel/python-file-server.git
cd python-file-server
```

---

## 💻 Uso Rápido

Inicia el servidor con la configuración por defecto:

```bash
python3 server.py
```

Luego abre en tu navegador:
- **URL**: `http://localhost:8000`
- **Usuario por defecto**: `admin`
- **Contraseña por defecto**: `admin123`

### Opciones por Línea de Comandos

Puedes personalizar el puerto, la carpeta a compartir o las credenciales al ejecutar el script:

```bash
python3 server.py --port 8080 --dir /ruta/a/mis/archivos --user camilo --password miclave123
```

Para ejecutarlo **sin autenticación**:

```bash
python3 server.py --no-auth
```

### Configuración mediante `.env`

También puedes copiar el archivo `.env.example` a `.env` y ajustar tus variables:

```bash
cp .env.example .env
```

```env
PORT=8000
HOST=0.0.0.0
STORAGE_DIR=./storage
AUTH_USER=admin
AUTH_PASS=admin123
SECRET_KEY=tu-clave-secreta
```

---

## 🛠️ Uso desde la Terminal (API / CLI con `curl`)

El servidor también soporta autenticación básica HTTP para automatizaciones:

- **Listar archivos**:
  ```bash
  curl -u admin:admin123 "http://localhost:8000/api/files?path="
  ```

- **Subir un archivo**:
  ```bash
  curl -u admin:admin123 -X POST --data-binary @mi_archivo.pdf \
    "http://localhost:8000/api/upload?path=&filename=mi_archivo.pdf"
  ```

- **Descargar un archivo**:
  ```bash
  curl -u admin:admin123 -OJ "http://localhost:8000/api/download?path=mi_archivo.pdf"
  ```

---

## 📂 Estructura del Proyecto

```text
.
├── server.py            # Servidor HTTP multihilo y endpoints de la API
├── templates/
│   ├── index.html       # Interfaz principal del explorador de archivos
│   └── login.html       # Pantalla de inicio de sesión
├── static/
│   ├── styles.css       # Estilos modernos con soporte Light/Dark mode
│   └── app.js           # Lógica frontend (Drag & Drop, modales, vista previa)
├── storage/             # Carpeta predeterminada donde se almacenan los archivos
├── .env.example         # Plantilla de variables de entorno
└── README.md            # Documentación del proyecto
```
