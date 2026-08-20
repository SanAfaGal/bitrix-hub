import cv2
import numpy as np
import pytest

from app.forms.signature_cleaner import clean_signature_photo


def _noisy_photo_with_ink_line() -> bytes:
    img = np.full((200, 400, 3), 245, dtype=np.uint8)
    rng = np.random.default_rng(0)
    noise = rng.integers(-8, 8, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    cv2.line(img, (40, 150), (360, 60), (20, 20, 20), 4)
    ok, jpg = cv2.imencode(".jpg", img)
    assert ok
    return jpg.tobytes()


def test_clean_signature_photo_keeps_only_ink():
    cleaned_png = clean_signature_photo(_noisy_photo_with_ink_line())

    decoded = cv2.imdecode(np.frombuffer(cleaned_png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert decoded.shape[2] == 4

    alpha = decoded[..., 3]
    ink_pixels = int((alpha > 0).sum())
    total_pixels = alpha.size

    # Solo el trazo (una línea delgada) debería quedar opaco, no el papel/ruido.
    assert 0 < ink_pixels < total_pixels * 0.1


def test_clean_signature_photo_rejects_invalid_bytes():
    with pytest.raises(ValueError):
        clean_signature_photo(b"not an image")


def _photo_with_uneven_lighting_and_thin_line() -> bytes:
    """Simula una foto de celular real: sombra de la mano/teléfono que oscurece
    la mitad de la hoja, más una firma delgada encima."""
    height, width = 300, 600
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        value = int(120 + (x / width) * 130)  # sombra a la izquierda -> bien iluminado a la derecha
        img[:, x] = (value, value, value)
    rng = np.random.default_rng(1)
    noise = rng.integers(-6, 6, img.shape, dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    cv2.line(img, (80, 220), (520, 90), (10, 10, 10), 3)
    cv2.line(img, (150, 180), (300, 240), (10, 10, 10), 2)
    ok, jpg = cv2.imencode(".jpg", img)
    assert ok
    return jpg.tobytes()


def test_clean_signature_photo_ignores_shadow_from_uneven_lighting():
    cleaned_png = clean_signature_photo(_photo_with_uneven_lighting_and_thin_line())

    decoded = cv2.imdecode(np.frombuffer(cleaned_png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    alpha = decoded[..., 3]
    ink_pixels = int((alpha > 0).sum())
    total_pixels = alpha.size

    # Un umbral global (Otsu) confunde toda la mitad sombreada con tinta
    # (~48% de la foto). El umbral adaptativo + filtro de blobs grandes debe
    # quedarse solo con las líneas delgadas.
    assert ink_pixels < total_pixels * 0.05
