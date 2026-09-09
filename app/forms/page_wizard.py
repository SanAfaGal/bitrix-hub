"""Markup del wizard previo al formulario completo de Autorización de Corretaje.

Separado de `page.py` por tamaño (límite de 500 líneas del repo). Tres pasos
antes de mostrar "Completa la información":

1. Autorización (sí/no) — enlace a la Ley 1581 de 2012 en el portal oficial
   de Función Pública, más un checkbox de "he leído y autorizo". Si dice que
   no, el wizard se detiene ahí.
2. Ubicación del inmueble — solo se pide el dato; la cobertura por zona
   (`app/forms/coverage.py`) es un chequeo aparte, todavía WIP y sin usar en
   este flujo.
3. Matrícula/ID — siempre, después de la ubicación (es una validación
   distinta: si el inmueble ya está publicado, no si hay cobertura de zona).
   Consulta Xposure en vivo (`/formularios/autorizacion-de-corretaje/verify-matricula`)
   — si ya está publicado, el wizard se detiene con un mensaje de bloqueo en
   vez de mostrar el resto del formulario.

Cada paso es una `<div class="card">` que `page_wizard_script.py` muestra u
oculta con la clase `card--hidden` (mismo patrón que `success-view--hidden`
en `page_script.py`).
"""
from __future__ import annotations

_WIZARD_HTML = """<div class="card" id="wizard-step-authorization">
      <div class="card__header">
        <h2 class="card__title">Antes de empezar</h2>
        <p class="card__subtitle">Confírmanos esto para continuar.</p>
      </div>
      <a class="wizard-law-link" href="https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981"
         target="_blank" rel="noopener noreferrer">
        Leer la Ley 1581 de 2012 en el portal oficial de Función Pública
        <svg class="wizard-law-link__icon" width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
          <polyline points="15 3 21 3 21 9"></polyline>
          <line x1="10" y1="14" x2="21" y2="3"></line>
        </svg>
      </a>
      <label class="wizard-checkbox" for="wizard-data-consent">
        <input type="checkbox" id="wizard-data-consent" required>
        <span class="wizard-checkbox__text">
          He leído y autorizo el tratamiento de mis datos personales por parte de Alberto Álvarez
          Servicios Integrales Inmobiliarios, conforme a la Ley 1581 de 2012 y sus decretos
          reglamentarios, para los fines del proceso de corretaje de mi inmueble.
          <span class="field__required">*</span>
        </span>
      </label>
      <span class="field__error" id="error-wizard-data-consent"></span>
      <div class="wizard-actions">
        <button type="button" class="btn btn--primary" id="wizard-authorize-yes">Sí, autorizo</button>
        <button type="button" class="btn btn--outline" id="wizard-authorize-no">No, todavía no</button>
      </div>
    </div>
    <div class="card success-view card--hidden" id="wizard-step-declined">
      <span class="success-view__icon success-view__icon--info">👋</span>
      <h2 class="success-view__title">Entendido</h2>
      <p class="success-view__text">
        Cuando quieras continuar, contáctanos y con gusto retomamos el proceso.
      </p>
      <div class="wizard-actions">
        <button type="button" class="btn btn--back" id="wizard-back-declined">
          <svg class="wizard-back-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true"><path d="M19 12H5"></path><path d="M12 19l-7-7 7-7"></path></svg>
          <span>Regresar</span>
        </button>
      </div>
    </div>
    <div class="card card--hidden" id="wizard-step-location">
      <div class="card__header">
        <h2 class="card__title">
          Ubicación del inmueble
          <span class="wizard-status-dot" id="wizard-status-location" title="Verificando disponibilidad..."></span>
        </h2>
        <p class="card__subtitle">
          Cuéntanos dónde está el inmueble: es necesario validar si tenemos cobertura en esa
          ubicación.
        </p>
      </div>
__LOCATION_FIELD_HTML__
      <input type="hidden" id="field-location_sector_code" name="location_sector_code" form="authorization-form" value="">
      <div class="wizard-actions">
        <button type="button" class="btn btn--back" id="wizard-back-location">
          <svg class="wizard-back-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true"><path d="M19 12H5"></path><path d="M12 19l-7-7 7-7"></path></svg>
          <span>Regresar</span>
        </button>
        <button type="button" class="btn btn--primary" id="wizard-location-continue">Continuar</button>
      </div>
    </div>
    <div class="card card--hidden" id="wizard-step-matricula">
      <div class="card__header">
        <h2 class="card__title">
          Matrícula del inmueble
          <span class="wizard-status-dot" id="wizard-status-matricula" title="Verificando disponibilidad..."></span>
        </h2>
        <p class="card__subtitle">
          Antes de continuar, verificamos que este inmueble no esté ya publicado en Xposure MLS.
        </p>
        <div class="wizard-info-note">
          <svg class="wizard-info-note__icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true">
            <circle cx="12" cy="12" r="9"></circle>
            <line x1="12" y1="11" x2="12" y2="16"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
          <span>
            Xposure MLS es la plataforma donde las inmobiliarias comparten su inventario de
            propiedades entre sí. Así evitamos publicar dos veces el mismo inmueble.
          </span>
        </div>
      </div>
      <div class="field" id="field-wrap-wizard-registration-number">
        <label class="field__label" for="wizard-registration-number">
          Matrícula inmobiliaria <span class="field__required">*</span>
        </label>
        <span class="field__hint">
          Número de identificación del inmueble en el registro de instrumentos públicos.
        </span>
        <input class="field__input" id="wizard-registration-number" type="text"
               placeholder="Ej: 050-123456" autocomplete="off" maxlength="13" required>
        <span class="field__error" id="error-wizard-registration-number"></span>
      </div>
      <div class="wizard-actions">
        <button type="button" class="btn btn--back" id="wizard-back-matricula">
          <svg class="wizard-back-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true"><path d="M19 12H5"></path><path d="M12 19l-7-7 7-7"></path></svg>
          <span>Regresar</span>
        </button>
        <button type="button" class="btn btn--primary" id="wizard-matricula-continue">Continuar</button>
      </div>
    </div>
    <div class="card card--hidden" id="wizard-step-confirm-match">
      <div class="card__header">
        <h2 class="card__title">¿Este es tu inmueble?</h2>
        <p class="card__subtitle">
          Encontramos este inmueble publicado en Xposure MLS con la misma matrícula que
          escribiste.
        </p>
      </div>
      <div class="wizard-info-note">
        <svg class="wizard-info-note__icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true">
          <circle cx="12" cy="12" r="9"></circle>
          <line x1="12" y1="11" x2="12" y2="16"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <span id="wizard-confirm-match-search-note"></span>
      </div>
      <a class="document-cta" id="wizard-confirm-match-link" href="#" target="_blank" rel="noopener noreferrer">
        <span class="document-cta__icon">🏠</span>
        <span class="document-cta__text">
          <strong>Ver el inmueble encontrado</strong>
          <span>Ábrelo y compara la dirección con la tuya</span>
        </span>
        <span class="document-cta__arrow">›</span>
      </a>
      <div class="wizard-actions">
        <button type="button" class="btn btn--outline" id="wizard-confirm-match-no">No, no es mi inmueble</button>
        <button type="button" class="btn btn--primary" id="wizard-confirm-match-yes">Sí, es mi inmueble</button>
      </div>
    </div>
    <div class="card success-view card--hidden" id="wizard-step-blocked">
      <span class="success-view__icon success-view__icon--error">⚠</span>
      <h2 class="success-view__title">No podemos continuar</h2>
      <p class="success-view__text" id="wizard-blocked-message"></p>
      <a class="btn btn--outline wizard-blocked-link wizard-blocked-link--hidden" id="wizard-blocked-link"
         href="#" target="_blank" rel="noopener noreferrer">Ver el inmueble publicado</a>
      <div class="wizard-actions">
        <button type="button" class="btn btn--back" id="wizard-back-blocked">
          <svg class="wizard-back-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               aria-hidden="true"><path d="M19 12H5"></path><path d="M12 19l-7-7 7-7"></path></svg>
          <span>Regresar</span>
        </button>
      </div>
    </div>"""


