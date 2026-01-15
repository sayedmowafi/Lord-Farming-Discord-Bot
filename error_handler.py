import discord
from discord.ext import commands
import logging
import traceback

logger = logging.getLogger(__name__)


class ErrorHandler(commands.Cog):
    """Global error handler for the bot."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"Command error in {ctx.command}: {error}")
        
        embed = discord.Embed(
            title="❌ Command Error",
            description="An error occurred while processing your command.",
            color=discord.Color.red()
        )
        
        try:
            await ctx.send(embed=embed, ephemeral=True)
        except:
            pass
    
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        logger.error(f"App command error in {interaction.command}: {error}")
        
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏰ Command on Cooldown",
                description=f"Please wait {error.retry_after:.1f} seconds before using this command again.",
                color=discord.Color.orange()
            )
        elif isinstance(error, discord.app_commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="You don't have permission to use this command.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="❌ Command Error",
                description="An unexpected error occurred. Please try again later.",
                color=discord.Color.red()
            )
            
            logger.error(f"Unexpected error: {''.join(traceback.format_exception(type(error), error, error.__traceback__))}")
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            pass


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
