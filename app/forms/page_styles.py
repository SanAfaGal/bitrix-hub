"""CSS del formulario de Autorización de Corretaje — separado de page.py por tamaño."""
from __future__ import annotations

FORM_STYLE = """<style>
  :root {
    color-scheme: light;

    --color-navy: #044c7c;
    --color-teal: #0c688e;
    --color-teal-hover: #0a5578;
    --color-error: #b3453a;
    --color-error-bg: #fbeceb;
    --color-success: #2f8f5b;
    --color-success-bg: #e9f6ee;
    --color-info-bg: #e8f1f5;
    --color-warning: #9a6b12;
    --color-warning-bg: #fdf2dc;
    --color-warning-border: #f0cd85;
    --color-bg: #f3f3fb;
    --color-card: #ffffff;
    --color-border: #cccccc;
    --color-text-muted: #848484;
    --color-text-faint: #9ea7aa;
    --color-label: #9c8c7c;
    --color-on-accent: #ffffff;

    --font-family: 'Barlow Condensed', -apple-system, 'Segoe UI', sans-serif;

    --space-1: 4px;  --space-2: 8px;  --space-3: 12px;  --space-4: 16px;
    --space-5: 20px; --space-6: 24px; --space-7: 28px;

    --radius-sm: 10px; --radius-md: 12px; --radius-lg: 16px; --radius-xl: 20px; --radius-pill: 999px;

    --shadow-card: 0 10px 30px rgba(4, 76, 124, 0.08);

    --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    font-family: var(--font-family);
    background: var(--color-bg);
    color: var(--color-navy);
  }

  .page {
    min-height: 100vh;
    display: flex;
    justify-content: center;
    padding: 40px 20px;
  }
  @media (max-width: 480px) {
    .page { padding: 20px 12px; }
  }

  .frame {
    width: 100%;
    max-width: 560px;
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  #form-flow {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    text-align: center;
  }
  .brand__logo {
    height: 40px;
    width: auto;
  }
  .brand__name {
    font-size: 22px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-navy);
  }
  .brand__tagline {
    font-size: 14px;
    font-weight: 500;
    color: var(--color-teal);
  }

  .card {
    background: var(--color-card);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-card);
    padding: var(--space-7) var(--space-6);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .card__header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: var(--space-2);
  }
  .card__title {
    font-size: 20px;
    font-weight: 700;
    margin: 0;
    color: var(--color-navy);
  }
  .card__subtitle {
    font-size: 14px;
    font-weight: 500;
    margin: 0;
    color: var(--color-text-muted);
  }

  .success-view {
    align-items: center;
    text-align: center;
    gap: var(--space-3);
  }
  .success-view--hidden { display: none; }
  .success-view__icon {
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--color-success-bg);
    color: var(--color-success);
    font-size: 28px;
    font-weight: 700;
  }
  .success-view__title {
    font-size: 20px;
    font-weight: 700;
    margin: 0;
    color: var(--color-navy);
  }
  .success-view__text {
    font-size: 14px;
    font-weight: 500;
    margin: 0;
    color: var(--color-text-muted);
  }

  .document-cta {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    background: var(--color-info-bg);
    border-radius: var(--radius-md);
    border: 1.5px solid transparent;
    padding: var(--space-3) var(--space-4);
    text-decoration: none;
    color: var(--color-navy);
    transition: border-color 0.15s var(--ease-standard);
  }
  .document-cta:hover { border-color: var(--color-teal); }
  .document-cta__icon { font-size: 26px; line-height: 1; }
  .document-cta__text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
  }
  .document-cta__text strong { font-size: 14px; font-weight: 700; }
  .document-cta__text span {
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
  }
  .document-cta__arrow {
    font-size: 20px;
    font-weight: 700;
    color: var(--color-teal);
  }

  form { display: flex; flex-direction: column; gap: var(--space-4); }

  .form-section__title {
    display: inline-flex;
    align-self: flex-start;
    align-items: center;
    gap: var(--space-2);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: var(--color-on-accent);
    background: var(--color-teal);
    border-radius: var(--radius-pill);
    padding: 7px 16px;
    margin-top: var(--space-5);
    box-shadow: 0 6px 14px rgba(4, 76, 124, 0.28);
  }
  .form-section__title:first-of-type {
    margin-top: 0;
  }
  .form-section__title-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }

  .field { display: flex; flex-direction: column; gap: var(--space-1); }
  .field--hidden { display: none; }
  .field__label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-navy);
  }
  .field__required {
    color: var(--color-error);
  }
  .field__hint {
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    margin-top: -2px;
  }

  .submit-warning {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    background: var(--color-warning-bg);
    border: 1.5px solid var(--color-warning-border);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--color-warning);
  }
  .submit-warning__icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .field__input {
    font-family: var(--font-family);
    font-size: 16px;
    font-weight: 500;
    padding: 10px 12px;
    border: 1.5px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-card);
    color: var(--color-navy);
    width: 100%;
    transition: border-color 0.15s var(--ease-standard);
  }
  .field__input:focus {
    outline: none;
    border-color: var(--color-teal);
  }
  .field__input--invalid {
    border-color: var(--color-error);
  }
  .field__error {
    display: none;
    font-size: 12px;
    font-weight: 600;
    color: var(--color-error);
  }
  .field__error--visible {
    display: block;
  }

  .field-group {
    background: var(--color-bg);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .field-group__legend {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-label);
  }

  .signature-group__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .signature-tabs {
    display: flex;
    gap: 2px;
    background: var(--color-card);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-pill);
    padding: 2px;
  }
  .signature-tab {
    font-family: var(--font-family);
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    border: none;
    border-radius: var(--radius-pill);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
    transition: background-color 0.15s var(--ease-standard), color 0.15s var(--ease-standard);
  }
  .signature-tab--active { background: var(--color-teal); color: var(--color-on-accent); }

  .signature-canvas-wrap { position: relative; }
  .signature-box {
    border: 1.5px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-card);
    touch-action: none;
    width: 100%;
    height: 160px;
    display: block;
    transition: border-color 0.15s var(--ease-standard), background-color 0.15s var(--ease-standard);
  }
  .signature-box--ready { border-color: var(--color-teal); background: var(--color-info-bg); }
  .signature-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 0 var(--space-5);
    font-size: 13px;
    font-weight: 500;
    color: var(--color-text-muted);
    pointer-events: none;
  }
  .signature-placeholder--hidden { display: none; }
  .signature-file-input { display: none; }

  /* Barra flotante en la esquina del recuadro de firma — así Deshacer/Borrar
     quedan junto al trazo que afectan, en vez de perdidos como texto plano
     debajo del canvas donde no queda claro a qué aplican. */
  .signature-toolbar {
    position: absolute;
    top: var(--space-2);
    right: var(--space-2);
    z-index: 2;
    display: flex;
    gap: var(--space-1);
  }
  .signature-icon-btn {
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border-radius: 50%;
    border: 1.5px solid var(--color-border);
    background: rgba(255, 255, 255, 0.92);
    color: var(--color-teal);
    cursor: pointer;
    transition: background-color 0.15s var(--ease-standard), border-color 0.15s var(--ease-standard),
      opacity 0.15s var(--ease-standard);
  }
  .signature-icon-btn svg { width: 15px; height: 15px; }
  .signature-icon-btn:hover:not(:disabled) { background: var(--color-info-bg); border-color: var(--color-teal); }
  .signature-icon-btn:disabled { opacity: 0.4; cursor: default; }

  .signature-processing-overlay {
    position: absolute;
    inset: 0;
    z-index: 3;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    text-align: center;
    padding: 0 var(--space-5);
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.82);
    backdrop-filter: blur(1px);
  }
  .signature-processing-overlay--hidden { display: none; }
  .signature-processing-overlay__text {
    font-size: 12px;
    font-weight: 600;
    color: var(--color-teal);
  }
  .signature-box--processing { pointer-events: none; }
  .signature-tab:disabled { opacity: 0.5; cursor: default; }

  .signature-actions {
    display: flex;
    justify-content: center;
    margin-top: var(--space-2);
  }
  .signature-status-text {
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-muted);
    transition: color 0.15s var(--ease-standard);
  }
  .signature-status-text--ready { color: var(--color-teal); font-weight: 700; }
  .signature-status-text--error { color: var(--color-error); font-weight: 700; }
  .signature-note {
    font-size: 12px;
    font-weight: 500;
    color: var(--color-text-faint);
    margin: var(--space-2) 0 0;
  }

  .btn {
    font-family: var(--font-family);
    font-size: 14px;
    font-weight: 600;
    padding: 14px 20px;
    border-radius: var(--radius-md);
    border: none;
    cursor: pointer;
    transition: background-color 0.15s var(--ease-standard), border-color 0.15s var(--ease-standard);
  }
  .btn--primary {
    background: var(--color-teal);
    color: var(--color-on-accent);
    width: 100%;
  }
  .btn--primary:hover { background: var(--color-teal-hover); }
  .btn--primary:disabled { background: var(--color-text-faint); cursor: default; }
  .btn--outline {
    background: transparent;
    color: var(--color-teal);
    border: 1.5px solid var(--color-teal);
    padding: 6px 14px;
  }
  .btn--outline:hover { background: var(--color-info-bg); }
  .btn--link {
    background: none;
    border: none;
    color: var(--color-teal);
    font-weight: 600;
    padding: 0;
    text-decoration: none;
    display: inline-block;
  }
  .btn--link:hover { color: var(--color-teal-hover); }

  #form-status {
    font-size: 13px;
    font-weight: 600;
    text-align: center;
    margin-top: var(--space-2);
    color: var(--color-text-muted);
  }
  .form-status--error {
    color: var(--color-error);
    background: var(--color-error-bg);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
  }
  .status-loading {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .spinner {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid var(--color-border);
    border-top-color: var(--color-teal);
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  .spinner--lg {
    width: 28px;
    height: 28px;
    border-width: 3px;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>"""
