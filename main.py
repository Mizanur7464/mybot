import os
import re
from datetime import datetime

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db

load_dotenv()

(
    WAIT_ADD_AMOUNT,
    WAIT_ADD_CATEGORY,
    WAIT_ADD_NOTE,
    WAIT_ADD_NECESSITY,
    WAIT_BUDGET,
    WAIT_EDIT_ID,
    WAIT_EDIT_DATA,
    WAIT_DELETE_ID,
) = range(8)

CATEGORIES = ["খাবার", "পরিবহন", "কেনাকাটা", "বিল", "বিনোদন", "অন্যান্য"]

BTN_ADD = "➕ খরচ যোগ"
BTN_TODAY = "📅 আজকের হিসাব"
BTN_MONTH = "📊 মাসিক হিসাব"
BTN_BUDGET = "🎯 বাজেট সেট"
BTN_EDIT = "✏️ এডিট"
BTN_DELETE = "🗑 ডিলিট"
BTN_REPORT = "📑 রিপোর্ট"
BTN_VIEW_UNNECESSARY = "🔴 অদরকারি"
BTN_CANCEL = "❌ বাতিল"
BTN_SKIP_NOTE = "⏭ স্কিপ"
BTN_NECESSARY = "✅ দরকারি"
BTN_UNNECESSARY = "❌ অদরকারি"

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_ADD), KeyboardButton(BTN_TODAY)],
            [KeyboardButton(BTN_MONTH), KeyboardButton(BTN_BUDGET)],
            [KeyboardButton(BTN_VIEW_UNNECESSARY), KeyboardButton(BTN_REPORT)],
            [KeyboardButton(BTN_EDIT), KeyboardButton(BTN_DELETE)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True,
    )


