const $ = (selector) => document.querySelector(selector);
const i18n = window.PlaqueI18n;
const t = (key, values) => i18n.t(key, values);
i18n.applyStatic();
const elements = {
  fileInput: $('#file-input'), dropzone: $('#dropzone'), selectedFile: $('#selected-file'),
  fileName: $('#file-name'), fileSize: $('#file-size'), start: $('#start-button'),
  feedback: $('#upload-feedback'), health: $('#system-status'),
  jobPanel: $('#current-job'), jobStage: $('#job-stage'), jobPercent: $('#job-percent'),
  jobProgress: $('#job-progress'), jobDetail: $('#job-detail'), jobRegions: $('#job-regions'),
  empty: $('#empty-view'), result: $('#result-video'), source: $('#source-video'),
  compare: $('#compare-view'), compareSource: $('#compare-source'), compareResult: $('#compare-result'),
  viewerFilename: $('#viewer-filename'), watermark: $('#viewer-watermark'), download: $('#download-link'),
  history: $('#history-list'), count: $('#history-count'),
};

let chosenFile = null;
let localURL = null;
let activeJob = null;
let activeView = 'result';
let uploading = false;
let engineReady = false;
let viewerKey = '';
let lastJobs = [];
let feedbackKey = '';
let healthState = 'checking';
const allowedExtensions = new Set(['mp4', 'mov', 'mkv', 'avi', 'webm', 'wmv', 'flv', 'm4v']);

function formatSize(bytes) {
  const units = i18n.language === 'fr' ? ['Ko', 'Mo'] : ['KB', 'MB'];
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} ${units[0]}`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} ${units[1]}`;
}

function setFeedback(key, error = false) {
  feedbackKey = key;
  elements.feedback.textContent = key ? t(key) : '';
  elements.feedback.classList.toggle('error', error);
}

function selectFile(file) {
  if (!file) return;
  const extension = file.name.split('.').pop().toLowerCase();
  if (!allowedExtensions.has(extension)) {
    setFeedback('file_invalid_format', true);
    return;
  }
  if (file.size > 4 * 1024 ** 3) {
    setFeedback('file_too_large', true);
    return;
  }
  if (localURL) URL.revokeObjectURL(localURL);
  localURL = URL.createObjectURL(file);
  chosenFile = file;
  activeJob = null;
  viewerKey = '';
  activeView = 'source';
  elements.selectedFile.hidden = false;
  elements.fileName.textContent = file.name;
  elements.fileSize.textContent = formatSize(file.size);
  elements.start.disabled = !engineReady || uploading;
  elements.jobPanel.hidden = true;
  setFeedback('');
  renderViewer();
}

elements.fileInput.addEventListener('change', () => selectFile(elements.fileInput.files[0]));
$('#remove-file').addEventListener('click', () => {
  chosenFile = null;
  elements.fileInput.value = '';
  elements.selectedFile.hidden = true;
  elements.start.disabled = true;
  if (localURL) URL.revokeObjectURL(localURL);
  localURL = null;
  renderViewer();
});
for (const type of ['dragenter', 'dragover']) {
  elements.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    elements.dropzone.classList.add('dragover');
  });
}
for (const type of ['dragleave', 'drop']) {
  elements.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    elements.dropzone.classList.remove('dragover');
  });
}
elements.dropzone.addEventListener('drop', (event) => selectFile(event.dataTransfer.files[0]));
document.querySelectorAll('.viewer-tab').forEach((button) => {
  button.addEventListener('click', () => { activeView = button.dataset.view; renderViewer(); });
});

function setVideo(video, url) {
  if (video.dataset.url === url) return;
  video.pause();
  video.src = url;
  video.dataset.url = url;
  video.load();
}

