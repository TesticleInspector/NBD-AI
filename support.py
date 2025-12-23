import os, AI, aiofiles, orjson, enum
from datetime import datetime
from discord import ButtonStyle, Interaction, Embed, TextStyle, Color, File
from discord.ui import View, button, Modal, TextInput, Button

base_path = os.path.dirname(os.path.abspath(__file__))
logs_file = os.path.join(base_path, "logs.txt")
bug_report_file = os.path.join(base_path, "bug_reports.txt")
startup_file = os.path.join(base_path, "startup.json")
users_sessions_file = os.path.join(base_path, "users_sessions.json")
sessions_db_file = os.path.join(base_path, "sessions_db.json")
model_concepts_file = os.path.join(base_path, "models_concepts.json")
models_file = os.path.join(base_path, "models.json")


# ============================
#          FUNCTIONS         
# ============================

def set_bot(bot_instance) -> None:
    "Sets the bot instance for the support module"
    global _bot
    _bot = bot_instance

async def log(message: str) -> None:
    "Appends the provided message to the logs file"
    with open(logs_file,"a",encoding="utf-8") as f:
        f.write(str(datetime.now().replace(microsecond=0)) + f" --> {message}\n")

async def get_user_sessions(user_id: int) -> dict[str,dict[str,list[str,str]]]:
    """
    Returns all sessions started by the user. Return form:  
    {"model_name_1": {  
    \u2003\u2003"session_id_1":["session name","Time when last modified (Unix / POSIX)"]  
    \u2003\u2003"session_id_2"...  
    \u2003},  
    \u2003"model_name_2"...  
    }  
    If the user has no sessions, returns None.
    """
    if not os.path.exists(users_sessions_file):
        async with aiofiles.open(users_sessions_file, "wb") as f:
            await f.write(orjson.dumps({}, option=orjson.OPT_INDENT_2))
    
    async with aiofiles.open(users_sessions_file, "rb") as f:
        file = await f.read()
        data = orjson.loads(file)

        try:
            user_sessions = data[str(user_id)]
        except KeyError:
            user_sessions = None

        return user_sessions

async def show_modal(interaction: Interaction, fields: dict[str, list], title: str = "Enter data") -> list[str] | str:
    '''
    Displays a modal using the provided fields.  
    Fields = {"Text above field": list}  
    List = ["Text on field": str, min characters: int, max characters: int]
    '''
    class DynamicModal(Modal):
        def __init__(self):
            super().__init__(title=title)
            self.inputs: list[TextInput] = []

            for label, params in fields.items():
                placeholder,min_length,max_length = params

                text_input = TextInput(
                    label=label,
                    placeholder=placeholder,
                    min_length=min_length,
                    max_length=max_length,
                    required=True,
                    style=TextStyle.short
                )
                self.add_item(text_input)
                self.inputs.append(text_input)

            self.result: list[str] | None = None
            self.done = False

        async def on_submit(self, interaction: Interaction):
            self.result = [field.value for field in self.inputs]
            await interaction.response.defer()
            self.stop()

    modal = DynamicModal()
    await interaction.response.send_modal(modal)
    await modal.wait()
    if len(fields) == 1:
        return modal.result[0]
    return modal.result

async def split_sessions_into_pages(user_sessions, max_chars=1000):
    pages = []
    current_page = []
    current_len = 0

    for model, sessions in user_sessions.items():
        model_lines = [f"### {model}:"]
        for session_id, session_data in sessions.items():
            session_name, timestamp = session_data
            model_lines.append(f"**{len(model_lines)}.** {session_name}   (Last modified: {timestamp})")

        model_len = sum(len(line) + 1 for line in model_lines)
        if current_len + model_len > max_chars and current_page:
            pages.append(current_page)
            current_page = []
            current_len = 0

        current_page.extend(model_lines)
        current_len += model_len

    if current_page:
        pages.append(current_page)
    if not pages:
        pages = [["You don't have any sessions active"]]

    return pages

async def get_session_id_by_number(user_id: str, model: str, session_num: str) -> str:
    "Returns session id for provided model by its number on a list."
    async with aiofiles.open(users_sessions_file, "rb") as f:
        file = await f.read()
        data = orjson.loads(file)

    try:
        session_num = int(session_num)
    except ValueError:
        return "TypeError"
    
    if session_num > len(list(data[user_id][model].keys())) or session_num <= 0:
        return "IndexError"
    
    ids = list(data[user_id][model].keys())

    return ids[session_num-1]

