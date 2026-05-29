"""
Unilag Aggregate Score Calculator Telegram Bot
Calculates aggregate using JAMB, O'Level (WAEC/NECO), and Post-UTME scores,
then compares against real per-department cutoff marks.
"""

import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
(
    FACULTY,
    DEPARTMENT,
    JAMB_SCORE,
    OLEVEL_GRADES,
    POST_UTME,
) = range(5)

# ---------------------------------------------------------------------------
# Unilag aggregate formula
#   JAMB / 8                       → out of 50
#   Best-5 O'Level (scaled to 20)  → out of 20
#   Post-UTME × 0.4                → out of 40
#   Total                          → out of 110
# ---------------------------------------------------------------------------

OLEVEL_GRADE_POINTS = {
    "A1": 6, "B2": 5, "B3": 4,
    "C4": 3, "C5": 2, "C6": 1,
    "D7": 0, "E8": 0, "F9": 0,
}

GRADE_KEYBOARD = [["A1", "B2", "B3"], ["C4", "C5", "C6"], ["D7", "E8", "F9"]]

# ---------------------------------------------------------------------------
# Faculty → Department → Cutoff data
# Cutoffs are approximate figures based on published Unilag admission trends.
# Format: { dept_name: cutoff_out_of_110 }
# ---------------------------------------------------------------------------
FACULTY_DATA: dict[str, dict[str, float]] = {
    "🎨 Arts": {
        "English": 50,
        "History & Strategic Studies": 46,
        "Linguistics, African & Asian Studies": 46,
        "Philosophy": 44,
        "French": 45,
        "Creative Arts": 44,
    },
    "💼 Business Administration": {
        "Accounting": 62,
        "Actuarial Science": 62,
        "Business Administration": 58,
        "Finance": 62,
        "Insurance": 56,
    },
    "📚 Education": {
        "Adult Education": 42,
        "Early Childhood Education": 42,
        "Educational Management": 42,
        "Guidance & Counselling": 43,
        "Human Kinetics & Health Education": 43,
        "Library & Information Science": 43,
        "Science Education": 46,
    },
    "⚙️ Engineering": {
        "Chemical Engineering": 61,
        "Civil Engineering": 75.625,
        "Computer Engineering": 82.875,
        "Computer Science": 83.425,
        "Electrical/Electronics Engineering": 79.5,
        "Mechanical Engineering": 78.525,
        "Metallurgical & Materials Engineering": 56,
        "Systems Engineering": 61,
        "Surveying & Geoinformatics": 56,
    },
    "🏙 Environmental Sciences": {
        "Architecture": 59,
        "Building": 53,
        "Estate Management": 56,
        "Quantity Surveying": 53,
        "Urban & Regional Planning": 51,
    },
    "⚖️ Law": {
        "Law": 66,
    },
    "🏥 Medicine": {
        "Medicine & Surgery (MBBS)": 85.025,
        "Dentistry (BDS)": 71,
        "Nursing Science": 61,
        "Physiotherapy": 59,
        "Radiography": 56,
    },
    "💊 Pharmacy": {
        "Pharmacy": 66,
    },
    "🔬 Sciences": {
        "Biochemistry": 56,
        "Botany": 49,
        "Chemistry": 53,
        "Computer Science": 83.425,
        "Geology": 51,
        "Marine Sciences": 51,
        "Mathematics": 53,
        "Microbiology": 56,
        "Physics": 51,
        "Statistics": 53,
        "Zoology": 49,
    },
    "🌍 Social Sciences": {
        "Economics": 59,
        "Geography": 49,
        "Mass Communication": 61,
        "Political Science": 56,
        "Psychology": 59,
        "Sociology": 53,
    },
}

# Build a flat lookup for convenience: "dept name" → cutoff
DEPT_CUTOFFS: dict[str, int] = {}
for _depts in FACULTY_DATA.values():
    DEPT_CUTOFFS.update(_depts)

# Build keyboard rows for each faculty (≤3 items per row)
def _make_keyboard(items: list[str]) -> list[list[str]]:
    rows = []
    for i in range(0, len(items), 2):
        rows.append(items[i: i + 2])
    return rows

FACULTY_KEYBOARD = _make_keyboard(list(FACULTY_DATA.keys()))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_emoji(text: str) -> str:
    """Remove leading emoji + space from faculty label."""
    return " ".join(text.split()[1:]) if text and not text[0].isalpha() else text


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome to the *Unilag Aggregate Score Calculator!*\n\n"
        "I'll calculate your University of Lagos admission aggregate and compare it "
        "to your *department's cutoff mark*.\n\n"
        "The aggregate is computed from:\n"
        "• 📄 *JAMB UTME score* → max 50 pts\n"
        "• 📝 *O'Level best-5 grades* → max 20 pts\n"
        "• 📊 *Post-UTME score* → max 40 pts\n"
        "• *Total: 110 points*\n\n"
        "Which *faculty* are you applying to?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            FACULTY_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return FACULTY


