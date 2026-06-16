/* ============================================
   SLIDE PRESENTATION APP
   Escbase Slide Starter
   ============================================ */

// State
let currentSlide = 0;
let totalSlides = 6;
let isReady = true;
let isAnimating = false;
let audioCtx = null;
let bgMusicGain = null;
let bgMusicSource = null;
let customBgmAudio = null;
let isMuted = false;

// Per-slide audio config - benchmark launch vibe
const slideTransitions = [
  "dramatic",
  "sweep",
  "bass",
  "rise",
  "chord",
  "minimal"
];
const slideReveals = [
  "sparkle",
  "pop",
  "blip",
  "bubble",
  "tick",
  "bell"
];

// Per-slide script text
const slideScripts = [
  "Crypto đang lệch pha khi ETF bán mạnh nhưng Bitcoin vẫn giữ vùng hỗ trợ chính.",
  "Bitcoin dao động quanh bảy mươi ba đến bảy mươi bốn nghìn đô la. Mốc bảy mươi nghìn vẫn được giữ. Vùng tám mươi nghìn vẫn là kháng cự gần.",
  "Vốn hóa crypto ở mức hai phẩy bốn chín nghìn tỷ đô la. Bitcoin ETF bị rút ròng một phẩy bốn hai tỷ đô la. Dòng tiền tổ chức đang thận trọng.",
  "Ethereum ETF mất hai trăm bốn mươi mốt triệu đô la. XRP ETF hút vào mười lăm phẩy hai triệu đô la. Solana ETF vẫn dương hai phẩy ba sáu triệu đô la.",
  "Rủi ro lớn nhất đến từ eo biển Hormuz. Iran muốn thu phí tàu dầu khoảng một đô la mỗi thùng. Iran yêu cầu thanh toán bằng Bitcoin. Stablecoin có thể bị phong tỏa nên Bitcoin được chọn.",
  "Nếu Hormuz không thông trước tháng tám, dầu có thể nóng lại. Khi lạm phát tăng, Fed khó nới lỏng hơn. Theo dõi kênh để cập nhật crypto, vĩ mô và dòng tiền ETF mỗi ngày."
];
const initialSlideScripts = [...slideScripts];
const initialSlideTransitions = [...slideTransitions];
const initialSlideReveals = [...slideReveals];

const themePresets = {
  'creator-pink-blue': {
    label: 'Creator Pink Blue',
    variables: {
      '--primary': '#ea4c89',
      '--primary-light': '#ff9ac2',
      '--primary-dark': '#8f1d50',
      '--accent': '#4a90e2',
      '--accent-light': '#9bd3ff',
      '--info': '#50c878',
      '--success': '#50c878',
      '--bg-dark': '#07030d'
    }
  },
  'openclaw-neon-green': {
    label: 'OpenClaw Neon Green',
    variables: {
      '--primary': '#00e676',
      '--primary-light': '#b9f6ca',
      '--primary-dark': '#0a7442',
      '--accent': '#ffab40',
      '--accent-light': '#ffd699',
      '--info': '#69f0ae',
      '--success': '#00e676',
      '--bg-dark': '#030807'
    }
  },
  'cyber-purple': {
    label: 'Cyber Purple',
    variables: {
      '--primary': '#8b5cf6',
      '--primary-light': '#c4b5fd',
      '--primary-dark': '#4c1d95',
      '--accent': '#22d3ee',
      '--accent-light': '#a5f3fc',
      '--info': '#38bdf8',
      '--success': '#34d399',
      '--bg-dark': '#080413'
    }
  },
  'minimal-gold': {
    label: 'Minimal Gold',
    variables: {
      '--primary': '#f5c542',
      '--primary-light': '#ffe9a3',
      '--primary-dark': '#926b10',
      '--accent': '#ffffff',
      '--accent-light': '#f4f4f5',
      '--info': '#facc15',
      '--success': '#a3e635',
      '--bg-dark': '#090807'
    }
  },
  'dark-terminal': {
    label: 'Dark Terminal',
    variables: {
      '--primary': '#22c55e',
      '--primary-light': '#86efac',
      '--primary-dark': '#14532d',
      '--accent': '#94a3b8',
      '--accent-light': '#cbd5e1',
      '--info': '#38bdf8',
      '--success': '#22c55e',
      '--bg-dark': '#020617'
    }
  },
  'custom': {
    label: 'Custom',
    variables: {
      '--primary': '#ea4c89',
      '--primary-light': '#ff9ac2',
      '--primary-dark': '#8f1d50',
      '--accent': '#4a90e2',
      '--accent-light': '#9bd3ff',
      '--info': '#50c878',
      '--success': '#50c878',
      '--bg-dark': '#07030d'
    }
  }
};

const previewColorControls = [
  { key: '--primary', type: 'theme', label: 'Primary' },
  { key: '--accent', type: 'theme', label: 'Accent' },
  { key: 'backgroundColor', type: 'visual', label: 'Màu nền' },
  { key: 'gridLight', type: 'visual', label: 'Đèn lưới' },
  { key: 'iconGlow', type: 'visual', label: 'Icon glow' },
  { key: 'iconBacklight', type: 'visual', label: 'Backlight' },
  { key: 'iconLight', type: 'visual', label: 'Ánh icon' }
];

const backgroundFxOptions = {
  scan: 'Scan / Flow / Noise',
  particles: 'Particles',
  rings: 'Rings',
  lorenz: 'Lorenz',
  none: 'Tắt animation'
};

const defaultPreviewSettings = {
  "theme": {
    "preset": "custom",
    "variables": {
      "--primary": "#ff6a00",
      "--primary-light": "#ffbf80",
      "--primary-dark": "#9a3900",
      "--accent": "#8fa8ff",
      "--accent-light": "#dbe3ff",
      "--info": "#4fd0ff",
      "--success": "#68f2b4",
      "--bg-dark": "#07111e"
    },
    "customVariables": {
      "--primary": "#ff6a00",
      "--primary-light": "#ffbf80",
      "--primary-dark": "#9a3900",
      "--accent": "#8fa8ff",
      "--accent-light": "#dbe3ff",
      "--info": "#4fd0ff",
      "--success": "#68f2b4",
      "--bg-dark": "#07111e"
    }
  },
  "bgm": {
    "mode": "custom",
    "preset": "ambient",
    "volume": 0.3,
    "custom": {
      "name": "meta.mp3",
      "path": "preview-assets/bgm/meta.mp3",
      "url": "preview-assets/bgm/meta.mp3"
    }
  },
  "subtitles": {
    "enabled": true,
    "color": "#ffffff",
    "fontSize": 18,
    "bottom": 152,
    "maxLines": 1
  },
  "visuals": {
    "colorMode": "dark",
    "backgroundColor": "#07111e",
    "gridEnabled": false,
    "gridLight": "#8fa8ff",
    "iconGlow": "#ff6a00",
    "iconBacklight": "#4fd0ff",
    "iconLight": "#68f2b4",
    "backgroundFx": "particles",
    "customValues": {
      "backgroundColor": "#07111e",
      "gridLight": "#8fa8ff",
      "iconGlow": "#ff6a00",
      "iconBacklight": "#4fd0ff",
      "iconLight": "#68f2b4"
    }
  },
  "slides": {
    "deletedIds": [],
    "scriptLines": [
      "Crypto đang lệch pha khi ETF bán mạnh nhưng Bitcoin vẫn giữ vùng hỗ trợ chính.",
      "Bitcoin dao động quanh bảy mươi ba đến bảy mươi bốn nghìn đô la. Mốc bảy mươi nghìn vẫn được giữ. Vùng tám mươi nghìn vẫn là kháng cự gần.",
      "Vốn hóa crypto ở mức hai phẩy bốn chín nghìn tỷ đô la. Bitcoin ETF bị rút ròng một phẩy bốn hai tỷ đô la. Dòng tiền tổ chức đang thận trọng.",
      "Ethereum ETF mất hai trăm bốn mươi mốt triệu đô la. XRP ETF hút vào mười lăm phẩy hai triệu đô la. Solana ETF vẫn dương hai phẩy ba sáu triệu đô la.",
      "Rủi ro lớn nhất đến từ eo biển Hormuz. Iran muốn thu phí tàu dầu khoảng một đô la mỗi thùng. Iran yêu cầu thanh toán bằng Bitcoin. Stablecoin có thể bị phong tỏa nên Bitcoin được chọn.",
      "Nếu Hormuz không thông trước tháng tám, dầu có thể nóng lại. Khi lạm phát tăng, Fed khó nới lỏng hơn. Theo dõi kênh để cập nhật crypto, vĩ mô và dòng tiền ETF mỗi ngày."
    ],
    "transitionSounds": [
      "dramatic",
      "sweep",
      "bass",
      "rise",
      "chord",
      "minimal"
    ],
    "revealSounds": [
      "sparkle",
      "pop",
      "blip",
      "bubble",
      "tick",
      "bell"
    ]
  }
};

let previewSettings = JSON.parse(JSON.stringify(defaultPreviewSettings));

// DOM Elements
const initialSlides = Array.from(document.querySelectorAll('.slide'));
initialSlides.forEach((slide, index) => {
  if (!slide.dataset.slideId) slide.dataset.slideId = slide.dataset.slide || String(index);
});
const initialSlideIds = initialSlides.map(slide => slide.dataset.slideId);
let slides = [...initialSlides];
totalSlides = slides.length;
const progressFill = document.getElementById('progressFill');
const currentSlideEl = document.getElementById('currentSlide');
const container = document.getElementById('slideContainer');
let themeEditorPanel = null;
let previewSubtitleOverlay = null;
let previewSubtitleLine = null;
let previewSubtitleRaf = null;
let previewSubtitleStartedAt = 0;
let previewSubtitleSlide = 0;
let previewSettingsSaveChain = Promise.resolve();
let scriptAutoSaveTimer = null;

function subtitleCaptionConstraints() {
  return (previewSettings?.subtitles?.maxLines || defaultPreviewSettings.subtitles.maxLines) <= 1
    ? { maxWords: 6, maxChars: 34 }
    : { maxWords: 9, maxChars: 62 };
}

function buildPreviewSubtitleCaptions(text) {
  const words = text.match(/\S+/g) || [];
  const captions = [];
  let current = [];
  let cursor = 0;
  const { maxWords, maxChars } = subtitleCaptionConstraints();
  const flush = () => {
    if (!current.length) return;
    const phraseWords = [...current];
    const phrase = phraseWords.join(' ');
    const duration = Math.max(1.1, phrase.length * 0.065);
    const totalWeight = Math.max(1, phraseWords.reduce((sum, word) => sum + Math.max(1, word.length), 0));
    let wordCursor = cursor;
    const timedWords = phraseWords.map((word, index) => {
      const span = index === phraseWords.length - 1
        ? (cursor + duration) - wordCursor
        : duration * Math.max(1, word.length) / totalWeight;
      const result = { text: word, start: wordCursor, end: wordCursor + span };
      wordCursor += span;
      return result;
    });
    captions.push({ text: phrase, start: cursor, end: cursor + duration, words: timedWords });
    cursor += duration;
    current = [];
  };
  words.forEach((word) => {
    const tentative = [...current, word].join(' ');
    if (current.length && (current.length >= maxWords || tentative.length > maxChars)) {
      flush();
    }
    current.push(word);
  });
  flush();
  return captions;
}

let previewSubtitleCaptions = slideScripts.map(buildPreviewSubtitleCaptions);

function findPreviewActiveWordIndex(words, time) {
  let candidate = -1;
  for (let i = 0; i < words.length; i += 1) {
    const word = words[i];
    if (time >= word.start && time <= word.end + 0.08) return i;
    if (word.start <= time) candidate = i;
    if (word.start > time) break;
  }
  return candidate;
}

function fitPreviewSubtitleLine() {
  if (!previewSubtitleLine) return;
  previewSubtitleLine.style.transform = '';
  previewSubtitleLine.style.transformOrigin = '';
  if ((previewSettings?.subtitles?.maxLines || defaultPreviewSettings.subtitles.maxLines) > 1) return;
  const overlayRect = previewSubtitleOverlay?.getBoundingClientRect();
  const availableWidth = Math.max(0, (overlayRect?.width || previewSubtitleLine.parentElement?.getBoundingClientRect().width || previewSubtitleLine.getBoundingClientRect().width || 0) - 8);
  if (!availableWidth) return;
  const range = document.createRange();
  range.selectNodeContents(previewSubtitleLine);
  const measuredWidth = range.getBoundingClientRect().width || 0;
  if (!availableWidth || !measuredWidth || measuredWidth <= availableWidth) return;
  const scale = Math.min(1, availableWidth / measuredWidth);
  previewSubtitleLine.style.transformOrigin = 'center center';
  previewSubtitleLine.style.transform = `scale(${scale})`;
}

