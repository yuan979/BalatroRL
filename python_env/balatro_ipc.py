import socket
import json
import time
import logging

logger = logging.getLogger("BalatroIPC")

class BalatroIPC:
    def __init__(self, host='127.0.0.1', port=12345):
        self.host = host
        self.port = port
        self.sock = None
        self.stream = None
        
    def connect(self, max_retries=10, delay=1.0):
        for attempt in range(max_retries):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # 新增：设置 3.0 秒超时！如果 Lua 卡死，Python 会抛出 TimeoutError，而不是永远阻塞
                self.sock.settimeout(3.0) 
                
                self.stream = self.sock.makefile('r', encoding='utf-8')
                logger.info(f"Successfully connected to Balatro at {self.host}:{self.port}")
                return
            except ConnectionRefusedError:
                logger.warning(f"Connection refused. Retrying {attempt + 1}/{max_retries} in {delay}s...")
                time.sleep(delay)
        raise ConnectionError("Failed to connect to Balatro TCP Server.")

    def disconnect(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_action_and_get_state(self, action_cmd: str) -> dict:
        """
        发送动作并同步阻塞接收游戏状态（核心 IPC 逻辑）
        """
        if not self.sock:
            self.connect()

        try:
            # 1. 发送动作指令（附带换行符）
            self.sock.sendall(f"{action_cmd}\n".encode('utf-8'))
            
            # 2. 阻塞读取直到遇到换行符
            response = self.stream.readline()
            
            if not response:
                raise ConnectionAbortedError("Socket connection dropped by server.")
                
            return json.loads(response)
            
        except Exception as e:
            logger.error(f"IPC Error during step: {e}")
            self.disconnect() # 发生错误时断开，下次请求时会自动重连
            raise e