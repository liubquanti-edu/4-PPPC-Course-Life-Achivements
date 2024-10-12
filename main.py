import telebot
from config import TOKEN, ADMIN_ID
from firebase import add_user_to_achievement, get_achievements, get_global_stats, add_new_achievement

bot = telebot.TeleBot(TOKEN)

# Словник для зберігання вибраних досягнень користувачами
user_selected_achievement = {}

# Словник для збереження тимчасових даних при створенні нового досягнення
new_achievement_data = {}

# Ласкаво просимо
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "Вітаємо! Ви можете почати виконувати життєві досягнення. Введіть /achievements для перегляду доступних досягнень.")

# Виведення глобальної статистики
@bot.message_handler(commands=['stats'])
def send_stats(message):
    stats = get_global_stats()
    bot.send_message(message.chat.id, f"Загальна кількість виконаних досягнень: {stats}")

# Показ доступних досягнень
@bot.message_handler(commands=['achievements'])
def show_achievements(message):
    achievements = get_achievements()  # Отримуємо досягнення з Firebase

    if not achievements:
        bot.send_message(message.chat.id, "Наразі немає доступних досягнень.")
        return

    response_message = "Ось доступні досягнення:\n"
    for achievement in achievements:
        response_message += f"/achievement_{achievement['id']} - {achievement['name']}: {achievement['description']}\n"

    bot.send_message(message.chat.id, response_message)

# Вибір конкретного досягнення
@bot.message_handler(func=lambda message: message.text.startswith('/achievement_'))
def select_achievement(message):
    achievement_id = message.text.split('_')[1]
    
    # Отримуємо інформацію про вибране досягнення
    achievements = get_achievements()
    selected_achievement = next((ach for ach in achievements if ach['id'] == achievement_id), None)

    if selected_achievement:
        user_selected_achievement[str(message.chat.id)] = achievement_id
        bot.send_message(message.chat.id, f"Ви обрали досягнення: {selected_achievement['name']}. Надішліть текст або фото для підтвердження його виконання.")
    else:
        bot.send_message(message.chat.id, "Невідоме досягнення. Будь ласка, спробуйте ще раз.")

# Створення нового досягнення (доступно тільки для користувача з ADMIN_ID)
@bot.message_handler(commands=['create_achievement'])
def create_achievement(message):
    if message.chat.id == ADMIN_ID:
        new_achievement_data[message.chat.id] = {}
        bot.send_message(message.chat.id, "Введіть назву нового досягнення:")
    else:
        bot.send_message(message.chat.id, "У вас немає прав на створення нових досягнень.")

# Обробка тексту та фото для вибраного досягнення
@bot.message_handler(content_types=['text', 'photo'])
def handle_message(message):
    user_id = str(message.chat.id)

    # Створення нового досягнення
    if message.chat.id == ADMIN_ID and message.chat.id in new_achievement_data:
        if 'name' not in new_achievement_data[message.chat.id]:
            new_achievement_data[message.chat.id]['name'] = message.text
            bot.send_message(message.chat.id, "Назву досягнення збережено! Тепер надішліть фото для цього досягнення.")
        elif 'photo_url' not in new_achievement_data[message.chat.id] and message.photo:
            photo_id = message.photo[-1].file_id
            photo_info = bot.get_file(photo_id)
            photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{photo_info.file_path}"
            new_achievement_data[message.chat.id]['photo_url'] = photo_url

            # Додаємо нове досягнення до Firebase
            achievement_name = new_achievement_data[message.chat.id]['name']
            add_new_achievement(achievement_name, photo_url)
            bot.send_message(message.chat.id, f"Досягнення '{achievement_name}' успішно створено!")
            del new_achievement_data[message.chat.id]  # Очищуємо тимчасові дані
        else:
            bot.send_message(message.chat.id, "Будь ласка, надішліть фото для нового досягнення.")
    elif user_id not in user_selected_achievement:
        bot.send_message(message.chat.id, "Спершу виберіть досягнення за допомогою команди /achievements.")
    else:
        achievement_id = user_selected_achievement[user_id]

        if message.text:
            text = message.text
            photo_url = None
            add_user_to_achievement(user_id, achievement_id, text, photo_url)
            bot.send_message(message.chat.id, "Ваш текст для досягнення збережено!")
        
        elif message.photo:
            photo_id = message.photo[-1].file_id
            photo_info = bot.get_file(photo_id)
            photo_url = f"https://api.telegram.org/file/bot{TOKEN}/{photo_info.file_path}"
            text = "Фото досягнення"
            add_user_to_achievement(user_id, achievement_id, text, photo_url)
            bot.send_message(message.chat.id, "Ваше фото для досягнення збережено!")

# Запуск бота
bot.polling()