function renderPreviewCaption(caption, time) {
  const words = Array.isArray(caption.words) ? caption.words : [];
  if (!words.length) {
    previewSubtitleLine.textContent = caption.text;
    fitPreviewSubtitleLine();
    return;
  }
  const activeWordIndex = findPreviewActiveWordIndex(words, time);
  previewSubtitleLine.replaceChildren();
  words.forEach((word, index) => {
    const span = document.createElement('span');
    span.className = 'script-subtitle-word';
    if (index < activeWordIndex) {
      span.classList.add('past');
    } else if (index === activeWordIndex) {
      span.classList.add('active');
    }
    span.textContent = word.text;
    previewSubtitleLine.appendChild(span);
  });
  fitPreviewSubtitleLine();
}

function ensurePreviewSubtitleOverlay() {
  if (previewSubtitleOverlay) return;
  previewSubtitleOverlay = document.createElement('div');
  previewSubtitleOverlay.className = 'script-subtitles preview-script-subtitles';
  previewSubtitleLine = document.createElement('div');
  previewSubtitleLine.className = 'script-subtitle-line';
  previewSubtitleOverlay.appendChild(previewSubtitleLine);
  container.appendChild(previewSubtitleOverlay);
}

function renderPreviewSubtitles() {
  if (window.__SCRIPT_SUBTITLE_DATA__) return;
  if (previewSettings.subtitles?.enabled === false) {
    if (previewSubtitleOverlay) previewSubtitleOverlay.classList.remove('visible');
    return;
  }
  ensurePreviewSubtitleOverlay();
  const captions = previewSubtitleCaptions[previewSubtitleSlide] || [];
  const time = (performance.now() - previewSubtitleStartedAt) / 1000;
  let idx = captions.findIndex(caption => time >= caption.start && time <= caption.end + 0.18);
  if (idx < 0) idx = captions.findLastIndex(caption => caption.start <= time);
  if (idx < 0 || time > (captions[captions.length - 1]?.end || 0) + 0.7) {
    previewSubtitleOverlay.classList.remove('visible');
    previewSubtitleLine.replaceChildren();
    previewSubtitleLine.style.transform = '';
    previewSubtitleLine.style.transformOrigin = '';
  } else {
    renderPreviewCaption(captions[idx], time);
    previewSubtitleOverlay.classList.add('visible');
  }
  previewSubtitleRaf = requestAnimationFrame(renderPreviewSubtitles);
}

function startPreviewSubtitles(slideIdx) {
  if (window.__SCRIPT_SUBTITLE_DATA__) return;
  if (previewSettings.subtitles?.enabled === false) {
    if (previewSubtitleOverlay) previewSubtitleOverlay.classList.remove('visible');
    return;
  }
  if (previewSubtitleRaf) cancelAnimationFrame(previewSubtitleRaf);
  previewSubtitleSlide = slideIdx;
  previewSubtitleStartedAt = performance.now();
  renderPreviewSubtitles();
}

function stopPreviewSubtitles() {
  if (previewSubtitleRaf) cancelAnimationFrame(previewSubtitleRaf);
  previewSubtitleRaf = null;
  if (previewSubtitleOverlay) previewSubtitleOverlay.classList.remove('visible');
}

