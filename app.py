import socket
import struct
import threading
import time
import json
from node import Node
from config import MCAST_GRP, MCAST_PORT, BUFFER_SIZE

class App:
    def __init__(self, id, ip, port):
        self.node = Node(id, ip, port) # o seu nó 
        self.friends = {} # todos os nós de fora
        self.leader_id = None # id do leader
        self.state = "running" # running, election and consensus
        self.timeout_threshold = 10 # Limite do timeout (em segundos)
        self.stop_event = threading.Event() # responsavel por parar os loopings

        # responsavel por esperar a thread iniciar
        self._ready_multicast = threading.Event() 
        self._ready_unicast = threading.Event()

        # socket para enviar multicast
        self.multicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', 1))
        self.multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.node.ip))

        # socket dedicado para ouvir unicast na própria porta do node
        self.unicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.unicast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.unicast_sock.bind((self.node.ip, self.node.port))
        self.unicast_sock.settimeout(1.0)

    def start(self):
        threading.Thread(target=self._listener_multicast, daemon=True).start()
        threading.Thread(target=self._listener_unicast, daemon=True).start()
        threading.Thread(target=self._monitor_peers, daemon=True).start()

        self._ready_multicast.wait()
        self._ready_unicast.wait()
        print("[START] Listeners prontos. Iniciando discovery.")

        self._start_discovery()
        self._start_keep_alive()

    # (A Fazer)
    def _consensus(self):
        return

    # (A Fazer)
    def _election(self):
        return

    def _start_discovery(self):
        """Envia um multicast para saber quem está na rede"""
        while not self.stop_event.is_set() and len(self.friends) < 1:
            msg = json.dumps({
                'type': 'discover',
                'id': self.node.id,
                'ip': self.node.ip,
                'port': self.node.port
            })
            self.multicast_sock.sendto(msg.encode(), (MCAST_GRP, MCAST_PORT))
            print("[DISCOVER] Procurando nodes via multicast...")
            time.sleep(5)

    def _start_keep_alive(self):
        """ Envia que vc está vivo a cada 5 segundos """
        while not self.stop_event.is_set():
            msg = json.dumps({
                'type': 'heartbeat',
                'id': self.node.id,
                'ip': self.node.ip,
                'port': self.node.port,
            })                        
            self.multicast_sock.sendto(msg.encode(), (MCAST_GRP, MCAST_PORT))
            time.sleep(5)
            print(f"[WAITING] Total de nodes: {len(self.friends) + 1}")

    def _listener_multicast(self):
        """Escuta respostas enviadas por multicast"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', MCAST_PORT))
        
        mreq = struct.pack('4s4s', socket.inet_aton(MCAST_GRP), socket.inet_aton(self.node.ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)

        self._ready_multicast.set()
        print(f"[MULTICAST LISTENER] ouvindo multicast {MCAST_GRP}:{MCAST_PORT}")

        while not self.stop_event.is_set():
            try:
                data, (sender_ip, sender_port) = sock.recvfrom(BUFFER_SIZE)
                payload = json.loads(data.decode())

                # Ignora o seu multicast
                if payload.get('id') == self.node.id: 
                    continue

                peer_id = payload.get('id')
                peer_ip = payload.get('ip')
                peer_port = payload.get('port')
                
                if peer_id not in self.friends :
                    print(f"Node encontrado: {peer_id} em {peer_ip}:{peer_port}")                    
                    self._add_friend(peer_id, peer_ip, peer_port, False)
                    self._send_ack(peer_ip, peer_port) # envia ACK unicast diretamente ao nó
                    

                if payload.get('type') == 'heartbeat':                    
                    self.friends[peer_id].last_seen = time.time()

            except socket.timeout:
                continue

        sock.close()

    def _listener_unicast(self):
        """Escuta respostas enviadas unicamente para esse nó"""
        self._ready_unicast.set()
        print(f"[UNICAST LISTENER] ouvindo unicast {self.node.ip}:{self.node.port}")
        while not self.stop_event.is_set():
            try:
                data, (sender_ip, sender_port) = self.unicast_sock.recvfrom(BUFFER_SIZE)
                payload = json.loads(data.decode())

                if payload.get('id') == self.node.id:
                    continue

                if payload.get('type') == 'ack': 
                    peer_id = payload['id']
                    peer_ip = payload['ip']
                    peer_port = payload['port']
                    peer_is_leader = payload['isLeader']

                    if peer_id not in self.friends:                        
                        self._add_friend(peer_id, peer_ip, peer_port, peer_is_leader) # add um novo amigo caso ele não esteja add

                    self.friends[peer_id].last_seen = time.time() # Atualiza a ultima vez que ele foi visto

                    # self._send_keep_alive(peer_ip, peer_port) # Manda um sinal de volta dizendo que ele está vivo

            except socket.timeout:
                continue

        self.unicast_sock.close()

    def _monitor_peers(self):
        """Monitora os nós que estão muito tempo sem dar sinal de vida"""
        while not self.stop_event.is_set():
            now = time.time()
            for peer_id, node in list(self.friends.items()):
                if now - node.last_seen > self.timeout_threshold:
                    print(f"[TIMEOUT] Nó {peer_id} sem resposta por {self.timeout_threshold} segundos")                    
                    
                    # remove o integrante 
                    self._remove_friend(peer_id)                    
                    # Se for o líder, dispare eleição:
                    # if peer_id == self.leader_id:
                    #     self._election()
            time.sleep(1)

    def _send_ack(self, peer_ip, peer_port):
        """Envia um ACK unicast para o peer que acabou de descobrir."""
        ack_msg = json.dumps({
            'type': 'ack',
            'id': self.node.id,
            'ip': self.node.ip,
            'port': self.node.port,
            'isLeader': self.node.is_leader
        })
        self.unicast_sock.sendto(ack_msg.encode(), (peer_ip, peer_port))
        print(f"Respondendo {peer_ip}:{peer_port}")
    
    def _add_friend(self, id, ip, port, is_leader):
        """Add um novo nó da rede"""
        if id == self.node.id or id in self.friends:
            return
        
        new_node = Node(id, ip, port)
        if is_leader:
            new_node.is_leader = True
            self.leader_id = new_node.id

        self.friends[id] = new_node
        print(f"[ADD NODE] Novo nó add {id} -> {ip}:{port}")

    def _remove_friend(self, id):
        """Remove um novo nó da rede"""
        if id not in self.friends:
            return
        del self.friends[id]
        print(f"[DELETE NODE] Deletando nó {id}")