def category_keyboard() -> ReplyKeyboardMarkup:
    rows = []
    for i in range(0, len(CATEGORIES), 2):
        chunk = CATEGORIES[i : i + 2]
        rows.append([KeyboardButton(c) for c in chunk])
    rows.append([KeyboardButton(BTN_CANCEL)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def note_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_SKIP_NOTE)],
            [KeyboardButton(BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def necessity_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_NECESSARY), KeyboardButton(BTN_UNNECESSARY)],
            [KeyboardButton(BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def format_list(rows, title: str) -> str:
    if not rows:
        return f"{title}\n\nকোনো খরচ নেই।"
    lines = [title, ""]
    for r in rows:
        note = f" — {r['note']}" if r["note"] else ""
        nec = r["necessity"] if "necessity" in r.keys() else "দরকারি"
        tag = "🔴" if nec == "অদরকারি" else "🟢"
        lines.append(f"#{r['id']} ৳{r['amount']:.0f} | {r['category']} {tag}{nec}{note}")
    lines.append("")
    lines.append(f"মোট: ৳{db.sum_amounts(rows):.0f}")
    unnecessary = sum(float(r["amount"]) for r in rows if r["necessity"] == "অদরকারি")
    if unnecessary > 0:
        lines.append(f"অদরকারি: ৳{unnecessary:.0f}")
    return "\n".join(lines)


def parse_amount(text: str) -> float | None:
    text = text.strip().replace("৳", "").replace(",", "").replace(" ", "")
    text = text.translate(BN_DIGITS)
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    amount = float(text)
    if amount <= 0:
        return None
    return amount


def parse_expense_text(text: str) -> tuple[float, str, str] | None:
    text = text.strip()
    m = re.match(
        r"^[৳Tt]?\s*(\d+(?:\.\d+)?)\s+(\S+)(?:\s+(.+))?$",
        text.translate(BN_DIGITS),
    )
    if m:
        amount = float(m.group(1))
        second = m.group(2)
        rest = (m.group(3) or "").strip()
        if second in CATEGORIES:
            return amount, second, rest
        return amount, "অন্যান্য", f"{second} {rest}".strip()
    amount = parse_amount(text)
    if amount is not None:
        return amount, "অন্যান্য", ""
    return None


async def save_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    amount = context.user_data["add_amount"]
    category = context.user_data["add_category"]
    note = context.user_data.get("add_note", "")
    necessity = context.user_data.get("add_necessity", "দরকারি")

    eid = db.add_expense(user_id, amount, category, note, necessity)
    month_total = db.sum_amounts(db.get_month_expenses(user_id))
    budget = db.get_budget(user_id)
    warn = "\n⚠️ মাসিক বাজেট অতিক্রম হয়েছে!" if budget > 0 and month_total > budget else ""
    tip = "\n💡 অদরকারি খরচ কমানোর চেষ্টা করুন।" if necessity == "অদরকারি" else ""

    await update.message.reply_text(
        f"যোগ হয়েছে #{eid}\n৳{amount:.0f} | {category} | {necessity}"
        + (f" — {note}" if note else "")
        + f"\nএই মাসের মোট: ৳{month_total:.0f}{warn}{tip}",
        reply_markup=main_keyboard(),
    )
    context.user_data.pop("add_amount", None)
    context.user_data.pop("add_category", None)
    context.user_data.pop("add_note", None)
    context.user_data.pop("add_necessity", None)
    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "খরচ হিসাব বট\n\nনিচের বাটন দিয়ে কাজ করুন।",
        reply_markup=main_keyboard(),
    )


async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_today_expenses(update.effective_user.id)
    await update.message.reply_text(
        format_list(rows, "📅 আজকের খরচ"),
        reply_markup=main_keyboard(),
    )


async def show_month(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_month_expenses(update.effective_user.id)
    now = datetime.now()
    await update.message.reply_text(
        format_list(rows, f"📊 {now.year}-{now.month:02d} মাসের খরচ"),
        reply_markup=main_keyboard(),
    )


async def show_unnecessary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_month_expenses(update.effective_user.id)
    rows = [r for r in rows if r["necessity"] == "অদরকারি"]
    now = datetime.now()
    await update.message.reply_text(
        format_list(rows, f"🔴 অদরকারি খরচ ({now.year}-{now.month:02d})"),
        reply_markup=main_keyboard(),
    )


async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    rows = db.get_month_expenses(user_id)
    total = db.sum_amounts(rows)
    budget = db.get_budget(user_id)
    breakdown = db.category_breakdown(rows)
    now = datetime.now()
    lines = [
        f"📑 মাসিক রিপোর্ট ({now.year}-{now.month:02d})",
        "",
        f"মোট খরচ: ৳{total:.0f}",
        f"বাজেট: ৳{budget:.0f}",
    ]
    if budget > 0:
        left = budget - total
        lines.append(f"বাকি: ৳{left:.0f}")
        if total > budget:
            lines.append("⚠️ বাজেট অতিক্রম হয়েছে!")
    necessary = sum(float(r["amount"]) for r in rows if r["necessity"] == "দরকারি")
    unnecessary = sum(float(r["amount"]) for r in rows if r["necessity"] == "অদরকারি")
    lines.append(f"দরকারি: ৳{necessary:.0f}")
    lines.append(f"অদরকারি: ৳{unnecessary:.0f}")
    lines.append("")
    lines.append("ক্যাটাগরি:")
    if breakdown:
        for cat, amt in breakdown.items():
            lines.append(f"• {cat}: ৳{amt:.0f}")
    else:
        lines.append("• কোনো খরচ নেই")
    await update.message.reply_text("\n".join(lines), reply_markup=main_keyboard())


async def ask_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "কত টাকা খরচ হয়েছে?\nউদাহরণ: `500` বা `৫০০`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_ADD_AMOUNT


async def receive_add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    amount = parse_amount(text)
    if amount is None:
        await update.message.reply_text(
            "শুধু সংখ্যা দিন। উদাহরণ: `500` বা `৫০০`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_ADD_AMOUNT

    context.user_data["add_amount"] = amount
    await update.message.reply_text(
        f"৳{amount:.0f}\n\nক্যাটাগরি বেছে নিন:",
        reply_markup=category_keyboard(),
    )
    return WAIT_ADD_CATEGORY


async def receive_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    if text not in CATEGORIES:
        await update.message.reply_text(
            "বাটন থেকে ক্যাটাগরি বেছে নিন।",
            reply_markup=category_keyboard(),
        )
        return WAIT_ADD_CATEGORY

    context.user_data["add_category"] = text
    await update.message.reply_text(
        "কারণ লিখুন (ঐচ্ছিক):",
        reply_markup=note_keyboard(),
    )
    return WAIT_ADD_NOTE


async def receive_add_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    if text == BTN_SKIP_NOTE:
        context.user_data["add_note"] = ""
    else:
        context.user_data["add_note"] = text

    await update.message.reply_text(
        "এই খরচটা দরকারি নাকি অদরকারি?",
        reply_markup=necessity_keyboard(),
    )
    return WAIT_ADD_NECESSITY


async def receive_add_necessity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    if text == BTN_NECESSARY:
        context.user_data["add_necessity"] = "দরকারি"
    elif text == BTN_UNNECESSARY:
        context.user_data["add_necessity"] = "অদরকারি"
    else:
        await update.message.reply_text(
            "বাটন থেকে বেছে নিন।",
            reply_markup=necessity_keyboard(),
        )
        return WAIT_ADD_NECESSITY

    return await save_expense(update, context)


async def ask_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current = db.get_budget(update.effective_user.id)
    await update.message.reply_text(
        f"বর্তমান মাসিক বাজেট: ৳{current:.0f}\n\nনতুন বাজেট লিখুন (শুধু সংখ্যা):",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_BUDGET


async def ask_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "এডিট করতে খরচের ID দিন:\nউদাহরণ: `12`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_EDIT_ID


async def ask_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "ডিলিট করতে খরচের ID দিন:\nউদাহরণ: `12`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_DELETE_ID


async def receive_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    amount = parse_amount(text)
    if amount is None:
        await update.message.reply_text(
            "শুধু সংখ্যা দিন। উদাহরণ: `15000` বা `১৫০০০`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_BUDGET

    db.set_budget(update.effective_user.id, amount)
    await update.message.reply_text(
        f"বাজেট সেট: ৳{amount:.0f}",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def receive_edit_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    text = text.translate(BN_DIGITS).lstrip("#")
    if not text.isdigit():
        await update.message.reply_text(
            "শুধু ID দিন। উদাহরণ: `12`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_EDIT_ID

    eid = int(text)
    row = db.get_expense(update.effective_user.id, eid)
    if not row:
        await update.message.reply_text("এই ID পাওয়া যায়নি।", reply_markup=main_keyboard())
        return ConversationHandler.END

    context.user_data["edit_id"] = eid
    await update.message.reply_text(
        f"বর্তমান: #{row['id']} ৳{row['amount']:.0f} | {row['category']}"
        + (f" — {row['note']}" if row["note"] else "")
        + "\n\nনতুন মান লিখুন (যেমন: `300 পরিবহন অফিস`):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_EDIT_DATA


async def receive_edit_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    if text == BTN_CANCEL:
        return await cancel(update, context)

    parsed = parse_expense_text(text)
    if not parsed:
        await update.message.reply_text(
            "সঠিক ফরম্যাট নয়। উদাহরণ: `300 পরিবহন`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_EDIT_DATA

    eid = context.user_data.get("edit_id")
    amount, category, note = parsed
    ok = db.update_expense(update.effective_user.id, eid, amount, category, note)
    if not ok:
        await update.message.reply_text("আপডেট ব্যর্থ।", reply_markup=main_keyboard())
    else:
        await update.message.reply_text(
            f"আপডেট হয়েছে #{eid}\n৳{amount:.0f} | {category}",
            reply_markup=main_keyboard(),
        )
    return ConversationHandler.END


async def receive_delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == BTN_CANCEL:
        return await cancel(update, context)

    text = text.translate(BN_DIGITS).lstrip("#")
    if not text.isdigit():
        await update.message.reply_text(
            "শুধু ID দিন। উদাহরণ: `12`",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_DELETE_ID

    eid = int(text)
    ok = db.delete_expense(update.effective_user.id, eid)
    if ok:
        await update.message.reply_text(f"ডিলিট হয়েছে #{eid}", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("এই ID পাওয়া যায়নি।", reply_markup=main_keyboard())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("add_amount", None)
    context.user_data.pop("add_category", None)
    context.user_data.pop("add_note", None)
    context.user_data.pop("add_necessity", None)
    await update.message.reply_text("বাতিল।", reply_markup=main_keyboard())
    return ConversationHandler.END


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()

    if text == BTN_ADD:
        return await ask_add(update, context)
    if text == BTN_TODAY:
        await show_today(update, context)
        return ConversationHandler.END
    if text == BTN_MONTH:
        await show_month(update, context)
        return ConversationHandler.END
    if text == BTN_VIEW_UNNECESSARY:
        await show_unnecessary(update, context)
        return ConversationHandler.END
    if text == BTN_BUDGET:
        return await ask_budget(update, context)
    if text == BTN_EDIT:
        return await ask_edit(update, context)
    if text == BTN_DELETE:
        return await ask_delete(update, context)
    if text == BTN_REPORT:
        await show_report(update, context)
        return ConversationHandler.END
    if text == BTN_CANCEL:
        return await cancel(update, context)

    await update.message.reply_text(
        "নিচের বাটন ব্যবহার করুন।",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        raise SystemExit("BOT_TOKEN সেট করুন (.env ফাইলে)")

    db.init_db()

    app = Application.builder().token(token).build()

    menu_regex = (
        f"^({re.escape(BTN_ADD)}|{re.escape(BTN_BUDGET)}|"
        f"{re.escape(BTN_EDIT)}|{re.escape(BTN_DELETE)})$"
    )

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(menu_regex), handle_menu),
        ],
        states={
            WAIT_ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_amount)],
            WAIT_ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_category)],
            WAIT_ADD_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_note)],
            WAIT_ADD_NECESSITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_necessity)],
            WAIT_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_budget)],
            WAIT_EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_id)],
            WAIT_EDIT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_data)],
            WAIT_DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_delete_id)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
