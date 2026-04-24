const datasetSelect = document.getElementById("datasetSelect");
const toggleDatasetFormBtn = document.getElementById("toggleDatasetFormBtn");
const datasetFormPanel = document.getElementById("datasetFormPanel");
const datasetNameInput = document.getElementById("datasetNameInput");
const datasetRootInput = document.getElementById("datasetRootInput");
const datasetSplitsInput = document.getElementById("datasetSplitsInput");
const datasetImageDirInput = document.getElementById("datasetImageDirInput");
const datasetGtFilesInput = document.getElementById("datasetGtFilesInput");
const datasetSeqinfoInput = document.getElementById("datasetSeqinfoInput");
const datasetGameinfoInput = document.getElementById("datasetGameinfoInput");
const datasetSaveBtn = document.getElementById("datasetSaveBtn");
const datasetCancelBtn = document.getElementById("datasetCancelBtn");
const datasetFormStatus = document.getElementById("datasetFormStatus");
const splitSelect = document.getElementById("splitSelect");
const seqSelect = document.getElementById("seqSelect");
const annotationTypeSelect = document.getElementById("annotationTypeSelect");
const annotationFileSelect = document.getElementById("annotationFileSelect");
const annotationHint = document.getElementById("annotationHint");
const frameSlider = document.getElementById("frameSlider");
const frameHint = document.getElementById("frameHint");

const showGT = document.getElementById("showGT");
const showBBox = document.getElementById("showBBox");
const showID = document.getElementById("showID");
const showVis = document.getElementById("showVis");
const highlightVis = document.getElementById("highlightVis");

const boxColor = document.getElementById("boxColor");
const visColor = document.getElementById("visColor");
const frameInput = document.getElementById("frameInput");
const goBtn = document.getElementById("goBtn");

const visList = document.getElementById("visList");

const refreshBtn = document.getElementById("refreshBtn");
const statusText = document.getElementById("statusText");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const playBtn = document.getElementById("playBtn");
const stopBtn = document.getElementById("stopBtn");
const playbackSpeed = document.getElementById("playbackSpeed");
const speedHint = document.getElementById("speedHint");
const viewerInfo = document.getElementById("viewerInfo");
const hoverInfo = document.getElementById("hoverInfo");

const gameinfoBox = document.getElementById("gameinfoBox");
const seqinfoBox = document.getElementById("seqinfoBox");
const lockedBoxInfo = document.getElementById("lockedBoxInfo");
const zoomInput = document.getElementById("zoomInput");
const zoomResetBtn = document.getElementById("zoomResetBtn");
const zoomHint = document.getElementById("zoomHint");
const minimapCanvas = document.getElementById("minimapCanvas");
const minimapRect = document.getElementById("minimapRect");

// Canvas
const canvas = document.getElementById("frameCanvas");
const ctx = canvas.getContext("2d");
const minimapCtx = minimapCanvas.getContext("2d");

let lastFrameInfo = null;
let currentImage = null;
let currentBoxes = [];
let currentMotFrame = null;
let hoveredIndex = -1;
let lockedBoxIndex = -1;

// Playback state
let isPlaying = false;
let playbackIntervalId = null;

// Zoom and pan state
let zoomLevel = 1.0; // 1.0 = 100%
let panX = 0; // image-space x coordinate at the viewport center
let panY = 0;
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;

// Zoom control mode
let zoomMode = "pan"; // "pan", "magnify", "rect"
let rectSelectStartX = 0;
let rectSelectStartY = 0;
let isRectSelecting = false;

const EPS_VIS = 1e-6;

// text size
const ID_FONT_PX = 18;
const VIS_FONT_PX = 18;

// hover dark overlay alpha
const HOVER_OVERLAY_ALPHA = 0.35;

// dim factor for other boxes when hover
const DIM_FACTOR = 0.25;

// stroke widths
const STROKE_W_NORMAL = 2;
const STROKE_W_HOVER = 4;

// ---- helpers ----
function setStatus(s) {
  statusText.textContent = s;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

async function postJSON(url, payload) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Request failed");
  return data;
}

function getRadio(name, fallback) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : fallback;
}

function throttle(fn, waitMs) {
  let last = 0;
  let timer = null;
  return function (...args) {
    const now = Date.now();
    const remaining = waitMs - (now - last);
    if (remaining <= 0) {
      last = now;
      fn.apply(this, args);
    } else {
      clearTimeout(timer);
      timer = setTimeout(() => {
        last = Date.now();
        fn.apply(this, args);
      }, remaining);
    }
  };
}

function hexToRgb(hex) {
  let s = (hex || "").trim();
  if (s.startsWith("#")) s = s.slice(1);
  if (s.length !== 6) return { r: 0, g: 255, b: 0 };
  return {
    r: parseInt(s.slice(0, 2), 16),
    g: parseInt(s.slice(2, 4), 16),
    b: parseInt(s.slice(4, 6), 16),
  };
}

function clamp01(x) {
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function visIsNot1(vis) {
  return typeof vis === "number" && vis >= 0 && Math.abs(vis - 1.0) > EPS_VIS;
}

function getParams() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value;
  const annotationType = annotationTypeSelect.value;
  const annotationFile = annotationFileSelect.value;
  const frame_idx = frameSlider.value;

  const params = new URLSearchParams();
  params.set("dataset", dataset);
  params.set("split", split);
  params.set("seq", seq);
  params.set("annotation_type", annotationType);
  if (annotationFile) params.set("annotation_file", annotationFile);
  params.set("frame_idx", frame_idx);

  params.set("frame_mode", getRadio("frameMode", "idx")); // idx|mot
  params.set("frame_value", frameInput.value || "");

  return params;
}

function updateNavUI() {
  const idx = parseInt(frameSlider.value || "0", 10);
  const maxV = parseInt(frameSlider.max || "0", 10);

  prevBtn.disabled = idx <= 0;
  nextBtn.disabled = idx >= maxV;

  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value || "(no seq)";
  const annotationLabel = `${annotationTypeSelect.value}:${annotationFileSelect.value || "-"}`;
  viewerInfo.textContent = `${dataset}/${split}/${seq} | ${annotationLabel} | frame_idx: ${idx} / ${maxV} | mot: ${currentMotFrame ?? "-"}`;
}

