const ICON = { info: 'i-info', warn: 'i-alert', error: 'i-alert' };

export function toast(message, { kind = 'info', timeout = 5000 } = {}) {
  const host = document.getElementById('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast toast--${kind}`;
  el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  el.innerHTML = `<svg aria-hidden="true"><use href="assets/icons.svg#${ICON[kind]}"></use></svg><div></div>
    <button class="toast__close" aria-label="Dismiss"><svg width="16" height="16" aria-hidden="true"><use href="assets/icons.svg#i-close"></use></svg></button>`;
  el.children[1].textContent = message;
  const close = () => el.remove();
  el.querySelector('button').addEventListener('click', close);
  host.append(el);
  while (host.children.length > 4) host.firstElementChild.remove();
  if (timeout) setTimeout(close, timeout);
}
