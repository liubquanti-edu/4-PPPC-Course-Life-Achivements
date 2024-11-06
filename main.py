from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import random
import firebase_admin
from firebase_admin import credentials, firestore
from config import TOKEN, FIREBASE

# Firebase setup
cred = credentials.Certificate(FIREBASE)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Bot setup
app = Application.builder().token(TOKEN).build()

# Стан для розмови
WAITING_FOR_COMPLETION_DESCRIPTION = 1

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_ref = db.collection('users').document(str(user.id))
    
    # Зберігаємо ім'я користувача, якщо воно ще не збережено
    if not user_ref.get().exists:
        user_ref.set({
            'username': user.full_name,
            'completed_achievements': {}
        }, merge=True)
    
    achievement_id = context.args[0] if context.args else None
    if achievement_id:
        achievement = db.collection('achievements').document(achievement_id).get()
        if achievement.exists:
            achievement_data = achievement.to_dict()
            await send_random_achievement_details(update.message, achievement_data)
            return

    keyboard = [
        [InlineKeyboardButton("🎲 Випадкове досягнення", callback_data='random')],
        [InlineKeyboardButton("🔍 Знайти досягнення", callback_data='find')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Вітаю! Оберіть дію:", reply_markup=reply_markup)

async def send_achievement_details(message, achievement, achievement_id, user_id):
    # Підраховуємо кількість виконань для цього досягнення
    users_ref = db.collection('users').stream()
    completed_count = sum(1 for user in users_ref if achievement_id in user.to_dict().get('completed_achievements', {}))
    
    # Перевіряємо, чи користувач виконав це досягнення
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})
    user_completion_text = completed_achievements.get(achievement_id, {}).get('description', None)
    
    # Формуємо текст досягнення
    achievement_text = f"{achievement['title']}\n\n{achievement['description']}\n\n" \
                       f"Виконали {completed_count} користувачів."
    
    if user_completion_text:
        achievement_text += f"\n\n📝 Ваш опис виконання: {user_completion_text}"
    
    # Клавіатура для виконання досягнення
    keyboard = [
        [InlineKeyboardButton("📝 Виконати", callback_data=f'complete_{achievement_id}')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Відправляємо деталі досягнення разом з кількістю виконань і текстом виконання, якщо він є
    await message.reply_photo(
        photo=achievement['photo_url'],
        caption=achievement_text,
        reply_markup=reply_markup
    )


async def send_random_achievement_details(message, achievement):
    keyboard = [
        [InlineKeyboardButton("🔄 Нове випадкове", callback_data='new_random')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_photo(
        photo=achievement['photo_url'],
        caption=f"{achievement['title']}\n\n{achievement['description']}",
        reply_markup=reply_markup
    )

# Callback for menu buttons
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id  # Отримуємо ID користувача
    
    if query.data == 'random':
        await send_random_achievement(query)
    elif query.data == 'find':
        await list_achievements(query)
    elif query.data == 'stats':
        await send_stats(query)
    elif query.data == 'global_stats':
        await send_global_stats(query) 
    elif query.data == 'new_random':
        await send_random_achievement(query, edit=True)
    elif query.data == 'main_menu':
        await query.message.delete()
    elif query.data.startswith('achievement_'):
        achievement_id = query.data.split('_')[1]
        achievement = db.collection('achievements').document(achievement_id).get()
        if achievement.exists:
            await send_achievement_details(query.message, achievement.to_dict(), achievement_id, user_id)  # Додаємо user_id
    elif query.data.startswith('complete_'):
        achievement_id = query.data.split('_')[1]
        context.user_data['achievement_id'] = achievement_id
        await query.message.reply_text("Опишіть, як ви виконали це досягнення:")
        return WAITING_FOR_COMPLETION_DESCRIPTION  # Повертаємо стан

async def save_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    achievement_id = context.user_data.get('achievement_id')
    user_id = update.effective_user.id
    description = update.message.text

    # Зберігаємо дані у Firestore
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})
    completed_achievements[achievement_id] = {'description': description}
    user_ref.set({'completed_achievements': completed_achievements}, merge=True)

    await update.message.reply_text("Виконання збережено! ✅")
    return ConversationHandler.END


# Cancel handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Дію скасовано.")
    return ConversationHandler.END

# Register handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        WAITING_FOR_COMPLETION_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_completion)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_completion))

# Останнє відправлене досягнення
last_achievement_id = None

async def send_random_achievement(query, edit=False):
    global last_achievement_id
    user_id = query.from_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})

    # Отримуємо всі досягнення, окрім виконаних
    achievements_ref = db.collection('achievements').stream()
    achievements = [
        (ach.id, ach.to_dict()) for ach in achievements_ref
        if ach.id not in completed_achievements
    ]

    # Перевірка наявності невиконаних досягнень
    if not achievements:
        await query.message.reply_text("Усі досягнення вже виконано!")
        return

    # Пошук випадкового досягнення
    achievement_id, achievement = random.choice(achievements)
    
    # Уникнення повторів (тільки якщо є більше одного досягнення)
    while achievement_id == last_achievement_id and len(achievements) > 1:
        achievement_id, achievement = random.choice(achievements)

    last_achievement_id = achievement_id  # Зберігаємо ID останнього досягнення

    # Клавіатура для випадкового досягнення
    keyboard = [
        [InlineKeyboardButton("📝 Виконати", callback_data=f'complete_{achievement_id}')],
        [InlineKeyboardButton("🔄 Нове випадкове", callback_data='new_random')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Відправка або редагування випадкового досягнення
    if edit:
        await query.message.edit_media(
            media=InputMediaPhoto(
                media=achievement['photo_url'],
                caption=f"{achievement['title']}\n{achievement['description']}"
            ),
            reply_markup=reply_markup
        )
    else:
        await query.message.reply_photo(
            photo=achievement['photo_url'],
            caption=f"{achievement['title']}\n{achievement['description']}",
            reply_markup=reply_markup
        )

async def list_achievements(query):
    user_id = query.from_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})

    # Отримуємо всі досягнення
    achievements_ref = db.collection('achievements').stream()
    achievements = [(ach.id, ach.to_dict()) for ach in achievements_ref]
    
    if not achievements:
        await query.message.reply_text("Немає доступних досягнень.")
        return
    
    # Формуємо клавіатуру з перевіркою виконаних досягнень
    keyboard = []
    for achievement_id, achievement in achievements:
        title = achievement['title']
        
        # Додаємо прапорець для виконаних досягнень
        if achievement_id in completed_achievements:
            title += " ✅"
        
        keyboard.append([InlineKeyboardButton(title, callback_data=f'achievement_{achievement_id}')])

    # Додаємо кнопку назад
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Оберіть досягнення:", reply_markup=reply_markup)


