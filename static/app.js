// Estado global de la aplicación
const state = {
  currentPath: "",
  items: [],
  searchQuery: "",
};

// Elementos del DOM
const fileTableBody = document.getElementById("fileTableBody");
const emptyState = document.getElementById("emptyState");
const breadcrumbsEl = document.getElementById("breadcrumbs");
const searchInput = document.getElementById("searchInput");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const newFolderBtn = document.getElementById("newFolderBtn");
const downloadZipBtn = document.getElementById("downloadZipBtn");
const logoutBtn = document.getElementById("logoutBtn");
const themeToggleBtn = document.getElementById("themeToggleBtn");
const brandHome = document.getElementById("brandHome");
const dropOverlay = document.getElementById("dropOverlay");

// Progreso de subida
const uploadProgressPanel = document.getElementById("uploadProgressPanel");
const uploadStatusText = document.getElementById("uploadStatusText");
const uploadPercentText = document.getElementById("uploadPercentText");
const uploadProgressBar = document.getElementById("uploadProgressBar");

// Disco
const diskLabel = document.getElementById("diskLabel");
const diskFill = document.getElementById("diskFill");

// Modal Prompt
const promptModal = document.getElementById("promptModal");
const promptModalTitle = document.getElementById("promptModalTitle");
const promptModalLabel = document.getElementById("promptModalLabel");
const promptInput = document.getElementById("promptInput");
const promptForm = document.getElementById("promptForm");
const promptCloseBtn = document.getElementById("promptCloseBtn");
const promptCancelBtn = document.getElementById("promptCancelBtn");

// Modal Preview
const previewModal = document.getElementById("previewModal");
const previewTitle = document.getElementById("previewTitle");
const previewContent = document.getElementById("previewContent");
const previewDownloadBtn = document.getElementById("previewDownloadBtn");
const previewCloseBtn = document.getElementById("previewCloseBtn");

let promptCallback = null;

// --- Inicialización de Tema ---
function initTheme() {
  const saved = localStorage.getItem("fs_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
}

themeToggleBtn.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("fs_theme", next);
});

