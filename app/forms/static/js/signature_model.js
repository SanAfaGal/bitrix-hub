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

  // Si el modelo en el navegador no termina en este tiempo (celular viejo o
  // lento), no dejamos a la persona esperando indefinidamente: se cae al
  // respaldo del servidor igual que si hubiera fallado. 20s porque la
  // inferencia de RMBG-1.4 en WASM (no solo la descarga del modelo) puede
  // tardar más de 10s en un celular real incluso con el modelo ya cargado —
  // con un umbral más corto, la mayoría de los celulares terminaba cayendo
  // al servidor sin necesidad, perdiendo el camino rápido casi siempre.
  var BROWSER_MODEL_TIMEOUT_MS = 20000;

  function withTimeout(promise, ms) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { reject(new Error('El navegador tardó demasiado.')); }, ms);
      promise.then(
        function (value) { clearTimeout(timer); resolve(value); },
        function (err) { clearTimeout(timer); reject(err); }
      );
    });
  }

  // Respaldo si el navegador no pudo correr el modelo: la foto cruda se
  // manda al servidor, que la limpia con OpenCV (ver app/forms/signature_cleaner.py).
  function removeBackgroundOnServer(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        fetch(window.BH_CONFIG.cleanSignaturePath, {
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
    return withTimeout(removeBackgroundInBrowser(file), BROWSER_MODEL_TIMEOUT_MS).catch(function (err) {
      console.warn('Limpieza en el navegador falló o tardó demasiado, uso el respaldo del servidor:', err);
      return removeBackgroundOnServer(file);
    });
  }

