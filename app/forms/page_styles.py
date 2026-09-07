"""CSS del formulario de Autorización de Corretaje — separado de page.py por tamaño.

`FORM_STYLE` se arma concatenando este CSS base (tokens, layout, tarjetas,
botones) con los fragmentos de `page_styles_fields.py` (secciones/campos) y
`page_styles_signature.py` (recuadro de firma) — mismo patrón que
`page_script.py` con los fragmentos de JS: un único `<style>` en el HTML
final, la separación es solo de archivos fuente por el límite de 500 líneas.
"""
from __future__ import annotations

from app.forms.page_styles_fields import FIELD_STYLE
from app.forms.page_styles_signature import SIGNATURE_STYLE

_CORE_STYLE = """  :root {
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

"""

_BUTTON_STYLE = """  .btn {
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
"""

FORM_STYLE = "<style>\n" + _CORE_STYLE + FIELD_STYLE + SIGNATURE_STYLE + _BUTTON_STYLE + "</style>"
