import logging
from balatro_env import BalatroEnv
from balatro_actions import ACTION_MAPPING

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TestRoutine")

if __name__ == "__main__":
    logger.info("Initializing Balatro Environment...")
    env = BalatroEnv()
    
    obs, info = env.reset()
    state = info['raw_state']
    screen = state.get('current_screen', 'UNKNOWN')
    mask = info['action_mask']
    
    valid_actions = [ACTION_MAPPING[i] for i, valid in enumerate(mask) if valid]
    
    logger.info(f"Current Screen: {screen}")
    logger.info(f"Valid actions count: {len(valid_actions)}")
    logger.info(f"Valid actions: {valid_actions}")