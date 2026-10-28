import { ROUTES } from '../router.js';

export function initSidebar() {
  const nav = document.getElementById('nav');
  nav.innerHTML = ROUTES.map((r, i) => `
    <a class="nav__link" href="#/${r.id}" data-id="${r.id}" title="${r.label}">
      <svg aria-hidden="true"><use href="assets/icons.svg#${r.icon}"></use></svg>
      <span class="nav__label">${r.label}</span>
      <span class="nav__num">${String(i + 1).padStart(2, '0')}</span>
    </a>`).join('');

  const btn = document.getElementById('menu-btn');
  const setOpen = (open) => {
    document.body.classList.toggle('nav-open', open);
    btn.setAttribute('aria-expanded', String(open));
  };
  btn.addEventListener('click', () => setOpen(!document.body.classList.contains('nav-open')));
  nav.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });

  return {
    setActive(id) {
      for (const a of nav.querySelectorAll('a')) {
        if (a.dataset.id === id) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
      }
    },
  };
}