function updateFrameHint() {
  const idx = parseInt(frameSlider.value || "0", 10);
  if (lastFrameInfo && lastFrameInfo.min_frame !== undefined) {
    const estMot = lastFrameInfo.min_frame + idx;
    frameHint.textContent = `frame_idx: ${idx} (est mot: ${estMot})`;
  } else {
    frameHint.textContent = `frame_idx: ${idx}`;
  }
  updateNavUI();
}

// ---- playback control ----
function startPlayback() {
  const maxV = parseInt(frameSlider.max || "0", 10);
  if (maxV <= 0) return;

  isPlaying = true;
  playBtn.disabled = true;
  stopBtn.disabled = false;
  
  // Get frame rate from seqinfo if available, default to 30fps
  const frameRate = (seqinfoBox && seqinfoBox.textContent) ? 30 : 30;
  const speed = parseFloat(playbackSpeed.value) || 1;
  const interval = (1000 / frameRate) / speed;

  playbackIntervalId = setInterval(() => {
    const idx = parseInt(frameSlider.value || "0", 10);
    if (idx >= maxV) {
      // Loop back to start
      frameSlider.value = 0;
    } else {
      frameSlider.value = idx + 1;
    }
    updateFrameHint();
    loadFrameImageAndBoxes();
  }, interval);
}

function stopPlayback() {
  isPlaying = false;
  if (playbackIntervalId !== null) {
    clearInterval(playbackIntervalId);
    playbackIntervalId = null;
  }
  playBtn.disabled = false;
  stopBtn.disabled = true;
}

function updatePlaybackSpeed() {
  const speed = parseFloat(playbackSpeed.value) || 1;
  speedHint.textContent = `${speed}x`;
  
  // If playing, restart with new speed
  if (isPlaying) {
    stopPlayback();
    startPlayback();
  }
}

// ---- locked box info ----
function updateLockedBoxInfo() {
  if (lockedBoxIndex < 0 || lockedBoxIndex >= currentBoxes.length) {
    const placeholder = `
      <table class="boxTable">
        <tr><td>ID</td><td>-</td></tr>
        <tr><td>X1</td><td>-</td><td>Y1</td><td>-</td></tr>
        <tr><td>X2</td><td>-</td><td>Y2</td><td>-</td></tr>
        <tr><td>Width</td><td>-</td></tr>
        <tr><td>Height</td><td>-</td></tr>
        <tr><td>Visibility</td><td>-</td></tr>
      </table>
    `;
    lockedBoxInfo.innerHTML = placeholder;
    return;
  }

  const box = currentBoxes[lockedBoxIndex];
  const html = `
    <table class="boxTable">
      <tr><td>ID</td><td>${box.id}</td></tr>
      <tr><td>X1</td><td>${box.x1.toFixed(2)}</td><td>Y1</td><td>${box.y1.toFixed(2)}</td></tr>
      <tr><td>X2</td><td>${box.x2.toFixed(2)}</td><td>Y2</td><td>${box.y2.toFixed(2)}</td></tr>
      <tr><td>Width</td><td>${(box.x2 - box.x1).toFixed(2)}</td></tr>
      <tr><td>Height</td><td>${(box.y2 - box.y1).toFixed(2)}</td></tr>
      <tr><td>Visibility</td><td>${typeof box.vis === "number" && box.vis >= 0 ? box.vis.toFixed(2) : "N/A"}</td></tr>
    </table>
  `;
  lockedBoxInfo.innerHTML = html;
}

// ---- zoom control ----
function getImageCenter() {
  if (!currentImage) return { x: 0, y: 0 };
  return {
    x: currentImage.naturalWidth / 2,
    y: currentImage.naturalHeight / 2,
  };
}

function clampPan() {
  if (!currentImage) return;

  const imgW = currentImage.naturalWidth;
  const imgH = currentImage.naturalHeight;
  const halfViewW = canvas.width / (2 * zoomLevel);
  const halfViewH = canvas.height / (2 * zoomLevel);

  if (imgW <= 2 * halfViewW) {
    panX = imgW / 2;
  } else {
    panX = Math.max(halfViewW, Math.min(imgW - halfViewW, panX));
  }

  if (imgH <= 2 * halfViewH) {
    panY = imgH / 2;
  } else {
    panY = Math.max(halfViewH, Math.min(imgH - halfViewH, panY));
  }
}

function setZoomLevel(newZoom, anchorCanvasX = canvas.width / 2, anchorCanvasY = canvas.height / 2) {
  const oldZoom = zoomLevel;
  const clampedZoom = Math.max(1.0, Math.min(4.0, newZoom));

  if (!currentImage) {
    zoomLevel = clampedZoom;
    zoomInput.value = Math.round(zoomLevel * 100);
    zoomHint.textContent = `${Math.round(zoomLevel * 100)}%`;
    return;
  }

  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;

  const imageX = (anchorCanvasX - centerX) / oldZoom + panX;
  const imageY = (anchorCanvasY - centerY) / oldZoom + panY;

  zoomLevel = clampedZoom;
  panX = imageX - (anchorCanvasX - centerX) / zoomLevel;
  panY = imageY - (anchorCanvasY - centerY) / zoomLevel;
  clampPan();

  zoomInput.value = Math.round(zoomLevel * 100);
  zoomHint.textContent = `${Math.round(zoomLevel * 100)}%`;
}

function applyZoom() {
  const val = parseInt(zoomInput.value || "100", 10);
  const percent = Math.max(10, Math.min(400, val));
  setZoomLevel(percent / 100);
  drawScene();
  updateMinimap();
  updateMinimapVisibility();
}

function resetZoom() {
  zoomLevel = 1.0;
  const center = getImageCenter();
  panX = center.x;
  panY = center.y;
  zoomInput.value = 100;
  zoomHint.textContent = "100%";
  drawScene();
  updateMinimap();
  updateMinimapVisibility();
}

