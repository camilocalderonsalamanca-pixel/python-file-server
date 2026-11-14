// Estado global de la aplicación v3.0 (ICFD Enterprise Edition)
const state = {
  currentPath: "",
  items: [],
  searchQuery: "",
  favoritesOnly: false,
  tagFilter: "",
  sortBy: "name", // "name" | "size" | "mtime"
  sortAsc: true,
  viewMode: localStorage.getItem("fs_view") || "table", // "table" | "grid"
  selectedPaths: new Set(),
  user: { username: "", role: "viewer" },
  activeTab: "files",
  editingPath: null,
  sharingPath: null,
  metaItem: null,
  permItem: null,
};

const PRESET_TAGS = [
  "Contabilidad",
  "Tesorería",
  "Actas",
  "Secretaría",
  "Directiva",
  "Aprobado",
  "Pendiente",
  "Urgente",
];

// --- Elementos del DOM ---
const fileTableBody = document.getElementById("fileTableBody");
const gridViewContainer = document.getElementById("gridViewContainer");
const tableViewContainer = document.getElementById("tableViewContainer");
const emptyState = document.getElementById("emptyState");
const breadcrumbsEl = document.getElementById("breadcrumbs");
const searchInput = document.getElementById("searchInput");
const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const newFolderBtn = document.getElementById("newFolderBtn");
const newTextFileBtn = document.getElementById("newTextFileBtn");
const downloadZipBtn = document.getElementById("downloadZipBtn");
const viewModeBtn = document.getElementById("viewModeBtn");
const viewModeIcon = document.getElementById("viewModeIcon");
const logoutBtn = document.getElementById("logoutBtn");
const themeToggleBtn = document.getElementById("themeToggleBtn");
const brandHome = document.getElementById("brandHome");
const dropOverlay = document.getElementById("dropOverlay");
const userBadge = document.getElementById("userBadge");

// Filtros rápidos
const filterAllBtn = document.getElementById("filterAllBtn");
const filterFavBtn = document.getElementById("filterFavBtn");
const tagFilterSelect = document.getElementById("tagFilterSelect");

// Selección Múltiple (Bulk)
const selectAllCheckbox = document.getElementById("selectAllCheckbox");
const bulkBar = document.getElementById("bulkBar");
const bulkCount = document.getElementById("bulkCount");
const bulkZipBtn = document.getElementById("bulkZipBtn");
const bulkMoveBtn = document.getElementById("bulkMoveBtn");
const bulkDeleteBtn = document.getElementById("bulkDeleteBtn");
const bulkClearBtn = document.getElementById("bulkClearBtn");

// Progreso de subida y Disco
const uploadProgressPanel = document.getElementById("uploadProgressPanel");
const uploadStatusText = document.getElementById("uploadStatusText");
const uploadPercentText = document.getElementById("uploadPercentText");
const uploadProgressBar = document.getElementById("uploadProgressBar");
const diskLabel = document.getElementById("diskLabel");
const diskFill = document.getElementById("diskFill");

// Modales y Menú Contextual
const contextMenu = document.getElementById("contextMenu");

const promptModal = document.getElementById("promptModal");
const promptModalTitle = document.getElementById("promptModalTitle");
const promptModalLabel = document.getElementById("promptModalLabel");
const promptInput = document.getElementById("promptInput");
const promptForm = document.getElementById("promptForm");

const metaModal = document.getElementById("metaModal");
const metaForm = document.getElementById("metaForm");
const metaTargetLabel = document.getElementById("metaTargetLabel");
const metaCustomTagInput = document.getElementById("metaCustomTagInput");
const metaNoteInput = document.getElementById("metaNoteInput");

const versionsModal = document.getElementById("versionsModal");
const versionsTargetLabel = document.getElementById("versionsTargetLabel");
const versionsTableBody = document.getElementById("versionsTableBody");

const permissionsModal = document.getElementById("permissionsModal");
const permForm = document.getElementById("permForm");
const permTargetLabel = document.getElementById("permTargetLabel");
const permRestrictCheck = document.getElementById("permRestrictCheck");
const permUsersList = document.getElementById("permUsersList");

const shareModal = document.getElementById("shareModal");
const shareForm = document.getElementById("shareForm");
const shareTargetLabel = document.getElementById("shareTargetLabel");
const shareHoursInput = document.getElementById("shareHoursInput");
const shareMaxDlInput = document.getElementById("shareMaxDlInput");
const sharePasswordInput = document.getElementById("sharePasswordInput");
const shareResultBox = document.getElementById("shareResultBox");
const shareResultUrl = document.getElementById("shareResultUrl");

const editorModal = document.getElementById("editorModal");
const editorTitle = document.getElementById("editorTitle");
const editorTextarea = document.getElementById("editorTextarea");
const editorSaveBtn = document.getElementById("editorSaveBtn");

const userModal = document.getElementById("userModal");
const userForm = document.getElementById("userForm");
const userFormName = document.getElementById("userFormName");
const userFormPass = document.getElementById("userFormPass");
const userFormRole = document.getElementById("userFormRole");

const previewModal = document.getElementById("previewModal");
const previewTitle = document.getElementById("previewTitle");
const previewContent = document.getElementById("previewContent");
const previewDownloadBtn = document.getElementById("previewDownloadBtn");
const previewEditBtn = document.getElementById("previewEditBtn");

let promptCallback = null;

// --- Tema Claro / Oscuro ---
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

// --- Utilidades ---
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
  setTimeout(() => toast.remove(), 3500);
}

function isTextEditable(name, mime) {
  const ext = name.split(".").pop().toLowerCase();
  const textExts = ["txt", "md", "json", "py", "js", "ts", "css", "html", "xml", "yml", "yaml", "csv", "tsv", "log", "sh", "env", "ini", "conf", "sql"];
  return (mime && mime.startsWith("text/")) || textExts.includes(ext);
}

function isOfficePreviewable(name) {
  const lower = name.toLowerCase();
  return lower.endsWith(".xlsx") || lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".docx");
}

function isArchivable(name) {
  const lower = name.toLowerCase();
  return lower.endsWith(".zip") || lower.endsWith(".tar.gz") || lower.endsWith(".tgz") || lower.endsWith(".tar");
}

function getTagClass(tag) {
  const t = tag.toLowerCase();
  if (t.includes("urgente") || t.includes("pendiente")) return "tag-urgent";
  if (t.includes("aprobado")) return "tag-success";
  if (t.includes("tesorer") || t.includes("contab")) return "tag-gold";
  return "tag-navy";
}

