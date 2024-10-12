import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE

cred = credentials.Certificate(FIREBASE)
firebase_admin.initialize_app(cred)

db = firestore.client()

def add_new_achievement(name, photo_url):
    achievement_ref = db.collection('achievements').document()
    achievement_ref.set({
        'name': name,
        'description': '',
        'photo_url': photo_url
    })


# Додаємо користувача до досягнення
def add_user_to_achievement(user_id, achievement_id, text, photo_url):
    achievement_ref = db.collection('achievements').document(achievement_id)
    achievement_ref.collection('users').document(user_id).set({
        'text': text,
        'photo_url': photo_url
    }, merge=True)

# Отримуємо список досягнень з бази даних
def get_achievements():
    achievements_ref = db.collection('achievements')
    achievements = achievements_ref.stream()

    achievement_list = []
    for achievement in achievements:
        achievement_data = achievement.to_dict()
        achievement_list.append({
            'id': achievement.id,
            'name': achievement_data.get('name'),
            'description': achievement_data.get('description')
        })
    
    return achievement_list

# Отримуємо глобальну статистику
def get_global_stats():
    achievements_ref = db.collection('achievements')
    achievements = achievements_ref.stream()

    total_achievements = 0
    for achievement in achievements:
        users_ref = achievement.reference.collection('users')
        users = users_ref.stream()
        total_achievements += len(list(users))
    
    return total_achievements