function renderViewer() {
  const sourceURL = activeJob ? `/api/jobs/${activeJob.id}/source` : localURL;
  const resultURL = activeJob?.status === 'done' ? `/api/jobs/${activeJob.id}/video` : null;
  if ((activeView === 'result' || activeView === 'compare') && !resultURL) activeView = sourceURL ? 'source' : 'result';
  const key = `${activeJob?.id || localURL || ''}:${activeJob?.status || ''}`;
  if (viewerKey !== key) {
    if (sourceURL) {
      setVideo(elements.source, sourceURL);
      setVideo(elements.compareSource, sourceURL);
    }
    if (resultURL) {
      setVideo(elements.result, resultURL);
      setVideo(elements.compareResult, resultURL);
    }
    viewerKey = key;
  }
  const hasVideo = Boolean(sourceURL || resultURL);
  elements.empty.hidden = hasVideo;
  elements.source.hidden = !hasVideo || activeView !== 'source';
  elements.result.hidden = !resultURL || activeView !== 'result';
  elements.compare.hidden = !resultURL || activeView !== 'compare';
  elements.watermark.hidden = !hasVideo || activeView === 'compare';
  elements.viewerFilename.textContent = activeJob?.filename || chosenFile?.name || t('no_video');
  elements.download.hidden = !resultURL;
  if (resultURL) elements.download.href = `${resultURL}?download=1`;
  document.querySelectorAll('.viewer-tab').forEach((button) => {
    const selected = button.dataset.view === activeView;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
}

function renderJob(job) {
  elements.jobPanel.hidden = false;
  const legacyStages = {'En attente': 'queued', 'Chargement du modèle': 'loading_model',
    'Détection et floutage': 'processing', 'Terminé': 'done', 'Échec': 'error'};
  elements.jobStage.textContent = t(`stage_${legacyStages[job.stage] || job.stage || job.status}`);
  elements.jobPercent.textContent = `${job.progress}%`;
  elements.jobProgress.style.width = `${job.progress}%`;
  const count = job.regions || 0;
  elements.jobRegions.textContent = t(count === 0 ? 'zero_regions' : count === 1 ? 'one_region' : 'many_regions', {count});
  if (job.status === 'done') {
    elements.jobDetail.textContent = t('job_done_detail', {count: job.frames});
    elements.jobDetail.style.color = '';
  } else if (job.status === 'error') {
    elements.jobDetail.textContent = job.error_code ? t(`error_${job.error_code}`) : t('job_failed_detail');
    elements.jobDetail.title = job.error || '';
    elements.jobDetail.style.color = '#ffad9e';
  } else {
    elements.jobDetail.textContent = job.frames ? t('job_frames', {count: job.frames}) : t('job_initial');
    elements.jobDetail.title = '';
    elements.jobDetail.style.color = '';
  }
}

function showUploadProgress(percent) {
  elements.jobPanel.hidden = false;
  elements.jobStage.textContent = t('stage_upload');
  elements.jobPercent.textContent = `${percent}%`;
  elements.jobProgress.style.width = `${percent}%`;
  elements.jobDetail.textContent = t('job_upload_detail');
  elements.jobRegions.textContent = '';
}

elements.start.addEventListener('click', () => {
  if (!chosenFile || !engineReady || uploading) return;
  uploading = true;
  elements.start.disabled = true;
  setFeedback('');
  showUploadProgress(0);
  const strength = document.querySelector('input[name="strength"]:checked').value;
  const request = new XMLHttpRequest();
  request.open('POST', `/api/jobs?filename=${encodeURIComponent(chosenFile.name)}&strength=${strength}`);
  request.setRequestHeader('Content-Type', 'application/octet-stream');
  request.upload.onprogress = (event) => {
    if (event.lengthComputable) showUploadProgress(Math.min(99, Math.round(event.loaded / event.total * 100)));
  };
  request.onload = () => {
    uploading = false;
    let response;
    try { response = JSON.parse(request.responseText); } catch { response = {}; }
    if (request.status !== 201) {
      elements.start.disabled = !chosenFile || !engineReady;
      elements.jobPanel.hidden = true;
      setFeedback(response.code ? `error_${response.code}` : 'upload_failed', true);
      return;
    }
    activeJob = response;
    chosenFile = null;
    elements.fileInput.value = '';
    elements.selectedFile.hidden = true;
    elements.start.disabled = true;
    if (localURL) URL.revokeObjectURL(localURL);
    localURL = null;
    viewerKey = '';
    renderViewer();
    renderJob(response);
    refreshJobs();
  };
  request.onerror = () => {
    uploading = false;
    elements.start.disabled = !chosenFile || !engineReady;
    elements.jobPanel.hidden = true;
    setFeedback('upload_network_error', true);
  };
  request.send(chosenFile);
});

function renderHistory(jobs) {
  lastJobs = jobs;
  elements.history.replaceChildren();
  elements.count.textContent = t(jobs.length === 0 ? 'zero_videos' : jobs.length === 1 ? 'one_video' : 'many_videos', {count: jobs.length});
  if (!jobs.length) {
    const empty = document.createElement('div');
    empty.className = 'history-empty';
    empty.textContent = t('history_empty');
    elements.history.append(empty);
    return;
  }
  for (const job of jobs) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = `history-row${activeJob?.id === job.id ? ' selected' : ''}`;
    const icon = document.createElement('span');
    icon.className = 'history-icon';
    icon.textContent = '▶';
    const name = document.createElement('span');
    name.className = 'history-name';
    const title = document.createElement('strong');
    title.textContent = job.filename;
    const date = document.createElement('small');
    date.textContent = `${new Date(job.created_at).toLocaleString(i18n.language === 'fr' ? 'fr-FR' : 'en-US', { dateStyle: 'medium', timeStyle: 'short' })} · ${formatSize(job.size)}`;
    name.append(title, date);
    const badge = document.createElement('span');
    badge.className = `history-state ${job.status}`;
    badge.textContent = t(`status_${job.status}`);
    const arrow = document.createElement('span');
    arrow.className = 'history-arrow';
    arrow.textContent = '↗';
    row.append(icon, name, badge, arrow);
    row.addEventListener('click', () => {
      activeJob = job;
      chosenFile = null;
      elements.fileInput.value = '';
      elements.selectedFile.hidden = true;
      elements.start.disabled = true;
      if (localURL) URL.revokeObjectURL(localURL);
      localURL = null;
      viewerKey = '';
      activeView = job.status === 'done' ? 'result' : 'source';
      renderViewer();
      renderJob(job);
      renderHistory(jobs);
      window.scrollTo({top: 0, behavior: 'smooth'});
    });
    elements.history.append(row);
  }
}

async function refreshJobs() {
  try {
    const response = await fetch('/api/jobs', {cache: 'no-store'});
    if (!response.ok) throw new Error('Liste indisponible');
    const jobs = await response.json();
    if (activeJob) {
      const latest = jobs.find((job) => job.id === activeJob.id);
      if (latest) {
        const wasDone = activeJob.status === 'done';
        activeJob = latest;
        if (!wasDone && latest.status === 'done') activeView = 'result';
        renderJob(latest);
        renderViewer();
      }
    }
    renderHistory(jobs);
  } catch {
    // Keep the current preview; the next poll can reconnect.
  }
}

function renderHealth() {
  elements.health.classList.toggle('bad', healthState !== 'ready');
  elements.health.lastElementChild.textContent = t(`engine_${healthState}`);
}

async function checkHealth() {
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    const health = await response.json();
    engineReady = response.ok && health.model_ready && health.ffmpeg_ready && health.ffprobe_ready && health.python_ready;
    healthState = engineReady ? 'ready' : 'setup';
    renderHealth();
    if (!engineReady && !feedbackKey) setFeedback('setup_help', true);
    if (engineReady && feedbackKey === 'setup_help') setFeedback('');
    elements.start.disabled = !engineReady || !chosenFile || uploading;
  } catch {
    engineReady = false;
    healthState = 'unavailable';
    renderHealth();
    elements.start.disabled = true;
  }
}