function projectNameFromPath() {
  const match = window.location.pathname.match(/\/slide\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function settingsStorageKey() {
  return `preview-settings:${projectNameFromPath() || 'local'}`;
}

function scriptStorageKey() {
  return `preview-script:${projectNameFromPath() || 'local'}`;
}

function hasDeletedSlides(settings = previewSettings) {
  return Array.isArray(settings?.slides?.deletedIds) && settings.slides.deletedIds.length > 0;
}

function activeInitialIndexes(deletedIds = previewSettings.slides?.deletedIds || []) {
  const deleted = new Set(deletedIds.map(String));
  return initialSlideIds
    .map((id, index) => deleted.has(id) ? -1 : index)
    .filter(index => index >= 0);
}

function activeInitialIds(deletedIds = previewSettings.slides?.deletedIds || []) {
  const deleted = new Set(deletedIds.map(String));
  return initialSlideIds.filter(id => !deleted.has(id));
}

function linesForActiveSlides(lines, deletedIds = previewSettings.slides?.deletedIds || []) {
  if (!Array.isArray(lines)) return null;
  const cleaned = lines.map(line => String(line || '').trim());
  if (cleaned.length === totalSlides) return cleaned;
  if (cleaned.length !== initialSlideIds.length) return null;
  return activeInitialIndexes(deletedIds).map(index => cleaned[index] || '');
}

function isHexColor(value) {
  return typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value);
}

function hexToRgba(hex, alpha) {
  const value = isHexColor(hex) ? hex.slice(1) : 'ffffff';
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function storedCustomVisualSettings(settings = previewSettings) {
  const visuals = settings?.visuals || {};
  const theme = settings?.theme || {};
  const customVars = theme.customVariables && typeof theme.customVariables === 'object'
    ? theme.customVariables
    : (theme.preset === 'custom' && theme.variables && typeof theme.variables === 'object' ? theme.variables : {});
  const stored = visuals.customValues && typeof visuals.customValues === 'object' ? visuals.customValues : null;
  const current = visuals;
  const source = stored || current;
  const fallback = defaultPreviewSettings.visuals;
  return {
    backgroundColor: isHexColor(source.backgroundColor) ? source.backgroundColor : (isHexColor(customVars['--bg-dark']) ? customVars['--bg-dark'] : fallback.backgroundColor),
    gridLight: isHexColor(source.gridLight) ? source.gridLight : (isHexColor(customVars['--accent']) ? customVars['--accent'] : fallback.gridLight),
    iconGlow: isHexColor(source.iconGlow) ? source.iconGlow : (isHexColor(customVars['--primary']) ? customVars['--primary'] : fallback.iconGlow),
    iconBacklight: isHexColor(source.iconBacklight) ? source.iconBacklight : (isHexColor(customVars['--accent']) ? customVars['--accent'] : fallback.iconBacklight),
    iconLight: isHexColor(source.iconLight) ? source.iconLight : (isHexColor(customVars['--success']) ? customVars['--success'] : fallback.iconLight)
  };
}

function normalizeVisualSettings(settings) {
  const input = settings?.visuals || {};
  const themeVariables = settings?.theme?.variables || {};
  const fallback = defaultPreviewSettings.visuals;
  const fx = ['flow', 'noise', 'slide'].includes(input.backgroundFx) ? 'scan' : input.backgroundFx;
  return {
    colorMode: input.colorMode === 'light' ? 'light' : 'dark',
    backgroundColor: isHexColor(input.backgroundColor) ? input.backgroundColor : (isHexColor(themeVariables['--bg-dark']) ? themeVariables['--bg-dark'] : fallback.backgroundColor),
    gridEnabled: typeof input.gridEnabled === 'boolean' ? input.gridEnabled : fallback.gridEnabled,
    gridLight: isHexColor(input.gridLight) ? input.gridLight : (isHexColor(themeVariables['--accent']) ? themeVariables['--accent'] : fallback.gridLight),
    iconGlow: isHexColor(input.iconGlow) ? input.iconGlow : (isHexColor(themeVariables['--primary']) ? themeVariables['--primary'] : fallback.iconGlow),
    iconBacklight: isHexColor(input.iconBacklight) ? input.iconBacklight : (isHexColor(themeVariables['--accent']) ? themeVariables['--accent'] : fallback.iconBacklight),
    iconLight: isHexColor(input.iconLight) ? input.iconLight : (isHexColor(themeVariables['--success']) ? themeVariables['--success'] : fallback.iconLight),
    backgroundFx: fx && backgroundFxOptions[fx] ? fx : fallback.backgroundFx,
    customValues: storedCustomVisualSettings(settings)
  };
}

function storedCustomThemeVariables(settings = previewSettings) {
  const theme = settings?.theme || {};
  const stored = theme.customVariables && typeof theme.customVariables === 'object' ? theme.customVariables : null;
  const fallback = theme.variables && typeof theme.variables === 'object' ? theme.variables : {};
  return {
    ...themePresets.custom.variables,
    ...(stored || fallback)
  };
}

function normalizeThemeSettings(settings) {
  const preset = settings?.theme?.preset && themePresets[settings.theme.preset]
    ? settings.theme.preset
    : defaultPreviewSettings.theme.preset;
  const customVariables = storedCustomThemeVariables(settings);
  return {
    preset,
    variables: {
      ...(preset === 'custom' ? customVariables : themePresets[preset].variables),
      ...(preset === 'custom' ? {} : (settings?.theme?.variables || {}))
    },
    customVariables
  };
}

function normalizeBgmSettings(settings) {
  const input = settings?.bgm || {};
  const custom = input.custom && typeof input.custom === 'object' ? input.custom : {};
  const preset = input.preset && bgmPresets[input.preset] ? input.preset : defaultPreviewSettings.bgm.preset;
  let mode = ['preset', 'custom', 'none'].includes(input.mode) ? input.mode : defaultPreviewSettings.bgm.mode;
  const volume = Math.min(0.3, Math.max(0, Number(input.volume ?? defaultPreviewSettings.bgm.volume) || 0));
  const normalizedCustom = {
    name: String(custom.name || ''),
    path: String(custom.path || ''),
    url: String(custom.url || '')
  };
  if (mode === 'custom' && !normalizedCustom.path && !normalizedCustom.url) mode = 'preset';
  return {
    mode,
    preset,
    volume,
    custom: normalizedCustom
  };
}

function normalizeSubtitleSettings(settings) {
  const input = settings?.subtitles || {};
  const fallback = defaultPreviewSettings.subtitles;
  const fontSize = Math.min(28, Math.max(12, Number(input.fontSize ?? fallback.fontSize) || fallback.fontSize));
  const bottom = Math.min(180, Math.max(40, Number(input.bottom ?? fallback.bottom) || fallback.bottom));
  const maxLines = Math.round(Math.min(3, Math.max(1, Number(input.maxLines ?? fallback.maxLines) || fallback.maxLines)));
  const color = typeof input.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(input.color) ? input.color : fallback.color;
  return {
    enabled: input.enabled !== false,
    color,
    fontSize,
    bottom,
    maxLines
  };
}

function normalizeSlideAudioList(value, expectedCount) {
  if (!Array.isArray(value)) return [];
  const cleaned = value.map(item => String(item || '').trim()).filter(Boolean);
  return cleaned.length === expectedCount ? cleaned : [];
}

function normalizeSlideSettings(settings) {
  const input = settings?.slides || {};
  const allowed = new Set(initialSlideIds);
  const deletedIds = [];
  if (Array.isArray(input.deletedIds)) {
    input.deletedIds.forEach((id) => {
      const value = String(id);
      if (allowed.has(value) && !deletedIds.includes(value)) deletedIds.push(value);
    });
  }
  const activeCount = initialSlideIds.length - deletedIds.length;
  const rawScriptLines = Array.isArray(input.scriptLines) ? input.scriptLines : [];
  const scriptLines = rawScriptLines
    .map(line => String(line || '').trim())
    .filter(Boolean);
  const transitionSounds = normalizeSlideAudioList(input.transitionSounds, activeCount);
  const revealSounds = normalizeSlideAudioList(input.revealSounds, activeCount);
  return {
    deletedIds,
    scriptLines: scriptLines.length === activeCount ? scriptLines : [],
    transitionSounds,
    revealSounds
  };
}

function normalizePreviewSettings(settings) {
  const theme = normalizeThemeSettings(settings);
  return {
    ...settings,
    theme,
    visuals: normalizeVisualSettings({ ...settings, theme }),
    bgm: normalizeBgmSettings(settings),
    subtitles: normalizeSubtitleSettings(settings),
    slides: normalizeSlideSettings(settings)
  };
}

function applyThemeSettings(settings = previewSettings) {
  const normalized = normalizePreviewSettings(settings);
  previewSettings = normalized;
  Object.entries(normalized.theme.variables).forEach(([name, value]) => {
    document.documentElement.style.setProperty(name, value);
  });
  const select = document.getElementById('themePresetSelect');
  if (select) select.value = normalized.theme.preset;
  renderThemeSwatches();
}

function updateVisualControls() {
  const controls = document.querySelectorAll('[data-preview-color-key]');
  const vars = previewSettings.theme.variables;
  const visuals = previewSettings.visuals || defaultPreviewSettings.visuals;
  controls.forEach((input) => {
    const key = input.dataset.previewColorKey;
    const type = input.dataset.previewColorType;
    const value = type === 'theme' ? vars[key] : visuals[key];
    if (isHexColor(value)) input.value = value;
  });
  const gridEnabled = document.getElementById('gridEnabled');
  if (gridEnabled) gridEnabled.checked = visuals.gridEnabled !== false;
  const backgroundFxSelect = document.getElementById('backgroundFxSelect');
  if (backgroundFxSelect) backgroundFxSelect.value = visuals.backgroundFx || defaultPreviewSettings.visuals.backgroundFx;
}

function applyBackgroundFx(backgroundFx) {
  const fx = ['flow', 'noise', 'slide'].includes(backgroundFx) ? 'scan' : backgroundFx;
  document.querySelectorAll('.fx-canvas').forEach((canvas) => {
    if (!canvas.dataset.defaultFx) canvas.dataset.defaultFx = canvas.dataset.fx || 'scan';
    if (fx === 'none') {
      canvas.hidden = true;
      return;
    }
    canvas.hidden = false;
    canvas.dataset.fx = backgroundFxOptions[fx] ? fx : defaultPreviewSettings.visuals.backgroundFx;
  });
}

function applyVisualSettings(settings = previewSettings) {
  const normalized = normalizePreviewSettings(settings);
  previewSettings = normalized;
  const visuals = normalized.visuals;
  previewSettings.theme.variables['--bg-dark'] = visuals.backgroundColor;
  document.documentElement.style.setProperty('--bg-dark', visuals.backgroundColor);
  document.documentElement.style.setProperty('--background-glow', hexToRgba(visuals.gridLight, 0.26));
  document.documentElement.style.setProperty('--background-glow-soft', hexToRgba(visuals.gridLight, 0.14));
  document.documentElement.style.setProperty('--grid-light', visuals.gridLight);
  document.documentElement.style.setProperty('--grid-light-soft', hexToRgba(visuals.gridLight, 0.22));
  document.documentElement.style.setProperty('--grid-line', hexToRgba(visuals.gridLight, 0.14));
  document.documentElement.style.setProperty('--grid-line-soft', hexToRgba(visuals.gridLight, 0.08));
  document.documentElement.style.setProperty('--grid-opacity', visuals.gridEnabled ? '1' : '0');
  document.documentElement.style.setProperty('--icon-glow', visuals.iconGlow);
  document.documentElement.style.setProperty('--icon-glow-soft', hexToRgba(visuals.iconGlow, 0.36));
  document.documentElement.style.setProperty('--icon-glow-strong', hexToRgba(visuals.iconGlow, 0.68));
  document.documentElement.style.setProperty('--icon-backlight', visuals.iconBacklight);
  document.documentElement.style.setProperty('--icon-backlight-soft', hexToRgba(visuals.iconBacklight, 0.42));
  document.documentElement.style.setProperty('--icon-light', visuals.iconLight);
  document.documentElement.style.setProperty('--icon-light-soft', hexToRgba(visuals.iconLight, 0.58));
  document.documentElement.style.setProperty('--background-fx-opacity', visuals.backgroundFx === 'none' ? '0' : '0.48');
  applyBackgroundFx(visuals.backgroundFx);
  updateVisualControls();
}

function selectedBgmValue(bgm = previewSettings.bgm) {
  if (bgm.mode === 'none') return 'none';
  if (bgm.mode === 'custom') return 'custom';
  return bgm.preset;
}

function updateBgmControls() {
  const bgm = previewSettings.bgm;
  const value = selectedBgmValue(bgm);
  const selects = [document.getElementById('bgmSelect'), document.getElementById('editorBgmSelect')];
  selects.forEach((select) => {
    if (select) select.value = value;
  });
  const volume = document.getElementById('bgmVolume');
  const volumeValue = document.getElementById('bgmVolumeValue');
  const customName = document.getElementById('bgmCustomName');
  if (volume) volume.value = String(bgm.volume);
  if (volumeValue) volumeValue.textContent = Math.round(bgm.volume * 100) + '%';
  if (customName) {
    customName.textContent = bgm.custom.name || (bgm.mode === 'custom' ? 'Custom BGM' : 'Chưa upload file');
  }
}

function applyBgmSettings(settings = previewSettings) {
  const normalized = normalizePreviewSettings(settings);
  previewSettings = normalized;
  const preset = bgmPresets[normalized.bgm.preset];
  if (preset) {
    for (let i = 0; i < 4; i++) {
      chordProgression[i] = preset.chords[i];
      arpNotes[i] = preset.arps[i];
    }
  }
  updateBgmControls();
  if (bgMusicGain && audioCtx) {
    bgMusicGain.gain.setTargetAtTime(normalized.bgm.volume, audioCtx.currentTime, 0.08);
  }
}

function updateSubtitleControls() {
  const subtitles = previewSettings.subtitles;
  const enabled = document.getElementById('subtitleEnabled');
  const color = document.getElementById('subtitleColor');
  const fontSize = document.getElementById('subtitleFontSize');
  const fontSizeValue = document.getElementById('subtitleFontSizeValue');
  const bottom = document.getElementById('subtitleBottom');
  const bottomValue = document.getElementById('subtitleBottomValue');
  if (enabled) enabled.checked = subtitles.enabled;
  if (color) color.value = subtitles.color;
  if (fontSize) fontSize.value = String(subtitles.fontSize);
  if (fontSizeValue) fontSizeValue.textContent = subtitles.fontSize + 'px';
  if (bottom) bottom.value = String(subtitles.bottom);
  if (bottomValue) bottomValue.textContent = subtitles.bottom + 'px';
}

function applySubtitleSettings(settings = previewSettings) {
  const normalized = normalizePreviewSettings(settings);
  previewSettings = normalized;
  const subtitles = normalized.subtitles;
  document.documentElement.style.setProperty('--subtitle-color', subtitles.color);
  document.documentElement.style.setProperty('--subtitle-font-size', subtitles.fontSize + 'px');
  document.documentElement.style.setProperty('--subtitle-bottom', subtitles.bottom + 'px');
  document.documentElement.style.setProperty('--subtitle-max-lines', subtitles.maxLines);
  document.documentElement.style.setProperty('--subtitle-flex-wrap', subtitles.maxLines <= 1 ? 'nowrap' : 'wrap');
  document.documentElement.style.setProperty('--subtitle-white-space', subtitles.maxLines <= 1 ? 'nowrap' : 'normal');
  previewSubtitleCaptions = slideScripts.map(buildPreviewSubtitleCaptions);
  updateSubtitleControls();
  if (!subtitles.enabled) stopPreviewSubtitles();
}

function updateSlideCounterTotal() {
  const totalSlideEl = document.getElementById('totalSlides');
  if (totalSlideEl) totalSlideEl.textContent = totalSlides;
}

function renumberRuntimeSlides() {
  slides.forEach((slide, index) => {
    slide.dataset.slide = String(index);
  });
}

function playVideosInElement(element) {
  element?.querySelectorAll('video').forEach(video => {
    video.muted = isMuted;
    try { video.currentTime = 0; } catch {}
    video.play().catch(() => {});
  });
}

function pauseVideosInSlide(slide, reset = true) {
  slide?.querySelectorAll('video').forEach(video => {
    video.pause();
    if (reset) {
      try { video.currentTime = 0; } catch {}
    }
  });
}

function setActiveRuntimeSlide(index = currentSlide, options = {}) {
  if (!slides.length) return;
  isAnimating = false;
  currentSlide = Math.min(Math.max(0, index), totalSlides - 1);
  stopPreviewSubtitles();
  slides.forEach((slide, slideIndex) => {
    slide.classList.toggle('active', slideIndex === currentSlide);
    slide.style.transform = '';
    slide.style.opacity = '';
    resetElements(slideIndex);
  });
  const activeSlide = slides[currentSlide];
  const firstEl = activeSlide?.querySelector('.slide-element');
  if (options.revealFirst && firstEl) {
    firstEl.classList.add('visible');
    playVideosInElement(firstEl);
    startPreviewSubtitles(currentSlide);
  }
  updateProgress();
  updateAudioPanel();
}

function updateSlideDeleteControls() {
  const badge = document.getElementById('slideDeleteBadge');
  const deleteButton = document.getElementById('deleteSlideBtn');
  const restoreButton = document.getElementById('restoreSlideBtn');
  const deletedCount = previewSettings.slides?.deletedIds?.length || 0;
  if (badge) badge.textContent = `Slide ${Math.min(currentSlide + 1, totalSlides)} / ${totalSlides}`;
  if (deleteButton) deleteButton.disabled = totalSlides <= 1;
  if (restoreButton) restoreButton.disabled = deletedCount <= 0;
}

function setSlideDeleteStatus(message) {
  setEditorStatus('slideDeleteStatus', message);
}

function applySlideSettings(settings = previewSettings) {
  const normalized = normalizeSlideSettings(settings);
  const deleted = new Set(normalized.deletedIds);
  if (!deleted.size && !normalized.scriptLines.length && slides.length === initialSlides.length) {
    updateSlideCounterTotal();
    updateSlideDeleteControls();
    return;
  }

  initialSlides.forEach((slide) => {
    const shouldDelete = deleted.has(slide.dataset.slideId);
    if (shouldDelete && slide.parentNode) {
      pauseVideosInSlide(slide);
      slide.remove();
    } else if (!shouldDelete && !slide.parentNode) {
      const slideInitialIndex = initialSlides.indexOf(slide);
      const nextLiveSlide = initialSlides
        .slice(slideInitialIndex + 1)
        .find(candidate => !deleted.has(candidate.dataset.slideId) && candidate.parentNode === container);
      container.insertBefore(slide, nextLiveSlide || previewSubtitleOverlay || null);
    }
  });

  slides = initialSlides.filter(slide => !deleted.has(slide.dataset.slideId));
  totalSlides = slides.length;
  renumberRuntimeSlides();
  updateSlideCounterTotal();

  const activeIndexes = activeInitialIndexes(normalized.deletedIds);
  const activeScripts = normalized.scriptLines.length === slides.length
    ? normalized.scriptLines
    : (slideScripts.length === initialSlideIds.length
      ? activeIndexes.map(index => slideScripts[index] || initialSlideScripts[index] || '')
      : (slideScripts.length === slides.length ? slideScripts : activeIndexes.map(index => initialSlideScripts[index] || '')));

  const transitionSource = slideTransitions.length === initialSlideIds.length ? slideTransitions : initialSlideTransitions;
  const revealSource = slideReveals.length === initialSlideIds.length ? slideReveals : initialSlideReveals;
  const activeTransitions = normalized.transitionSounds.length === slides.length
    ? normalized.transitionSounds
    : activeIndexes.map(index => transitionSource[index] || initialSlideTransitions[index] || 'minimal');
  const activeReveals = normalized.revealSounds.length === slides.length
    ? normalized.revealSounds
    : activeIndexes.map(index => revealSource[index] || initialSlideReveals[index] || 'ping');
  slideScripts.splice(0, slideScripts.length, ...activeScripts);
  slideTransitions.splice(0, slideTransitions.length, ...activeTransitions);
  slideReveals.splice(0, slideReveals.length, ...activeReveals);
  syncRuntimeSlideSettings();
  previewSubtitleCaptions = slideScripts.map(buildPreviewSubtitleCaptions);
  currentSlide = Math.min(currentSlide, totalSlides - 1);
  if (currentSlide < 0) currentSlide = 0;
  setActiveRuntimeSlide(currentSlide, { revealFirst: !isReady });
}

function applyPreviewSettings(settings = previewSettings) {
  const normalized = normalizePreviewSettings(settings);
  previewSettings = normalized;
  applyThemeSettings(normalized);
  applyVisualSettings(normalized);
  applyBgmSettings(normalized);
  applySubtitleSettings(normalized);
  applySlideSettings(normalized);
}

function restartBackgroundMusic() {
  const shouldRestart = Boolean(bgMusicGain) && !isMuted;
  stopBackgroundMusic(0.25);
  if (shouldRestart) setTimeout(() => startBackgroundMusic(), 320);
}

function setEditorStatus(targetId, message) {
  const status = document.getElementById(targetId);
  if (!status) return;
  status.textContent = message || '';
  status.hidden = !message;
}

function setThemeStatus(message) {
  setEditorStatus('themeEditorStatus', message);
}

function setBgmStatus(message) {
  setEditorStatus('bgmEditorStatus', message);
}

function setSubtitleStatus(message) {
  setEditorStatus('subtitleEditorStatus', message);
}

function setScriptStatus(message) {
  setEditorStatus('scriptEditorStatus', message);
}

function setSlideAudioStatus(message) {
  setEditorStatus('slideAudioEditorStatus', message);
}

function syncRuntimeSlideSettings() {
  previewSettings.slides = {
    ...(previewSettings.slides || {}),
    scriptLines: [...slideScripts],
    transitionSounds: [...slideTransitions],
    revealSounds: [...slideReveals]
  };
}

async function savePreviewSettings(setStatus = setThemeStatus) {
  syncRuntimeSlideSettings();
  const snapshot = JSON.parse(JSON.stringify(previewSettings));
  window.localStorage.setItem(settingsStorageKey(), JSON.stringify(snapshot));
  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) {
    setStatus('Đã lưu trên trình duyệt');
    return;
  }
  previewSettingsSaveChain = previewSettingsSaveChain.catch(() => {}).then(async () => {
    const response = await fetch('/api/preview-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, settings: snapshot })
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    setStatus('Đã lưu preview-settings.json và app.js');
  });
  return previewSettingsSaveChain;
}

async function loadPreviewSettings() {
  const cached = window.localStorage.getItem(settingsStorageKey());
  if (cached) {
    try {
      previewSettings = normalizePreviewSettings(JSON.parse(cached));
      applyPreviewSettings(previewSettings);
    } catch {}
  }

  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) {
    applyPreviewSettings(previewSettings);
    return;
  }
  try {
    const response = await fetch(`/api/preview-settings?project=${encodeURIComponent(project)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.settings && Object.keys(data.settings).length) {
      previewSettings = normalizePreviewSettings(data.settings);
      window.localStorage.setItem(settingsStorageKey(), JSON.stringify(previewSettings));
      applyPreviewSettings(previewSettings);
    }
  } catch {
    applyPreviewSettings(previewSettings);
  }
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Không đọc được file'));
    reader.readAsDataURL(file);
  });
}

async function uploadCustomBgm(file) {
  setBgmStatus('Đang upload...');
  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) {
    previewSettings.bgm = {
      ...previewSettings.bgm,
      mode: 'custom',
      custom: {
        name: file.name,
        path: '',
        url: URL.createObjectURL(file)
      }
    };
    applyBgmSettings(previewSettings);
    restartBackgroundMusic();
    setBgmStatus('Dùng tạm trong trình duyệt');
    return;
  }

  try {
    const dataUrl = await readFileDataUrl(file);
    const response = await fetch('/api/preview-bgm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project,
        audio: {
          name: file.name,
          type: file.type,
          data: dataUrl
        }
      })
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    const data = await response.json();
    previewSettings.bgm = {
      ...previewSettings.bgm,
      mode: 'custom',
      custom: data.audio
    };
    applyBgmSettings(previewSettings);
    restartBackgroundMusic();
    await savePreviewSettings(setBgmStatus);
  } catch (error) {
    setBgmStatus(error.message || 'Không upload được');
  }
}

function applyProjectScript(lines) {
  const activeLines = linesForActiveSlides(lines);
  if (!activeLines || activeLines.length !== totalSlides) return false;
  slideScripts.splice(0, slideScripts.length, ...activeLines);
  syncRuntimeSlideSettings();
  previewSubtitleCaptions = slideScripts.map(buildPreviewSubtitleCaptions);
  updateScriptPanel();
  updateScriptEditor();
  if (!isReady) startPreviewSubtitles(currentSlide);
  return true;
}

async function loadProjectScript() {
  if (hasDeletedSlides() && Array.isArray(previewSettings.slides?.scriptLines) && previewSettings.slides.scriptLines.length === totalSlides) {
    applyProjectScript(previewSettings.slides.scriptLines);
    window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));
    return;
  }

  const cached = window.localStorage.getItem(scriptStorageKey());
  if (cached) {
    try {
      applyProjectScript(JSON.parse(cached));
    } catch {}
  }

  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) return;
  try {
    const response = await fetch(`/api/slide-script?project=${encodeURIComponent(project)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (applyProjectScript(data.lines)) {
      window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));
    }
  } catch {}
}

function updateScriptEditor() {
  const badge = document.getElementById('scriptEditorBadge');
  const text = document.getElementById('scriptEditorText');
  if (!badge || !text) return;
  badge.textContent = `Slide ${currentSlide + 1} / ${totalSlides}`;
  text.value = slideScripts[currentSlide] || '';
}

function syncCurrentSlideScriptFromEditor() {
  const text = document.getElementById('scriptEditorText');
  if (!text) return false;
  const nextText = text.value.trim();
  if (!nextText) {
    setScriptStatus('Script không được trống');
    return false;
  }
  slideScripts[currentSlide] = nextText;
  previewSubtitleCaptions[currentSlide] = buildPreviewSubtitleCaptions(nextText);
  const sText = document.getElementById('scriptText');
  if (sText && !isReady) sText.textContent = nextText;
  if (!isReady) startPreviewSubtitles(currentSlide);
  return true;
}

async function persistProjectScript(statusText = 'Đang tự lưu...', options = {}) {
  const {
    allowCountChange = false,
    syncPreviewSettings = hasDeletedSlides(),
    setStatus = setScriptStatus
  } = options;
  window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));
  syncRuntimeSlideSettings();
  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) {
    if (syncPreviewSettings) await savePreviewSettings(setStatus);
    setStatus('Đã lưu trên trình duyệt');
    return;
  }
  setStatus(statusText);
  const payload = { project, lines: slideScripts };
  if (allowCountChange) payload.allowCountChange = true;
  const response = await fetch('/api/slide-script', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  if (syncPreviewSettings) await savePreviewSettings(setStatus);
  setStatus('Đã lưu script-90s.txt, preview-settings.json, app.js và upload-metadata');
}