async def faculty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()
    if chosen not in FACULTY_DATA:
        await update.message.reply_text(
            "⚠️ Please choose a faculty from the keyboard below.",
            reply_markup=ReplyKeyboardMarkup(
                FACULTY_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FACULTY

    context.user_data["faculty"] = chosen
    depts = list(FACULTY_DATA[chosen].keys())
    dept_keyboard = _make_keyboard(depts)

    await update.message.reply_text(
        f"✅ Faculty: *{strip_emoji(chosen)}*\n\n"
        "Now choose your *department*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            dept_keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return DEPARTMENT


async def department_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()
    faculty = context.user_data.get("faculty", "")
    valid_depts = list(FACULTY_DATA.get(faculty, {}).keys())

    if chosen not in valid_depts:
        dept_keyboard = _make_keyboard(valid_depts)
        await update.message.reply_text(
            "⚠️ Please choose a department from the keyboard below.",
            reply_markup=ReplyKeyboardMarkup(
                dept_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return DEPARTMENT

    context.user_data["department"] = chosen
    cutoff = DEPT_CUTOFFS[chosen]
    context.user_data["cutoff"] = cutoff

    await update.message.reply_text(
        f"✅ Department: *{chosen}*\n"
        f"📌 Cutoff mark: *{cutoff} / 110*\n\n"
        "Now enter your *JAMB UTME score* (0 – 400):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return JAMB_SCORE


async def jamb_score_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        score = int(text)
        if not (0 <= score <= 400):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid JAMB score between *0 and 400*:",
            parse_mode="Markdown",
        )
        return JAMB_SCORE

    context.user_data["jamb"] = score
    context.user_data["olevel_grades"] = []
    context.user_data["subject_count"] = 0

    await update.message.reply_text(
        f"✅ JAMB Score: *{score} / 400*\n\n"
        "Now let's record your *O'Level results* (WAEC or NECO).\n"
        "Enter your *best 5 subject grades* one at a time.\n\n"
        "*Subject 1 of 5* — select your grade:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return OLEVEL_GRADES


async def olevel_grades_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    grade = update.message.text.strip().upper()

    if grade not in OLEVEL_GRADE_POINTS:
        await update.message.reply_text(
            "⚠️ Please select a valid grade from the keyboard (A1 – F9).",
            reply_markup=ReplyKeyboardMarkup(
                GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return OLEVEL_GRADES

    context.user_data["olevel_grades"].append(grade)
    context.user_data["subject_count"] += 1
    count = context.user_data["subject_count"]

    if count < 5:
        await update.message.reply_text(
            f"✅ Subject {count}: *{grade}*\n\n"
            f"*Subject {count + 1} of 5* — select your grade:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return OLEVEL_GRADES

    await update.message.reply_text(
        f"✅ Subject 5: *{grade}*\n\n"
        "Last step! Enter your *Post-UTME score* (0 – 100):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return POST_UTME


async def post_utme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        score = float(text)
        if not (0 <= score <= 100):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid Post-UTME score between *0 and 100*:",
            parse_mode="Markdown",
        )
        return POST_UTME

    context.user_data["post_utme"] = score

    # ---- Retrieve stored data ----
    jamb         = context.user_data["jamb"]
    grades       = context.user_data["olevel_grades"]
    faculty_name = strip_emoji(context.user_data["faculty"])
    dept_name    = context.user_data["department"]
    cutoff       = context.user_data["cutoff"]

    # ---- Calculate components ----
    jamb_component    = jamb / 8                          # out of 50
    olevel_points     = sum(OLEVEL_GRADE_POINTS[g] for g in grades)
    olevel_component  = (olevel_points / 30) * 20         # out of 20
    post_utme_comp    = score * 0.4                       # out of 40
    aggregate         = jamb_component + olevel_component + post_utme_comp

    # ---- Per-grade breakdown ----
    grade_lines = "\n".join(
        f"  {i+1}. {g} ({OLEVEL_GRADE_POINTS[g]} pts)"
        for i, g in enumerate(grades)
    )

    # ---- Gap analysis ----
    gap = aggregate - cutoff
    if gap >= 5:
        verdict = (
            "🟢 *Well above cutoff!*\n"
            f"You are *{gap:.2f} points above* the {dept_name} cutoff. "
            "Your chances of admission look very strong. 🎉"
        )
    elif gap >= 0:
        verdict = (
            "🟡 *Above cutoff — but close.*\n"
            f"You are *{gap:.2f} points above* the {dept_name} cutoff. "
            "You qualify, but competition may be tight. Stay hopeful!"
        )
    elif gap >= -5:
        verdict = (
            "🟠 *Just below cutoff.*\n"
            f"You are *{abs(gap):.2f} points below* the {dept_name} cutoff. "
            "This is very close — a slightly better Post-UTME performance "
            "could have made the difference. Consider supplementary admission or "
            "a related department."
        )
    else:
        verdict = (
            "🔴 *Below cutoff.*\n"
            f"You are *{abs(gap):.2f} points below* the {dept_name} cutoff. "
            "You may want to consider departments with lower cutoffs, "
            "improve your Post-UTME score, or explore other universities."
        )

    # ---- Suggest alternatives if below cutoff ----
    alternatives = []
    if gap < 0:
        for dept, co in sorted(DEPT_CUTOFFS.items(), key=lambda x: x[1]):
            if aggregate >= co and dept != dept_name:
                alternatives.append(f"  • {dept} (cutoff: {co})")
            if len(alternatives) == 3:
                break

    alt_section = ""
    if alternatives:
        alt_section = (
            "\n\n💡 *Departments you currently qualify for:*\n"
            + "\n".join(alternatives)
        )

    result_message = (
        "🎓 *UNILAG Aggregate Score Result*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏛 Faculty: *{faculty_name}*\n"
        f"📖 Department: *{dept_name}*\n"
        f"📌 Dept. Cutoff: *{cutoff} / 110*\n\n"
        "*Score Breakdown:*\n"
        f"📄 JAMB: *{jamb}/400* → {jamb_component:.2f}/50\n"
        f"📝 O'Level (best 5):\n{grade_lines}\n"
        f"   Subtotal: {olevel_points}/30 → {olevel_component:.2f}/20\n"
        f"📊 Post-UTME: *{score}/100* → {post_utme_comp:.2f}/40\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 *Your Aggregate: {aggregate:.2f} / 110*\n"
        f"📌 *Dept. Cutoff:   {cutoff:.1f} / 110*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{verdict}"
        f"{alt_section}\n\n"
        "_Note: Cutoff marks change yearly. Always confirm on the official "
        "Unilag admission portal (unilag.edu.ng)._\n\n"
        "🔄 Calculate again? Send /start"
    )

    # ---- Save result for /share ----
    context.user_data["last_result"] = {
        "faculty":          faculty_name,
        "department":       dept_name,
        "cutoff":           cutoff,
        "jamb":             jamb,
        "jamb_comp":        jamb_component,
        "olevel_grades":    grades,
        "olevel_points":    olevel_points,
        "olevel_comp":      olevel_component,
        "post_utme":        score,
        "post_utme_comp":   post_utme_comp,
        "aggregate":        aggregate,
        "gap":              gap,
    }

    result_message += "\n📤 Want a shareable card? Send /share"

    await update.message.reply_text(result_message, parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ Calculation cancelled. Send /start to begin again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    faculties = "\n".join(
        f"  {fac} → {', '.join(list(depts.keys())[:3])}{'…' if len(depts) > 3 else ''}"
        for fac, depts in FACULTY_DATA.items()
    )
    await update.message.reply_text(
        "📖 *Unilag Aggregate Calculator — Help*\n\n"
        "Commands:\n"
        "/start — Begin a new calculation\n"
        "/share — Get a shareable summary card of your last result\n"
        "/tips — Post-UTME prep tips for your department\n"
        "/predict — See required Post-UTME per department\n"
        "/compare — See all departments you qualify for\n"
        "/cutoffs — Browse all department cutoff marks\n"
        "/cancel — Cancel the current session\n"
        "/help — Show this message\n\n"
        "*Aggregate formula:*\n"
        "• JAMB ÷ 8 → max 50 pts\n"
        "• O'Level best-5 grades → max 20 pts\n"
        "  (A1=6, B2=5, B3=4, C4=3, C5=2, C6=1)\n"
        "• Post-UTME × 0.4 → max 40 pts\n"
        "• *Total: 110 points*\n\n"
        "*Supported faculties & departments:*\n"
        f"{faculties}\n\n"
        "_Cutoff figures are approximate based on published Unilag admission trends._",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /cutoffs — browse cutoffs states
# ---------------------------------------------------------------------------
BROWSE_FACULTY = 10   # separate state for /cutoffs
COMPARE_SCORE  = 11   # separate state for /compare
PREDICT_JAMB   = 12   # separate states for /predict
PREDICT_OLEVEL = 13
SHARE_NAME     = 14   # separate state for /share
TIPS_FACULTY   = 15   # separate states for /tips
TIPS_DEPT      = 16


async def cutoffs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📋 *Unilag Department Cutoff Marks*\n\n"
        "Choose a faculty to see its cutoff marks:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            FACULTY_KEYBOARD + [["📊 All Faculties"]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return BROWSE_FACULTY


async def cutoffs_faculty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()

    if chosen == "📊 All Faculties":
        # Send one message per faculty to avoid hitting Telegram's 4096-char limit
        await update.message.reply_text(
            "📋 *All Unilag Cutoff Marks* _(out of 110)_\n"
            "_Tap /cutoffs anytime to browse again. /start to calculate._",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        for fac, depts in FACULTY_DATA.items():
            lines = "\n".join(
                f"  • {dept}: *{co}*" for dept, co in sorted(depts.items(), key=lambda x: -x[1])
            )
            await update.message.reply_text(
                f"{fac}\n{lines}",
                parse_mode="Markdown",
            )
        await update.message.reply_text(
            "_Cutoffs are approximate and may change each admission year._\n"
            "👉 /start to calculate your aggregate  |  /cutoffs to browse again",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if chosen not in FACULTY_DATA:
        await update.message.reply_text(
            "⚠️ Please choose a faculty from the keyboard.",
            reply_markup=ReplyKeyboardMarkup(
                FACULTY_KEYBOARD + [["📊 All Faculties"]],
                one_time_keyboard=True,
                resize_keyboard=True,
            ),
        )
        return BROWSE_FACULTY

    depts = FACULTY_DATA[chosen]
    lines = "\n".join(
        f"  • {dept}: *{co}*"
        for dept, co in sorted(depts.items(), key=lambda x: -x[1])
    )
    faculty_label = strip_emoji(chosen)

    await update.message.reply_text(
        f"📋 *{faculty_label} — Cutoff Marks* _(out of 110)_\n\n"
        f"{lines}\n\n"
        "_These are approximate figures based on published Unilag admission trends._\n\n"
        "👉 /start to calculate your aggregate  |  /cutoffs to browse another faculty",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /compare — enter aggregate → see every qualifying department ranked
# ---------------------------------------------------------------------------

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔍 *Department Eligibility Checker*\n\n"
        "Enter your *aggregate score* (0 – 110) and I'll show every Unilag "
        "department you qualify for, ranked from most to least competitive.\n\n"
        "Type your score now:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return COMPARE_SCORE


async def compare_score_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        score = float(text)
        if not (0 <= score <= 110):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a number between *0 and 110*:",
            parse_mode="Markdown",
        )
        return COMPARE_SCORE

    # Build ranked list: qualifying departments sorted by cutoff descending
    qualifying: list[tuple[str, str, float]] = []   # (faculty_label, dept, cutoff)
    for fac, depts in FACULTY_DATA.items():
        for dept, cutoff in depts.items():
            if score >= cutoff:
                qualifying.append((strip_emoji(fac), dept, cutoff))

    qualifying.sort(key=lambda x: -x[2])   # highest cutoff first = most competitive

    if not qualifying:
        # Find the single closest department above the score
        closest = min(DEPT_CUTOFFS.items(), key=lambda x: x[1] - score if x[1] > score else float("inf"))
        await update.message.reply_text(
            f"❌ *No departments found for an aggregate of {score:.3f}.*\n\n"
            f"The closest department above your score is:\n"
            f"  • *{closest[0]}* (cutoff: {closest[1]})\n\n"
            "You would need to improve your score to qualify.\n\n"
            "👉 /start to calculate your aggregate  |  /cutoffs to browse cutoff marks",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # Group results by faculty for readability
    by_faculty: dict[str, list[tuple[str, float]]] = {}
    for fac_label, dept, cutoff in qualifying:
        by_faculty.setdefault(fac_label, []).append((dept, cutoff))

    # Build the reply — split into chunks if many results
    header = (
        f"✅ *Departments you qualify for with {score:.3f} / 110*\n"
        f"_{len(qualifying)} department{'s' if len(qualifying) != 1 else ''} found, "
        f"ranked highest cutoff first_\n\n"
    )

    sections: list[str] = []
    for fac_label, dept_list in by_faculty.items():
        lines = "\n".join(
            f"  • {dept} *(cutoff: {co})*"
            for dept, co in dept_list
        )
        sections.append(f"🏛 *{fac_label}*\n{lines}")

    body = "\n\n".join(sections)
    footer = (
        "\n\n_Cutoffs are approximate. Confirm on unilag.edu.ng._\n"
        "👉 /start to recalculate  |  /compare again  |  /cutoffs to browse"
    )

    full = header + body + footer

    # Telegram max message length is 4096 chars; split if needed
    if len(full) <= 4096:
        await update.message.reply_text(full, parse_mode="Markdown")
    else:
        await update.message.reply_text(header, parse_mode="Markdown")
        for section in sections:
            await update.message.reply_text(section, parse_mode="Markdown")
        await update.message.reply_text(footer.strip(), parse_mode="Markdown")

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /predict — JAMB + O'Level → required Post-UTME per department
# ---------------------------------------------------------------------------

async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "🎯 *Post-UTME Score Predictor*\n\n"
        "Tell me your *JAMB score* and *O'Level grades* and I'll calculate the "
        "*minimum Post-UTME score* you need to hit each department's cutoff.\n\n"
        "Enter your *JAMB UTME score* (0 – 400):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PREDICT_JAMB


async def predict_jamb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        score = int(text)
        if not (0 <= score <= 400):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid JAMB score between *0 and 400*:",
            parse_mode="Markdown",
        )
        return PREDICT_JAMB

    context.user_data["predict_jamb"] = score
    context.user_data["predict_grades"] = []
    context.user_data["predict_count"] = 0

    await update.message.reply_text(
        f"✅ JAMB Score: *{score} / 400*\n\n"
        "Now enter your *O'Level best-5 grades* one at a time.\n\n"
        "*Subject 1 of 5* — select your grade:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return PREDICT_OLEVEL


async def predict_olevel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    grade = update.message.text.strip().upper()

    if grade not in OLEVEL_GRADE_POINTS:
        await update.message.reply_text(
            "⚠️ Please select a valid grade from the keyboard (A1 – F9).",
            reply_markup=ReplyKeyboardMarkup(
                GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return PREDICT_OLEVEL

    context.user_data["predict_grades"].append(grade)
    context.user_data["predict_count"] += 1
    count = context.user_data["predict_count"]

    if count < 5:
        await update.message.reply_text(
            f"✅ Subject {count}: *{grade}*\n\n"
            f"*Subject {count + 1} of 5* — select your grade:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                GRADE_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return PREDICT_OLEVEL

    # All 5 grades collected — compute predictions
    jamb          = context.user_data["predict_jamb"]
    grades        = context.user_data["predict_grades"]

    jamb_comp     = jamb / 8                                    # out of 50
    olevel_pts    = sum(OLEVEL_GRADE_POINTS[g] for g in grades)
    olevel_comp   = (olevel_pts / 30) * 20                     # out of 20
    fixed_score   = jamb_comp + olevel_comp                    # what you already have

    grade_summary = ", ".join(grades)

    # For each department: required Post-UTME = (cutoff - fixed_score) / 0.4
    rows: list[tuple[str, str, float, float, str]] = []
    # (faculty_label, dept, cutoff, required_postutme, status_emoji)
    for fac, depts in FACULTY_DATA.items():
        for dept, cutoff in depts.items():
            required = (cutoff - fixed_score) / 0.4
            if required <= 0:
                status = "🟢"    # already qualify even with 0 Post-UTME
            elif required <= 50:
                status = "🟡"    # achievable (within bottom half)
            elif required <= 75:
                status = "🟠"    # tough but possible
            elif required <= 100:
                status = "🔴"    # very hard
            else:
                status = "⛔"   # mathematically impossible (need >100)
            rows.append((strip_emoji(fac), dept, cutoff, required, status))

    # Sort: impossible last, then by required score ascending (easiest first)
    rows.sort(key=lambda r: (r[3] > 100, r[3]))

    # Group by status tier for clarity
    tiers = {
        "🟢 Already qualify (any Post-UTME score)": [],
        "🟡 Achievable — need 0–50":                [],
        "🟠 Tough — need 51–75":                    [],
        "🔴 Very hard — need 76–100":               [],
        "⛔ Not reachable this cycle":               [],
    }
    for fac_label, dept, cutoff, req, status in rows:
        req_display = "0 ✓" if req <= 0 else f"{req:.1f}"
        entry = f"  • {dept} *(cutoff {cutoff}, need {req_display})*"
        if status == "🟢":
            tiers["🟢 Already qualify (any Post-UTME score)"].append(entry)
        elif status == "🟡":
            tiers["🟡 Achievable — need 0–50"].append(entry)
        elif status == "🟠":
            tiers["🟠 Tough — need 51–75"].append(entry)
        elif status == "🔴":
            tiers["🔴 Very hard — need 76–100"].append(entry)
        else:
            tiers["⛔ Not reachable this cycle"].append(entry)

    header = (
        "🎯 *Post-UTME Score Predictor — Results*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 JAMB: *{jamb}/400* → {jamb_comp:.2f}/50\n"
        f"📝 O'Level ({grade_summary}) → {olevel_comp:.2f}/20\n"
        f"📌 Fixed score (before Post-UTME): *{fixed_score:.2f}*\n\n"
        "Departments are grouped by how achievable they are:\n\n"
    )

    sections: list[str] = []
    for tier_label, entries in tiers.items():
        if entries:
            sections.append(f"*{tier_label}*\n" + "\n".join(entries))

    footer = (
        "\n_Post-UTME scores shown are the minimum needed out of 100. "
        "Cutoffs are approximate — confirm at unilag.edu.ng._\n\n"
        "👉 /start to calculate your full aggregate  |  /predict again  |  /compare"
    )

    full = header + "\n\n".join(sections) + footer

    if len(full) > 4096:
        await update.message.reply_text(header, parse_mode="Markdown")
        for section in sections:
            if section:
                await update.message.reply_text(section, parse_mode="Markdown")
        await update.message.reply_text(footer.strip(), parse_mode="Markdown")
    else:
        await update.message.reply_text(full, parse_mode="Markdown")

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /tips — department-specific Post-UTME preparation advice
# ---------------------------------------------------------------------------

DEPT_TIPS: dict[str, dict] = {
    # ── Arts ──────────────────────────────────────────────────────────────
    "English": {
        "subjects": ["Use of English", "Literature in English"],
        "focus": [
            "Comprehension passages — speed and accuracy",
            "Summary writing and essay techniques",
            "Figures of speech and literary devices",
            "Tenses, concord, and sentence construction",
            "Set texts: prose, drama, poetry",
        ],
        "advice": "Read widely — newspapers, novels, poetry. Practice timed essays. The Unilag Post-UTME tests deep comprehension, so build your vocabulary daily.",
    },
    "History & Strategic Studies": {
        "subjects": ["Use of English", "History / Government"],
        "focus": [
            "Nigerian pre-colonial and colonial history",
            "African history and independence movements",
            "World wars and their impact on Africa",
            "Comprehension and essay writing",
            "Current geopolitical events",
        ],
        "advice": "Use past questions from History and Government. Read a good Nigerian history textbook cover to cover. Current affairs questions are common.",
    },
    "Linguistics, African & Asian Studies": {
        "subjects": ["Use of English", "Literature / Any language"],
        "focus": [
            "Elements of phonetics and phonology",
            "Sentence structure and grammar",
            "Comprehension and essay precision",
            "African cultural and social concepts",
        ],
        "advice": "Focus heavily on Use of English. Exposure to a second language (French, Yoruba, Hausa, Igbo) gives a helpful background.",
    },
    "Philosophy": {
        "subjects": ["Use of English", "Government / Literature"],
        "focus": [
            "Critical reasoning and argument structure",
            "Comprehension accuracy",
            "Essay clarity and logical flow",
            "Basic logic: deductive vs inductive reasoning",
        ],
        "advice": "Philosophy Post-UTME is largely English-based. Practice writing structured, well-argued essays. Read editorials and opinion columns to sharpen critical thinking.",
    },
    "French": {
        "subjects": ["Use of English", "French"],
        "focus": [
            "French grammar: tenses, conjugation, gender",
            "French comprehension and translation",
            "Vocabulary building (300+ common words)",
            "English essay and comprehension",
        ],
        "advice": "Use French past questions and listen to French audio daily. Apps like Duolingo supplement well. Fluency in spoken French is a huge advantage.",
    },
    "Creative Arts": {
        "subjects": ["Use of English", "Literature / Fine Arts"],
        "focus": [
            "Principles and elements of design",
            "Nigerian and African art history",
            "Colour theory and composition",
            "Literary analysis of dramatic texts",
            "Comprehension and creative writing",
        ],
        "advice": "Build a small portfolio of your art — interviews sometimes feature portfolio review. Study Nigerian art (Aina Onabolu, Ben Enwonwu) for history questions.",
    },

    # ── Business Administration ───────────────────────────────────────────
    "Accounting": {
        "subjects": ["Mathematics", "Economics", "Use of English"],
        "focus": [
            "Financial statements: income, balance sheet, cash flow",
            "Depreciation, ledgers, trial balance",
            "Ratios and basic financial analysis",
            "BODMAS, algebra, indices (Maths)",
            "Micro and macroeconomics basics",
        ],
        "advice": "Practice accounting past questions from JAMB and ICAN introductory. Speed in arithmetic is critical — use mental maths techniques.",
    },
    "Actuarial Science": {
        "subjects": ["Mathematics", "Further Mathematics", "Economics"],
        "focus": [
            "Probability and statistics",
            "Sequences, series, and financial mathematics",
            "Calculus: differentiation and integration",
            "Interest rates and annuities concepts",
            "Economics: demand, supply, elasticity",
        ],
        "advice": "This is the most maths-intensive Business course. Drill past Further Maths questions. Strong algebra and calculus foundations are non-negotiable.",
    },
    "Business Administration": {
        "subjects": ["Mathematics", "Economics", "Use of English"],
        "focus": [
            "Business concepts: marketing, HR, operations",
            "Economics: macro and micro fundamentals",
            "Commercial arithmetic: profit, loss, interest",
            "Comprehension and report writing",
        ],
        "advice": "Read a basic Business Studies and Economics textbook. Stay current with Nigerian business news — the Financial Times or Businessday.",
    },
    "Finance": {
        "subjects": ["Mathematics", "Economics", "Use of English"],
        "focus": [
            "Time value of money, simple and compound interest",
            "Basic statistics: mean, median, mode",
            "Economics: banking, monetary policy, trade",
            "Financial markets overview",
        ],
        "advice": "Finance is quantitative. Daily Maths practice is essential. Understand how Nigerian banks and the CBN work — it appears in economics questions.",
    },
    "Insurance": {
        "subjects": ["Mathematics", "Economics", "Use of English"],
        "focus": [
            "Basic probability and risk concepts",
            "Commercial arithmetic",
            "Economics: demand, supply, elasticity",
            "English comprehension and summary",
        ],
        "advice": "Insurance is less competitive but still requires solid Maths and Economics. Understand the concept of risk, premium, and indemnity.",
    },

    # ── Education ─────────────────────────────────────────────────────────
    "Adult Education": {
        "subjects": ["Use of English", "Any Arts or Social Science subject"],
        "focus": [
            "English comprehension and essay",
            "Basic numeracy and logic",
            "Social studies concepts",
        ],
        "advice": "Focus on Use of English. Demonstrate communication ability — essays matter here.",
    },
    "Early Childhood Education": {
        "subjects": ["Use of English", "Biology / Home Economics"],
        "focus": [
            "Child development milestones",
            "Basic biology: reproduction, nutrition",
            "English comprehension and essay",
        ],
        "advice": "Read on Piaget and Vygotsky's learning theories — they appear in education questions. Strong English is the key differentiator.",
    },
    "Educational Management": {
        "subjects": ["Use of English", "Economics / Government"],
        "focus": [
            "Management principles (planning, organising, leading)",
            "Economics fundamentals",
            "English comprehension",
        ],
        "advice": "Understand basic management and administrative concepts. Nigerian educational policy and UBE are common topics.",
    },
    "Guidance & Counselling": {
        "subjects": ["Use of English", "Biology / Government"],
        "focus": [
            "Basic psychology: Maslow's hierarchy, Freud",
            "Communication and interpersonal skills concepts",
            "English comprehension and summary writing",
        ],
        "advice": "Empathy and communication theory feature in questions. Read introductory psychology materials alongside English practice.",
    },
    "Human Kinetics & Health Education": {
        "subjects": ["Biology", "Use of English", "Chemistry / Physics"],
        "focus": [
            "Human anatomy: muscles, skeletal system",
            "Sports physiology: VO2 max, training principles",
            "Nutrition and diet",
            "First aid and injury management",
            "History of sports and Olympic games",
        ],
        "advice": "This blends Biology and physical education theory. Use waec Biology past questions and supplement with sports science notes.",
    },
    "Library & Information Science": {
        "subjects": ["Use of English", "Any Arts / Social Science"],
        "focus": [
            "Cataloguing and classification concepts",
            "Reference and bibliographic tools",
            "English comprehension and summary",
            "ICT basics in information management",
        ],
        "advice": "English is paramount. Familiarise yourself with the Dewey Decimal System and basic library science vocabulary.",
    },
    "Science Education": {
        "subjects": ["Mathematics", "Physics or Biology or Chemistry"],
        "focus": [
            "Core content of your intended teaching subject",
            "Pedagogy basics: methods of teaching",
            "English comprehension",
        ],
        "advice": "Focus on the science subject you intend to specialise in. Solid content knowledge is tested alongside education theory.",
    },

    # ── Engineering ───────────────────────────────────────────────────────
    "Chemical Engineering": {
        "subjects": ["Mathematics", "Chemistry", "Physics"],
        "focus": [
            "Mole concept, stoichiometry, equilibrium",
            "Organic chemistry: hydrocarbons, polymers",
            "Mechanics: force, pressure, fluid statics",
            "Algebra, logarithms, trigonometry",
            "Thermodynamics basics",
        ],
        "advice": "Chem Eng is Chemistry-heavy. Master mole calculations and organic reactions. Physics mechanics is also frequently tested.",
    },
    "Civil Engineering": {
        "subjects": ["Mathematics", "Physics", "Chemistry"],
        "focus": [
            "Statics: forces, moments, equilibrium",
            "Mechanics: motion, work, energy",
            "Trigonometry and coordinate geometry",
            "Basic material properties (stress, strain)",
            "Algebra and calculus fundamentals",
        ],
        "advice": "Physics mechanics is the backbone of Civil Eng Post-UTME. Practise force diagrams and resolving vectors. Strong Maths is equally vital.",
    },
    "Computer Engineering": {
        "subjects": ["Mathematics", "Physics", "Further Mathematics"],
        "focus": [
            "Number systems: binary, octal, hexadecimal",
            "Boolean algebra and logic gates",
            "Electricity and magnetism (Physics)",
            "Calculus: differentiation and integration",
            "Sequences, series, and probability",
        ],
        "advice": "Number systems and logic gates separate Comp Eng candidates. Practice binary conversions daily. The cutoff (82.875) demands near-perfect scores.",
    },
    "Electrical/Electronics Engineering": {
        "subjects": ["Mathematics", "Physics", "Further Mathematics"],
        "focus": [
            "Electricity: Ohm's law, Kirchhoff's laws, circuits",
            "Electromagnetism: inductance, capacitance",
            "Number systems and digital logic",
            "Calculus and trigonometry",
            "Waves and optics",
        ],
        "advice": "Deep Physics electricity knowledge is essential. Build circuits mentally and practise Kirchhoff's laws with multi-loop problems.",
    },
    "Mechanical Engineering": {
        "subjects": ["Mathematics", "Physics", "Further Mathematics"],
        "focus": [
            "Mechanics: kinematics, Newton's laws, momentum",
            "Thermodynamics: heat, work, efficiency",
            "Trigonometry and vectors",
            "Calculus: rates of change",
            "Fluid mechanics basics",
        ],
        "advice": "Mechanics problems dominate. Practise resolving forces, energy conservation, and projectile motion until they're second nature.",
    },
    "Metallurgical & Materials Engineering": {
        "subjects": ["Mathematics", "Chemistry", "Physics"],
        "focus": [
            "Atomic structure and bonding",
            "Properties of metals and alloys",
            "Electrochemistry and corrosion",
            "Mechanics: stress and strain",
            "Algebra and logarithms",
        ],
        "advice": "Less well-known but a strong career path. Focus on Chemistry (atomic structure, bonding) and Physics mechanics equally.",
    },
    "Systems Engineering": {
        "subjects": ["Mathematics", "Physics", "Further Mathematics"],
        "focus": [
            "Control systems basics",
            "Logic and Boolean algebra",
            "Calculus and linear algebra",
            "Mechanics and electricity (Physics)",
        ],
        "advice": "Similar preparation to Computer and Electrical Engineering. Broad maths and physics foundation is key.",
    },
    "Surveying & Geoinformatics": {
        "subjects": ["Mathematics", "Physics", "Geography"],
        "focus": [
            "Trigonometry: bearings, angles, distances",
            "Coordinate geometry and map projections",
            "Physics: optics and measurement",
            "Basic GIS and remote sensing concepts",
        ],
        "advice": "Trigonometry is central to surveying. Ensure you can handle bearing and traverse problems. Geography of Nigeria features in some questions.",
    },

    # ── Environmental Sciences ────────────────────────────────────────────
    "Architecture": {
        "subjects": ["Mathematics", "Physics", "Fine Arts / Technical Drawing"],
        "focus": [
            "Technical drawing: projection, sectioning",
            "History of architecture: styles and periods",
            "Physics: structures, forces, materials",
            "Aesthetics and design principles",
            "Nigerian and African architecture",
        ],
        "advice": "A drawing/creative aptitude test is sometimes included. Practise technical drawing and study architectural history alongside Physics.",
    },
    "Building": {
        "subjects": ["Mathematics", "Physics", "Chemistry"],
        "focus": [
            "Building materials: concrete, timber, steel",
            "Structural concepts: loads, supports",
            "Mathematics: measurement and estimation",
            "Basic chemistry of construction materials",
        ],
        "advice": "Understand how buildings are constructed physically. Visit a construction site if possible — practical awareness helps in descriptive questions.",
    },
    "Estate Management": {
        "subjects": ["Mathematics", "Economics", "Use of English"],
        "focus": [
            "Basic property valuation concepts",
            "Economics: land, rent, supply and demand",
            "Commercial arithmetic",
            "Nigerian land use and property law overview",
        ],
        "advice": "Read about the Nigerian Land Use Act 1978 — it's a common topic. Economics and Maths questions are straightforward; don't drop marks there.",
    },
    "Quantity Surveying": {
        "subjects": ["Mathematics", "Physics", "Economics"],
        "focus": [
            "Mensuration: areas, volumes, perimeters",
            "Cost estimation and bill of quantities concepts",
            "Basic economics and commercial arithmetic",
            "Physics: forces and materials",
        ],
        "advice": "Strong Maths (especially mensuration) is the core requirement. Understand the concept of bills of quantities and cost planning.",
    },
    "Urban & Regional Planning": {
        "subjects": ["Mathematics", "Geography", "Economics"],
        "focus": [
            "Human and physical geography",
            "Nigerian urbanisation trends and cities",
            "Population statistics and settlement patterns",
            "Basic economics: public goods, externalities",
        ],
        "advice": "Geography knowledge of Nigeria is frequently tested. Understand urban challenges like traffic, housing, and waste in Lagos specifically.",
    },

    # ── Law ───────────────────────────────────────────────────────────────
    "Law": {
        "subjects": ["Use of English", "Government", "Literature / CRS"],
        "focus": [
            "English comprehension, grammar, and essay — extremely high standard",
            "Nigerian constitutional history: 1960, 1963, 1979, 1999 constitutions",
            "Government: arms of government, rule of law, separation of powers",
            "Current Nigerian legal affairs and landmark cases",
            "Logical reasoning and argument analysis",
        ],
        "advice": "Law has one of the highest cutoffs (66). Your Use of English must be near-perfect. Read The Punch and Vanguard law pages. Practice formal essay writing every day.",
    },

    # ── Medicine ─────────────────────────────────────────────────────────
    "Medicine & Surgery (MBBS)": {
        "subjects": ["Biology", "Chemistry", "Physics", "Mathematics"],
        "focus": [
            "Cell biology: organelles, cell division, genetics",
            "Human physiology: circulatory, respiratory, nervous systems",
            "Organic chemistry: amino acids, proteins, carbohydrates",
            "Chemistry: mole concept, reaction kinetics, equilibrium",
            "Physics: optics, electricity, radioactivity",
        ],
        "advice": "The highest cutoff (85.025) demands excellence across all four sciences. Drill past JAMB Biology and Chemistry questions. Use USMLE Step 1 flashcard apps for human physiology — they're excellent supplementary material.",
    },
    "Dentistry (BDS)": {
        "subjects": ["Biology", "Chemistry", "Physics"],
        "focus": [
            "Oral anatomy: teeth types, jaw structure",
            "Human biology: tissues, histology basics",
            "Organic and inorganic chemistry",
            "Infection control and sterilisation concepts",
        ],
        "advice": "Similar preparation to Medicine. Biology and Chemistry are the most weighted. Learn the names and functions of the major teeth types.",
    },
    "Nursing Science": {
        "subjects": ["Biology", "Chemistry", "Use of English"],
        "focus": [
            "Human anatomy and physiology",
            "Nutrition and disease prevention",
            "Basic pharmacology: drug classes and actions",
            "Health and safety, infection control",
            "English comprehension",
        ],
        "advice": "Focus on human body systems — cardiovascular, respiratory, and reproductive. Basic pharmacology (drug categories) is commonly tested.",
    },
    "Physiotherapy": {
        "subjects": ["Biology", "Physics", "Chemistry"],
        "focus": [
            "Musculoskeletal anatomy: joints, muscles, bones",
            "Physics: waves, electricity (modalities)",
            "Human physiology: nervous and muscular systems",
            "Kinesiology basics: movement and gait",
        ],
        "advice": "Know all major muscles and joints of the body. Physics waves and electricity (ultrasound, TENS) have physiotherapy applications that may appear in questions.",
    },
    "Radiography": {
        "subjects": ["Physics", "Chemistry", "Biology"],
        "focus": [
            "Radiation physics: X-rays, ionising radiation",
            "Atomic structure and radioactivity",
            "Medical imaging concepts: MRI, CT, ultrasound",
            "Human anatomy: organ positions and systems",
        ],
        "advice": "Physics is the most critical subject for Radiography. Focus on waves, optics, and radioactivity. Learn the basic imaging modalities and what they measure.",
    },

    # ── Pharmacy ─────────────────────────────────────────────────────────
    "Pharmacy": {
        "subjects": ["Chemistry", "Biology", "Physics", "Mathematics"],
        "focus": [
            "Organic chemistry: functional groups, reactions, drug structures",
            "Biochemistry: enzymes, metabolism, pH",
            "Cell biology and microbiology basics",
            "Pharmacokinetics: absorption, distribution, metabolism",
            "Mathematics: calculations, concentrations, dilutions",
        ],
        "advice": "Chemistry is the backbone of Pharmacy. Master organic reactions and functional groups. Understand how drugs interact with the body at a basic level — it shows depth.",
    },

    # ── Sciences ──────────────────────────────────────────────────────────
    "Biochemistry": {
        "subjects": ["Chemistry", "Biology", "Mathematics"],
        "focus": [
            "Metabolism: glycolysis, Krebs cycle, electron transport",
            "Protein structure and enzyme kinetics",
            "Nucleic acids: DNA replication, transcription, translation",
            "Organic chemistry: functional groups",
            "Cell biology fundamentals",
        ],
        "advice": "Learn metabolic pathways by drawing them out — it helps retention. Biochemistry blends Biology and Chemistry; equally strong preparation in both is essential.",
    },
    "Botany": {
        "subjects": ["Biology", "Chemistry"],
        "focus": [
            "Plant anatomy: cells, tissues, organs",
            "Photosynthesis and plant respiration",
            "Plant reproduction: sexual and asexual",
            "Ecology: ecosystem, food chains, habitats",
            "Taxonomy: classification of plants",
        ],
        "advice": "Focus on JAMB Biology (plant sections) for most of the content. Ecology and plant physiology are the most commonly tested areas.",
    },
    "Chemistry": {
        "subjects": ["Chemistry", "Mathematics", "Physics"],
        "focus": [
            "Mole concept, stoichiometry, gas laws",
            "Organic chemistry: reaction mechanisms",
            "Electrochemistry: electrolysis, cell EMF",
            "Equilibrium: Le Chatelier's principle, Ksp",
            "Periodic table trends and bonding",
        ],
        "advice": "Master the mole concept — it underpins at least 30% of Chemistry questions. Use JAMB Chemistry past questions from 2000–2024 as your primary resource.",
    },
    "Computer Science": {
        "subjects": ["Mathematics", "Physics", "Further Mathematics"],
        "focus": [
            "Number systems: binary, hexadecimal, octal conversions",
            "Boolean algebra, logic gates, truth tables",
            "Algorithms and flowcharts",
            "Data structures basics: arrays, stacks, queues",
            "Calculus, statistics, and probability",
        ],
        "advice": "The highest cutoff in Sciences (83.425). Number systems and logic gates are almost always tested. Write simple algorithms and trace them. Competitive — leave no mark on the table.",
    },
    "Geology": {
        "subjects": ["Chemistry", "Physics", "Mathematics / Geography"],
        "focus": [
            "Rock types: igneous, sedimentary, metamorphic",
            "Plate tectonics and Earth structure",
            "Mineralogy: common minerals and their properties",
            "Chemistry: atomic structure, bonding",
            "Map reading and topographic interpretation",
        ],
        "advice": "Study Nigerian geology — the Niger Delta, Basement Complex, and Chad Basin feature regularly. Map reading from Geography is a hidden advantage.",
    },
    "Marine Sciences": {
        "subjects": ["Biology", "Chemistry", "Physics / Geography"],
        "focus": [
            "Ocean zones and ecosystems",
            "Marine biology: fish, plankton, coral",
            "Physical oceanography: currents, tides, waves",
            "Nigerian coastal geography",
            "Ecology and environmental science",
        ],
        "advice": "Read on Nigeria's coastal regions and the Niger Delta ecosystem. Standard Biology and Chemistry past questions cover most of the content.",
    },
    "Mathematics": {
        "subjects": ["Mathematics", "Further Mathematics", "Physics"],
        "focus": [
            "Calculus: limits, differentiation, integration",
            "Algebra: polynomials, surds, matrices",
            "Statistics and probability",
            "Sequences, series, and permutations",
            "Coordinate geometry and trigonometry",
        ],
        "advice": "Every mark matters. Use Further Maths WAEC past questions (2010–2024) as your bible. Speed and accuracy under timed conditions distinguish top scorers.",
    },
    "Microbiology": {
        "subjects": ["Biology", "Chemistry"],
        "focus": [
            "Bacteria: structure, classification, reproduction",
            "Viruses: structure, replication cycles",
            "Fungi and parasites",
            "Sterilisation, aseptic technique",
            "Immunity and vaccine concepts",
        ],
        "advice": "Learn the major bacteria and virus families and the diseases they cause. Sterilisation methods (autoclave, UV, chemical) are popular exam topics.",
    },
    "Physics": {
        "subjects": ["Physics", "Mathematics", "Further Mathematics"],
        "focus": [
            "Mechanics: kinematics, Newton's laws, energy",
            "Waves: SHM, sound, light",
            "Electricity: circuits, electromagnetic induction",
            "Modern physics: photoelectric effect, radioactivity",
            "Calculus and vectors",
        ],
        "advice": "Understand derivations, not just formulas. Examiners love conceptual questions. Use Nelkon & Parker alongside JAMB past questions.",
    },
    "Statistics": {
        "subjects": ["Mathematics", "Further Mathematics"],
        "focus": [
            "Probability: permutations, combinations, distributions",
            "Hypothesis testing and confidence intervals",
            "Data presentation: histograms, frequency tables",
            "Regression and correlation",
            "Calculus for continuous distributions",
        ],
        "advice": "Statistics is heavily quantitative. Use Further Maths past questions and supplement with an introductory statistics textbook. SPSS concepts may appear.",
    },
    "Zoology": {
        "subjects": ["Biology", "Chemistry"],
        "focus": [
            "Animal kingdom: classification and characteristics",
            "Vertebrate anatomy: fish, amphibians, reptiles, birds, mammals",
            "Animal reproduction and development",
            "Ecology: food webs, population dynamics",
            "Genetics and heredity",
        ],
        "advice": "Use JAMB Biology past questions — they cover 90% of Zoology content. Focus on animal classification and comparative anatomy of vertebrates.",
    },

    # ── Social Sciences ───────────────────────────────────────────────────
    "Economics": {
        "subjects": ["Economics", "Mathematics", "Use of English"],
        "focus": [
            "Micro: demand, supply, elasticity, market structures",
            "Macro: GDP, inflation, monetary and fiscal policy",
            "Nigerian economy: CBN, NNPC, trade balance",
            "Commercial arithmetic: percentage, interest, index numbers",
            "Comprehension and essay writing",
        ],
        "advice": "Read a full Economics textbook (Lipsey or a Nigerian A-level text). Stay current with CBN policy announcements and Nigeria's economic data.",
    },
    "Geography": {
        "subjects": ["Geography", "Mathematics / Economics"],
        "focus": [
            "Physical geography: climate, geomorphology, hydrology",
            "Human geography: population, settlement, migration",
            "Nigerian geography: states, rivers, climate zones",
            "Map reading: scale, relief, grid references",
            "Statistics: population graphs, data interpretation",
        ],
        "advice": "Know Nigeria's geography inside out — every state, major river, and climate zone. Map reading skills are tested practically, so practice with topographic maps.",
    },
    "Mass Communication": {
        "subjects": ["Use of English", "Literature / Government"],
        "focus": [
            "History of mass media: print, broadcast, digital",
            "Nigerian media landscape: NTA, FRCN, newspapers",
            "Media theories: agenda setting, gatekeeping",
            "News writing: inverted pyramid structure",
            "English grammar, comprehension, and essay",
        ],
        "advice": "Read Nigerian newspapers daily (Punch, Vanguard, Guardian). Understand how news is gathered and presented. Media ethics and law occasionally feature.",
    },
    "Political Science": {
        "subjects": ["Government", "Use of English", "Economics / History"],
        "focus": [
            "Nigerian government: executive, legislature, judiciary",
            "Constitutional development: 1960 to 1999",
            "Political concepts: democracy, sovereignty, federalism",
            "International relations: UN, AU, ECOWAS, NATO",
            "Current Nigerian political affairs",
        ],
        "advice": "Know the 1999 Constitution key sections. Follow Nigerian politics actively — recent events appear in questions. Government past questions are your best resource.",
    },
    "Psychology": {
        "subjects": ["Biology", "Use of English", "Government / Literature"],
        "focus": [
            "Major theories: Freud, Piaget, Skinner, Maslow",
            "Brain anatomy and neuroscience basics",
            "Research methods: experimental, survey, case study",
            "Perception, memory, and learning",
            "Abnormal psychology: anxiety, depression, schizophrenia overview",
        ],
        "advice": "Read an introductory psychology text (Atkinson & Hilgard or similar). Memorise the major theorists and their contributions — they're directly tested.",
    },
    "Sociology": {
        "subjects": ["Use of English", "Government / Economics", "Literature"],
        "focus": [
            "Sociological theories: Durkheim, Weber, Marx",
            "Social institutions: family, education, religion",
            "Nigerian social issues: poverty, urbanisation, crime",
            "Research methods: qualitative vs quantitative",
            "Comprehension and essay writing",
        ],
        "advice": "Understand the three founding theorists deeply — questions on their ideas are almost guaranteed. Relate sociological concepts to Nigerian society for essay questions.",
    },
}

# Build a set of all known dept names for quick lookup
_ALL_KNOWN_DEPTS = set(DEPT_TIPS.keys())


async def tips_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # If user just completed /start, offer their dept directly
    last = context.user_data.get("last_result")
    if last and last.get("department") in _ALL_KNOWN_DEPTS:
        dept = last["department"]
        context.user_data["tips_shortcut"] = dept
        await update.message.reply_text(
            f"📚 *Post-UTME Prep Tips*\n\n"
            f"Your last calculation was for *{dept}*.\n"
            f"Show tips for this department, or choose another faculty?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [[f"✅ Yes — {dept[:30]}"], ["🔄 Choose a different faculty"]],
                one_time_keyboard=True,
                resize_keyboard=True,
            ),
        )
    else:
        context.user_data.pop("tips_shortcut", None)
        await update.message.reply_text(
            "📚 *Post-UTME Prep Tips*\n\n"
            "Choose a faculty to browse department tips:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                FACULTY_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
    return TIPS_FACULTY


async def tips_faculty_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()

    # Shortcut: user confirmed their last department
    shortcut = context.user_data.get("tips_shortcut")
    if shortcut and chosen.startswith("✅ Yes"):
        return await _send_tips(update, shortcut)

    # Reset shortcut if they chose "different faculty"
    context.user_data.pop("tips_shortcut", None)

    # Strip leading "🔄 Choose a different faculty" fallthrough
    if chosen.startswith("🔄"):
        await update.message.reply_text(
            "Choose a faculty:",
            reply_markup=ReplyKeyboardMarkup(
                FACULTY_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return TIPS_FACULTY

    if chosen not in FACULTY_DATA:
        await update.message.reply_text(
            "⚠️ Please choose a faculty from the keyboard.",
            reply_markup=ReplyKeyboardMarkup(
                FACULTY_KEYBOARD, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return TIPS_FACULTY

    context.user_data["tips_faculty"] = chosen
    depts = list(FACULTY_DATA[chosen].keys())
    await update.message.reply_text(
        f"✅ Faculty: *{strip_emoji(chosen)}*\n\nNow choose your department:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            _make_keyboard(depts), one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return TIPS_DEPT


async def tips_dept_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chosen = update.message.text.strip()
    faculty = context.user_data.get("tips_faculty", "")
    valid = list(FACULTY_DATA.get(faculty, {}).keys())

    if chosen not in valid:
        await update.message.reply_text(
            "⚠️ Please choose a department from the keyboard.",
            reply_markup=ReplyKeyboardMarkup(
                _make_keyboard(valid), one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return TIPS_DEPT

    return await _send_tips(update, chosen)


async def _send_tips(update: Update, dept: str) -> int:
    tips = DEPT_TIPS.get(dept)
    cutoff = DEPT_CUTOFFS.get(dept, "N/A")

    if not tips:
        await update.message.reply_text(
            f"ℹ️ No specific tips for *{dept}* yet.\n\n"
            "General advice: drill JAMB past questions for your subject combination, "
            "focus on past Post-UTME papers, and practise timed conditions.\n\n"
            "👉 /start to calculate your aggregate",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    subjects_str = " • ".join(tips["subjects"])
    focus_str    = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(tips["focus"]))

    msg = (
        f"📚 *Post-UTME Prep Tips — {dept}*\n"
        f"📌 Cutoff: *{cutoff} / 110*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📖 *Key subjects tested:*\n"
        f"  {subjects_str}\n\n"
        f"🎯 *What to focus on:*\n"
        f"{focus_str}\n\n"
        f"💡 *Expert advice:*\n"
        f"_{tips['advice']}_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👉 /start to calculate  |  /predict to set score targets  |  /tips for another dept"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /share — generate a screenshot-ready summary card from the last /start result
# ---------------------------------------------------------------------------

async def share_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data.get("last_result"):
        await update.message.reply_text(
            "⚠️ No result found.\n\n"
            "Please run /start first to calculate your aggregate, "
            "then send /share to get your card.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📤 *Share Your Result*\n\n"
        "What name should appear on the card?\n"
        "_(Type your first name or full name)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SHARE_NAME


async def share_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Please enter a name:")
        return SHARE_NAME

    r = context.user_data["last_result"]

    gap       = r["gap"]
    aggregate = r["aggregate"]
    cutoff    = r["cutoff"]

    if gap >= 5:
        status_line = "✅ ABOVE CUTOFF"
        bar_filled  = min(int((aggregate / 110) * 20), 20)
    elif gap >= 0:
        status_line = "🟡 ABOVE — CLOSE CALL"
        bar_filled  = min(int((aggregate / 110) * 20), 20)
    elif gap >= -5:
        status_line = "🟠 JUST BELOW CUTOFF"
        bar_filled  = min(int((aggregate / 110) * 20), 20)
    else:
        status_line = "❌ BELOW CUTOFF"
        bar_filled  = min(int((aggregate / 110) * 20), 20)

    bar_empty = 20 - bar_filled
    progress_bar = "█" * bar_filled + "░" * bar_empty

    olevel_str = "  ".join(r["olevel_grades"])

    # Box width: 34 chars inner content
    W = 36

    def row(label: str, value: str) -> str:
        content = f" {label}: {value}"
        padding = W - len(content) - 1
        return f"║{content}{' ' * max(padding, 0)}║"

    def divider() -> str:
        return f"╠{'═' * W}╣"

    def blank() -> str:
        return f"║{' ' * W}║"

    def centered(text: str) -> str:
        pad_total = W - len(text)
        pad_left  = pad_total // 2
        pad_right = pad_total - pad_left
        return f"║{' ' * pad_left}{text}{' ' * pad_right}║"

    card_lines = [
        f"╔{'═' * W}╗",
        centered("🎓 UNILAG AGGREGATE RESULT"),
        f"╠{'═' * W}╣",
        blank(),
        row("👤 Name",       name[:28]),
        row("🏛 Faculty",    r["faculty"][:26]),
        row("📖 Dept",       r["department"][:26]),
        blank(),
        f"╠{'═' * W}╣",
        blank(),
        row("📄 JAMB",       f"{r['jamb']}/400  →  {r['jamb_comp']:.2f}/50"),
        row("📝 O'Level",    f"{olevel_str}  →  {r['olevel_comp']:.2f}/20"),
        row("📊 Post-UTME",  f"{r['post_utme']:.0f}/100  →  {r['post_utme_comp']:.2f}/40"),
        blank(),
        f"╠{'═' * W}╣",
        blank(),
        centered(f"AGGREGATE:  {aggregate:.3f} / 110"),
        centered(f"CUTOFF  :   {cutoff} / 110"),
        blank(),
        centered(f"[{progress_bar}]"),
        blank(),
        centered(status_line),
        blank(),
        f"╠{'═' * W}╣",
        centered("unilag.edu.ng  |  @UnilagAggBot"),
        f"╚{'═' * W}╝",
    ]

    card = "```\n" + "\n".join(card_lines) + "\n```"

    await update.message.reply_text(
        f"📤 *Here's your result card, {name}!*\n\n"
        f"{card}\n\n"
        "_Screenshot this and share with friends 📸_\n\n"
        "👉 /start to recalculate  |  /predict  |  /compare",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FACULTY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, faculty_handler)],
            DEPARTMENT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, department_handler)],
            JAMB_SCORE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, jamb_score_handler)],
            OLEVEL_GRADES: [MessageHandler(filters.TEXT & ~filters.COMMAND, olevel_grades_handler)],
            POST_UTME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, post_utme_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    cutoffs_handler = ConversationHandler(
        entry_points=[CommandHandler("cutoffs", cutoffs_command)],
        states={
            BROWSE_FACULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, cutoffs_faculty_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    compare_handler = ConversationHandler(
        entry_points=[CommandHandler("compare", compare_command)],
        states={
            COMPARE_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_score_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    predict_handler = ConversationHandler(
        entry_points=[CommandHandler("predict", predict_command)],
        states={
            PREDICT_JAMB:   [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_jamb_handler)],
            PREDICT_OLEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_olevel_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    share_handler = ConversationHandler(
        entry_points=[CommandHandler("share", share_command)],
        states={
            SHARE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, share_name_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    tips_handler = ConversationHandler(
        entry_points=[CommandHandler("tips", tips_command)],
        states={
            TIPS_FACULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, tips_faculty_handler)],
            TIPS_DEPT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tips_dept_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(cutoffs_handler)
    app.add_handler(compare_handler)
    app.add_handler(predict_handler)
    app.add_handler(share_handler)
    app.add_handler(tips_handler)
    app.add_handler(CommandHandler("help", help_command))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
