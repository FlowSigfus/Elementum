import random
from database import get_db, now_msk
from decorators import positive_args

def get_today_str():
    return now_msk().date().isoformat()

@positive_args
def claim_daily_case(user_id, manual_override=False):
"""Проверка возможности получения кейса сегодня, Увеличение стрика, Выбор редкости карт в зависимости от стрика, Выдача до 10 уникальных карт"""
    with get_db() as conn:
        row = conn.execute('SELECT last_claim_date, streak FROM daily_cases WHERE user_id = ?', (user_id,)).fetchone()
        today = get_today_str()
        if not manual_override and row and row['last_claim_date'] == today:
            return None, None, "Сегодня вы уже забирали кейс"
        streak = (row['streak'] + 1) if row else 1

        # Вероятности редкостей (зависят от стрика)
        if streak >= 7:
            rarities_weights = [('легендарная', 0.1), ('эпическая', 0.3), ('редкая', 0.6), ('обычная', 1.0)]
        else:
            rarities_weights = [('легендарная', 0.02), ('эпическая', 0.1), ('редкая', 0.3), ('обычная', 1.0)]

        awarded_cards = []       # список имён выданных карт
        awarded_ids = set()      # чтобы не повторяться
        #  до 10 разных карт
        attempts = 0
        while len(awarded_cards) < 10 and attempts < 50:   # попытки, чтобы избежать бесконечного цикла
            # Выбираем редкость по вероятностям
            roll = random.random()
            chosen_rarity = 'обычная'
            for rarity, threshold in rarities_weights:
                if roll < threshold:
                    chosen_rarity = rarity
                    break
            # Ищем случайную карту нужной редкости, ещё не выданную
            card = conn.execute(
                'SELECT id, name FROM cards WHERE rarity = ? AND id NOT IN ({}) ORDER BY RANDOM() LIMIT 1'.format(
                    ','.join('?' for _ in awarded_ids) if awarded_ids else '0'
                ), (chosen_rarity,) + tuple(awarded_ids)
            ).fetchone()
            if card:
                awarded_ids.add(card['id'])
                awarded_cards.append(card['name'])
                conn.execute('''
                    INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, 1)
                    ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + 1
                ''', (user_id, card['id']))
            attempts += 1

        # Обновляем стрик и дату
        conn.execute('''
            INSERT INTO daily_cases (user_id, last_claim_date, streak) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_claim_date=excluded.last_claim_date, streak=excluded.streak
        ''', (user_id, today, streak))
        conn.commit()

        if awarded_cards:
            return None, None, f"Вы получили карты: {', '.join(awarded_cards)} (всего {len(awarded_cards)} шт.)"
        else:
            return None, None, "Не удалось выдать карты"

def check_and_award_quests(user_id, action_type, value=1):
""" Отслеживает выполнение ежедневных квестов игроком и автоматически выдаёт награды при достижении нужного прогресса"""
    today = get_today_str()
    with get_db() as conn:
        quests = conn.execute('''
            SELECT q.*, uq.progress, uq.completed
            FROM daily_quests q
            LEFT JOIN user_quests uq ON uq.quest_id = q.id AND uq.user_id = ? AND uq.date = ?
            WHERE uq.completed = 0 OR uq.completed IS NULL
        ''', (user_id, today)).fetchall()
        for q in quests:
            if q['requirement_type'] == action_type and not q['completed']:
                new_progress = (q['progress'] or 0) + value
                if new_progress >= q['requirement_value']:
                    conn.execute('''
                        INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                        ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
                    ''', (user_id, q['reward_card_id'], q['reward_quantity'], q['reward_quantity']))
                    conn.execute('''
                        INSERT OR REPLACE INTO user_quests (user_id, quest_id, progress, completed, date)
                        VALUES (?, ?, ?, 1, ?)
                    ''', (user_id, q['id'], q['requirement_value'], today))
                else:
                    conn.execute('''
                        INSERT OR REPLACE INTO user_quests (user_id, quest_id, progress, completed, date)
                        VALUES (?, ?, ?, 0, ?)
                    ''', (user_id, q['id'], new_progress, today))
        conn.commit()

def check_achievements(user_id, action_type, value=1, recursive=True):
""" Проверка и выдача достижений игроку.
 Получает список уже полученных игроком достижений из таблицы user_achievements, Ищет новые достижения в таблице achievements, имеющее тот же requirement_type. 
 Для каждого подходящего достижения - проверяет родительское достижение (parent_achievement). Если оно есть, но игрок его ещё не получил — ачивка не выдаётся (нужна иерархия)
 Если recursive == True, вызывает саму себя с теми же параметрами, но recursive=False. Это нужно, чтобы после выдачи одной ачивки сразу проверить, не выполнилось ли следующее достижение (например, цепочка: 10 побед → 50 побед → 100 побед). Рекурсия ограничена одним уровнем, чтобы избежать бесконечного цикла."""
    with get_db() as conn:
        achieved_ids = [row['achievement_id'] for row in conn.execute('SELECT achievement_id FROM user_achievements WHERE user_id = ?', (user_id,))]
        placeholders = ','.join('?' for _ in achieved_ids) if achieved_ids else '0'
        query = f'''
            SELECT * FROM achievements
            WHERE requirement_type = ?
            AND requirement_value <= ?
            AND id NOT IN ({placeholders})
        '''
        params = [action_type, value] + achieved_ids
        new_achievements = conn.execute(query, params).fetchall()
        awarded = []
        for ach in new_achievements:
            if ach['parent_achievement']:
                parent_obtained = conn.execute('SELECT 1 FROM user_achievements WHERE user_id = ? AND achievement_id = ?', (user_id, ach['parent_achievement'])).fetchone()
                if not parent_obtained:
                    continue
            conn.execute('INSERT INTO user_achievements (user_id, achievement_id, unlocked_at) VALUES (?, ?, ?)',
                         (user_id, ach['id'], now_msk().isoformat()))
            conn.execute('''
                INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
            ''', (user_id, ach['reward_card_id'], ach['reward_quantity'], ach['reward_quantity']))
            awarded.append(ach['name'])
            conn.commit()
            if recursive:
                check_achievements(user_id, action_type, value, recursive=False)
        return awarded

def claim_daily_bonus(user_id):
""" Ежедневный бонус для игрока — выдаёт случайную обычную карту (5-10 копий) и монеты"""
    today = get_today_str()
    with get_db() as conn:   
        row = conn.execute('SELECT last_daily_bonus FROM users WHERE id = ?', (user_id,)).fetchone()
        if row and row['last_daily_bonus'] == today:
            return False, "Сегодня вы уже получили бонус"
        card = conn.execute('SELECT id, name FROM cards WHERE rarity = "обычная" ORDER BY RANDOM() LIMIT 1').fetchone()
        if not card:
            card = {'id': 1, 'name': 'Огненный удар'}
        bonus_qty = random.randint(5, 10)
        conn.execute('''
            INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
            ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
        ''', (user_id, card['id'], bonus_qty, bonus_qty))
        conn.execute('UPDATE users SET coins = coins + 20, last_daily_bonus = ? WHERE id = ?', (today, user_id))
        conn.commit()
        return True, f"Вы получили бонусную карту {card['name']} x{bonus_qty} и 20 монет!"
