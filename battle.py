import random
from models.card import get_damage_multiplier
from decorators import logger   # импортируем декоратор

class Battle:
    def __init__(self, player, enemy_health, enemy_cards, enemy_element, player_card_pool, player_cards_list, get_card_func, enemy_name="Противник"):
        self.player = player
        self.enemy_name = enemy_name
        self.enemy_health = enemy_health
        self.max_health = enemy_health           # для врага (прогресс-бар)
        self.enemy_cards = enemy_cards
        self.enemy_element = enemy_element
        self.player_card_pool = player_card_pool
        self.player_cards_list = player_cards_list
        # Группировка карт по типу действия
        self.grouped_cards = {
            'attack': [],
            'defense': [],
            'heal': [],
            'skip': []
        }
        for card in player_cards_list:
            self.grouped_cards[card.action_type].append(card)
        self.get_card_by_id = get_card_func
        self.player_shield = 0
        self.enemy_shield = 0
        self.player_skip = False
        self.enemy_skip = False
        self.total_player_damage_dealt = 0
        self.turn = 'player'
        self.history = []
        self.boost_used = False
        self.enemy = type('Enemy', (), {'username': 'Противник'})()   # простой объект с атрибутом username = "Противник", чтобы имитировать структуру игрока
    @logger
    def apply_player_card(self, card_id):
    """Проверка возможности хода, Определение типа карты и выполнение действия, ереключение хода и ход врага"""
        if self.turn != 'player':
            return "Сейчас не ваш ход!"
        if self.player_card_pool.get(card_id, 0) <= 0:
            return "У вас больше нет этой карты!"
        card = self.get_card_by_id(card_id)
        if not card:
            return "Ошибка: карта не найдена"

        # Вычисляем параметры до применения (для истории)
        if card.action_type == 'attack':
            defender_element = self.enemy_element
            player_mult = self.player.get_element_multiplier()
            element_mult = get_damage_multiplier(card.element, defender_element) # множитель стихий из таблицы ELEMENT_ADVANTAGE
            final_damage = int(card.base_value * element_mult * player_mult)
            actual_damage = self.damage_enemy(final_damage)
            # Запись в историю
            self.history.append({
                'actor': self.player.username,
                'card_name': card.name,
                'element': card.element,
                'damage': actual_damage,
                'multiplier': element_mult,
                'player_mult': player_mult,
                'target': 'enemy'
            })
            msg = f"{self.player.username} наносит {actual_damage} урона!"
        elif card.action_type == 'defense':
            self.shield_player(card.base_value)
            self.history.append({
                'actor': self.player.username,
                'card_name': card.name,
                'effect': f'щит {card.base_value}'
            })
            msg = f"{self.player.username} получает щит {card.base_value}!"
        elif card.action_type == 'heal':
            self.heal_player(card.base_value)
            self.history.append({
                'actor': self.player.username,
                'card_name': card.name,
                'effect': f'лечение {card.base_value}'
            })
            msg = f"{self.player.username} восстанавливает {card.base_value} здоровья!"
        elif card.action_type == 'skip':
            self.skip_enemy()
            self.history.append({
                'actor': self.player.username,
                'card_name': card.name,
                'effect': 'пропуск хода врага'
            })
            msg = f"{self.player.username} заставляет противника пропустить ход!"
        else:
            msg = "Ничего не произошло"

        # Уменьшаем количество карты
        self.player_card_pool[card_id] -= 1

        if self.enemy_health <= 0:
            return "Победа! " + msg
        self.turn = 'enemy'
        enemy_msg = self.enemy_turn()
        if self.enemy_health <= 0:
            return msg + "<br>" + enemy_msg + "<br>Победа!"
        if self.player.health <= 0:
            return msg + "<br>" + enemy_msg + "<br>Вы проиграли!"
        return msg + "<br>" + enemy_msg
    @logger
    def enemy_turn(self):
    """ Проверка пропуска хода врага, «Умный» выбор карты, Применение выбранной карты, Переключение хода и возврат результата"""
        if self.enemy_skip:
            self.enemy_skip = False
            self.turn = 'player'
            return "Противник пропускает ход!"

        # Умный выбор карты вместо случайного
        available_cards = self.enemy_cards[:]
        # Убираем лечение, если здоровье почти полное
        if self.enemy_health >= 0.8 * self.max_health:
            available_cards = [c for c in available_cards if self.get_card_by_id(c).action_type != 'heal']
        # Убираем защиту, если уже есть щит
        if self.enemy_shield > 0:
            available_cards = [c for c in available_cards if self.get_card_by_id(c).action_type != 'defense']

        # Если после фильтрации ничего не осталось, берём исходный список
        if not available_cards:
            available_cards = self.enemy_cards

        card_id = random.choice(available_cards)
        card = self.get_card_by_id(card_id)
        if not card:
            self.turn = 'player'
            return "Противник пытался использовать несуществующую карту, ход пропущен"

        if card.action_type == 'attack':
            defender_element = self.player.element
            element_mult = get_damage_multiplier(card.element, defender_element)
            final_damage = int(card.base_value * element_mult)
            actual_damage = self.damage_player(final_damage)
            self.history.append({
                'actor': 'Противник',
                'card_name': card.name,
                'element': card.element,
                'damage': actual_damage,
                'multiplier': element_mult,
                'target': 'player'
            })
            msg = f"Противник наносит {actual_damage} урона!"
        elif card.action_type == 'defense':
            self.shield_enemy(card.base_value)
            self.history.append({
                'actor': 'Противник',
                'card_name': card.name,
                'effect': f'щит {card.base_value}'
            })
            msg = f"Противник получает щит {card.base_value}!"
        elif card.action_type == 'heal':
            self.heal_enemy(card.base_value)
            self.history.append({
                'actor': 'Противник',
                'card_name': card.name,
                'effect': f'лечение {card.base_value}'
            })
            msg = f"Противник восстанавливает {card.base_value} здоровья!"
        elif card.action_type == 'skip':
            self.skip_player()
            self.history.append({
                'actor': 'Противник',
                'card_name': card.name,
                'effect': 'пропуск хода игрока'
            })
            msg = f"Противник заставляет вас пропустить ход!"
        else:
            msg = "Ничего не произошло"

        if self.player.health <= 0:
            msg += "<br>Вы проиграли!"
        self.turn = 'player'
        return msg
    @logger
    def apply_boost(self, card):
    """ Проверка возможности усиления, Усиление в зависимости от типа карты, """
        if self.boost_used:
            return False, "Усиление уже использовано в этом бою"
        if self.turn != 'player':
            return False, "Сейчас не ваш ход"
        # Применяем усиленную версию карты (урон/щит/лечение *1.5)
        if card.action_type == 'attack':
            boosted_damage = int(card.base_value * 1.5)
            defender_element = self.enemy_element
            player_mult = self.player.get_element_multiplier()
            element_mult = get_damage_multiplier(card.element, defender_element)
            final_damage = int(boosted_damage * element_mult * player_mult)
            actual_damage = self.damage_enemy(final_damage)
            self.history.append({
                'actor': self.player.username,
                'card_name': f"✨ {card.name} (усиление)",
                'element': card.element,
                'damage': actual_damage,
                'multiplier': element_mult,
                'player_mult': player_mult,
                'target': 'enemy'
            })
            msg = f"Усиленная атака! Нанесено {actual_damage} урона."
        elif card.action_type == 'defense':
            boosted_shield = int(card.base_value * 1.5)
            self.shield_player(boosted_shield)
            self.history.append({
                'actor': self.player.username,
                'card_name': f"✨ {card.name} (усиление)",
                'effect': f'щит {boosted_shield}'
            })
            msg = f"Усиленный щит! +{boosted_shield} защиты."
        elif card.action_type == 'heal':
            boosted_heal = int(card.base_value * 1.5)
            self.heal_player(boosted_heal)
            self.history.append({
                'actor': self.player.username,
                'card_name': f"✨ {card.name} (усиление)",
                'effect': f'лечение {boosted_heal}'
            })
            msg = f"Усиленное лечение! +{boosted_heal} здоровья."
        elif card.action_type == 'skip':
            self.skip_enemy()
            self.history.append({
                'actor': self.player.username,
                'card_name': f"✨ {card.name} (усиление)",
                'effect': 'пропуск хода врага'
            })
            msg = "Усиленный пропуск хода!"
        else:
            return False, "Эта карта не поддерживает усиление"
        self.boost_used = True
        # Проверка победы
        if self.enemy_health <= 0:
            msg += " Победа!"
        return True, msg

    # Вспомогательные методы
    def damage_enemy(self, amount):
    """ Наносит урон врагу с учётом его текущего щита"""
        actual_damage = amount
        if self.enemy_shield > 0:
            blocked = min(self.enemy_shield, amount)
            actual_damage = amount - blocked
            self.enemy_shield -= blocked
        self.enemy_health -= actual_damage
        self.total_player_damage_dealt += actual_damage
        return actual_damage

    def damage_player(self, amount):
        actual_damage = amount
        if self.player_shield > 0:
            blocked = min(self.player_shield, amount)
            actual_damage = amount - blocked
            self.player_shield -= blocked
        self.player.health -= actual_damage
        return actual_damage

    def shield_player(self, amount): self.player_shield += amount
    def shield_enemy(self, amount): self.enemy_shield += amount
    def heal_player(self, amount): self.player.health = min(100, self.player.health + amount)
    def heal_enemy(self, amount): self.enemy_health = min(100, self.enemy_health + amount)
    def skip_player(self): self.player_skip = True
    def skip_enemy(self): self.enemy_skip = True



