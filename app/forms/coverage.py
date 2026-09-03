"""Chequeo de cobertura por ubicación en el formulario de Autorización de Corretaje.

Placeholder: el listado real de sectores/ciudades con cobertura todavía no
existe (en construcción del lado del negocio), así que por ahora esta
función siempre deja pasar — es el único punto a cambiar cuando el listado
esté listo, sin tocar nada del wizard que la llama.
"""
from __future__ import annotations


def is_location_covered(location: str) -> bool:
    return True
