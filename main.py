import socket
import random
from app import App

def get_local_ip():
    # obtém IP real da máquina
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()

def main():
    local_ip = get_local_ip()
    local_port = random.randint(20000, 60000)
    node_id = random.randint(10000, 100000)  # ID aleatório
    app = App(node_id, local_ip, local_port)
    app.start()

if __name__ == '__main__':
    main()
