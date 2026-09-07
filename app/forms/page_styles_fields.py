"""CSS de secciones, campos e inputs del formulario — separado de page_styles.py por tamaño."""
from __future__ import annotations

FIELD_STYLE = """  .form-section__title {
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
  .field__hint--regular {
    font-weight: 400;
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
  .field__input[readonly] {
    background: var(--color-bg);
    color: var(--color-text-muted);
    cursor: not-allowed;
  }
  .field__confirm {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--color-success);
  }
  .field__confirm--hidden {
    display: none;
  }
  /* Lápiz para "Corregir" superpuesto dentro del campo (mismo contenedor
     .field__input-wrap que el desplegable de ubicación) — el input readonly
     ya deja espacio a la derecha (padding-right) para que no quede debajo. */
  .field__correct-btn {
    position: absolute;
    top: 50%;
    right: 8px;
    transform: translateY(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .field__correct-btn:hover { background: var(--color-bg); color: var(--color-teal); }
  .field__correct-btn svg { width: 16px; height: 16px; }
  .field__correct-btn--hidden { display: none; }
  .field__input--correctable { padding-right: 36px; }

  /* Desplegable de sugerencias de ubicación — propio en vez de <datalist>
     nativo, para poder fijar la tipografía de marca y limitar cuántas filas
     se ven sin scroll (máx. 5, altura fija por fila). */
  .field__input-wrap { position: relative; }
  .location-suggest {
    position: absolute;
    top: calc(100% + var(--space-1));
    left: 0;
    right: 0;
    z-index: 10;
    margin: 0;
    padding: var(--space-1) 0;
    list-style: none;
    background: var(--color-card);
    border: 1.5px solid var(--color-border);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-card);
    max-height: calc(5 * 38px);
    overflow-y: auto;
  }
  .location-suggest[hidden] { display: none; }
  .location-suggest__item {
    font-family: var(--font-family);
    font-size: 15px;
    font-weight: 500;
    padding: 9px 12px;
    color: var(--color-navy);
    cursor: pointer;
  }
  .location-suggest__item:hover,
  .location-suggest__item--active {
    background: var(--color-info-bg);
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

"""
