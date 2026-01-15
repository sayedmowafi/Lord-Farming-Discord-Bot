# Lord Farming Discord Bot

A Discord bot for organizing **Marvel Rivals** Lord Farming sessions with automatic matchmaking, team formation management, and an integrated warning system.

## Features

### Host Management
- **Session Creation** — Join a designated voice channel to create a new farming session
- **Custom Formations** — Configure team compositions (2-2-2, 3-3-6, or custom)
- **Session Controls** — Lock/unlock sessions, start/stop farming, end sessions
- **Warning System** — Issue manual warnings to players for rule violations

### Player Experience  
- **Role Verification** — Link your in-game name (IGN) and select available roles
- **Smart Queueing** — Join role-specific voice channels for automatic team matching
- **Character Selection** — Choose your character via DM with conflict detection
- **Flex Support** — Queue as flex to fill any needed role

### Automated Systems
- **Intelligent Matchmaking** — Auto-fill teams based on formation requirements using FIFO priority
- **Voice Management** — Automatic voice channel creation and player movement
- **Grace Period Warnings** — 3-minute grace period before issuing warnings for leaving team VC
- **Status Updates** — Real-time team status and missing role announcements

## Tech Stack

- **Python 3.8+**
- **discord.py** — Discord API wrapper
- **aiosqlite** — Async SQLite database operations
- **python-dotenv** — Environment variable management

## Project Structure

```
lord-farming-bot/
├── bot.py              # Main bot class and event handlers
├── commands.py         # Slash command definitions
├── config.py           # Configuration and constants
├── database.py         # Database operations (SQLite)
├── matchmaking.py      # Matchmaking engine logic
├── nickname_manager.py # Player nickname management
├── views.py            # Discord UI components (buttons, modals, selects)
├── error_handler.py    # Global error handling
├── run.py              # Entry point
├── requirements.txt    # Python dependencies
└── README.md
```

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/lord-farming-bot.git
cd lord-farming-bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file in the project root:
```env
BOT_TOKEN=your_discord_bot_token_here
DB_URL=lord_farming.db
LOG_LEVEL=INFO
```

### 4. Configure Discord IDs
Update `config.py` with your server's channel and role IDs:
```python
JOIN_TO_HOST_VC = 1234567890123456789
LORD_FARMING_CATEGORY = 1234567890123456789
SUPPORT_VC = 1234567890123456789
TANK_VC = 1234567890123456789
DPS_VC = 1234567890123456789
FLEX_VC = 1234567890123456789
VERIFIED_ROLE = 1234567890123456789
ANNOUNCEMENTS_CHANNEL = 1234567890123456789
LORD_FARMING_ROLE = 1234567890123456789
```

### 5. Run the Bot
```bash
python run.py
```

## Discord Server Setup

### Required Channels
| Channel | Type | Purpose |
|---------|------|---------|
| Join to Host | Voice | Hosts join here to create sessions |
| Lord Farming | Category | Parent category for session VCs |
| Support Queue | Voice | Support players queue here |
| Tank Queue | Voice | Tank players queue here |
| DPS Queue | Voice | DPS players queue here |
| Flex Queue | Voice | Flex players queue here |
| Announcements | Text | Bot posts missing role notifications |

### Required Roles
- **Verified** — Assigned to players who complete `/verify`
- **Lord Farming** — Mentioned when teams need players

### Bot Permissions
- Manage Channels
- Move Members
- Connect to Voice
- View Channels
- Send Messages
- Manage Nicknames

## Commands

### Player Commands
| Command | Description |
|---------|-------------|
| `/verify` | Link your IGN and set available roles |
| `/profile` | View your or another user's profile |
| `/status` | Check current session status |
| `/queue` | See who's waiting in the global queue |
| `/unlink` | Delete your profile data |
| `/help` | Show help information |

### Host Commands
| Command | Description |
|---------|-------------|
| `/host lock` | Lock/unlock the session |
| `/host end` | End the current session |
| `/warn @user` | Issue a manual warning |
| `/unassign @user` | Remove a player from their team |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/admin sessions` | List all active sessions |
| `/admin cleanup` | Force cleanup inactive sessions |

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Player profiles, IGN, roles, warning counts |
| `sessions` | Active farming sessions |
| `formation_requirements` | Team composition settings per session |
| `queue` | Players waiting for team assignment |
| `assignments` | Current team assignments |
| `warns` | Warning history |
| `voice_state` | Voice channel tracking for grace periods |

## How It Works

### Session Flow
1. **Host joins** "Join to Host" voice channel
2. **Bot DMs host** for character selection and team formation setup
3. **Voice channel created** for the session
4. **Players join** role queue voice channels
5. **Bot DMs players** for character selection
6. **Matchmaking engine** assigns players to teams based on formation
7. **Players moved** to session voice channel automatically
8. **Host starts farming** — warning system activates
9. **Session ends** — cleanup and data reset

### Warning System
- Players who leave their team voice channel during active farming receive a warning after a **3-minute grace period**
- **3 warnings** result in automatic removal from the session
- Hosts can issue manual warnings via `/warn` command

### Character Conflict Resolution
- Each team can only have **one of each character**
- Players are notified if their character is already taken
- They can leave and rejoin with a different character selection

## License

MIT License — Feel free to use and modify for your own Discord servers.
