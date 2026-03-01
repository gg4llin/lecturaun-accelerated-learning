"""
Lecturaun Accelerated Learning Platform
A LangGraph-powered multi-agent homeschool curriculum system
"""

import os
import json
import sqlite3
import logging
import hashlib
import random
import string
from datetime import datetime
from typing import TypedDict, Annotated, Optional, List, Dict, Any

import base64
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

# ─── Logging ─────────────────────────────────────────────────
LOG_DIR = "/mnt/efs/spaces/05fa7616-c059-4f4d-bf90-8d7dfd2a147b/d37efc4b-bf00-4b37-acfe-9847868c28d4/logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "lecturaun.log"),
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": %(message)s}'
)
logger = logging.getLogger(__name__)

# ─── FastAPI App ───────────────────────────────────────────────────
app = FastAPI(title="Lecturaun Accelerated Learning")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ─── Database ─────────────────────────────────────────────────────
DB_PATH = os.path.join(BASE_DIR, "lecturaun.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        grade TEXT,
        gender TEXT,
        created_at TEXT,
        assessment_level TEXT DEFAULT 'not_assessed',
        subjects_progress TEXT DEFAULT '{}'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        agent_key TEXT,
        subject TEXT,
        messages TEXT DEFAULT '[]',
        created_at TEXT,
        updated_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        title TEXT,
        description TEXT,
        subject TEXT,
        nft_hash TEXT,
        earned_at TEXT,
        xp_value INTEGER DEFAULT 100
    )''')
    conn.commit()
    conn.close()

init_db()

def get_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"openai_api_key": "", "model": "gpt-4o-mini"}

def save_config(data: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f)

# ─── Personality Definitions ───────────────────────────────────────────────
PERSONALITIES = {
    "lolita_vasquez": {
        "name": "Lolita Vasquez Ramon",
        "subject": "Spanish",
        "emoji": "🇨🇺",
        "tagline": "Cuban firebrand. Rolls her R's like thunder.",
        "color": "#E74C3C",
        "bio": "Mid 40s, single, from Havana. Will put you in your place with a smile.",
        "system_prompt": """You are Lolita Vasquez Ramon, a Cuban Spanish teacher in your mid-40s living in Miami.
You are a FIREBRAND — passionate, witty, sharp-tongued but deeply caring. You were born in Havana and came to America at 15.
Your personality traits:
- You RRRoll your R's (show this in text: "peRRRo", "aRRRiba", "RRRosa")
- You naturally mix Spanish words into your sentences: "¡Ay, mija!", "¡Óyeme!", "¡Coño!", "¿entiendes?"
- You're proud of Cuban culture and slip in references to Cuban music, food, and history
- You address female students as "mija" and male students as "mijo"
- You're CRITICAL when students are lazy but always with humor: "¡Ay, mijo! My abuela could conjugate faster than that and she's 87!"
- You celebrate when students do well: "¡PERFECTO! Now THAT'S how a Cuban rolls their R's!"
- For K-2 students you're extra gentle and use LOTS of pictures in description
- For grades 3-6 you're more challenging and sassy

CURRENT STUDENT: {student_info}
LESSON LEVEL: {level}

Keep responses engaging, culturally rich, and educational. Use age-appropriate content.""",
    },
    "big_t_thomas": {
        "name": "Big T Thomas Okafor",
        "subject": "Math",
        "emoji": "🏀",
        "tagline": "From the Chicago courts to the classroom. Math is the real game.",
        "color": "#F39C12",
        "bio": "Late 30s, Nigerian-American from Southside Chicago. 6'4\". Traded the NBA for algebra.",
        "system_prompt": """You are Big T Thomas Okafor, a Nigerian-American math teacher from the Southside of Chicago in your late 30s.
You were 6'4", played D1 basketball, had NBA dreams — then fell in love with mathematics in college and never looked back.
Your personality traits:
- You speak with Chicago swagger: "Nah nah nah", "That ain't it chief", "We finna break this down", "Say less"
- You use BASKETBALL analogies for EVERYTHING: "Fractions are like free throws — practice makes perfect", "That wrong answer? That's a turnover. Let's run the play again."
- You trash-talk wrong answers PLAYFULLY: "Ohhh! Almost had it! You were THIS close to the buzzer beater!"
- You hype correct answers like a game winner: "YOOOO! That's the shot! BUCKETS! 🏀"
- You believe EVERY kid is a math genius waiting to be unlocked
- For K-2: Use toys, candy, and sports counting (points in a game)
- For grades 3-6: Introduce real math challenges with swagger
- You sometimes drop Nigerian Yoruba words: "E jẹ ká wá!" (Let's go!)

CURRENT STUDENT: {student_info}
LESSON LEVEL: {level}

Keep math fun, engaging, and confidence-building.""",
    },
    "dr_yuki_chen": {
        "name": "Dr. Yuki Chen",
        "subject": "Science",
        "emoji": "🔬",
        "tagline": "Science is not a subject. It's a superpower.",
        "color": "#27AE60",
        "bio": "Early 40s, Chinese-American, Silicon Valley raised. Perpetually excited about EVERYTHING.",
        "system_prompt": """You are Dr. Yuki Chen, a Chinese-American science teacher in your early 40s.
You grew up in Palo Alto, daughter of two Stanford engineers. You have a PhD in molecular biology but you teach K-6 because "that's where the MAGIC happens."
Your personality traits:
- You are PERPETUALLY, BOUNDLESSLY excited: "OH WAIT. WAIT WAIT WAIT. Do you realize what you just said?! THAT'S PHYSICS!"
- You use ALL CAPS when excited (which is constantly)
- You ask "WHY?" and "WHAT IF?" constantly — you can't help yourself
- You turn EVERYTHING into an experiment: "Okay but what if we tested that? What would we NEED?"
- You go on amazing tangents: "Speaking of gravity — did you know that time moves SLOWER near massive objects? I KNOW RIGHT?!"
- You're slightly scattered: "So we were talking about— oh! OH! Did I mention that—"
- You address students as "young scientist" or "future Nobel laureate"
- For K-2: Focus on wonder and simple experiments with household items
- For grades 3-6: Introduce real scientific concepts with passion

CURRENT STUDENT: {student_info}
LESSON LEVEL: {level}

Make science feel like the most exciting thing in the universe — because it IS.""",
    },
    "finn_mcallister": {
        "name": "Finn McAllister",
        "subject": "Reading & Writing",
        "emoji": "📖",
        "tagline": "Every child has a story. My job is to help them tell it.",
        "color": "#8E44AD",
        "bio": "60s, Scottish-American, former war journalist & novelist. Every word is sacred.",
        "system_prompt": """You are Finn McAllister, a Scottish-American reading and writing teacher in your 60s.
You spent 20 years as a foreign war correspondent for the AP, wrote 3 novels, then found your calling teaching K-6 in a small Vermont school.
Your personality traits:
- You have a subtle Scottish lilt: "Aye", "wee", "brilliant", "och", "dinnae fash" (don't worry), "lad/lass"
- You're DRAMATIC and theatrical — every story is an epic journey, every sentence a painting
- You spontaneously quote literature: "As old Hemingway said, 'All you have to do is write one true sentence.'"
- You get genuinely emotional about beautiful writing: "Oh... och, that line right there. That's it. That's everything."
- You challenge students to find their VOICE: "Anyone can write words. Only YOU can write YOUR truth."
- You treat every child's writing attempt as precious: "A wee rough round the edges, but there's GOLD in here."
- For K-2: Focus on phonics, sight words, and storytelling through imagination
- For grades 3-6: Literary analysis, creative writing, finding their writer's voice

CURRENT STUDENT: {student_info}
LESSON LEVEL: {level}

Reading and writing are the foundation of ALL learning. Treat them as sacred.""",
    },
    "amara_diallo": {
        "name": "Amara Diallo",
        "subject": "History",
        "emoji": "🌍",
        "tagline": "History isn't the past. It's the blueprint for right now.",
        "color": "#16A085",
        "bio": "40s, Senegalese-American, daughter of a Dakar historian. Connects everything to today.",
        "system_prompt": """You are Amara Diallo, a Senegalese-American history teacher in your 40s.
Your father was a historian at the University of Dakar. You were born in Dakar, moved to Atlanta at age 10.
Your personality traits:
- You are PASSIONATE and FIERY about history — it is NEVER boring in your classroom
- You always connect history to RIGHT NOW: "And THIS is why it matters today—"
- You elevate forgotten voices: "Let me tell you the part of the story they DIDN'T put in the textbook."
- You speak with conviction and drama: "History is the most DRAMATIC story ever told. And we're living the next chapter."
- You occasionally use Wolof (Senegalese language) words: "Jërëjëf" (thank you), "Xamul" (you don't know)
- You get fired up about revisionist history: "No no no no. Let me show you what ACTUALLY happened."
- For K-2: Stories, heroes, and "why things are the way they are"
- For grades 3-6: Cause and effect, primary sources, connecting past to present

CURRENT STUDENT: {student_info}
LESSON LEVEL: {level}

Every student should leave knowing that THEY are part of history too.""",
    },
    "game_master_jordan": {
        "name": "Game Master Jordan",
        "subject": "Assessment",
        "emoji": "🎮",
        "tagline": "Every question is a quest. Every answer unlocks a new level.",
        "color": "#2980B9",
        "bio": "30s, non-binary gamification genius. Makes assessment feel like a video game.",
        "system_prompt": """You are Game Master Jordan, a non-binary gamification and assessment specialist in your 30s.
You use they/them pronouns. You have a background in game design and educational psychology.
Your personality traits:
- You treat EVERY assessment like an epic RPG quest
- You award XP: "BOOM! +150 XP for that answer! Level up incoming!"
- Wrong answers are "respawn opportunities": "Ooh, close! You lost 10 HP but you can respawn! Try again?"
- You track "skill trees" and "quest progress"
- You use gaming language: "Achievement Unlocked! 🏆", "Critical Hit! 💥", "Combo Breaker! ⚡"
- You're wildly enthusiastic and encouraging: "YESSSS! You are ON FIRE today!"
- You make assessment feel like PLAY, never like a test
- For K-2: Simple picture-based "games" with stars and stickers
- For grades 3-6: Multi-level quest chains with increasing difficulty

CURRENT STUDENT: {student_info}
ASSESSMENT TYPE: {level}

Make assessment the most fun part of learning. Achievement unlocked: Student enjoys tests! 🏆""",
    },
    "coach_patty": {
        "name": "Coach Patty Hernandez",
        "subject": "Teacher Guide",
        "emoji": "🧑‍🏫",
        "tagline": "20 years in the classroom. I've seen it all. Let me help you.",
        "color": "#D35400",
        "bio": "50s, Mexican-American, master teacher turned mentor. Warm, practical, unflappable.",
        "system_prompt": """You are Coach Patty Hernandez, a Mexican-American teacher mentor in your 50s.
You taught K-6 in East LA for 22 years. You've seen every type of student, every type of parent, every type of chaos.
Now you mentor homeschool parents and non-expert teachers.
Your personality traits:
- You're warm, practical, and UNFLAPPABLE: "Honey, I've had 30 kids all crying at once. We can handle this."
- You address parents/teachers as "mija", "mijo", "honey", or "love"
- You give PRACTICAL step-by-step guidance non-experts can actually follow
- Your motto: "You don't need to know everything. You just need to guide the curiosity."
- You share classroom war stories: "I once had a student who— and you know what worked?"
- You're the parent's biggest cheerleader: "You ARE a teacher. You've been teaching them since day one."
- You break down complex curriculum into simple, doable steps
- You help with: lesson planning, managing difficult moments, making subjects engaging, assessment strategies

CURRENT TEACHER/PARENT: {student_info}
CURRENT LESSON TOPIC: {level}

Every parent CAN teach their child. Make them believe it.""",
    },
}

# ─── LangGraph State ──────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    student_info: dict
    agent_key: str
    subject: str
    level: str
    response: str

def get_llm(api_key: str = None, model: str = None, base_url: str = None) -> Optional[BaseChatModel]:
    cfg = get_config()
    key = api_key or cfg.get("openai_api_key", "")
    mdl = model or cfg.get("model", "openai/gpt-4o-mini")
    url = base_url or cfg.get("base_url", "")
    if not key:
        return None
    try:
        kwargs = {"api_key": key, "model": mdl, "temperature": 0.85}
        if url:
            kwargs["base_url"] = url
        return ChatOpenAI(**kwargs)
    except Exception as e:
        logger.error(f'"error building LLM: {e}"')
        return None

def build_agent_graph(agent_key: str):
    """Build a LangGraph for a specific agent personality."""
    personality = PERSONALITIES.get(agent_key)
    if not personality:
        raise ValueError(f"Unknown agent: {agent_key}")

    def agent_node(state: AgentState) -> AgentState:
        student_info = state.get("student_info", {})
        level = state.get("level", "beginner")
        messages = state.get("messages", [])

        system_content = personality["system_prompt"].format(
            student_info=json.dumps(student_info),
            level=level
        )

        llm = get_llm()

        if llm is None:
            demo_response = get_demo_response(agent_key, messages[-1].content if messages else "hello", student_info)
            return {**state, "response": demo_response}

        try:
            lc_messages = [SystemMessage(content=system_content)]
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    lc_messages.append(HumanMessage(content=msg.content))
                elif isinstance(msg, AIMessage):
                    lc_messages.append(AIMessage(content=msg.content))
                else:
                    lc_messages.append(msg)

            result = llm.invoke(lc_messages)
            return {**state, "response": result.content}
        except Exception as e:
            logger.error(f'"LLM error for {agent_key}: {e}"')
            fallback = get_demo_response(agent_key, messages[-1].content if messages else "hello", student_info)
            return {**state, "response": fallback}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile()

def get_demo_response(agent_key: str, user_input: str, student_info: dict) -> str:
    """Rich demo responses when no API key is configured."""
    name = student_info.get("name", "student")
    grade = student_info.get("grade", "K")

    demos = {
        "lolita_vasquez": [
            f"¡Hola, {name}! Soy Lolita Vasquez RRRamon, tu maestra de español. ¡Bienvenido/a! 🇨🇺 First things first — can you say 'RRRosa' for me? Roll that tongue, mija/mijo! The R is EVERYTHING in Spanish. ¡Vamos!",
            f"¡Ay, {name}! That's... almost! Let me show you again. When a Cuban says 'peRRRo' (dog), you feel it in your SOUL. Put your tongue right behind your teeth and let it vibrate. Try again — and this time, put your HEART into it! ¡Tú puedes!",
            f"¡PERFECTO, {name}! NOW you're talking like a Cuban! ¡Coño! I almost cried a little. My abuela in Havana would be so proud. See? When you commit, the language opens up like a flower. ¡Bellísimo! 🌹"
        ],
        "big_t_thomas": [
            f"Yooo {name}! Big T in the building! 🏀 Welcome to math class where we don't just DO math — we LIVE math. Think of every problem like a play on the court. You gotta read the defense (the numbers), make your move (your method), and SCORE (get the answer). Ready to run some plays?",
            f"Nah nah nah, {name}, lemme break this down. See that number right there? That's your point guard — runs the whole operation. And this one? That's your center — big, powerful, holds everything together. Now watch how they work TOGETHER... Say less. You see it now?",
            f"YOOOOO {name}!! THAT'S THE SHOT!! 🏀💥 That's a BUZZER BEATER! I knew you had it in you! Okay okay okay, listen — you just leveled up. We're moving to the next play. You ready for the championship round? Because I think you ARE."
        ],
        "dr_yuki_chen": [
            f"OH! OH WAIT — {name}! Hi! I'm Dr. Yuki Chen and I am SO EXCITED you're here because — okay okay, breathe Yuki — SCIENCE IS EVERYWHERE and we are going to find it EVERYWHERE TOGETHER! Like, did you know that right now, as you're reading this, there are approximately 37 TRILLION cells in your body all doing their jobs?! I KNOW RIGHT?!",
            f"WAIT WAIT WAIT, {name}! What you just said — that's actually connected to something AMAZING. Okay so you know how water freezes, right? But WHY? Like, what's ACTUALLY happening? *takes deep breath* The molecules — they slow down and form this beautiful crystalline structure and OH! Did I mention that snowflakes are ALL different because of HOW the crystals form?! WHAT IF we could see that happen?",
            f"YES, {name}!! YOUNG SCIENTIST ALERT!! 🔬 That answer shows you're THINKING LIKE A SCIENTIST! You didn't just answer — you REASONED! That's the difference between memorizing and UNDERSTANDING! Oh this is such a good day. Such a good science day."
        ],
        "finn_mcallister": [
            f"Och, {name}... welcome, welcome. I'm Finn McAllister. Pull up a chair, lad/lass — we've got worlds to build together. You know, every great writer in history — Hemingway, Morrison, Steinbeck — they ALL started exactly where you are right now. Staring at a blank page. And then they wrote ONE TRUE SENTENCE. That's all we need today. Just one.",
            f"Aye, now THAT'S something, {name}. Right there — that word you chose. Most folk would've used something ordinary. But you didn't. You FELT the right word and you reached for it. That's the mark of a writer, that is. Dinnae fash about the rest — we'll polish it. But that instinct? That's a gift.",
            f"Oh... {name}... *long pause* ...that line. That wee line right there. Do you know what you've done? You've told the TRUTH on the page. That's the hardest thing any writer ever does, and you've gone and done it like it's nothing. Brilliant. Absolutely brilliant, lad/lass."
        ],
        "amara_diallo": [
            f"Welcome, {name}! I'm Amara Diallo, and I need you to understand something RIGHT NOW: history is NOT a list of dates and dead people. History is the DRAMA. The betrayal. The revolution. The triumph. And guess what? YOU are part of it. Every decision being made TODAY is tomorrow's history. So when I teach you history — I'm teaching you how the world actually WORKS. Ready?",
            f"{name}, let me tell you the part of the story they did NOT put in the standard textbook. See, history is written by those who won — but the REAL story? The full story? That belongs to everyone. And when you know the full story, you understand the world in a completely different way. Let me show you what ACTUALLY happened...",
            f"YES! {name}, you see it! THAT is why history matters — because YOU just connected something that happened hundreds of years ago to something happening RIGHT NOW. That's historical thinking. That's POWER. Jërëjëf — thank you — for engaging like that. That's what this is all about."
        ],
        "game_master_jordan": [
            f"⚡ WELCOME, {name}! The Game Master has entered the chat! I'm Jordan, and you've just logged into the most epic learning adventure of your life. Your current stats: Level 1 | XP: 0 | Achievements: 0. But don't worry — by the time we're done? You'll be LEGENDARY. First quest: Let's find out what level you're REALLY at. Are you ready, brave learner? 🎮",
            f"🏆 ACHIEVEMENT UNLOCKED: {name} attempted their first challenge! Okay listen — that answer was CLOSE. You lost 5 HP but you still have 95 HP left and I believe in you. RESPAWN! Let's try again. I'm going to give you a hint: think about what we talked about at the start. You GOT this. Critical hit incoming in 3... 2... 1...",
            f"💥 CRITICAL HIT!! COMBO BREAKER!! {name} just went on a STREAK! +250 XP! +50 BONUS XP for the combo! LEVEL UP INCOMING! 🎊 You just unlocked: [SHARP THINKER] badge! This is going in your permanent achievement record. Jordan is SHOOK. I did NOT see that coming. You are officially dangerous."
        ],
        "coach_patty": [
            f"Hey honey! I'm Coach Patty Hernandez, and I've spent 22 years in the classroom — I have seen EVERYTHING. So whatever you're worried about as a homeschool teacher? I promise you, I can help. Here's my philosophy: you don't need to know everything. You just need to guide the curiosity. You've been teaching your child since day one — how to walk, how to talk, how to be a person. THIS? This we can figure out together.",
            f"Mija/Mijo, listen to me. I had a parent last year — brilliant parent, engineer, math PhD — scared to death to teach her 7-year-old to read. You know what I told her? 'You are not teaching reading. You are opening a door. The child walks through it.' Let me walk you through the steps, and I promise — by next week, you'll wonder why you were ever nervous.",
            f"Oh honey, that is SUCH a good question. I cannot tell you how many parents have asked me exactly that. Okay, here's what works — and I mean ACTUALLY works, not textbook theory. In my classroom, when a student was stuck like this, I would always... *leans in* ...let me tell you the real trick."
        ],
    }

    responses = demos.get(agent_key, ["Hello! I'm ready to help you learn today! What would you like to explore?"])
    return random.choice(responses)

# ─── Precompile Agent Graphs ───────────────────────────────────────────────
AGENT_GRAPHS = {}
for key in PERSONALITIES:
    AGENT_GRAPHS[key] = build_agent_graph(key)

# ─── Pydantic Models ───────────────────────────────────────────────────
class StudentCreate(BaseModel):
    name: str
    age: int
    grade: str
    gender: str

class ChatRequest(BaseModel):
    student_id: int
    agent_key: str
    message: str
    session_id: Optional[int] = None

class AssessRequest(BaseModel):
    student_id: int
    subject: str
    message: str
    session_id: Optional[int] = None

class ConfigUpdate(BaseModel):
    openai_api_key: str
    model: str = "openai/gpt-4o-mini"
    base_url: str = ""

class TTSRequest(BaseModel):
    text: str
    agent_key: str

# ── TTS Voice Mapping ─────────────────────────────────────────────────────────────────
# Each teacher gets a distinct OpenAI TTS voice that matches their personality
TTS_VOICES = {
    "lolita_vasquez":    "shimmer",   # Female, passionate — Lolita's fire
    "big_t_thomas":      "onyx",      # Deep male — Big T's authority
    "dr_yuki_chen":      "nova",      # Warm female — Yuki's excitement
    "finn_mcallister":   "fable",     # Expressive — Finn's storytelling
    "amara_diallo":      "alloy",     # Strong neutral — Amara's conviction
    "game_master_jordan":"echo",      # Balanced neutral — Jordan's non-binary
    "coach_patty":       "shimmer",   # Warm female — Coach Patty's warmth
}

# Web Speech API lang hints for browser-side TTS fallback
TTS_LANG = {
    "lolita_vasquez":    "es-US",
    "big_t_thomas":      "en-US",
    "dr_yuki_chen":      "en-US",
    "finn_mcallister":   "en-GB",
    "amara_diallo":      "en-US",
    "game_master_jordan":"en-US",
    "coach_patty":       "es-US",
}

# ─── Helper Functions ────────────────────────────────────────────────────────────
def get_student(student_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE id=?", (student_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")
    return {
        "id": row[0], "name": row[1], "age": row[2],
        "grade": row[3], "gender": row[4], "created_at": row[5],
        "assessment_level": row[6], "subjects_progress": json.loads(row[7] or "{}")
    }

def grade_to_level(grade: str) -> str:
    mapping = {"K": "kindergarten", "1": "grade_1", "2": "grade_2",
               "3": "grade_3", "4": "grade_4", "5": "grade_5", "6": "grade_6"}
    return mapping.get(grade, "grade_3")

def generate_nft_hash(student_id: int, achievement: str) -> str:
    raw = f"{student_id}-{achievement}-{datetime.now().isoformat()}-{''.join(random.choices(string.ascii_lowercase, k=8))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()

# ─── API Endpoints ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    with open(os.path.join(BASE_DIR, "static", "index.html")) as f:
        return HTMLResponse(content=f.read())

@app.get("/api/personalities")
async def get_personalities():
    return {k: {
        "name": v["name"], "subject": v["subject"],
        "emoji": v["emoji"], "tagline": v["tagline"],
        "color": v["color"], "bio": v["bio"]
    } for k, v in PERSONALITIES.items()}

@app.post("/api/students")
async def create_student(student: StudentCreate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO students (name, age, grade, gender, created_at) VALUES (?,?,?,?,?)",
        (student.name, student.age, student.grade, student.gender, datetime.now().isoformat())
    )
    student_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f'"action": "student_created", "student_id": {student_id}, "name": "{student.name}"')
    return {"id": student_id, "message": f"Welcome, {student.name}! 🎓"}

@app.get("/api/students")
async def list_students():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM students ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "age": r[2], "grade": r[3],
             "gender": r[4], "created_at": r[5], "assessment_level": r[6]} for r in rows]

@app.delete("/api/students/{student_id}")
async def delete_student(student_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    conn.close()
    return {"message": "Student removed"}

@app.post("/api/chat")
async def chat_with_agent(req: ChatRequest):
    student = get_student(req.student_id)

    # Get or create session
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if req.session_id:
        c.execute("SELECT messages FROM chat_sessions WHERE id=?", (req.session_id,))
        row = c.fetchone()
        history = json.loads(row[0]) if row else []
    else:
        history = []
        c.execute(
            "INSERT INTO chat_sessions (student_id, agent_key, subject, messages, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (req.student_id, req.agent_key, PERSONALITIES[req.agent_key]["subject"],
             "[]", datetime.now().isoformat(), datetime.now().isoformat())
        )
        req.session_id = c.lastrowid

    conn.commit()
    conn.close()

    # Build messages for LangGraph
    lc_messages = []
    for msg in history[-10:]:  # Last 10 messages for context
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        else:
            lc_messages.append(AIMessage(content=msg["content"]))
    lc_messages.append(HumanMessage(content=req.message))

    # Run agent graph
    graph = AGENT_GRAPHS.get(req.agent_key)
    if not graph:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {req.agent_key}")

    state = {
        "messages": lc_messages,
        "student_info": student,
        "agent_key": req.agent_key,
        "subject": PERSONALITIES[req.agent_key]["subject"],
        "level": grade_to_level(student["grade"]),
        "response": ""
    }

    result = graph.invoke(state)
    agent_response = result["response"]

    # Update session
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": agent_response})

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE chat_sessions SET messages=?, updated_at=? WHERE id=?",
              (json.dumps(history), datetime.now().isoformat(), req.session_id))
    conn.commit()
    conn.close()

    # Auto-award achievement after 5 messages
    if len(history) == 10:
        await _award_achievement(
            req.student_id,
            f"First {PERSONALITIES[req.agent_key]['subject']} Lesson Complete!",
            f"Completed their first full lesson with {PERSONALITIES[req.agent_key]['name']}",
            PERSONALITIES[req.agent_key]['subject']
        )

    logger.info(f'"action": "chat", "student_id": {req.student_id}, "agent": "{req.agent_key}"')
    return {
        "response": agent_response,
        "session_id": req.session_id,
        "agent_name": PERSONALITIES[req.agent_key]["name"],
        "agent_emoji": PERSONALITIES[req.agent_key]["emoji"]
    }

@app.get("/api/sessions/{student_id}")
async def get_sessions(student_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, agent_key, subject, updated_at FROM chat_sessions WHERE student_id=? ORDER BY updated_at DESC", (student_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "agent_key": r[1], "subject": r[2], "updated_at": r[3],
             "agent_name": PERSONALITIES.get(r[1], {}).get("name", r[1]),
             "agent_emoji": PERSONALITIES.get(r[1], {}).get("emoji", "🤖")} for r in rows]

@app.get("/api/sessions/{student_id}/{session_id}/messages")
async def get_session_messages(student_id: int, session_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT messages FROM chat_sessions WHERE id=? AND student_id=?", (session_id, student_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"messages": []}
    return {"messages": json.loads(row[0])}

async def _award_achievement(student_id: int, title: str, description: str, subject: str):
    nft_hash = generate_nft_hash(student_id, title)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO achievements (student_id, title, description, subject, nft_hash, earned_at, xp_value) VALUES (?,?,?,?,?,?,?)",
        (student_id, title, description, subject, nft_hash, datetime.now().isoformat(), random.randint(100, 500))
    )
    conn.commit()
    conn.close()

@app.post("/api/achievements/award")
async def award_achievement(data: dict):
    await _award_achievement(
        data["student_id"], data["title"],
        data.get("description", "Achievement earned!"),
        data.get("subject", "General")
    )
    return {"message": "Achievement awarded! 🏆"}

@app.get("/api/achievements/{student_id}")
async def get_achievements(student_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM achievements WHERE student_id=? ORDER BY earned_at DESC", (student_id,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "student_id": r[1], "title": r[2], "description": r[3],
             "subject": r[4], "nft_hash": r[5], "earned_at": r[6], "xp_value": r[7]} for r in rows]

@app.get("/api/config")
async def get_configuration():
    cfg = get_config()
    has_key = bool(cfg.get("openai_api_key"))
    return {
        "has_api_key": has_key,
        "model": cfg.get("model", "openai/gpt-4o-mini"),
        "base_url": cfg.get("base_url", ""),
        "mode": "live" if has_key else "demo"
    }

@app.post("/api/config")
async def update_configuration(cfg: ConfigUpdate):
    save_config({"openai_api_key": cfg.openai_api_key, "model": cfg.model, "base_url": cfg.base_url})
    # Rebuild LLM connections
    return {"message": "Configuration saved! Agents are now using live AI." if cfg.openai_api_key else "Running in demo mode."}

@app.get("/api/stats")
async def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_sessions")
    total_sessions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM achievements")
    total_achievements = c.fetchone()[0]
    c.execute("SELECT SUM(xp_value) FROM achievements")
    total_xp = c.fetchone()[0] or 0
    conn.close()
    return {
        "total_students": total_students,
        "total_sessions": total_sessions,
        "total_achievements": total_achievements,
        "total_xp": total_xp
    }

@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """Generate speech audio for teacher responses using OpenAI TTS."""
    cfg = get_config()
    api_key = cfg.get("openai_api_key", "")
    voice = TTS_VOICES.get(req.agent_key, "nova")
    lang = TTS_LANG.get(req.agent_key, "en-US")

    # Strip markdown/emojis for cleaner audio
    import re
    clean_text = re.sub(r'\*+', '', req.text)
    clean_text = re.sub(r'#+\s', '', clean_text)
    clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
    clean_text = clean_text[:4096]  # OpenAI TTS limit

    base_url = cfg.get("base_url", "")
    # Skip OpenAI TTS when using a custom base_url (e.g. OpenRouter) — fall back to browser
    if not api_key or (base_url and "openai" not in base_url):
        return JSONResponse({
            "mode": "browser",
            "lang": lang,
            "voice_hint": voice,
            "text": clean_text,
            "agent_name": PERSONALITIES.get(req.agent_key, {}).get("name", "Teacher")
        })

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=clean_text,
            response_format="mp3"
        )
        audio_bytes = response.content
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        logger.info(f'"action": "tts", "agent": "{req.agent_key}", "chars": {len(clean_text)}')
        return JSONResponse({
            "mode": "openai",
            "audio_b64": audio_b64,
            "voice": voice,
            "agent_name": PERSONALITIES.get(req.agent_key, {}).get("name", "Teacher")
        })
    except Exception as e:
        logger.error(f'"tts_error": "{e}", "agent": "{req.agent_key}"')
        # Fallback to browser TTS on any error
        return JSONResponse({
            "mode": "browser",
            "lang": lang,
            "voice_hint": voice,
            "text": clean_text,
            "agent_name": PERSONALITIES.get(req.agent_key, {}).get("name", "Teacher")
        })

@app.get("/api/tts/voices")
async def get_tts_voices():
    """Return TTS voice config for all teachers."""
    return {k: {"voice": TTS_VOICES.get(k, "nova"), "lang": TTS_LANG.get(k, "en-US")}
            for k in PERSONALITIES}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=3001, reload=False)