// ---- minimap ----
function updateMinimap() {
  if (!currentImage) return;

  const mmWidth = minimapCanvas.width = 160;
  const mmHeight = minimapCanvas.height = 90;
  
  const imgAspect = currentImage.naturalWidth / currentImage.naturalHeight;
  let mmImgWidth, mmImgHeight;
  
  if (imgAspect > 16/9) {
    mmImgWidth = mmWidth;
    mmImgHeight = mmWidth / imgAspect;
  } else {
    mmImgHeight = mmHeight;
    mmImgWidth = mmHeight * imgAspect;
  }
  
  const mmOffsetX = (mmWidth - mmImgWidth) / 2;
  const mmOffsetY = (mmHeight - mmImgHeight) / 2;
  
  // Draw image on minimap
  minimapCtx.clearRect(0, 0, mmWidth, mmHeight);
  minimapCtx.drawImage(currentImage, mmOffsetX, mmOffsetY, mmImgWidth, mmImgHeight);
  
  // Draw rectangle showing viewport
  if (zoomLevel > 1) {
    const viewportWidth = mmImgWidth / zoomLevel;
    const viewportHeight = mmImgHeight / zoomLevel;
    const rectCenterX = mmOffsetX + (panX / currentImage.naturalWidth) * mmImgWidth;
    const rectCenterY = mmOffsetY + (panY / currentImage.naturalHeight) * mmImgHeight;
    const rectX = rectCenterX - viewportWidth / 2;
    const rectY = rectCenterY - viewportHeight / 2;
    
    minimapRect.style.left = Math.max(0, Math.min(mmWidth - viewportWidth, rectX)) + "px";
    minimapRect.style.top = Math.max(0, Math.min(mmHeight - viewportHeight, rectY)) + "px";
    minimapRect.style.width = viewportWidth + "px";
    minimapRect.style.height = viewportHeight + "px";
    minimapRect.style.display = "block";
  } else {
    minimapRect.style.display = "none";
  }
}

// ---- meta panel ----
function renderMetaKV(container, kv, highlightKey) {
  if (!kv || Object.keys(kv).length === 0) {
    container.innerHTML = "No data";
    return;
  }

  let html = "";
  for (const [k, v] of Object.entries(kv)) {
    const isHL = (highlightKey && k === highlightKey);
    html += `
      <div class="metaRow">
        <div class="metaKey">${k}</div>
        <div class="metaVal ${isHL ? "metaHighlight" : ""}">${v}</div>
      </div>
    `;
  }
  container.innerHTML = html;
}

async function loadMeta() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value;
  if (!seq) {
    gameinfoBox.innerHTML = "No data";
    seqinfoBox.innerHTML = "No data";
    return;
  }

  try {
    const meta = await fetchJSON(`/api/seq_meta?dataset=${encodeURIComponent(dataset)}&split=${encodeURIComponent(split)}&seq=${encodeURIComponent(seq)}`);
    renderMetaKV(gameinfoBox, meta.gameinfo || {}, "actionClass");
    renderMetaKV(seqinfoBox, meta.seqinfo || {}, null);
  } catch (e) {
    gameinfoBox.innerHTML = `Failed to load: ${e.message}`;
    seqinfoBox.innerHTML = `Failed to load: ${e.message}`;
  }
}

// ---- drawing ----
function computeStrength(vis, mode) {
  // mode: fixed|by_vis, but vis!=1 color is handled elsewhere
  if (mode === "by_vis" && typeof vis === "number" && vis >= 0) {
    const vis01 = clamp01(vis);
    return {
      fillAlpha: 0.10 + 0.35 * vis01,   // 0.10~0.45
      lineAlpha: 0.40 + 0.60 * vis01,   // 0.40~1.00
    };
  }
  return { fillAlpha: 0.25, lineAlpha: 1.0 };
}

function getBoxRgb(box, baseRgb) {
  if (highlightVis.checked && visIsNot1(box.vis)) {
    return hexToRgb(visColor.value);
  }
  return baseRgb;
}

function drawTextWithOutline(text, x, y, fillStyle, fontPx, alpha = 1.0) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = `${fontPx}px Arial`;
  ctx.lineWidth = 4;
  ctx.strokeStyle = "rgba(0,0,0,0.55)";
  ctx.fillStyle = fillStyle;
  ctx.strokeText(text, x, y);
  ctx.fillText(text, x, y);
  ctx.restore();
}

function drawAllBoxes(dimAll = false, dimFactor = 1.0) {
  if (!showGT.checked) return;
  const base = hexToRgb(boxColor.value);
  const visRgb = hexToRgb(visColor.value);
  const mode = getRadio("colorMode", "fixed");

  for (let i = 0; i < currentBoxes.length; i++) {
    const b = currentBoxes[i];

    const strength = computeStrength(b.vis, mode);
    let fillAlpha = strength.fillAlpha;
    let lineAlpha = strength.lineAlpha;

    if (dimAll) {
      fillAlpha *= dimFactor;
      lineAlpha *= dimFactor;
    }

    const rgb = getBoxRgb(b, base);

    if (showBBox.checked) {
      // fill
      ctx.save();
      ctx.globalAlpha = fillAlpha;
      ctx.fillStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
      ctx.fillRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
      ctx.restore();

      // stroke
      ctx.save();
      ctx.globalAlpha = lineAlpha;
      ctx.lineWidth = STROKE_W_NORMAL;
      ctx.strokeStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
      ctx.strokeRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
      ctx.restore();
    }

    // labels always show
    const idText = `id:${b.id}`;
    const visText = (typeof b.vis === "number" && b.vis >= 0) ? `v:${b.vis.toFixed(2)}` : "v:NA";

    // ID position: above box left
    if (showID.checked) {
      const x = Math.max(0, b.x1);
      const y = Math.max(ID_FONT_PX, b.y1 - 6);
      drawTextWithOutline(
        idText,
        x,
        y,
        `rgb(${rgb.r},${rgb.g},${rgb.b})`,
        ID_FONT_PX,
        dimAll ? dimFactor : 1.0
      );
    }

    // visibility position: center-right inside box
    if (showVis.checked) {
      const cx = b.x2 - 6; // near right edge
      const cy = (b.y1 + b.y2) / 2;

      // align right: measure text width
      ctx.save();
      ctx.font = `${VIS_FONT_PX}px Arial`;
      const w = ctx.measureText(visText).width;
      ctx.restore();

      const x = Math.max(0, cx - w);
      const y = Math.max(VIS_FONT_PX, cy);

      drawTextWithOutline(
        visText,
        x,
        y,
        `rgb(${visRgb.r},${visRgb.g},${visRgb.b})`,
        VIS_FONT_PX,
        dimAll ? dimFactor : 1.0
      );
    }
  }
}