function queueScriptAutoSave() {
  if (!syncCurrentSlideScriptFromEditor()) return;
  setScriptStatus('Sẽ tự lưu...');
  if (scriptAutoSaveTimer) clearTimeout(scriptAutoSaveTimer);
  scriptAutoSaveTimer = setTimeout(async () => {
    try {
      await persistProjectScript();
    } catch (error) {
      setScriptStatus(error.message || 'Không tự lưu được');
    }
  }, 700);
}

async function saveCurrentSlideScript() {
  if (scriptAutoSaveTimer) clearTimeout(scriptAutoSaveTimer);
  if (!syncCurrentSlideScriptFromEditor()) return;
  const project = projectNameFromPath();
  if (!project || !window.location.protocol.startsWith('http')) {
    window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));
    setScriptStatus('Đã tự lưu trên trình duyệt');
    return;
  }
  try {
    await persistProjectScript('Đang lưu...');
  } catch (error) {
    setScriptStatus(error.message || 'Không lưu được');
  }
}

async function deleteCurrentSlide() {
  if (totalSlides <= 1) {
    setSlideDeleteStatus('Không thể xoá slide cuối cùng.');
    return;
  }
  const slide = slides[currentSlide];
  if (!slide) return;
  const slideNumber = currentSlide + 1;
  const confirmed = window.confirm(`Xoá slide ${slideNumber} khỏi preview?\n\nHành động này sẽ cập nhật script-90s.txt, preview-settings và app.js.`);
  if (!confirmed) return;

  if (scriptAutoSaveTimer) clearTimeout(scriptAutoSaveTimer);
  syncCurrentSlideScriptFromEditor();
  const deletedId = slide.dataset.slideId || slide.dataset.slide || String(currentSlide);
  const deletedIds = Array.from(new Set([...(previewSettings.slides?.deletedIds || []), deletedId]));
  const nextScripts = slideScripts.filter((_, index) => index !== currentSlide);
  const nextSlideIndex = Math.min(currentSlide, totalSlides - 2);

  previewSettings.slides = {
    ...(previewSettings.slides || {}),
    deletedIds,
    scriptLines: nextScripts
  };

  isReady = false;
  setSlideDeleteStatus('Đang xoá...');
  applyPreviewSettings(previewSettings);
  setActiveRuntimeSlide(nextSlideIndex, { revealFirst: true });
  window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));

  try {
    await persistProjectScript('Đang lưu script-90s.txt...', {
      allowCountChange: true,
      syncPreviewSettings: true,
      setStatus: setSlideDeleteStatus
    });
    setSlideDeleteStatus(`Đã xoá slide ${slideNumber} trong preview.`);
  } catch (error) {
    setSlideDeleteStatus(error.message || 'Đã xoá trong phiên này, nhưng chưa lưu được.');
  }
}

async function restoreDeletedSlide() {
  const deletedIds = [...(previewSettings.slides?.deletedIds || [])];
  if (!deletedIds.length) {
    setSlideDeleteStatus('Chưa có slide nào để khôi phục.');
    return;
  }

  if (scriptAutoSaveTimer) clearTimeout(scriptAutoSaveTimer);
  syncCurrentSlideScriptFromEditor();

  const restoredId = String(deletedIds[deletedIds.length - 1]);
  const currentActiveIds = activeInitialIds(deletedIds);
  const scriptBySlideId = new Map(currentActiveIds.map((id, index) => [id, slideScripts[index] || initialSlideScripts[initialSlideIds.indexOf(id)] || '']));
  const nextDeletedIds = deletedIds.filter(id => id !== restoredId);
  const nextActiveIds = activeInitialIds(nextDeletedIds);
  const nextScripts = nextActiveIds.map((id) => (
    id === restoredId
      ? initialSlideScripts[initialSlideIds.indexOf(id)] || ''
      : scriptBySlideId.get(id) || initialSlideScripts[initialSlideIds.indexOf(id)] || ''
  ));
  const restoredIndex = nextActiveIds.indexOf(restoredId);

  previewSettings.slides = {
    ...(previewSettings.slides || {}),
    deletedIds: nextDeletedIds,
    scriptLines: nextScripts
  };

  isReady = false;
  setSlideDeleteStatus('Đang khôi phục...');
  applyPreviewSettings(previewSettings);
  setActiveRuntimeSlide(restoredIndex >= 0 ? restoredIndex : currentSlide, { revealFirst: true });
  window.localStorage.setItem(scriptStorageKey(), JSON.stringify(slideScripts));

  try {
    await persistProjectScript('Đang lưu script-90s.txt...', {
      allowCountChange: true,
      syncPreviewSettings: true,
      setStatus: setSlideDeleteStatus
    });
    setSlideDeleteStatus(`Đã khôi phục slide ${initialSlideIds.indexOf(restoredId) + 1}.`);
  } catch (error) {
    setSlideDeleteStatus(error.message || 'Đã khôi phục trong phiên này, nhưng chưa lưu được.');
  }
}