document.querySelectorAll('.language-switch button').forEach((button) => {
  button.addEventListener('click', () => {
    i18n.setLanguage(button.dataset.lang);
    renderHealth();
    if (feedbackKey) setFeedback(feedbackKey, elements.feedback.classList.contains('error'));
    if (uploading) showUploadProgress(Number.parseInt(elements.jobPercent.textContent, 10) || 0);
    else if (activeJob) renderJob(activeJob);
    renderViewer();
    renderHistory(lastJobs);
  });
});

let syncing = false;
for (const [a, b] of [[elements.compareSource, elements.compareResult], [elements.compareResult, elements.compareSource]]) {
  a.addEventListener('play', () => { if (!syncing && b.paused) { syncing = true; b.play().catch(() => {}); syncing = false; } });
  a.addEventListener('pause', () => { if (!syncing && !b.paused) { syncing = true; b.pause(); syncing = false; } });
  a.addEventListener('seeked', () => { if (!syncing && Number.isFinite(b.duration) && Math.abs(a.currentTime - b.currentTime) > .25) { syncing = true; b.currentTime = Math.min(a.currentTime, b.duration); syncing = false; } });
}

checkHealth();
async function pollJobs() {
  await refreshJobs();
  const active = activeJob && ['queued', 'processing'].includes(activeJob.status);
  setTimeout(pollJobs, document.hidden ? 15000 : active ? 1500 : 5000);
}
pollJobs();
setInterval(checkHealth, 30000);