function drawHoveredBoxOnTop() {
  if (!showGT.checked) return;
  if (hoveredIndex < 0 || hoveredIndex >= currentBoxes.length) return;

  const base = hexToRgb(boxColor.value);
  const visRgb = hexToRgb(visColor.value);
  const mode = getRadio("colorMode", "fixed");
  const b = currentBoxes[hoveredIndex];

  const strength = computeStrength(b.vis, mode);
  const rgb = getBoxRgb(b, base);

  if (showBBox.checked) {
    // fill
    ctx.save();
    ctx.globalAlpha = strength.fillAlpha;
    ctx.fillStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
    ctx.fillRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
    ctx.restore();

    // stroke thicker
    ctx.save();
    ctx.globalAlpha = 1.0;
    ctx.lineWidth = STROKE_W_HOVER;
    ctx.strokeStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
    ctx.strokeRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
    ctx.restore();
  }

  // texts (full alpha)
  const idText = `id:${b.id}`;
  const visText = (typeof b.vis === "number" && b.vis >= 0) ? `v:${b.vis.toFixed(2)}` : "v:NA";

  if (showID.checked) {
    const x = Math.max(0, b.x1);
    const y = Math.max(ID_FONT_PX, b.y1 - 6);
    drawTextWithOutline(idText, x, y, `rgb(${rgb.r},${rgb.g},${rgb.b})`, ID_FONT_PX, 1.0);
  }

  if (showVis.checked) {
    const cx = b.x2 - 6;
    const cy = (b.y1 + b.y2) / 2;

    ctx.save();
    ctx.font = `${VIS_FONT_PX}px Arial`;
    const w = ctx.measureText(visText).width;
    ctx.restore();

    const x = Math.max(0, cx - w);
    const y = Math.max(VIS_FONT_PX, cy);
    drawTextWithOutline(
      visText,
      x,
      y,
      `rgb(${visRgb.r},${visRgb.g},${visRgb.b})`,
      VIS_FONT_PX,
      1.0
    );
  }

  // hover info bar
  const bbStr = `bbox=(${b.x1.toFixed(0)},${b.y1.toFixed(0)},${(b.x2-b.x1).toFixed(0)},${(b.y2-b.y1).toFixed(0)})`;
  const vStr = (typeof b.vis === "number" && b.vis >= 0) ? `vis=${b.vis.toFixed(2)}` : "vis=NA";
  hoverInfo.textContent = `Hover: id=${b.id} | ${vStr} | ${bbStr}`;
}

function drawLockedBoxOnTop() {
  if (!showGT.checked) return;
  if (lockedBoxIndex < 0 || lockedBoxIndex >= currentBoxes.length) return;

  const base = hexToRgb(boxColor.value);
  const visRgb = hexToRgb(visColor.value);
  const mode = getRadio("colorMode", "fixed");
  const b = currentBoxes[lockedBoxIndex];

  const strength = computeStrength(b.vis, mode);
  const rgb = getBoxRgb(b, base);

  if (showBBox.checked) {
    // fill
    ctx.save();
    ctx.globalAlpha = strength.fillAlpha;
    ctx.fillStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
    ctx.fillRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
    ctx.restore();

    // stroke thicker
    ctx.save();
    ctx.globalAlpha = 1.0;
    ctx.lineWidth = STROKE_W_HOVER;
    ctx.strokeStyle = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
    ctx.strokeRect(b.x1, b.y1, (b.x2 - b.x1), (b.y2 - b.y1));
    ctx.restore();
  }

  // texts (full alpha)
  const idText = `id:${b.id}`;
  const visText = (typeof b.vis === "number" && b.vis >= 0) ? `v:${b.vis.toFixed(2)}` : "v:NA";

  if (showID.checked) {
    const x = Math.max(0, b.x1);
    const y = Math.max(ID_FONT_PX, b.y1 - 6);
    drawTextWithOutline(idText, x, y, `rgb(${rgb.r},${rgb.g},${rgb.b})`, ID_FONT_PX, 1.0);
  }

  if (showVis.checked) {
    const cx = b.x2 - 6;
    const cy = (b.y1 + b.y2) / 2;

    ctx.save();
    ctx.font = `${VIS_FONT_PX}px Arial`;
    const w = ctx.measureText(visText).width;
    ctx.restore();

    const x = Math.max(0, cx - w);
    const y = Math.max(VIS_FONT_PX, cy);
    drawTextWithOutline(
      visText,
      x,
      y,
      `rgb(${visRgb.r},${visRgb.g},${visRgb.b})`,
      VIS_FONT_PX,
      1.0
    );
  }

  // locked info bar
  const bbStr = `bbox=(${b.x1.toFixed(0)},${b.y1.toFixed(0)},${(b.x2-b.x1).toFixed(0)},${(b.y2-b.y1).toFixed(0)})`;
  const vStr = (typeof b.vis === "number" && b.vis >= 0) ? `vis=${b.vis.toFixed(2)}` : "vis=NA";
  hoverInfo.textContent = `Locked: id=${b.id} | ${vStr} | ${bbStr}`;
}

function drawScene() {
  if (!currentImage) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    hoverInfo.textContent = "Hover: none";
    return;
  }

  // Canvas size stays the same, but we scale all drawing
  if (canvas.width !== currentImage.naturalWidth || canvas.height !== currentImage.naturalHeight) {
    canvas.width = currentImage.naturalWidth;
    canvas.height = currentImage.naturalHeight;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // Apply zoom transformation centered, with pan offset
  ctx.save();
  
  // Translate to canvas center, then scale and center the chosen image point.
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  
  ctx.translate(centerX, centerY);
  ctx.scale(zoomLevel, zoomLevel);
  ctx.translate(-panX, -panY);
  
  // Draw image
  ctx.drawImage(currentImage, 0, 0);

  if (showGT.checked) {
    const hasHover = hoveredIndex >= 0 && hoveredIndex < currentBoxes.length;
    const hasLock = lockedBoxIndex >= 0 && lockedBoxIndex < currentBoxes.length;

    if (!hasHover && !hasLock) {
      // normal
      drawAllBoxes(false, 1.0);
    } else {
      // 1) draw everything dimmed first
      drawAllBoxes(true, DIM_FACTOR);

      // 2) add global dark overlay
      ctx.globalAlpha = HOVER_OVERLAY_ALPHA;
      ctx.fillStyle = "black";
      ctx.fillRect(0, 0, currentImage.naturalWidth, currentImage.naturalHeight);
      ctx.globalAlpha = 1.0;

      // 3) draw hovered or locked box full on top
      if (hasHover) {
        drawHoveredBoxOnTop();
      } else if (hasLock) {
        drawLockedBoxOnTop();
      }
    }
  }

  ctx.restore();
  
  if (!showGT.checked) {
    hoverInfo.textContent = "Hover: none";
  }
}

