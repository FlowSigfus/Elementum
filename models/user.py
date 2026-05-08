from datetime import datetime, timedelta
import database as db

class User:
    def __init__(self, user_id, username, element='fire', last_element_change=None,
                 trained=False, curse_end=None, avatar='default.png',
                 last_nickname_change=None, allow_duels=True):
        self._id = user_id
        self._username = username
        self._element = element
        self._last_element_change = last_element_change
        self._health = 100
        self._cards = []
        self._trained = trained
        self._curse_end = curse_end  # строка ISO или None
        self._avatar = avatar
        self._last_nickname_change = last_nickname_change
        self._allow_duels = allow_duels

    @property
    def id(self):
        return self._id

    @property
    def username(self):
        return self._username

    @property
    def element(self):
        return self._element

    @property
    def health(self):
        return self._health

    @health.setter
    def health(self, value):
        self._health = max(0, min(100, value))

    @property
    def trained(self):
        return self._trained

    @property
    def max_health(self):
        return 100

    @property
    def cursed(self):
        if self._curse_end:
            return datetime.now() < datetime.fromisoformat(self._curse_end)
        return False

    @property
    def avatar(self):
        return self._avatar

    @property
    def allow_duels(self):
        return self._allow_duels

    def set_avatar(self, avatar_filename):
        self._avatar = avatar_filename
        with db.get_db() as conn:
            conn.execute('UPDATE users SET avatar = ? WHERE id = ?', (avatar_filename, self._id))
            conn.commit()

    def change_nickname(self, new_username):
        if self._last_nickname_change:
            last = datetime.fromisoformat(self._last_nickname_change)
            if datetime.now() - last < timedelta(days=30):
                return False, "Никнейм можно менять не чаще раза в месяц"
        with db.get_db() as conn:
            try:
                conn.execute('UPDATE users SET username = ?, last_nickname_change = ? WHERE id = ?',
                             (new_username, datetime.now().isoformat(), self._id))
                conn.commit()
                self._username = new_username
                self._last_nickname_change = datetime.now().isoformat()
                return True, "Никнейм изменён"
            except sqlite3.IntegrityError:
                return False, "Это имя уже занято"

    def set_element(self, new_element):
        if self._last_element_change:
            last = datetime.fromisoformat(self._last_element_change)
            if datetime.now() - last < timedelta(days=30):
                return False, "Стихию можно менять не чаще раза в месяц"
        self._element = new_element
        self._last_element_change = datetime.now().isoformat()
        with db.get_db() as conn:
            conn.execute('UPDATE users SET element = ?, last_element_change = ? WHERE id = ?',
                         (new_element, self._last_element_change, self._id))
            conn.commit()
        return True, "Стихия изменена"

    def train_element(self):
        if self._trained:
            return False, "Вы уже обучены"
        self._trained = True
        with db.get_db() as conn:
            conn.execute('UPDATE users SET trained = 1 WHERE id = ?', (self._id,))
            conn.commit()
        return True, "Вы усилили свою стихию!"

    def apply_curse(self, hours=24):
        end_time = datetime.now() + timedelta(hours=hours)
        self._curse_end = end_time.isoformat()
        with db.get_db() as conn:
            conn.execute('UPDATE users SET curse_end = ? WHERE id = ?', (self._curse_end, self._id))
            conn.commit()

    def get_element_multiplier(self):
        mult = 1.0
        if self._trained:
            mult += 0.2
        if self.cursed:
            mult -= 0.2
        return mult

    def take_damage(self, amount):
        self.health -= amount

    def heal(self, amount):
        self.health += amount

    def add_card(self, card):
        self._cards.append(card)

    def get_cards(self):
        return self._cards.copy()