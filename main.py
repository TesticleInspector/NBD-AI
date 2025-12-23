import discord, asyncio, json, logging, support, subprocess
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!!!", intents=intents)

@bot.event
async def on_ready():
    try:
        comm = await bot.tree.sync()
    except Exception as e:
        print("Error loading:",e)
    else:
        print("Loaded",len(comm),"slash commands")
    await support.log("[INFO] Started Los Pizdatos")

async def load_cogs():
    await bot.load_extension("cogs.Chat")
    await bot.load_extension("cogs.Misc")

async def main():
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    async with bot:
        await load_cogs()
        with open(support.startup_file,"r") as f:
            data = json.load(f)
            await bot.start(data["token"])

asyncio.run(main())