/* Gratitude appearance preference: browser storage contains no business data. */
(() => {
  const root = document.documentElement;
  const key = 'arcenal-matos-appearance';
  const modes = ['system', 'light', 'dark'];
  root.classList.add('js');
  try {
    const saved = localStorage.getItem(key);
    root.dataset.theme = modes.includes(saved) ? saved : 'system';
  } catch { root.dataset.theme = 'system'; }

  document.addEventListener('DOMContentLoaded', () => {
    const choice = document.getElementById('theme-choice');
    choice.value = root.dataset.theme;
    choice.addEventListener('change', () => {
      root.dataset.theme = choice.value;
      try { localStorage.setItem(key, choice.value); } catch { /* Keep the choice for this page. */ }
    });
    const button = document.getElementById('nav-toggle');
    const sidebar = document.querySelector('.sidebar');
    function closeNavigation() {
      sidebar.classList.remove('nav-open');
      button?.setAttribute('aria-expanded', 'false');
    }
    button?.addEventListener('click', () => {
      const open = sidebar.classList.toggle('nav-open');
      button.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && sidebar.classList.contains('nav-open')) {
        closeNavigation();
        button.focus();
      }
    });
    document.querySelectorAll('.tablewrap').forEach(wrapper => {
      wrapper.tabIndex = 0;
      wrapper.setAttribute('role', 'region');
      wrapper.setAttribute('aria-label', 'Tableau défilant');
      const hint = document.createElement('p');
      hint.className = 'table-scroll-hint';
      hint.textContent = 'Faites défiler le tableau horizontalement pour consulter toutes les colonnes.';
      wrapper.before(hint);
      const update = () => { hint.hidden = wrapper.scrollWidth <= wrapper.clientWidth; };
      update();
      if (typeof ResizeObserver !== 'undefined') new ResizeObserver(update).observe(wrapper);
    });
    document.querySelectorAll('form[data-confirm]').forEach(form => {
      form.addEventListener('submit', event => {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
      });
    });
  });
})();
