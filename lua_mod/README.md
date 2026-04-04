# Balatro RL Exporter (Lua Mod)

This mod transforms the game **Balatro** into a fully functioning, headless-capable Reinforcement Learning (RL) environment. It seamlessly extracts the game state into JSON format and executes actions sent from an external Python RL agent without interrupting the game's internal UI animations or logic loops.

## 🏗️ Architecture (TCP Socket IPC)

The communication between the game (Lua) and the RL agent (Python) is completely decoupled using a high-speed, memory-level **TCP Socket connection** (default port 12345). This eliminates disk I/O wear and reduces synchronization latency to <1ms:
- **Server (Lua Mod):** Runs a non-blocking TCP server hooked into `love.update()`. It listens for incoming commands.
- **Client (Python Env):** Connects to the game, sends a command string, and is safely blocked until the Lua engine physically executes the action and returns the new game state as a JSON string.

## 🚀 Installation

1. Ensure you have [Steamodded](https://github.com/Steamodded/smods) installed.
2. Place the `rlexporter` folder into your `%AppData%\Balatro\Mods\` directory.
3. Launch the game. The console will display `[RL_MOD] TCP Socket Engine Hooked Successfully!`.

## 📂 File Structure

- `rlexporter.lua`: The main entry point. Hooks the TCP server polling into `love.update()`.
- `ipc_server.lua`: Manages the TCP Socket lifecycle, connection acceptance, and JSON payload routing.
- `state_extractor.lua`: Parses `G.STATE` and extracts critical variables (money, hand, jokers, blinds, shop).
- `card_extractor.lua`: Serializes complex Love2D `Card` objects into clean, RL-friendly dictionaries.
- `run_info_extractor.lua`: Extracts static deck information and poker hand levels.
- `action_executor.lua`: The core action engine. Uses an aggressive BFS memory search to trigger authentic UI events and bypasses animation locks.
- `logger.lua`: Centralized logging system.

## 🎮 Action Space Dictionary

The Python agent must send one of the following commands (space-separated) via the TCP Socket connection:

### Game Flow & Navigation
- `SELECT_BLIND <Small|Big|Boss>`: Selects the specified blind to start the round.
- `SKIP_BLIND <Small|Big|Boss>`: Skips the specified blind to claim its Tag reward.
- `CASH_OUT`: Clicks the "Cash Out" button at the round evaluation screen.
- `NEXT_ROUND`: Clicks the "Next Round" button to leave the shop.

### In-Game Micro-Management
- `PLAY <idx1> [idx2] ...`: Highlights and plays the specified cards from the hand (1-indexed, left-to-right). Example: `PLAY 1 3 5`
- `DISCARD <idx1> [idx2] ...`: Highlights and discards the specified cards.
- `SWAP_HAND <idx1> <idx2>`: Swaps the position of two cards in your hand.
- `SWAP_JOKER <idx1> <idx2>`: Swaps the position of two jokers.
- `USE_CONSUMABLE <idx> [target_idx1] ...`: Uses a consumable (Tarot/Planet). Optionally targets specific cards in hand.

### Shop Management
- `BUY_CARD <idx>`: Buys a standard card (Joker/Tarot/Planet) from the shop slots.
- `BUY_VOUCHER <idx>`: Redeems a voucher from the shop.
- `BUY_BOOSTER <idx>`: Purchases and opens a booster pack.
- `SELL_JOKER <idx>`: Sells a joker.
- `SELL_CONSUMABLE <idx>`: Sells a consumable.

### Booster Pack Interaction
- `SELECT_PACK_CARD <idx>`: Selects a specific card when a booster pack is opened.
- `SKIP_PACK`: Skips the current booster pack.

### Special & Debug Commands
- `GET_STATE`: Returns the current environment state without triggering any game actions (used for environment reset/heartbeat).
- `GET_RUN_INFO`: Returns static run information (deck state, poker hands).
- `SET_MONEY <amount>`: Instantly sets your current money to the specified amount for testing. Example: `SET_MONEY 500`

## 🛡️ Stability Features
- **Aggressive UI Search (BFS):** Bypasses mock-event crashes by scanning the global memory tree (`G.OVERLAY_MENU`, `G.ROOM`, `G.jiggle`) to locate and physically trigger real UI nodes.
- **Safe Fallbacks:** If a dynamic UI node is absent, the engine seamlessly routes to a safe mock fallback event (`G.FUNCS.use_card`).
- **State Validation:** Actions are strictly validated against `G.STATE` to prevent out-of-context commands.