/* Shared V1.0 page interactions. Keep this file dependency-free. */
(function () {
    'use strict';

    function closeMobileNav() {
        document.body.classList.remove('nav-open');
        const toggle = document.getElementById('nav-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const toggle = document.getElementById('nav-toggle');
        const backdrop = document.getElementById('nav-backdrop');

        if (toggle) {
            toggle.addEventListener('click', function () {
                const open = document.body.classList.toggle('nav-open');
                toggle.setAttribute('aria-expanded', String(open));
            });
        }
        if (backdrop) backdrop.addEventListener('click', closeMobileNav);
        document.querySelectorAll('#app-nav a').forEach(function (link) {
            link.addEventListener('click', closeMobileNav);
        });

        document.querySelectorAll('form[data-confirm]').forEach(function (form) {
            form.addEventListener('submit', function (event) {
                if (!window.confirm(form.dataset.confirm)) event.preventDefault();
            });
        });

        document.querySelectorAll('form[data-busy-text]').forEach(function (form) {
            form.addEventListener('submit', function () {
                const submit = form.querySelector('button[type="submit"], input[type="submit"]');
                if (!submit) return;
                submit.disabled = true;
                if (submit.tagName === 'BUTTON') submit.textContent = form.dataset.busyText;
                else submit.value = form.dataset.busyText;
            });
        });

        document.querySelectorAll('[data-quantity-step]').forEach(function (button) {
            button.addEventListener('click', function () {
                const input = document.getElementById(button.dataset.quantityStep);
                if (!input) return;
                const step = Number(input.step) || 1;
                const min = input.min === '' ? 0 : Number(input.min);
                const max = input.max === '' ? Infinity : Number(input.max);
                const direction = button.dataset.direction === 'down' ? -1 : 1;
                const current = Number(input.value) || 0;
                input.value = Math.min(max, Math.max(min, current + direction * step));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
    });
})();
