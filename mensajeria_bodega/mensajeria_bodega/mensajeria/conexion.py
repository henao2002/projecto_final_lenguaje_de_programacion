"""
conexion.py · Atiende a UN cliente, de principio a fin, en su propio hilo.

Pasos de una conexión:
  1. El cliente se presenta con un "hola" y su nombre (req. 01).
  2. Se queda en un ciclo: recibe una trama, la revisa y la reparte.
  3. Si se desconecta (o se apaga su equipo), se le saca de la lista y el
     servidor sigue normal con los demás (req. 04).

Aquí vive el ÚNICO lugar donde se pone el emisor y la hora de un mensaje:
la función sellar(). El cliente NUNCA decide quién firmó ni a qué hora
(req. 06: autoría no suplantable).
"""

import queue
import socket
from datetime import datetime

from mensajeria.conectados import (
    CANAL_GENERAL, CANALES, Directorio, Sesion, describir_conectados, nombre_valido,
)
from mensajeria.mensaje import Mensaje, a_bytes, desde_bytes
from mensajeria.protocolo import enviar_trama, recibir_trama

SERVIDOR = "servidor"           # nombre con el que firma los avisos el servidor
ESPERA_PRESENTACION = 30.0      # segundos que esperamos el "hola" inicial


def ahora() -> datetime:
    """EFECTO (lee el reloj). Se usa solo en este módulo, al recibir."""
    return datetime.now().replace(microsecond=0)


def sellar(mensaje: Mensaje, emisor: str, hora: datetime) -> Mensaje:
    """
    Pone el emisor y la hora que decide el SERVIDOR. Si el cliente mandó
    otro emisor u otra hora (por ejemplo para suplantar a alguien), se pisan.
    Devuelve un Mensaje NUEVO (_replace no modifica el original).
    """
    return mensaje._replace(emisor=emisor, timestamp=hora)


def aviso(tipo: str, contenido: str, canal: str | None = None) -> Mensaje:
    """Un mensaje del servidor (bienvenida, sistema o error)."""
    return Mensaje(tipo=tipo, emisor=SERVIDOR, canal=canal, contenido=contenido, timestamp=ahora())