// ---- hit test ----
function getMousePosOnCanvas(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = canvas.width / rect.width;
  const sy = canvas.height / rect.height;
  
  // Mouse position in canvas coordinates
  let x = (e.clientX - rect.left) * sx;
  let y = (e.clientY - rect.top) * sy;
  
  // Convert from canvas coordinates to image coordinates accounting for zoom and pan
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  
  x = (x - centerX) / zoomLevel + panX;
  y = (y - centerY) / zoomLevel + panY;
  
  return { x, y };
}

function hitTestBox(x, y) {
  let best = -1;
  let bestArea = Infinity;
  for (let i = 0; i < currentBoxes.length; i++) {
    const b = currentBoxes[i];
    if (x >= b.x1 && x <= b.x2 && y >= b.y1 && y <= b.y2) {
      const area = (b.x2 - b.x1) * (b.y2 - b.y1);
      if (area < bestArea) {
        bestArea = area;
        best = i;
      }
    }
  }
  return best;
}

canvas.addEventListener("mousemove", (e) => {
  if (!showGT.checked || currentBoxes.length === 0) return;
  const { x, y } = getMousePosOnCanvas(e);
  const idx = hitTestBox(x, y);
  if (idx !== hoveredIndex) {
    hoveredIndex = idx;
    drawScene();
  }
});

canvas.addEventListener("mouseleave", () => {
  if (hoveredIndex !== -1) {
    hoveredIndex = -1;
    drawScene();
  }
});

let clickThreshold = 5; // pixels
let clickStartX = 0;
let clickStartY = 0;

canvas.addEventListener("mousedown", (e) => {
  clickStartX = e.clientX;
  clickStartY = e.clientY;
  // Handle different modes
  if (zoomMode === "pan") {
    if (zoomLevel <= 1) return; // Only pan when zoomed
    isDragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
  } else if (zoomMode === "magnify") {
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / rect.width;
    const sy = canvas.height / rect.height;
    const canvasX = (e.clientX - rect.left) * sx;
    const canvasY = (e.clientY - rect.top) * sy;
    setZoomLevel(zoomLevel * 1.1, canvasX, canvasY);
    drawScene();
    updateMinimap();
    updateMinimapVisibility();
  } else if (zoomMode === "demagnify") {
    const rect = canvas.getBoundingClientRect();
    const sx = canvas.width / rect.width;
    const sy = canvas.height / rect.height;
    const canvasX = (e.clientX - rect.left) * sx;
    const canvasY = (e.clientY - rect.top) * sy;
    setZoomLevel(zoomLevel / 1.1, canvasX, canvasY);
    drawScene();
    updateMinimap();
    updateMinimapVisibility();
  } else if (zoomMode === "rect") {
    // start rectangle selection
    isRectSelecting = true;
    rectSelectStartX = e.clientX;
    rectSelectStartY = e.clientY;
  }
});

canvas.addEventListener("click", (e) => {
  if (!showGT.checked || currentBoxes.length === 0) return;
  
  // Check if this was a drag, not a click
  const dx = e.clientX - clickStartX;
  const dy = e.clientY - clickStartY;
  if (Math.sqrt(dx*dx + dy*dy) > clickThreshold) {
    return; // This was a drag
  }
  
  const { x, y } = getMousePosOnCanvas(e);
  const idx = hitTestBox(x, y);
  if (idx >= 0) {
    // Click on a box: lock it
    lockedBoxIndex = idx;
    updateLockedBoxInfo();
    drawScene();
  } else {
    // Click on empty area: unlock
    lockedBoxIndex = -1;
    updateLockedBoxInfo();
    drawScene();
  }
});

canvas.addEventListener("mousemove", (e) => {
  if (isRectSelecting) {
    drawScene();

    const startPos = getMousePosOnCanvas({
      clientX: rectSelectStartX,
      clientY: rectSelectStartY,
    });
    const endPos = getMousePosOnCanvas(e);
    const sxMin = Math.min(startPos.x, endPos.x);
    const syMin = Math.min(startPos.y, endPos.y);
    const sw = Math.abs(endPos.x - startPos.x);
    const sh = Math.abs(endPos.y - startPos.y);

    ctx.save();
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    ctx.translate(centerX, centerY);
    ctx.scale(zoomLevel, zoomLevel);
    ctx.translate(-panX, -panY);

    ctx.strokeStyle = "#35e6fd";
    ctx.lineWidth = 2 / zoomLevel;
    ctx.setLineDash([6 / zoomLevel, 4 / zoomLevel]);
    ctx.strokeRect(sxMin, syMin, sw, sh);
    ctx.restore();
    return;
  }

  if (!isDragging) return;
  
  const deltaX = e.clientX - dragStartX;
  const deltaY = e.clientY - dragStartY;
  
  // Scale delta by canvas size and zoom level
  const rect = canvas.getBoundingClientRect();
  const scaledDeltaX = (deltaX / rect.width) * canvas.width / zoomLevel;
  const scaledDeltaY = (deltaY / rect.height) * canvas.height / zoomLevel;
  
  panX -= scaledDeltaX;
  panY -= scaledDeltaY;
  clampPan();
  
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  
  drawScene();
  updateMinimap();
});

canvas.addEventListener("mouseup", (e) => {
  isDragging = false;
  if (isRectSelecting) {
    isRectSelecting = false;
    const startPos = getMousePosOnCanvas({
      clientX: rectSelectStartX,
      clientY: rectSelectStartY,
    });
    const endPos = getMousePosOnCanvas(e);
    const px_min = Math.min(startPos.x, endPos.x);
    const py_min = Math.min(startPos.y, endPos.y);
    const px_max = Math.max(startPos.x, endPos.x);
    const py_max = Math.max(startPos.y, endPos.y);
    const pw = px_max - px_min;
    const ph = py_max - py_min;

    if (pw > 10 && ph > 10) {
      const desiredZoomX = canvas.width / pw;
      const desiredZoomY = canvas.height / ph;
      const newZoom = Math.min(4.0, Math.max(1.0, Math.min(desiredZoomX, desiredZoomY)));
      const centerPx_x = (px_min + px_max) / 2;
      const centerPx_y = (py_min + py_max) / 2;

      zoomLevel = newZoom;
      panX = centerPx_x;
      panY = centerPx_y;
      clampPan();
      zoomInput.value = Math.round(zoomLevel * 100);
      zoomHint.textContent = Math.round(zoomLevel * 100) + "%";
      drawScene();
      updateMinimap();
      updateMinimapVisibility();
    } else {
      drawScene();
    }
  }
});

