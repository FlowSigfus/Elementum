import sqlite3
import hashlib
import os
import secrets
from datetime import datetime, timezone, timedelta

DB_PATH = 'game.db'
MSK_TZ = timezone(timedelta(hours=3))
NFC_SECRET = "my_super_secret_key_change_me"

def now_msk():
    return datetime.now(MSK_TZ)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # ------------------ Таблица пользователей ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                element TEXT DEFAULT 'fire',
                last_element_change TEXT,
                trained INTEGER DEFAULT 0,
                curse_end TEXT,
                last_nfc TEXT,
                avatar TEXT DEFAULT "default.png",
                last_nickname_change TEXT,
                email TEXT UNIQUE,
                is_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                reset_token TEXT,
                reset_token_expiry TEXT,
                last_nfc_boost TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_daily_bonus TEXT,
                allow_duels INTEGER DEFAULT 1,
                coins INTEGER DEFAULT 0
            )
        ''')

        # ------------------ Временные регистрации (до подтверждения email) ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                verification_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ------------------ Коллекция карт игроков ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_cards (
                user_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                level INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, card_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # ------------------ Прогресс сюжета ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS story_progress (
                user_id INTEGER PRIMARY KEY,
                chapter INTEGER DEFAULT 1,
                battle_index INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # ------------------ Справочник карт ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                element TEXT,
                base_value INTEGER,
                mana_cost INTEGER DEFAULT 1,
                description TEXT,
                rarity TEXT DEFAULT 'обычная'
            )
        ''')

        # ------------------ Ежедневные кейсы ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_cases (
                user_id INTEGER PRIMARY KEY,
                last_claim_date TEXT,
                streak INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Ежедневные квесты ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_quests (
                id INTEGER PRIMARY KEY,
                name TEXT,
                description TEXT,
                requirement_type TEXT,
                requirement_value INTEGER,
                reward_card_id INTEGER,
                reward_quantity INTEGER
            )
        ''')

        # ------------------ Прогресс квестов ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_quests (
                user_id INTEGER,
                quest_id INTEGER,
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                date TEXT,
                PRIMARY KEY (user_id, quest_id, date),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Достижения ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY,
                name TEXT,
                description TEXT,
                requirement_type TEXT,
                requirement_value INTEGER,
                reward_card_id INTEGER,
                reward_quantity INTEGER,
                parent_achievement INTEGER,
                FOREIGN KEY (parent_achievement) REFERENCES achievements(id)
            )
        ''')

        # ------------------ Выданные достижения ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER,
                achievement_id INTEGER,
                unlocked_at TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Статистика игрока ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_damage INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Витрина (любимые карты) ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS showcase (
                user_id INTEGER,
                card_id INTEGER,
                slot INTEGER CHECK (slot BETWEEN 1 AND 3),
                PRIMARY KEY (user_id, slot),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (card_id) REFERENCES cards(id)
            )
        ''')

        # ------------------ PvP очередь ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pvp_queue (
                user_id INTEGER PRIMARY KEY,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ------------------ PvP матчи ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pvp_matches (
                id TEXT PRIMARY KEY,
                player1_id INTEGER,
                player2_id INTEGER,
                status TEXT DEFAULT 'waiting',
                winner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player1_id) REFERENCES users(id),
                FOREIGN KEY (player2_id) REFERENCES users(id)
            )
        ''')

        # ------------------ PvP рейтинг ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pvp_rating (
                user_id INTEGER PRIMARY KEY,
                rating INTEGER DEFAULT 1200,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Крафт рецепты ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS craft_recipes (
                id INTEGER PRIMARY KEY,
                input_rarity TEXT,
                output_rarity TEXT,
                cards_required INTEGER DEFAULT 3
            )
        ''')
        conn.executemany('INSERT OR IGNORE INTO craft_recipes (input_rarity, output_rarity) VALUES (?,?)', [
            ('обычная', 'редкая'),
            ('редкая', 'эпическая'),
            ('эпическая', 'легендарная'),
        ])

        # ------------------ Торговые предложения ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trade_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                card_id INTEGER,
                quantity INTEGER DEFAULT 1,
                wanted_card_id INTEGER,
                wanted_quantity INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                give_coins INTEGER DEFAULT 0,
                give_type TEXT DEFAULT "card",
                wanted_type TEXT DEFAULT "card",
                wanted_coins INTEGER DEFAULT 0,
                status TEXT DEFAULT "active",
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Друзья ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER,
                friend_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, friend_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (friend_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Приглашения в друзья (токены) ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS friend_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                token TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Магазин: товары (NFC-карты и наборы) ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price_cents INTEGER NOT NULL,
                delivery_required INTEGER DEFAULT 1,
                weight_grams INTEGER DEFAULT 0,
                image TEXT,
                stock INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_digital INTEGER DEFAULT 0
            )
        ''')

        # ------------------ Магазин: заказы ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_orders (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                fullname TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                delivery_method TEXT,
                delivery_address TEXT,
                delivery_price_cents INTEGER DEFAULT 0,
                total_cents INTEGER NOT NULL,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                payment_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # ------------------ Магазин: позиции заказа ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                price_cents INTEGER,
                FOREIGN KEY (order_id) REFERENCES shop_orders(id),
                FOREIGN KEY (product_id) REFERENCES shop_products(id)
            )
        ''')

        # ------------------ Магазин: таблица платежей ------------------
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_payments (
                id TEXT PRIMARY KEY,
                order_id TEXT,
                amount_cents INTEGER,
                status TEXT DEFAULT 'pending',
                yookassa_id TEXT,
                confirmation_url TEXT,
                paid_at TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES shop_orders(id)
            )
        ''')

        # ------------------ Заполнение товаров, если пусто ------------------
        cursor = conn.execute("SELECT COUNT(*) FROM shop_products")
        if cursor.fetchone()[0] == 0:
            default_products = [
                (1, 'Полный набор NFC-карт (60 штук)', 'Все 60 карт игры', 180000, 1, 0, 'full_set.jpg', 10, 1, 0),
                (2, 'Набор стихии Огня (10 карт)', '10 карт огненной стихии', 30000, 1, 0, 'fire_set.jpg', 10, 1, 0),
                (3, 'Набор стихии Воды (10 карт)', '10 карт водной стихии', 30000, 1, 0, 'water_set.jpg', 10, 1, 0),
                (4, 'Набор стихии Земли (10 карт)', '10 карт земляной стихии', 30000, 1, 0, 'earth_set.jpg', 10, 1, 0),
                (5, 'Набор стихии Воздуха (10 карт)', '10 карт воздушной стихии', 30000, 1, 0, 'air_set.jpg', 10, 1, 0),
                (6, 'Набор стихии Света (10 карт)', '10 карт светлой стихии', 30000, 1, 0, 'light_set.jpg', 10, 1, 0),
                (7, 'Набор стихии Тьмы (10 карт)', '10 карт тёмной стихии', 30000, 1, 0, 'dark_set.jpg', 10, 1, 0),
                (8, 'Стартовый набор (15 карт)', 'Базовый набор для начинающих', 15000, 1, 0, 'starter_set.jpg', 15, 1, 0),
                (9, '100 монет', 'Внутриигровая валюта', 1000, 0, 0, 'coins_pack.jpg', 999, 1, 1),  # is_digital=1
            ]
            conn.executemany('INSERT INTO shop_products (id, name, description, price_cents, delivery_required, weight_grams, image, stock, is_active, is_digital) VALUES (?,?,?,?,?,?,?,?,?,?)', default_products)

        # ------------------ NFC hash для карт ------------------
        cursor = conn.execute("PRAGMA table_info(cards)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'nfc_hash' not in columns:
            conn.execute('ALTER TABLE cards ADD COLUMN nfc_hash TEXT')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_nfc_hash ON cards (nfc_hash)')

        # ------------------ Заполнение карт, если таблица пуста ------------------
        cursor = conn.execute("SELECT COUNT(*) FROM cards")
        if cursor.fetchone()[0] == 0:
            default_cards = [
                # Огонь (1-10)
                (1, 'Огненный удар', 'attack', 'fire', 20, 1, 'Наносит 20 урона', 'обычная'),
                (2, 'Пламенный всполох', 'attack', 'fire', 25, 2, 'Наносит 25 урона', 'обычная'),
                (3, 'Огненный шар', 'attack', 'fire', 35, 3, 'Мощный огненный шар', 'редкая'),
                (4, 'Костёр', 'heal', 'fire', 10, 1, 'Восстанавливает 10 здоровья', 'обычная'),
                (5, 'Огненная стена', 'defense', 'fire', 20, 2, 'Блокирует 20 урона', 'обычная'),
                (6, 'Пепельный щит', 'defense', 'fire', 30, 3, 'Блокирует 30 урона', 'редкая'),
                (7, 'Инферно', 'attack', 'fire', 45, 4, 'Наносит 45 урона всем врагам', 'эпическая'),
                (8, 'Феникс', 'heal', 'fire', 40, 4, 'Восстанавливает 40 здоровья и накладывает щит 20', 'легендарная'),
                (9, 'Огненный дракон', 'attack', 'fire', 60, 5, 'Наносит 60 урона, игнорирует щит', 'легендарная'),
                (10, 'Испепеление', 'attack', 'fire', 30, 3, 'Наносит 30 урона и поджигает (5 урона ход)', 'эпическая'),
                # Вода (11-20)
                (11, 'Ледяная стрела', 'attack', 'water', 18, 1, 'Наносит 18 урона', 'обычная'),
                (12, 'Водная струя', 'attack', 'water', 22, 2, 'Наносит 22 урона', 'обычная'),
                (13, 'Ледяной щит', 'defense', 'water', 25, 2, 'Блокирует 25 урона', 'редкая'),
                (14, 'Исцеляющий дождь', 'heal', 'water', 15, 2, 'Восстанавливает 15 здоровья', 'обычная'),
                (15, 'Цунами', 'attack', 'water', 40, 4, 'Наносит 40 урона', 'эпическая'),
                (16, 'Ледяная глыба', 'defense', 'water', 35, 3, 'Блокирует 35 урона', 'редкая'),
                (17, 'Жажда крови', 'attack', 'water', 20, 2, 'Наносит 20 урона и лечит на 10', 'редкая'),
                (18, 'Снежная буря', 'attack', 'water', 25, 3, 'Наносит 25 урона и замораживает (пропуск хода)', 'эпическая'),
                (19, 'Водяной дракон', 'attack', 'water', 55, 5, 'Наносит 55 урона', 'легендарная'),
                (20, 'Омут', 'skip', 'water', 0, 1, 'Пропускает ход противника', 'редкая'),
                # Земля (21-30)
                (21, 'Земляной удар', 'attack', 'earth', 22, 1, 'Наносит 22 урона', 'обычная'),
                (22, 'Каменная стена', 'defense', 'earth', 30, 2, 'Блокирует 30 урона', 'редкая'),
                (23, 'Прикосновение земли', 'heal', 'earth', 15, 2, 'Восстанавливает 15 здоровья', 'обычная'),
                (24, 'Землетрясение', 'attack', 'earth', 35, 3, 'Наносит 35 урона', 'редкая'),
                (25, 'Костяная броня', 'defense', 'earth', 20, 1, 'Блокирует 20 урона', 'обычная'),
                (26, 'Оползень', 'attack', 'earth', 45, 4, 'Наносит 45 урона', 'эпическая'),
                (27, 'Голем', 'defense', 'earth', 50, 4, 'Блокирует 50 урона', 'эпическая'),
                (28, 'Корни жизни', 'heal', 'earth', 30, 3, 'Восстанавливает 30 здоровья', 'редкая'),
                (29, 'Каменный тиран', 'attack', 'earth', 65, 5, 'Наносит 65 урона', 'легендарная'),
                (30, 'Пыльная буря', 'skip', 'earth', 0, 2, 'Пропускает ход противника', 'редкая'),
                # Воздух (31-40)
                (31, 'Порыв ветра', 'attack', 'air', 20, 1, 'Наносит 20 урона', 'обычная'),
                (32, 'Воздушный щит', 'defense', 'air', 25, 2, 'Блокирует 25 урона', 'редкая'),
                (33, 'Молния', 'attack', 'air', 35, 2, 'Наносит 35 урона', 'редкая'),
                (34, 'Вихрь', 'attack', 'air', 40, 3, 'Наносит 40 урона', 'эпическая'),
                (35, 'Цепная молния', 'attack', 'air', 25, 3, 'Рекурсивно бьёт с уменьшением урона', 'эпическая'),
                (36, 'Ураган', 'attack', 'air', 55, 5, 'Наносит 55 урона', 'легендарная'),
                (37, 'Лёгкое дуновение', 'heal', 'air', 10, 1, 'Восстанавливает 10 здоровья', 'обычная'),
                (38, 'Буря', 'attack', 'air', 30, 3, 'Наносит 30 урона и сбивает щит', 'редкая'),
                (39, 'Попутный ветер', 'skip', 'air', 0, 0, 'Пропускает ход противника', 'обычная'),
                (40, 'Грозовой фронт', 'defense', 'air', 40, 3, 'Блокирует 40 урона', 'эпическая'),
                # Свет (41-50)
                (41, 'Световой луч', 'attack', 'light', 25, 1, 'Наносит 25 урона', 'обычная'),
                (42, 'Божественный щит', 'defense', 'light', 30, 2, 'Блокирует 30 урона', 'редкая'),
                (43, 'Исцеление', 'heal', 'light', 20, 2, 'Восстанавливает 20 здоровья', 'обычная'),
                (44, 'Святая кара', 'attack', 'light', 40, 3, 'Наносит 40 урона', 'эпическая'),
                (45, 'Молитва', 'heal', 'light', 30, 3, 'Восстанавливает 30 здоровья', 'редкая'),
                (46, 'Ангельские крылья', 'defense', 'light', 50, 4, 'Блокирует 50 урона', 'эпическая'),
                (47, 'Свет утра', 'heal', 'light', 50, 5, 'Восстанавливает 50 здоровья', 'легендарная'),
                (48, 'Паладин', 'attack', 'light', 60, 5, 'Наносит 60 урона', 'легендарная'),
                (49, 'Ослепление', 'skip', 'light', 0, 2, 'Пропускает ход противника', 'редкая'),
                (50, 'Благословение', 'heal', 'light', 25, 2, 'Восстанавливает 25 здоровья и даёт щит 10', 'эпическая'),
                # Тьма (51-60)
                (51, 'Теневой удар', 'attack', 'dark', 25, 1, 'Наносит 25 урона', 'обычная'),
                (52, 'Вампиризм', 'attack', 'dark', 20, 2, 'Наносит 20 урона, лечит на 10', 'редкая'),
                (53, 'Тёмный щит', 'defense', 'dark', 30, 2, 'Блокирует 30 урона', 'редкая'),
                (54, 'Проклятие', 'attack', 'dark', 15, 1, 'Наносит 15 урона и накладывает проклятие (ослабление 0.8)', 'эпическая'),
                (55, 'Ночь', 'skip', 'dark', 0, 1, 'Пропускает ход противника', 'обычная'),
                (56, 'Теневой дракон', 'attack', 'dark', 55, 5, 'Наносит 55 урона', 'легендарная'),
                (57, 'Жертва', 'heal', 'dark', 30, 3, 'Восстанавливает 30 здоровья, но теряет 5 здоровья в следующем ходу', 'эпическая'),
                (58, 'Тьма', 'defense', 'dark', 45, 4, 'Блокирует 45 урона', 'эпическая'),
                (59, 'Кошмар', 'attack', 'dark', 35, 3, 'Наносит 35 урона и пугает (снижает атаку)', 'редкая'),
                (60, 'Чёрная дыра', 'attack', 'dark', 70, 6, 'Наносит 70 урона', 'легендарная'),
            ]
            conn.executemany('INSERT INTO cards (id, name, action_type, element, base_value, mana_cost, description, rarity) VALUES (?,?,?,?,?,?,?,?)', default_cards)

        # ------------------ Генерация nfc_hash для карт, где он отсутствует ------------------
        cursor = conn.execute('SELECT id FROM cards WHERE nfc_hash IS NULL')
        rows = cursor.fetchall()
        for row in rows:
            new_hash = secrets.token_hex(16)
            conn.execute('UPDATE cards SET nfc_hash = ? WHERE id = ?', (new_hash, row['id']))

        # ------------------ Заполнение ежедневных квестов ------------------
        default_quests = [
            (1, 'Победитель', 'Победить в 3 сражениях', 'win_battles', 3, 5, 1),
            (2, 'Маг-разрушитель', 'Нанести 500 урона', 'damage_dealt', 500, 10, 1),
            (3, 'Коллекционер', 'Получить 2 карты из кейсов', 'cards_from_cases', 2, 3, 1),
            (4, 'Защитник', 'Поставить щит 5 раз', 'shields_used', 5, 2, 1),
            (5, 'Целитель', 'Восстановить 200 здоровья', 'healing_done', 200, 14, 1),
            (6, 'Страйкер', 'Использовать 10 карт в боях', 'cards_used', 10, 1, 1),
            (7, 'Авантюрист', 'Победить босса', 'defeat_boss', 1, 7, 1),
        ]
        conn.executemany('INSERT OR IGNORE INTO daily_quests (id, name, description, requirement_type, requirement_value, reward_card_id, reward_quantity) VALUES (?,?,?,?,?,?,?)', default_quests)

        # ------------------ Заполнение достижений ------------------
        default_achievements = [
            (1, 'Новичок', 'Победить первого босса', 'defeat_boss', 1, 1, 1, None),
            (2, 'Завоеватель', 'Победить 5 боссов', 'defeat_boss', 5, 5, 1, 1),
            (3, 'Мастер стихий', 'Собрать все 6 кристаллов', 'story_chapter', 6, 7, 1, None),
            (4, 'Легенда', 'Завершить сюжет', 'story_chapter', 25, 15, 3, 3),
            (5, 'Картограф', 'Собрать 30 разных карт', 'unique_cards', 30, 9, 1, None),
            (6, 'Мастер огня', 'Собрать все карты огня', 'collect_element_cards', 10, 7, 1, None),
            (7, 'Дружба', 'Победить босса в коопе с тремя друзьями', 'coop_boss', 1, 5, 3, None),
            (8, 'Торговец', 'Совершить 10 обменов картами', 'trades', 10, 2, 2, None),
            (9, 'Крафтер', 'Создать 5 карт через крафт', 'crafts', 5, 9, 1, None),
        ]
        conn.executemany('INSERT OR IGNORE INTO achievements (id, name, description, requirement_type, requirement_value, reward_card_id, reward_quantity, parent_achievement) VALUES (?,?,?,?,?,?,?,?)', default_achievements)

        conn.commit()

# ------------------ Хеширование паролей ------------------
def hash_password(password):
    salt = os.urandom(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt + pwd_hash

def verify_password(stored, provided):
    salt = stored[:32]
    original = stored[32:]
    calc = hashlib.pbkdf2_hmac('sha256', provided.encode('utf-8'), salt, 100000)
    return calc == original

"""# ------------------ Верификация NFC-меток ------------------
def verify_nfc_tag(tag_id, signature):
    expected = hashlib.sha256((tag_id + NFC_SECRET).encode()).hexdigest()
    return signature == expected"""