class Conexion:
    """Un cliente conectado. Se crea una por cada persona y corre en su hilo."""

    def __init__(
        self,
        sock: socket.socket,
        ip: str,
        directorio: Directorio,
        cola: "queue.Queue[Mensaje | None]",
    ) -> None:
        self.sock = sock
        self.ip = ip
        self.directorio = directorio
        self.cola = cola            # aquí se ponen los mensajes para la bitácora
        self.nombre: str | None = None

    # ------------------------------------------------------------------
    def atender(self) -> None:
        """Lo que hace el hilo de este cliente. Nunca deja escapar un error."""
        try:
            sesion = self._presentarse()
            if sesion is None:
                return
            self.nombre = sesion.nombre
            print(f"[+] {sesion.nombre} se conectó desde {self.ip}")
            self._anunciar(f"{sesion.nombre} se conectó")
            self._ciclo(sesion)
        except Exception as error:  # cinturón de seguridad: el servidor sigue vivo
            print(f"[!] Error inesperado con {self.nombre or self.ip}: {error!r}")
        finally:
            self._cerrar()

    # ------------------------------------------------------------------
    def _presentarse(self) -> Sesion | None:
        """Espera el 'hola' con el nombre. Devuelve la sesión o None si falla."""
        self.sock.settimeout(ESPERA_PRESENTACION)
        trama = recibir_trama(self.sock)
        self.sock.settimeout(None)          # de aquí en adelante, sin límite
        if trama is None:
            return None

        primero = desde_bytes(trama)
        if primero is None or primero.tipo != "hola":
            self._mandar(aviso("error", "Primero debe presentarse con su nombre."))
            return None

        nombre = primero.contenido.strip()
        if not nombre_valido(nombre):
            self._mandar(aviso("error", "Nombre inválido: use de 2 a 20 letras o números."))
            return None

        hora = ahora()
        sesion = Sesion(nombre=nombre, sock=self.sock, ip=self.ip,
                        ultimo_latido=hora, ultima_actividad=hora)
        if not self.directorio.registrar(sesion):
            self._mandar(aviso("error", f"Ya hay alguien conectado como '{nombre}'."))
            return None

        sesion.enviar(aviso("bienvenida", f"Hola {nombre}. Canales: {' '.join(CANALES)}. "
                                          f"Ya está en {CANAL_GENERAL}."))
        return sesion

    # ------------------------------------------------------------------
    def _ciclo(self, sesion: Sesion) -> None:
        """Recibe tramas hasta que el cliente se vaya."""
        while (trama := recibir_trama(self.sock)) is not None:
            recibido = desde_bytes(trama)
            if recibido is None:
                # JSON dañado: se descarta ESE mensaje y se sigue (req. técnico 05).
                self._error(sesion, "Mensaje dañado: se descartó.")
                continue

            hora = ahora()
            self.directorio.marcar_actividad(sesion.nombre, hora)
            mensaje = sellar(recibido, sesion.nombre, hora)

            if mensaje.tipo == "salir":
                return
            self._repartir(sesion, mensaje)

    # ------------------------------------------------------------------
    def _repartir(self, sesion: Sesion, m: Mensaje) -> None:
        """Decide qué hacer según el tipo de mensaje."""
        if m.tipo == "mensaje":
            self._mensaje_de_canal(sesion, m)
        elif m.tipo == "privado":
            self._mensaje_privado(sesion, m)
        elif m.tipo == "unirse":
            self._unirse(sesion, m)
        elif m.tipo == "dejar":
            self._dejar(sesion, m)
        elif m.tipo == "conectados":
            texto = describir_conectados(self.directorio.fotos(), ahora())
            sesion.enviar(aviso("sistema", texto))
        else:
            self._error(sesion, f"Tipo de mensaje no permitido: '{m.tipo}'.")

    def _mensaje_de_canal(self, sesion: Sesion, m: Mensaje) -> None:
        """Req. 02 y 11: el mensaje llega SOLO a los miembros del canal."""
        canal = m.canal or CANAL_GENERAL
        if canal not in CANALES:
            self._error(sesion, f"El canal '{canal}' no existe.")
            return
        if canal not in self.directorio.canales_de(sesion.nombre):
            self._error(sesion, f"No está en {canal}. Use /unirse {canal}")
            return
        if not m.contenido.strip():
            return  # mensaje vacío: no se reparte ni se guarda
        m = m._replace(canal=canal, destino=None)

        self.cola.put(m)  # 1) a la bitácora (lo escribe el hilo escritor)
        for otro in self.directorio.miembros(canal):   # 2) a los demás del canal
            if otro.nombre != sesion.nombre:
                otro.enviar(m)

    def _mensaje_privado(self, sesion: Sesion, m: Mensaje) -> None:
        """Req. 12: le llega SOLO a la persona de destino."""
        destino = (m.destino or "").strip()
        receptor = self.directorio.obtener(destino)
        if receptor is None:
            self._error(sesion, f"'{destino}' no está conectado.")
            return
        if destino == sesion.nombre:
            self._error(sesion, "No puede enviarse un privado a usted mismo.")
            return
        if not m.contenido.strip():
            return
        m = m._replace(canal=None, destino=destino)

        self.cola.put(m)
        receptor.enviar(m)

    def _unirse(self, sesion: Sesion, m: Mensaje) -> None:
        canal = m.canal or ""
        if canal not in CANALES:
            self._error(sesion, f"El canal '{canal}' no existe. Canales: {' '.join(CANALES)}")
            return
        self.directorio.unirse(sesion.nombre, canal)
        self.cola.put(m)  # el escritor lo ignora (no se guarda), pero pasa por el mismo camino
        sesion.enviar(aviso("sistema", f"Se unió a {canal}.", canal))

    def _dejar(self, sesion: Sesion, m: Mensaje) -> None:
        canal = m.canal or ""
        if canal == CANAL_GENERAL:
            self._error(sesion, f"Todos están en {CANAL_GENERAL}: no se puede dejar.")
            return
        if canal not in self.directorio.canales_de(sesion.nombre):
            self._error(sesion, f"No está en '{canal}'.")
            return
        self.directorio.dejar(sesion.nombre, canal)
        self.cola.put(m)
        sesion.enviar(aviso("sistema", f"Salió de {canal}.", canal))

    # ------------------------------------------------------------------
    def _error(self, sesion: Sesion, texto: str) -> None:
        """Le avisa el error al cliente. También pasa por la cola (no se guarda)."""
        error = aviso("error", texto)._replace(destino=sesion.nombre)
        self.cola.put(error)
        sesion.enviar(error)

    def _anunciar(self, texto: str) -> None:
        """Aviso del servidor a todos los de #general (no se guarda en la bitácora)."""
        mensaje = aviso("sistema", texto, CANAL_GENERAL)
        for otro in self.directorio.miembros(CANAL_GENERAL):
            if otro.nombre != self.nombre:
                otro.enviar(mensaje)

    def _mandar(self, mensaje: Mensaje) -> None:
        """Envío directo antes de tener sesión (por ejemplo, un error de nombre)."""
        try:
            enviar_trama(self.sock, a_bytes(mensaje))
        except OSError:
            pass

    def _cerrar(self) -> None:
        """Saca a la persona de la lista y cierra su conexión."""
        if self.nombre is not None:
            self.directorio.quitar(self.nombre)
            print(f"[-] {self.nombre} se desconectó")
            self._anunciar(f"{self.nombre} se desconectó")
        try:
            self.sock.close()
        except OSError:
            pass
