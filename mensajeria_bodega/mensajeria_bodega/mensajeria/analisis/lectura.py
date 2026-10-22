"""
lectura.py · De las líneas de la bitácora a Registros.

  - desde_linea : PURA. Una línea -> un Registro (o None si está dañada).
  - registros   : PURA. Muchas líneas -> muchos Registros, con map y filter.
  - leer_mensajes: el BORDE. La única que abre el archivo para leer.

Todo es PEREZOSO: se procesa una línea a la vez, cuando alguien pide la
siguiente. Por eso leer 100.000 mensajes ocupa la misma memoria que leer 10
(req. 10).
"""

import json
import os
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import NamedTuple


class Registro(NamedTuple):
    """Un mensaje ya guardado en la bitácora (inmutable)."""

    tipo: str
    emisor: str
    canal: str | None
    destino: str | None
    contenido: str
    timestamp: datetime


def desde_linea(linea: str) -> Registro | None:
    """
    PURA: convierte una línea JSON en Registro.
    Si la línea está dañada devuelve None: no lanza error y no imprime.
    """
    try:
        datos = json.loads(linea)
        return Registro(
            tipo=str(datos["tipo"]),
            emisor=str(datos["emisor"]),
            canal=datos.get("canal"),          # puede ser None (en un privado)
            destino=datos.get("destino"),      # puede ser None (en un mensaje de canal)
            contenido=str(datos["contenido"]),
            timestamp=datetime.fromisoformat(datos["timestamp"]),
        )
    # JSONDecodeError: JSON roto · KeyError: falta un campo
    # TypeError: no es un diccionario ("5", "[]") o la hora es None
    # ValueError: la hora está mal escrita
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def registros(lineas: Iterable[str]) -> Iterator[Registro]:
    """
    PURA y perezosa: aplica desde_linea a cada línea (map) y se queda solo con
    las que NO son None (filter). Recibe LÍNEAS, no una ruta: así se puede
    probar con una lista, sin crear ningún archivo.
    """
    return filter(None, map(desde_linea, lineas))


def leer_mensajes(ruta: str) -> Iterator[Registro]:
    """
    El BORDE de la lectura: abre el archivo y entrega los registros uno por uno
    (es un generador, por el 'yield'). Nunca carga el archivo completo.
    Si la bitácora todavía no existe, simplemente no entrega nada.
    """
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8", errors="replace") as archivo:
        yield from registros(archivo)
