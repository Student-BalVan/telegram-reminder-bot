import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен будет из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Хранилище задач
user_tasks = {}


class ReminderTask:
    def __init__(self, user_id, task_text, reminder_time, task_id=None):
        self.task_id = task_id or f"{user_id}_{datetime.now().timestamp()}"
        self.user_id = user_id
        self.task_text = task_text
        self.reminder_time = reminder_time
        self.created_at = datetime.now()
        self.completed = False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = f"""
Привет, {user_name}! 👋

Я бот для напоминаний. 

📝 **Добавить напоминание** - просто напиши мне задачу и время
⏰ **Примеры**:
   - "через 2 часа"
   - "через 30 минут" 
   - "завтра в 10:00"

📋 **Команды**:
/list - все напоминания
/help - справка
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 **Как добавить напоминание:**
• "Сделать домашку через 2 часа"
• "Напомни позвонить маме завтра в 18:00"
• "Через 30 минут проверить почту"
"""
    await update.message.reply_text(help_text)


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_tasks or not user_tasks[user_id]:
        await update.message.reply_text("📭 У вас нет активных напоминаний")
        return

    tasks = user_tasks[user_id]
    task_list = "📋 **Ваши напоминания:**\n\n"
    for i, task in enumerate(tasks, 1):
        status = "✅ Выполнено" if task.completed else "⏳ Ожидает"
        time_left = task.reminder_time - datetime.now()
        hours_left = max(0, int(time_left.total_seconds() // 3600))
        minutes_left = max(0, int((time_left.total_seconds() % 3600) // 60))

        task_list += f"{i}. {task.task_text}\n"
        task_list += f"   🕐 Через: {hours_left}ч {minutes_left}мин\n"
        task_list += f"   📊 Статус: {status}\n\n"

    await update.message.reply_text(task_list)


def parse_time(text):
    text = text.lower().strip()
    now = datetime.now()

    try:
        if "через" in text:
            if "минут" in text:
                minutes = int(''.join(filter(str.isdigit, text.split("минут")[0].split()[-1])))
                return now + timedelta(minutes=minutes)
            elif "час" in text:
                hours = int(''.join(filter(str.isdigit, text.split("час")[0].split()[-1])))
                return now + timedelta(hours=hours)
            elif "день" in text:
                days = int(''.join(filter(str.isdigit, text.split("день")[0].split()[-1])))
                return now + timedelta(days=days)

        if "завтра" in text:
            time_part = text.split("в ")[-1] if "в " in text else text
            time_str = ''.join(filter(lambda x: x.isdigit() or x == ':', time_part))
            if ':' in time_str:
                hours, minutes = map(int, time_str.split(':'))
                tomorrow = now + timedelta(days=1)
                return tomorrow.replace(hour=hours, minute=minutes, second=0, microsecond=0)

        if text.startswith('в ') or ' в ' in text:
            time_str = ''.join(filter(lambda x: x.isdigit() or x == ':', text))
            if ':' in time_str:
                hours, minutes = map(int, time_str.split(':'))
                result = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                if result < now:
                    result += timedelta(days=1)
                return result

        if text.isdigit():
            return now + timedelta(minutes=int(text))

    except (ValueError, IndexError):
        return None
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if text.startswith('/'):
        return

    reminder_time = parse_time(text)
    if not reminder_time:
        await update.message.reply_text("❌ Не могу понять время. Попробуйте: 'Через 2 часа' или 'Завтра в 10:00'")
        return

    task_text = text
    time_phrases = ["через", "завтра", "в "]
    for phrase in time_phrases:
        if phrase in task_text.lower():
            task_text = task_text.lower().split(phrase)[0].strip()
            break

    if not task_text:
        task_text = "Напоминание"

    task = ReminderTask(user_id, task_text, reminder_time)
    if user_id not in user_tasks:
        user_tasks[user_id] = []
    user_tasks[user_id].append(task)

    asyncio.create_task(schedule_reminder(task, context.bot))

    time_diff = reminder_time - datetime.now()
    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)

    await update.message.reply_text(
        f"✅ Записано!\n📝 {task_text}\n⏰ Через: {hours}ч {minutes}мин"
    )


async def schedule_reminder(task: ReminderTask, bot):
    now = datetime.now()
    delay = (task.reminder_time - now).total_seconds()

    if delay > 0:
        await asyncio.sleep(delay)

    if (task.user_id in user_tasks and
            task in user_tasks[task.user_id] and
            not task.completed):
        keyboard = [
            [
                InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{task.task_id}"),
                InlineKeyboardButton("🔄 Отложить на 1 час", callback_data=f"snooze_{task.task_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await bot.send_message(
            chat_id=task.user_id,
            text=f"🔔 **Напоминание!**\n\n{task.task_text}",
            reply_markup=reply_markup
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data.startswith("done_"):
        task_id = data[5:]
        if user_id in user_tasks:
            for task in user_tasks[user_id]:
                if task.task_id == task_id:
                    task.completed = True
                    await query.edit_message_text(f"✅ Отлично! Задача выполнена:\n{task.task_text}")
                    break

    elif data.startswith("snooze_"):
        task_id = data[7:]
        if user_id in user_tasks:
            for task in user_tasks[user_id]:
                if task.task_id == task_id:
                    task.reminder_time += timedelta(hours=1)
                    asyncio.create_task(schedule_reminder(task, context.bot))
                    await query.edit_message_text(f"⏰ Напомню через 1 час:\n{task.task_text}")
                    break


def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Бот-напоминатель запущен...")
    app.run_polling()


if __name__ == '__main__':
    main()