"""
persistencia.py · La bitácora en disco y su carpeta de respaldo.

Resuelve el req. 07: "cada mensaje aceptado queda guardado en disco; apagar
el servidor no pierde ninguno".

LA IDEA (Unidad 3, programación funcional):

    Mensaje --(puro: a_json)--> cola --> escritor (EFECTO: escribe el archivo)

  - Muchos hilos (uno por cliente) ponen mensajes en una COLA.
  - UN SOLO hilo, el escritor, los saca y los escribe. Así nunca hay dos
    hilos escribiendo el archivo a la vez (no se mezclan líneas).
  - El escritor NO es "daemon" y se apaga con un centinela (None): antes de
    terminar vacía la cola completa. Por eso no se pierde ningún mensaje.

El formato es JSON Lines: un mensaje JSON por línea, en UTF-8.
"""

import os
import queue
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from mensajeria.mensaje import Mensaje

# Solo se guardan los mensajes de canal y los privados (no unirse/dejar/error).
# Es una constante inmutable: nadie la puede cambiar mientras corre el programa.
TIPOS_GUARDADOS = frozenset({"mensaje", "privado"})

# Cuántas copias de respaldo se conservan (las más viejas se borran).
RESPALDOS_A_CONSERVAR = 20


# ---------------------- Funciones PURAS ----------------------

def se_guarda(mensaje: Mensaje) -> bool:
    """PURA (predicado): True solo si el mensaje va a la bitácora."""
    return mensaje.tipo in TIPOS_GUARDADOS


def nombre_respaldo(ahora: datetime) -> str:
    """PURA: el nombre del archivo de respaldo, con fecha y hora."""
    return f"mensajes_{ahora:%Y%m%d_%H%M%S}.log"


def respaldos_a_borrar(nombres: list[str], conservar: int) -> list[str]:
    """
    PURA: de una lista de respaldos, cuáles sobran.
    Como el nombre lleva la fecha (AñoMesDía_HoraMinSeg), ordenar por nombre
    es ordenar por fecha. Se conservan los 'conservar' más recientes.
    """
    ordenados = sorted(n for n in nombres if n.startswith("mensajes_") and n.endswith(".log"))
    return ordenados[:-conservar] if conservar > 0 else ordenados


# ---------------------- El BORDE (efectos) ----------------------

def escribir(
    cola: "queue.Queue[Mensaje | None]",
    ruta: str,
    serializar: Callable[[Mensaje], str],
    guardar_si: Callable[[Mensaje], bool],
) -> None:
    """
    El hilo escritor. Es una FUNCIÓN DE ORDEN SUPERIOR: recibe como
    parámetros la función que convierte a texto (serializar) y la que decide
    qué se guarda (guardar_si). El escritor no sabe nada de JSON ni de tipos.

    Termina cuando saca de la cola el centinela None.
    """
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    # "a" = append: agrega al final y NUNCA borra lo que ya había.
    with open(ruta, "a", encoding="utf-8") as archivo:
        while (mensaje := cola.get()) is not None:
            if guardar_si(mensaje):
                archivo.write(serializar(mensaje) + "\n")
                # flush + fsync: el mensaje queda de verdad en el disco ya
                # mismo. Si se va la luz, lo que se aceptó ya está guardado.
                archivo.flush()
                os.fsync(archivo.fileno())


def respaldar(ruta_log: str, carpeta: str, ahora: datetime) -> str | None:
    """
    Copia la bitácora a la carpeta de respaldo (datos/respaldo/).
    Se llama al ARRANCAR y al APAGAR el servidor. Devuelve la ruta de la
    copia, o None si todavía no había bitácora que copiar.
    """
    if not os.path.exists(ruta_log) or os.path.getsize(ruta_log) == 0:
        return None
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, nombre_respaldo(ahora))
    shutil.copy2(ruta_log, destino)          # copia el archivo con su fecha
    for viejo in respaldos_a_borrar(os.listdir(carpeta), RESPALDOS_A_CONSERVAR):
        os.remove(os.path.join(carpeta, viejo))
    return destino
