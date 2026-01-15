import discord
from discord.ext import commands
import asyncio
from typing import Optional, Dict, List

import config
from matchmaking import MatchmakingEngine


class HostFormationView(discord.ui.View):
    """View for host to set up team formations."""
    
    def __init__(self, bot, session_id: str, session_name: str, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.session_id = session_id
        self.session_name = session_name
        self.guild_id = guild_id
        self.formations = {'A': None, 'B': None}
    
    @discord.ui.button(label="Set Team A Formation", style=discord.ButtonStyle.primary, emoji="🔴")
    async def set_team_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamFormationModal(self.bot, self.session_id, self.session_name, self.guild_id, 'A', self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Set Team B Formation", style=discord.ButtonStyle.secondary, emoji="🔵")
    async def set_team_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TeamFormationModal(self.bot, self.session_id, self.session_name, self.guild_id, 'B', self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Quick 3-3-6 Setup", style=discord.ButtonStyle.success, emoji="⚡")
    async def quick_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Quick setup with Team A as 6 DPS and Team B as 3 Support 3 Tank."""
        await self.bot.db.set_formation(self.session_id, 'A', 0, 0, 6)
        await self.bot.db.set_formation(self.session_id, 'B', 3, 3, 0)
        await self.create_session_voice_channel(interaction)
    
    @discord.ui.button(label="Create Session", style=discord.ButtonStyle.danger, emoji="🎮", disabled=True)
    async def create_session_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_session_voice_channel(interaction)
    
    async def create_session_voice_channel(self, interaction: discord.Interaction):
        """Create the session voice channel and start the session."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            embed = discord.Embed(
                title="Error",
                description="Could not find the server. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        category = guild.get_channel(config.LORD_FARMING_CATEGORY)
        
        if not category:
            embed = discord.Embed(
                title="Error",
                description="Lord Farming category not found. Please contact an admin.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        channel = await guild.create_voice_channel(
            name=self.session_name,
            category=category,
            user_limit=12
        )
        
        await self.bot.db.update_session_voice_channel(self.session_id, channel.id)
        
        host_member = guild.get_member(interaction.user.id)
        if host_member and host_member.voice:
            try:
                await host_member.move_to(channel)
            except discord.HTTPException:
                pass
        
        formations = await self.bot.db.get_formations(self.session_id)
        
        embed = discord.Embed(
            title=f"✅ {self.session_name} Created!",
            description=f"Voice channel created: {channel.mention}\n\n**Team A Formation:**\n{self.format_formation(formations.get('A', {}))}\n\n**Team B Formation:**\n{self.format_formation(formations.get('B', {}))}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Next Steps",
            value="Players can now join role queues to be assigned to teams!",
            inline=False
        )
        
        view = HostControlView(self.bot, self.session_id)
        await interaction.response.send_message(embed=embed, view=view)
        
        matchmaker = MatchmakingEngine(self.bot)
        asyncio.create_task(matchmaker.process_session(self.session_id))
    
    def format_formation(self, formation: dict) -> str:
        if not formation:
            return "Not set"
        
        parts = []
        if formation.get('support', 0) > 0:
            parts.append(f"{formation['support']} Support")
        if formation.get('tank', 0) > 0:
            parts.append(f"{formation['tank']} Tank")
        if formation.get('dps', 0) > 0:
            parts.append(f"{formation['dps']} DPS")
        
        result = ", ".join(parts)
        if formation.get('note'):
            result += f"\nNote: {formation['note']}"
        
        return result or "Empty team"


class TeamFormationModal(discord.ui.Modal):
    """Modal for setting individual team formation."""
    
    def __init__(self, bot, session_id: str, session_name: str, guild_id: int, team: str, parent_view):
        super().__init__(title=f"Team {team} Formation Setup")
        self.bot = bot
        self.session_id = session_id
        self.session_name = session_name
        self.guild_id = guild_id
        self.team = team
        self.parent_view = parent_view
    
    support_count = discord.ui.TextInput(
        label="Support Count",
        placeholder="Number of support players (0-6)",
        required=True,
        max_length=1
    )
    
    tank_count = discord.ui.TextInput(
        label="Tank Count",
        placeholder="Number of tank players (0-6)",
        required=True,
        max_length=1
    )
    
    dps_count = discord.ui.TextInput(
        label="DPS Count",
        placeholder="Number of DPS players (0-6)",
        required=True,
        max_length=1
    )
    
    team_note = discord.ui.TextInput(
        label="Team Note (Optional)",
        placeholder="Special instructions for this team",
        required=False,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            support = int(self.support_count.value)
            tank = int(self.tank_count.value)
            dps = int(self.dps_count.value)
            
            if any(x < 0 for x in [support, tank, dps]):
                raise ValueError("All counts must be 0 or positive")
            
            if (support + tank + dps) != 6:
                raise ValueError("Team must have exactly 6 total players")
            
            await self.bot.db.set_formation(
                self.session_id, self.team, 
                support, tank, dps,
                self.team_note.value or None
            )
            
            self.parent_view.formations[self.team] = {
                'support': support,
                'tank': tank, 
                'dps': dps,
                'note': self.team_note.value or None
            }
            
            if self.parent_view.formations['A'] and self.parent_view.formations['B']:
                for item in self.parent_view.children:
                    if hasattr(item, 'label') and item.label == "Create Session":
                        item.disabled = False
                        break
            
            embed = discord.Embed(
                title=f"🎮 {self.session_name} - Setup",
                description="Team formations:",
                color=discord.Color.blue()
            )
            
            for team_name in ['A', 'B']:
                formation = self.parent_view.formations[team_name]
                if formation:
                    formation_text = f"Support: {formation['support']}, Tank: {formation['tank']}, DPS: {formation['dps']}"
                    if formation['note']:
                        formation_text += f"\nNote: {formation['note']}"
                    embed.add_field(
                        name=f"Team {team_name} ✅",
                        value=formation_text,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"Team {team_name} ❌",
                        value="Not configured yet",
                        inline=False
                    )
            
            if self.parent_view.formations['A'] and self.parent_view.formations['B']:
                embed.add_field(
                    name="Ready!",
                    value="Both teams configured. Click 'Create Session' to start!",
                    inline=False
                )
            
            await interaction.response.edit_message(embed=embed, view=self.parent_view)
            
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Formation",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            embed = discord.Embed(
                title="Error",
                description="Failed to set formation. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class HostControlView(discord.ui.View):
    """View for host to control their session."""
    
    def __init__(self, bot, session_id: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id
    
    async def get_session_and_guild(self):
        for guild in self.bot.guilds:
            session = await self.bot.db.get_active_session(guild.id)
            if session and session['session_id'] == self.session_id:
                return session, guild
        return None, None
    
    @discord.ui.button(label="Lock Session", style=discord.ButtonStyle.primary, emoji="🔒")
    async def lock_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        session, guild = await self.get_session_and_guild()
        if not session:
            embed = discord.Embed(
                title="❌ Error",
                description="Session not found.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        if session['status'] == 'locked':
            await self.bot.db.update_session_status(self.session_id, 'forming')
            button.label = "Lock Session"
            button.emoji = "🔒"
            button.style = discord.ButtonStyle.primary
            
            embed = discord.Embed(
                title="🔓 Session Unlocked", 
                description="Players can now join the session again.",
                color=discord.Color.green()
            )
        else:
            await self.bot.db.update_session_status(self.session_id, 'locked')
            button.label = "Unlock Session"
            button.emoji = "🔓"
            button.style = discord.ButtonStyle.secondary
            
            embed = discord.Embed(
                title="🔒 Session Locked",
                description="No new players can join the session.",
                color=discord.Color.orange()
            )
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Start Farming", style=discord.ButtonStyle.success, emoji="🎮")
    async def start_farming(self, interaction: discord.Interaction, button: discord.ui.Button):
        session, guild = await self.get_session_and_guild()
        if not session:
            embed = discord.Embed(
                title="❌ Error",
                description="Session not found.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        if session['status'] == 'active':
            await self.bot.db.update_session_status(self.session_id, 'forming')
            button.label = "Start Farming"
            button.emoji = "🎮"
            button.style = discord.ButtonStyle.success
            
            embed = discord.Embed(
                title="⏸️ Farming Stopped",
                description="Session returned to forming. Matchmaking re-enabled, warning system disabled.",
                color=discord.Color.blue()
            )
        else:
            await self.bot.db.update_session_status(self.session_id, 'active')
            button.label = "Stop Farming"
            button.emoji = "⏸️"
            button.style = discord.ButtonStyle.secondary
            
            embed = discord.Embed(
                title="🎮 Farming Started!",
                description="Session is now active. Warning system enabled, matchmaking stopped.",
                color=discord.Color.green()
            )
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="End Session", style=discord.ButtonStyle.danger, emoji="🛑")
    async def end_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        session, guild = await self.get_session_and_guild()
        if not session:
            embed = discord.Embed(
                title="❌ Error",
                description="Session not found.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        if session['voice_channel_id'] and guild:
            channel = guild.get_channel(session['voice_channel_id'])
            if channel:
                await channel.delete()
        
        await self.bot.db.cleanup_session(self.session_id)
        
        embed = discord.Embed(
            title="🛑 Session Ended",
            description="The Lord Farming session has been ended and cleaned up.",
            color=discord.Color.red()
        )
        
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)


class PlayerCharacterView(discord.ui.View):
    """View for players to select their character."""
    
    def __init__(self, bot, session_id: str, role: str, user: dict):
        super().__init__(timeout=120)
        self.bot = bot
        self.session_id = session_id
        self.role = role
        self.user = user
        
        if role == 'flex':
            self.add_item(FlexRoleSelect(user['roles']))
        else:
            self.add_item(CharacterSelect(role, session_id, bot))
    
    async def handle_character_selection(self, interaction: discord.Interaction, role: str, character: str):
        if self.session_id is None:
            await self.bot.add_to_global_queue_with_character(interaction.user, role, character, self.user)
            
            embed = discord.Embed(
                title="🕐 Waiting for Host",
                description=f"You're queued as **{role.title()}** playing **{character}**!\n\nWhen someone starts a session, you'll be automatically matched.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            success = await self.bot.db.add_to_queue(self.session_id, interaction.user.id, role, character)
            
            if success:
                embed = discord.Embed(
                    title="✅ Queued Successfully!",
                    description=f"You're queued as **{role.title()}** playing **{character}**.\nWaiting for team assignment...",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                matchmaker = MatchmakingEngine(self.bot)
                asyncio.create_task(matchmaker.process_session(self.session_id))
            else:
                embed = discord.Embed(
                    title="Error",
                    description="Failed to join queue. Please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)


class FlexRoleSelect(discord.ui.Select):
    """Select menu for flex players to choose their role."""
    
    def __init__(self, available_roles: List[str]):
        options = []
        for role in available_roles:
            if role in ['support', 'tank', 'dps']:
                options.append(discord.SelectOption(
                    label=role.title(),
                    value=role,
                    emoji="🎯" if role == 'dps' else "🛡️" if role == 'tank' else "💚"
                ))
        
        super().__init__(placeholder="Choose your role for this session", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        selected_role = self.values[0]
        
        character_select = CharacterSelect(selected_role, self.view.session_id, self.view.bot)
        self.view.clear_items()
        self.view.add_item(character_select)
        
        embed = discord.Embed(
            title=f"Selected: {selected_role.title()}",
            description="Now choose your character:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class CharacterSelect(discord.ui.Select):
    """Select menu for character selection."""
    
    def __init__(self, role: str, session_id: str = None, bot = None):
        self.role = role
        self.session_id = session_id
        self.bot = bot
        
        characters = config.CHARACTERS.get(role, [])
        
        options = []
        for char in characters[:25]:
            option = discord.SelectOption(
                label=char,
                value=char
            )
            options.append(option)
        
        super().__init__(
            placeholder=f"Choose your {role.title()} character",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_character = self.values[0]
        await self.view.handle_character_selection(interaction, self.role, selected_character)


class ConfirmationView(discord.ui.View):
    """Generic confirmation view."""
    
    def __init__(self, confirm_callback, cancel_callback=None, timeout=60):
        super().__init__(timeout=timeout)
        self.confirm_callback = confirm_callback
        self.cancel_callback = cancel_callback
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.confirm_callback:
            await self.confirm_callback(interaction)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.cancel_callback:
            await self.cancel_callback(interaction)
        else:
            embed = discord.Embed(
                title="Cancelled",
                description="Operation cancelled.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class HostCharacterViewForSetup(discord.ui.View):
    """View for host to select their character during initial session setup."""
    
    def __init__(self, bot, session_id: str, session_name: str, guild_id: int, user: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.session_id = session_id
        self.session_name = session_name
        self.guild_id = guild_id
        self.user = user
        
        available_roles = user['roles']
        if 'support' in available_roles:
            self.add_item(HostRoleButtonForSetup(bot, session_id, session_name, guild_id, 'support', user))
        if 'tank' in available_roles:
            self.add_item(HostRoleButtonForSetup(bot, session_id, session_name, guild_id, 'tank', user))
        if 'dps' in available_roles:
            self.add_item(HostRoleButtonForSetup(bot, session_id, session_name, guild_id, 'dps', user))


class HostRoleButtonForSetup(discord.ui.Button):
    """Button for host to select their role during setup."""
    
    def __init__(self, bot, session_id: str, session_name: str, guild_id: int, role: str, user: dict):
        emoji = "💚" if role == 'support' else "🛡️" if role == 'tank' else "🎯"
        super().__init__(label=f"Play {role.title()}", emoji=emoji, style=discord.ButtonStyle.primary)
        self.bot = bot
        self.session_id = session_id
        self.session_name = session_name
        self.guild_id = guild_id
        self.role = role
        self.user = user
    
    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🎯 {self.role.title()} Character Selection",
            description=f"Select your {self.role} character:",
            color=discord.Color.purple()
        )
        
        view = HostCharacterSelectViewForSetup(self.bot, self.session_id, self.session_name, self.guild_id, self.role, self.user)
        await interaction.response.edit_message(embed=embed, view=view)


class HostCharacterSelectViewForSetup(discord.ui.View):
    """View for host character selection during setup."""
    
    def __init__(self, bot, session_id: str, session_name: str, guild_id: int, role: str, user: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.session_id = session_id
        self.session_name = session_name
        self.guild_id = guild_id
        self.role = role
        self.user = user
        
        self.add_item(HostCharacterSelectForSetup(role))
    
    async def handle_character_selection(self, interaction: discord.Interaction, character: str):
        success = await self.bot.db.add_to_queue(self.session_id, interaction.user.id, self.role, character)
        
        if success:
            embed = discord.Embed(
                title="✅ Character Selected!",
                description=f"You're playing **{self.role.title()}** as **{character}**!\n\nNow let's set up the team formations.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            
            await self.bot.send_host_formation_dm(interaction.user, self.session_id, self.session_name, self.guild_id)
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to add you to the session. Please try again.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=None)


class HostCharacterSelectForSetup(discord.ui.Select):
    """Select menu for host character selection during setup."""
    
    def __init__(self, role: str):
        self.role = role
        
        characters = config.CHARACTERS.get(role, [])
        
        options = []
        for char in characters[:25]:
            options.append(discord.SelectOption(
                label=char,
                value=char
            ))
        
        super().__init__(
            placeholder=f"Choose your {role.title()} character",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_character = self.values[0]
        await self.view.handle_character_selection(interaction, selected_character)
