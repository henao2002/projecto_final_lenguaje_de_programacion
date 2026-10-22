"""
generar_bitacora.py · Crea una bitácora FALSA de un mes para probar el reporte.

Sirve para demostrar el req. 10 (unos 100.000 mensajes) sin tener que
escribir 100.000 mensajes a mano. NO toca la bitácora real (datos/mensajes.log).

    python generar_bitacora.py                    # 100.000 mensajes en datos/mes_prueba.log
    python generar_bitacora.py --cantidad 5000
    python -m mensajeria.analisis.reporte datos/mes_prueba.log
"""

import argparse
import random
from datetime import datetime, timedelta

from mensajeria import CARPETA_DATOS
from mensajeria.conectados import CANALES
from mensajeria.mensaje import Mensaje

PERSONAS = ["ana", "luis", "sofía", "carlos", "marta", "jorge", "paula", "diego",
            "valentina", "andrés", "camila", "supervisor1", "supervisor2", "supervisor3"]

FRASES = [
    "El pedido {n} ya está alistado en el muelle {m}",
    "Falta una caja en el despacho del pedido {n}",
    "Montacargas {m} sin batería, se necesita cambio",
    "Recepción del camión {m} lista, pasa a revisión",
    "Estiba dañada en el pasillo {m}, por favor revisar",
    "Despacho {n} sale incompleto, falta producto",
    "Inventario del pasillo {m} actualizado",
    "¿Quién puede apoyar en el muelle {m}?",
    "Camión {m} retrasado, llega en 30 minutos",
    "Pedido {n} con novedad: producto averiado",
]

# Más mensajes en ciertas horas (inicio y cambio de turno), como en una bodega real.
PESO_POR_HORA = [2, 1, 1, 1, 1, 3, 8, 9, 7, 6, 6, 5, 4, 7, 9, 8, 6, 5, 4, 4, 3, 7, 5, 3]


def generar(cantidad: int, ruta: str, semilla: int = 2026) -> None:
    azar = random.Random(semilla)                 # misma semilla -> mismo archivo
    inicio = datetime(2026, 9, 1)
    with open(ruta, "w", encoding="utf-8") as archivo:
        for _ in range(cantidad):
            dia = azar.randrange(30)
            hora = azar.choices(range(24), weights=PESO_POR_HORA)[0]
            momento = inicio + timedelta(days=dia, hours=hora,
                                         minutes=azar.randrange(60), seconds=azar.randrange(60))
            texto = azar.choice(FRASES).format(n=azar.randrange(1000, 9999), m=azar.randrange(1, 12))
            emisor = azar.choice(PERSONAS)
            if azar.random() < 0.15:              # 15 % son privados
                destino = azar.choice([p for p in PERSONAS if p != emisor])
                m = Mensaje("privado", emisor, None, destino, texto, momento)
            else:
                m = Mensaje("mensaje", emisor, azar.choice(CANALES), None, texto, momento)
            archivo.write(m.a_json() + "\n")
    print(f"Listo: {cantidad} mensajes en {ruta}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera una bitácora de prueba")
    parser.add_argument("--cantidad", type=int, default=100_000)
    parser.add_argument("--salida", default=str(CARPETA_DATOS / "mes_prueba.log"))
    args = parser.parse_args()
    generar(args.cantidad, args.salida)
