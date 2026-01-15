import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
import logging

import config
from matchmaking import MatchmakingEngine
from nickname_manager import NicknameManager

logger = logging.getLogger(__name__)


class LordFarmingCommands(commands.Cog):
    """Slash commands for Lord Farming bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.nickname_manager = NicknameManager(bot)
    
    @app_commands.command(name="verify", description="Link your IGN and set your available roles")
    @app_commands.describe(
        ign="Your in-game name for Marvel Rivals",
        support="Can you play Support roles?",
        tank="Can you play Tank roles?", 
        dps="Can you play DPS roles?"
    )
    async def verify(
        self, 
        interaction: discord.Interaction,
        ign: str,
        support: bool = False,
        tank: bool = False,
        dps: bool = False
    ):
        if not any([support, tank, dps]):
            embed = discord.Embed(
                title="❌ Error",
                description="You must select at least one role!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        roles = []
        if support:
            roles.append('support')
        if tank:
            roles.append('tank')
        if dps:
            roles.append('dps')
        
        success = await self.bot.db.create_user(interaction.user.id, ign, roles)
        
        if success:
            verified_role = interaction.guild.get_role(config.VERIFIED_ROLE)
            if verified_role:
                try:
                    await interaction.user.add_roles(verified_role)
                except Exception as e:
                    logger.error(f"Failed to add verified role: {e}")
            
            await self.nickname_manager.set_default_nickname_on_verify(interaction.user, ign)
            
            embed = discord.Embed(
                title="✅ Verification Complete!",
                description=f"**IGN:** {ign}\n**Roles:** {', '.join(role.title() for role in roles)}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Next Steps",
                value="You can now join role queues to participate in Lord Farming!",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to save your profile. Please try again.",
                color=discord.Color.red()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="status", description="Show current session status and team formations")
    async def status(self, interaction: discord.Interaction):
        session = await self.bot.db.get_active_session(interaction.guild.id)
        
        if not session:
            embed = discord.Embed(
                title="No Active Session",
                description="There's no active Lord Farming session right now.",
                color=discord.Color.grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        matchmaker = MatchmakingEngine(self.bot)
        embed = await matchmaker.generate_status_embed(session['session_id'])
        
        host = interaction.guild.get_member(session['host_id'])
        embed.add_field(
            name="Session Info",
            value=f"**Host:** {host.mention if host else 'Unknown'}\n**Status:** {session['status'].title()}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    host_group = app_commands.Group(name="host", description="Host commands for Lord Farming")
    
    @host_group.command(name="lock", description="Lock the session to prevent new joins")
    async def host_lock(self, interaction: discord.Interaction):
        session = await self.bot.db.get_active_session(interaction.guild.id)
        
        if not session:
            embed = discord.Embed(
                title="❌ No Active Session",
                description="There's no active session to lock.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if session['host_id'] != interaction.user.id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Only the session host can lock the session.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        new_status = 'locked' if session['status'] == 'forming' else 'forming'
        await self.bot.db.update_session_status(session['session_id'], new_status)
        
        embed = discord.Embed(
            title=f"🔒 Session {'Locked' if new_status == 'locked' else 'Unlocked'}",
            description=f"Session is now {'locked' if new_status == 'locked' else 'open for new players'}.",
            color=discord.Color.orange() if new_status == 'locked' else discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @host_group.command(name="end", description="End the current session and cleanup")
    async def host_end(self, interaction: discord.Interaction):
        session = await self.bot.db.get_active_session(interaction.guild.id)
        
        if not session:
            embed = discord.Embed(
                title="❌ No Active Session",
                description="There's no active session to end.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if session['host_id'] != interaction.user.id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Only the session host can end the session.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if session['voice_channel_id']:
            channel = interaction.guild.get_channel(session['voice_channel_id'])
            if channel:
                try:
                    await channel.delete()
                except:
                    pass
        
        assignments = await self.bot.db.get_assignments(session['session_id'])
        for team in ['A', 'B']:
            for assignment in assignments.get(team, []):
                member = interaction.guild.get_member(assignment['discord_id'])
                if member:
                    await self.nickname_manager.reset_nickname(member)
        
        await self.bot.db.cleanup_session(session['session_id'])
        
        if hasattr(self.bot, '_conflict_notifications'):
            self.bot._conflict_notifications.clear()
        
        embed = discord.Embed(
            title="🛑 Session Ended",
            description="The Lord Farming session has been ended and cleaned up.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="warn", description="Issue a manual warning to a player")
    @app_commands.describe(
        user="The user to warn",
        reason="Reason for the warning"
    )
    async def warn(
        self, 
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str
    ):
        session = await self.bot.db.get_active_session(interaction.guild.id)
        
        if not session:
            embed = discord.Embed(
                title="❌ No Active Session",
                description="There's no active session to issue warnings for.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if session['host_id'] != interaction.user.id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Only the session host can issue warnings.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        success = await self.bot.db.add_warn(session['session_id'], user.id, reason, 'manual')
        
        if not success:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to issue warning. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        warns = await self.bot.db.get_session_warns(session['session_id'], user.id)
        
        if warns >= config.WARN_THRESHOLD:
            await self.bot.db.unassign_from_team(session['session_id'], user.id)
            await self.bot.db.update_voice_state(user.id, None, None, None)
            
            try:
                user_embed = discord.Embed(
                    title="🚫 Kicked from Session",
                    description=f"You've been kicked from the Lord Farming session.\n**Reason:** {reason}\n**Warnings:** {warns}/{config.WARN_THRESHOLD}",
                    color=discord.Color.red()
                )
                await user.send(embed=user_embed)
            except:
                pass
            
            embed = discord.Embed(
                title="🚫 User Kicked",
                description=f"{user.mention} has been kicked from the session (reached warning limit).",
                color=discord.Color.red()
            )
        else:
            try:
                user_embed = discord.Embed(
                    title="⚠️ Warning Issued",
                    description=f"You received a warning from the session host.\n**Reason:** {reason}\n**Warnings:** {warns}/{config.WARN_THRESHOLD}",
                    color=discord.Color.orange()
                )
                await user.send(embed=user_embed)
            except:
                pass
            
            embed = discord.Embed(
                title="⚠️ Warning Issued",
                description=f"Warning issued to {user.mention}.\n**Reason:** {reason}\n**Warnings:** {warns}/{config.WARN_THRESHOLD}",
                color=discord.Color.orange()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="unassign", description="Remove a player from their team assignment")
    @app_commands.describe(user="The user to unassign from their team")
    async def unassign(self, interaction: discord.Interaction, user: discord.Member):
        session = await self.bot.db.get_active_session(interaction.guild.id)
        
        if not session:
            embed = discord.Embed(
                title="❌ No Active Session",
                description="There's no active session.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if session['host_id'] != interaction.user.id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Only the session host can unassign players.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        success = await self.bot.db.unassign_from_team(session['session_id'], user.id)
        
        if success:
            await self.bot.db.update_voice_state(user.id, None, None, None)
            
            try:
                user_embed = discord.Embed(
                    title="📤 Unassigned from Team",
                    description="You've been unassigned from your team. You can rejoin the queue if needed.",
                    color=discord.Color.blue()
                )
                await user.send(embed=user_embed)
            except:
                pass
            
            embed = discord.Embed(
                title="✅ Player Unassigned",
                description=f"{user.mention} has been unassigned from their team.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to unassign player. They might not be assigned to a team.",
                color=discord.Color.red()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="profile", description="View your or another user's profile")
    @app_commands.describe(user="User to view profile for (optional)")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target_user = user or interaction.user
        
        profile = await self.bot.db.get_user(target_user.id)
        
        if not profile:
            embed = discord.Embed(
                title="❌ Profile Not Found",
                description=f"{'You haven' if target_user == interaction.user else f'{target_user.display_name} hasn'}'t set up {'your' if target_user == interaction.user else 'their'} profile yet. Use `/verify` to get started!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"👤 {target_user.display_name}'s Profile",
            color=discord.Color.blue()
        )
        embed.add_field(name="IGN", value=profile['ign'], inline=True)
        embed.add_field(name="Available Roles", value=", ".join(role.title() for role in profile['roles']), inline=True)
        embed.add_field(name="Total Warnings", value=profile['warns_total'], inline=True)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="unlink", description="Delete your profile data")
    async def unlink(self, interaction: discord.Interaction):
        verified_role = interaction.guild.get_role(config.VERIFIED_ROLE)
        if verified_role and verified_role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(verified_role)
            except:
                pass
        
        embed = discord.Embed(
            title="🗑️ Profile Unlinked",
            description="Your profile has been unlinked. Use `/verify` if you want to link again.",
            color=discord.Color.grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="queue", description="Show current global queue status")
    async def queue_status(self, interaction: discord.Interaction):
        if not hasattr(self.bot, '_global_queue'):
            embed = discord.Embed(
                title="📋 Global Queue",
                description="No players currently waiting in queue.",
                color=discord.Color.grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        guild_players = [p for p in self.bot._global_queue if p['guild_id'] == interaction.guild.id]
        
        if not guild_players:
            embed = discord.Embed(
                title="📋 Global Queue", 
                description="No players currently waiting in queue.",
                color=discord.Color.grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        role_players = {'support': [], 'tank': [], 'dps': [], 'flex': []}
        for player in guild_players:
            role = player['role']
            if role in role_players:
                character = player.get('character', 'No character selected')
                user_profile = player.get('user_profile', {})
                ign = user_profile.get('ign', 'Unknown')
                role_players[role].append(f"• {ign} ({character})")
        
        embed = discord.Embed(
            title="📋 Global Queue",
            description=f"**{len(guild_players)} players** waiting for a session to start:",
            color=discord.Color.blue()
        )
        
        for role, players in role_players.items():
            if players:
                emoji = "💚" if role == 'support' else "🛡️" if role == 'tank' else "🎯" if role == 'dps' else "🔄"
                embed.add_field(
                    name=f"{emoji} {role.title()} ({len(players)})",
                    value="\n".join(players),
                    inline=False
                )
        
        embed.add_field(
            name="💡 Tip",
            value="Join 'Join to Host' voice channel to start a session and match these players!",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="help", description="Show help information for Lord Farming bot")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Lord Farming Bot - Help",
            description="Complete guide to using the Lord Farming bot for Marvel Rivals",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🚀 Getting Started",
            value="1. Use `/verify` to link your IGN and set available roles\n2. Join role queue VCs (Support/Tank/DPS/Flex)\n3. Select your character when prompted\n4. Get auto-matched to teams!",
            inline=False
        )
        
        embed.add_field(
            name="👥 For Players",
            value="`/verify` - Link IGN and roles\n`/profile` - View your profile\n`/queue` - See who's waiting\n`/status` - Check current session\n`/unlink` - Delete your data",
            inline=True
        )
        
        embed.add_field(
            name="🎯 For Hosts",
            value="`/host lock` - Lock session\n`/host end` - End session\n`/warn @user` - Issue warning\n`/unassign @user` - Remove from team\n\n**To Host:** Join 'Join to Host' VC",
            inline=True
        )
        
        embed.add_field(
            name="⚙️ For Admins",
            value="`/admin sessions` - List all sessions\n`/admin cleanup` - Force cleanup\n\n*Requires Administrator permission*",
            inline=False
        )
        
        embed.add_field(
            name="🎭 Character System",
            value="• Each team can only have **one of each character**\n• First-come-first-served priority\n• Get notified if character conflict occurs\n• Can rejoin with different character",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Warning System",
            value="• **3-minute grace period** if you leave team VC\n• **3 warnings = auto-kick** from session\n• Only applies when farming is active\n• Host can issue manual warnings",
            inline=False
        )
        
        embed.add_field(
            name="🔄 Session Flow",
            value="**Host:** Join to Host VC → Set formations → Session created\n**Players:** Join role queue → Select character → Auto-matched\n**Teams:** Get moved to team VC automatically",
            inline=False
        )
        
        embed.set_footer(text="Need more help? Contact an admin or check the bot's README!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    admin_group = app_commands.Group(name="admin", description="Admin commands for Lord Farming bot")
    
    @admin_group.command(name="sessions", description="List all active sessions (Admin only)")
    async def admin_sessions(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You need administrator permissions to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        sessions = []
        for guild in self.bot.guilds:
            session = await self.bot.db.get_active_session(guild.id)
            if session:
                sessions.append({
                    'guild': guild.name,
                    'session': session
                })
        
        if not sessions:
            embed = discord.Embed(
                title="📋 Active Sessions",
                description="No active sessions found.",
                color=discord.Color.grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Active Sessions",
            description=f"Found {len(sessions)} active session(s):",
            color=discord.Color.blue()
        )
        
        for session_info in sessions:
            session = session_info['session']
            assignments = await self.bot.db.get_assignments(session['session_id'])
            total_players = len(assignments.get('A', [])) + len(assignments.get('B', []))
            
            embed.add_field(
                name=f"{session_info['guild']} - {session['name']}",
                value=f"Host: <@{session['host_id']}>\nStatus: {session['status'].title()}\nPlayers: {total_players}/12",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @admin_group.command(name="cleanup", description="Force cleanup inactive sessions (Admin only)")
    async def admin_cleanup(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You need administrator permissions to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        cleaned = 0
        for guild in self.bot.guilds:
            session = await self.bot.db.get_active_session(guild.id)
            if session and session['voice_channel_id']:
                channel = guild.get_channel(session['voice_channel_id'])
                if not channel or len(channel.members) == 0:
                    await self.bot.db.cleanup_session(session['session_id'])
                    if channel:
                        try:
                            await channel.delete()
                        except:
                            pass
                    cleaned += 1
        
        embed = discord.Embed(
            title="🧹 Cleanup Complete",
            description=f"Cleaned up {cleaned} inactive session(s).",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(LordFarmingCommands(bot))