async def get_session_name_by_id(user_id: str, model: str, session_id: str) -> str:
    "Returns session name for provided model by its id."
    async with aiofiles.open(users_sessions_file, "rb") as f:
        file = await f.read()
        data = orjson.loads(file)

    return data[str(user_id)][model][session_id][0]

async def get_last_message_pair(model: str, session_id: str):
    # Load history
    history = await AI.load_history_async(model, session_id)
    if not history:
        return None, None

    last_user = None
    last_ai = None
    first_user_index = None

    # Find first user
    for i, msg in enumerate(history):
        if msg["role"] == "user":
            first_user_index = i
            break

    # Find last complete user→AI pair
    for i in range(len(history) - 1):
        if history[i]["role"] == "user" and history[i + 1]["role"] == "assistant":
            last_user = history[i]["content"]
            last_ai = history[i + 1]["content"]

    if last_ai is None:
        return None, None

    # If last user is the first user, return None for user
    last_user_index = next((i for i, m in enumerate(history) if m["role"] == "user" and m["content"] == last_user), None)
    if last_user_index == first_user_index:
        last_user = None

    await AI.remove_trailing_user_if_no_ai(model,session_id)

    return last_user, last_ai

async def get_model_pfp(model: str) -> str:
    "Returns the model's avatar URL, defined in models.json"
    async with aiofiles.open(models_file, "rb") as f:
        file = await f.read()
        data = orjson.loads(file)

    return data[model][1]
    
async def add_session_to_db(interaction: Interaction, session_id: str) -> None:
    "Adds the session ID to the database of all sessions."
    user_id = str(interaction.user.id)

    if not os.path.exists(sessions_db_file):
        async with aiofiles.open(sessions_db_file, "wb") as f:
            await f.write(orjson.dumps({}, option=orjson.OPT_INDENT_2))

    async with aiofiles.open(sessions_db_file, "rb") as f:
        content = await f.read()
        data = orjson.loads(content) if content else {}

    if user_id not in data:
        data[user_id] = [interaction.user.name]
    if session_id not in data[user_id]:
        data[user_id].append(session_id)

    async with aiofiles.open(sessions_db_file, "wb") as f:
        await f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))

async def add_model_concept_to_db(interaction: Interaction, name: str, description: str, avatar: str) -> bool:
    "Adds a model concept to the concepts file"
    if not os.path.exists(model_concepts_file):
        async with aiofiles.open(model_concepts_file, "wb") as f:
            await f.write(orjson.dumps({}, option=orjson.OPT_INDENT_2))

    async with aiofiles.open(model_concepts_file, "rb") as f:
        content = await f.read()
        data = orjson.loads(content) if content else {}

    if name not in data:
        data[name] = [interaction.user.id,description,avatar]
    else:
        return False

    async with aiofiles.open(model_concepts_file, "wb") as f:
        await f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
    
    return True

async def save_reported_bug(interaction: Interaction, bug: str) -> None:
    "Appends a reported bug to the bug report file."
    with open(bug_report_file,"a",encoding="utf-8") as f:
        f.write(f"Reported by {interaction.user.name}: {bug}\n")

# ============================
#           CLASSES           
# ============================

class Page_Types(enum.Enum):
    SINGLE = 0
    FIRST = 1
    MIDDLE = 2
    LAST = 3

