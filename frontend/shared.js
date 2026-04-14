async function apiJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    credentials: 'same-origin',
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || 'Request failed');
  }
  return data;
}

function toast(message, type = 'success') {
  const element = document.getElementById('toast');
  if (!element) return;
  element.textContent = message;
  element.className = `toast ${type} show`;
  window.clearTimeout(window.__toastTimer);
  window.__toastTimer = window.setTimeout(() => element.classList.remove('show'), 2800);
}

function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

async function logoutUser() {
  await apiJson('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

function recurrenceLabel(message) {
  if (message.recurrence_type === 'every_n_days') {
    return `Every ${message.recurrence_interval_days} days`;
  }
  if (message.recurrence_type === 'daily') return 'Daily';
  if (message.recurrence_type === 'weekly') return 'Weekly';
  return 'One time';
}

function statusDotClass(status) {
  if (status === 'sent') return 'dot-sent';
  if (status === 'failed') return 'dot-failed';
  if (status === 'cancelled') return 'dot-cancelled';
  return 'dot-scheduled';
}