canvas.addEventListener("mouseleave", () => {
  isDragging = false;
});

// ---- load image + boxes ----
let renderAbort = null;

async function loadFrameImageAndBoxes() {
  const seq = seqSelect.value;
  if (!seq) return;

  try {
    if (renderAbort) renderAbort.abort();
    renderAbort = new AbortController();

    const params = getParams();
    const imgUrl = `/api/render_raw?${params.toString()}&t=${Date.now()}`;
    const boxUrl = `/api/frame_boxes?${params.toString()}&t=${Date.now()}`;

    const [imgResp, boxJson] = await Promise.all([
      fetch(imgUrl, { signal: renderAbort.signal }),
      fetchJSON(boxUrl)
    ]);

    if (!imgResp.ok) throw new Error(await imgResp.text());

    const blob = await imgResp.blob();
    const objUrl = URL.createObjectURL(blob);

    const img = new Image();
    img.onload = () => {
      if (canvas.dataset.objurl) URL.revokeObjectURL(canvas.dataset.objurl);
      canvas.dataset.objurl = objUrl;

      currentImage = img;
      currentMotFrame = boxJson.mot_frame ?? null;
      currentBoxes = (boxJson.boxes || []).map(b => ({
        id: b.id,
        x1: b.x1, y1: b.y1, x2: b.x2, y2: b.y2,
        vis: b.vis
      }));

      hoveredIndex = -1;
      lockedBoxIndex = -1;
      const center = getImageCenter();
      panX = center.x;
      panY = center.y;
      updateLockedBoxInfo();
      updateNavUI();
      drawScene();
      updateMinimap();
      updateMinimapVisibility();
    };
    img.src = objUrl;
  } catch (e) {
    if (e.name === "AbortError") return;
    console.error(e);
    setStatus(`Render error: ${e.message}`);
  }
}

const renderThrottled = throttle(() => {
  frameInput.value = "";
  loadFrameImageAndBoxes();
}, 80);

// ---- vis!=1 list ----
async function loadVisNot1Frames() {
  const params = getParams();
  const seq = seqSelect.value;
  if (!seq) {
    visList.innerHTML = "";
    return;
  }

  try {
    const frames = await fetchJSON(`/api/vis_not1_frames?${params.toString()}`);
    if (!frames || frames.length === 0) {
      visList.innerHTML = `<div class="hint">No vis != 1 frames for the selected annotation file.</div>`;
      return;
    }

    visList.innerHTML = "";
    for (const fr of frames) {
      const div = document.createElement("div");
      div.className = "visItem";
      div.innerHTML = `<span>MOT frame: ${fr}</span><span class="visBadge">jump</span>`;
      div.addEventListener("click", () => {
        frameInput.value = fr;
        const motRadio = document.querySelector('input[name="frameMode"][value="mot"]');
        if (motRadio) motRadio.checked = true;
        loadFrameImageAndBoxes();
      });
      visList.appendChild(div);
    }
  } catch (e) {
    visList.innerHTML = `<div class="hint">Failed to load list: ${e.message}</div>`;
  }
}

async function loadAnnotationFiles() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value;
  const previousType = annotationTypeSelect.value || "gt";
  const previousFile = annotationFileSelect.value || "";

  annotationFileSelect.innerHTML = "";
  if (!seq) {
    annotationHint.textContent = "Choose a GT or DET file from this sequence.";
    return;
  }

  const payload = await fetchJSON(
    `/api/annotation_files?dataset=${encodeURIComponent(dataset)}&split=${encodeURIComponent(split)}&seq=${encodeURIComponent(seq)}`
  );

  const sources = payload.sources || { gt: [], det: [] };
  const defaults = payload.defaults || {};
  const availableTypes = Object.entries(sources)
    .filter(([, files]) => files && files.length > 0)
    .map(([type]) => type);

  const nextType = availableTypes.includes(previousType)
    ? previousType
    : payload.default_type || availableTypes[0] || "gt";
  annotationTypeSelect.value = nextType;

  const files = sources[nextType] || [];
  for (const filename of files) {
    const opt = document.createElement("option");
    opt.value = filename;
    opt.textContent = filename;
    annotationFileSelect.appendChild(opt);
  }

  const nextFile = files.includes(previousFile)
    ? previousFile
    : defaults[nextType] || payload.default_file || files[0] || "";
  if (nextFile) {
    annotationFileSelect.value = nextFile;
  }

  annotationFileSelect.disabled = files.length === 0;
  annotationHint.textContent = files.length > 0
    ? `${nextType.toUpperCase()} files from this sequence.`
    : `No ${nextType.toUpperCase()} files found in this sequence.`;
}

function refreshAnnotationFileOptions() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value;
  if (!seq) {
    annotationFileSelect.innerHTML = "";
    annotationFileSelect.disabled = true;
    annotationHint.textContent = "Choose a GT or DET file from this sequence.";
    return;
  }

  loadAnnotationFiles().catch((e) => {
    annotationFileSelect.innerHTML = "";
    annotationFileSelect.disabled = true;
    annotationHint.textContent = `Failed to load annotation files: ${e.message}`;
  });
}

// ---- load metadata ----
let datasetConfigs = [];

async function loadDatasets(preferredName = null) {
  const payload = await fetchJSON("/api/datasets");
  datasetConfigs = payload.datasets || [];
  const previous = datasetSelect.value;
  datasetSelect.innerHTML = "";

  for (const dataset of datasetConfigs) {
    const opt = document.createElement("option");
    opt.value = dataset.name;
    opt.textContent = dataset.name;
    datasetSelect.appendChild(opt);
  }

  const defaultDataset = payload.default || (datasetConfigs[0] && datasetConfigs[0].name) || "";
  const nextDataset = datasetConfigs.some(d => d.name === preferredName)
    ? preferredName
    : datasetConfigs.some(d => d.name === previous)
      ? previous
      : defaultDataset;
  if (nextDataset) {
    datasetSelect.value = nextDataset;
  }
}

