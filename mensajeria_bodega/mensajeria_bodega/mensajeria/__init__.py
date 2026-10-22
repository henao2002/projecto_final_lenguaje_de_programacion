"""
Paquete "mensajeria": el sistema de chat interno del centro de distribución.

Cómo está repartido (cada archivo tiene UNA sola responsabilidad):

    protocolo.py    -> cómo viajan los bytes por la red (prefijo de longitud)
    mensaje.py      -> qué es un Mensaje y cómo se pasa a JSON y de vuelta
    conectados.py   -> quién está conectado, en qué canales y si está activo
    conexion.py     -> atiende a UN cliente (hay un hilo por cada persona)
    latidos.py      -> recibe los "sigo vivo" por UDP (puerto 8001)
    persistencia.py -> guarda la bitácora en disco y hace los respaldos
    servidor.py     -> junta todo y arranca el servidor (puerto 8000)
    cliente.py      -> el programa que usa cada estación de la bodega
    analisis/       -> el reporte de operación (Hito 3)
"""

from pathlib import Path

# Carpeta raíz del proyecto (la que contiene "mensajeria/" y "datos/").
# Así las rutas funcionan igual sin importar desde dónde se ejecute.
RAIZ = Path(__file__).resolve().parent.parent

# Dónde vive la bitácora y dónde se guardan sus copias de respaldo.
CARPETA_DATOS = RAIZ / "datos"
RUTA_LOG = CARPETA_DATOS / "mensajes.log"
CARPETA_RESPALDO = CARPETA_DATOS / "respaldo"

# Puertos que exige TI (requerimiento técnico 01).
PUERTO_TCP = 8000
PUERTO_UDP = 8001
