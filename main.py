from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters
import random
import firebase_admin
import asyncio
from firebase_admin import credentials, firestore
from config import TOKEN, FIREBASE, ADMIN_ID

cred = credentials.Certificate(FIREBASE)
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Application.builder().token(TOKEN).build()

WAITING_FOR_COMPLETION_DESCRIPTION = 1
WAITING_FOR_FRIEND_CONFIRMATION = 2

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
        [InlineKeyboardButton("👥 Друзі", callback_data='friends')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_data = user_ref.get().to_dict()
    username = user_data.get('username', 'Користувач')
    await update.message.reply_text(f"👋  •  Вітаємо у White Life, {username}!\n\n✅  •  Тут ви зможете виконувати різноманітні життєві досягнення та ділитися цим з друзями.\n\n⚙️  •  Функції налаштувать та друзів доступні в меню /command.\n\n🔽  •  Оберіть дію:", reply_markup=reply_markup)

async def suggest_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    suggestion_text = ' '.join(context.args)  # Отримуємо текст пропозиції

    # Перевірка, чи було вказано опис досягнення
    if not suggestion_text:
        await update.message.reply_text("📬  •  Щоб запропонувати досягнення, вкажіть опис після команди, наприклад:\n\n/suggest Моя пропозиція для досягнення")
        return

    # Відправляємо пропозицію адміністратору
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📢  •  Нова пропозиція від <a href='tg://user?id={user.id}'>{user.full_name}</a>.\n\n⭐  •  {suggestion_text}",
        parse_mode='HTML'
    )
    
    await update.message.reply_text("✅  •  Вашу пропозицію було надіслано адміністратору.")

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

async def rfriend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    friend_id = ' '.join(context.args)

    if not friend_id:
        await update.message.reply_text("⚙️ • Будь ласка, вкажіть ID користувача після команди, наприклад: \n\n/rfriend 123456789")
        return

    friend_ref = db.collection('users').document(friend_id)
    user_ref = db.collection('users').document(str(user_id))

    # Перевірка, чи існує друг
    if not friend_ref.get().exists:
        await update.message.reply_text("❌ • Користувача з таким ID не знайдено.")
        return

    # Отримуємо список друзів поточного користувача
    user_data = user_ref.get().to_dict()
    if 'friends' not in user_data or friend_id not in user_data['friends']:
        await update.message.reply_text("❌ • Користувач не є вашим другом.")
        return

    # Видаляємо друга з обох списків
    user_ref.update({
        'friends': firestore.ArrayRemove([friend_id])  # Видаляємо друга зі списку друзів поточного користувача
    })
    friend_ref.update({
        'friends': firestore.ArrayRemove([str(user_id)])  # Видаляємо поточного користувача зі списку друзів іншого користувача
    })

    await update.message.reply_text(f"❌ • Друга видалено.")



async def list_friends(query):
    user_id = query.from_user.id
    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    friends = user_data.get('friends', [])

    if not friends:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f'😢 • У вас немає друзів.\n\n🆔 • Ваш ID: <span class="tg-spoiler">{user_id}</span>\n\n✈️ • Скопіюйте та надішліть його другу, щоб він додав вас до друзів.\n\n👀 • Щоб додати друга самостійно - скористайтеся командою /friend.', reply_markup=reply_markup, parse_mode='HTML')
        return

    keyboard = [
        [InlineKeyboardButton(db.collection('users').document(friend_id).get().to_dict().get('username', 'Невідомий користувач'), callback_data=f'friend_{friend_id}') for friend_id in friends]
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_id = query.from_user.id
    await query.message.reply_text(f'💙 • Ваш список друзів.\n\n🆔 • Ваш ID: <span class="tg-spoiler">{user_id}</span>\n\n✈️ • Скопіюйте та надішліть його другу, щоб він додав вас до друзів.\n\n👀 • Щоб додати друга самостійно - скористайтеся командою /friend.\n\n💔 • Щоб видалити друга - скористайтеся командою /rfriend.', reply_markup=reply_markup, parse_mode='HTML')


async def friend_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    friend_id = ' '.join(context.args)

    if not friend_id:
        await update.message.reply_text("⚙️ • Будь ласка, вкажіть ID користувача після команди, наприклад:\n\n/friend 123456789")
        return

    friend_ref = db.collection('users').document(friend_id)
    user_ref = db.collection('users').document(str(user.id))

    # Перевірка, чи існує друг
    if not friend_ref.get().exists:
        await update.message.reply_text("❌ • Користувача з таким ID не знайдено.")
        return

    # Отримуємо список друзів поточного користувача
    user_data = user_ref.get().to_dict()
    friends = user_data.get('friends', [])
    
    # Перевірка, чи друг вже є у списку
    if friend_id in friends:
        await update.message.reply_text("❌ • Ви вже є друзями з цим користувачем.")
        return

    # Відправляємо запит на підтвердження дружби
    await context.bot.send_message(
        chat_id=friend_id,
        text=f"👥 • <a href='tg://user?id={user.id}'>{user.full_name}</a> хоче додати вас у друзі.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Підтвердити", callback_data=f'confirm_friend_{user.id}')],
            [InlineKeyboardButton("❌ Відхилити", callback_data=f'reject_friend_{user.id}')],
        ]),
        parse_mode='HTML'
    )
    await update.message.reply_text("✅ • Запит на додавання у друзі надіслано.")


