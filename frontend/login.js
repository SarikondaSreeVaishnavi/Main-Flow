const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const tabs = document.querySelectorAll('.auth-tab');

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    tabs.forEach((item) => item.classList.remove('active'));
    document.querySelectorAll('.auth-form').forEach((form) => form.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.tab).classList.add('active');
  });
});

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await apiJson('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: document.getElementById('loginEmail').value,
        password: document.getElementById('loginPassword').value,
      }),
    });
    window.location.href = '/dashboard';
  } catch (error) {
    toast(error.message, 'error');
  }
});

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await apiJson('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('registerName').value,
        email: document.getElementById('registerEmail').value,
        password: document.getElementById('registerPassword').value,
      }),
    });
    toast('Account created. Redirecting...', 'success');
    window.setTimeout(() => {
      window.location.href = '/dashboard';
    }, 800);
  } catch (error) {
    toast(error.message, 'error');
  }
});
