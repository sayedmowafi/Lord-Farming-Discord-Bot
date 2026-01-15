import discord
import logging

logger = logging.getLogger(__name__)


class NicknameManager:
    """Manages user nicknames based on their Marvel Rivals IGN and current role."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def update_user_nickname(self, member: discord.Member, role: str = None, joining: bool = True):
        """Update user's nickname based on their IGN and role."""
        try:
            user_profile = await self.bot.db.get_user(member.id)
            if not user_profile:
                return
            
            ign = user_profile['ign']
            
            if joining and role:
                role_display = {
                    'support': 'Support',
                    'tank': 'Tank', 
                    'dps': 'DPS',
                    'flex': 'Flex'
                }.get(role, role.title())
                
                new_nickname = f"{ign} ({role_display})"
            else:
                new_nickname = ign
            
            if member.display_name == new_nickname:
                return
            
            await member.edit(nick=new_nickname)
            
        except discord.HTTPException as e:
            if e.status != 403:
                logger.warning(f"Failed to update nickname for {member.name}: {e}")
        except Exception as e:
            logger.error(f"Error updating nickname for {member.name}: {e}")
    
    async def set_team_nickname(self, member: discord.Member, role: str, team: str):
        """Set nickname when assigned to a team."""
        try:
            user_profile = await self.bot.db.get_user(member.id)
            if not user_profile:
                return
            
            ign = user_profile['ign']
            role_display = {
                'support': 'Support',
                'tank': 'Tank',
                'dps': 'DPS'
            }.get(role, role.title())
            
            if member.guild_permissions.administrator:
                await self._send_admin_role_notification(member, role, team, ign)
                return
            
            new_nickname = f"{ign} ({role_display})"
            
            await member.edit(nick=new_nickname)
            
        except discord.HTTPException as e:
            if e.status == 403 and 'user_profile' in locals():
                await self._send_admin_role_notification(member, role, team, user_profile['ign'])
            elif e.status != 403:
                logger.warning(f"Failed to set team nickname for {member.name}: {e}")
        except Exception as e:
            logger.error(f"Error setting team nickname for {member.name}: {e}")
    
    async def _send_admin_role_notification(self, member: discord.Member, role: str, team: str, ign: str):
        """Send DM to admin users when nickname cannot be changed."""
        try:
            role_display = {
                'support': 'Support',
                'tank': 'Tank',
                'dps': 'DPS'
            }.get(role, role.title())
            
            embed = discord.Embed(
                title="🎯 Team Assignment (Admin)",
                description=f"Since your nickname cannot be changed due to admin permissions, here's your assignment:",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Your Role",
                value=f"**{role_display}** on **Team {team}**",
                inline=False
            )
            embed.add_field(
                name="Display Format",
                value=f"Your nickname would be: `{ign} ({role_display})`",
                inline=False
            )
            embed.set_footer(text="Please keep track of your role during the session!")
            
            await member.send(embed=embed)
            
        except discord.HTTPException:
            pass
        except Exception as e:
            logger.error(f"Error sending admin role notification to {member.name}: {e}")
    
    async def reset_nickname(self, member: discord.Member):
        """Reset nickname to just IGN when leaving sessions."""
        try:
            user_profile = await self.bot.db.get_user(member.id)
            if not user_profile:
                return
            
            ign = user_profile['ign']
            await member.edit(nick=ign)
            
        except discord.HTTPException as e:
            if e.status != 403:
                logger.warning(f"Failed to reset nickname for {member.name}: {e}")
        except Exception as e:
            logger.error(f"Error resetting nickname for {member.name}: {e}")
    
    async def set_default_nickname_on_verify(self, member: discord.Member, ign: str):
        """Set default nickname when user verifies."""
        try:
            await member.edit(nick=ign)
        except discord.HTTPException as e:
            if e.status != 403:
                logger.warning(f"Failed to set default nickname for {member.name}: {e}")
        except Exception as e:
            logger.error(f"Error setting default nickname for {member.name}: {e}")