async def handle_friend_request(query, action):
    user_id = query.from_user.id
    friend_id = query.data.split('_')[2]

    user_ref = db.collection('users').document(str(user_id))
    friend_ref = db.collection('users').document(str(friend_id))

    if action == 'confirm':
        user_ref.update({'friends': firestore.ArrayUnion([friend_id])})
        friend_ref.update({'friends': firestore.ArrayUnion([str(user_id)])})
        await query.message.reply_text("✅  •  Ви тепер друзі!")
    else:
        await query.message.reply_text("❌  •  Запит відхилено.")

async def friend_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('friend_'):
        friend_id = query.data.split('_')[1]
        friend_ref = db.collection('users').document(friend_id).get()
        if friend_ref.exists:
            await send_friend_stats(query, friend_id)
    elif query.data.startswith('confirm_friend_'):
        await handle_friend_request(query, 'confirm')
    elif query.data.startswith('reject_friend_'):
        await handle_friend_request(query, 'reject')

app.add_handler(CommandHandler("friend", friend_request))
app.add_handler(CallbackQueryHandler(friend_button_handler, pattern='friend_'))
app.add_handler(CallbackQueryHandler(friend_button_handler, pattern='confirm_friend_'))
app.add_handler(CallbackQueryHandler(friend_button_handler, pattern='reject_friend_'))

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
    elif query.data == 'friends':
        await list_friends(query)
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
    user = update.effective_user
    user_id = user.id
    description = update.message.text

    user_ref = db.collection('users').document(str(user_id))
    user_data = user_ref.get().to_dict() or {}
    completed_achievements = user_data.get('completed_achievements', {})
    completed_achievements[achievement_id] = {'description': description}
    user_ref.set({'completed_achievements': completed_achievements}, merge=True)

    await update.message.reply_text("✅  •  Виконання збережено!")
    # Відкриваємо деталі досягнення після збереження виконання
    achievement = db.collection('achievements').document(achievement_id).get()
    if achievement.exists:
        await send_achievement_details(update.message, achievement.to_dict(), achievement_id, user_id)
    # Отримуємо список друзів користувача
    user_data = user_ref.get().to_dict() or {}
    friends = user_data.get('friends', [])

    # Відправляємо повідомлення всім друзям
    for friend_id in friends:
        friend_ref = db.collection('users').document(friend_id)
        friend_data = friend_ref.get().to_dict() or {}
        friend_username = friend_data.get('username', 'Друг')

        await context.bot.send_message(
            chat_id=friend_id,
            text=f"👥  •  Ваш друг <a href='tg://user?id={user.id}'>{user.full_name}</a> виконав досягнення!\n\n⭐  •  {db.collection('achievements').document(achievement_id).get().to_dict().get('title', 'Невідоме досягнення')}.\n\n📝  •  Опис виконання:\n\n<blockquote expandable>{description}</blockquote>",
            parse_mode='HTML'
        )
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
        await update.message.reply_text("⚙️  •  Будь ласка, вкажіть новий нікнейм після команди, наприклад:\n\n/username Нікнейм")
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
        msg = await update.message.reply_text("🔒  •  Ваш статус було змінено на <b>приватний</b>. Ви більше не будете показуватись у глобальній статистиці.", parse_mode='HTML')
        await asyncio.sleep(3)
        await msg.delete()
        try:
            await update.message.delete()
        except:
            pass
    else:
        msg = await update.message.reply_text("🔒  •  Ваш статус було змінено на <b>публічний</b>. Ви більше не будете показуватись у глобальній статистиці.", parse_mode='HTML')
        await asyncio.sleep(3)
        await msg.delete()
        try:
            await update.message.delete()
        except:
            pass

rfriend_handler = CommandHandler("rfriend", rfriend)
app.add_handler(rfriend_handler)
privacy_handler = CommandHandler("privacy", toggle_privacy)
app.add_handler(privacy_handler)
suggest_handler = CommandHandler("suggest", suggest_achievement)
app.add_handler(suggest_handler)
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
        msg = await query.message.reply_text("⭐  •  Усі досягнення вже виконано!")
        await asyncio.sleep(3)
        await msg.delete()
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
        stats_text += "⭐  •  Ви ще не виконали жодного досягнення."

    keyboard = [
        [InlineKeyboardButton("🌍 Глобальна статистика", callback_data='global_stats')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(stats_text, reply_markup=reply_markup)

async def send_friend_stats(query, friend_id):
    # Отримуємо дані друга
    friend_ref = db.collection('users').document(friend_id).get()
    if not friend_ref.exists:
        await query.message.reply_text("❌  •  Користувача не знайдено.")
        return

    friend_data = friend_ref.to_dict()
    completed_achievements = friend_data.get('completed_achievements', {})
    completed_count = len(completed_achievements)
    achievements_list = "\n".join(
        [f"⭐  •  {db.collection('achievements').document(ach_id).get().to_dict().get('title', 'Невідоме досягнення')}\n<blockquote expandable>{desc['description']}</blockquote>"
         for ach_id, desc in completed_achievements.items()]
    )
    
    stats_text = f"📊  •  Статистика друга.\n\n✅  •  Виконаних досягнень: {completed_count}\n\n"
    if achievements_list:
        stats_text += f"📃  •  Список виконаних досягнень:\n{achievements_list}"
    else:
        stats_text += "⭐  •  Друг ще не виконав жодного досягнення."
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='HTML')

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