function clearDatasetForm() {
  datasetNameInput.value = "";
  datasetRootInput.value = "";
  datasetSplitsInput.value = "";
  datasetImageDirInput.value = "";
  datasetGtFilesInput.value = "";
  datasetSeqinfoInput.value = "";
  datasetGameinfoInput.value = "";
}

function setDatasetFormOpen(isOpen) {
  datasetFormPanel.style.display = isOpen ? "block" : "none";
  toggleDatasetFormBtn.textContent = isOpen ? "Hide Dataset Form" : "Add Dataset";
  if (isOpen) {
    datasetNameInput.focus();
  }
}

async function saveDataset() {
  const payload = {
    name: datasetNameInput.value.trim(),
    root: datasetRootInput.value.trim(),
    splits: datasetSplitsInput.value.trim(),
    image_dir: datasetImageDirInput.value.trim(),
    gt_files: datasetGtFilesInput.value.trim(),
    seqinfo_filename: datasetSeqinfoInput.value.trim(),
    gameinfo_filename: datasetGameinfoInput.value.trim(),
  };

  if (!payload.name || !payload.root) {
    datasetFormStatus.textContent = "Dataset name and root path are required.";
    return;
  }

  try {
    datasetSaveBtn.disabled = true;
    datasetFormStatus.textContent = "Saving dataset...";
    const result = await postJSON("/api/datasets", payload);
    const savedName = result.dataset && result.dataset.name ? result.dataset.name : payload.name;
    clearDatasetForm();
    setDatasetFormOpen(false);
    await loadDatasets(savedName);
    await refreshAll();
    datasetFormStatus.textContent = `Saved dataset: ${savedName}`;
  } catch (e) {
    datasetFormStatus.textContent = `Failed to save dataset: ${e.message}`;
  } finally {
    datasetSaveBtn.disabled = false;
  }
}

async function loadSplits() {
  const dataset = datasetSelect.value;
  const splits = await fetchJSON(`/api/splits?dataset=${encodeURIComponent(dataset)}`);
  const previous = splitSelect.value;
  splitSelect.innerHTML = "";
  for (const s of splits) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    splitSelect.appendChild(opt);
  }
  if (splits.includes(previous)) {
    splitSelect.value = previous;
  }
}

async function loadSequences() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seqs = await fetchJSON(`/api/sequences?dataset=${encodeURIComponent(dataset)}&split=${encodeURIComponent(split)}`);
  const previous = seqSelect.value;
  seqSelect.innerHTML = "";
  for (const s of seqs) {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    seqSelect.appendChild(opt);
  }
  if (seqs.includes(previous)) {
    seqSelect.value = previous;
  }
}

async function loadFrameInfo() {
  const dataset = datasetSelect.value;
  const split = splitSelect.value;
  const seq = seqSelect.value;
  if (!seq) return { count: 0 };

  const info = await fetchJSON(`/api/frame_info?dataset=${encodeURIComponent(dataset)}&split=${encodeURIComponent(split)}&seq=${encodeURIComponent(seq)}`);
  lastFrameInfo = info;

  const count = info.count || 0;
  frameSlider.min = 0;
  frameSlider.max = Math.max(0, count - 1);
  frameSlider.value = 0;

  updateFrameHint();
  return info;
}

async function refreshAll() {
  try {
    setStatus("Loading...");
    await loadSplits();
    await loadSequences();
    await loadAnnotationFiles();
    const info = await loadFrameInfo();
    await loadVisNot1Frames();
    await loadMeta();
    setStatus(`Loaded. frames=${info.count || 0}`);
    frameInput.value = "";
    loadFrameImageAndBoxes();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
}

// ---- navigation ----
function stepFrame(delta) {
  const idx = parseInt(frameSlider.value || "0", 10);
  const maxV = parseInt(frameSlider.max || "0", 10);
  const next = Math.max(0, Math.min(maxV, idx + delta));
  if (next === idx) return;

  frameSlider.value = next;
  frameInput.value = "";
  updateFrameHint();
  loadFrameImageAndBoxes();
}

// ---- events ----
datasetSelect.addEventListener("change", () => {
  stopPlayback();
  refreshAll();
});

toggleDatasetFormBtn.addEventListener("click", () => {
  const isOpen = datasetFormPanel.style.display !== "none";
  if (isOpen) {
    clearDatasetForm();
    datasetFormStatus.textContent = "Custom datasets are stored locally for future runs.";
  }
  setDatasetFormOpen(!isOpen);
});

datasetCancelBtn.addEventListener("click", () => {
  clearDatasetForm();
  datasetFormStatus.textContent = "Custom datasets are stored locally for future runs.";
  setDatasetFormOpen(false);
});

[datasetNameInput, datasetRootInput, datasetSplitsInput, datasetImageDirInput, datasetGtFilesInput, datasetSeqinfoInput, datasetGameinfoInput].forEach((el) => {
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveDataset();
  });
});

