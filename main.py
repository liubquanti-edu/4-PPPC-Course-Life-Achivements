import random
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, ForceReply, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config import TOKEN, ADMIN_ID, FIREBASE

# Ініціалізація Firebase
cred = credentials.Certificate(FIREBASE)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        ["Випадкове досягнення"],
        ["Знайти досягнення"],
        ["Статистика"]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Вітаємо! Виберіть опцію:",
        reply_markup=reply_markup
    )

# Випадкове досягнення
async def random_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    achievements_ref = db.collection('achievements')
    achievements = achievements_ref.stream()
    
    achievements_list = [achievement for achievement in achievements]
    if not achievements_list:
        await update.message.reply_text("Немає досягнень у базі даних.")
        return
    
    random_achievement = random.choice(achievements_list)
    title = random_achievement.get('title')
    description = random_achievement.get('description')
    photo_url = random_achievement.get('photo_url')

    await update.message.reply_photo(photo=photo_url, caption=f"{title}\n{description}")

# Статистика
async def statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_ref = db.collection('users').document(str(update.effective_user.id))
    user_doc = user_ref.get()
    
    if user_doc.exists:
        completed_achievements = user_doc.to_dict().get('completed_achievements', [])
        message = f"Ви виконали {len(completed_achievements)} досягнень:\n"
        for achievement in completed_achievements:
            message += f"- {achievement}\n"
    else:
        message = "Ви ще не виконали жодного досягнення."
    
    await update.message.reply_text(message)

# Функція для створення досягнення
async def create_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Ви не маєте прав доступу для виконання цієї команди.")
        return

    await update.message.reply_text("Введіть назву досягнення:")
    context.user_data["step"] = "TITLE"  # Встановлюємо стан на TITLE

# Функція для отримання назви, опису, та фото URL досягнення
async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "step" not in context.user_data:
        return  # Якщо крок не визначено, нічого не робимо

    if context.user_data["step"] == "TITLE":
        context.user_data["title"] = update.message.text
        await update.message.reply_text("Введіть опис досягнення:")
        context.user_data["step"] = "DESCRIPTION"  # Перехід до наступного кроку

    elif context.user_data["step"] == "DESCRIPTION":
        context.user_data["description"] = update.message.text
        await update.message.reply_text("Введіть URL фото досягнення:")
        context.user_data["step"] = "PHOTO_URL"  # Перехід до наступного кроку

    elif context.user_data["step"] == "PHOTO_URL":
        context.user_data["photo_url"] = update.message.text

        # Додаємо досягнення до Firestore
        achievements_ref = db.collection('achievements')
        achievements_ref.add({
            "title": context.user_data["title"],
            "description": context.user_data["description"],
            "photo_url": context.user_data["photo_url"]
        })

        await update.message.reply_text("Досягнення успішно створено!")
        context.user_data.clear()  # Очищення даних після завершення

    else:
        await update.message.reply_text("Неочікувана помилка. Спробуйте ще раз.")

# Оновимо функцію handle_buttons для коректної обробки
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "step" in context.user_data:
        await receive_title(update, context)  # Якщо користувач створює досягнення, перенаправляємо його
    else:
        user_input = update.message.text
        if user_input == "Випадкове досягнення":
            await random_achievement(update, context)
        elif user_input == "Знайти досягнення":
            await find_achievement(update, context)
        elif user_input == "Статистика":
            await statistics(update, context)
        else:
            await update.message.reply_text("Невідома команда. Будь ласка, скористайтесь меню.")

# Функція для виведення списку досягнень з кнопками
async def find_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    achievements_ref = db.collection('achievements')
    achievements = achievements_ref.stream()

    achievements_list = [achievement for achievement in achievements]
    if not achievements_list:
        await update.message.reply_text("Немає досягнень у базі даних.")
        return

    keyboard = []
    for achievement in achievements_list:
        achievement_id = achievement.id  # Отримуємо ID досягнення
        title = achievement.get('title')
        keyboard.append([InlineKeyboardButton(title, callback_data=f"achievement_{achievement_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Оберіть досягнення:", reply_markup=reply_markup)

# Функція для показу деталей досягнення
async def show_achievement_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # Підтверджуємо callback-запит

    # Отримуємо ID досягнення з callback_data
    achievement_id = query.data.split("_")[1]
    achievement_ref = db.collection('achievements').document(achievement_id)
    achievement = achievement_ref.get()

    if achievement.exists:
        title = achievement.get('title')
        description = achievement.get('description')
        photo_url = achievement.get('photo_url')

        # Відправляємо фото і деталі досягнення
        await query.message.reply_photo(photo=photo_url, caption=f"{title}\n{description}")
    else:
        await query.message.reply_text("Досягнення не знайдено.")

def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("create_achievement", create_achievement))
    app.add_handler(CommandHandler("find_achievement", find_achievement))

    # Оновлений обробник для callback-запитів
    app.add_handler(CallbackQueryHandler(show_achievement_details, pattern="^achievement_"))

    # Оновлений обробник для роботи з текстом користувача
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    
    app.run_polling()

if __name__ == '__main__':
    main()