// --- Autenticación y Permisos en UI ---
async function initAuth() {
  try {
    const res = await fetch("/api/auth/status");
    const data = await res.json();
    if (!data.authenticated) {
      window.location.href = "/login";
      return;
    }
    state.user = { username: data.username, role: data.role };
    const roleNames = { admin: "Admin", editor: "Editor", viewer: "Lector" };
    userBadge.textContent = `👤 ${data.username} (${roleNames[data.role] || data.role})`;

    const canWrite = data.role === "admin" || data.role === "editor";
    const isAdmin = data.role === "admin";

    document.querySelectorAll(".write-only").forEach((el) => {
      el.classList.toggle("hidden", !canWrite);
    });
    document.querySelectorAll(".admin-only").forEach((el) => {
      el.classList.toggle("hidden", !isAdmin);
    });
    if (!canWrite) {
      document.getElementById("tabBtnShares").classList.add("hidden");
    }
  } catch (_) {}
}

// --- Navegación por Pestañas ---
document.querySelectorAll(".nav-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    switchTab(tab);
  });
});

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));

  document.getElementById("sectionFiles").classList.toggle("hidden", tab !== "files");
  document.getElementById("sectionStats").classList.toggle("hidden", tab !== "stats");
  document.getElementById("sectionTrash").classList.toggle("hidden", tab !== "trash");
  document.getElementById("sectionShares").classList.toggle("hidden", tab !== "shares");
  document.getElementById("sectionUsers").classList.toggle("hidden", tab !== "users");
  document.getElementById("sectionAudit").classList.toggle("hidden", tab !== "audit");

  if (tab === "files") loadFiles();
  if (tab === "stats") loadStats();
  if (tab === "trash") loadTrash();
  if (tab === "shares") loadShares();
  if (tab === "users") loadUsers();
  if (tab === "audit") loadAudit();
}

// --- Filtros Rápidos (Favoritos y Etiquetas) ---
filterAllBtn.addEventListener("click", () => {
  state.favoritesOnly = false;
  state.tagFilter = "";
  tagFilterSelect.value = "";
  updateFilterBarUI();
  loadFiles();
});

filterFavBtn.addEventListener("click", () => {
  state.favoritesOnly = !state.favoritesOnly;
  updateFilterBarUI();
  loadFiles();
});

tagFilterSelect.addEventListener("change", () => {
  state.tagFilter = tagFilterSelect.value;
  updateFilterBarUI();
  loadFiles();
});

function updateFilterBarUI() {
  const isAll = !state.favoritesOnly && !state.tagFilter;
  filterAllBtn.classList.toggle("active", isAll);
  filterFavBtn.classList.toggle("active", state.favoritesOnly);
}

// --- Ordenamiento por Columnas ---
document.querySelectorAll(".sortable-th").forEach((th) => {
  th.addEventListener("click", () => {
    const col = th.dataset.sort;
    if (state.sortBy === col) {
      state.sortAsc = !state.sortAsc;
    } else {
      state.sortBy = col;
      state.sortAsc = col === "name";
    }
    updateSortHeadersUI();
    sortItemsInPlace();
    renderFilesView();
  });
});

function updateSortHeadersUI() {
  ["name", "size", "mtime"].forEach((col) => {
    const el = document.getElementById(`sortIcon_${col}`);
    if (!el) return;
    if (state.sortBy === col) {
      el.textContent = state.sortAsc ? "▲" : "▼";
    } else {
      el.textContent = "";
    }
  });
}

function sortItemsInPlace() {
  const dirFactor = state.sortAsc ? 1 : -1;
  state.items.sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    if (state.sortBy === "size") {
      return (a.size - b.size) * dirFactor;
    }
    if (state.sortBy === "mtime") {
      return (a.mtime - b.mtime) * dirFactor;
    }
    return a.name.localeCompare(b.name, "es", { numeric: true }) * dirFactor;
  });
}

