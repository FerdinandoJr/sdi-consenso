import time

class Node:
    def __init__(self, id, ip, port):
        self.id = id
        self.ip = ip
        self.port = port
        self.is_leader = False
        self.last_seen = time.time()

        print(f"[NODE CREATE] {self.id}: {self.ip}:{self.port} | {self.is_leader} | {self.last_seen}")