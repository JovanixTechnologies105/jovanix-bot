# jovanix-bot 🎓

**Unilag Aggregate Score Calculator Telegram Bot**

A Telegram bot that helps Nigerian university applicants calculate their University of Lagos (UNILAG) admission aggregate score and compare it against real 2025 department cutoff marks.

## Features

| Command | Description |
|---------|-------------|
| `/start` | Step-by-step aggregate calculation with cutoff verdict |
| `/tips` | Department-specific Post-UTME preparation advice |
| `/share` | Screenshot-ready summary card of your result |
| `/predict` | JAMB + O'Level → minimum Post-UTME needed per department |
| `/compare` | Enter your aggregate → all qualifying departments ranked |
| `/cutoffs` | Browse cutoff marks by faculty or all at once |
| `/help` | Formula explanation + full command list |

## Aggregate Formula

| Component | Calculation | Max Points |
|-----------|------------|------------|
| JAMB score | JAMB ÷ 8 | 50 |
| O'Level (best 5 subjects) | Scaled from 30 pts | 20 |
| Post-UTME | Score × 0.4 | 40 |
| **Total** | | **110** |

**O'Level grade points:** A1=6, B2=5, B3=4, C4=3, C5=2, C6=1

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r bot/requirements.txt
   ```
3. Set your Telegram bot token as an environment variable:
   ```bash
   export TELEGRAM_BOT_TOKEN=your_token_here
   ```
   Get a token from [@BotFather](https://t.me/BotFather) on Telegram.

4. Run the bot:
   ```bash
   python bot/bot.py
   ```

## Covered Faculties & Departments

- 🎨 **Arts** — English, History, Linguistics, Philosophy, French, Creative Arts
- 💼 **Business Administration** — Accounting, Actuarial Science, Business Admin, Finance, Insurance
- 📚 **Education** — 7 specialisations
- ⚙️ **Engineering** — Chemical, Civil, Computer Engineering, Computer Science, Electrical, Mechanical, Metallurgical, Systems, Surveying
- 🏙 **Environmental Sciences** — Architecture, Building, Estate Management, Quantity Surveying, Urban Planning
- ⚖️ **Law**
- 🏥 **Medicine** — MBBS, Dentistry, Nursing, Physiotherapy, Radiography
- 💊 **Pharmacy**
- 🔬 **Sciences** — Biochemistry, Botany, Chemistry, Computer Science, Geology, Marine Sciences, Maths, Microbiology, Physics, Statistics, Zoology
- 🌍 **Social Sciences** — Economics, Geography, Mass Communication, Political Science, Psychology, Sociology

## Cutoff Data

Cutoff marks reflect published 2025 Unilag admission figures. Always verify on the official [Unilag admission portal](https://unilag.edu.ng).

## License

MIT
