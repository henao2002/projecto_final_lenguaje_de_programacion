import socket
import threading

# Configuración de red: Dirección IP local (localhost) y puerto de escucha
HOST = "127.0.0.1"
PORT = 8000

# Diccionario global para almacenar los clientes conectados: {objeto_conexion: "NombreDeUsuario"}
clientes = {}

# Objeto Lock para sincronizar hilos. Evita que varios hilos modifiquen la lista
# de clientes al mismo tiempo (condiciones de carrera / race conditions).
lock = threading.Lock()

def difundir(mensaje, emisor=None):
    """
    Función de difusión (Broadcast): Reenvía un mensaje a todos los clientes 
    conectados en el chat, omitiendo opcionalmente al usuario que lo envió (emisor).
    """
    # Protegemos el recorrido del diccionario usando el bloqueo (with lock)
    with lock:
        for conexion in clientes:
            # Verificamos que no se le devuelva el mensaje al propio emisor
            if conexion != emisor:
                try:
                    # Enviamos los datos en bytes a través del socket del cliente
                    conexion.sendall(mensaje)
                except:
                    # Si ocurre un error al enviar (ej. cliente desconectado bruscamente), lo ignoramos
                    pass

def atender_cliente(conexion, direccion):
    """
    Función que se ejecuta en un hilo independiente (hilo por cliente).
    Maneja toda la comunicación individual de una estación conectada.
    """
    try:
        # El primer mensaje obligatorio que envía el cliente recién conectado es su nombre de usuario
        nombre_bytes = conexion.recv(1024)
        nombre = nombre_bytes.decode('utf-8').strip()
        
        # Si no llega ningún nombre, cerramos la conexión de inmediato
        if not nombre:
            conexion.close()
            return

        # Registramos de forma segura al nuevo cliente en el diccionario global
        with lock:
            clientes[conexion] = nombre

        # Mostramos en la consola del ordenador central quién se conectó y desde qué IP/puerto
        print(f"[+] {nombre} conectado desde {direccion}")
        
        # Notificamos a todos los demás usuarios que alguien nuevo entró al sistema
        difundir(f"--- {nombre} se ha unido al chat ---".encode('utf-8'), conexion)

        # Bucle continuo para escuchar los mensajes que envíe este cliente específico
        while True:
            datos = conexion.recv(1024) # Recibe hasta 1024 bytes de datos
            
            # Si 'datos' está vacío, significa que el cliente cerró la conexión de forma normal
            if not datos:
                break
            
            texto = datos.decode('utf-8')
            
            # Requisito Hito 1: El ordenador central visualiza la mensajería interna en tiempo real
            print(f"[{nombre}]: {texto}")
            
            # Reenviamos el mensaje formateado con el nombre a las demás estaciones
            difundir(f"{nombre}: {texto}".encode('utf-8'), conexion)

    except:
        # Captura cualquier error inesperado de red durante la comunicación
        pass
    
    finally:
        # Bloque finally: Se ejecuta obligatoriamente al terminar o fallar el hilo
        with lock:
            # Eliminamos al cliente del diccionario y obtenemos su nombre para el registro
            nombre = clientes.pop(conexion, "Desconocido")
        
        # Cerramos físicamente el socket de esta conexión
        conexion.close()
        
        # Informamos en la consola del servidor la salida del usuario
        print(f"[-] {nombre} se ha desconectado.")
        
        # Anunciamos a los demás participantes que el usuario abandonó el chat
        difundir(f"--- {nombre} ha abandonado el chat ---".encode('utf-8'))


# Bloque principal para poner en marcha el servidor de red
# Usamos 'with' para asegurar que el socket principal se cierre correctamente al terminar
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
    
    # SO_REUSEADDR permite reutilizar el puerto de inmediato si reiniciamos el servidor, 
    # evitando el error de "Dirección ya en uso" (Address already in use).
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Vinculamos el servidor al HOST y PORT definidos arriba
    servidor.bind((HOST, PORT))
    
    # Ponemos al servidor en modo escucha (esperando conexiones entrantes)
    servidor.listen()
    print(f"Servidor escuchando en {HOST}:{PORT}")

    # Bucle infinito principal: Se encarga exclusivamente de aceptar nuevas conexiones de clientes
    while True:
        # accept() bloquea la ejecución hasta que una nueva estación intenta conectarse.
        # Devuelve el socket de la conexión particular y la tuerca con la dirección (IP, puerto).
        conexion, direccion = servidor.accept()
        
        # Creamos un hilo (Thread) independiente para atender al nuevo cliente de forma concurrente.
        # daemon=True hace que el hilo muera automáticamente cuando el programa principal se cierre.
        hilo = threading.Thread(target=atender_cliente, args=(conexion, direccion), daemon=True)
        
        # Iniciamos la ejecución del hilo
        hilo.start()