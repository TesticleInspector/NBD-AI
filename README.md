NBD AI uses Ollama LLM (llama3.1:8b) connected with Discord via discord.py library, to allow Discord users to chat directly from there. All chats are stored purely for sessions and are not meant to be used against anyone.

How to start bot:

Download Ollama on your machine
 1. Call "ollama pull llama3.1:8b" in terminal on your machine. Thia will download the LLM (~5GB)
 2. Inside startup.json enter your bot's token
 3. Run main.py and enjoy, bot will automatically download any libraries needed.
Bot might work worse on some machines, due to differences in RAM and GPU.

Things to change for your own bot:
 1. Inside cogs/Misc.py change bot logs to your case.
 2. Inside support.py change app_install_url to your own.

ANY USE OF THIS BOT THAT VIOLATES LICENSE IS CONSIDERED STEALING.
