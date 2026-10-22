"""
latidos.py · Recibe los "sigo vivo" de las estaciones por UDP (puerto 8001).

Req. 08: cada estación manda un latido cada 5 segundos. Si alguien lleva más
de 15 segundos sin mandarlo, aparece como "inactivo" en la lista de conectados.

¿Por qué UDP y no TCP? Un latido es pequeño y se repite: si se pierde uno no
pasa nada, llega el siguiente. UDP es más liviano: no abre conexión.

Formato del latido (un solo datagrama, JSON):  {"tipo": "latido", "contenido": "ana"}
"""

import socket
import threading
from datetime import datetime

from mensajeria.conectados import Directorio
from mensajeria.mensaje import desde_bytes

TAMANO_MAXIMO = 1024     # un latido es corto; lo que pase de esto se ignora


class ReceptorLatidos:
    """Un hilo que escucha latidos UDP y actualiza el directorio."""

    def __init__(self, host: str, puerto: int, directorio: Directorio) -> None:
        self.directorio = directorio
        self._detener = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, puerto))
        # Cada segundo "despierta" para revisar si le pidieron detenerse.
        self.sock.settimeout(1.0)
        self.hilo = threading.Thread(target=self._escuchar, name="latidos", daemon=True)

    def iniciar(self) -> None:
        self.hilo.start()

    def detener(self) -> None:
        self._detener.set()
        self.hilo.join(timeout=3)
        self.sock.close()

    def _escuchar(self) -> None:
        while not self._detener.is_set():
            try:
                datos, (ip, _puerto) = self.sock.recvfrom(TAMANO_MAXIMO)
            except socket.timeout:
                continue                    # no llegó nada; volver a revisar
            except OSError:
                if self._detener.is_set():
                    return
                continue                    # error suelto de red: se ignora

            latido = desde_bytes(datos)
            if latido is None or latido.tipo != "latido":
                continue                    # basura por UDP: se ignora sin romper nada
            nombre = latido.contenido.strip()
            # El directorio solo lo acepta si el nombre está conectado y la IP coincide.
            self.directorio.latido(nombre, ip, datetime.now().replace(microsecond=0))
