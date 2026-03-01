# Lecturaun Accelerated Learning

> AI-powered K-6 homeschool curriculum platform with personality-driven teachers, blockchain achievements, and a LangGraph multi-agent system.

## 🎓 What is Lecturaun?

Lecturaun is an accelerated homeschool curriculum platform (K-6) where every subject is taught by a unique AI teacher with a distinct personality — not a generic chatbot.

## 🧑‍🏫 Meet the Teachers

| Teacher | Subject | Personality |
|---------|---------|-------------|
| 🇨🇺 Lolita Vasquez Ramon | Spanish | Cuban firebrand, rolls her RRR's, calls students "mija/mijo" |
| 🏀 Big T Thomas Okafor | Math | Nigerian-American from Chicago, basketball analogies, pure swagger |
| 🔬 Dr. Yuki Chen | Science | Perpetually EXCITED about EVERYTHING. "WAIT. DO YOU SEE WHAT JUST HAPPENED?!" |
| 📖 Finn McAllister | Reading & Writing | Scottish storyteller, dramatic, literary, gets emotional about good writing |
| 🌍 Amara Diallo | History | West African-American, connects everything to today, "let me tell you the REAL story" |
| 🎮 Game Master Jordan | Assessment | Non-binary gamification expert, turns every test into an RPG quest |
| 🧑‍🏫 Coach Patty Hernandez | Teacher Guide | 22-year classroom veteran, helps non-expert parents deliver lessons |

## 🚀 Features

- **Multi-Agent LangGraph Architecture** — each teacher is a LangGraph StateGraph node
- **Student Management** — add K-6 students with grade, age, gender tracking
- **Interactive Classroom** — real-time chat with any teacher
- **TTS Voice** — each teacher has a unique OpenAI TTS voice (with browser fallback)
- **Blockchain Achievements** — SHA-256 hashed credentials for every milestone
- **XP & Leveling** — gamified progress tracking
- **OpenRouter Support** — works with any OpenAI-compatible API

## 📦 Project Structure

```
lecturaun/          # Main K-6 learning platform (port 3001)
├── app.py          # FastAPI + LangGraph backend
├── requirements.txt
└── static/
    └── index.html  # Dashboard UI

buzzhq/             # Marketing Command Center (port 3002)
├── app.py          # 5 marketing agents
└── static/
    └── index.html

Brand_Voice_Profile.md  # Lecturaun brand voice guidelines
```

## ⚙️ Setup

```bash
pip install -r lecturaun/requirements.txt
cd lecturaun && python app.py        # Runs on port 3001
cd buzzhq && python app.py           # Runs on port 3002
```

Then open `http://localhost:3001` and go to **Settings** to add your API key.

## 🤖 AI Configuration

Supports **OpenAI** and **OpenRouter** (or any OpenAI-compatible endpoint):
- **OpenAI:** Just add your `sk-...` key in Settings
- **OpenRouter:** Add key + set Base URL to `https://openrouter.ai/api/v1`, then pick any model

## 🍌 Buzz HQ — Marketing Command Center

A separate 5-agent marketing team:
- **Buzz Nakamura** — Guerrilla hype agent, Reddit/Discord invasion specialist
- **Valentina Cross** — Content director, cinematic copy
- **Rex Holloway** — SEO & community strategist  
- **Mira Osei** — Evangelist manager, superfan builder
- **Dash Kowalski** — Analytics, brutally honest KPI tracker

## 📄 License

MIT