async def send_stats(query):
    user_id = str(query.from_user.id)
    user_ref = db.collection('users').document(user_id).get()
    
    # Отримуємо дані про виконані досягнення
    user_data = user_ref.to_dict() if user_ref.exists else {}
    completed_achievements = user_data.get('completed_achievements', {})

    # Формуємо текст для списку досягнень
    completed_count = len(completed_achievements)
    achievements_list = "\n".join(
        [f"• {db.collection('achievements').document(ach_id).get().to_dict().get('title', 'Невідоме досягнення')}"
         for ach_id in completed_achievements]
    )
    
    # Підготовка повідомлення для статистики
    stats_text = f"Ви виконали {completed_count} досягнень.\n\n"
    if achievements_list:
        stats_text += f"Список виконаних досягнень:\n{achievements_list}"
    else:
        stats_text += "Ви ще не виконали жодного досягнення."

    # Додаємо кнопку для повернення до головного меню
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
        [InlineKeyboardButton("🌍 Глобальна статистика", callback_data='global_stats')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(stats_text, reply_markup=reply_markup)


async def send_global_stats(query):
    users_ref = db.collection('users').stream()
    
    # Отримуємо ім'я та кількість виконаних досягнень для кожного користувача
    users_completed_count = []
    for user in users_ref:
        user_data = user.to_dict()
        completed_achievements = user_data.get('completed_achievements', {})
        username = user_data.get('username', 'Анонім')
        users_completed_count.append((username, len(completed_achievements)))

    # Сортуємо за кількістю виконаних досягнень у порядку спадання і беремо топ-10
    top_users = sorted(users_completed_count, key=lambda x: x[1], reverse=True)[:10]
    
    # Формуємо повідомлення для відображення
    global_stats_message = "🏆 Топ 10 користувачів за кількістю досягнень:\n"
    for i, (username, count) in enumerate(top_users, start=1):
        global_stats_message += f"{i}. {username}: {count} досягнень\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(global_stats_message, reply_markup=reply_markup)

if __name__ == "__main__":
    app.run_polling()