function setupThemeEditor() {
  if (themeEditorPanel) return;
  themeEditorPanel = document.createElement('div');
  themeEditorPanel.className = 'theme-editor-panel';
  themeEditorPanel.innerHTML = `
    <div class="theme-editor-title"><i class="fa-solid fa-sliders"></i><span>Preview Editor</span></div>
    <div class="theme-editor-section theme-editor-section-theme">
      <div class="theme-editor-section-title">Tone màu</div>
      <label class="theme-editor-field">
        <span>Preset</span>
        <select id="themePresetSelect">
          ${Object.entries(themePresets).map(([key, preset]) => `<option value="${key}">${preset.label}</option>`).join('')}
        </select>
      </label>
      <div class="theme-editor-swatches" id="themeEditorSwatches"></div>
      <div class="theme-editor-mini-row">
        <label class="theme-editor-check theme-editor-mini-check">
          <input id="gridEnabled" type="checkbox" />
          <span>Lưới</span>
        </label>
        <label class="theme-editor-field theme-editor-mini-select">
          <span>Animation nền</span>
          <select id="backgroundFxSelect">
            ${Object.entries(backgroundFxOptions).map(([key, label]) => `<option value="${key}">${label}</option>`).join('')}
          </select>
        </label>
      </div>
    </div>
    <div class="theme-editor-section theme-editor-section-bgm">
      <div class="theme-editor-section-title">Nhạc nền</div>
      <label class="theme-editor-field">
        <span>BGM</span>
        <select id="editorBgmSelect">
          <option value="ambient">Ambient</option>
          <option value="cinematic">Cinematic</option>
          <option value="lofi">Lo-fi</option>
          <option value="piano">Piano</option>
          <option value="dark">Dark</option>
          <option value="custom">Custom upload</option>
          <option value="none">Tắt</option>
        </select>
      </label>
      <label class="theme-editor-field">
        <span>Volume <b id="bgmVolumeValue">12%</b></span>
        <input id="bgmVolume" type="range" min="0" max="0.3" step="0.01" />
      </label>
      <label class="theme-editor-upload">
        <input id="bgmUpload" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg" />
        <span><i class="fa-solid fa-upload"></i> Upload BGM</span>
      </label>
      <div class="theme-editor-file" id="bgmCustomName">Chưa upload file</div>
      <div class="theme-editor-status" id="bgmEditorStatus" hidden></div>
    </div>
    <div class="theme-editor-section theme-editor-section-audio">
      <div class="theme-editor-section-title">Âm thanh slide</div>
      <div class="audio-slide-header editor-audio-slide-header">
        <span class="audio-slide-badge" id="editorAudioPanelSlide">Ready</span>
        <div class="audio-slide-nav">
          <button class="audio-nav-btn" type="button" onclick="audioPanelPrev()"><i class="fa-solid fa-chevron-left"></i></button>
          <button class="audio-nav-btn" type="button" onclick="audioPanelNext()"><i class="fa-solid fa-chevron-right"></i></button>
        </div>
      </div>
      <label class="theme-editor-field">
        <span>Chuyển slide</span>
        <select id="editorTransitionSelect" onchange="setSlideTransition(currentSlide, this.value)">
          <option value="gong">Gong</option>
          <option value="rise">Rise</option>
          <option value="bass">Bass</option>
          <option value="chime">Chime</option>
          <option value="sweep">Sweep</option>
          <option value="boom">Boom</option>
          <option value="alarm">Alarm</option>
          <option value="chord">Chord</option>
          <option value="ascending">Ascending</option>
          <option value="retro">Retro</option>
          <option value="minimal">Minimal</option>
          <option value="dramatic">Dramatic</option>
        </select>
      </label>
      <label class="theme-editor-field">
        <span>Hiện element</span>
        <select id="editorRevealSelect" onchange="setSlideReveal(currentSlide, this.value)">
          <option value="ping">Ping</option>
          <option value="pop">Pop</option>
          <option value="chime">Chime</option>
          <option value="click">Click</option>
          <option value="bubble">Bubble</option>
          <option value="woosh">Woosh</option>
          <option value="sparkle">Sparkle</option>
          <option value="drop">Drop</option>
          <option value="tick">Tick</option>
          <option value="bell">Bell</option>
          <option value="blip">Blip</option>
          <option value="snap">Snap</option>
        </select>
      </label>
      <div class="theme-editor-actions">
        <button class="theme-editor-ghost-button" type="button" onclick="testTransition()">Test slide</button>
        <button class="theme-editor-ghost-button" type="button" onclick="testReveal()">Test reveal</button>
      </div>
      <div class="theme-editor-status" id="slideAudioEditorStatus" hidden></div>
    </div>
    <div class="theme-editor-section theme-editor-section-subtitles">
      <div class="theme-editor-section-title">Phụ đề</div>
      <label class="theme-editor-check">
        <input id="subtitleEnabled" type="checkbox" />
        <span>Bật subtitle</span>
      </label>
      <label class="theme-editor-field">
        <span>Màu chữ</span>
        <input id="subtitleColor" type="color" />
      </label>
      <label class="theme-editor-field">
        <span>Cỡ chữ <b id="subtitleFontSizeValue">18px</b></span>
        <input id="subtitleFontSize" type="range" min="12" max="28" step="1" />
      </label>
      <label class="theme-editor-field">
        <span>Vị trí đáy <b id="subtitleBottomValue">152px</b></span>
        <input id="subtitleBottom" type="range" min="40" max="180" step="4" />
      </label>
      <div class="theme-editor-status" id="subtitleEditorStatus" hidden></div>
      <div class="theme-editor-divider"></div>
      <div class="theme-editor-file" id="slideDeleteBadge">Slide 1 / ${totalSlides}</div>
      <div class="theme-editor-slide-actions">
        <button class="theme-editor-danger-button" type="button" id="deleteSlideBtn">
          <i class="fa-solid fa-trash"></i> Xoá slide
        </button>
        <button class="theme-editor-restore-button" type="button" id="restoreSlideBtn">
          <i class="fa-solid fa-rotate-left"></i> Khôi phục
        </button>
      </div>
      <div class="theme-editor-status" id="slideDeleteStatus" hidden></div>
    </div>
    <div class="theme-editor-section theme-editor-section-script">
      <div class="theme-editor-section-title">Script</div>
      <div class="theme-editor-file" id="scriptEditorBadge">Slide 1</div>
      <textarea id="scriptEditorText" class="script-editor-text" rows="8"></textarea>
      <div class="script-editor-hint">Tự lưu sau khi dừng gõ.</div>
      <div class="theme-editor-status" id="scriptEditorStatus" hidden></div>
    </div>
    <div class="theme-editor-status" id="themeEditorStatus" hidden></div>
  `;
  document.body.appendChild(themeEditorPanel);

  const select = document.getElementById('themePresetSelect');
  select.addEventListener('change', async () => {
    const preset = select.value;
    const customVariables = storedCustomThemeVariables(previewSettings);
    const customVisuals = storedCustomVisualSettings(previewSettings);
    const variables = preset === 'custom'
      ? { ...customVariables }
      : { ...themePresets[preset].variables };
    const visualColors = preset === 'custom'
      ? { ...customVisuals }
      : {
        backgroundColor: variables['--bg-dark'] || previewSettings.visuals?.backgroundColor,
        gridLight: variables['--accent'] || previewSettings.visuals?.gridLight,
        iconGlow: variables['--primary'] || previewSettings.visuals?.iconGlow,
        iconBacklight: variables['--accent'] || previewSettings.visuals?.iconBacklight,
        iconLight: variables['--success'] || previewSettings.visuals?.iconLight
      };
    previewSettings.theme = {
      preset,
      variables,
      customVariables
    };
    previewSettings.visuals = {
      ...previewSettings.visuals,
      ...visualColors,
      customValues: customVisuals
    };
    applyPreviewSettings(previewSettings);
    setThemeStatus('Đang lưu...');
    try {
      await savePreviewSettings();
    } catch (error) {
      setThemeStatus(error.message || 'Không lưu được');
    }
  });

  const swatches = document.getElementById('themeEditorSwatches');
  swatches.addEventListener('input', (event) => {
    const input = event.target;
    if (!input.matches('[data-preview-color-key]')) return;
    setPreviewColor(input.dataset.previewColorKey, input.dataset.previewColorType, input.value, input);
  });
  swatches.addEventListener('change', (event) => {
    if (event.target.matches('[data-preview-color-key]')) savePreviewColorSettings();
  });

  const gridEnabled = document.getElementById('gridEnabled');
  gridEnabled.addEventListener('change', () => {
    previewSettings.visuals = {
      ...previewSettings.visuals,
      gridEnabled: gridEnabled.checked
    };
    applyVisualSettings(previewSettings);
    savePreviewColorSettings();
  });

  const backgroundFxSelect = document.getElementById('backgroundFxSelect');
  backgroundFxSelect.addEventListener('change', () => {
    previewSettings.visuals = {
      ...previewSettings.visuals,
      backgroundFx: backgroundFxSelect.value
    };
    applyVisualSettings(previewSettings);
    savePreviewColorSettings();
  });

  const editorBgmSelect = document.getElementById('editorBgmSelect');
  editorBgmSelect.addEventListener('change', () => switchBGM(editorBgmSelect.value));

  const bgmVolume = document.getElementById('bgmVolume');
  bgmVolume.addEventListener('input', () => {
    previewSettings.bgm = {
      ...previewSettings.bgm,
      volume: Number(bgmVolume.value)
    };
    applyBgmSettings(previewSettings);
  });
  bgmVolume.addEventListener('change', async () => {
    setBgmStatus('Đang lưu...');
    try {
      await savePreviewSettings(setBgmStatus);
    } catch (error) {
      setBgmStatus(error.message || 'Không lưu được');
    }
  });

  const bgmUpload = document.getElementById('bgmUpload');
  bgmUpload.addEventListener('change', async () => {
    const file = bgmUpload.files && bgmUpload.files[0];
    if (!file) return;
    await uploadCustomBgm(file);
    bgmUpload.value = '';
  });

  const subtitleEnabled = document.getElementById('subtitleEnabled');
  const subtitleColor = document.getElementById('subtitleColor');
  const subtitleFontSize = document.getElementById('subtitleFontSize');
  const subtitleBottom = document.getElementById('subtitleBottom');
  const saveSubtitleSettings = async () => {
    setSubtitleStatus('Đang lưu...');
    try {
      await savePreviewSettings(setSubtitleStatus);
    } catch (error) {
      setSubtitleStatus(error.message || 'Không lưu được');
    }
  };
  subtitleEnabled.addEventListener('change', () => {
    previewSettings.subtitles = {
      ...previewSettings.subtitles,
      enabled: subtitleEnabled.checked
    };
    applySubtitleSettings(previewSettings);
    saveSubtitleSettings();
  });
  subtitleColor.addEventListener('input', () => {
    previewSettings.subtitles = {
      ...previewSettings.subtitles,
      color: subtitleColor.value
    };
    applySubtitleSettings(previewSettings);
  });
  subtitleColor.addEventListener('change', saveSubtitleSettings);
  subtitleFontSize.addEventListener('input', () => {
    previewSettings.subtitles = {
      ...previewSettings.subtitles,
      fontSize: Number(subtitleFontSize.value)
    };
    applySubtitleSettings(previewSettings);
  });
  subtitleFontSize.addEventListener('change', saveSubtitleSettings);
  subtitleBottom.addEventListener('input', () => {
    previewSettings.subtitles = {
      ...previewSettings.subtitles,
      bottom: Number(subtitleBottom.value)
    };
    applySubtitleSettings(previewSettings);
  });
  subtitleBottom.addEventListener('change', saveSubtitleSettings);

  const scriptEditorText = document.getElementById('scriptEditorText');
  scriptEditorText.addEventListener('input', queueScriptAutoSave);
  const scriptSaveBtn = document.getElementById('scriptSaveBtn');
  if (scriptSaveBtn) scriptSaveBtn.addEventListener('click', saveCurrentSlideScript);
  const deleteSlideBtn = document.getElementById('deleteSlideBtn');
  if (deleteSlideBtn) deleteSlideBtn.addEventListener('click', deleteCurrentSlide);
  const restoreSlideBtn = document.getElementById('restoreSlideBtn');
  if (restoreSlideBtn) restoreSlideBtn.addEventListener('click', restoreDeletedSlide);

  applyPreviewSettings(previewSettings);
  updateScriptEditor();
  updateSlideDeleteControls();
  renderThemeSwatches();
}

function previewControlColor(control, vars, visuals) {
  return control.type === 'theme' ? vars[control.key] : visuals[control.key];
}

function renderThemeSwatches() {
  const wrap = document.getElementById('themeEditorSwatches');
  if (!wrap) return;
  const vars = previewSettings.theme.variables;
  const visuals = previewSettings.visuals || defaultPreviewSettings.visuals;
  wrap.innerHTML = previewColorControls.map((control) => {
    const color = previewControlColor(control, vars, visuals) || '#000000';
    return `<label class="theme-editor-swatch" title="${control.label}" aria-label="${control.label}">
      <input type="color" value="${color}" data-preview-color-key="${control.key}" data-preview-color-type="${control.type}" />
      <span style="background:${color}"></span>
    </label>`;
  }).join('');
}

