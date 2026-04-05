import logging
import time
from balatro_env import BalatroEnv
from balatro_actions import ACTION_MAPPING

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

def get_action_index(action_name: str) -> int:
    for k, v in ACTION_MAPPING.items():
        if v == action_name:
            return k
    return -1

def test_start_only():
    env = BalatroEnv()
    obs, info = env.reset()
    screen = info.get('raw_state', {}).get('current_screen', 'UNKNOWN')
    logging.info(f"Initial Screen: {screen}")

    if screen not in ["MAIN_MENU", "GAME_OVER"]:
        logging.error("Please make sure the game is on the MAIN MENU before running this script!")
        env.close()
        return

    logging.info("Sending START_NEW_RUN command...")
    action_idx = get_action_index("START_NEW_RUN")
    env.step(action_idx)
    
    # 每秒轮询一次，观察游戏是否从 MAIN_MENU 切出去了
    for i in range(5):
        time.sleep(1)
        state = env.ipc.send_action_and_get_state("GET_STATE")
        new_screen = state.get("current_screen", "UNKNOWN")
        logging.info(f"Polling state (Second {i+1})... Current screen: {new_screen}")
        if new_screen != "MAIN_MENU":
            logging.info("SUCCESS! The game has transitioned away from the Main Menu!")
            break
            
    env.close()

if __name__ == "__main__":
    test_start_only()