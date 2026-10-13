import socket
import threading

HOST = "127.0.0.1"
PORT = 8000

def recibir_mensajes(conexion):
    """Escucha de forma continua los mensajes enviados por el servidor."""
    while True:
        try:
            datos = conexion.recv(1024)
            if not datos:
                break
            print(f"\r{datos.decode('utf-8')}\n> ", end="", flush=True)
        except:
            break

# Conexión principal con el servidor
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as cliente:
    cliente.connect((HOST, PORT))

    # Identificación inicial del usuario
    nombre = input("Ingresa tu nombre: ")
    cliente.sendall(nombre.encode('utf-8'))

    print("\n--- Conectado al chat. Escribe '0' para salir ---\n")

    # Hilo para recibir mensajes concurrentemente
    hilo = threading.Thread(target=recibir_mensajes, args=(cliente,), daemon=True)
    hilo.start()

    # Bucle principal de envío
    while True:
        mensaje = input("> ")
        if mensaje.lower() == "0":
            break
        if mensaje.strip():
            cliente.sendall(mensaje.encode('utf-8'))