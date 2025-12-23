# chat_sessions.py
import os, uuid, shutil, asyncio, aiohttp, time, aiofiles, subprocess
from datetime import datetime
import orjson

# ---------------------------
# CONFIG
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "users_sessions.json")
MODELS_DIR = os.path.join(BASE_DIR, "models")

ACTIVE_DIR = os.path.join(BASE_DIR, "active_chats")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archived_chats")

API_URL = "http://localhost:11434/api/chat"

# ---------------------------
# GLOBALS
# ---------------------------
user_sessions = {}

# ---------------------------
# UTILITIES
# ---------------------------
def discord_ts():
    return f"<t:{int(time.time())}:R>"

def _chat_path(model, session_id, archived=False):
    base = ARCHIVE_DIR if archived else ACTIVE_DIR
    return os.path.join(base, model, f"{session_id}.txt")

# ---------------------------
# INIT
# ---------------------------
def init_sessions():
    global user_sessions
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "rb") as f:
                user_sessions = orjson.loads(f.read())
        except:
            user_sessions = {}
    else:
        user_sessions = {}
    
    build_models()
    

def build_models():
    for filename in os.listdir(MODELS_DIR):
        full_path = os.path.join(MODELS_DIR, filename)
        if os.path.isfile(full_path):
            name = os.path.splitext(filename)[0]
            subprocess.Popen(["ollama","create",name,"-f",f"models/{name}.modelfile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ---------------------------
# DISK HELPERS
# ---------------------------
def _save_sessions():
    """Save the current in-memory sessions to disk."""
    with open(DATA_FILE, "wb") as f:
        f.write(orjson.dumps(user_sessions, option=orjson.OPT_INDENT_2))

def _ensure_chat(model, session_id):
    path = _chat_path(model, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        now = datetime.now().strftime("%d-%m-%Y  %H:%M.%S")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=-=-=-=-=-=-= Session started: {now} =-=-=-=-=-=-=\n\n")

def _append_chat(model, session_id, user_msg, ai_msg):
    path = _chat_path(model, session_id)
    if not os.path.exists(path):
        _ensure_chat(model, session_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"User: {user_msg}\n{model}: {ai_msg}\n")

def _load_history(model, session_id):
    path = _chat_path(model, session_id)
    if not os.path.exists(path): return []
    prefix_user, prefix_ai = "User: ", f"{model}: "
    len_u, len_a = len(prefix_user), len(prefix_ai)
    msgs=[]
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.rstrip()
            if line.startswith(prefix_user): msgs.append({"role":"user","content":line[len_u:]})
            elif line.startswith(prefix_ai): msgs.append({"role":"assistant","content":line[len_a:]})
    return msgs

def _archive_chat(model, session_id):
    path = _chat_path(model, session_id)
    if not os.path.exists(path): return
    end_time = datetime.now().strftime("%d-%m-%Y  %H:%M.%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n=-=-=-=-=-=-= Session ended: {end_time} =-=-=-=-=-=-=\n")
    arch_dir = os.path.join(ARCHIVE_DIR, model)
    os.makedirs(arch_dir, exist_ok=True)
    arch_path = os.path.join(arch_dir, f"{session_id}.txt")
    if os.path.exists(arch_path):
        arch_path = os.path.join(arch_dir, f"{session_id}_{int(time.time())}.txt")
    shutil.move(path, arch_path)

async def remove_trailing_user_if_no_ai(model: str, session_id: str) -> bool:
    path = _chat_path(model, session_id)
    if not os.path.exists(path):
        return False

    user_prefix = "User: "
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        lines = await f.readlines()

    if not lines: return False

    # Remove trailing empty lines
    while lines and lines[-1].strip() == "":
        lines.pop()

    if not lines: return False

    if lines[-1].lstrip().startswith(user_prefix):
        lines.pop()
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.writelines(lines)
        return True

    return False

# ---------------------------
# ASYNC WRAPPERS
# ---------------------------
async def save_sessions(): await asyncio.to_thread(_save_sessions)
async def ensure_chat_async(model, session_id): await asyncio.to_thread(_ensure_chat, model, session_id)
async def append_chat_async(model, session_id, user_msg, ai_msg): await asyncio.to_thread(_append_chat, model, session_id, user_msg, ai_msg)
async def load_history_async(model, session_id): return await asyncio.to_thread(_load_history, model, session_id)
async def archive_chat_async(model, session_id): await asyncio.to_thread(_archive_chat, model, session_id)

def ensure_user_model(user_id, model):
    if user_id not in user_sessions: user_sessions[user_id]={}
    if model not in user_sessions[user_id]: user_sessions[user_id][model]={}

# ---------------------------
# LLM CALL
# ---------------------------
async def generate_llm_reply(model, messages, user_msg):
    messages.append({"role":"user","content":user_msg})
    parts=[]
    async with aiohttp.ClientSession() as client:
        try:
            async with client.post(API_URL,json={"model":model,"messages":messages},timeout=None) as resp:
                async for chunk in resp.content:
                    try:
                        data = orjson.loads(chunk)
                        content = data.get("message",{}).get("content")
                        if content: parts.append(content)
                    except: continue
        except: pass
    reply="".join(parts)
    messages.append({"role":"assistant","content":reply})
    return reply

# ---------------------------
# SESSION API
# ---------------------------
async def start_session(user_id, model, session_id=None, session_name=None, auto_hi=True):
    user_id = str(user_id)
    ensure_user_model(user_id, model)

    if session_id:
        session_id = str(session_id)
        if session_id in user_sessions[user_id][model]:
            return session_id, None

    session_id = str(uuid.uuid4())
    name = (session_name or "New Session").strip() or "New Session"
    user_sessions[user_id][model][session_id] = [name, discord_ts()]
    await save_sessions()
    await ensure_chat_async(model, session_id)

    hi_reply = None
    if auto_hi:
        hi_reply = await chat(user_id, model, session_id, '"Hi"')

    return session_id, hi_reply

async def chat(user_id, model, session_id, user_input):
    user_id = str(user_id)
    if user_id not in user_sessions or model not in user_sessions[user_id] or session_id not in user_sessions[user_id][model]:
        raise ValueError("Session not found")
    name,_ = user_sessions[user_id][model][session_id]
    user_sessions[user_id][model][session_id]=[name, discord_ts()]
    await save_sessions()
    hist = await load_history_async(model,session_id)
    reply = await generate_llm_reply(model,hist,user_input)
    await append_chat_async(model,session_id,user_input,reply)
    return reply

async def end_session(user_id, model, session_id):
    user_id = str(user_id)
    if user_id not in user_sessions or model not in user_sessions[user_id] or session_id not in user_sessions[user_id][model]: return False
    await archive_chat_async(model, session_id)
    del user_sessions[user_id][model][session_id]
    if not user_sessions[user_id][model]: del user_sessions[user_id][model]
    if not user_sessions[user_id]: del user_sessions[user_id]
    await save_sessions()
    return True

async def list_sessions(user_id):
    return user_sessions.get(str(user_id),{}).copy()

async def rename_session(user_id, model, session_id, new_name):
    user_id=str(user_id)
    if user_id not in user_sessions or model not in user_sessions[user_id] or session_id not in user_sessions[user_id][model]: return False
    user_sessions[user_id][model][session_id][0]=new_name.strip() or user_sessions[user_id][model][session_id][0]
    await save_sessions()
    return True

# ---------------------------
# TERMINAL RUNNER
# ---------------------------
async def terminal_runner():
    init_sessions()
    os.system("cls")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    user_id = "local"
    model = input("Model: ").strip()
    sess = input("Session ID (blank=new): ").strip() or None
    sess_name=None
    if sess is None:
        sess_name=input("Custom session name (blank=New Session): ").strip() or "New Session"
    session_id,reply = await start_session(user_id,model,session_id=sess,session_name=sess_name)
    print(f"{model}: {reply}\n")

    # print("Start chatting. Type 'end' to archive, 'exit' to quit.\n")
    while True:
        user_text=input("You: ").strip()
        if not user_text: continue
        if user_text.lower() in ("exit","quit"): break
        if user_text.lower()=="end":
            ok=await end_session(user_id,model,session_id)
            print(f"Session {session_id} archived." if ok else "Failed to archive.")
            break
        reply=await chat(user_id,model,session_id,user_text)
        print(f"{model}: {reply}\n")

if __name__=="__main__":
    asyncio.run(terminal_runner())