// --- Utilidades de formato ---
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(timestamp) {
  if (!timestamp) return "-";
  const d = new Date(timestamp * 1000);
  return d.toLocaleString("es-CL", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

// --- Iconos SVG ---
function getFolderSvg() {
  return `<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" stroke="currentColor" stroke-width="1.5">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
  </svg>`;
}

function getFileSvg() {
  return `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
    <polyline points="14 2 14 8 20 8"></polyline>
  </svg>`;
}

// --- Carga de Archivos ---
async function loadFiles(path = state.currentPath, search = state.searchQuery) {
  try {
    const params = new URLSearchParams({ path, search });
    const res = await fetch(`/api/files?${params.toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Error al cargar archivos", "error");
      return;
    }

    state.currentPath = data.current_path;
    state.items = data.items || [];

    renderBreadcrumbs();
    renderFiles();
    if (data.disk) {
      updateDiskUsage(data.disk);
    }
  } catch (err) {
    showToast("Error de conexión con el servidor", "error");
  }
}

function updateDiskUsage(disk) {
  const pct = disk.total > 0 ? Math.min(100, Math.round((disk.used / disk.total) * 100)) : 0;
  diskLabel.textContent = `${formatBytes(disk.free)} libres de ${formatBytes(disk.total)}`;
  diskFill.style.width = `${pct}%`;
}

function renderBreadcrumbs() {
  breadcrumbsEl.innerHTML = "";

  const rootCrumb = document.createElement("span");
  rootCrumb.className = `crumb ${state.currentPath === "" ? "active" : ""}`;
  rootCrumb.textContent = "🏠 Inicio";
  rootCrumb.addEventListener("click", () => navigateTo(""));
  breadcrumbsEl.appendChild(rootCrumb);

  if (!state.currentPath) return;

  const parts = state.currentPath.split("/").filter(Boolean);
  let accumulated = "";

  parts.forEach((part, idx) => {
    accumulated = accumulated ? `${accumulated}/${part}` : part;
    const targetPath = accumulated;

    const sep = document.createElement("span");
    sep.className = "crumb-sep";
    sep.textContent = "/";
    breadcrumbsEl.appendChild(sep);

    const crumb = document.createElement("span");
    crumb.className = `crumb ${idx === parts.length - 1 ? "active" : ""}`;
    crumb.textContent = part;
    crumb.addEventListener("click", () => navigateTo(targetPath));
    breadcrumbsEl.appendChild(crumb);
  });
}

function renderFiles() {
  fileTableBody.innerHTML = "";

  // Si estamos en una subcarpeta y no estamos buscando, mostrar fila ".." para subir
  if (state.currentPath && !state.searchQuery) {
    const parentPath = state.currentPath.includes("/")
      ? state.currentPath.substring(0, state.currentPath.lastIndexOf("/"))
      : "";
    const upRow = document.createElement("tr");
    upRow.innerHTML = `
      <td colspan="4">
        <div class="item-cell" id="upDirRow">
          <span class="item-icon folder">${getFolderSvg()}</span>
          <span class="item-name">.. (Subir nivel)</span>
        </div>
      </td>
    `;
    upRow.querySelector("#upDirRow").addEventListener("click", () => navigateTo(parentPath));
    fileTableBody.appendChild(upRow);
  }

  if (state.items.length === 0) {
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");

  state.items.forEach((item) => {
    const tr = document.createElement("tr");

    // Celda nombre
    const nameTd = document.createElement("td");
    const cellDiv = document.createElement("div");
    cellDiv.className = "item-cell";
    cellDiv.innerHTML = `
      <span class="item-icon ${item.is_dir ? "folder" : "file"}">
        ${item.is_dir ? getFolderSvg() : getFileSvg()}
      </span>
      <span class="item-name"></span>
    `;
    cellDiv.querySelector(".item-name").textContent = state.searchQuery ? item.path : item.name;
    cellDiv.addEventListener("click", () => {
      if (item.is_dir) {
        searchInput.value = "";
        state.searchQuery = "";
        navigateTo(item.path);
      } else {
        openPreview(item);
      }
    });
    nameTd.appendChild(cellDiv);

    // Celda tamaño
    const sizeTd = document.createElement("td");
    sizeTd.className = "col-size";
    sizeTd.textContent = item.is_dir ? "Carpeta" : formatBytes(item.size);

    // Celda fecha
    const dateTd = document.createElement("td");
    dateTd.className = "col-date";
    dateTd.textContent = formatDate(item.mtime);

    // Celda acciones
    const actionsTd = document.createElement("td");
    actionsTd.className = "col-actions";
    const group = document.createElement("div");
    group.className = "action-group";

    // Botón Descargar (Archivo o Carpeta ZIP)
    const dlBtn = document.createElement("button");
    dlBtn.className = "action-btn";
    dlBtn.title = item.is_dir ? "Descargar carpeta (ZIP)" : "Descargar archivo";
    dlBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <polyline points="7 10 12 15 17 10"></polyline>
      <line x1="12" y1="15" x2="12" y2="3"></line>
    </svg>`;
    dlBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const url = item.is_dir
        ? `/api/zip?path=${encodeURIComponent(item.path)}`
        : `/api/download?path=${encodeURIComponent(item.path)}`;
      window.location.href = url;
    });

    // Botón Renombrar
    const renBtn = document.createElement("button");
    renBtn.className = "action-btn";
    renBtn.title = "Renombrar";
    renBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 20h9"></path>
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
    </svg>`;
    renBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openPromptModal({
        title: "Renombrar",
        label: "Nuevo nombre:",
        defaultValue: item.name,
        onConfirm: async (newName) => {
          await renameItem(item.path, newName);
        },
      });
    });

    // Botón Eliminar
    const delBtn = document.createElement("button");
    delBtn.className = "action-btn danger";
    delBtn.title = "Eliminar";
    delBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="3 6 5 6 21 6"></polyline>
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
    </svg>`;
    delBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const msg = item.is_dir
        ? `¿Eliminar la carpeta "${item.name}" y todo su contenido?`
        : `¿Eliminar el archivo "${item.name}"?`;
      if (confirm(msg)) {
        await deleteItem(item.path);
      }
    });

    group.appendChild(dlBtn);
    group.appendChild(renBtn);
    group.appendChild(delBtn);
    actionsTd.appendChild(group);

    tr.appendChild(nameTd);
    tr.appendChild(sizeTd);
    tr.appendChild(dateTd);
    tr.appendChild(actionsTd);
    fileTableBody.appendChild(tr);
  });
}

