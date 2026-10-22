"""
servidor.py · Arranca el servidor de mensajería.

Cómo se ejecuta (desde la carpeta raíz del proyecto):

    python -m mensajeria.servidor                 # solo en este equipo (localhost)
    python -m mensajeria.servidor --host 0.0.0.0  # para toda la red local de la bodega

Para apagarlo: Ctrl + C. Al apagar, el servidor espera a que se escriba TODO
lo que quedó en la cola y hace una copia de respaldo de la bitácora.

Lo que pone en marcha:
  - Un socket TCP en el puerto 8000 que acepta clientes (un hilo por cliente).
  - Un socket UDP en el puerto 8001 que recibe los latidos.
  - Un hilo escritor que guarda la bitácora en datos/mensajes.log.
"""

import argparse
import queue
import socket
import threading
import time
from datetime import datetime

from mensajeria import CARPETA_RESPALDO, PUERTO_TCP, PUERTO_UDP, RUTA_LOG
from mensajeria.conectados import Directorio
from mensajeria.conexion import Conexion
from mensajeria.latidos import ReceptorLatidos
from mensajeria.mensaje import Mensaje
from mensajeria.persistencia import escribir, respaldar, se_guarda


class Servidor:
    """Junta todas las piezas: red TCP, latidos UDP, directorio y bitácora."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        puerto_tcp: int = PUERTO_TCP,
        puerto_udp: int = PUERTO_UDP,
        ruta_log: str = str(RUTA_LOG),
        carpeta_respaldo: str = str(CARPETA_RESPALDO),
    ) -> None:
        self.host = host
        self.puerto_tcp = puerto_tcp
        self.puerto_udp = puerto_udp
        self.ruta_log = ruta_log
        self.carpeta_respaldo = carpeta_respaldo

        self.directorio = Directorio()
        self.cola: "queue.Queue[Mensaje | None]" = queue.Queue()
        self._detener = threading.Event()
        self._hilos_clientes: list[threading.Thread] = []

        # El escritor NO es daemon: así el programa espera a que vacíe la cola.
        # Le pasamos las FUNCIONES Mensaje.a_json y se_guarda (orden superior).
        self._escritor = threading.Thread(
            target=escribir,
            args=(self.cola, self.ruta_log, Mensaje.a_json, se_guarda),
            name="escritor",
        )
        self._sock_tcp: socket.socket | None = None
        self._latidos: ReceptorLatidos | None = None
        self._hilo_aceptar: threading.Thread | None = None

    # ------------------------------------------------------------------
    def iniciar(self) -> None:
        """Abre los puertos y arranca todos los hilos."""
        copia = respaldar(self.ruta_log, self.carpeta_respaldo, datetime.now())
        if copia:
            print(f"[respaldo] Copia de la bitácora al arrancar: {copia}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR: permite volver a arrancar el servidor enseguida, sin
        # esperar a que el sistema operativo libere el puerto (req. técnico 04).
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.puerto_tcp))
        sock.listen()            # sin número fijo de clientes (req. 03)
        sock.settimeout(1.0)     # cada segundo revisa si le pidieron apagarse
        self._sock_tcp = sock

        self._latidos = ReceptorLatidos(self.host, self.puerto_udp, self.directorio)
        self._escritor.start()
        self._latidos.iniciar()
        self._hilo_aceptar = threading.Thread(target=self._aceptar, name="aceptar", daemon=True)
        self._hilo_aceptar.start()
        print(f"Servidor escuchando en {self.host}: TCP {self.puerto_tcp} · UDP {self.puerto_udp}")
        print(f"Bitácora: {self.ruta_log}")

    def _aceptar(self) -> None:
        """Acepta clientes nuevos y le da a cada uno su propio hilo."""
        assert self._sock_tcp is not None
        while not self._detener.is_set():
            try:
                cliente, (ip, _puerto) = self._sock_tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                break                       # el socket se cerró: estamos apagando
            conexion = Conexion(cliente, ip, self.directorio, self.cola)
            hilo = threading.Thread(target=conexion.atender, daemon=True)
            hilo.start()
            # Se guarda el hilo para esperarlo al apagar; se limpian los que ya terminaron.
            self._hilos_clientes = [h for h in self._hilos_clientes if h.is_alive()] + [hilo]

    # ------------------------------------------------------------------
    def detener(self) -> None:
        """Apaga en orden para NO perder mensajes."""
        print("\nApagando el servidor...")
        self._detener.set()

        # 1) Dejar de aceptar clientes nuevos.
        if self._hilo_aceptar is not None:
            self._hilo_aceptar.join(timeout=3)
        if self._sock_tcp is not None:
            self._sock_tcp.close()

        # 2) Cerrar las conexiones de los clientes y esperar a sus hilos.
        for sesion in self.directorio.todas():
            try:
                sesion.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for hilo in self._hilos_clientes:
            hilo.join(timeout=3)

        # 3) Detener los latidos.
        if self._latidos is not None:
            self._latidos.detener()

        # 4) Recién ahora el centinela: el escritor vacía la cola y termina.
        if self._escritor.is_alive():
            self.cola.put(None)
            self._escritor.join()

        # 5) Copia de respaldo con todo lo del turno.
        copia = respaldar(self.ruta_log, self.carpeta_respaldo, datetime.now())
        if copia:
            print(f"[respaldo] Copia de la bitácora al apagar: {copia}")
        print("Servidor apagado. No se perdió ningún mensaje.")

    def esperar(self) -> None:
        """Deja el servidor corriendo hasta que alguien presione Ctrl + C."""
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.detener()


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor de mensajería de la bodega")
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 = solo este equipo; 0.0.0.0 = toda la red local")
    args = parser.parse_args()

    servidor = Servidor(host=args.host)
    try:
        servidor.iniciar()
    except OSError as error:
        print(f"No se pudo abrir el puerto: {error}. ¿Ya hay otro servidor corriendo?")
        return
    print("Presione Ctrl + C para apagar.\n")
    servidor.esperar()


if __name__ == "__main__":
    main()