// --- Carga de Archivos ---
async function loadFiles(path = state.currentPath, search = state.searchQuery) {
  try {
    const params = new URLSearchParams({
      path,
      search,
      favorites: state.favoritesOnly ? "1" : "0",
      tag: state.tagFilter || "",
    });
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
    sortItemsInPlace();
    state.selectedPaths.clear();
    updateBulkBar();

    // Poblar selector de etiquetas con etiquetas personalizadas existentes
    if (Array.isArray(data.all_tags)) {
      const currentVal = state.tagFilter;
      const allKnown = Array.from(new Set([...PRESET_TAGS, ...data.all_tags]));
      tagFilterSelect.innerHTML = `<option value="">Todas las etiquetas</option>`;
      allKnown.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        if (t === currentVal) opt.selected = true;
        tagFilterSelect.appendChild(opt);
      });
    }

    renderBreadcrumbs();
    renderFilesView();
    if (data.disk) {
      const pct = data.disk.total > 0 ? Math.min(100, Math.round((data.disk.used / data.disk.total) * 100)) : 0;
      diskLabel.textContent = `${formatBytes(data.disk.free)} libres de ${formatBytes(data.disk.total)}`;
      diskFill.style.width = `${pct}%`;
    }
  } catch (_) {
    showToast("Error de conexión con el servidor", "error");
  }
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
  let acc = "";
  parts.forEach((part, idx) => {
    acc = acc ? `${acc}/${part}` : part;
    const targetPath = acc;
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

function renderFilesView() {
  const isGrid = state.viewMode === "grid";
  viewModeIcon.textContent = isGrid ? "☰" : "⊞";

  if (state.items.length === 0 && !state.currentPath) {
    tableViewContainer.classList.add("hidden");
    gridViewContainer.classList.add("hidden");
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.toggle("hidden", state.items.length > 0);
  tableViewContainer.classList.toggle("hidden", isGrid);
  gridViewContainer.classList.toggle("hidden", !isGrid);

  if (isGrid) {
    renderGridView();
  } else {
    renderTableView();
  }
}

function getFileIconChar(item) {
  if (item.is_dir) return "📁";
  const name = item.name.toLowerCase();
  if (name.endsWith(".xlsx") || name.endsWith(".xls") || name.endsWith(".csv")) return "📊";
  if (name.endsWith(".docx") || name.endsWith(".doc")) return "📘";
  if (name.endsWith(".pdf")) return "📕";
  if (item.mime.startsWith("image/")) return "🖼️";
  if (item.mime.startsWith("video/")) return "🎬";
  if (item.mime.startsWith("audio/")) return "🎵";
  if (isArchivable(name)) return "📦";
  return "📄";
}

function renderTableView() {
  fileTableBody.innerHTML = "";
  selectAllCheckbox.checked = false;

  const canWrite = state.user.role === "admin" || state.user.role === "editor";
  const isAdmin = state.user.role === "admin";
  const isDeepSearch = Boolean(state.searchQuery || state.favoritesOnly || state.tagFilter);

  if (state.currentPath && !isDeepSearch) {
    const parentPath = state.currentPath.includes("/")
      ? state.currentPath.substring(0, state.currentPath.lastIndexOf("/"))
      : "";
    const upRow = document.createElement("tr");
    upRow.innerHTML = `
      <td></td>
      <td colspan="4">
        <div class="item-cell" id="upDirRow">
          <span class="item-icon folder">📁</span>
          <span class="item-name">.. (Subir nivel)</span>
        </div>
      </td>
    `;
    upRow.querySelector("#upDirRow").addEventListener("click", () => navigateTo(parentPath));
    fileTableBody.appendChild(upRow);
  }

  state.items.forEach((item) => {
    const tr = document.createElement("tr");
    tr.addEventListener("contextmenu", (e) => openContextMenu(e, item));

    // Checkbox
    const checkTd = document.createElement("td");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.selectedPaths.has(item.path);
    cb.addEventListener("change", () => {
      if (cb.checked) state.selectedPaths.add(item.path);
      else state.selectedPaths.delete(item.path);
      updateBulkBar();
    });
    checkTd.appendChild(cb);

    // Nombre + Favorito + Etiquetas + Nota + Candado + Versiones
    const nameTd = document.createElement("td");
    const rowWrap = document.createElement("div");
    rowWrap.className = "item-row-wrap";

    // Botón Estrella Favorito
    const favBtn = document.createElement("button");
    favBtn.className = `fav-star-btn ${item.is_favorite ? "active" : ""}`;
    favBtn.title = item.is_favorite ? "Quitar de Favoritos" : "Agregar a Favoritos";
    favBtn.innerHTML = item.is_favorite ? '<i class="fas fa-star"></i>' : '<i class="far fa-star"></i>';
    favBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavorite(item);
    });
    rowWrap.appendChild(favBtn);

    const cellDiv = document.createElement("div");
    cellDiv.className = "item-cell";
    const iconChar = getFileIconChar(item);
    cellDiv.innerHTML = `<span class="item-icon">${iconChar}</span><span class="item-name"></span>`;
    cellDiv.querySelector(".item-name").textContent = isDeepSearch ? item.path : item.name;
    cellDiv.addEventListener("click", () => {
      if (item.is_dir) {
        searchInput.value = "";
        state.searchQuery = "";
        state.favoritesOnly = false;
        state.tagFilter = "";
        tagFilterSelect.value = "";
        updateFilterBarUI();
        navigateTo(item.path);
      } else {
        openPreview(item);
      }
    });
    rowWrap.appendChild(cellDiv);

    // Badges (Carpeta Privada, Etiquetas, Nota, Versiones)
    const badgesWrap = document.createElement("div");
    badgesWrap.className = "item-badges";

    if (item.is_dir && item.is_restricted) {
      const lockBadge = document.createElement("span");
      lockBadge.className = "meta-badge badge-restricted";
      lockBadge.title = "Carpeta con acceso restringido";
      lockBadge.innerHTML = '<i class="fas fa-lock"></i> Privada';
      badgesWrap.appendChild(lockBadge);
    }

    (item.tags || []).forEach((tag) => {
      const tBadge = document.createElement("span");
      tBadge.className = `meta-badge ${getTagClass(tag)}`;
      tBadge.textContent = tag;
      tBadge.title = `Filtrar por etiqueta: ${tag}`;
      tBadge.addEventListener("click", (e) => {
        e.stopPropagation();
        state.tagFilter = tag;
        tagFilterSelect.value = tag;
        updateFilterBarUI();
        loadFiles();
      });
      badgesWrap.appendChild(tBadge);
    });

    if (item.note) {
      const noteBadge = document.createElement("span");
      noteBadge.className = "meta-badge badge-note";
      noteBadge.title = `Nota: ${item.note}`;
      noteBadge.innerHTML = `<i class="fas fa-comment-dots"></i> ${item.note.length > 26 ? item.note.slice(0, 26) + "…" : item.note}`;
      if (canWrite) {
        noteBadge.addEventListener("click", (e) => {
          e.stopPropagation();
          openMetaModal(item);
        });
      }
      badgesWrap.appendChild(noteBadge);
    }

    if (!item.is_dir && item.versions_count > 0) {
      const verBadge = document.createElement("span");
      verBadge.className = "meta-badge badge-version";
      verBadge.title = `Ver ${item.versions_count} versión(es) anterior(es)`;
      verBadge.innerHTML = `<i class="fas fa-clock-rotate-left"></i> v${item.versions_count + 1}`;
      verBadge.addEventListener("click", (e) => {
        e.stopPropagation();
        openVersionsModal(item);
      });
      badgesWrap.appendChild(verBadge);
    }

    rowWrap.appendChild(badgesWrap);
    nameTd.appendChild(rowWrap);

    // Tamaño y Fecha
    const sizeTd = document.createElement("td");
    sizeTd.className = "col-size";
    sizeTd.textContent = item.is_dir ? "Carpeta" : formatBytes(item.size);

    const dateTd = document.createElement("td");
    dateTd.className = "col-date";
    dateTd.textContent = formatDate(item.mtime);

    // Acciones
    const actionsTd = document.createElement("td");
    actionsTd.className = "col-actions";
    const group = document.createElement("div");
    group.className = "action-group";

    // Descargar
    const dlBtn = createActionBtn("⬇️", item.is_dir ? "Descargar ZIP" : "Descargar", () => {
      window.location.href = item.is_dir
        ? `/api/zip?path=${encodeURIComponent(item.path)}`
        : `/api/download?path=${encodeURIComponent(item.path)}`;
    });
    group.appendChild(dlBtn);

    // Etiquetas y Nota
    if (canWrite) {
      const tagBtn = createActionBtn("🏷️", "Etiquetas y Nota", () => openMetaModal(item));
      group.appendChild(tagBtn);
    }

    // Historial de Versiones (para archivos)
    if (!item.is_dir) {
      const verBtn = createActionBtn("🕓", "Historial de versiones", () => openVersionsModal(item));
      group.appendChild(verBtn);
    }

    // Permisos de Carpeta (solo Admin en carpetas)
    if (isAdmin && item.is_dir) {
      const permBtn = createActionBtn("🔒", "Permisos de acceso a carpeta", () => openPermissionsModal(item));
      group.appendChild(permBtn);
    }

    // Compartir Enlace
    if (canWrite) {
      const shareBtn = createActionBtn("🔗", "Compartir enlace público", () => openShareModal(item));
      group.appendChild(shareBtn);
    }

    // Editar texto
    if (canWrite && !item.is_dir && isTextEditable(item.name, item.mime)) {
      const editBtn = createActionBtn("📝", "Editar texto/código", () => openTextEditor(item.path, item.name));
      group.appendChild(editBtn);
    }

    // Descomprimir ZIP/TAR
    if (canWrite && !item.is_dir && isArchivable(item.name)) {
      const extBtn = createActionBtn("📦", "Extraer aquí", () => extractArchive(item.path));
      group.appendChild(extBtn);
    }

    // Renombrar
    if (canWrite) {
      const renBtn = createActionBtn("✏️", "Renombrar", () => {
        openPromptModal({
          title: "Renombrar",
          label: "Nuevo nombre:",
          defaultValue: item.name,
          onConfirm: (newName) => renameItem(item.path, newName),
        });
      });
      group.appendChild(renBtn);
    }

    // Eliminar (Enviar a Papelera)
    if (isAdmin) {
      const delBtn = createActionBtn("🗑️", "Enviar a la papelera", async () => {
        await deleteItem(item.path, false);
      }, true);
      group.appendChild(delBtn);
    }

    actionsTd.appendChild(group);
    tr.appendChild(checkTd);
    tr.appendChild(nameTd);
    tr.appendChild(sizeTd);
    tr.appendChild(dateTd);
    tr.appendChild(actionsTd);
    fileTableBody.appendChild(tr);
  });
}

function renderGridView() {
  gridViewContainer.innerHTML = "";
  state.items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "grid-card";
    card.addEventListener("contextmenu", (e) => openContextMenu(e, item));

    const thumb = document.createElement("div");
    thumb.className = "grid-thumb";
    if (!item.is_dir && item.mime && item.mime.startsWith("image/")) {
      const img = document.createElement("img");
      img.src = `/api/download?path=${encodeURIComponent(item.path)}&inline=1`;
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      thumb.innerHTML = `<span style="font-size:2.6rem;">${getFileIconChar(item)}</span>`;
    }

    const title = document.createElement("div");
    title.className = "grid-title";
    title.textContent = (item.is_favorite ? "⭐ " : "") + item.name;

    const meta = document.createElement("div");
    meta.className = "grid-meta";
    meta.textContent = item.is_dir
      ? item.is_restricted ? "🔒 Carpeta Privada" : "Carpeta"
      : formatBytes(item.size);

    card.appendChild(thumb);
    card.appendChild(title);
    card.appendChild(meta);

    card.addEventListener("click", () => {
      if (item.is_dir) navigateTo(item.path);
      else openPreview(item);
    });
    gridViewContainer.appendChild(card);
  });
}