class PVPBattle:
    def __init__(self, player1, player2, player1_card_pool, player2_card_pool, get_card_func):
        self.player1 = player1
        self.player2 = player2
        self.player1_card_pool = player1_card_pool.copy()
        self.player2_card_pool = player2_card_pool.copy()
        self.get_card_by_id = get_card_func
        self.player1_health = 100
        self.player2_health = 100
        self.player1_shield = 0
        self.player2_shield = 0
        self.player1_skip = False
        self.player2_skip = False
        self.turn = player1.id
        self.history = []
        self.winner = None

    def apply_card(self, player_id, card_id):
    """ Проверка состояния боя, Определение текущего игрока и противника, Обработка пропуска хода, Проверка наличия карты, Применение эффекта карты в зависимости от action_type, Переключение хода"""
        if self.winner:
            return False, "Бой уже закончен"
        if player_id != self.turn:
            return False, "Сейчас не ваш ход"

        # Определяем игрока и противника
        if player_id == self.player1.id:
            player = self.player1
            opponent = self.player2
            card_pool = self.player1_card_pool
            skip_flag = self.player1_skip
        else:
            player = self.player2
            opponent = self.player1
            card_pool = self.player2_card_pool
            skip_flag = self.player2_skip

        if skip_flag:
            # Пропуск хода из-за предыдущей карты "skip"
            if player_id == self.player1.id:
                self.player1_skip = False
            else:
                self.player2_skip = False
            self.turn = opponent.id
            return True, "Ход пропущен (действие карты противника)"

        if card_pool.get(card_id, 0) <= 0:
            return False, "У вас нет этой карты"
        card = self.get_card_by_id(card_id)
        if not card:
            return False, "Карта не найдена"

        # Применяем карту
        if card.action_type == 'attack':
            defender_element = opponent.element
            attacker_mult = player.get_element_multiplier()
            element_mult = get_damage_multiplier(card.element, defender_element)
            final_damage = int(card.base_value * element_mult * attacker_mult)
            # Наносим урон противнику
            if opponent.id == self.player1.id:
                actual = self._damage_player(opponent.id, final_damage)
            else:
                actual = self._damage_player(opponent.id, final_damage)
            self.history.append({
                'actor': player.username,
                'card_name': card.name,
                'element': card.element,
                'damage': actual,
                'multiplier': element_mult,
                'player_mult': attacker_mult,
                'effect': f'наносит {actual} урона'
            })
            msg = f"{player.username} наносит {actual} урона!"
        elif card.action_type == 'defense':
            shield_amount = card.base_value
            if player.id == self.player1.id:
                self.player1_shield += shield_amount
            else:
                self.player2_shield += shield_amount
            self.history.append({
                'actor': player.username,
                'card_name': card.name,
                'effect': f'получает щит {shield_amount}'
            })
            msg = f"{player.username} получает щит {shield_amount}!"
        elif card.action_type == 'heal':
            heal_amount = card.base_value
            if player.id == self.player1.id:
                self.player1_health = min(100, self.player1_health + heal_amount)
            else:
                self.player2_health = min(100, self.player2_health + heal_amount)
            self.history.append({
                'actor': player.username,
                'card_name': card.name,
                'effect': f'лечит {heal_amount}'
            })
            msg = f"{player.username} восстанавливает {heal_amount} здоровья!"
        elif card.action_type == 'skip':
            # Устанавливаем пропуск хода для противника
            if opponent.id == self.player1.id:
                self.player1_skip = True
            else:
                self.player2_skip = True
            self.history.append({
                'actor': player.username,
                'card_name': card.name,
                'effect': 'пропускает ход противника'
            })
            msg = f"{player.username} заставляет противника пропустить ход!"
        else:
            return False, "Неизвестный тип карты"

        # Уменьшаем количество карты
        card_pool[card_id] -= 1

        # Проверка победы
        if self.player1_health <= 0:
            self.winner = self.player2.id
            return True, f"Победил {self.player2.username}! " + msg
        if self.player2_health <= 0:
            self.winner = self.player1.id
            return True, f"Победил {self.player1.username}! " + msg

        # Передача хода (если нет пропуска – просто переключаем)
        self.turn = opponent.id
        return True, msg

    def _damage_player(self, player_id, amount):
    """ Наносит урон одному из двух игроков в PvP-бою, учитывая его текущий щит"""
        if player_id == self.player1.id:
            if self.player1_shield > 0:
                blocked = min(self.player1_shield, amount)
                amount -= blocked
                self.player1_shield -= blocked
            self.player1_health -= amount
            return amount
        else:
            if self.player2_shield > 0:
                blocked = min(self.player2_shield, amount)
                amount -= blocked
                self.player2_shield -= blocked
            self.player2_health -= amount
            return amount
