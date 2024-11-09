from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters
import random
import firebase_admin
from firebase_admin import credentials, firestore
from config import TOKEN, FIREBASE

cred = credentials.Certificate(FIREBASE)
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Application.builder().token(TOKEN).build()

WAITING_FOR_COMPLETION_DESCRIPTION = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_ref = db.collection('users').document(str(user.id))
    
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
    await update.message.reply_text("👋  •  Вітаємо у White Life!\n\n✅  •  Тут ви зможете виконувати різноманітні життєві досягнення та ділитися цим з друзями.\n\n⚙️  •  Функції налаштувать доступні в меню /command.\n\n🔽  •  Оберіть дію:", reply_markup=reply_markup)

async def send_achievement_details(message, achievement, achievement_id, user_id):
    users_ref = db.collection('users').stream()
    completed_count = sum(1 for user in users_ref if achievement_id in user.to_dict().get('completed_achievements', {}))
    
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})
    user_completion_text = completed_achievements.get(achievement_id, {}).get('description', None)
    
    achievement_text = f"<b>⭐  •  {achievement['title']}</b>\n🌐  •  Вже виконали: {completed_count}\n\n<blockquote>{achievement['description']}</blockquote>"
    
    if user_completion_text:
        achievement_text += f"\n\n📝  •  Ваш опис виконання:\n\n<blockquote>{user_completion_text}</blockquote>"
    
    if user_completion_text:
        keyboard = [
            [InlineKeyboardButton("📝 Редагувати виконання", callback_data=f'complete_{achievement_id}')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Виконати", callback_data=f'complete_{achievement_id}')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_photo(
        photo=achievement['photo_url'],
        caption=achievement_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️  •  Меню команд знаходиться ліворуч від поля для ведення повідомлення.")

async def send_random_achievement_details(message, achievement):
    keyboard = [
        [InlineKeyboardButton("🔄 Інше досягнення", callback_data='new_random')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_photo(
        photo=achievement['photo_url'],
        caption=f"{achievement['title']}\n\n{achievement['description']}",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
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
            await send_achievement_details(query.message, achievement.to_dict(), achievement_id, user_id)
    elif query.data.startswith('complete_'):
        achievement_id = query.data.split('_')[1]
        context.user_data['achievement_id'] = achievement_id
        await query.message.reply_text("💬  •  Опишіть, як ви виконали це досягнення:")
        return WAITING_FOR_COMPLETION_DESCRIPTION

async def save_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    achievement_id = context.user_data.get('achievement_id')
    user_id = update.effective_user.id
    description = update.message.text

    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})
    completed_achievements[achievement_id] = {'description': description}
    user_ref.set({'completed_achievements': completed_achievements}, merge=True)

    await update.message.reply_text("✅  •  Виконання збережено!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Дію скасовано.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        WAITING_FOR_COMPLETION_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_completion)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

async def change_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    new_username = ' '.join(context.args)  # Отримуємо новий нікнейм із аргументів команди

    # Перевірка, чи вказано нове ім'я
    if not new_username:
        await update.message.reply_text("⚙️  •  Будь ласка, вкажіть новий нікнейм після команди, наприклад: \n/username Нікнейм")
        return

    # Оновлення нікнейму в базі даних
    user_ref = db.collection('users').document(str(user_id))
    user_ref.update({
        'username': new_username
    })

    await update.message.reply_text(f"⚙️  •  Ваш нікнейм було успішно змінено на: {new_username}")

async def toggle_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Отримуємо поточний статус приватності користувача з бази даних
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    is_private = user_data.get('privacy', False)  # Якщо користувач не має цього поля, за замовчуванням його статус публічний

    # Перемикаємо статус на протилежний
    new_privacy_status = not is_private

    # Оновлюємо статус у Firebase
    user_ref.update({
        'privacy': new_privacy_status
    })

    # Відправляємо повідомлення користувачу про зміну статусу
    if new_privacy_status:
        await update.message.reply_text("🔒  •  Ваш статус було змінено на <b>приватний</b>. Ви більше не будете показуватись у глобальній статистиці.", parse_mode='HTML')
    else:
        await update.message.reply_text("🔓  •  Ваш статус було змінено на <b>публічний</b>. Ви знову будете показуватись у глобальній статистиці.", parse_mode='HTML')

privacy_handler = CommandHandler("privacy", toggle_privacy)
app.add_handler(privacy_handler)
command_handler = CommandHandler("command", command)
app.add_handler(command_handler)
username_handler = CommandHandler("username", change_username)
app.add_handler(username_handler)
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_completion))

last_achievement_id = None

async def send_random_achievement(query, edit=False):
    global last_achievement_id
    user_id = query.from_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})

    achievements_ref = db.collection('achievements').stream()
    achievements = [
        (ach.id, ach.to_dict()) for ach in achievements_ref
        if ach.id not in completed_achievements
    ]

    if not achievements:
        await query.message.reply_text("⭐  •  Усі досягнення вже виконано!")
        return

    achievement_id, achievement = random.choice(achievements)
    
    while achievement_id == last_achievement_id and len(achievements) > 1:
        achievement_id, achievement = random.choice(achievements)

    last_achievement_id = achievement_id

    keyboard = [
        [InlineKeyboardButton("🔄 Інше досягнення", callback_data='new_random')],
        [InlineKeyboardButton("📝 Виконати", callback_data=f'complete_{achievement_id}')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit:
        users_ref = db.collection('users').stream()
        completed_count = sum(1 for user in users_ref if achievement_id in user.to_dict().get('completed_achievements', {}))

        await query.message.edit_media(
            media=InputMediaPhoto(
            media=achievement['photo_url'],
            caption=f"<b>⭐  •  {achievement['title']}</b>\n🌐  •  Вже виконали: {completed_count}\n\n<blockquote>{achievement['description']}</blockquote>",
            parse_mode='HTML'
            ),
            reply_markup=reply_markup
        )
    else:
        users_ref = db.collection('users').stream()
        completed_count = sum(1 for user in users_ref if achievement_id in user.to_dict().get('completed_achievements', {}))

        await query.message.reply_photo(
            photo=achievement['photo_url'],
            caption=f"<b>⭐  •  {achievement['title']}</b>\n🌐  •  Вже виконали: {completed_count}\n\n<blockquote>{achievement['description']}</blockquote>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

async def list_achievements(query):
    user_id = query.from_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})

    achievements_ref = db.collection('achievements').stream()
    achievements = [(ach.id, ach.to_dict()) for ach in achievements_ref]
    
    if not achievements:
        await query.message.reply_text("Немає доступних досягнень.")
        return
    
    keyboard = []
    for achievement_id, achievement in achievements:
        title = achievement['title']
        
        if achievement_id in completed_achievements:
            title = "✅ " + title
        else:
            title = "❌ " + title
        
        keyboard.append([InlineKeyboardButton(title, callback_data=f'achievement_{achievement_id}')])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("⭐  •  Оберіть досягнення:", reply_markup=reply_markup)


async def send_stats(query):
    user_id = str(query.from_user.id)
    user_ref = db.collection('users').document(user_id).get()
    
    user_data = user_ref.to_dict() if user_ref.exists else {}
    completed_achievements = user_data.get('completed_achievements', {})

    completed_count = len(completed_achievements)
    achievements_list = "\n".join(
        [f"⭐  •  {db.collection('achievements').document(ach_id).get().to_dict().get('title', 'Невідоме досягнення')}"
         for ach_id in completed_achievements]
    )
    
    stats_text = f"📊  •  Статистика.\n\n✅  •  Виконаних досягнень: {completed_count}\n\n"
    if achievements_list:
        stats_text += f"📃  •  Список виконаних досягнень:\n{achievements_list}"
    else:
        stats_text += "Ви ще не виконали жодного досягнення."

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
        [InlineKeyboardButton("🌍 Глобальна статистика", callback_data='global_stats')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(stats_text, reply_markup=reply_markup)


async def send_global_stats(query):
    users_ref = db.collection('users').stream()
    
    users_completed_count = []
    for user in users_ref:
        user_data = user.to_dict()
        
        # Перевіряємо статус приватності
        if user_data.get('privacy', False):  # Якщо користувач приватний, пропускаємо його
            continue
        
        completed_achievements = user_data.get('completed_achievements', {})
        username = user_data.get('username', 'Анонім')
        users_completed_count.append((username, len(completed_achievements)))

    top_users = sorted(users_completed_count, key=lambda x: x[1], reverse=True)[:10]
    
    global_stats_message = "🏆  •  Топ 10 користувачів за кількістю досягнень:\n\n"
    for i, (username, count) in enumerate(top_users, start=1):
        if i == 1:
            medal = "🥇  •  "
        elif i == 2:
            medal = "🥈  •  "
        elif i == 3:
            medal = "🥉  •  "
        else:
            medal = "🏅  •  "
        global_stats_message += f"{medal} {username}: {count}\n"

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(global_stats_message, reply_markup=reply_markup)

if __name__ == "__main__":
    app.run_polling()