function createActionBtn(label, title, onClick, isDanger = false) {
  const btn = document.createElement("button");
  btn.className = `action-btn ${isDanger ? "danger" : ""}`;
  btn.title = title;
  btn.textContent = label;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return btn;
}

function navigateTo(path) {
  state.currentPath = path;
  loadFiles(path, state.searchQuery);
}

// --- Menú Contextual (Clic Derecho) ---
function openContextMenu(e, item) {
  e.preventDefault();
  e.stopPropagation();

  const canWrite = state.user.role === "admin" || state.user.role === "editor";
  const isAdmin = state.user.role === "admin";

  contextMenu.innerHTML = "";
  const actions = [
    {
      label: item.is_dir ? "📂 Abrir carpeta" : "👁️ Vista previa",
      onClick: () => (item.is_dir ? navigateTo(item.path) : openPreview(item)),
    },
    {
      label: item.is_favorite ? "⭐ Quitar de Favoritos" : "⭐ Agregar a Favoritos",
      onClick: () => toggleFavorite(item),
    },
  ];

  if (canWrite) {
    actions.push({
      label: "🏷️ Etiquetas y Nota",
      onClick: () => openMetaModal(item),
    });
  }

  if (!item.is_dir) {
    actions.push({
      label: `🕓 Historial de Versiones (${item.versions_count || 0})`,
      onClick: () => openVersionsModal(item),
    });
  }

  if (isAdmin && item.is_dir) {
    actions.push({
      label: "🔒 Permisos de Acceso",
      onClick: () => openPermissionsModal(item),
    });
  }

  if (canWrite) {
    actions.push({
      label: "🔗 Compartir Enlace Público",
      onClick: () => openShareModal(item),
    });
  }

  if (canWrite && !item.is_dir && isTextEditable(item.name, item.mime)) {
    actions.push({
      label: "📝 Editar Texto / Código",
      onClick: () => openTextEditor(item.path, item.name),
    });
  }

  if (canWrite && !item.is_dir && isArchivable(item.name)) {
    actions.push({
      label: "📦 Extraer Archivo Aquí",
      onClick: () => extractArchive(item.path),
    });
  }

  if (canWrite) {
    actions.push({
      label: "✏️ Renombrar",
      onClick: () =>
        openPromptModal({
          title: "Renombrar",
          label: "Nuevo nombre:",
          defaultValue: item.name,
          onConfirm: (newName) => renameItem(item.path, newName),
        }),
    });
  }

  actions.push({
    label: item.is_dir ? "⬇️ Descargar en ZIP" : "⬇️ Descargar archivo",
    onClick: () => {
      window.location.href = item.is_dir
        ? `/api/zip?path=${encodeURIComponent(item.path)}`
        : `/api/download?path=${encodeURIComponent(item.path)}`;
    },
  });

  if (isAdmin) {
    actions.push({
      label: "🗑️ Enviar a Papelera",
      danger: true,
      onClick: () => deleteItem(item.path, false),
    });
  }

  actions.forEach((act) => {
    const btn = document.createElement("button");
    btn.className = `context-menu-item ${act.danger ? "danger" : ""}`;
    btn.textContent = act.label;
    btn.addEventListener("click", () => {
      closeContextMenu();
      act.onClick();
    });
    contextMenu.appendChild(btn);
  });

  contextMenu.classList.remove("hidden");
  const menuW = 240;
  const menuH = actions.length * 36 + 16;
  const x = Math.min(e.clientX, window.innerWidth - menuW - 12);
  const y = Math.min(e.clientY, window.innerHeight - menuH - 12);
  contextMenu.style.left = `${Math.max(8, x)}px`;
  contextMenu.style.top = `${Math.max(8, y)}px`;
}

function closeContextMenu() {
  contextMenu.classList.add("hidden");
}

window.addEventListener("click", closeContextMenu);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeContextMenu();
});

// --- Favoritos, Etiquetas y Notas ---
async function toggleFavorite(item) {
  const res = await fetch("/api/favorites/toggle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: item.path }),
  });
  const data = await res.json();
  if (res.ok) {
    item.is_favorite = data.is_favorite;
    showToast(data.is_favorite ? "Agregado a Favoritos ⭐" : "Quitado de Favoritos", "info");
    if (state.favoritesOnly && !data.is_favorite) {
      loadFiles();
    } else {
      renderFilesView();
    }
  }
}

function openMetaModal(item) {
  state.metaItem = item;
  metaTargetLabel.textContent = `Elemento: ${item.path}`;
  const currentTags = new Set(item.tags || []);

  document.querySelectorAll("#presetTagsContainer .tag-toggle-btn").forEach((btn) => {
    const tag = btn.dataset.tag;
    btn.classList.toggle("active", currentTags.has(tag));
  });

  const customTags = (item.tags || []).filter((t) => !PRESET_TAGS.includes(t));
  metaCustomTagInput.value = customTags.join(", ");
  metaNoteInput.value = item.note || "";
  metaModal.classList.remove("hidden");
}

