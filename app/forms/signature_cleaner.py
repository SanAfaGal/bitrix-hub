"""Limpieza de fotos de firma con OpenCV: separa la tinta del fondo (papel, sombras, luz)."""
from __future__ import annotations

import cv2
import numpy as np

# Negro, igual que el trazo dibujado a mano — no el azul de marca, para que
# la firma se vea igual sin importar si se dibujó o se subió una foto.
_INK_COLOR_BGR = np.array([0x00, 0x00, 0x00], dtype=np.uint8)
_MORPH_KERNEL = np.ones((3, 3), np.uint8)

# Umbral adaptativo: ventana de vecindario para calcular el punto de corte
# local (impar, más grande que el grosor de un trazo pero chico frente a la
# hoja completa) y la constante que se le resta a la media local.
_ADAPTIVE_BLOCK_SIZE = 35
_ADAPTIVE_C = 12

# Un trazo de firma es delgado y alargado. Cualquier componente conexo que
# ocupe más de esta fracción del área total de la foto no es tinta — es una
# sombra, un borde de la hoja, o un objeto de fondo que el umbral local no
# pudo descartar del todo.
_MAX_COMPONENT_AREA_FRACTION = 0.06


def clean_signature_photo(image_bytes: bytes) -> bytes:
    """Recibe una foto (jpg/png) de una firma en papel y devuelve un PNG con fondo
    transparente y solo la tinta, en negro.

    Dos pasadas, pensadas para fotos de celular reales (luz despareja, sombra
    de la mano que sostiene el teléfono):
    1. Umbral adaptativo (no global como Otsu) — calcula el punto de corte
       por vecindario, así que una sombra que oscurece medio la hoja no hace
       que ese lado entero se confunda con tinta.
    2. Filtro por tamaño de componente conexo — descarta cualquier blob
       grande que igual se haya colado (sombra dura, borde de la hoja); un
       trazo de firma real es delgado y nunca ocupa una fracción grande de
       la foto.
    """
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("No se pudo leer la imagen.")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    mask = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        _ADAPTIVE_BLOCK_SIZE,
        _ADAPTIVE_C,
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _MORPH_KERNEL, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _MORPH_KERNEL, iterations=1)
    mask = _drop_oversized_components(mask)

    output = np.zeros((*mask.shape, 4), dtype=np.uint8)
    output[..., :3] = _INK_COLOR_BGR
    output[..., 3] = mask

    ok, png_bytes = cv2.imencode(".png", output)
    if not ok:
        raise ValueError("No se pudo generar el PNG limpio.")
    return png_bytes.tobytes()


def _drop_oversized_components(mask: np.ndarray) -> np.ndarray:
    total_area = mask.shape[0] * mask.shape[1]
    max_area = total_area * _MAX_COMPONENT_AREA_FRACTION

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cleaned = np.zeros_like(mask)
    for label in range(1, count):  # 0 es el fondo
        if stats[label, cv2.CC_STAT_AREA] <= max_area:
            cleaned[labels == label] = 255
    return cleaned
