async function loadMessagesTable() {
  const messages = await apiJson('/api/messages');
  const tbody = document.getElementById('messagesTable');

  if (!messages.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="muted">No scheduled messages stored yet.</td></tr>';
    return;
  }

  tbody.innerHTML = messages.map((message) => `
    <tr>
      <td>#${message.id}</td>
      <td>${message.sender_user_id}</td>
      <td>${message.recipient_user_id ?? '—'}</td>
      <td>${message.recipient_email}</td>
      <td>${message.subject}</td>
      <td>${recurrenceLabel(message)}</td>
      <td>${formatDate(message.send_at)}</td>
      <td>${formatDate(message.next_run_at)}</td>
      <td>${formatDate(message.last_sent_at)}</td>
      <td><span class="message-pill"><i class="dot ${statusDotClass(message.status)}"></i>${message.status}</span></td>
      <td>
        <div class="row-actions">
          ${message.status === 'scheduled' ? `<button class="secondary-btn" type="button" onclick="cancelMessage(${message.id})">Cancel</button>` : ''}
        </div>
      </td>
    </tr>
  `).join('');
}

async function cancelMessage(id) {
  try {
    await apiJson(`/api/messages/${id}`, { method: 'DELETE' });
    toast('Message cancelled.');
    loadMessagesTable();
  } catch (error) {
    toast(error.message, 'error');
  }
}

document.getElementById('logoutButton').addEventListener('click', logoutUser);
loadMessagesTable().catch((error) => {
  toast(error.message, 'error');
  window.location.href = '/login';
});
