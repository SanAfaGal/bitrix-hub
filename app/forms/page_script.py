"""JS del formulario de Autorización de Corretaje — separado de page.py por tamaño.

Contiene `__CLEAN_SIGNATURE_PATH__`, reemplazado por `render_form_html()` en
`page.py` (mismo mecanismo de placeholders que el resto de la plantilla).
"""
from __future__ import annotations

FORM_SCRIPT = """<script type="module">
import { env, AutoModel, AutoProcessor, RawImage } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/+esm';

(function () {
  var canvas = document.getElementById('signature-canvas');
  var ctx = canvas.getContext('2d');
  var drawing = false;
  var hasSignature = false;
  var mode = 'draw';

  // Quitar el fondo de una foto de firma corre en el celular del cliente,
  // no en el servidor: RMBG-1.4 vía Transformers.js/WASM — el mismo modelo
  // y la misma configuración de preprocesamiento que usa
  // https://github.com/addyosmani/bg-remove (https://bg.addy.ie/) en su
  // camino "cross-browser". Se precarga apenas se abre la página — para
  // cuando la persona termine de leer el documento y llenar sus datos, el
  // modelo ya debería estar listo, sin que la firma sea el momento en que
  // note la espera.
  // Si por lo que sea el modelo no carga o falla (celular muy viejo, sin
  // datos suficientes, error de red), se cae automáticamente al respaldo
  // en el servidor (OpenCV, ver /limpiar-firma) — nunca se queda sin poder
  // limpiar la firma.
  var BACKGROUND_MODEL_ID = 'briaai/RMBG-1.4';
  var backgroundModel = { model: null, processor: null, ready: false };

  var backgroundModelPromise = (function preloadBackgroundModel() {
    env.allowLocalModels = false;
    if (env.backends && env.backends.onnx && env.backends.onnx.wasm) {
      env.backends.onnx.wasm.proxy = true;
    }
    return Promise.all([
      AutoModel.from_pretrained(BACKGROUND_MODEL_ID, { dtype: 'q8' }),
      AutoProcessor.from_pretrained(BACKGROUND_MODEL_ID, {
        revision: 'main',
        config: {
          do_normalize: true,
          do_pad: true,
          do_rescale: true,
          do_resize: true,
          image_mean: [0.5, 0.5, 0.5],
          feature_extractor_type: 'ImageFeatureExtractor',
          image_std: [0.5, 0.5, 0.5],
          resample: 2,
          rescale_factor: 0.00392156862745098,
          size: { width: 1024, height: 1024 }
        }
      })
    ]).then(function (results) {
      backgroundModel.model = results[0];
      backgroundModel.processor = results[1];
      backgroundModel.ready = true;
    }).catch(function (err) {
      console.warn('No se pudo precargar el modelo de firma en el navegador, se usará el servidor:', err);
    });
  })();

  // Corre MODNet sobre la foto y devuelve un canvas con fondo transparente
  // y la tinta en negro — mismo criterio que el trazo dibujado a mano.
  function removeBackgroundInBrowser(file) {
    return backgroundModelPromise.then(function () {
      if (!backgroundModel.ready) throw new Error('Modelo no disponible en el navegador.');
      return RawImage.fromURL(URL.createObjectURL(file));
    }).then(function (img) {
      return backgroundModel.processor(img).then(function (processed) {
        return backgroundModel.model({ input: processed.pixel_values });
      }).then(function (result) {
        return RawImage.fromTensor(result.output[0].mul(255).to('uint8')).resize(img.width, img.height);
      }).then(function (maskImage) {
        var maskData = maskImage.data;
        var outCanvas = document.createElement('canvas');
        outCanvas.width = img.width;
        outCanvas.height = img.height;
        var outCtx = outCanvas.getContext('2d');
        var pixelData = outCtx.createImageData(img.width, img.height);
        for (var i = 0; i < maskData.length; i++) {
          pixelData.data[i * 4] = 0;
          pixelData.data[i * 4 + 1] = 0;
          pixelData.data[i * 4 + 2] = 0;
          pixelData.data[i * 4 + 3] = maskData[i];
        }
        outCtx.putImageData(pixelData, 0, 0);
        return outCanvas;
      });
    });
  }

  // Respaldo si el navegador no pudo correr el modelo: la foto cruda se
  // manda al servidor, que la limpia con OpenCV (ver app/forms/signature_cleaner.py).
  function removeBackgroundOnServer(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        fetch('__CLEAN_SIGNATURE_PATH__', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_png: reader.result })
        }).then(function (resp) {
          if (!resp.ok) throw new Error('No se pudo limpiar la foto de la firma.');
          return resp.json();
        }).then(function (json) {
          var cleaned = new Image();
          cleaned.onload = function () { resolve(cleaned); };
          cleaned.onerror = function () { reject(new Error('No se pudo cargar la imagen limpia.')); };
          cleaned.src = json.cleaned_png;
        }).catch(reject);
      };
      reader.onerror = function () { reject(new Error('No se pudo leer el archivo.')); };
      reader.readAsDataURL(file);
    });
  }

  function removeSignaturePhotoBackground(file) {
    return removeBackgroundInBrowser(file).catch(function (err) {
      console.warn('Limpieza en el navegador falló, uso el respaldo del servidor:', err);
      return removeBackgroundOnServer(file);
    });
  }

  // Umbral compartido: un pixel se considera "tinta" si no es casi blanco.
  // Se usa para recortar el trazo/la foto al final.
  var NEAR_WHITE_LUMINANCE = 235;

  var tabDraw = document.getElementById('tab-draw');
  var tabUpload = document.getElementById('tab-upload');
  var placeholder = document.getElementById('signature-placeholder');
  var fileInput = document.getElementById('signature-file');
  var statusText = document.getElementById('signature-status-text');
  var undoButton = document.getElementById('undo-signature');

  // Un snapshot del canvas por cada trazo, tomado justo antes de que
  // empiece — "Deshacer" restaura el último y lo saca de la pila.
  var strokeHistory = [];

  function resizeCanvas() {
    var ratio = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#000000';
  }
  resizeCanvas();

  // Centraliza el estado visual de la firma: qué pestaña está activa, si se
  // ve el placeholder de "subir foto", y si el recuadro ya tiene una firma
  // lista (borde/texto en teal) — se llama cada vez que algo cambia.
  function refreshSignatureUI() {
    tabDraw.classList.toggle('signature-tab--active', mode === 'draw');
    tabUpload.classList.toggle('signature-tab--active', mode === 'upload');
    canvas.style.touchAction = mode === 'draw' ? 'none' : 'auto';
    canvas.classList.toggle('signature-box--ready', hasSignature);
    placeholder.classList.toggle('signature-placeholder--hidden', hasSignature || mode !== 'upload');

    if (hasSignature) {
      statusText.textContent = '✓ Firma lista';
    } else {
      statusText.textContent = mode === 'draw' ? 'Firma aquí con el dedo' : 'Elegí una foto de tu firma';
    }
    statusText.classList.toggle('signature-status-text--ready', hasSignature);
  }

  function setMode(newMode) {
    mode = newMode;
    refreshSignatureUI();
  }

  tabDraw.addEventListener('click', function () { setMode('draw'); });
  tabUpload.addEventListener('click', function () {
    setMode('upload');
    fileInput.click();
  });

  function pointerPosition(evt) {
    var rect = canvas.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  }

  canvas.addEventListener('pointerdown', function (evt) {
    if (mode !== 'draw') return;
    strokeHistory.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
    drawing = true;
    hasSignature = true;
    refreshSignatureUI();
    var p = pointerPosition(evt);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    evt.preventDefault();
  });
  canvas.addEventListener('pointermove', function (evt) {
    if (!drawing) return;
    var p = pointerPosition(evt);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    evt.preventDefault();
  });
  window.addEventListener('pointerup', function () { drawing = false; });

  canvas.addEventListener('click', function () {
    if (mode === 'upload') fileInput.click();
  });

  // Un pixel cuenta como "tinta" si no es transparente y no es casi blanco
  // (descarta el papel/fondo de una foto subida). Único criterio, reusado
  // tanto para saber si queda algo dibujado como para recortar al final.
  function isInkPixel(pixels, offset) {
    var luminance = (pixels[offset] + pixels[offset + 1] + pixels[offset + 2]) / 3;
    return pixels[offset + 3] > 10 && luminance < NEAR_WHITE_LUMINANCE;
  }

  function canvasHasInk() {
    var pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (var i = 0; i < pixels.length; i += 4) {
      if (isInkPixel(pixels, i)) return true;
    }
    return false;
  }

  undoButton.addEventListener('click', function () {
    if (strokeHistory.length === 0) return;
    var previous = strokeHistory.pop();
    ctx.putImageData(previous, 0, 0);
    hasSignature = canvasHasInk();
    refreshSignatureUI();
  });

  document.getElementById('clear-signature').addEventListener('click', function () {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    strokeHistory = [];
    hasSignature = false;
    fileInput.value = '';
    refreshSignatureUI();
  });

  var form = document.getElementById('authorization-form');
  var status = document.getElementById('form-status');
  var submitButton = document.getElementById('submit-button');

  // Spinner + frases que van rotando mientras se espera al backend, para
  // que la espera no se sienta larga aunque tarde unos segundos. Devuelve
  // una función para pararla al terminar (éxito o error).
  function startStatusAnimation(messages) {
    var i = 0;
    status.innerHTML = '<span class="status-loading">'
      + '<span class="spinner"></span>'
      + '<span class="status-loading__text">' + messages[0] + '</span>'
      + '</span>';
    var textEl = status.querySelector('.status-loading__text');
    var timer = setInterval(function () {
      i = (i + 1) % messages.length;
      textEl.textContent = messages[i];
    }, 1800);
    return function stop() { clearInterval(timer); };
  }

  function drawImageFitted(image) {
    var rect = canvas.getBoundingClientRect();
    var scale = Math.min(rect.width / image.width, rect.height / image.height);
    var w = image.width * scale;
    var h = image.height * scale;
    var x = (rect.width - w) / 2;
    var y = (rect.height - h) / 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, x, y, w, h);
    // Una foto cargada es un reinicio, no un trazo — "Deshacer" solo aplica
    // a los trazos dibujados después de esto.
    strokeHistory = [];
  }

  // Quita el fondo de la foto (en el navegador si se pudo, si no en el
  // servidor) y dibuja el resultado en el mismo canvas — la persona ve al
  // instante qué se pudo extraer, igual que si hubiera firmado con el dedo.
  fileInput.addEventListener('change', function (evt) {
    var file = evt.target.files[0];
    if (!file) return;
    var stopAnimation = startStatusAnimation([
      'Limpiando la firma...',
      'Separando la tinta del fondo...',
      'Analizando la foto...',
      'Descartando sombras y reflejos...',
      'Afinando los bordes del trazo...',
      'Preparando la firma para el documento...',
      'Esto puede tardar unos segundos...',
      'Ya casi...'
    ]);
    removeSignaturePhotoBackground(file).then(function (result) {
      drawImageFitted(result);
      hasSignature = true;
      refreshSignatureUI();
      stopAnimation();
      status.textContent = '';
    }).catch(function (err) {
      stopAnimation();
      status.textContent = 'Ocurrió un error: ' + err.message;
    });
  });

  // Recorta el canvas al recuadro real de la tinta para que la firma quede
  // centrada y a tamaño completo en el PDF, sin importar en qué esquina la
  // hayan dibujado ni cuánto margen blanco traiga una foto subida.
  function trimSignature(sourceCanvas) {
    var w = sourceCanvas.width;
    var h = sourceCanvas.height;
    var pixels = sourceCanvas.getContext('2d').getImageData(0, 0, w, h).data;
    var minX = w, minY = h, maxX = 0, maxY = 0, found = false;

    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var i = (y * w + x) * 4;
        if (isInkPixel(pixels, i)) {
          found = true;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (!found) return sourceCanvas;

    var padding = 6;
    minX = Math.max(0, minX - padding);
    minY = Math.max(0, minY - padding);
    maxX = Math.min(w - 1, maxX + padding);
    maxY = Math.min(h - 1, maxY + padding);

    var trimmed = document.createElement('canvas');
    trimmed.width = maxX - minX + 1;
    trimmed.height = maxY - minY + 1;
    trimmed.getContext('2d').drawImage(
      sourceCanvas, minX, minY, trimmed.width, trimmed.height, 0, 0, trimmed.width, trimmed.height
    );
    return trimmed;
  }

  form.addEventListener('submit', function (evt) {
    evt.preventDefault();
    if (!hasSignature) {
      status.textContent = 'Falta la firma.';
      return;
    }
    var data = {};
    new FormData(form).forEach(function (value, key) { data[key] = value; });
    data.signer_id_number = data.id_number;
    data.signature_png = trimSignature(canvas).toDataURL('image/png');

    submitButton.disabled = true;
    var stopAnimation = startStatusAnimation([
      'Generando el documento...',
      'Armando el PDF...',
      'Colocando la firma en el documento...',
      'Verificando los datos...',
      'Ya casi...'
    ]);

    fetch(window.location.pathname, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(function (resp) {
      if (!resp.ok) throw new Error('Error al generar el documento.');
      return resp.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'Autorización de Corretaje - Firmada.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      stopAnimation();
      status.textContent = 'Documento firmado y descargado. Gracias.';
    }).catch(function (err) {
      stopAnimation();
      status.textContent = 'Ocurrió un error: ' + err.message;
      submitButton.disabled = false;
    });
  });
})();
</script>"""