splitSelect.addEventListener("change", () => {
  stopPlayback();
  (async () => {
    try {
      setStatus("Loading...");
      await loadSequences();
      await loadAnnotationFiles();
      const info = await loadFrameInfo();
      await loadVisNot1Frames();
      await loadMeta();
      setStatus(`Loaded. frames=${info.count || 0}`);
      frameInput.value = "";
      loadFrameImageAndBoxes();
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  })();
});

seqSelect.addEventListener("change", async () => {
  try {
    stopPlayback();
    setStatus("Loading frames...");
    await loadAnnotationFiles();
    const info = await loadFrameInfo();
    await loadVisNot1Frames();
    await loadMeta();
    setStatus(`Loaded. frames=${info.count || 0}`);
    frameInput.value = "";
    loadFrameImageAndBoxes();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
});

annotationTypeSelect.addEventListener("change", async () => {
  try {
    await loadAnnotationFiles();
    await loadVisNot1Frames();
    loadFrameImageAndBoxes();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
});

annotationFileSelect.addEventListener("change", async () => {
  try {
    await loadVisNot1Frames();
    loadFrameImageAndBoxes();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
});

// slider realtime
frameSlider.addEventListener("input", () => {
  updateFrameHint();
  renderThrottled();
});

// toggles redraw (no refetch)
[showGT, showBBox, showID, showVis, highlightVis].forEach(el => {
  el.addEventListener("change", () => drawScene());
});

boxColor.addEventListener("change", () => drawScene());
visColor.addEventListener("change", () => drawScene());
document.querySelectorAll('input[name="colorMode"]').forEach(el => {
  el.addEventListener("change", () => drawScene());
});

goBtn.addEventListener("click", () => {
  loadFrameImageAndBoxes();

  // idx mode sync slider
  const mode = getRadio("frameMode", "idx");
  const v = parseInt(frameInput.value || "", 10);
  if (!Number.isNaN(v) && mode === "idx") {
    const maxV = parseInt(frameSlider.max || "0", 10);
    frameSlider.value = Math.max(0, Math.min(maxV, v));
    updateFrameHint();
  }
});

frameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") goBtn.click();
});

refreshBtn.addEventListener("click", refreshAll);
datasetSaveBtn.addEventListener("click", saveDataset);

prevBtn.addEventListener("click", () => stepFrame(-1));
nextBtn.addEventListener("click", () => stepFrame(1));

playBtn.addEventListener("click", startPlayback);
stopBtn.addEventListener("click", stopPlayback);
playbackSpeed.addEventListener("input", updatePlaybackSpeed);

zoomInput.addEventListener("input", applyZoom);
zoomResetBtn.addEventListener("click", resetZoom);

// ---- Zoom control buttons ----
const zoomInBtn = document.getElementById("zoomInBtn");
const zoomOutBtn = document.getElementById("zoomOutBtn");
const panBtn = document.getElementById("panBtn");
const rectZoomBtn = document.getElementById("rectZoomBtn");
const minimapOverlay = document.getElementById("minimapOverlay");

function updateZoomButtonsUI() {
  zoomInBtn.classList.remove("active");
  zoomOutBtn.classList.remove("active");
  panBtn.classList.remove("active");
  rectZoomBtn.classList.remove("active");
  
  if (zoomMode === "magnify") zoomInBtn.classList.add("active");
  else if (zoomMode === "demagnify") zoomOutBtn.classList.add("active");
  else if (zoomMode === "pan") panBtn.classList.add("active");
  else if (zoomMode === "rect") rectZoomBtn.classList.add("active");
}

zoomInBtn.addEventListener("click", () => {
  if (zoomMode === "magnify") {
    zoomMode = "pan";
  } else {
    zoomMode = "magnify";
  }
  updateZoomButtonsUI();
});

zoomOutBtn.addEventListener("click", () => {
  if (zoomMode === "demagnify") {
    zoomMode = "pan";
  } else {
    zoomMode = "demagnify";
  }
  updateZoomButtonsUI();
});

panBtn.addEventListener("click", () => {
  zoomMode = zoomMode === "pan" ? "pan" : "pan";
  updateZoomButtonsUI();
});

rectZoomBtn.addEventListener("click", () => {
  if (zoomMode === "rect") {
    zoomMode = "pan";
  } else {
    zoomMode = "rect";
  }
  updateZoomButtonsUI();
});

// Show/hide minimap based on zoom level
function updateMinimapVisibility() {
  if (zoomLevel > 1.0) {
    minimapOverlay.style.display = "block";
  } else {
    minimapOverlay.style.display = "none";
  }
}

// ---- Minimap rectangle dragging ----
let isMinimapDragging = false;
let minimapDragStartX = 0;
let minimapDragStartY = 0;

minimapRect.addEventListener("mousedown", (e) => {
  isMinimapDragging = true;
  minimapDragStartX = e.clientX;
  minimapDragStartY = e.clientY;
  minimapRect.style.cursor = "grabbing";
  e.stopPropagation();
});

document.addEventListener("mousemove", (e) => {
  if (!isMinimapDragging) return;
  
  const deltaX = e.clientX - minimapDragStartX;
  const deltaY = e.clientY - minimapDragStartY;
  
  // Move viewport rect in minimap
  const newX = parseFloat(minimapRect.style.left || 0) + deltaX;
  const newY = parseFloat(minimapRect.style.top || 0) + deltaY;
  const mmWidth = minimapCanvas.width;
  const mmHeight = minimapCanvas.height;
  const rectW = minimapRect.offsetWidth;
  const rectH = minimapRect.offsetHeight;
  
  // Clamp within minimap bounds
  const clampedX = Math.max(0, Math.min(mmWidth - rectW, newX));
  const clampedY = Math.max(0, Math.min(mmHeight - rectH, newY));
  
  minimapRect.style.left = clampedX + "px";
  minimapRect.style.top = clampedY + "px";
  
  // Calculate image aspect and minimap image dimensions
  const mmCanvasWidth = minimapCanvas.width;
  const mmCanvasHeight = minimapCanvas.height;
  const imgAspect = currentImage.naturalWidth / currentImage.naturalHeight;
  
  let mmImgWidth, mmImgHeight;
  if (imgAspect > 16/9) {
    mmImgWidth = mmCanvasWidth;
    mmImgHeight = mmCanvasWidth / imgAspect;
  } else {
    mmImgHeight = mmCanvasHeight;
    mmImgWidth = mmCanvasHeight * imgAspect;
  }
  
  const mmOffsetX = (mmCanvasWidth - mmImgWidth) / 2;
  const mmOffsetY = (mmCanvasHeight - mmImgHeight) / 2;
  
  // Center of rect in minimap
  const rectCenterX = clampedX + rectW / 2;
  const rectCenterY = clampedY + rectH / 2;
  
  // Convert to relative position on image (0 to 1)
  const relX = (rectCenterX - mmOffsetX) / mmImgWidth;
  const relY = (rectCenterY - mmOffsetY) / mmImgHeight;
  
  // Convert to image pixel space
  const imgCenterX = relX * currentImage.naturalWidth;
  const imgCenterY = relY * currentImage.naturalHeight;
  
  panX = imgCenterX;
  panY = imgCenterY;
  clampPan();
  
  minimapDragStartX = e.clientX;
  minimapDragStartY = e.clientY;
  
  drawScene();
});

document.addEventListener("mouseup", () => {
  isMinimapDragging = false;
  minimapRect.style.cursor = "pointer";
});

// keyboard
document.addEventListener("keydown", (e) => {
  const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
  if (tag === "input" || tag === "select" || tag === "textarea") return;

  if (e.key === "ArrowLeft") stepFrame(-1);
  if (e.key === "ArrowRight") stepFrame(1);
});

// ---- init ----
(async function init() {
  try {
    await loadDatasets();
    await refreshAll();
    updateZoomButtonsUI();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
  }
})();