document.querySelectorAll("#presetTagsContainer .tag-toggle-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.classList.toggle("active");
  });
});

metaForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.metaItem) return;

  const selectedPresets = [];
  document.querySelectorAll("#presetTagsContainer .tag-toggle-btn.active").forEach((btn) => {
    selectedPresets.push(btn.dataset.tag);
  });

  const customList = metaCustomTagInput.value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  const allTags = Array.from(new Set([...selectedPresets, ...customList]));

  const res = await fetch("/api/metadata/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: state.metaItem.path,
      tags: allTags,
      note: metaNoteInput.value.trim(),
    }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Etiquetas y nota guardadas", "success");
    metaModal.classList.add("hidden");
    loadFiles();
  } else {
    showToast(data.error || "No se pudo guardar", "error");
  }
});

document.getElementById("metaCloseBtn").addEventListener("click", () => metaModal.classList.add("hidden"));
document.getElementById("metaCancelBtn").addEventListener("click", () => metaModal.classList.add("hidden"));

// --- Historial de Versiones ---
async function openVersionsModal(item) {
  versionsTargetLabel.textContent = `Archivo: ${item.path}`;
  versionsTableBody.innerHTML = `<tr><td colspan="5">Cargando versiones...</td></tr>`;
  versionsModal.classList.remove("hidden");

  const res = await fetch(`/api/versions?path=${encodeURIComponent(item.path)}`);
  const data = await res.json();
  versionsTableBody.innerHTML = "";

  if (!res.ok) {
    versionsTableBody.innerHTML = `<tr><td colspan="5">${data.error || "Error al consultar versiones"}</td></tr>`;
    return;
  }

  const versions = data.versions || [];
  if (versions.length === 0) {
    versionsTableBody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align:center; padding: 1.5rem; color: var(--text-muted);">
          Este archivo aún no tiene versiones anteriores registradas.<br>
          <small>Las versiones se guardan automáticamente cada vez que subes un archivo con el mismo nombre o lo editas.</small>
        </td>
      </tr>
    `;
    return;
  }

  const canWrite = state.user.role === "admin" || state.user.role === "editor";

  versions.forEach((v) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${formatDate(v.created_at)}</b></td>
      <td>👤 ${v.created_by}</td>
      <td>${formatBytes(v.size)}</td>
      <td style="color:var(--text-muted)">${v.comment || "Versión histórica"}</td>
      <td class="col-actions">
        <div class="action-group">
          <a class="btn btn-sm btn-outline" href="/api/versions/download?id=${encodeURIComponent(v.id)}" title="Descargar esta versión">⬇️</a>
          ${canWrite ? `<button class="btn btn-sm btn-primary ver-restore-btn" title="Restaurar esta versión">♻️ Restaurar</button>` : ""}
          ${canWrite ? `<button class="action-btn danger ver-del-btn" title="Eliminar versión">🗑️</button>` : ""}
        </div>
      </td>
    `;

    const restBtn = tr.querySelector(".ver-restore-btn");
    if (restBtn) {
      restBtn.addEventListener("click", async () => {
        if (!confirm("¿Restaurar esta versión? El archivo actual se guardará automáticamente como respaldo antes de restaurar.")) return;
        const r = await fetch("/api/versions/restore", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: v.id }),
        });
        if (r.ok) {
          showToast("Versión restaurada con éxito", "success");
          openVersionsModal(item);
          loadFiles();
        } else {
          showToast("No se pudo restaurar la versión", "error");
        }
      });
    }

    const delBtn = tr.querySelector(".ver-del-btn");
    if (delBtn) {
      delBtn.addEventListener("click", async () => {
        const r = await fetch("/api/versions/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: v.id }),
        });
        if (r.ok) {
          showToast("Versión eliminada", "info");
          openVersionsModal(item);
          loadFiles();
        }
      });
    }

    versionsTableBody.appendChild(tr);
  });
}

document.getElementById("versionsCloseBtn").addEventListener("click", () => versionsModal.classList.add("hidden"));
document.getElementById("versionsCloseFooterBtn").addEventListener("click", () => versionsModal.classList.add("hidden"));

// --- Permisos de Carpeta (ACL Admin) ---
async function openPermissionsModal(item) {
  state.permItem = item;
  permTargetLabel.textContent = `Carpeta: /${item.path}`;
  permissionsModal.classList.remove("hidden");

  const res = await fetch(`/api/permissions?path=${encodeURIComponent(item.path)}`);
  const data = await res.json();
  if (!res.ok) {
    showToast(data.error || "Error al cargar permisos", "error");
    return;
  }

  const perm = data.permission || {};
  permRestrictCheck.checked = Boolean(perm.is_restricted);
  const allowedRoles = new Set(perm.allowed_roles || ["admin"]);
  const allowedUsers = new Set(perm.allowed_users || []);

  document.querySelectorAll(".perm-role-cb").forEach((cb) => {
    cb.checked = allowedRoles.has(cb.value);
  });

  permUsersList.innerHTML = "";
  (data.users || []).forEach((u) => {
    const lbl = document.createElement("label");
    lbl.className = "checkbox-pill";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "perm-user-cb";
    cb.value = u;
    cb.checked = allowedUsers.has(u);
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(` 👤 ${u}`));
    permUsersList.appendChild(lbl);
  });
}

permForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.permItem) return;

  const allowedRoles = ["admin"];
  document.querySelectorAll(".perm-role-cb:checked").forEach((cb) => allowedRoles.push(cb.value));

  const allowedUsers = [];
  document.querySelectorAll(".perm-user-cb:checked").forEach((cb) => allowedUsers.push(cb.value));

  const res = await fetch("/api/permissions/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: state.permItem.path,
      is_restricted: permRestrictCheck.checked,
      allowed_roles: allowedRoles,
      allowed_users: allowedUsers,
    }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Permisos de carpeta actualizados", "success");
    permissionsModal.classList.add("hidden");
    loadFiles();
  } else {
    showToast(data.error || "No se pudieron guardar los permisos", "error");
  }
});

document.getElementById("permCloseBtn").addEventListener("click", () => permissionsModal.classList.add("hidden"));
document.getElementById("permCancelBtn").addEventListener("click", () => permissionsModal.classList.add("hidden"));

