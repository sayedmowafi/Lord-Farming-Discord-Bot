import discord
from discord.ext import commands, tasks
import asyncio
import logging
import uuid
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

import config
from database import Database
from nickname_manager import NicknameManager

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True


class LordFarmingBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        self.db = Database(config.DB_URL)
        self.pending_grace_warnings = {}
        self.nickname_manager = NicknameManager(self)
    
    async def setup_hook(self):
        await self.db.initialize()
        
        try:
            await self.load_extension('commands')
        except Exception as e:
            logger.error(f"Failed to load commands cog: {e}")
        
        try:
            await self.load_extension('error_handler')
        except Exception as e:
            logger.error(f"Failed to load error handler: {e}")
        
        self.grace_period_monitor.start()
        self.matchmaking_monitor.start()
        self.session_timeout_monitor.start()
        
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        await self.recover_active_sessions()
    
    async def recover_active_sessions(self):
        """Recover active sessions after bot restart and cleanup orphaned sessions."""
        try:
            cleaned_count = 0
            recovered_count = 0
            
            for guild in self.guilds:
                session = await self.db.get_active_session(guild.id)
                if session:
                    if session['voice_channel_id']:
                        channel = guild.get_channel(session['voice_channel_id'])
                        if not channel:
                            await self.db.cleanup_session(session['session_id'])
                            cleaned_count += 1
                            continue
                        
                        if len(channel.members) == 0:
                            if not hasattr(self, '_empty_vc_timers'):
                                self._empty_vc_timers = {}
                            self._empty_vc_timers[session['session_id']] = discord.utils.utcnow()
                    else:
                        await self.db.cleanup_session(session['session_id'])
                        cleaned_count += 1
                        continue
                    
                    from matchmaking import MatchmakingEngine
                    matchmaker = MatchmakingEngine(self)
                    await matchmaker.update_status_message(session['session_id'], guild)
                    
                    host = guild.get_member(session['host_id'])
                    if host:
                        embed = discord.Embed(
                            title="🔄 Bot Reconnected",
                            description=f"Your Lord Farming session **{session['name']}** is still active and has been recovered.",
                            color=discord.Color.blue()
                        )
                        try:
                            await host.send(embed=embed)
                        except:
                            pass
                    
                    recovered_count += 1
            
            logger.info(f"Session recovery: {recovered_count} recovered, {cleaned_count} cleaned up")
        except Exception as e:
            logger.error(f"Error recovering sessions: {e}")
    
    @tasks.loop(seconds=30)
    async def grace_period_monitor(self):
        """Monitor grace periods and issue warnings when they expire."""
        pass
    
    @tasks.loop(seconds=15)
    async def matchmaking_monitor(self):
        """Periodically process matchmaking for active sessions."""
        try:
            from matchmaking import MatchmakingEngine
            matchmaker = MatchmakingEngine(self)
            
            for guild in self.guilds:
                session = await self.db.get_active_session(guild.id)
                if session and session['status'] == 'forming':
                    await matchmaker.process_session(session['session_id'])
        except Exception as e:
            logger.error(f"Error in matchmaking monitor: {e}")
    
    @tasks.loop(seconds=30)
    async def session_timeout_monitor(self):
        """Monitor sessions for empty voice channels and auto-cleanup."""
        try:
            for guild in self.guilds:
                session = await self.db.get_active_session(guild.id)
                if session and session['voice_channel_id']:
                    channel = guild.get_channel(session['voice_channel_id'])
                    
                    if not channel:
                        await self.db.cleanup_session(session['session_id'])
                        continue
                    
                    if len(channel.members) == 0:
                        session_id = session['session_id']
                        current_time = discord.utils.utcnow()
                        
                        if not hasattr(self, '_empty_vc_timers'):
                            self._empty_vc_timers = {}
                        
                        if session_id not in self._empty_vc_timers:
                            self._empty_vc_timers[session_id] = current_time
                        else:
                            empty_since = self._empty_vc_timers[session_id]
                            if (current_time - empty_since).total_seconds() >= 60:
                                await self.cleanup_empty_session(session, channel, guild)
                                del self._empty_vc_timers[session_id]
                    else:
                        if hasattr(self, '_empty_vc_timers') and session['session_id'] in self._empty_vc_timers:
                            del self._empty_vc_timers[session['session_id']]
        except Exception as e:
            logger.error(f"Error in session timeout monitor: {e}")
    
    async def cleanup_empty_session(self, session, channel, guild):
        """Cleanup an empty session after timeout."""
        try:
            host = guild.get_member(session['host_id'])
            if host:
                embed = discord.Embed(
                    title="⏰ Session Auto-Closed",
                    description=f"Your Lord Farming session **{session['name']}** was automatically closed because the voice channel was empty for more than 1 minute.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="💡 Tip",
                    value="Sessions are automatically cleaned up when no one is in the voice channel to keep things tidy!",
                    inline=False
                )
                try:
                    await host.send(embed=embed)
                except:
                    pass
            
            await channel.delete()
            await self.db.cleanup_session(session['session_id'])
        except Exception as e:
            logger.error(f"Error cleaning up empty session: {e}")
    
    async def on_voice_state_update(self, member, before, after):
        try:
            await self.handle_voice_state_change(member, before, after)
        except Exception as e:
            logger.error(f"Error handling voice state update: {e}")
    
    async def handle_voice_state_change(self, member, before, after):
        """Process voice state changes for host detection and player monitoring."""
        if after.channel and after.channel.id == config.JOIN_TO_HOST_VC:
            await self.handle_host_join(member)
        elif after.channel and after.channel.id in config.ROLE_VCS.values():
            await self.handle_player_queue_join(member, after.channel)
        elif before.channel and not after.channel:
            await self.handle_player_leave(member, before.channel)
        elif before.channel and after.channel and before.channel != after.channel:
            await self.handle_player_move(member, before.channel, after.channel)
    
    async def handle_host_join(self, member):
        """Handle when someone joins the Join to Host VC."""
        session = await self.db.get_active_session(member.guild.id)
        if session:
            if session['host_id'] == member.id:
                embed = discord.Embed(
                    title="Reconnected to Your Session",
                    description=f"Welcome back! Your session **{session['name']}** is still active.",
                    color=discord.Color.green()
                )
                await member.send(embed=embed)
                return
            else:
                embed = discord.Embed(
                    title="Session Already Active",
                    description="There's already an active Lord Farming session. Please wait for it to end.",
                    color=discord.Color.red()
                )
                await member.send(embed=embed)
                return
        
        session_id = str(uuid.uuid4())[:8]
        session_number = await self.get_next_session_number(member.guild.id)
        session_name = f"Lord Farming #{session_number}"
        
        success = await self.db.create_session(session_id, member.guild.id, member.id, session_name)
        if not success:
            embed = discord.Embed(
                title="Error",
                description="Failed to create session. Please try again.",
                color=discord.Color.red()
            )
            await member.send(embed=embed)
            return
        
        await self.send_host_character_selection_dm(member, session_id, session_name, member.guild.id)
        await self.process_global_queue(session_id, member.guild.id)
    
    async def get_next_session_number(self, guild_id: int) -> int:
        """Get the next sequential session number for this guild."""
        try:
            guild = self.get_guild(guild_id)
            if not guild:
                return 1
            
            category = guild.get_channel(config.LORD_FARMING_CATEGORY)
            if not category:
                return 1
            
            used_numbers = set()
            for channel in category.voice_channels:
                if channel.name.startswith("Lord Farming #"):
                    try:
                        number_part = channel.name.split("#")[1].strip()
                        number_str = number_part.split()[0]
                        number = int(number_str)
                        used_numbers.add(number)
                    except (IndexError, ValueError):
                        continue
            
            next_number = 1
            while next_number in used_numbers:
                next_number += 1
            
            return next_number
        except Exception as e:
            logger.error(f"Error getting next session number: {e}")
            return 1
    
    async def send_host_character_selection_dm(self, host, session_id: str, session_name: str, guild_id: int):
        """Send DM to host for character selection first."""
        user_profile = await self.db.get_user(host.id)
        if not user_profile:
            embed = discord.Embed(
                title="⚠️ Host Verification Required",
                description="You need to verify your account first! Use `/verify` command to set your IGN and available roles.",
                color=discord.Color.orange()
            )
            try:
                await host.send(embed=embed)
            except:
                pass
            return
        
        embed = discord.Embed(
            title="🎯 Host Character Selection",
            description=f"Welcome to {session_name}! As the host, you need to select your role and character first before setting up team formations.",
            color=discord.Color.purple()
        )
        
        from views import HostCharacterViewForSetup
        view = HostCharacterViewForSetup(self, session_id, session_name, guild_id, user_profile)
        try:
            await host.send(embed=embed, view=view)
        except:
            pass

    async def send_host_formation_dm(self, host, session_id: str, session_name: str, guild_id: int):
        """Send DM to host for setting up team formations."""
        embed = discord.Embed(
            title=f"🎮 {session_name} - Setup",
            description="Welcome to Lord Farming! Set up your team formations below.\n\n**Team A:** ❌ Not configured\n**Team B:** ❌ Not configured",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Instructions",
            value="• Set each team formation individually\n• Each team needs exactly 6 players\n• Teams can have different compositions\n• Use 'Quick 3-3-6 Setup' for standard formation",
            inline=False
        )
        
        view = HostFormationView(self, session_id, session_name, guild_id)
        await host.send(embed=embed, view=view)
    
    async def handle_player_queue_join(self, member, channel):
        """Handle when a player joins a role queue VC."""
        verified_role = member.guild.get_role(config.VERIFIED_ROLE)
        if not verified_role or verified_role not in member.roles:
            embed = discord.Embed(
                title="Verification Required",
                description="You need to verify your account first! Use `/verify` command.",
                color=discord.Color.red()
            )
            try:
                await member.send(embed=embed)
            except:
                pass
            
            try:
                await member.move_to(None)
            except:
                pass
            return
        
        user = await self.db.get_user(member.id)
        if not user:
            embed = discord.Embed(
                title="Profile Not Found",
                description="Please use `/verify` command to set up your profile first.",
                color=discord.Color.red()
            )
            try:
                await member.send(embed=embed)
            except:
                pass
            return
        
        role = None
        for role_name, channel_id in config.ROLE_VCS.items():
            if channel.id == channel_id:
                role = role_name
                break
        
        if not role:
            return
        
        if role != 'flex' and role not in user['roles']:
            embed = discord.Embed(
                title="Role Not Available",
                description=f"You haven't verified the {role.title()} role. Use `/verify` to update your roles.",
                color=discord.Color.red()
            )
            try:
                await member.send(embed=embed)
            except:
                pass
            return
        
        await self.nickname_manager.update_user_nickname(member, role, joining=True)
        await self.send_player_character_dm(member, None, role, user)
    
    async def add_to_global_queue_with_character(self, member, role: str, character: str, user: dict):
        """Add player to global queue with character selection when no session is active."""
        if not hasattr(self, '_global_queue'):
            self._global_queue = []
        
        self._global_queue = [p for p in self._global_queue if p['discord_id'] != member.id]
        
        self._global_queue.append({
            'discord_id': member.id,
            'guild_id': member.guild.id,
            'role': role,
            'character': character,
            'user_profile': user,
            'timestamp': discord.utils.utcnow()
        })
    
    async def process_global_queue(self, session_id: str, guild_id: int):
        """Process global queue when a new session is created."""
        if not hasattr(self, '_global_queue'):
            return
        
        guild = self.get_guild(guild_id)
        if not guild:
            return
        
        guild_players = [p for p in self._global_queue if p['guild_id'] == guild_id]
        
        if not guild_players:
            return
        
        for player_data in guild_players:
            member = guild.get_member(player_data['discord_id'])
            if member:
                if 'character' in player_data:
                    success = await self.db.add_to_queue(
                        session_id, 
                        player_data['discord_id'], 
                        player_data['role'], 
                        player_data['character']
                    )
                    
                    if success:
                        embed = discord.Embed(
                            title="🎮 Session Started!",
                            description=f"You've been added to the Lord Farming session as **{player_data['role'].title()}** playing **{player_data['character']}**!",
                            color=discord.Color.green()
                        )
                        try:
                            await member.send(embed=embed)
                        except:
                            pass
                else:
                    await self.send_player_character_dm(
                        member, 
                        session_id, 
                        player_data['role'], 
                        player_data['user_profile']
                    )
        
        self._global_queue = [p for p in self._global_queue if p['guild_id'] != guild_id]
    
    async def remove_from_global_queue(self, discord_id: int):
        """Remove player from global queue when they leave."""
        if not hasattr(self, '_global_queue'):
            return
        
        self._global_queue = [p for p in self._global_queue if p['discord_id'] != discord_id]
    
    async def send_player_character_dm(self, player, session_id: str, role: str, user: dict):
        """Send DM to player for character selection with queue status."""
        session = await self.db.get_active_session(player.guild.id) if session_id is None else {'session_id': session_id}
        actual_session_id = session['session_id'] if session else None
        
        queue_info = await self.get_queue_status(actual_session_id, role) if actual_session_id else None
        suggestions = await self.get_character_suggestions(actual_session_id, role) if actual_session_id else None
        
        if session_id is None and not session:
            embed = discord.Embed(
                title="🎯 Join Lord Farming Queue",
                description=f"Joining as **{role.title()}**\nSelect your character:",
                color=discord.Color.blue()
            )
        else:
            description = f"Joining as **{role.title()}**\nSelect your character:"
            
            if queue_info:
                description += f"\n\n📊 **Queue Status:**\n{queue_info}"
            
            if suggestions:
                description += f"\n\n💡 **Smart Suggestions:**\n{suggestions}"
            
            embed = discord.Embed(
                title="🎯 Join Lord Farming",
                description=description,
                color=discord.Color.green()
            )
        
        view = PlayerCharacterView(self, actual_session_id, role, user)
        await player.send(embed=embed, view=view)
    
    async def get_queue_status(self, session_id: str, role: str) -> str:
        """Get queue status for a specific role in a session."""
        try:
            queue = await self.db.get_queue(session_id)
            formations = await self.db.get_formations(session_id)
            assignments = await self.db.get_assignments(session_id)
            
            if not formations:
                return "No team formations set yet."
            
            total_needed = 0
            for team in ['A', 'B']:
                formation = formations.get(team, {})
                total_needed += formation.get(role, 0)
            
            assigned_count = 0
            for team in ['A', 'B']:
                for assignment in assignments.get(team, []):
                    if assignment['role'] == role:
                        assigned_count += 1
            
            queued_count = 0
            for player in queue:
                if player['role'] == role:
                    queued_count += 1
            
            remaining_spots = total_needed - assigned_count
            
            if remaining_spots <= 0:
                return f"All {role.title()} spots filled! Consider switching roles."
            
            if queued_count == 0:
                wait_estimate = "Instant match likely!"
            elif queued_count <= remaining_spots:
                wait_estimate = "Quick match expected!"
            else:
                wait_estimate = f"~{(queued_count - remaining_spots + 1) * 30}s wait estimated"
            
            return f"Position: #{queued_count + 1} • Spots left: {remaining_spots} • {wait_estimate}"
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return "Queue status unavailable"
    
    async def get_character_suggestions(self, session_id: str, role: str) -> str:
        """Get smart character suggestions to avoid conflicts."""
        try:
            assignments = await self.db.get_assignments(session_id)
            queue = await self.db.get_queue(session_id)
            
            taken_characters = set()
            
            for team in ['A', 'B']:
                for assignment in assignments.get(team, []):
                    if assignment['role'] == role and assignment.get('character'):
                        taken_characters.add(assignment['character'])
            
            for player in queue:
                if player['role'] == role and player.get('character'):
                    taken_characters.add(player['character'])
            
            all_characters = config.CHARACTERS.get(role, [])
            available_characters = [char for char in all_characters if char not in taken_characters]
            
            if not taken_characters:
                return f"Any {role.title()} character is fine! First to join."
            
            if len(available_characters) == 0:
                return f"All {role.title()} characters taken! Consider switching roles for instant queue."
            
            suggestions = available_characters[:3]
            suggestion_text = ", ".join(suggestions)
            
            if len(available_characters) > 3:
                suggestion_text += f" (and {len(available_characters) - 3} more)"
            
            taken_text = ", ".join(list(taken_characters)[:3])
            if len(taken_characters) > 3:
                taken_text += f" (+{len(taken_characters) - 3} more)"
            
            return f"🚫 Taken: {taken_text}\n✅ Available: {suggestion_text}"
        except Exception as e:
            logger.error(f"Error getting character suggestions: {e}")
            return "Suggestions unavailable"
    
    async def handle_player_leave(self, member, left_channel):
        """Handle when a player leaves a voice channel."""
        voice_state = await self.db.get_voice_state(member.id)
        if not voice_state or not voice_state['session_id']:
            await self.nickname_manager.reset_nickname(member)
            await self.remove_from_global_queue(member.id)
            return
        
        session = await self.db.get_active_session(member.guild.id)
        if not session or session['session_id'] != voice_state['session_id']:
            await self.nickname_manager.reset_nickname(member)
            return
        
        if left_channel and left_channel.id == session.get('voice_channel_id'):
            if session['status'] == 'active':
                await self.start_grace_period(member, voice_state, session)
    
    async def handle_player_move(self, member, old_channel, new_channel):
        """Handle when a player moves between voice channels."""
        await self.db.update_voice_state(member.id, new_channel.id)
        
        voice_state = await self.db.get_voice_state(member.id)
        if voice_state and voice_state['grace_until']:
            session = await self.db.get_active_session(member.guild.id)
            if session and session['voice_channel_id'] == new_channel.id:
                await self.db.clear_grace_period(member.id)
                
                embed = discord.Embed(
                    title="Grace Period Cleared",
                    description="Welcome back! Your warning has been cancelled.",
                    color=discord.Color.green()
                )
                try:
                    await member.send(embed=embed)
                except:
                    pass
    
    async def start_grace_period(self, member, voice_state, session):
        """Start grace period for a player who left their team VC."""
        await self.db.set_grace_period(member.id, config.GRACE_PERIOD_MINUTES)
        
        embed = discord.Embed(
            title="⚠️ Warning: Rejoin Required",
            description=f"You left your team voice channel **{session['name']}**!\n\nPlease rejoin within **{config.GRACE_PERIOD_MINUTES} minutes** or you'll receive a warning.",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="🎯 What to do",
            value=f"Rejoin the voice channel: **{session['name']}**",
            inline=False
        )
        embed.add_field(
            name="⏰ Time Remaining", 
            value=f"**{config.GRACE_PERIOD_MINUTES} minutes**",
            inline=True
        )
        embed.add_field(
            name="❌ What happens if you don't rejoin",
            value="You'll receive a warning and may be kicked from the session",
            inline=False
        )
        
        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass
        
        asyncio.create_task(self.schedule_grace_period_check(member.id, session['session_id']))
    
    async def schedule_grace_period_check(self, discord_id: int, session_id: str):
        """Schedule the grace period expiration check."""
        try:
            await asyncio.sleep(config.GRACE_PERIOD_MINUTES * 60)
            await self.check_grace_period_expired(discord_id, session_id)
        except Exception as e:
            logger.error(f"Error in grace period check for {discord_id}: {e}")
    
    async def check_grace_period_expired(self, discord_id: int, session_id: str):
        """Check if grace period has expired and issue warning."""
        voice_state = await self.db.get_voice_state(discord_id)
        if not voice_state or not voice_state['grace_until']:
            return
        
        await self.db.add_warn(session_id, discord_id, "Left team voice channel", "auto")
        await self.db.clear_grace_period(discord_id)
        
        warns = await self.db.get_session_warns(session_id, discord_id)
        
        guild = None
        for g in self.guilds:
            session = await self.db.get_active_session(g.id)
            if session and session['session_id'] == session_id:
                guild = g
                break
        
        member = guild.get_member(discord_id) if guild else None
        
        if warns >= config.WARN_THRESHOLD:
            embed = discord.Embed(
                title="🚫 Kicked from Session",
                description=f"You've reached the warning limit ({config.WARN_THRESHOLD}) and have been removed from the Lord Farming session.",
                color=discord.Color.red()
            )
            
            await self.db.unassign_from_team(session_id, discord_id)
            await self.db.update_voice_state(discord_id, None, None, None)
        else:
            embed = discord.Embed(
                title="⚠️ Warning Issued",
                description=f"You received a warning for leaving your team VC.\nWarnings: {warns}/{config.WARN_THRESHOLD}",
                color=discord.Color.red()
            )
        
        try:
            if member:
                await member.send(embed=embed)
        except:
            pass


from views import HostFormationView, PlayerCharacterView

bot = LordFarmingBot()

if __name__ == "__main__":
    bot.run(config.BOT_TOKEN)
