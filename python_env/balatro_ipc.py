import socket
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger("BalatroIPC")

# region agent log
_DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "debug-260fea.log"
_DEBUG_SESSION_ID = "260fea"
_DEBUG_IPC_SEQ = 0


def _ipc_dbglog(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": "ipc-trace",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        # Never fail IPC due to debug logging, but surface failures loudly.
        try:
            logger.warning(
                "[RL_DEBUG_LOG_FAIL] %s: %s | path=%s",
                type(e).__name__,
                e,
                str(_DEBUG_LOG_PATH),
            )
        except Exception:
            pass


# endregion

# region agent log
_ipc_dbglog(
    "H0",
    "python_env/balatro_ipc.py:module_import",
    "balatro_ipc imported",
    {
        "debug_log_path": str(_DEBUG_LOG_PATH),
        "python_exe": __import__("sys").executable,
    },
)
# endregion

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
                # region agent log
                _ipc_dbglog(
                    "H1",
                    "python_env/balatro_ipc.py:connect",
                    "ipc connected",
                    {"host": self.host, "port": self.port, "attempt": attempt + 1},
                )
                # endregion
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
        global _DEBUG_IPC_SEQ
        _DEBUG_IPC_SEQ += 1
        seq = _DEBUG_IPC_SEQ
        cmd0 = (action_cmd or "").split(" ", 1)[0]
        is_get_state = cmd0 == "GET_STATE"

        if not self.sock:
            self.connect()

        try:
            # region agent log
            if seq <= 5 or seq % 50 == 0:
                _ipc_dbglog(
                    "H1",
                    "python_env/balatro_ipc.py:send_action_and_get_state",
                    "ipc send",
                    {
                        "seq": seq,
                        "cmd0": cmd0,
                        "is_get_state": bool(is_get_state),
                        "cmd_len": len(action_cmd or ""),
                    },
                )
            # endregion

            # 1. 发送动作指令（附带换行符）
            self.sock.sendall(f"{action_cmd}\n".encode('utf-8'))
            
            # 2. 阻塞读取直到遇到换行符
            response = self.stream.readline()
            
            if not response:
                raise ConnectionAbortedError("Socket connection dropped by server.")

            parsed = json.loads(response)
            # region agent log
            if seq <= 5 or seq % 50 == 0:
                scr = None
                if isinstance(parsed, dict):
                    scr = parsed.get("current_screen")
                _ipc_dbglog(
                    "H1",
                    "python_env/balatro_ipc.py:send_action_and_get_state",
                    "ipc recv",
                    {
                        "seq": seq,
                        "cmd0": cmd0,
                        "resp_len": len(response),
                        "current_screen": scr,
                        "last_action_invalid": bool(parsed.get("last_action_invalid"))
                        if isinstance(parsed, dict)
                        else None,
                        "last_action_throttled": bool(parsed.get("last_action_throttled"))
                        if isinstance(parsed, dict)
                        else None,
                    },
                )
            # endregion

            return parsed
            
        except Exception as e:
            logger.error(f"IPC Error during step: {e}")
            # region agent log
            _ipc_dbglog(
                "H2",
                "python_env/balatro_ipc.py:send_action_and_get_state",
                "ipc error",
                {"seq": seq, "cmd0": cmd0, "exc_type": type(e).__name__},
            )
            # endregion
            self.disconnect() # 发生错误时断开，下次请求时会自动重连
            raise e