function setPreviewColor(key, type, value, input) {
  if (!isHexColor(value)) return;
  const customVariables = storedCustomThemeVariables(previewSettings);
  const customVisuals = storedCustomVisualSettings(previewSettings);
  if (type === 'theme') {
    const nextCustomVariables = {
      ...customVariables,
      [key]: value
    };
    const nextCustomVisuals = { ...customVisuals };
    if (key === '--bg-dark') nextCustomVisuals.backgroundColor = value;
    previewSettings.theme = {
      preset: 'custom',
      variables: nextCustomVariables,
      customVariables: nextCustomVariables
    };
    previewSettings.visuals = {
      ...previewSettings.visuals,
      ...(key === '--bg-dark' ? { backgroundColor: value } : {}),
      customValues: nextCustomVisuals
    };
  } else {
    const nextCustomVisuals = {
      ...customVisuals,
      [key]: value
    };
    const nextCustomVariables = key === 'backgroundColor'
      ? { ...customVariables, '--bg-dark': value }
      : customVariables;
    previewSettings.theme = {
      preset: 'custom',
      variables: nextCustomVariables,
      customVariables: nextCustomVariables
    };
    previewSettings.visuals = {
      ...previewSettings.visuals,
      [key]: value,
      customValues: nextCustomVisuals
    };
  }
  previewSettings = normalizePreviewSettings(previewSettings);
  Object.entries(previewSettings.theme.variables).forEach(([name, color]) => {
    document.documentElement.style.setProperty(name, color);
  });
  applyVisualSettings(previewSettings);
  if (input?.nextElementSibling) input.nextElementSibling.style.background = value;
  const presetSelect = document.getElementById('themePresetSelect');
  if (presetSelect) presetSelect.value = previewSettings.theme.preset;
}

async function savePreviewColorSettings() {
  setThemeStatus('Đang lưu...');
  try {
    await savePreviewSettings();
  } catch (error) {
    setThemeStatus(error.message || 'Không lưu được');
  }
}

// ============================================
// AUDIO ENGINE
// ============================================
function initAudio() {
  if (audioCtx) return;
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
}

function playTone(type, freqStart, freqEnd, delay, fadeInTime, vol, duration, Q) {
  if (!audioCtx || isMuted) return;
  const t = audioCtx.currentTime + delay;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  const filter = audioCtx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 3000;
  if (Q) filter.Q.value = Q;
  osc.type = type;
  osc.frequency.setValueAtTime(freqStart, t);
  if (freqEnd !== freqStart) osc.frequency.exponentialRampToValueAtTime(freqEnd, t + duration);
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(vol, t + fadeInTime);
  gain.gain.exponentialRampToValueAtTime(0.001, t + duration);
  osc.connect(filter); filter.connect(gain); gain.connect(audioCtx.destination);
  osc.start(t); osc.stop(t + duration + 0.05);
}

function playNoiseWhoosh(freqStart, freqEnd, duration) {
  if (!audioCtx || isMuted) return;
  const t = audioCtx.currentTime;
  const noise = createNoiseBuffer(duration + 0.1);
  const src = audioCtx.createBufferSource();
  src.buffer = noise;
  const filter = audioCtx.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.setValueAtTime(freqStart, t);
  filter.frequency.exponentialRampToValueAtTime(freqEnd, t + duration);
  filter.Q.value = 0.8;
  const gain = audioCtx.createGain();
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(0.04, t + 0.04);
  gain.gain.exponentialRampToValueAtTime(0.001, t + duration);
  src.connect(filter); filter.connect(gain); gain.connect(audioCtx.destination);
  src.start(t); src.stop(t + duration + 0.1);
}

function createNoiseBuffer(duration) {
  const sampleRate = audioCtx.sampleRate;
  const length = sampleRate * duration;
  const buffer = audioCtx.createBuffer(1, length, sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = (Math.random() * 2 - 1) * 0.5;
  return buffer;
}

// ============================================
// 12 TRANSITION SOUNDS
// ============================================
const transitionLib = {
  gong() { playTone('sine', 130, 260, 0, 0.6, 0.09, 0.8); playTone('triangle', 260, 520, 0.08, 0.4, 0.06, 0.6); playNoiseWhoosh(400, 1200, 0.35); },
  rise() { playTone('sine', 220, 440, 0, 0.5, 0.08, 0.6); playTone('triangle', 330, 660, 0.1, 0.35, 0.05, 0.5); },
  bass() { playTone('sine', 65, 55, 0, 0.12, 0.07, 0.7); playTone('triangle', 130, 110, 0.1, 0.08, 0.05, 0.5); playTone('sine', 65, 55, 0.35, 0.10, 0.06, 0.5); },
  chime() { playTone('sine', 880, 1320, 0, 0.6, 0.07, 0.5); playTone('sine', 1100, 880, 0.1, 0.4, 0.04, 0.4); },
  sweep() { playTone('sine', 440, 880, 0, 0.5, 0.07, 0.55); playNoiseWhoosh(600, 3000, 0.3); playTone('triangle', 660, 880, 0.12, 0.3, 0.04, 0.4); },
  boom() { playTone('sine', 80, 60, 0, 0.15, 0.09, 0.8); playTone('sine', 160, 120, 0.05, 0.12, 0.06, 0.6); playNoiseWhoosh(200, 600, 0.4); },
  alarm() { playTone('sawtooth', 370, 185, 0, 0.04, 0.07, 0.25, 2.5); playTone('sawtooth', 370, 185, 0.15, 0.04, 0.07, 0.25, 2.5); playNoiseWhoosh(1500, 3500, 0.2); },
  chord() { playTone('sine', 440, 440, 0, 0.55, 0.06, 0.7); playTone('sine', 554, 554, 0.06, 0.45, 0.05, 0.6); playTone('sine', 660, 660, 0.12, 0.4, 0.04, 0.55); playTone('sine', 880, 880, 0.2, 0.3, 0.03, 0.5); },
  ascending() { playTone('sine', 330, 440, 0, 0.5, 0.06, 0.4); playTone('sine', 440, 554, 0.15, 0.4, 0.05, 0.4); playTone('sine', 554, 660, 0.3, 0.35, 0.04, 0.4); },
  retro() { playTone('square', 262, 131, 0, 0.15, 0.03, 0.15, 2); playTone('square', 393, 262, 0.08, 0.12, 0.03, 0.15, 2); playNoiseWhoosh(2000, 500, 0.1); },
  minimal() { playTone('sine', 523, 784, 0, 0.4, 0.04, 0.3); },
  dramatic() { playTone('sine', 110, 55, 0, 0.15, 0.1, 1.0); playNoiseWhoosh(100, 400, 0.6); playTone('sine', 220, 440, 0.3, 0.5, 0.07, 0.6); }
};

// ============================================
// 12 REVEAL SOUNDS
// ============================================
const revealLib = {
  ping() { playTone('sine', 1000, 1400, 0, 0.03, 0.06, 0.18); },
  pop() { playTone('sine', 800, 1200, 0, 0.02, 0.06, 0.15); playTone('sine', 1200, 600, 0, 0.02, 0.03, 0.12); },
  chime() { playTone('sine', 1200, 1800, 0, 0.02, 0.05, 0.3); playTone('sine', 1500, 2000, 0.06, 0.02, 0.03, 0.25); },
  click() { playTone('triangle', 2000, 800, 0, 0.01, 0.07, 0.06); },
  bubble() { const b = 400 + Math.random() * 400; playTone('sine', b, b * 2, 0, 0.02, 0.05, 0.2); playTone('sine', b * 1.3, b * 2.5, 0.05, 0.02, 0.03, 0.15); },
  woosh() { playNoiseWhoosh(800 + Math.random() * 400, 2000 + Math.random() * 1000, 0.15); },
  sparkle() { playTone('sine', 1500, 2200, 0, 0.02, 0.04, 0.2); playTone('sine', 2000, 2800, 0.04, 0.02, 0.03, 0.18); playTone('sine', 2500, 1800, 0.08, 0.02, 0.02, 0.15); },
  drop() { playTone('sine', 1400, 400, 0, 0.02, 0.06, 0.2); },
  tick() { playTone('triangle', 3000, 1500, 0, 0.01, 0.05, 0.05); },
  bell() { playTone('sine', 880, 1100, 0, 0.02, 0.05, 0.35); playTone('sine', 1100, 880, 0.08, 0.02, 0.03, 0.3); },
  blip() { playTone('square', 600, 900, 0, 0.02, 0.03, 0.08, 3); },
  snap() { playTone('triangle', 4000, 500, 0, 0.01, 0.06, 0.04); playNoiseWhoosh(3000, 1000, 0.05); }
};

// ============================================
// PLAY DISPATCHER
// ============================================
function playSlideSound(slideIndex) {
  if (!audioCtx || isMuted) return;
  const key = slideTransitions[slideIndex] || 'minimal';
  if (transitionLib[key]) transitionLib[key]();
}

function playRevealSound() {
  if (!audioCtx || isMuted) return;
  const key = slideReveals[currentSlide] || 'ping';
  if (revealLib[key]) revealLib[key]();
}

// ============================================
// BACKGROUND MUSIC
// ============================================
let bgChordIndex = 0;
let bgArpInterval = null;
let bgChordInterval = null;

const chordProgression = [
  [130.81, 164.81, 196.00, 246.94],
  [110.00, 130.81, 164.81, 196.00],
  [87.31, 130.81, 164.81, 207.65],
  [98.00, 123.47, 146.83, 174.61],
];

const arpNotes = [
  [523.25, 659.25, 783.99, 987.77],
  [440.00, 523.25, 659.25, 783.99],
  [349.23, 523.25, 659.25, 830.61],
  [392.00, 493.88, 587.33, 698.46],
];

function startBackgroundMusic() {
  if (!audioCtx || isMuted) return;
  if (bgMusicGain) return;
  const bgm = normalizeBgmSettings(previewSettings);
  if (bgm.mode === 'none') return;
  bgMusicGain = audioCtx.createGain();
  bgMusicGain.gain.setValueAtTime(0, audioCtx.currentTime);
  bgMusicGain.gain.linearRampToValueAtTime(bgm.volume, audioCtx.currentTime + 4);
  bgMusicGain.connect(audioCtx.destination);
  if (bgm.mode === 'custom' && startCustomBackgroundMusic(bgm)) return;
  bgChordIndex = 0;
  playChord();
  bgChordInterval = setInterval(() => {
    bgChordIndex = (bgChordIndex + 1) % chordProgression.length;
    playChord();
  }, 8000);
  playArpNote();
  bgArpInterval = setInterval(playArpNote, 2000);
}

function resolveCustomBgmUrl(bgm) {
  if (!bgm || !bgm.custom) return '';
  return bgm.custom.path || bgm.custom.url || '';
}

function startCustomBackgroundMusic(bgm) {
  const url = resolveCustomBgmUrl(bgm);
  if (!url) return false;
  customBgmAudio = new Audio(url);
  customBgmAudio.loop = true;
  customBgmAudio.preload = 'auto';
  customBgmAudio.volume = 1;
  bgMusicSource = audioCtx.createMediaElementSource(customBgmAudio);
  bgMusicSource.connect(bgMusicGain);
  customBgmAudio.currentTime = 0;
  customBgmAudio.play().catch(() => {
    stopBackgroundMusic(0.1);
  });
  return true;
}

function playChord() {
  if (!audioCtx || !bgMusicGain || isMuted) return;
  const chord = chordProgression[bgChordIndex];
  chord.forEach((freq, i) => {
    const osc1 = audioCtx.createOscillator();
    const osc2 = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    const filter = audioCtx.createBiquadFilter();
    osc1.type = 'sine'; osc1.frequency.value = freq;
    osc2.type = 'triangle'; osc2.frequency.value = freq * 1.003;
    filter.type = 'lowpass'; filter.frequency.value = 350 + i * 50; filter.Q.value = 0.5;
    const t = audioCtx.currentTime;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.18, t + 2);
    gain.gain.setValueAtTime(0.18, t + 5);
    gain.gain.linearRampToValueAtTime(0.001, t + 8);
    osc1.connect(gain); osc2.connect(gain); gain.connect(filter); filter.connect(bgMusicGain);
    osc1.start(t + i * 0.15); osc2.start(t + i * 0.15);
    osc1.stop(t + 8.5); osc2.stop(t + 8.5);
  });
}