// --- Dashboard de Estadísticas de Almacenamiento ---
async function loadStats() {
  const kpiGrid = document.getElementById("statsKpiGrid");
  const catList = document.getElementById("statsCategoriesList");
  const largestBody = document.getElementById("statsLargestTableBody");

  kpiGrid.innerHTML = `<div class="card">Calculando estadísticas...</div>`;
  const res = await fetch("/api/stats");
  if (!res.ok) return;
  const data = await res.json();

  kpiGrid.innerHTML = `
    <div class="card kpi-card">
      <div class="kpi-label">Espacio en Repositorio</div>
      <div class="kpi-value">${formatBytes(data.total_bytes)}</div>
      <div class="kpi-sub">${data.total_files} archivos en ${data.total_dirs} carpetas</div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-label">Espacio Libre en Disco</div>
      <div class="kpi-value">${formatBytes(data.disk.free)}</div>
      <div class="kpi-sub">Total disco: ${formatBytes(data.disk.total)}</div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-label">Historial de Versiones</div>
      <div class="kpi-value">${formatBytes(data.versions_bytes)}</div>
      <div class="kpi-sub">Respaldos automáticos (.versions)</div>
    </div>
    <div class="card kpi-card">
      <div class="kpi-label">Papelera de Reciclaje</div>
      <div class="kpi-value">${formatBytes(data.trash_bytes)}</div>
      <div class="kpi-sub">Archivos pendientes de vaciar</div>
    </div>
  `;

  catList.innerHTML = "";
  const totalB = Math.max(1, data.total_bytes);
  Object.values(data.categories || {}).forEach((cat) => {
    const pct = Math.min(100, Math.round((cat.bytes / totalB) * 100));
    const row = document.createElement("div");
    row.className = "stat-cat-row";
    row.innerHTML = `
      <div class="stat-cat-header">
        <span><b>${cat.label}</b> (${cat.count} archivos)</span>
        <span>${formatBytes(cat.bytes)} (${pct}%)</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" style="width: ${pct}%"></div>
      </div>
    `;
    catList.appendChild(row);
  });

  largestBody.innerHTML = "";
  (data.largest_files || []).forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${f.name}</b><br><small style="color:var(--text-muted)">/${f.path}</small></td>
      <td class="col-size">${formatBytes(f.size)}</td>
      <td class="col-actions">
        <a class="action-btn" href="/api/download?path=${encodeURIComponent(f.path)}" title="Descargar">⬇️</a>
      </td>
    `;
    largestBody.appendChild(tr);
  });
}

document.getElementById("refreshStatsBtn").addEventListener("click", loadStats);

// --- Selección Múltiple y Operaciones Masivas ---
selectAllCheckbox.addEventListener("change", () => {
  if (selectAllCheckbox.checked) {
    state.items.forEach((i) => state.selectedPaths.add(i.path));
  } else {
    state.selectedPaths.clear();
  }
  renderTableView();
  updateBulkBar();
});

function updateBulkBar() {
  const count = state.selectedPaths.size;
  bulkBar.classList.toggle("hidden", count === 0);
  bulkCount.textContent = `${count} seleccionado${count === 1 ? "" : "s"}`;
}

bulkClearBtn.addEventListener("click", () => {
  state.selectedPaths.clear();
  renderTableView();
  updateBulkBar();
});

bulkDeleteBtn.addEventListener("click", async () => {
  const paths = Array.from(state.selectedPaths);
  if (!paths.length) return;
  const res = await fetch("/api/bulk/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast(`${data.deleted} elementos movidos a la papelera`, "success");
    loadFiles();
  } else {
    showToast(data.error || "Error al eliminar", "error");
  }
});

bulkMoveBtn.addEventListener("click", () => {
  const paths = Array.from(state.selectedPaths);
  openPromptModal({
    title: "Mover elementos seleccionados",
    label: "Ruta de carpeta destino (vacío para raíz /):",
    defaultValue: state.currentPath,
    onConfirm: async (dest) => {
      const res = await fetch("/api/bulk/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths, destination: dest === "/" ? "" : dest }),
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`${data.moved} elementos movidos`, "success");
        loadFiles();
      } else {
        showToast(data.error || "No se pudo mover", "error");
      }
    },
  });
});

bulkZipBtn.addEventListener("click", async () => {
  const paths = Array.from(state.selectedPaths);
  if (!paths.length) return;
  const res = await fetch("/api/bulk/zip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
  });
  if (!res.ok) {
    showToast("No se pudo generar el ZIP", "error");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "seleccion.zip";
  a.click();
  URL.revokeObjectURL(url);
});

// --- Operaciones Individuales ---
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

async function deleteItem(path, permanent = false) {
  const res = await fetch("/api/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, permanent }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Movido a la papelera", "success");
    loadFiles();
  } else {
    showToast(data.error || "No se pudo eliminar", "error");
  }
}

async function extractArchive(path) {
  showToast("Extrayendo archivo...", "info");
  const res = await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast(`Extraído en ${data.extracted_to}`, "success");
    loadFiles();
  } else {
    showToast(data.error || "Error al descomprimir", "error");
  }
}

// --- Editor de Texto / Código ---
async function openTextEditor(relPath, displayName, isNew = false) {
  state.editingPath = relPath;
  editorTitle.textContent = `📝 ${displayName}`;
  editorTextarea.value = "";
  editorModal.classList.remove("hidden");

  if (!isNew) {
    try {
      const res = await fetch(`/api/download?path=${encodeURIComponent(relPath)}&inline=1`);
      if (res.ok) {
        editorTextarea.value = await res.text();
      }
    } catch (_) {}
  }
  editorTextarea.focus();
}

editorSaveBtn.addEventListener("click", async () => {
  if (!state.editingPath) return;
  const res = await fetch("/api/save-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: state.editingPath, content: editorTextarea.value }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Archivo guardado (versión anterior respaldada)", "success");
    editorModal.classList.add("hidden");
    loadFiles();
  } else {
    showToast(data.error || "Error al guardar", "error");
  }
});

document.getElementById("editorCloseBtn").addEventListener("click", () => editorModal.classList.add("hidden"));
document.getElementById("editorCancelBtn").addEventListener("click", () => editorModal.classList.add("hidden"));

newTextFileBtn.addEventListener("click", () => {
  openPromptModal({
    title: "Nuevo Archivo de Texto",
    label: "Nombre del archivo (ej. notas.md o planilla.csv):",
    defaultValue: "notas.txt",
    onConfirm: (fileName) => {
      const fullRel = state.currentPath ? `${state.currentPath}/${fileName}` : fileName;
      openTextEditor(fullRel, fileName, true);
    },
  });
});

// --- Enlaces Públicos (Compartir) ---
function openShareModal(item) {
  state.sharingPath = item.path;
  shareTargetLabel.textContent = `Elemento: ${item.path}`;
  shareHoursInput.value = "";
  shareMaxDlInput.value = "";
  sharePasswordInput.value = "";
  shareResultBox.classList.add("hidden");
  shareModal.classList.remove("hidden");
}

shareForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const res = await fetch("/api/shares/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: state.sharingPath,
      expires_hours: shareHoursInput.value || null,
      max_downloads: shareMaxDlInput.value || null,
      password: sharePasswordInput.value || null,
    }),
  });
  const data = await res.json();
  if (res.ok) {
    const fullUrl = `${window.location.origin}/s/${data.share.token}`;
    shareResultUrl.value = fullUrl;
    shareResultBox.classList.remove("hidden");
    navigator.clipboard?.writeText(fullUrl).catch(() => {});
    showToast("Enlace público generado", "success");
  } else {
    showToast(data.error || "Error al crear enlace", "error");
  }
});

document.getElementById("shareCloseBtn").addEventListener("click", () => shareModal.classList.add("hidden"));
document.getElementById("shareCancelBtn").addEventListener("click", () => shareModal.classList.add("hidden"));

async function loadShares() {
  const res = await fetch("/api/shares");
  if (!res.ok) return;
  const data = await res.json();
  const tbody = document.getElementById("sharesTableBody");
  tbody.innerHTML = "";
  (data.items || []).forEach((s) => {
    const url = `${window.location.origin}/s/${s.token}`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${s.path}</b></td>
      <td><a href="${url}" target="_blank">${url}</a></td>
      <td>${s.downloads}${s.max_downloads ? ` / ${s.max_downloads}` : " (ilimitado)"}</td>
      <td>${s.expires_at ? formatDate(s.expires_at) : "Nunca"}</td>
      <td>${s.has_password ? "🔒 Sí" : "Libre"}</td>
      <td class="col-actions"><button class="action-btn danger">🗑️ Revocar</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async () => {
      await fetch("/api/shares/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: s.token }),
      });
      showToast("Enlace revocado", "success");
      loadShares();
    });
    tbody.appendChild(tr);
  });
}

// --- Papelera (Trash) ---
async function loadTrash() {
  const res = await fetch("/api/trash");
  if (!res.ok) return;
  const data = await res.json();
  const tbody = document.getElementById("trashTableBody");
  tbody.innerHTML = "";
  (data.items || []).forEach((t) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${t.is_dir ? "📁" : "📄"} <b>${t.name}</b></td>
      <td>${t.orig_path}</td>
      <td>${formatBytes(t.size)}</td>
      <td>${t.deleted_by}</td>
      <td>${formatDate(t.deleted_at)}</td>
      <td class="col-actions"><button class="btn btn-sm btn-primary">♻️ Restaurar</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async () => {
      const r = await fetch("/api/trash/restore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: t.id }),
      });
      if (r.ok) {
        showToast("Elemento restaurado", "success");
        loadTrash();
      } else {
        showToast("No se pudo restaurar", "error");
      }
    });
    tbody.appendChild(tr);
  });
}

document.getElementById("emptyTrashBtn").addEventListener("click", async () => {
  if (!confirm("¿Vaciar toda la papelera de forma permanente?")) return;
  const res = await fetch("/api/trash/empty", { method: "POST" });
  if (res.ok) {
    showToast("Papelera vaciada", "success");
    loadTrash();
  }
});

// --- Usuarios (Admin) ---
async function loadUsers() {
  const res = await fetch("/api/users");
  if (!res.ok) return;
  const data = await res.json();
  const tbody = document.getElementById("usersTableBody");
  tbody.innerHTML = "";
  (data.items || []).forEach((u) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>👤 ${u.username}</b></td>
      <td>${u.role.toUpperCase()}</td>
      <td>${formatDate(u.created_at)}</td>
      <td class="col-actions">
        <button class="action-btn edit-u">✏️ Editar</button>
        <button class="action-btn danger del-u">🗑️ Eliminar</button>
      </td>
    `;
    tr.querySelector(".edit-u").addEventListener("click", () => {
      userFormName.value = u.username;
      userFormPass.value = "";
      userFormRole.value = u.role;
      userModal.classList.remove("hidden");
    });
    tr.querySelector(".del-u").addEventListener("click", async () => {
      if (!confirm(`¿Eliminar al usuario "${u.username}"?`)) return;
      const r = await fetch("/api/users/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u.username }),
      });
      const d = await r.json();
      if (r.ok) {
        showToast("Usuario eliminado", "success");
        loadUsers();
      } else {
        showToast(d.error || "No se pudo eliminar", "error");
      }
    });
    tbody.appendChild(tr);
  });
}

