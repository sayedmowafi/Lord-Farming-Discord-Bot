import asyncio
import logging
import time
from typing import Dict, List, Optional
from collections import defaultdict
import discord

import config

logger = logging.getLogger(__name__)


class MatchmakingEngine:
    """Handles matchmaking logic for Lord Farming sessions."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def process_session(self, session_id: str):
        """Process matchmaking for a specific session."""
        try:
            guild_id = await self.get_session_guild_id(session_id)
            if not guild_id:
                return
            
            session = await self.bot.db.get_active_session(guild_id)
            if not session or session['session_id'] != session_id:
                return
            
            if session['status'] in ['locked', 'ended', 'active']:
                return
            
            formations = await self.bot.db.get_formations(session_id)
            queue = await self.bot.db.get_queue(session_id)
            assignments = await self.bot.db.get_assignments(session_id)
            
            if not formations or not queue:
                return
            
            matches = await self.find_matches(formations, queue, assignments, guild_id)
            
            if matches:
                await self.execute_matches(session_id, matches, guild_id)
            
            await self.check_team_status(session_id, formations, assignments, guild_id)
            
        except Exception as e:
            logger.error(f"Error in matchmaking for session {session_id}: {e}")
    
    async def get_session_guild_id(self, session_id: str) -> Optional[int]:
        for guild in self.bot.guilds:
            session = await self.bot.db.get_active_session(guild.id)
            if session and session['session_id'] == session_id:
                return guild.id
        return None
    
    async def find_matches(self, formations: Dict, queue: List, assignments: Dict, guild_id: int) -> List[Dict]:
        """Find possible team assignments from queue with character conflict detection."""
        matches = []
        
        team_counts = {
            'A': {'support': 0, 'tank': 0, 'dps': 0},
            'B': {'support': 0, 'tank': 0, 'dps': 0}
        }
        
        team_characters = {
            'A': set(),
            'B': set()
        }
        
        for team in ['A', 'B']:
            for assignment in assignments.get(team, []):
                role = assignment['role']
                character = assignment.get('character')
                
                if role in team_counts[team]:
                    team_counts[team][role] += 1
                
                if character:
                    team_characters[team].add(character)
        
        queue_by_role = defaultdict(list)
        for player in sorted(queue, key=lambda p: p.get('joined_at', '')):
            queue_by_role[player['role']].append(player)
        
        for team in ['A', 'B']:
            formation = formations.get(team, {})
            
            for role in ['support', 'tank', 'dps']:
                needed = formation.get(role, 0) - team_counts[team][role]
                available = queue_by_role[role].copy()
                
                assigned_count = 0
                i = 0
                
                while assigned_count < needed and i < len(available):
                    player = available[i]
                    character = player.get('character')
                    
                    if character and character in team_characters[team]:
                        await self.notify_character_conflict(player, character, team, guild_id)
                        i += 1
                        continue
                    
                    matches.append({
                        'team': team,
                        'player': player,
                        'role': role
                    })
                    
                    team_counts[team][role] += 1
                    if character:
                        team_characters[team].add(character)
                    
                    for queue_role in queue_by_role:
                        queue_by_role[queue_role] = [p for p in queue_by_role[queue_role] if p['discord_id'] != player['discord_id']]
                    
                    assigned_count += 1
                    i += 1
        
        return matches
    
    async def execute_matches(self, session_id: str, matches: List[Dict], guild_id: int):
        """Execute the team assignments."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        session = await self.bot.db.get_active_session(guild_id)
        voice_channel = guild.get_channel(session['voice_channel_id']) if session else None
        
        for match in matches:
            player_data = match['player']
            team = match['team']
            role = match['role']
            
            success = await self.bot.db.assign_to_team(
                session_id, team, player_data['discord_id'], 
                role, player_data.get('character')
            )
            
            if success:
                await self.move_player_to_team_vc(
                    guild, player_data['discord_id'], voice_channel, team, role, session_id
                )
                
                await self.send_assignment_dm(
                    guild, player_data['discord_id'], team, role, 
                    player_data.get('character'), voice_channel
                )
        
        await self.update_status_message(session_id, guild)
    
    async def move_player_to_team_vc(self, guild: discord.Guild, user_id: int, 
                                   voice_channel: discord.VoiceChannel, team: str, role: str = None, session_id: str = None):
        """Move player to their team voice channel."""
        if not voice_channel:
            return
        
        member = guild.get_member(user_id)
        if not member:
            return
        
        try:
            await asyncio.sleep(config.VOICE_MOVE_DELAY)
            
            if member.voice and member.voice.channel:
                await member.move_to(voice_channel)
            else:
                embed = discord.Embed(
                    title="🎯 Join Your Team Voice Channel!",
                    description=f"You've been assigned to **Team {team}**!\n\nPlease join: **{voice_channel.name}**",
                    color=discord.Color.green()
                )
                try:
                    await member.send(embed=embed)
                except:
                    pass
            
            await self.bot.db.update_voice_state(user_id, voice_channel.id, session_id, team)
            
            if role:
                await self.bot.nickname_manager.set_team_nickname(member, role, team)
            
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to move {member.display_name}: {e}")
            session_data = await self.bot.db.get_active_session(guild.id)
            if session_data:
                await self.bot.db.unassign_from_team(session_data['session_id'], user_id)
        except Exception as e:
            logger.error(f"Error moving player {user_id}: {e}")
    
    async def send_assignment_dm(self, guild: discord.Guild, user_id: int, team: str, 
                               role: str, character: str, voice_channel: discord.VoiceChannel):
        member = guild.get_member(user_id)
        if not member:
            return
        
        embed = discord.Embed(
            title=f"🎯 Assigned to Team {team}!",
            description=f"**Role:** {role.title()}\n**Character:** {character}\n**Voice Channel:** {voice_channel.mention if voice_channel else 'N/A'}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Important",
            value="Stay in your team voice channel during the farming session. Leaving may result in warnings!",
            inline=False
        )
        
        try:
            await member.send(embed=embed)
        except:
            pass
    
    async def check_team_status(self, session_id: str, formations: Dict, 
                              assignments: Dict, guild_id: int):
        """Check team fill status and notify if full or missing roles."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        team_counts = {
            'A': {'support': 0, 'tank': 0, 'dps': 0, 'total': 0},
            'B': {'support': 0, 'tank': 0, 'dps': 0, 'total': 0}
        }
        
        for team in ['A', 'B']:
            for assignment in assignments.get(team, []):
                role = assignment['role']
                if role in team_counts[team]:
                    team_counts[team][role] += 1
                    team_counts[team]['total'] += 1
        
        total_players = team_counts['A']['total'] + team_counts['B']['total']
        
        if total_players == 12:
            await self.notify_teams_full(session_id, guild_id)
        else:
            await self.notify_missing_roles_with_queue(session_id, formations, team_counts, guild_id)
    
    async def notify_teams_full(self, session_id: str, guild_id: int):
        """Notify when teams are full."""
        guild = self.bot.get_guild(guild_id)
        session = await self.bot.db.get_active_session(guild_id)
        
        if not guild or not session:
            return
        
        host = guild.get_member(session['host_id'])
        if host:
            embed = discord.Embed(
                title="🎉 Teams Full!",
                description="Both teams have been filled (12/12 players). You can now start the Lord Farming session when ready!",
                color=discord.Color.gold()
            )
            
            view = discord.ui.View()
            start_button = discord.ui.Button(
                label="Start Farming Session",
                style=discord.ButtonStyle.success,
                emoji="🎮"
            )
            
            async def start_callback(interaction):
                await self.bot.db.update_session_status(session_id, 'active')
                await interaction.response.send_message("✅ Farming session started! Warning system is now active.", ephemeral=True)
            
            start_button.callback = start_callback
            view.add_item(start_button)
            
            try:
                await host.send(embed=embed, view=view)
            except:
                pass
    
    async def notify_missing_roles_with_queue(self, session_id: str, formations: Dict, 
                                            team_counts: Dict, guild_id: int):
        """Notify about missing roles accounting for queued players."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        if not await self.is_oldest_session(session_id, guild_id):
            return
        
        queue = await self.bot.db.get_queue(session_id)
        
        queue_counts = {'support': 0, 'tank': 0, 'dps': 0}
        for player in queue:
            role = player.get('role')
            if role in queue_counts:
                queue_counts[role] += 1
        
        missing_roles = []
        
        total_needed = {'support': 0, 'tank': 0, 'dps': 0}
        total_available = {'support': 0, 'tank': 0, 'dps': 0}
        
        for team in ['A', 'B']:
            formation = formations.get(team, {})
            counts = team_counts[team]
            
            for role in ['support', 'tank', 'dps']:
                needed = formation.get(role, 0)
                assigned = counts[role]
                
                total_needed[role] += needed
                total_available[role] += assigned
        
        for role in ['support', 'tank', 'dps']:
            total_available[role] += queue_counts[role]
            
            if total_available[role] < total_needed[role]:
                missing_count = total_needed[role] - total_available[role]
                missing_roles.append(f"{missing_count} {role.title()}")
        
        if missing_roles and len(missing_roles) <= 3:
            last_announcement = getattr(self.bot, '_last_announcement_time', 0)
            current_time = time.time()
            
            if current_time - last_announcement < 180:
                return
            
            announcements_channel = guild.get_channel(config.ANNOUNCEMENTS_CHANNEL)
            
            if announcements_channel:
                role_mention = f"<@&{config.LORD_FARMING_ROLE}>"
                
                embed = discord.Embed(
                    title="🔍 Lord Farming Needs Players!",
                    description=f"**Missing:** {', '.join(missing_roles)}",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="🎯 How to Join",
                    value="Join the appropriate role queue voice channel to get matched!",
                    inline=False
                )
                embed.add_field(
                    name="📋 Queue Channels",
                    value="• **Support Queue** - For healers\n• **Tank Queue** - For tanks\n• **DPS Queue** - For damage dealers\n• **Flex Queue** - Can play any role",
                    inline=False
                )
                embed.set_footer(text="First come, first served! Character conflicts resolved automatically.")
                
                try:
                    await announcements_channel.send(f"{role_mention}", embed=embed)
                    self.bot._last_announcement_time = current_time
                except:
                    pass
    
    async def is_oldest_session(self, session_id: str, guild_id: int) -> bool:
        try:
            session = await self.bot.db.get_active_session(guild_id)
            return session and session['session_id'] == session_id
        except:
            return True
    
    async def update_status_message(self, session_id: str, guild: discord.Guild):
        """Update permanent status message in voice channel."""
        session = await self.bot.db.get_active_session(guild.id)
        if not session:
            return
        
        voice_channel = guild.get_channel(session['voice_channel_id'])
        if not voice_channel:
            return
        
        embed = await self.generate_status_embed(session_id)
        
        status_message_id = getattr(self.bot, f'_status_message_{session_id}', None)
        status_message = None
        
        if status_message_id:
            try:
                status_message = await voice_channel.fetch_message(status_message_id)
            except:
                pass
        
        if status_message:
            try:
                await status_message.edit(embed=embed)
                return
            except:
                pass
        
        try:
            new_message = await voice_channel.send(embed=embed)
            setattr(self.bot, f'_status_message_{session_id}', new_message.id)
            
            try:
                await new_message.pin()
            except:
                pass
        except Exception as e:
            logger.error(f"Failed to send status message: {e}")
    
    async def generate_status_embed(self, session_id: str) -> discord.Embed:
        formations = await self.bot.db.get_formations(session_id)
        assignments = await self.bot.db.get_assignments(session_id)
        queue = await self.bot.db.get_queue(session_id)
        
        embed = discord.Embed(
            title="📊 Team Status",
            color=discord.Color.blue()
        )
        
        for team in ['A', 'B']:
            formation = formations.get(team, {})
            team_assignments = assignments.get(team, [])
            
            role_assignments = {'support': [], 'tank': [], 'dps': []}
            for assignment in team_assignments:
                role = assignment['role']
                if role in role_assignments:
                    role_assignments[role].append(assignment)
            
            team_lines = []
            
            for role in ['support', 'tank', 'dps']:
                needed = formation.get(role, 0)
                current = len(role_assignments[role])
                
                if needed > 0:
                    status = "✅" if current >= needed else "❌"
                    team_lines.append(f"{status} {role.title()}: {current}/{needed}")
                    
                    for assignment in role_assignments[role]:
                        character = assignment.get('character', 'Unknown')
                        user_id = assignment.get('discord_id')
                        user_profile = await self.bot.db.get_user(user_id) if user_id else None
                        display_name = user_profile.get('ign', 'Unknown') if user_profile else 'Unknown'
                        team_lines.append(f"  - {display_name} ({character})")
            
            team_text = "\n".join(team_lines) if team_lines else "No formation set"
            
            embed.add_field(
                name=f"**Team {team}**",
                value=team_text,
                inline=True
            )
        
        if queue:
            queue_by_role = defaultdict(int)
            for player in queue:
                queue_by_role[player['role']] += 1
            
            queue_text = []
            for role, count in queue_by_role.items():
                queue_text.append(f"{role.title()}: {count}")
            
            embed.add_field(
                name="Queue",
                value="\n".join(queue_text) if queue_text else "Empty",
                inline=False
            )
        
        embed.timestamp = discord.utils.utcnow()
        return embed
    
    async def notify_character_conflict(self, player_data: Dict, character: str, team: str, guild_id: int):
        """Notify player about character conflict preventing team assignment."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        member = guild.get_member(player_data['discord_id'])
        if not member:
            return
        
        notification_key = f"conflict_{player_data['discord_id']}_{character}"
        if hasattr(self.bot, '_conflict_notifications'):
            if notification_key in self.bot._conflict_notifications:
                return
        else:
            self.bot._conflict_notifications = set()
        
        self.bot._conflict_notifications.add(notification_key)
        
        embed = discord.Embed(
            title="⚠️ Character Conflict",
            description=f"**{character}** is already taken on Team {team}!\n\nYou'll be assigned to the other team when a slot opens, or you can leave and rejoin with a different character.",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="💡 Tip",
            value="Each team can only have one of each character to ensure diverse team compositions!",
            inline=False
        )
        
        try:
            await member.send(embed=embed)
        except:
            pass