let arpNoteIndex = 0;
function playArpNote() {
  if (!audioCtx || !bgMusicGain || isMuted) return;
  const notes = arpNotes[bgChordIndex];
  const note = notes[arpNoteIndex % notes.length];
  arpNoteIndex++;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  const filter = audioCtx.createBiquadFilter();
  const delay = audioCtx.createDelay(1.0);
  const delayGain = audioCtx.createGain();
  osc.type = 'sine'; osc.frequency.value = note;
  filter.type = 'lowpass'; filter.frequency.value = 2000; filter.Q.value = 0.3;
  const t = audioCtx.currentTime;
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(0.12, t + 0.05);
  gain.gain.exponentialRampToValueAtTime(0.03, t + 0.8);
  gain.gain.linearRampToValueAtTime(0.001, t + 2.5);
  delay.delayTime.value = 0.375; delayGain.gain.value = 0.25;
  osc.connect(filter); filter.connect(gain); gain.connect(bgMusicGain);
  gain.connect(delay); delay.connect(delayGain); delayGain.connect(bgMusicGain);
  osc.start(t); osc.stop(t + 3);
}

function stopBackgroundMusic(fadeOut = 1) {
  if (bgChordInterval) { clearInterval(bgChordInterval); bgChordInterval = null; }
  if (bgArpInterval) { clearInterval(bgArpInterval); bgArpInterval = null; }
  if (customBgmAudio) {
    customBgmAudio.pause();
    customBgmAudio.currentTime = 0;
    customBgmAudio = null;
  }
  if (bgMusicSource) {
    try { bgMusicSource.disconnect(); } catch {}
    bgMusicSource = null;
  }
  if (bgMusicGain) {
    const gainNode = bgMusicGain;
    bgMusicGain = null;
    gainNode.gain.cancelScheduledValues(audioCtx.currentTime);
    gainNode.gain.setValueAtTime(gainNode.gain.value, audioCtx.currentTime);
    gainNode.gain.linearRampToValueAtTime(0, audioCtx.currentTime + fadeOut);
    setTimeout(() => {
      try { gainNode.disconnect(); } catch {}
    }, fadeOut * 1000 + 120);
  }
}

function toggleMute() {
  isMuted = !isMuted;
  const muteBtn = document.getElementById('muteBtn');
  if (isMuted) {
    muteBtn.innerHTML = '<i class="fa-solid fa-volume-xmark"></i>';
    stopBackgroundMusic();
  } else {
    muteBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
    initAudio();
    startBackgroundMusic();
  }
}

// ============================================
// SLIDE NAVIGATION
// ============================================
function init() {
  resetToStart();
  if (window.__PREVIEW_SETTINGS__) {
    applyPreviewSettings(window.__PREVIEW_SETTINGS__);
  }
  if (!window.__RENDER_MODE__) {
    setupThemeEditor();
    loadPreviewSettings().then(() => loadProjectScript());
  }
  container.addEventListener('click', handleClick);
  document.addEventListener('keydown', handleKeyboard);
  let touchStartX = 0, touchStartY = 0;
  container.addEventListener('touchstart', (e) => {
    touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY;
  }, { passive: true });
  container.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 40) {
      if (dx < 0) nextSlide(); else prevSlide();
    }
  }, { passive: true });
  updateAudioPanel();
}

function handleClick(e) {
  initAudio();
  if (!bgMusicGain && !isMuted) startBackgroundMusic();
  if (e.target.closest('.side-controls')) return;
  if (isReady) {
    isReady = false;
    updateProgress();
    updateAudioPanel();
    playSlideSound(0);
    const firstEl = slides[0].querySelector('.slide-element');
    if (firstEl && !firstEl.classList.contains('visible')) {
      firstEl.classList.add('visible');
      playVideosInElement(firstEl);
      createParticleBurst(firstEl);
      triggerShimmer(slides[0].querySelector('.title-shimmer'));
      playRevealSound();
      startPreviewSubtitles(0);
    }
    return;
  }
  const slide = slides[currentSlide];
  const mode = slide.dataset.mode;
  if (mode === 'highlight') {
    const elements = slide.querySelectorAll('.slide-element');
    const hidden = Array.from(elements).filter(el => !el.classList.contains('visible'));
    if (hidden.length > 0) { revealNextElement(); return; }
    const cards = slide.querySelectorAll('.highlightable');
    const highlighted = slide.querySelectorAll('.highlighted');
    if (highlighted.length < cards.length) {
      cards[highlighted.length].classList.add('highlighted');
      playRevealSound(); createParticleBurst(cards[highlighted.length]); return;
    }
    nextSlide(); return;
  }
  if (mode === 'traffic-light') {
    const elements = slide.querySelectorAll('.slide-element');
    const hidden = Array.from(elements).filter(el => !el.classList.contains('visible'));
    if (hidden.length > 0) { revealNextElement(); return; }
    const dots = slide.querySelectorAll('.lightable');
    const lit = slide.querySelectorAll('.lightable[class*="lit-"]');
    if (lit.length < dots.length) {
      const color = dots[lit.length].dataset.lightColor;
      dots[lit.length].classList.add('lit-' + color);
      playRevealSound(); createParticleBurst(dots[lit.length]); return;
    }
    nextSlide(); return;
  }
  const elements = slide.querySelectorAll('.slide-element');
  const hidden = Array.from(elements).filter(el => !el.classList.contains('visible'));
  if (hidden.length > 0) revealNextElement(); else nextSlide();
}

function handleKeyboard(e) {
  const target = e.target;
  if (target?.closest?.('.theme-editor-panel, input, textarea, select, button, [contenteditable="true"]')) {
    return;
  }
  if (e.key === 'ArrowRight' || e.key === ' ') {
    e.preventDefault();
    handleClick({ target: container, closest: () => null });
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault(); prevSlide();
  }
}

function nextSlide() {
  if (isAnimating) return;
  if (currentSlide >= totalSlides - 1) { resetToStart(); return; }
  goToSlide(currentSlide + 1);
}

function prevSlide() {
  if (isAnimating) return;
  if (currentSlide <= 0) { resetToStart(); return; }
  goToSlide(currentSlide - 1);
}

function resetToStart() {
  if (!slides.length) return;
  isAnimating = false;
  isReady = true;
  stopPreviewSubtitles();
  slides.forEach((slide, i) => {
    slide.classList.remove('active');
    slide.style.transform = '';
    slide.style.opacity = '';
    resetElements(i);
  });
  currentSlide = 0;
  slides[0].classList.add('active');
  slides[0].style.transform = '';
  slides[0].style.opacity = '';
  updateProgress();
  updateAudioPanel();
}

function goToSlide(index) {
  if (index < 0 || index >= totalSlides) return;
  if (index === currentSlide || isAnimating) return;
  isAnimating = true;
  initAudio();
  if (!bgMusicGain && !isMuted) startBackgroundMusic();
  playSlideSound(index);
  const direction = index > currentSlide ? 1 : -1;
  const oldSlide = slides[currentSlide];
  const newSlide = slides[index];
  pauseVideosInSlide(oldSlide);
  resetElements(index);
  oldSlide.classList.remove('active');
  oldSlide.style.transform = direction > 0 ? 'translateX(-60px)' : 'translateX(60px)';
  oldSlide.style.opacity = '0';
  newSlide.style.transform = direction > 0 ? 'translateX(60px)' : 'translateX(-60px)';
  newSlide.style.opacity = '0';
  requestAnimationFrame(() => {
    newSlide.classList.add('active');
    newSlide.style.transform = ''; newSlide.style.opacity = '';
    currentSlide = index;
    updateProgress();
    updateAudioPanel();
    setTimeout(() => {
      isAnimating = false;
      oldSlide.style.transform = ''; oldSlide.style.opacity = '';
      const firstEl = newSlide.querySelector('.slide-element');
      if (firstEl && !firstEl.classList.contains('visible')) {
        firstEl.classList.add('visible'); 
        playVideosInElement(firstEl);
        playRevealSound();
        createParticleBurst(firstEl);
        animateCounters(firstEl);
        startPreviewSubtitles(index);
      }
    }, 420);
  });
}

function revealNextElement() {
  const slide = slides[currentSlide];
  const hidden = Array.from(slide.querySelectorAll('.slide-element')).filter(el => !el.classList.contains('visible'));
  if (hidden.length > 0) {
    hidden[0].classList.add('visible'); playRevealSound(); createParticleBurst(hidden[0]);
    playVideosInElement(hidden[0]);
    animateCounters(hidden[0]);
  }
}

function resetElements(slideIndex) {
  const slide = slides[slideIndex];
  if (!slide) return;
  pauseVideosInSlide(slide);
  slide.querySelectorAll('.slide-element').forEach(el => el.classList.remove('visible'));
  slide.querySelectorAll('.highlighted').forEach(el => el.classList.remove('highlighted'));
  slide.querySelectorAll('.lightable').forEach(el => el.classList.remove('lit-red', 'lit-yellow', 'lit-green'));
  // Reset perf counters
  slide.querySelectorAll('[data-count-to]').forEach(el => { el.textContent = '0.0s'; });
}

function triggerShimmer(el) {
  if (!el) return;
  const shimmer = document.createElement('div');
  shimmer.style.cssText = `
    position: absolute; top: 0; left: 0; width: 60%; height: 100%;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 40%, rgba(255,255,255,0.3) 50%, rgba(255,255,255,0.15) 60%, transparent 100%);
    pointer-events: none; z-index: 10;
    transform: translateX(-160%);
    will-change: transform;
  `;
  el.style.position = 'relative';
  el.style.overflow = 'hidden';
  el.appendChild(shimmer);
  void shimmer.offsetWidth;
  shimmer.style.transition = 'transform 2.5s ease-in-out';
  setTimeout(() => { shimmer.style.transform = 'translateX(300%)'; }, 50);
  setTimeout(() => shimmer.remove(), 3000);
}

function createParticleBurst(element) {
  // Wait slightly longer (100ms) to ensure flexbox layouts have fully settled
  setTimeout(() => {
    // Focus the burst specifically on the icon rather than the whole block container
    let targetEl = element.querySelector('.icon-badge, .card-icon, i') || element;
    
    const rect = targetEl.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    if (!rect || !containerRect) return;

    // Detect CSS scale transform on container (used during auto_render recording)
    const scaleX = containerRect.width / container.offsetWidth || 1;
    const scaleY = containerRect.height / container.offsetHeight || 1;

    const cx = (rect.left - containerRect.left + rect.width / 2) / scaleX;
    const cy = (rect.top - containerRect.top + rect.height / 2) / scaleY;
    
    const particleCount = 30; // Increased for a much more vibrant burst
    const colors = [
      '#FF3F8E', '#04C2C9', '#2E5BFF', '#FF9F00', 
      '#00E676', '#D500F9', '#FFEA00', '#FF1744',
      '#00e5ff', '#84ffff', '#1de9b6', '#a7ffeb'
    ];

    for (let i = 0; i < particleCount; i++) {
      const particle = document.createElement('div');
      particle.className = 'particle';
      
      const angle = (Math.PI * 2 * i) / particleCount + (Math.random() * 0.4 - 0.2);
      const distance = 50 + Math.random() * 90;
      const dx = Math.cos(angle) * distance;
      const dy = Math.sin(angle) * distance;
      const size = 3 + Math.random() * 5;
      const color = colors[Math.floor(Math.random() * colors.length)];
      const duration = 0.7 + Math.random() * 0.5;
      
      particle.style.cssText = `
        position: absolute;
        width: ${size}px;
        height: ${size}px;
        border-radius: 50%;
        background: ${color};
        left: ${cx}px;
        top: ${cy}px;
        pointer-events: none;
        z-index: 2000;
        opacity: 1;
        box-shadow: 0 0 15px ${color}, 0 0 5px ${color};
        transition: transform ${duration}s cubic-bezier(0.22, 1, 0.36, 1), opacity ${duration}s ease-out;
      `;
      
      container.appendChild(particle);
      
      // Force reflow để trình duyệt vẽ trạng thái ban đầu (quan trọng cho headless render)
      void particle.offsetWidth;
      
      setTimeout(() => {
        particle.style.transform = `translate(${dx}px, ${dy}px) scale(0)`;
        particle.style.opacity = '0';
      }, 50);
      
      setTimeout(() => particle.remove(), duration * 1000 + 100);
    }
  }, 100);
}

