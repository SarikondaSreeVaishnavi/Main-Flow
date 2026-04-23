const messageForm = document.getElementById('messageForm');
const smtpForm = document.getElementById('smtpForm');
const recurrenceType = document.getElementById('recurrenceType');
const intervalWrap = document.getElementById('intervalWrap');
const specificDatesWrap = document.getElementById('specificDatesWrap');
const endDateWrap = document.getElementById('endDateWrap');
const specificDatePicker = document.getElementById('specificDatePicker');
const addDateButton = document.getElementById('addDateButton');
const selectedDatesEl = document.getElementById('selectedDates');
const preview = document.getElementById('messagePreview');

let currentUser = null;
const selectedDates = new Set();

function toggleIntervalInput() {
  const recurring = ['daily', 'weekly', 'every_n_days'].includes(recurrenceType.value);
  intervalWrap.classList.toggle('hidden', recurrenceType.value !== 'every_n_days');
  specificDatesWrap.classList.toggle('hidden', recurrenceType.value !== 'specific_dates');
  endDateWrap.classList.toggle('hidden', !recurring);
  if (!recurring) {
    document.getElementById('recurrenceEndAt').value = '';
  }
}

function renderSelectedDates() {
  if (!selectedDates.size) {
    selectedDatesEl.innerHTML = '<span class="muted">No specific dates added yet.</span>';
    return;
  }

  selectedDatesEl.innerHTML = Array.from(selectedDates).sort().map((dateValue) => `
    <button type="button" class="date-chip" data-date="${dateValue}">
      ${dateValue}
      <span>Remove</span>
    </button>
  `).join('');
}

function buildSpecificSendTimes(baseDateTime, dateValues) {
  const base = new Date(baseDateTime);
  const hours = base.getHours();
  const minutes = base.getMinutes();
  const hh = String(hours).padStart(2, '0');
  const mm = String(minutes).padStart(2, '0');

  return dateValues.map((dateValue) => `${dateValue}T${hh}:${mm}:00`);
}

async function loadMe() {
  currentUser = await apiJson('/api/me');
  document.getElementById('senderEmail').textContent = currentUser.smtp_sender || 'Not set';
  document.getElementById('smtpState').textContent = currentUser.smtp_ready ? 'Ready' : 'Missing credentials';
  document.getElementById('welcomeTitle').textContent = `Welcome, ${currentUser.name}`;
  document.getElementById('welcomeBody').textContent = 'Compose once, choose recurring or specific dates, and send with your saved SMTP account.';
}

async function loadSmtpCredentials() {
  const data = await apiJson('/api/smtp-credentials');
  document.getElementById('smtpHost').value = data.smtp_host || 'smtp.gmail.com';
  document.getElementById('smtpPort').value = data.smtp_port || 465;
  document.getElementById('smtpUsername').value = data.smtp_username || '';
}

smtpForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await apiJson('/api/smtp-credentials', {
      method: 'POST',
      body: JSON.stringify({
        smtp_host: document.getElementById('smtpHost').value,
        smtp_port: document.getElementById('smtpPort').value,
        smtp_username: document.getElementById('smtpUsername').value,
        smtp_password: document.getElementById('smtpPassword').value,
      }),
    });
    document.getElementById('smtpPassword').value = '';
    toast('SMTP credentials saved.');
    await loadMe();
  } catch (error) {
    toast(error.message, 'error');
  }
});

addDateButton.addEventListener('click', () => {
  const picked = specificDatePicker.value;
  if (!picked) {
    toast('Pick a date first.', 'error');
    return;
  }
  selectedDates.add(picked);
  specificDatePicker.value = '';
  renderSelectedDates();
});

selectedDatesEl.addEventListener('click', (event) => {
  const chip = event.target.closest('.date-chip');
  if (!chip) return;
  selectedDates.delete(chip.dataset.date);
  renderSelectedDates();
});

async function loadMessages() {
  const messages = await apiJson('/api/messages');
  if (!messages.length) {
    preview.innerHTML = '<div class="preview-card"><strong>No scheduled messages yet.</strong><span class="muted">Create your first message on the left.</span></div>';
    return;
  }

  preview.innerHTML = messages.slice(0, 5).map((message) => `
    <div class="preview-card">
      <div class="message-meta">
        <span class="message-pill"><i class="dot ${statusDotClass(message.status)}"></i>${message.status}</span>
        <span>#${message.id}</span>
        <span>Sender ${message.sender_user_id}</span>
        <span>Send to ${message.recipient_user_id ?? 'n/a'}</span>
      </div>
      <strong>${message.subject}</strong>
      <span>${message.recipient_email}</span>
      <div class="preview-meta">
        <span>First send: ${formatDate(message.send_at)}</span>
        <span>Next: ${formatDate(message.next_run_at)}</span>
        <span>${recurrenceLabel(message)}</span>
      </div>
    </div>
  `).join('');
}

messageForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const baseSendAt = document.getElementById('sendAt').value;
  const recurrence = recurrenceType.value;
  const recurrenceEndAt = document.getElementById('recurrenceEndAt').value;
  const recurring = ['daily', 'weekly', 'every_n_days'].includes(recurrence);
  const specificDates = recurrence === 'specific_dates' ? Array.from(selectedDates).sort() : [];

  if (recurrence === 'specific_dates' && !specificDates.length) {
    toast('Add one or more dates for specific dates mode.', 'error');
    return;
  }

  try {
    await apiJson('/api/messages', {
      method: 'POST',
      body: JSON.stringify({
        recipient_email: document.getElementById('recipientEmail').value,
        subject: document.getElementById('subject').value,
        body: document.getElementById('body').value,
        send_at: baseSendAt,
        recurrence_type: recurrence,
        recurrence_interval_days: document.getElementById('intervalDays').value,
        recurrence_end_at: recurring ? (recurrenceEndAt || undefined) : undefined,
        specific_send_times: recurrence === 'specific_dates' ? buildSpecificSendTimes(baseSendAt, specificDates) : undefined,
      }),
    });
    toast(recurrence === 'specific_dates' ? 'Specific-date schedules created.' : 'Message scheduled.');
    messageForm.reset();
    recurrenceType.value = 'once';
    selectedDates.clear();
    renderSelectedDates();
    toggleIntervalInput();
    await loadMessages();
  } catch (error) {
    toast(error.message, 'error');
  }
});

recurrenceType.addEventListener('change', toggleIntervalInput);
document.getElementById('logoutButton').addEventListener('click', logoutUser);
toggleIntervalInput();
renderSelectedDates();

Promise.all([loadMe(), loadSmtpCredentials()]).then(loadMessages).catch((error) => {
  toast(error.message, 'error');
  window.location.href = '/login';
});