function navigateTo(path) {
  state.currentPath = path;
  loadFiles(path, state.searchQuery);
}

// --- Operaciones API ---
async function createFolder(name) {
  const res = await fetch("/api/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: state.currentPath, name }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast(`Carpeta "${name}" creada`, "success");
    loadFiles();
  } else {
    showToast(data.error || "No se pudo crear la carpeta", "error");
  }
}

async function renameItem(path, newName) {
  const res = await fetch("/api/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, new_name: newName }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Elemento renombrado", "success");
    loadFiles();
  } else {
    showToast(data.error || "No se pudo renombrar", "error");
  }
}

async function deleteItem(path) {
  const res = await fetch("/api/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Elemento eliminado", "success");
    loadFiles();
  } else {
    showToast(data.error || "No se pudo eliminar", "error");
  }
}

// --- Subida de Archivos con Progreso ---
async function uploadFiles(fileList) {
  const files = Array.from(fileList);
  if (files.length === 0) return;

  uploadProgressPanel.classList.remove("hidden");

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const relName = file.webkitRelativePath || file.name;
    uploadStatusText.textContent = `Subiendo (${i + 1}/${files.length}): ${relName}`;
    uploadPercentText.textContent = "0%";
    uploadProgressBar.style.width = "0%";

    try {
      await uploadSingleFile(file, relName);
    } catch (err) {
      showToast(`Error al subir ${file.name}: ${err.message}`, "error");
    }
  }

  uploadProgressPanel.classList.add("hidden");
  showToast(
    files.length === 1 ? "Archivo subido correctamente" : `${files.length} archivos subidos`,
    "success"
  );
  fileInput.value = "";
  loadFiles();
}

function uploadSingleFile(file, relName) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const params = new URLSearchParams({
      path: state.currentPath,
      filename: relName,
    });

    xhr.open("POST", `/api/upload?${params.toString()}`, true);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-File-Name", encodeURIComponent(relName));

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        uploadPercentText.textContent = `${pct}%`;
        uploadProgressBar.style.width = `${pct}%`;
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        let errMsg = "Fallo en la subida";
        try {
          const resp = JSON.parse(xhr.responseText);
          if (resp.error) errMsg = resp.error;
        } catch (_) {}
        reject(new Error(errMsg));
      }
    };

    xhr.onerror = () => reject(new Error("Error de red"));
    xhr.send(file);
  });
}

// --- Modal de Prompt (Nueva Carpeta / Renombrar) ---
function openPromptModal({ title, label, defaultValue = "", onConfirm }) {
  promptModalTitle.textContent = title;
  promptModalLabel.textContent = label;
  promptInput.value = defaultValue;
  promptCallback = onConfirm;
  promptModal.classList.remove("hidden");
  setTimeout(() => {
    promptInput.focus();
    promptInput.select();
  }, 50);
}

function closePromptModal() {
  promptModal.classList.add("hidden");
  promptCallback = null;
}

promptForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const val = promptInput.value.trim();
  if (!val) return;
  const cb = promptCallback;
  closePromptModal();
  if (cb) await cb(val);
});

