import os
import time
import json
import logging

logger = logging.getLogger("BalatroIPC")

def read_json_safe(filepath, max_retries=100, delay=0.05):
    """
    安全的 JSON 读取机制：附带重试和异常捕获，解决进程间读写冲突
    """
    for _ in range(max_retries):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, PermissionError):
                pass
        time.sleep(delay)
    
    error_msg = f"Timeout reading {filepath}. Lua Mod might be stopped or game not running."
    logger.error(error_msg)
    raise TimeoutError(error_msg)

def send_action(cmd_string, action_file):
    """
    下发指令：采用临时文件重命名的方式实现原子写入
    """
    temp_file = action_file + ".tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(cmd_string)
        os.replace(temp_file, action_file)
        logger.debug(f"Action dispatched: {cmd_string}")
    except Exception as e:
        logger.error(f"Failed to dispatch action: {e}")