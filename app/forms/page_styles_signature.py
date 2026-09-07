"""CSS del recuadro de firma (pestañas, canvas, overlay de procesamiento) — separado de page_styles.py por tamaño."""
from __future__ import annotations

SIGNATURE_STYLE = """  .signature-group__header {
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

"""
