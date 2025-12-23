from discord.ext import commands
from discord import Interaction, app_commands
from support import get_user_sessions, Sessions_View, split_sessions_into_pages, log

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.allowed_contexts(guilds=True,dms=True,private_channels=True)
    @app_commands.command(name="start", description="Start command")
    async def start(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        user_sessions = await get_user_sessions(interaction.user.id)
        no_sessions = False

        if not user_sessions:
            no_sessions = True
            pages = [["You don't have any sessions active"]]
        else:
            pages = await split_sessions_into_pages(user_sessions, max_chars=1000)

        view = Sessions_View(pages, no_sessions, 0, interaction.user.display_name)
        await interaction.followup.send(embed=view.create_embed(), view=view)
        await log(f"[ACTION] Displayed user sessions to {interaction.user.name} (start command)")
            

async def setup(bot: commands.Bot):
    await bot.add_cog(Chat(bot))