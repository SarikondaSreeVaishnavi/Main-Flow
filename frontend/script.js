function toast(msg, type = 'success') {
  const element = document.getElementById('toast');
  element.textContent = msg;
  element.className = `toast ${type} show`;
  setTimeout(() => element.classList.remove('show'), 3000);
}

async function loadSuggestions() {
  const response = await fetch('/api/suggestions');
  const data = await response.json();
  document.getElementById('suggestions').innerHTML = data.map((suggestion) => `
    <button class="sug-btn" type="button" onclick="applySuggestion('${suggestion.datetime}')">
      <strong>${suggestion.label}</strong>
      <span>${suggestion.reason}</span>
    </button>
  `).join('');
}

function applySuggestion(datetimeValue) {
  document.getElementById('send_at').value = datetimeValue;
}

async function loadQueue() {
  const response = await fetch('/api/emails');
  const data = await response.json();
  const queue = document.getElementById('queue');

  if (!data.length) {
    queue.innerHTML = '<div class="empty">No emails scheduled yet.</div>';
    return;
  }

  data.sort((a, b) => new Date(a.send_at) - new Date(b.send_at));
  queue.innerHTML = data.map((email) => `
    <div class="email-row">
      <div class="status-dot dot-${email.status}"></div>
      <div class="email-info">
        <strong>${email.subject} → ${email.to}</strong>
        <small>${email.status === 'pending' ? '⏰ Sends ' + new Date(email.send_at).toLocaleString() : email.status.charAt(0).toUpperCase() + email.status.slice(1)}</small>
      </div>
      ${email.status === 'pending' ? `<button class="cancel-btn" type="button" onclick="cancelEmail('${email.id}')">Cancel</button>` : ''}
    </div>
  `).join('');
}

async function scheduleEmail() {
  const payload = {
    to: document.getElementById('to').value,
    subject: document.getElementById('subject').value,
    body: document.getElementById('body').value,
    send_at: document.getElementById('send_at').value,
  };

  if (!payload.to || !payload.subject || !payload.body || !payload.send_at) {
    toast('Please fill in all fields.', 'error');
    return;
  }

  const response = await fetch('/api/emails', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    toast(data.error, 'error');
    return;
  }

  toast('Email scheduled!');
  ['to', 'subject', 'body', 'send_at'].forEach((field) => {
    document.getElementById(field).value = '';
  });
  loadQueue();
}

async function cancelEmail(id) {
  const response = await fetch(`/api/emails/${id}`, { method: 'DELETE' });
  const data = await response.json();
  if (!response.ok) {
    toast(data.error, 'error');
    return;
  }

  toast('Email cancelled.');
  loadQueue();
}

document.getElementById('scheduleButton').addEventListener('click', scheduleEmail);
loadSuggestions();
loadQueue();
setInterval(loadQueue, 10000);