class Sessions_View(View):
    def __init__(self, pages, no_sessions, current_page=0, user_name="User"):
        super().__init__(timeout=7200)
        self.pages = pages
        self.no_sessions = no_sessions
        self.current_page = current_page
        self.user_name = user_name

        page_type = self.get_page_type()

        if page_type in [Page_Types.MIDDLE, Page_Types.LAST]:
            prev_button = Button(label="⪻", style=ButtonStyle.primary, row=0)
            prev_button.callback = self.previous_callback
            self.add_item(prev_button)

        if page_type in [Page_Types.FIRST, Page_Types.MIDDLE]:
            next_button = Button(label="⪼", style=ButtonStyle.primary, row=0)
            next_button.callback = self.next_callback
            self.add_item(next_button)

        if not no_sessions:
            join_session_button = Button(label="Join Session", style=ButtonStyle.primary, row=2)
            join_session_button.callback = self.join_session_callback
            self.add_item(join_session_button)

            terminate_session_button = Button(label="Terminate Session", style=ButtonStyle.danger, row=2)
            terminate_session_button.callback = self.terminate_session_callback
            self.add_item(terminate_session_button)

    def get_page_type(self) -> Page_Types:
        if len(self.pages) == 1:
            return Page_Types.SINGLE
        elif self.current_page == 0:
            return Page_Types.FIRST
        elif self.current_page == len(self.pages) - 1:
            return Page_Types.LAST
        else:
            return Page_Types.MIDDLE

    async def previous_callback(self, interaction: Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=Sessions_View(self.pages, False, self.current_page, self.user_name))
            await log(f"[ACTION] {interaction.user.name} went back, to page {self.current_page}")
        else:
            await interaction.response.defer()

    async def next_callback(self, interaction: Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=Sessions_View(self.pages, False, self.current_page, self.user_name))
            await log(f"[ACTION] {interaction.user.name} went forward, to page {self.current_page}")
        else:
            await interaction.response.defer()

    async def join_session_callback(self, interaction: Interaction):
        model,session_number = await show_modal(interaction,{"Model name": ["(not case sensitive)",1,20],"Session number": ["Enter here...",1,3]},"Enter Session")
        
        async with aiofiles.open(models_file, "rb") as f:
            file = await f.read()
            data = orjson.loads(file)

        model = next((item for item in list(data.keys()) if item.lower() == model.lower()), None)
        if not model:
            await interaction.followup.send(embed=Embed(description=f"Model does not exist.", color=Color.red()),ephemeral=True)
            return
        
        session_id = await get_session_id_by_number(str(interaction.user.id), model, session_number)
        if session_id == "IndexError":
            await interaction.followup.send(embed=Embed(description=f"Entered number is not a valid session number.", color=Color.red()),ephemeral=True)
            return
        elif session_id == "TypeError":
            await interaction.followup.send(embed=Embed(description=f"Entered value is not a number.", color=Color.red()),ephemeral=True)
            return
        
        AI.init_sessions()
        prompt, ai_reply = await get_last_message_pair(model,session_id)

        if ai_reply is None:
            await interaction.followup.send(embed=Embed(description=f"Session empty. Terminated automatically. Start another session.", color=Color.red()),ephemeral=True)
            await AI.end_session(interaction.user.id,model,session_id)
            await log(f"[ACTION] Autoterminated session {session_id} for {interaction.user.name}")
        else:
            if prompt is None:
                content = ai_reply
            else:
                content = f"(Replying to: `{prompt}`)\n\n\n{ai_reply}"

            avatar = await get_model_pfp(model)
            await interaction.followup.send(embed=Embed(description=content,color=Color.green()).set_author(name=model,icon_url=avatar),ephemeral=True,view=Respond_View(session_id,model))
            await log(f"[ACTION] {interaction.user.name} rejoined session {session_id}")

    async def terminate_session_callback(self, interaction: Interaction):
        model,session_number = await show_modal(interaction,{"Model name": ["(not case sensitive)",1,20],"Session number": ["Enter here...",1,3]},"Terminate Session")
        
        async with aiofiles.open(models_file, "rb") as f:
            file = await f.read()
            data = orjson.loads(file)

        model = next((item for item in list(data.keys()) if item.lower() == model.lower()), None)
        if not model:
            await interaction.followup.send(embed=Embed(description=f"Model does not exist.", color=Color.red()),ephemeral=True)
            return
        
        session_id = await get_session_id_by_number(str(interaction.user.id), model, session_number)
        if session_id == "IndexError":
            await interaction.followup.send(embed=Embed(description=f"Entered number is not a valid session number.", color=Color.red()),ephemeral=True)
            return
        elif session_id == "TypeError":
            await interaction.followup.send(embed=Embed(description=f"Entered value is not a number.", color=Color.red()),ephemeral=True)
            return
        
        AI.init_sessions()
        name = await get_session_name_by_id(interaction.user.id, model, session_id)
        await interaction.followup.send(f"# Are you sure?\n(Model: **{model}**, Session name: **{name}**)\nThis can't be undone. You won't be able to go " \
                "back to this chat ever again.",ephemeral=True,view=Confirmation_View(session_id,model))
        await log(f"[ACTION] {interaction.user.name} entered session termination")

    def create_embed(self):
        page_rows = self.pages[self.current_page]
        embed = Embed(
            title=f"Sessions of user {self.user_name}",
            description="\n".join(page_rows),
            color=Color.blue()
        )
        embed.set_footer(text=f"Page {self.current_page+1}/{len(self.pages)}")
        return embed
    
    @button(label="Start New Session",style=ButtonStyle.success,row=1)
    async def start_new_session(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        async with aiofiles.open(models_file, "rb") as f:
            file = await f.read()
            data = orjson.loads(file)
        
        models = []
        for i in range(len(list(data.keys()))):
            models.append(f"***{list(data.keys())[i]}*** - {list(data.values())[i][0]}")
        models = "\n".join(models)
        
        await interaction.followup.send(embed=Embed(title="Available models",description=models,color=Color.blue()),ephemeral=True,view=Start_New_Session_View())
        await log(f"[ACTION] Displayed available models to {interaction.user.name}")

    @button(label="Refresh",style=ButtonStyle.secondary,row=1)
    async def refresh(self, interaction: Interaction, button: Button):
        async with aiofiles.open(users_sessions_file, "rb") as f:
            file = await f.read()
            data = orjson.loads(file)

        user_sessions = data.get(str(interaction.user.id), {})
        pages = await split_sessions_into_pages(user_sessions)

        no_sessions = not bool(user_sessions)
        await interaction.response.edit_message(embed=Embed(
            title=f"Sessions of user {self.user_name}",
            description="\n".join(pages[0]),
            color=Color.blue()
        ).set_footer(text=f"Page 1/{len(pages)}"),
        view=Sessions_View(pages, no_sessions, current_page=0, user_name=self.user_name))
        await log(f"[ACTION] {interaction.user.name} refreshed session view")

class Start_New_Session_View(View):
    def __init__(self):
        super().__init__(timeout=7200)

    @button(label="Start New Session",style=ButtonStyle.success,row=1)
    async def start_new_session(self, interaction: Interaction, button: Button):
        model,session_name = await show_modal(interaction,{"Model name": ["(not case sensitive)",1,20],"Session Name": ["Enter here...",1,20]},"Start New Session")
        
        async with aiofiles.open(models_file, "rb") as f:
            file = await f.read()
            data = orjson.loads(file)

        model = next((item for item in list(data.keys()) if item.lower() == model.lower()), None)
        if not model:
            await interaction.followup.send(embed=Embed(description=f"Model does not exist.", color=Color.red()),ephemeral=True)
            return
        
        avatar = await get_model_pfp(model)
        msg = await interaction.followup.send(embed=Embed(description="Generating...",color=Color.gold()).set_author(name=model,icon_url=avatar),ephemeral=True)
        
        AI.init_sessions()
        session_id,start_msg = await AI.start_session(interaction.user.id,model,None,session_name)
        await add_session_to_db(interaction, session_id)
        
        await msg.edit(embed=Embed(description=start_msg,color=Color.green()).set_author(name=model,icon_url=avatar),view=Respond_View(session_id,model))
        await log(f"[ACTION] {interaction.user.name} started new session ({session_id})")

class Respond_View(View):
    def __init__(self,session_id,model):
        super().__init__(timeout=7200)
        self.session_id = session_id
        self.model = model
    
    @button(label="Respond",style=ButtonStyle.primary,row=0)
    async def respond(self, interaction: Interaction, button: Button):
        user_response = await show_modal(interaction,{"Your response": ["Enter here...",1,200]},f"Respond to {self.model}")
        avatar = await get_model_pfp(self.model)
        msg = await interaction.followup.send(embed=Embed(description="Generating...",color=Color.gold()).set_author(name=self.model,icon_url=avatar),ephemeral=True)
        ai_reply = await AI.chat(interaction.user.id, self.model, self.session_id, user_response)
        await msg.edit(embed=Embed(description=f"(Replying to: `{user_response}`)\n\n\n{ai_reply}",color=Color.green()).set_author(name=self.model,icon_url=avatar),view=self)
        await log(f"[ACTION] {interaction.user.name} responded to AI")

    @button(label="Terminate Session",style=ButtonStyle.danger,row=0)
    async def terminate_session(self, interaction: Interaction, button: Button):
        name = await get_session_name_by_id(interaction.user.id, self.model, self.session_id)
        await interaction.response.send_message(f"# Are you sure?\n(Model: **{self.model}**, Session name: **{name}**)\nThis can't be undone. You won't be able to go " \
                "back to this chat ever again.",ephemeral=True,view=Confirmation_View(self.session_id,self.model))
        await log(f"[ACTION] {interaction.user.name} entered session termination")

class Confirmation_View(View):
    def __init__(self, session_id, model):
        super().__init__(timeout=7200)
        self.session_id = session_id
        self.model = model
    
    @button(label="I'm Sure",style=ButtonStyle.danger,row=0)
    async def im_sure(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        
        msg = await interaction.followup.send(embed=Embed(description="Terminating...",color=Color.gold()),ephemeral=True)
        ok = await AI.end_session(interaction.user.id, self.model, self.session_id)
        
        if ok:
            await msg.edit(embed=Embed(description="Session terminated successfully.",color=Color.green()))
            await log(f"[ACTION] {interaction.user.name} terminated session ({self.session_id})")
        else:
            await msg.edit(embed=Embed(description="Something went wrong while terminating your session. Contact the developer if this issue persists.",color=Color.red()))
            await log(f"[ERROR] Something went wrong while terminating session {self.session_id} (Called by {interaction.user.name})")

class Bot_Info_View(View):
    def __init__(self):
        super().__init__(timeout=7200)

    @button(label="Share Bot",style=ButtonStyle.secondary,row=0)
    async def share_bot(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("If you press confirm, a share message will be sent, allowing everyone in this channel to install the bot on their profiles.",view=Share_Bot(),ephemeral=True)
        await log(f"[ACTION] {interaction.user.name} proceeds to sharing bot")

    @button(label="Submit Model Concept",style=ButtonStyle.primary,row=0)
    async def submit_model_concept(self, interaction: Interaction, button: Button):
        name,description,avatar = await show_modal(interaction,{"Model name": ["(if existing character enter: name (where it appears))",1,30],"Description": ["Describe your model (general look, behaviour etc.)",1,200],"Avatar": ["Model's image link (type anything if you don't have one)",1,500]},"Submitt Model Concept")
        ok = await add_model_concept_to_db(interaction, name, description, avatar)

        if not ok:
            await interaction.followup.send(embed=Embed(description="This name is already in the concept database. Please choose another name or write it differently.",color=Color.red()),ephemeral=True)
            return
        
        await interaction.followup.send(embed=Embed(description="Thank you for your submission.",color=Color.green()),ephemeral=True)
        await log(f"[ACTION] {interaction.user.name} submitted model concept")

    @button(label="Report a Bug",style=ButtonStyle.danger,row=0)
    async def report_a_bug(self, interaction: Interaction, button: Button):
        bug = await show_modal(interaction,{"What were you doing and what happened?": ["Enter here...",1,200]},"Report a Bug")
        await save_reported_bug(interaction, bug)
        await interaction.followup.send(embed=Embed(description="Thank you for your report.",color=Color.green()),ephemeral=True)
        await log(f"[ACTION] {interaction.user.name} reported a bug")

class Share_Bot(View):
    def __init__(self):
        super().__init__(timeout=7200)

    @button(label="Confirm",style=ButtonStyle.success,row=0)
    async def confirm(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        await interaction.followup.send(embed=Embed(title=f"{interaction.user.display_name} shared the bot with you!",
                                        description="To use this bot, you can either click the Install Bot button (or use the installation link) below, or access it through the bot's profile.\n\nInstallation link:\n`https://discord.com/oauth2/authorize?client_id=1444636160378011669`",
                                        color=Color.blue()),view=Install_View())
        await log(f"[ACTION] {interaction.user.name} shared bot")
        
class Install_View(View):
    def __init__(self):
        super().__init__()

        install_button = Button(
            label="Install Bot",
            style=ButtonStyle.link,
            url="https://discord.com/oauth2/authorize?client_id=1444636160378011669",
            row=0
        )
        self.add_item(install_button)