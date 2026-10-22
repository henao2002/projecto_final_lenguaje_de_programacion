"""
cliente.py · El programa que usa cada estación de la bodega.

Cómo se ejecuta (desde la carpeta raíz del proyecto):

    python -m mensajeria.cliente                       # pide el nombre
    python -m mensajeria.cliente ana                   # entra como "ana"
    python -m mensajeria.cliente ana --host 192.168.1.10   # servidor en otro equipo

Trabaja con TRES hilos:
  - El principal: lee lo que la persona escribe y lo manda.
  - Uno que RECIBE: muestra en pantalla lo que llega del servidor.
  - Uno de LATIDOS: cada 5 s le dice al servidor "sigo vivo" por UDP.
"""

import argparse
import socket
import sys
import threading

from mensajeria import PUERTO_TCP, PUERTO_UDP
from mensajeria.mensaje import Mensaje, a_bytes, desde_bytes
from mensajeria.protocolo import enviar_trama, recibir_trama

CADA_CUANTO_LATIDO = 5.0   # segundos (el servidor marca inactivo a los 15)

AYUDA = """
Comandos:
  texto normal              -> se envía al canal actual
  /usar #canal              -> cambia el canal actual (debe estar unido)
  /unirse #canal            -> entra a #recepcion, #alistamiento o #despacho
  /dejar #canal             -> sale de un canal
  /privado nombre texto     -> mensaje solo para esa persona
  /conectados               -> quién está, si está activo y su última actividad
  /pausa                    -> detiene/reanuda los latidos (para probar "inactivo")
  /ayuda                    -> muestra esta ayuda
  /salir                    -> se desconecta
"""


# ---------------- Funciones PURAS (texto -> Mensaje, Mensaje -> texto) ----------------

def interpretar(linea: str, canal_actual: str) -> Mensaje | None:
    """
    PURA: convierte lo que escribe la persona en el Mensaje a enviar.
    Devuelve None si es un comando local (/usar, /pausa, /ayuda) o está mal escrito.
    Fíjese que NO ponemos emisor ni hora: eso lo hace el servidor.
    """
    partes = linea.split(maxsplit=2)
    comando = partes[0].lower() if partes else ""
    if comando == "/unirse" and len(partes) >= 2:
        return Mensaje(tipo="unirse", canal=partes[1])
    if comando == "/dejar" and len(partes) >= 2:
        return Mensaje(tipo="dejar", canal=partes[1])
    if comando == "/privado" and len(partes) == 3:
        return Mensaje(tipo="privado", destino=partes[1], contenido=partes[2])
    if comando == "/conectados":
        return Mensaje(tipo="conectados")
    if comando == "/salir":
        return Mensaje(tipo="salir")
    if linea.startswith("/"):
        return None
    return Mensaje(tipo="mensaje", canal=canal_actual, contenido=linea)


def formatear(m: Mensaje) -> str:
    """PURA: cómo se ve en pantalla un mensaje que llegó."""
    hora = f"{m.timestamp:%H:%M:%S}" if m.timestamp else "--:--:--"
    if m.tipo == "mensaje":
        return f"[{hora}] {m.canal} {m.emisor}: {m.contenido}"
    if m.tipo == "privado":
        return f"[{hora}] (privado) {m.emisor}: {m.contenido}"
    if m.tipo == "error":
        return f"[{hora}] ERROR: {m.contenido}"
    return f"[{hora}] * {m.contenido}"


# ---------------- El cliente ----------------

