import logging
from balatro_env import BalatroEnv

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TestRoutine")

def run_diagnostic():
    logger.info("Initializing Balatro Environment (TCP Socket Mode)...")
    
    # 实例化环境，内部会自动尝试连接 Lua 端的 TCP Server
    try:
        env = BalatroEnv()
    except Exception as e:
        logger.error(f"Initialization failed: {e}. Is the game running with the Mod loaded?")
        return

    # 测试 1: 重置流程 (发送心跳指令 GET_STATE)
    logger.info("Testing reset()...")
    _, info = env.reset()
    state = info.get('raw_state', {})
    logger.info(f"Init Success. Screen: {state.get('current_screen', 'UNKNOWN')}")

    # 测试 2: 动作掩码机制
    mask = info.get('action_mask')
    if mask is not None and mask.any():
        logger.info("Action Masking is functioning. Valid actions detected.")
    else:
        logger.warning("Action Mask is entirely False. Check if game is in a transition state.")

    # 测试 3: 调试底层 TCP IPC 通信
    logger.info("Testing TCP IPC via SET_MONEY 888...")
    
    # 在新架构下，直接调用 env 内部的 ipc 实例，
    # 它会发送指令，并立刻被阻塞，直到瞬间接收到 Lua 返回的最新状态。
    try:
        new_state = env.ipc.send_action_and_get_state("SET_MONEY 888")
        
        if new_state.get('stats', {}).get('money') == 888:
            logger.info("TCP IPC Communication: VERIFIED")
        else:
            logger.error("TCP IPC Communication: FAILED (State updated, but money is incorrect)")
            
    except Exception as e:
        logger.error(f"TCP IPC Communication: FAILED with exception: {e}")
        
    finally:
        # 测试结束，安全关闭 Socket 连接
        env.close()

if __name__ == "__main__":
    run_diagnostic()