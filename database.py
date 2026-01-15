import aiosqlite
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def initialize(self):
        """Initialize the database with all required tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    discord_id INTEGER PRIMARY KEY,
                    ign TEXT NOT NULL,
                    roles TEXT NOT NULL,
                    warns_total INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    host_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT DEFAULT 'forming',
                    voice_channel_id INTEGER,
                    rules_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS formation_requirements (
                    session_id TEXT,
                    team TEXT,
                    support INTEGER DEFAULT 0,
                    tank INTEGER DEFAULT 0,
                    dps INTEGER DEFAULT 0,
                    note TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                    PRIMARY KEY (session_id, team)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS queue (
                    session_id TEXT,
                    discord_id INTEGER,
                    role TEXT NOT NULL,
                    character TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                    PRIMARY KEY (session_id, discord_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS assignments (
                    session_id TEXT,
                    team TEXT,
                    discord_id INTEGER,
                    role TEXT NOT NULL,
                    character TEXT,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id),
                    PRIMARY KEY (session_id, discord_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    discord_id INTEGER,
                    reason TEXT NOT NULL,
                    source TEXT DEFAULT 'auto',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voice_state (
                    discord_id INTEGER PRIMARY KEY,
                    current_channel_id INTEGER,
                    session_id TEXT,
                    team TEXT,
                    grace_until TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
    
    async def create_user(self, discord_id: int, ign: str, roles: List[str]) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO users (discord_id, ign, roles)
                    VALUES (?, ?, ?)
                ''', (discord_id, ign, json.dumps(roles)))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error creating user {discord_id}: {e}")
            return False
    
    async def get_user(self, discord_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT discord_id, ign, roles, warns_total FROM users WHERE discord_id = ?',
                    (discord_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'discord_id': row[0],
                            'ign': row[1],
                            'roles': json.loads(row[2]),
                            'warns_total': row[3]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting user {discord_id}: {e}")
            return None
    
    async def create_session(self, session_id: str, guild_id: int, host_id: int, name: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO sessions (session_id, guild_id, host_id, name, status)
                    VALUES (?, ?, ?, ?, 'forming')
                ''', (session_id, guild_id, host_id, name))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return False
    
    async def get_active_session(self, guild_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT session_id, guild_id, host_id, name, status, voice_channel_id, rules_json
                    FROM sessions 
                    WHERE guild_id = ? AND status IN ('forming', 'locked', 'active')
                    ORDER BY created_at DESC LIMIT 1
                ''', (guild_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'session_id': row[0],
                            'guild_id': row[1],
                            'host_id': row[2],
                            'name': row[3],
                            'status': row[4],
                            'voice_channel_id': row[5],
                            'rules_json': json.loads(row[6]) if row[6] else {}
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting active session for guild {guild_id}: {e}")
            return None
    
    async def update_session_status(self, session_id: str, status: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'UPDATE sessions SET status = ? WHERE session_id = ?',
                    (status, session_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating session {session_id} status: {e}")
            return False
    
    async def update_session_voice_channel(self, session_id: str, channel_id: int) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'UPDATE sessions SET voice_channel_id = ? WHERE session_id = ?',
                    (channel_id, session_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating session {session_id} voice channel: {e}")
            return False
    
    async def set_formation(self, session_id: str, team: str, support: int, tank: int, dps: int, note: str = None) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO formation_requirements 
                    (session_id, team, support, tank, dps, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (session_id, team, support, tank, dps, note))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting formation for {session_id} team {team}: {e}")
            return False
    
    async def get_formations(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        try:
            formations = {}
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT team, support, tank, dps, note
                    FROM formation_requirements WHERE session_id = ?
                ''', (session_id,)) as cursor:
                    async for row in cursor:
                        formations[row[0]] = {
                            'support': row[1],
                            'tank': row[2],
                            'dps': row[3],
                            'note': row[4]
                        }
            return formations
        except Exception as e:
            logger.error(f"Error getting formations for {session_id}: {e}")
            return {}
    
    async def add_to_queue(self, session_id: str, discord_id: int, role: str, character: str = None) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO queue (session_id, discord_id, role, character)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, discord_id, role, character))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding {discord_id} to queue: {e}")
            return False
    
    async def remove_from_queue(self, session_id: str, discord_id: int) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'DELETE FROM queue WHERE session_id = ? AND discord_id = ?',
                    (session_id, discord_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing {discord_id} from queue: {e}")
            return False
    
    async def get_queue(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            queue = []
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT discord_id, role, character, joined_at
                    FROM queue WHERE session_id = ?
                    ORDER BY joined_at ASC
                ''', (session_id,)) as cursor:
                    async for row in cursor:
                        queue.append({
                            'discord_id': row[0],
                            'role': row[1],
                            'character': row[2],
                            'joined_at': row[3]
                        })
            return queue
        except Exception as e:
            logger.error(f"Error getting queue for {session_id}: {e}")
            return []
    
    async def assign_to_team(self, session_id: str, team: str, discord_id: int, role: str, character: str = None) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO assignments (session_id, team, discord_id, role, character)
                    VALUES (?, ?, ?, ?, ?)
                ''', (session_id, team, discord_id, role, character))
                
                await db.execute(
                    'DELETE FROM queue WHERE session_id = ? AND discord_id = ?',
                    (session_id, discord_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error assigning {discord_id} to team {team}: {e}")
            return False
    
    async def get_assignments(self, session_id: str) -> Dict[str, List[Dict[str, Any]]]:
        try:
            assignments = {'A': [], 'B': []}
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT team, discord_id, role, character, assigned_at
                    FROM assignments WHERE session_id = ?
                    ORDER BY assigned_at ASC
                ''', (session_id,)) as cursor:
                    async for row in cursor:
                        assignments[row[0]].append({
                            'discord_id': row[1],
                            'role': row[2],
                            'character': row[3],
                            'assigned_at': row[4]
                        })
            return assignments
        except Exception as e:
            logger.error(f"Error getting assignments for {session_id}: {e}")
            return {'A': [], 'B': []}
    
    async def unassign_from_team(self, session_id: str, discord_id: int) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'DELETE FROM assignments WHERE session_id = ? AND discord_id = ?',
                    (session_id, discord_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error unassigning {discord_id}: {e}")
            return False
    
    async def add_warn(self, session_id: str, discord_id: int, reason: str, source: str = 'auto') -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO warns (session_id, discord_id, reason, source)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, discord_id, reason, source))
                
                await db.execute(
                    'UPDATE users SET warns_total = warns_total + 1 WHERE discord_id = ?',
                    (discord_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding warn for {discord_id}: {e}")
            return False
    
    async def get_session_warns(self, session_id: str, discord_id: int) -> int:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    'SELECT COUNT(*) FROM warns WHERE session_id = ? AND discord_id = ?',
                    (session_id, discord_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting session warns for {discord_id}: {e}")
            return 0
    
    async def update_voice_state(self, discord_id: int, channel_id: int = None, session_id: str = None, team: str = None) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO voice_state 
                    (discord_id, current_channel_id, session_id, team, last_seen_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (discord_id, channel_id, session_id, team))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating voice state for {discord_id}: {e}")
            return False
    
    async def set_grace_period(self, discord_id: int, minutes: int) -> bool:
        try:
            grace_until = datetime.now() + timedelta(minutes=minutes)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'UPDATE voice_state SET grace_until = ? WHERE discord_id = ?',
                    (grace_until.isoformat(), discord_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting grace period for {discord_id}: {e}")
            return False
    
    async def clear_grace_period(self, discord_id: int) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'UPDATE voice_state SET grace_until = NULL WHERE discord_id = ?',
                    (discord_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error clearing grace period for {discord_id}: {e}")
            return False
    
    async def get_voice_state(self, discord_id: int) -> Optional[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('''
                    SELECT discord_id, current_channel_id, session_id, team, grace_until
                    FROM voice_state WHERE discord_id = ?
                ''', (discord_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'discord_id': row[0],
                            'current_channel_id': row[1],
                            'session_id': row[2],
                            'team': row[3],
                            'grace_until': row[4]
                        }
                    return None
        except Exception as e:
            logger.error(f"Error getting voice state for {discord_id}: {e}")
            return None
    
    async def cleanup_session(self, session_id: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'UPDATE sessions SET status = "ended" WHERE session_id = ?',
                    (session_id,)
                )
                
                await db.execute(
                    'DELETE FROM queue WHERE session_id = ?',
                    (session_id,)
                )
                
                await db.execute(
                    'DELETE FROM assignments WHERE session_id = ?',
                    (session_id,)
                )
                
                await db.execute(
                    'UPDATE voice_state SET session_id = NULL, team = NULL, grace_until = NULL WHERE session_id = ?',
                    (session_id,)
                )
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
            return False
