"""Markup del wizard previo al formulario completo de Autorización de Corretaje.

Separado de `page.py` por tamaño (límite de 500 líneas del repo). Tres pasos
antes de mostrar "Completa la información":

1. Autorización (sí/no) — el texto de corretaje + tratamiento de datos
   personales (Ley 1581 de 2012) va en un textarea de solo lectura con
   scroll, más un checkbox de "he leído y autorizo" — texto genérico
   pendiente de revisión por el equipo legal, no hay política/PDF real
   todavía para linkear. Si dice que no, el wizard se detiene ahí.
2. Ubicación del inmueble — hoy la cobertura siempre "pasa"
   (`app/forms/coverage.py`, WIP), así que en la práctica este paso lleva
   directo al formulario completo.
3. Matrícula/ID (solo si el paso 2 no tuviera cobertura): consulta Xposure en
   vivo (`/formularios/autorizacion-de-corretaje/verify-matricula`) — si
   el inmueble ya está publicado, el wizard se detiene con un mensaje de
   bloqueo en vez de mostrar el resto del formulario.

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
      <textarea class="wizard-law-textarea" id="wizard-law-textarea" readonly>LEY 1581 DE 2012 — Régimen General de Protección de Datos Personales (resumen)

Objeto: regular el derecho fundamental de hábeas data, es decir, el derecho que tiene toda persona a conocer, actualizar y rectificar la información que se haya recolectado sobre ella en bases de datos.

Principios (Artículo 4): legalidad, finalidad, libertad, veracidad o calidad, transparencia, acceso y circulación restringida, seguridad y confidencialidad en el tratamiento de los datos personales.

Derechos del titular de los datos (Artículo 8):
— Conocer, actualizar y rectificar sus datos personales.
— Solicitar prueba de la autorización otorgada.
— Ser informado sobre el uso que se le ha dado a sus datos.
— Presentar quejas ante la Superintendencia de Industria y Comercio por infracciones a esta ley.
— Revocar la autorización y/o solicitar la supresión del dato, cuando no se respeten los principios, derechos y garantías constitucionales y legales.
— Acceder en forma gratuita a sus datos personales que hayan sido objeto de tratamiento.</textarea>
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
    </div>
    <div class="card card--hidden" id="wizard-step-location">
      <div class="card__header">
        <h2 class="card__title">Ubicación del inmueble</h2>
        <p class="card__subtitle">Antes de tus datos, cuéntanos dónde está.</p>
      </div>
__LOCATION_FIELD_HTML__
      <div class="wizard-actions">
        <button type="button" class="btn btn--primary" id="wizard-location-continue">Continuar</button>
      </div>
    </div>
    <div class="card card--hidden" id="wizard-step-matricula">
      <div class="card__header">
        <h2 class="card__title">Matrícula del inmueble</h2>
        <p class="card__subtitle">
          Todavía no tenemos cobertura confirmada en esa zona: valida el registro del inmueble
          para poder continuar.
        </p>
      </div>
      <div class="field" id="field-wrap-wizard-registration-number">
        <label class="field__label" for="wizard-registration-number">
          Matrícula inmobiliaria <span class="field__required">*</span>
        </label>
        <span class="field__hint">
          Número de identificación del inmueble en el registro de instrumentos públicos.
        </span>
        <input class="field__input" id="wizard-registration-number" type="text"
               placeholder="Ej: 050-123456" autocomplete="off" required>
        <span class="field__error" id="error-wizard-registration-number"></span>
      </div>
      <div class="wizard-actions">
        <button type="button" class="btn btn--primary" id="wizard-matricula-continue">Continuar</button>
      </div>
    </div>
    <div class="card success-view card--hidden" id="wizard-step-blocked">
      <span class="success-view__icon success-view__icon--error">⚠</span>
      <h2 class="success-view__title">No podemos continuar</h2>
      <p class="success-view__text" id="wizard-blocked-message"></p>
    </div>"""


WIZARD_STYLE = """<style>
.wizard-question { margin: 0 0 var(--space-4); line-height: 1.5; }
.wizard-actions { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.wizard-actions .btn { width: auto; flex: 1; }
.card--hidden { display: none; }
.success-view__icon--error { background: var(--color-error-bg); color: var(--color-error); }
.success-view__icon--info { background: var(--color-info-bg); color: var(--color-teal); }
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
.wizard-law-textarea {
  width: 100%;
  height: 140px;
  resize: none;
  overflow-y: auto;
  font-family: var(--font-family);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--color-text-muted);
  background: var(--color-bg);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-3);
}
</style>"""


def render_wizard_html(location_field_html: str) -> str:
    return _WIZARD_HTML.replace("__LOCATION_FIELD_HTML__", location_field_html)