document.getElementById("newUserBtn").addEventListener("click", () => {
  userFormName.value = "";
  userFormPass.value = "";
  userFormRole.value = "viewer";
  userModal.classList.remove("hidden");
});

userForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const res = await fetch("/api/users/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: userFormName.value.trim(),
      password: userFormPass.value,
      role: userFormRole.value,
    }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Usuario guardado", "success");
    userModal.classList.add("hidden");
    loadUsers();
  } else {
    showToast(data.error || "Error al guardar usuario", "error");
  }
});

document.getElementById("userCloseBtn").addEventListener("click", () => userModal.classList.add("hidden"));
document.getElementById("userCancelBtn").addEventListener("click", () => userModal.classList.add("hidden"));

// --- Auditoría (Admin) ---
async function loadAudit() {
  const res = await fetch("/api/audit");
  if (!res.ok) return;
  const data = await res.json();
  const tbody = document.getElementById("auditTableBody");
  tbody.innerHTML = "";
  (data.items || []).forEach((log) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="col-date">${formatDate(log.timestamp)}</td>
      <td><b>${log.username}</b></td>
      <td><code>${log.ip}</code></td>
      <td>${log.action}</td>
      <td>${log.target}</td>
      <td style="color:var(--text-muted)">${log.details || ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById("refreshAuditBtn").addEventListener("click", loadAudit);

// --- Subida de Archivos ---
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
  showToast(files.length === 1 ? "Archivo subido" : `${files.length} archivos subidos`, "success");
  fileInput.value = "";
  loadFiles();
}

function uploadSingleFile(file, relName) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const params = new URLSearchParams({ path: state.currentPath, filename: relName });
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
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else {
        let errMsg = "Fallo en la subida";
        try {
          errMsg = JSON.parse(xhr.responseText).error || errMsg;
        } catch (_) {}
        reject(new Error(errMsg));
      }
    };
    xhr.onerror = () => reject(new Error("Error de red"));
    xhr.send(file);
  });
}

// --- Modal Prompt ---
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
  const cb = promptCallback;
  closePromptModal();
  if (cb) await cb(val);
});

document.getElementById("promptCloseBtn").addEventListener("click", closePromptModal);
document.getElementById("promptCancelBtn").addEventListener("click", closePromptModal);