WIZARD_STYLE = """<style>
.wizard-question { margin: 0 0 var(--space-4); line-height: 1.5; }
.wizard-actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.wizard-actions .btn { width: auto; flex: 1; }
.card--hidden { display: none; }
.success-view__icon--error { background: var(--color-error-bg); color: var(--color-error); }
.success-view__icon--info { background: var(--color-info-bg); color: var(--color-teal); }
.wizard-blocked-link { display: inline-block; margin-top: var(--space-3); text-decoration: none; }
.wizard-blocked-link--hidden { display: none; }
.wizard-checkbox {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  cursor: pointer;
}
.wizard-checkbox input[type="checkbox"] {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  accent-color: var(--color-teal);
}
.wizard-checkbox__text {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--color-text-muted);
}
.wizard-checkbox input[type="checkbox"].field__input--invalid {
  outline: 1.5px solid var(--color-error);
  outline-offset: 2px;
}
.wizard-law-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-teal);
  text-decoration: underline;
  margin-bottom: var(--space-3);
}
.wizard-law-link__icon {
  flex-shrink: 0;
}
.wizard-actions .btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  line-height: 1;
}
.wizard-back-icon {
  display: block;
  flex-shrink: 0;
}
.wizard-info-note {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  margin-top: var(--space-2);
}
.wizard-info-note__icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--color-text-muted);
}
.wizard-info-note span {
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  color: var(--color-text-muted);
}
.btn--back {
  background: transparent;
  color: var(--color-text-muted);
  border: 1.5px solid var(--color-border);
  padding: 6px 14px;
}
.btn--back:hover {
  background: var(--color-bg);
  color: var(--color-navy);
  border-color: var(--color-text-muted);
}
.start-over-btn {
  display: block;
  margin: 0 auto var(--space-4);
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  color: var(--color-text-muted);
  font-family: var(--font-family);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.start-over-btn--hidden {
  display: none;
}
.wizard-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-border);
  margin-left: 6px;
  vertical-align: middle;
}
.wizard-status-dot--ok {
  background: #1f8a4c;
}
.wizard-status-dot--down {
  background: var(--color-error);
}
</style>"""


def render_wizard_html(location_field_html: str) -> str:
    return _WIZARD_HTML.replace("__LOCATION_FIELD_HTML__", location_field_html)
