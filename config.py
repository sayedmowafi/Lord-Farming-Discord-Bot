import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_URL = os.getenv('DB_URL', 'lord_farming.db')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Discord channel IDs - Replace these with your server's channel IDs
JOIN_TO_HOST_VC = 0000000000000000000  # Voice channel where hosts join to create sessions
LORD_FARMING_CATEGORY = 0000000000000000000  # Category where session VCs are created
SUPPORT_VC = 0000000000000000000  # Support queue voice channel
TANK_VC = 0000000000000000000  # Tank queue voice channel
DPS_VC = 0000000000000000000  # DPS queue voice channel
FLEX_VC = 0000000000000000000  # Flex queue voice channel
VERIFIED_ROLE = 0000000000000000000  # Role given to verified players
ANNOUNCEMENTS_CHANNEL = 0000000000000000000  # Channel for missing role announcements
LORD_FARMING_ROLE = 0000000000000000000  # Role to ping for missing players

# Role queue voice channels mapping
ROLE_VCS = {
    'support': SUPPORT_VC,
    'tank': TANK_VC,
    'dps': DPS_VC,
    'flex': FLEX_VC
}

# Warning system configuration
GRACE_PERIOD_MINUTES = 3  # Time to rejoin before warning
WARN_THRESHOLD = 3  # Auto-kick after this many warnings

# Rate limiting for voice moves
VOICE_MOVE_DELAY = 0.2  # 200ms between moves to avoid rate limits

# Marvel Rivals characters by role
CHARACTERS = {
    'dps': [
        'Spider-Man', 'Black Panther', 'Magik', 'Psylocke', 'Iron Man', 
        'Punisher', 'Winter Soldier', 'Star-Lord', 'Storm', 'Scarlet Witch',
        'Hawkeye', 'Black Widow', 'Wolverine', 'Squirrel Girl',
        'Moon Knight', 'Namor', 'Blade', 'Hela', 'Human Torch', 'Iron Fist', 
        'Mister Fantastic', 'Phoenix'
    ],
    'tank': [
        'Hulk', 'Captain America', 'Thor', 'Groot', 'Peni Parker',
        'Magneto', 'Emma Frost', 'Venom', 'Doctor Strange', 'The Thing'
    ],
    'support': [
        'Mantis', 'Luna Snow', 'Jeff the Land Shark', 'Rocket Raccoon',
        'Adam Warlock', 'Cloak & Dagger', 'Invisible Woman', 'Ultron', 'Loki'
    ]
}

# Formation presets for quick setup
FORMATION_PRESETS = {
    '2-2-2': {'support': 2, 'tank': 2, 'dps': 2},
    '3-3': {'support': 3, 'tank': 3, 'dps': 0},
    '6-dps': {'support': 0, 'tank': 0, 'dps': 6},
}