class Cliente:
    def __init__(self, nombre: str, host: str, puerto_tcp: int, puerto_udp: int) -> None:
        self.nombre = nombre
        self.host = host
        self.puerto_udp = puerto_udp
        self.canal_actual = "#general"
        self.conectado = threading.Event()
        self.latidos_activos = threading.Event()
        self.latidos_activos.set()
        self.fin = threading.Event()          # se activa al desconectarse
        self.sock = socket.create_connection((host, puerto_tcp), timeout=10)
        self.sock.settimeout(None)

    def enviar(self, mensaje: Mensaje) -> None:
        enviar_trama(self.sock, a_bytes(mensaje))

    def presentarse(self) -> bool:
        """Manda el 'hola' y espera la respuesta del servidor."""
        self.enviar(Mensaje(tipo="hola", contenido=self.nombre))
        trama = recibir_trama(self.sock)
        respuesta = desde_bytes(trama) if trama is not None else None
        if respuesta is None:
            print("El servidor cerró la conexión.")
            return False
        print(formatear(respuesta))
        return respuesta.tipo == "bienvenida"

    def recibir(self) -> None:
        """Hilo que muestra todo lo que llega del servidor."""
        while (trama := recibir_trama(self.sock)) is not None:
            mensaje = desde_bytes(trama)
            if mensaje is not None:
                print("\r" + formatear(mensaje))
                print(f"{self.canal_actual}> ", end="", flush=True)
        if self.conectado.is_set():
            print("\nSe perdió la conexión con el servidor. Presione Enter para salir.")
        self.conectado.clear()
        self.fin.set()

    def latir(self) -> None:
        """Hilo que manda un latido UDP cada 5 segundos mientras haya conexión."""
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        latido = a_bytes(Mensaje(tipo="latido", contenido=self.nombre))
        while self.conectado.is_set():
            if self.latidos_activos.is_set():
                try:
                    udp.sendto(latido, (self.host, self.puerto_udp))
                except OSError:
                    pass                       # si falla uno, ya irá el siguiente
            # Espera 5 s (o sale antes si se desconecta).
            self.fin.wait(CADA_CUANTO_LATIDO)
        udp.close()

    def correr(self) -> None:
        if not self.presentarse():
            self.sock.close()
            return
        self.conectado.set()
        threading.Thread(target=self.recibir, daemon=True).start()
        threading.Thread(target=self.latir, daemon=True).start()
        print(AYUDA)

        try:
            while self.conectado.is_set():
                linea = input(f"{self.canal_actual}> ").strip()
                if not self.conectado.is_set():
                    break
                if not linea:
                    continue
                if self._comando_local(linea):
                    continue
                mensaje = interpretar(linea, self.canal_actual)
                if mensaje is None:
                    print("Comando no reconocido. Escriba /ayuda")
                    continue
                if mensaje.tipo == "salir":
                    self.conectado.clear()     # primero: así no avisa "se perdió la conexión"
                    self.enviar(mensaje)
                    break
                self.enviar(mensaje)
        except (KeyboardInterrupt, EOFError):
            self.conectado.clear()
            try:
                self.enviar(Mensaje(tipo="salir"))
            except OSError:
                pass
        except OSError:
            print("No se pudo enviar: se perdió la conexión.")
        finally:
            self.conectado.clear()
            self.fin.set()
            self.sock.close()
            print("\nDesconectado. ¡Hasta luego!")

    def _comando_local(self, linea: str) -> bool:
        """Comandos que se resuelven en el propio cliente, sin ir al servidor."""
        partes = linea.split()
        comando = partes[0].lower()
        if comando == "/ayuda":
            print(AYUDA)
            return True
        if comando == "/usar" and len(partes) == 2:
            self.canal_actual = partes[1]
            print(f"Ahora escribe en {self.canal_actual}")
            return True
        if comando == "/pausa":
            if self.latidos_activos.is_set():
                self.latidos_activos.clear()
                print("Latidos en pausa: en ~15 s aparecerá como 'inactivo'.")
            else:
                self.latidos_activos.set()
                print("Latidos reanudados.")
            return True
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente de mensajería de la bodega")
    parser.add_argument("nombre", nargs="?", help="su nombre en el chat")
    parser.add_argument("--host", default="127.0.0.1", help="IP del servidor")
    args = parser.parse_args()

    nombre = args.nombre or input("Su nombre: ").strip()
    try:
        cliente = Cliente(nombre, args.host, PUERTO_TCP, PUERTO_UDP)
    except OSError:
        print(f"No se pudo conectar a {args.host}:{PUERTO_TCP}. ¿Está encendido el servidor?")
        sys.exit(1)
    cliente.correr()


if __name__ == "__main__":
    main()