promptCloseBtn.addEventListener("click", closePromptModal);
promptCancelBtn.addEventListener("click", closePromptModal);

// --- Vista Previa de Archivos ---
async function openPreview(item) {
  const inlineUrl = `/api/download?path=${encodeURIComponent(item.path)}&inline=1`;
  const downloadUrl = `/api/download?path=${encodeURIComponent(item.path)}`;

  previewTitle.textContent = item.name;
  previewDownloadBtn.href = downloadUrl;
  previewContent.innerHTML = "";
  previewModal.classList.remove("hidden");

  const mime = item.mime || "";
  const ext = item.name.split(".").pop().toLowerCase();
  const textExts = ["txt", "md", "json", "py", "js", "css", "html", "xml", "yml", "yaml", "csv", "log", "sh", "env"];

  if (mime.startsWith("image/")) {
    const img = document.createElement("img");
    img.src = inlineUrl;
    img.alt = item.name;
    previewContent.appendChild(img);
  } else if (mime.startsWith("video/")) {
    const video = document.createElement("video");
    video.src = inlineUrl;
    video.controls = true;
    video.autoplay = true;
    previewContent.appendChild(video);
  } else if (mime.startsWith("audio/")) {
    const audio = document.createElement("audio");
    audio.src = inlineUrl;
    audio.controls = true;
    audio.autoplay = true;
    previewContent.appendChild(audio);
  } else if (mime.startsWith("text/") || textExts.includes(ext)) {
    if (item.size > 512 * 1024) {
      previewContent.innerHTML = `<p>El archivo de texto es demasiado grande para la vista previa (${formatBytes(item.size)}).</p>`;
      return;
    }
    try {
      const res = await fetch(inlineUrl);
      const text = await res.text();
      const pre = document.createElement("pre");
      pre.textContent = text;
      previewContent.appendChild(pre);
    } catch (_) {
      previewContent.innerHTML = `<p>No se pudo cargar la vista previa.</p>`;
    }
  } else {
    previewContent.innerHTML = `
      <div style="text-align:center; padding: 2rem;">
        <p style="margin-bottom: 0.5rem;">Vista previa no disponible para este tipo de archivo (${mime}).</p>
        <p style="color: var(--text-muted); font-size: 0.88rem;">Tamaño: ${formatBytes(item.size)}</p>
      </div>
    `;
  }
}

previewCloseBtn.addEventListener("click", () => {
  previewContent.innerHTML = "";
  previewModal.classList.add("hidden");
});

// --- Eventos de Interfaz ---
uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => uploadFiles(e.target.files));

newFolderBtn.addEventListener("click", () => {
  openPromptModal({
    title: "Nueva Carpeta",
    label: "Nombre de la carpeta:",
    defaultValue: "",
    onConfirm: async (folderName) => {
      await createFolder(folderName);
    },
  });
});

downloadZipBtn.addEventListener("click", () => {
  window.location.href = `/api/zip?path=${encodeURIComponent(state.currentPath)}`;
});

brandHome.addEventListener("click", () => {
  searchInput.value = "";
  state.searchQuery = "";
  navigateTo("");
});

let searchTimeout = null;
searchInput.addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    state.searchQuery = e.target.value.trim();
    loadFiles(state.currentPath, state.searchQuery);
  }, 250);
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

// --- Drag & Drop Global ---
let dragCounter = 0;

window.addEventListener("dragenter", (e) => {
  e.preventDefault();
  dragCounter++;
  dropOverlay.classList.remove("hidden");
});

window.addEventListener("dragover", (e) => {
  e.preventDefault();
});

window.addEventListener("dragleave", (e) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    dropOverlay.classList.add("hidden");
  }
});

window.addEventListener("drop", (e) => {
  e.preventDefault();
  dragCounter = 0;
  dropOverlay.classList.add("hidden");
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    uploadFiles(e.dataTransfer.files);
  }
});

// Iniciar
initTheme();
loadFiles();
