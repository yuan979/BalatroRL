import logging
import time
from balatro_env import BalatroEnv
from balatro_actions import ACTION_MAPPING

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TestRoutine")

def get_action_index(action_name: str) -> int:
    for k, v in ACTION_MAPPING.items():
        if v == action_name:
            return k
    return -1

def wait_for_screen(env, target_screen, max_retries=10, delay=0.5):
    """
    持续轮询等待游戏进入目标界面 (处理动画过渡)
    """
    for _ in range(max_retries):
        time.sleep(delay)
        state = env.ipc.send_action_and_get_state("GET_STATE")
        current_screen = state.get("current_screen", "UNKNOWN")
        if current_screen == target_screen:
            return state
        logger.info(f"Waiting for animation... Current screen is still {current_screen}")
    return None

def run_diagnostic():
    logger.info("Initializing Balatro Environment for End-to-End Automation Testing...")
    try:
        env = BalatroEnv()
    except Exception as e:
        logger.error("Initialization failed: %s", e)
        return

    obs, info = env.reset()
    screen = info.get('raw_state', {}).get('current_screen', 'UNKNOWN')
    logger.info("Initial Screen: %s", screen)

    # 1. 自动开局
    if screen in ["MAIN_MENU", "GAME_OVER"]:
        logger.info("Detected Main Menu. Sending START_NEW_RUN...")
        env.step(get_action_index("START_NEW_RUN"))
        
        # 阻塞等待进入选盲注界面
        new_state = wait_for_screen(env, "BLIND_SELECT")
        if new_state:
            screen = new_state.get("current_screen")
            logger.info("Successfully entered: %s", screen)
        else:
            logger.error("Failed to transition to BLIND_SELECT.")
            return

    # 2. 自动选盲注
    if screen == "BLIND_SELECT":
        logger.info("Detected Blind Select. Sending SELECT_BLIND Small...")
        env.step(get_action_index("SELECT_BLIND Small"))
        
        # 阻塞等待进入打牌界面 (这里动画最长)
        new_state = wait_for_screen(env, "IN_GAME", max_retries=15, delay=0.5)
        if new_state:
            screen = new_state.get("current_screen")
            logger.info("Successfully entered: %s", screen)
        else:
            logger.error("Failed to transition to IN_GAME.")
            return

    # 3. 局内动作测试
    if screen == "IN_GAME":
        logger.info("Testing TOGGLE_CARD_1...")
        action_idx = get_action_index("TOGGLE_CARD_1")
        if action_idx != -1:
            obs, reward, terminated, truncated, step_info = env.step(action_idx)
            logger.info("Step Reward: %.4f", reward)
            
            # 打印刚刚选中的卡牌索引列表，验证缓存机制
            selected = step_info.get("internal_selection", [])
            logger.info("Currently Selected Cards Internally: %s", selected)
            
    env.close()

if __name__ == "__main__":
    run_diagnostic()