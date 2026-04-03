# Balatro RL Exporter (Lua Mod)

This mod transforms the game **Balatro** into a fully functioning, headless-capable Reinforcement Learning (RL) environment. It seamlessly extracts the game state into JSON format and executes actions sent from an external Python RL agent without interrupting the game's internal UI animations or logic loops.

## 🏗️ Architecture (IPC Mechanism)

The communication between the game (Lua) and the RL agent (Python) is completely decoupled using high-speed File I/O:
- **Observation (Read):** The mod exports the current game state to `rl_observation.json` and `rl_run_info.json` at a fixed interval (e.g., 2Hz).
- **Action (Write):** The Python agent writes a command string to `rl_action.txt`. The Lua mod polls this file at a high frequency (e.g., 10Hz), executes the action via native engine hooks, and immediately deletes the file.

## 🚀 Installation

1. Ensure you have [Steamodded](https://github.com/Steamodded/smods) installed.
2. Place the `rlexporter` folder into your `%AppData%\Balatro\Mods\` directory.
3. Launch the game. The console will display `[RL_MOD] [SUCCESS] Full RL Environment Hooked!`.

## 📂 File Structure

- `rlexporter.lua`: The main entry point. Hooks into `love.update()` to dispatch state extraction and action polling.
- `state_extractor.lua`: Parses `G.STATE` and extracts critical variables (money, hand, jokers, blinds, shop).
- `card_extractor.lua`: Serializes complex Love2D `Card` objects into clean, RL-friendly dictionaries.
- `run_info_extractor.lua`: Extracts static deck information and poker hand levels.
- `action_executor.lua`: The core action engine. Uses an aggressive BFS memory search to trigger authentic UI events and bypasses animation locks.
- `logger.lua`: Centralized logging system (toggle `DEBUG_MODE` to false during training to save I/O overhead).

## 🎮 Action Space Dictionary

The Python agent must write one of the following commands (space-separated) to `rl_action.txt`:

### Game Flow & Navigation
- `SELECT_BLIND <Small|Big|Boss>`: Selects the specified blind to start the round.
- `SKIP_BLIND <Small|Big|Boss>`: Skips the specified blind to claim its Tag reward.
- `CASH_OUT`: Clicks the "Cash Out" button at the round evaluation screen.
- `NEXT_ROUND`: Clicks the "Next Round" button to leave the shop.

### In-Game Micro-Management
- `PLAY <idx1> [idx2] ...`: Highlights and plays the specified cards from the hand (1-indexed, left-to-right). Example: `PLAY 1 3 5`
- `DISCARD <idx1> [idx2] ...`: Highlights and discards the specified cards.
- `SWAP_HAND <idx1> <idx2>`: Swaps the position of two cards in your hand (useful for multiplier ordering).
- `SWAP_JOKER <idx1> <idx2>`: Swaps the position of two jokers (useful for Blueprint/Brainstorm optimization).
- `USE_CONSUMABLE <idx> [target_idx1] ...`: Uses a consumable (Tarot/Planet). Optionally targets specific cards in hand. Example: `USE_CONSUMABLE 1 2 4` (uses the 1st consumable on the 2nd and 4th cards in hand).

### Shop Management
- `BUY_CARD <idx>`: Buys a standard card (Joker/Tarot/Planet) from the shop slots.
- `BUY_VOUCHER <idx>`: Redeems a voucher from the shop.
- `BUY_BOOSTER <idx>`: Purchases and opens a booster pack.
- `SELL_JOKER <idx>`: Sells a joker from your joker area.
- `SELL_CONSUMABLE <idx>`: Sells a consumable from your consumable area.

### Booster Pack Interaction
- `SELECT_PACK_CARD <idx>`: Selects a specific card when a booster pack is opened.
- `SKIP_PACK`: Skips the current booster pack.

### Debug Commands (Dev Only)
- `SET_MONEY <amount>`: Instantly sets your current money to the specified amount for testing. Example: `SET_MONEY 500`

## 🛡️ Stability Features
- **Aggressive UI Search (BFS):** Bypasses mock-event crashes by scanning the global memory tree (`G.OVERLAY_MENU`, `G.ROOM`, `G.jiggle`) to locate and physically trigger real UI nodes.
- **Safe Fallbacks:** If a dynamic UI node (like a 3D pack card) is absent from the static UI tree, the engine seamlessly routes to a safe mock fallback event (`G.FUNCS.use_card`).
- **State Validation:** Actions are strictly validated against `G.STATE` to prevent the agent from triggering commands out of context.