// --- Vista Previa (Imagen, Video/Audio Range, PDF, Excel/CSV, Word, Texto) ---
function renderSpreadsheetPreview(sheets) {
  const wrapper = document.createElement("div");
  wrapper.className = "office-viewer-wrap";

  const tabsBar = document.createElement("div");
  tabsBar.className = "office-tabs-bar";

  const filterInput = document.createElement("input");
  filterInput.type = "search";
  filterInput.className = "office-filter-input";
  filterInput.placeholder = "Filtrar filas en esta hoja...";

  const tableHost = document.createElement("div");
  tableHost.className = "office-table-host";

  let activeIdx = 0;

  function drawSheet(idx) {
    activeIdx = idx;
    tabsBar.querySelectorAll(".office-tab-btn").forEach((b, i) => b.classList.toggle("active", i === idx));
    const sheet = sheets[idx] || { rows: [] };
    const rows = sheet.rows || [];
    const q = filterInput.value.trim().toLowerCase();

    tableHost.innerHTML = "";
    if (rows.length === 0) {
      tableHost.innerHTML = `<p style="padding:1.5rem; color:var(--text-muted);">Esta hoja está vacía.</p>`;
      return;
    }

    const tbl = document.createElement("table");
    tbl.className = "office-grid-table";

    const thead = document.createElement("thead");
    const headTr = document.createElement("tr");
    const firstRow = rows[0] || [];
    firstRow.forEach((cellVal, cIdx) => {
      const th = document.createElement("th");
      th.textContent = cellVal !== "" ? cellVal : `Col ${cIdx + 1}`;
      headTr.appendChild(th);
    });
    thead.appendChild(headTr);
    tbl.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.slice(1).forEach((r) => {
      if (q && !r.some((c) => String(c).toLowerCase().includes(q))) return;
      const tr = document.createElement("tr");
      firstRow.forEach((_, cIdx) => {
        const td = document.createElement("td");
        td.textContent = r[cIdx] !== undefined ? r[cIdx] : "";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    tableHost.appendChild(tbl);
  }

  sheets.forEach((sh, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `office-tab-btn ${idx === 0 ? "active" : ""}`;
    btn.innerHTML = `<i class="fas fa-table"></i> ${sh.name}`;
    btn.addEventListener("click", () => drawSheet(idx));
    tabsBar.appendChild(btn);
  });

  tabsBar.appendChild(filterInput);
  filterInput.addEventListener("input", () => drawSheet(activeIdx));

  wrapper.appendChild(tabsBar);
  wrapper.appendChild(tableHost);
  drawSheet(0);
  return wrapper;
}

function renderDocxPreview(blocks) {
  const page = document.createElement("div");
  page.className = "docx-page-preview";

  if (!blocks || blocks.length === 0) {
    page.innerHTML = `<p style="color:var(--text-muted);">El documento no contiene texto visible.</p>`;
    return page;
  }

  blocks.forEach((b) => {
    if (b.type === "h1" || b.type === "h2" || b.type === "h3") {
      const h = document.createElement(b.type);
      h.textContent = b.text;
      page.appendChild(h);
    } else if (b.type === "p") {
      const p = document.createElement("p");
      p.textContent = b.text;
      page.appendChild(p);
    } else if (b.type === "table") {
      const tbl = document.createElement("table");
      tbl.className = "office-grid-table";
      (b.rows || []).forEach((r, rIdx) => {
        const tr = document.createElement("tr");
        r.forEach((c) => {
          const cell = document.createElement(rIdx === 0 ? "th" : "td");
          cell.textContent = c;
          tr.appendChild(cell);
        });
        tbl.appendChild(tr);
      });
      page.appendChild(tbl);
    }
  });
  return page;
}

async function openPreview(item) {
  const inlineUrl = `/api/download?path=${encodeURIComponent(item.path)}&inline=1`;
  const downloadUrl = `/api/download?path=${encodeURIComponent(item.path)}`;

  previewTitle.textContent = item.name;
  previewDownloadBtn.href = downloadUrl;
  previewContent.innerHTML = "";
  previewModal.classList.remove("hidden");

  const mime = item.mime || "";
  const canWrite = state.user.role === "admin" || state.user.role === "editor";
  const editable = isTextEditable(item.name, mime);

  previewEditBtn.classList.toggle("hidden", !(canWrite && editable));
  previewEditBtn.onclick = () => {
    previewModal.classList.add("hidden");
    openTextEditor(item.path, item.name);
  };

  if (isOfficePreviewable(item.name)) {
    previewContent.innerHTML = `<p style="padding:1.5rem;">Cargando documento Office...</p>`;
    try {
      const res = await fetch(`/api/office-preview?path=${encodeURIComponent(item.path)}`);
      const data = await res.json();
      previewContent.innerHTML = "";
      if (!res.ok) {
        previewContent.innerHTML = `<p style="padding:1.5rem;">${data.error || "Error al abrir vista previa."}</p>`;
        return;
      }
      if (data.type === "spreadsheet") {
        previewContent.appendChild(renderSpreadsheetPreview(data.sheets || []));
      } else if (data.type === "document") {
        previewContent.appendChild(renderDocxPreview(data.blocks || []));
      }
    } catch (_) {
      previewContent.innerHTML = `<p style="padding:1.5rem;">No se pudo procesar el documento.</p>`;
    }
    return;
  }

  if (mime.startsWith("image/")) {
    const img = document.createElement("img");
    img.src = inlineUrl;
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
  } else if (mime === "application/pdf" || item.name.toLowerCase().endsWith(".pdf")) {
    const iframe = document.createElement("iframe");
    iframe.src = inlineUrl;
    previewContent.appendChild(iframe);
  } else if (editable) {
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
        <p>Vista previa no disponible para (${mime}).</p>
        <p style="color: var(--text-muted); font-size: 0.88rem; margin-top:0.4rem;">Tamaño: ${formatBytes(item.size)}</p>
      </div>
    `;
  }
}

document.getElementById("previewCloseBtn").addEventListener("click", () => {
  previewContent.innerHTML = "";
  previewModal.classList.add("hidden");
});

// --- Eventos de Barra de Herramientas ---
uploadBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => uploadFiles(e.target.files));

newFolderBtn.addEventListener("click", () => {
  openPromptModal({
    title: "Nueva Carpeta",
    label: "Nombre de la carpeta:",
    onConfirm: (folderName) => {
      if (folderName) createFolder(folderName);
    },
  });
});

downloadZipBtn.addEventListener("click", () => {
  window.location.href = `/api/zip?path=${encodeURIComponent(state.currentPath)}`;
});

viewModeBtn.addEventListener("click", () => {
  state.viewMode = state.viewMode === "grid" ? "table" : "grid";
  localStorage.setItem("fs_view", state.viewMode);
  renderFilesView();
});

brandHome.addEventListener("click", () => {
  searchInput.value = "";
  state.searchQuery = "";
  state.favoritesOnly = false;
  state.tagFilter = "";
  tagFilterSelect.value = "";
  updateFilterBarUI();
  switchTab("files");
  navigateTo("");
});

let searchTimeout = null;
searchInput.addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    state.searchQuery = e.target.value.trim();
    if (state.activeTab !== "files") switchTab("files");
    else loadFiles(state.currentPath, state.searchQuery);
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
window.addEventListener("dragover", (e) => e.preventDefault());
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
  if (e.dataTransfer?.files?.length > 0) {
    uploadFiles(e.dataTransfer.files);
  }
});

// --- Inicio ---
initTheme();
initAuth().then(() => loadFiles());
