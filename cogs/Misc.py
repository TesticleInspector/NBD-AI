from discord.ext import commands
from discord import Interaction, app_commands, Embed
from support import Bot_Info_View, log

class Misc(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.allowed_contexts(guilds=True,dms=True,private_channels=True)
    @app_commands.command(name="bot-info", description="Bot info and idea comitting.")
    async def test(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(embed=Embed(title="Bot General Info",description="NBD AI is a project made by PVC Pipe Ø20mm, " \
                    "mostly for hatking_pl and wazuri. Its main purpose is NSFW roleplay with AI chatbots; however, there are SFW " \
                    "models. Project is open to community suggestions and reports. All of it can be done using buttons below. " \
                    "***For now bot does not have 24/7 hosting, but I'm working on it. It can't be hosted externally to protect users' privacy***\n\n" \
                    "### Activity log:\n=-=-= Version 1.0.0 =-=-=\n[11/29/2025 (<t:1764406800:R>)]\n- Bot's release\n\n" \
                    "-# By using this bot for NSFW purposes, you confirm that you are above the age of consent."),view=Bot_Info_View())
        await log(f"[ACTION] Displayed bot info to {interaction.user.name}")
async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))