function updateProgress() {
  updateSlideCounterTotal();
  if (isReady) {
    progressFill.style.width = '0%';
    currentSlideEl.textContent = '0';
  } else {
    progressFill.style.width = ((currentSlide + 1) / totalSlides) * 100 + '%';
    currentSlideEl.textContent = currentSlide + 1;
  }
  updateSlideDeleteControls();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function autoPlay() {
  initAudio(); startBackgroundMusic();
  for (let i = 0; i < totalSlides; i++) {
    if (i > 0) { goToSlide(i); await sleep(800); }
    const els = slides[i].querySelectorAll('.slide-element');
    for (let j = 0; j < els.length; j++) {
      els[j].classList.add('visible'); playRevealSound(); createParticleBurst(els[j]); await sleep(600);
    }
    await sleep(Math.floor(90000 / totalSlides) - els.length * 600);
  }
}

// ============================================
// AUDIO PANEL CONTROLLER
// ============================================
function updateAudioPanel() {
  const badges = [document.getElementById('audioPanelSlide'), document.getElementById('editorAudioPanelSlide')];
  const transitionSelects = [document.getElementById('transitionSelect'), document.getElementById('editorTransitionSelect')];
  const revealSelects = [document.getElementById('revealSelect'), document.getElementById('editorRevealSelect')];
  const badgeText = isReady ? '⏸ Ready' : 'Slide ' + (currentSlide + 1);
  badges.forEach((badge) => {
    if (badge) badge.textContent = badgeText;
  });
  transitionSelects.forEach((select) => {
    if (select) select.value = slideTransitions[currentSlide] || 'minimal';
  });
  revealSelects.forEach((select) => {
    if (select) select.value = slideReveals[currentSlide] || 'ping';
  });
  updateBgmControls();
  updateScriptPanel();
}

function updateScriptPanel() {
  const sBadge = document.getElementById('scriptSlideBadge');
  const sText = document.getElementById('scriptText');
  if (sBadge && sText) {
    if (isReady) {
      sBadge.textContent = '⏸ Ready';
      sText.textContent = 'Bấm vào slide để bắt đầu...';
    } else {
      sBadge.textContent = 'Slide ' + (currentSlide + 1);
      sText.textContent = slideScripts[currentSlide] || '';
    }
  }
  updateScriptEditor();
}

function saveSlideAudioSettings() {
  syncRuntimeSlideSettings();
  setSlideAudioStatus('Đang lưu...');
  savePreviewSettings(setSlideAudioStatus).catch((error) => {
    setSlideAudioStatus(error.message || 'Không lưu được');
  });
}

function setSlideTransition(idx, value) {
  slideTransitions[idx] = value;
  initAudio();
  if (!isMuted) playSlideSound(idx);
  saveSlideAudioSettings();
}

function setSlideReveal(idx, value) {
  slideReveals[idx] = value;
  initAudio();
  if (!isMuted) playRevealSound();
  saveSlideAudioSettings();
}

function audioPanelPrev() { if (currentSlide > 0) goToSlide(currentSlide - 1); }
function audioPanelNext() { if (currentSlide < totalSlides - 1) goToSlide(currentSlide + 1); }

function testTransition() {
  initAudio();
  if (!bgMusicGain && !isMuted) startBackgroundMusic();
  playSlideSound(currentSlide);
}

function testReveal() {
  initAudio();
  if (!bgMusicGain && !isMuted) startBackgroundMusic();
  playRevealSound();
}

// BGM Presets
const bgmPresets = {
  ambient: { chords: [[130.81, 164.81, 196, 246.94], [110, 130.81, 164.81, 196], [87.31, 130.81, 164.81, 207.65], [98, 123.47, 146.83, 174.61]], arps: [[523.25, 659.25, 783.99, 987.77], [440, 523.25, 659.25, 783.99], [349.23, 523.25, 659.25, 830.61], [392, 493.88, 587.33, 698.46]] },
  cinematic: { chords: [[146.83, 174.61, 220, 277.18], [116.54, 146.83, 174.61, 220], [98, 116.54, 146.83, 174.61], [110, 138.59, 164.81, 220]], arps: [[293.66, 349.23, 440, 554.37], [233.08, 293.66, 349.23, 440], [196, 233.08, 293.66, 349.23], [220, 277.18, 329.63, 440]] },
  lofi: { chords: [[130.81, 155.56, 196, 233.08], [110, 138.59, 164.81, 207.65], [87.31, 110, 130.81, 164.81], [98, 123.47, 155.56, 185]], arps: [[523.25, 622.25, 783.99, 932.33], [440, 554.37, 659.25, 783.99], [349.23, 440, 523.25, 659.25], [392, 493.88, 622.25, 739.99]] },
  piano: { chords: [[130.81, 164.81, 196, 261.63], [146.83, 174.61, 220, 293.66], [87.31, 110, 130.81, 174.61], [98, 123.47, 146.83, 196]], arps: [[261.63, 329.63, 392, 523.25], [293.66, 349.23, 440, 587.33], [174.61, 220, 261.63, 349.23], [196, 246.94, 293.66, 392]] },
  dark: { chords: [[65.41, 82.41, 98, 123.47], [73.42, 87.31, 110, 130.81], [55, 69.3, 82.41, 103.83], [61.74, 77.78, 92.5, 116.54]], arps: [[261.63, 311.13, 392, 466.16], [293.66, 349.23, 440, 523.25], [220, 277.18, 329.63, 415.3], [246.94, 311.13, 369.99, 466.16]] }
};

async function switchBGM(preset) {
  const nextBgm = normalizeBgmSettings({
    bgm: {
      ...previewSettings.bgm,
      mode: preset === 'none' ? 'none' : preset === 'custom' ? 'custom' : 'preset',
      preset: bgmPresets[preset] ? preset : previewSettings.bgm.preset
    }
  });
  if (preset === 'custom' && !nextBgm.custom.path && !nextBgm.custom.url) {
    applyBgmSettings({ ...previewSettings, bgm: nextBgm });
    setBgmStatus('Upload file để dùng custom BGM');
    return;
  }
  previewSettings.bgm = nextBgm;
  const p = bgmPresets[nextBgm.preset];
  if (p) {
    for (let i = 0; i < 4; i++) {
      chordProgression[i] = p.chords[i];
      arpNotes[i] = p.arps[i];
    }
  }
  applyBgmSettings(previewSettings);
  stopBackgroundMusic(0.25);
  setTimeout(() => { if (!isMuted) startBackgroundMusic(); }, 320);
  setBgmStatus('Đang lưu...');
  try {
    await savePreviewSettings(setBgmStatus);
  } catch (error) {
    setBgmStatus(error.message || 'Không lưu được');
  }
}

// ============================================
// PERF COUNTER ANIMATION
// ============================================
function animateCounters(element) {
  const counters = element.querySelectorAll('[data-count-to]');
  if (!counters.length) return;
  counters.forEach(el => {
    const target = parseFloat(el.dataset.countTo);
    const duration = 1000; // 1 second
    const startTime = performance.now();
    const prefix = '~';
    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = (target * eased).toFixed(1);
      el.textContent = prefix + current + 's';
      if (progress < 1) requestAnimationFrame(tick);
    }
    // Delay to sync with bar animation
    setTimeout(() => requestAnimationFrame(tick), 200);
  });
}

// Initialize
document.addEventListener('DOMContentLoaded', init);

// Extra visual effects for image-to-code viral slides
(() => {
  const fxStates = new WeakMap();
  function setupCanvas(canvas){
    const ctx = canvas.getContext('2d');
    const state = {ctx,w:0,h:0,dpr:1,pts:[],x:.1,y:0,z:0,t:0,particles:[]};
    fxStates.set(canvas,state);
    function resize(){
      const rect = canvas.getBoundingClientRect();
      state.dpr = window.devicePixelRatio || 1;
      state.w = canvas.offsetWidth || rect.width; 
      state.h = canvas.offsetHeight || rect.height;
      const scaleX = rect.width / state.w || 1;
      const scaleY = rect.height / state.h || 1;
      canvas.width = Math.max(1, state.w * scaleX * state.dpr);
      canvas.height = Math.max(1, state.h * scaleY * state.dpr);
      ctx.setTransform(scaleX * state.dpr, 0, 0, scaleY * state.dpr, 0, 0);
      state.particles = Array.from({length:42},()=>({x:Math.random()*state.w,y:Math.random()*state.h,vx:(Math.random()-.5)*.35,vy:(Math.random()-.5)*.35,r:1+Math.random()*2,h:180+Math.random()*100}));
    }
    resize(); addEventListener('resize',resize,{passive:true});
    return state;
  }
  function lorenz(s, dt=1){
    const {ctx,w,h}=s,dt_sim=.006,sigma=10,rho=28,beta=8/3;
    const steps = Math.max(1, Math.round(5 * dt));
    for(let k=0;k<steps;k++){const dx=sigma*(s.y-s.x),dy=s.x*(rho-s.z)-s.y,dz=s.x*s.y-beta*s.z;s.x+=dx*dt_sim;s.y+=dy*dt_sim;s.z+=dz*dt_sim;s.pts.push([s.x,s.y,s.z,s.t]);if(s.pts.length>850)s.pts.shift();s.t+=.002}
    const a=performance.now()*.00014;ctx.clearRect(0,0,w,h);ctx.lineWidth=1.25;ctx.lineCap='round';
    function raw(p){const ca=Math.cos(a),sa=Math.sin(a);return[p[0]*ca-p[2]*sa,p[1]-25,p[0]*sa+p[2]*ca]}
    const raws=s.pts.map(raw);let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9;raws.forEach(r=>{minX=Math.min(minX,r[0]);maxX=Math.max(maxX,r[0]);minY=Math.min(minY,r[1]);maxY=Math.max(maxY,r[1])});const fit=Math.min(w*.82/(maxX-minX||1),h*.62/(maxY-minY||1)),cx=(minX+maxX)/2,cy=(minY+maxY)/2;
    for(let i=1;i<raws.length;i++){const q=i/raws.length,r0=raws[i-1],r1=raws[i],d0=1+65/(120+r0[2]),d1=1+65/(120+r1[2]);ctx.strokeStyle=`hsla(${185+i*.22},95%,${55+q*24}%,${q*.72})`;ctx.beginPath();ctx.moveTo(w*.5+(r0[0]-cx)*fit*d0,h*.52-(r0[1]-cy)*fit*d0);ctx.lineTo(w*.5+(r1[0]-cx)*fit*d1,h*.52-(r1[1]-cy)*fit*d1);ctx.stroke()}
  }
  function particles(s, mode, dt=1){const {ctx,w,h}=s;ctx.clearRect(0,0,w,h);for(const p of s.particles){p.x+=p.vx*dt;p.y+=p.vy*dt;if(p.x<0||p.x>w)p.vx*=-1;if(p.y<0||p.y>h)p.vy*=-1;ctx.fillStyle=`hsla(${p.h},95%,70%,.65)`;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill()}ctx.strokeStyle='rgba(34,211,238,.13)';for(let i=0;i<s.particles.length;i++)for(let j=i+1;j<s.particles.length;j++){const a=s.particles[i],b=s.particles[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy);if(d<85){ctx.globalAlpha=(85-d)/420;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.globalAlpha=1}}if(mode==='flow'||mode==='scan'){const y=(performance.now()*.08)%h;ctx.fillStyle='rgba(34,211,238,.10)';ctx.fillRect(0,y,w,2)}}
  function rings(s, dt=1){const {ctx,w,h}=s;ctx.clearRect(0,0,w,h);const t=performance.now()*.001;for(let i=0;i<8;i++){ctx.strokeStyle=`hsla(${190+i*16},95%,65%,${.22-i*.018})`;ctx.lineWidth=1.4;ctx.beginPath();ctx.ellipse(w*.5,h*.43,50+i*25+Math.sin(t+i)*8,22+i*15, t*.25+i,0,Math.PI*2);ctx.stroke()}}
  function noise(s, dt=1){particles(s,'scan', dt);const {ctx,w,h}=s;for(let i=0;i<16;i++){ctx.fillStyle=`rgba(251,113,133,${Math.random()*.05})`;ctx.fillRect(Math.random()*w,Math.random()*h,40+Math.random()*90,1)}}
  let lastTime = performance.now();
  function tick(){
    const now = performance.now();
    let dt = (now - lastTime) / 16.666;
    if (dt > 5) dt = 5;
    lastTime = now;
    document.querySelectorAll('.fx-canvas').forEach(c=>{if(c.hidden)return;const s=fxStates.get(c)||setupCanvas(c),fx=c.dataset.fx;if(fx==='lorenz')lorenz(s, dt);else if(fx==='rings')rings(s, dt);else if(fx==='noise')noise(s, dt);else particles(s,fx, dt)});requestAnimationFrame(tick)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',tick);else tick();
})();
