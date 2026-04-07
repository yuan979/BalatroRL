import logging
import time
import numpy as np
from balatro_env import BalatroEnv
from balatro_actions import ACTION_MAPPING  # 直接导入字典

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("RandomAgent")

def run_stress_test(max_steps=500):
    logger.info("Initializing Balatro Environment for Stress Test...")
    env = BalatroEnv()
    
    obs, info = env.reset()
    
    total_reward = 0.0
    episodes = 1
    
    start_time = time.time()
    
    for step in range(1, max_steps + 1):
        # 1. 获取当前合法的动作掩码
        action_mask = info.get("action_mask", np.ones(env.action_space.n, dtype=bool))
        
        # 找出所有合法的动作索引
        valid_actions = np.where(action_mask)[0]
        
        if len(valid_actions) == 0:
            logger.error(f"Step {step}: DEADLOCK! No valid actions available. Screen: {info['raw_state'].get('current_screen')}")
            break
            
        # 2. 随机选择一个合法的动作
        action = np.random.choice(valid_actions)
        
        # 使用字典获取动作的字符串名称
        action_name = ACTION_MAPPING.get(action, "")
        
        # 针对盲注界面的 UI 延迟做特殊处理（复用我们之前的经验）
        screen = info["raw_state"].get("current_screen")
        if screen == "BLIND_SELECT" and "SELECT_BLIND" in action_name:
            time.sleep(1.5) # 必须等 UI 渲染
            
        # 3. 执行动作
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        
        macro_actions = ["START_NEW_RUN", "CASH_OUT", "NEXT_ROUND", "SKIP_PACK"]
        if action_name in macro_actions or "BLIND" in action_name or "PACK_CARD" in action_name:
            time.sleep(1.5)

        # 每 50 步打印一次进度和性能
        if step % 50 == 0:
            elapsed = time.time() - start_time
            sps = step / elapsed # Steps Per Second (SPS)
            logger.info(f"Step {step}/{max_steps} | SPS: {sps:.2f} | Current Reward: {total_reward:.2f} | Screen: {info['raw_state'].get('current_screen')}")
            
        # 4. 处理游戏结束 (重置环境)
        if terminated or truncated:
            logger.info(f"--- Episode {episodes} Finished. Total Reward: {total_reward:.2f} ---")
            obs, info = env.reset()
            total_reward = 0.0
            episodes += 1
            # 给引擎一点重置动画的时间
            time.sleep(2.0)

    elapsed = time.time() - start_time
    logger.info(f"Stress test completed. Total steps: {max_steps}. Average SPS: {max_steps/elapsed:.2f}")
    env.close()

if __name__ == "__main__":
    # 为了防止意外死循环，我们先测 500 步
    run_stress_test(max_steps=500)