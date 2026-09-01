"""CSS del panel admin — tokens y componentes de ui-style-guide.md, solo lo que este panel usa."""
from __future__ import annotations

ADMIN_STYLE = """<style>
  :root {
    color-scheme: light;

    --color-navy: #044c7c;
    --color-teal: #0c688e;
    --color-teal-hover: #0a5578;
    --color-error: #b3453a;
    --color-error-bg: #fbeceb;
    --color-info-bg: #e8f1f5;
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

  a { color: var(--color-teal); }
  a:hover { color: var(--color-teal-hover); }

  /* ── Login (página centrada, sin app-shell) ─────────────────────────── */

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
    max-width: 400px;
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
  .brand__logo { height: 44px; width: auto; }
  .brand__identity { display: flex; flex-direction: column; align-items: center; }
  .brand__name {
    font-size: 18px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-navy);
  }
  .brand__tagline { font-size: 12px; font-weight: 500; color: var(--color-teal); }

  .card {
    background: var(--color-card);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-card);
    padding: var(--space-7) var(--space-6);
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .card__header { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--space-2); }
  .card__title { font-size: 18px; font-weight: 700; margin: 0; color: var(--color-navy); }
  .card__subtitle { font-size: 13px; font-weight: 500; margin: 0; color: var(--color-text-muted); }

  .field { display: flex; flex-direction: column; gap: 6px; }
  .field__label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-label);
  }
  .field__input {
    font-family: var(--font-family);
    font-size: 14px;
    padding: var(--space-3);
    border: 1.5px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-card);
    color: var(--color-navy);
    transition: border-color 0.15s var(--ease-standard);
  }
  .field__input:focus { outline: none; border-color: var(--color-teal); }

  .btn {
    font-family: var(--font-family);
    font-size: 14px;
    font-weight: 600;
    padding: var(--space-3) var(--space-5);
    border-radius: var(--radius-md);
    border: 1.5px solid transparent;
    cursor: pointer;
    transition: background-color 0.15s var(--ease-standard), border-color 0.15s var(--ease-standard);
  }
  .btn--primary { background: var(--color-teal); color: var(--color-on-accent); }
  .btn--primary:hover { background: var(--color-teal-hover); }
  .btn--outline { background: transparent; border-color: var(--color-teal); color: var(--color-teal); }
  .btn--outline:hover { background: var(--color-info-bg); }
  .btn--link { background: none; border: none; color: var(--color-teal); padding: 0; font-size: 13px; cursor: pointer; }
  .btn-row { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; }

  .alert {
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 500;
  }
  .alert--error { background: var(--color-error-bg); color: var(--color-error); }
  .alert--info { background: var(--color-info-bg); color: var(--color-navy); }

  /* ── App shell (plantillas / configuración) ─────────────────────────── */

  .page-outer {
    height: 100vh;
    display: flex;
    justify-content: center;
    padding: 24px;
  }

  .app {
    width: 100%;
    max-width: 1560px;
    display: flex;
    flex-direction: column;
    background: var(--color-card);
    border-radius: var(--radius-xl);
    border: 1px solid #e7e9ee;
    box-shadow: var(--shadow-card);
    overflow: hidden;
  }

  .topbar {
    height: 68px;
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-5) var(--space-6);
    padding: var(--space-3) 32px;
    background: var(--color-card);
    border-bottom: 1px solid #e7e9ee;
  }
  .topbar__brand { display: flex; align-items: center; gap: var(--space-3); flex: 0 0 auto; }
  .topbar__mark { height: 36px; width: auto; flex: 0 0 auto; }
  .topbar__identity { display: flex; flex-direction: column; line-height: 1.15; }
  .topbar__name { font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-navy); }
  .topbar__tagline { font-size: 11px; font-weight: 500; color: var(--color-teal); }
  .topbar__divider { width: 1px; height: 28px; background: #e7e9ee; flex: 0 0 auto; }

  .topbar__nav { display: flex; align-items: center; gap: var(--space-2); flex: 0 0 auto; }
  .navpill {
    font-family: var(--font-family);
    font-size: 13px;
    font-weight: 600;
    padding: 7px 18px;
    border-radius: var(--radius-pill);
    border: 1.5px solid var(--color-teal);
    color: var(--color-teal);
    background: transparent;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    transition: background-color 0.15s var(--ease-standard), color 0.15s var(--ease-standard);
  }
  .navpill__icon { flex: 0 0 auto; margin-right: 6px; }
  .navpill--active { background: var(--color-teal); color: var(--color-on-accent); }
  .navpill__dot {
    width: 0; height: 6px; margin-left: 0; border-radius: 50%; background: currentColor; opacity: 0;
    transition: width 0.15s var(--ease-standard), margin-left 0.15s var(--ease-standard), opacity 0.15s var(--ease-standard);
  }
  .navpill__dot--visible { width: 6px; margin-left: 7px; opacity: 1; }

  .topbar__user { margin-left: auto; display: flex; align-items: center; gap: var(--space-5); }
  .avatar {
    width: 26px; height: 26px; border-radius: 50%; background: var(--color-info-bg); color: var(--color-teal);
    display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex: 0 0 auto;
  }
  .userchip { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--color-navy); }
  .logout-btn {
    display: flex; align-items: center; gap: 6px; background: none; border: none;
    color: var(--color-text-muted); font-family: var(--font-family); font-size: 13px; font-weight: 600;
    cursor: pointer; padding: 6px 4px;
  }
  .logout-btn:hover { color: var(--color-navy); }

  .body { flex: 1 1 auto; display: flex; min-height: 0; background: var(--color-bg); }

  .sidebar {
    width: 312px; flex: 0 0 auto; background: var(--color-card); border-right: 1px solid #e7e9ee;
    padding: var(--space-6) var(--space-4); overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-6);
  }
  .sidebar::-webkit-scrollbar { width: 8px; }
  .sidebar::-webkit-scrollbar-thumb { background: #d7dde3; border-radius: 8px; }
  .sidebar__intro-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--color-label); padding: 0 6px 8px; }
  .sidebar__intro-text { font-size: 12px; color: var(--color-text-muted); padding: 0 6px 4px; line-height: 1.45; }
  .sidebar__section { display: flex; flex-direction: column; gap: var(--space-2); }
  .sidebar__section-title { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--color-text-faint); padding: 0 6px 2px; }

  .sidebar__item {
    display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
    padding: var(--space-3) 14px; border-radius: var(--radius-md); text-decoration: none;
    background: var(--color-card); border: 1px solid #e7e9ee; box-shadow: 0 1px 2px rgba(4, 76, 124, 0.04);
    transition: background-color 0.15s var(--ease-standard), border-color 0.15s var(--ease-standard), transform 0.15s var(--ease-standard);
  }
  .sidebar__item:hover { background: var(--color-info-bg); border-color: #bcdae4; transform: translateX(2px); }
  .sidebar__item--active { background: var(--color-info-bg); border-color: var(--color-teal); box-shadow: none; }
  .sidebar__item--active:hover { transform: none; }
  .sidebar__item-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .sidebar__item-label { font-size: 13px; font-weight: 600; line-height: 1.3; color: var(--color-navy); }
  .sidebar__item-hint { font-size: 11px; color: var(--color-text-faint); line-height: 1.3; }
  .sidebar__item-end { flex: 0 0 auto; display: flex; align-items: center; gap: 6px; }
  .sidebar__item-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--color-teal); opacity: 0; }
  .sidebar__item-dot--visible { opacity: 1; }
  .sidebar__item-chevron { color: var(--color-text-faint); flex: 0 0 auto; transition: transform 0.15s var(--ease-standard), color 0.15s var(--ease-standard); }
  .sidebar__item:hover .sidebar__item-chevron { color: var(--color-teal); transform: translateX(2px); }
  .sidebar__item--active .sidebar__item-chevron { color: var(--color-teal); }

  .content { flex: 1 1 auto; padding: var(--space-7) 40px; display: flex; flex-direction: column; gap: var(--space-5); min-width: 0; overflow-y: auto; }
  .content--config { padding: var(--space-7) 48px; }

  .content__title-row { display: flex; align-items: baseline; gap: 10px; }
  .content__title { margin: 0; font-size: 24px; font-weight: 700; color: var(--color-navy); }
  .content__desc { margin: 0; font-size: 14px; color: var(--color-text-muted); max-width: 680px; line-height: 1.5; }

  .badge-unsaved {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--color-teal); background: var(--color-info-bg); padding: 3px 10px; border-radius: var(--radius-pill);
    visibility: hidden;
  }
  .badge-unsaved--visible { visibility: visible; }

  .editor-grid { display: flex; gap: var(--space-6); align-items: flex-start; }
  .editor-col { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: var(--space-3); }
  .side-col { width: 340px; flex: 0 0 auto; display: flex; flex-direction: column; gap: var(--space-3); }
  .content--config .editor-col { flex: 1 1 0; }
  .content--config .side-col { width: 320px; gap: var(--space-4); }

  .var-row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .var-row__label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-label); }
  .var-chip {
    font-family: var(--font-family); font-size: 12px; font-weight: 600; color: var(--color-teal);
    background: var(--color-info-bg); border: none; border-radius: var(--radius-pill); padding: 4px 12px; cursor: pointer;
  }
  .var-chip:hover { background: #dcecf1; }

  .editor-wrap { position: relative; }
  .editor-textarea {
    width: 100%; resize: vertical; font-family: var(--font-family); font-size: 14.5px; line-height: 1.55;
    color: var(--color-navy); padding: 16px; border: 1.5px solid var(--color-border); border-radius: var(--radius-md);
    background: var(--color-card); outline: none;
  }
  .editor-textarea:focus { border-color: var(--color-teal); }
  .char-count {
    position: absolute; right: 14px; bottom: 10px; font-size: 11px; color: var(--color-text-faint);
    background: rgba(255,255,255,0.9); padding: 1px 6px; border-radius: 6px; pointer-events: none;
  }

  /* Config: el prompt suele ser largo — que crezca el textarea a lo alto
     disponible en vez de quedar chico con doble scroll (el de `.content` y
     el del propio textarea). Un solo scroll, el del textarea. Solo en
     pantallas anchas: en mobile el editor-grid se apila en columna y este
     modo (contenedor sin scroll propio) recortaría la guía lateral. */
  @media (min-width: 901px) {
    .content--config { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
    .content--config .editor-grid { flex: 1 1 auto; min-height: 0; }
    .content--config .editor-col { min-height: 0; align-self: stretch; }
    /* El <form> que envuelve el textarea es hijo directo de .editor-col pero
       no tenía flex-grow — sin esto, .editor-col se estira pero el form
       adentro se queda con su alto de contenido y el hueco vacío reaparece. */
    .content--config .editor-col form { flex: 1 1 auto; min-height: 0; }
    .content--config .editor-wrap { flex: 1 1 auto; min-height: 0; display: flex; }
    .content--config .editor-textarea { flex: 1 1 auto; height: 100%; resize: none; }
    /* La columna lateral se queda en su alto natural, arriba — no se estira
       a fuerza a que coincida con el fin del textarea (que crece según el
       largo del prompt, no tiene por qué emparejar con estas tarjetas). */
    .content--config .side-col { overflow-y: auto; max-height: 100%; }
  }

  .save-meta { margin-left: 4px; font-size: 12.5px; color: var(--color-text-faint); }

  .preview-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-label); margin-bottom: 8px; }
  .chat-frame {
    background: #e7e0d6; border-radius: var(--radius-lg); padding: 18px 14px; min-height: 220px;
    display: flex; flex-direction: column; justify-content: flex-end; box-shadow: var(--shadow-card);
  }
  .chat-bubble {
    align-self: flex-end; max-width: 88%; background: #d9fdd3; border-radius: 12px 12px 2px 12px;
    padding: 9px 11px 7px; box-shadow: 0 1px 1px rgba(0,0,0,0.08);
  }
  .chat-bubble__text { font-size: 13.5px; line-height: 1.45; color: #111b21; white-space: pre-line; }
  .chat-bubble__meta { display: flex; justify-content: flex-end; align-items: center; gap: 3px; margin-top: 3px; }
  .chat-bubble__time { font-size: 10.5px; color: #667781; }

  .info-card {
    background: var(--color-card); border: 1px solid #e7e9ee; border-radius: var(--radius-lg);
    padding: 14px 16px; display: flex; flex-direction: column; gap: 6px;
  }
  .info-card__label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-label); }
  .info-card__text { margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--color-text-muted); }

  .guide-card { background: var(--color-info-bg); border-radius: var(--radius-lg); padding: 18px; display: flex; flex-direction: column; gap: var(--space-3); }
  .guide-card__title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: var(--color-navy); }
  .guide-card__tip { display: flex; gap: 8px; align-items: flex-start; }
  .guide-card__tip-dot { flex: 0 0 auto; width: 5px; height: 5px; border-radius: 50%; background: var(--color-teal); margin-top: 7px; }
  .guide-card__tip-text { margin: 0; font-size: 12.5px; line-height: 1.5; color: var(--color-navy); }

  /* ── Responsive ──────────────────────────────────────────────────────── */

  @media (max-width: 1180px) {
    .editor-grid { flex-direction: column; }
    .side-col, .content--config .side-col { width: 100%; }
    .chat-frame { min-height: 160px; }
  }

  @media (max-width: 900px) {
    .page-outer { padding: 0; }
    .app { border-radius: 0; border: none; box-shadow: none; min-height: 100vh; }
    .body { flex-direction: column; }
    .sidebar {
      width: 100%; max-height: 320px; border-right: none; border-bottom: 1px solid #e7e9ee;
      padding: var(--space-4);
    }
    .content, .content--config { padding: var(--space-6) var(--space-5); }
  }

  /* ── Prospectos (layout tipo WhatsApp Web: lista + hilo) ────────────── */

  .prospects-layout { flex: 1 1 auto; display: flex; min-width: 0; min-height: 0; }

  .prospect-list-pane {
    width: 340px; flex: 0 0 auto; min-height: 0; background: var(--color-card); border-right: 1px solid #e7e9ee;
    overflow-y: auto; display: flex; flex-direction: column;
  }
  .prospect-list-pane::-webkit-scrollbar { width: 8px; }
  .prospect-list-pane::-webkit-scrollbar-thumb { background: #d7dde3; border-radius: 8px; }

  .prospect-row {
    display: flex; align-items: flex-start; gap: 12px; padding: 13px var(--space-5);
    border-bottom: 1px solid #eef0f3; text-decoration: none; color: inherit; position: relative;
    transition: background-color 0.15s var(--ease-standard);
  }
  .prospect-row:hover { background: #f7f9fb; }
  .prospect-row--active { background: var(--color-info-bg); }
  .prospect-row--active::before {
    content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--color-teal);
  }

  .prospect-row__avatar {
    flex: 0 0 auto; width: 42px; height: 42px; border-radius: 50%;
    background: linear-gradient(135deg, var(--color-teal), var(--color-navy));
    color: var(--color-on-accent); display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 700; letter-spacing: 0.02em;
  }
  .prospect-row__avatar--muted { background: linear-gradient(135deg, #b9c2c9, #8b96a0); }

  .prospect-row__body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .prospect-row__top { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }
  .prospect-row__name { font-size: 14px; font-weight: 700; color: var(--color-navy); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .prospect-row__name--muted { color: var(--color-text-faint); font-weight: 600; font-style: italic; }
  .prospect-row__time { flex: 0 0 auto; font-size: 11px; color: var(--color-text-faint); }
  .prospect-row__bottom { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
  .prospect-row__preview { min-width: 0; font-size: 12.5px; color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .prospect-row__phone { font-size: 11px; color: var(--color-text-faint); }

  .prospect-badge {
    flex: 0 0 auto; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    padding: 2px 9px; border-radius: var(--radius-pill); white-space: nowrap;
  }
  .prospect-badge--deal { background: #dcecf1; color: var(--color-teal); }
  .prospect-badge--nodeal { background: #f1f1f6; color: var(--color-text-faint); }

  .prospect-empty { padding: var(--space-7); text-align: center; color: var(--color-text-muted); font-size: 14px; }

  .prospect-thread-pane { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: var(--color-bg); }
  .prospect-thread-pane--empty { align-items: center; justify-content: center; }

  .prospect-header {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 24px; background: var(--color-card); border-bottom: 1px solid #e7e9ee; flex: 0 0 auto;
  }
  .prospect-header__back {
    display: none; flex: 0 0 auto; align-items: center; justify-content: center;
    width: 32px; height: 32px; border-radius: 50%; color: var(--color-teal); text-decoration: none;
    margin-left: -6px;
  }
  .prospect-header__back:hover { background: var(--color-info-bg); }
  .prospect-header__avatar {
    flex: 0 0 auto; width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, var(--color-teal), var(--color-navy));
    color: var(--color-on-accent); display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; letter-spacing: 0.02em;
  }
  .prospect-header__avatar--muted { background: linear-gradient(135deg, #b9c2c9, #8b96a0); }
  .prospect-header__identity { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 0; }
  .prospect-header__name { margin: 0; font-size: 14px; font-weight: 700; line-height: 1.3; color: var(--color-navy); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .prospect-header__phone { font-size: 11.5px; line-height: 1.3; color: var(--color-text-muted); }

  .prospect-thread {
    flex: 1 1 auto; overflow-y: auto; padding: 24px 32px; display: flex; flex-direction: column; gap: 10px;
  }
  .prospect-bubble { max-width: 65%; border-radius: 12px; padding: 9px 11px 7px; box-shadow: 0 1px 1px rgba(0,0,0,0.08); }
  .prospect-bubble--user { align-self: flex-start; background: #ffffff; border-radius: 12px 12px 12px 2px; }
  .prospect-bubble--assistant { align-self: flex-end; background: #d9fdd3; border-radius: 12px 12px 2px 12px; }
  .prospect-bubble__text { font-size: 13.5px; line-height: 1.45; color: #111b21; white-space: pre-line; }
  .prospect-bubble__time { display: block; text-align: right; margin-top: 3px; font-size: 10.5px; color: #667781; }

  @media (max-width: 900px) {
    /* Mobile: una sola columna a la vez, como WhatsApp Web en celular — la
       lista o el hilo, nunca ambos. `prospects-layout--has-selection` (agregada
       cuando hay un chat seleccionado) decide cuál se muestra. */
    .prospects-layout { flex-direction: column; }
    .prospect-list-pane { width: 100%; height: 100%; max-height: none; border-right: none; }
    .prospect-thread-pane { display: none; }
    .prospects-layout--has-selection .prospect-list-pane { display: none; }
    .prospects-layout--has-selection .prospect-thread-pane { display: flex; width: 100%; }
    .prospect-header__back { display: inline-flex; }
    .prospect-thread { padding: 18px; }
    .prospect-header { padding: 10px 16px; }
  }

  @media (max-width: 640px) {
    .topbar { padding: var(--space-3) var(--space-4); height: auto; }
    .topbar__tagline { display: none; }
    .topbar__divider { display: none; }
    .topbar__nav { width: 100%; justify-content: flex-start; }
    .topbar__user { margin-left: 0; width: 100%; justify-content: space-between; }
    .content, .content--config { padding: var(--space-5) var(--space-4); gap: var(--space-4); }
    .content__title { font-size: 20px; }
    .btn-row { gap: var(--space-2); }
    .save-meta { width: 100%; margin-left: 0; }
  }

  /* Pills icon-only en pantallas angostas — la etiqueta sigue disponible por
     `title` (tooltip) y como texto accesible para lectores de pantalla. */
  @media (max-width: 480px) {
    .navpill { padding: 8px; }
    .navpill__icon { margin-right: 0; }
    .navpill__label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    .navpill__dot--visible { margin-left: 3px; }
  }
</style>"""
