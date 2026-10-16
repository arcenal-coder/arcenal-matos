document.querySelectorAll('[data-check-badges]').forEach(button => {
  button.addEventListener('click', () => {
    button.closest('form').querySelectorAll('input[type=checkbox][name=badges]').forEach(input => {
      if (!input.disabled) input.checked = button.dataset.checkBadges === 'true';
    });
  });
});
