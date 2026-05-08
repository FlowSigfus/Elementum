class Card:
    def __init__(self, id, name, action_type, element, base_value, mana_cost, description, rarity=''):
        self.id = id
        self.name = name
        self.action_type = action_type
        self.element = element
        self.base_value = base_value
        self.mana_cost = mana_cost
        self.desc = description
        self.rarity = rarity

    def use(self, user, battle):
        # user – либо объект User (игрок), либо фиктивный объект врага
        if self.action_type == 'attack':
            # Определяем защитника и его стихию
            if user == battle.player:
                defender = battle.enemy
                defender_element = battle.enemy_element
                # множитель от стихии игрока и его прокачки/проклятия
                player_mult = battle.player.get_element_multiplier()
                element_mult = get_damage_multiplier(self.element, defender_element)
                final_damage = int(self.base_value * element_mult * player_mult)
                battle.damage_enemy(final_damage)
                return f"{user.username} наносит {final_damage} урона (стихия {self.element} против {defender_element}, множ. {element_mult}, усиление {player_mult})!"
            else:
                # враг атакует игрока
                defender = battle.player
                defender_element = battle.player.element
                element_mult = get_damage_multiplier(self.element, defender_element)
                final_damage = int(self.base_value * element_mult)
                battle.damage_player(final_damage)
                return f"{user.username} наносит {final_damage} урона!"
        elif self.action_type == 'defense':
            if user == battle.player:
                battle.shield_player(self.base_value)
            else:
                battle.shield_enemy(self.base_value)
            return f"{user.username} получает щит {self.base_value}!"
        elif self.action_type == 'heal':
            if user == battle.player:
                battle.heal_player(self.base_value)
            else:
                battle.heal_enemy(self.base_value)
            return f"{user.username} восстанавливает {self.base_value} здоровья!"
        elif self.action_type == 'skip':
            if user == battle.player:
                battle.skip_enemy()
                battle.heal_player(10)
            else:
                battle.skip_player()
                battle.heal_enemy(10)
            return f"{user.username} заставляет противника пропустить ход и восстанавливает 10 здоровья!"
        else:
            return "Ничего не произошло"

# Функция множителя стихий
ELEMENT_ADVANTAGE = {
    ('water', 'fire'): 1.5,
    ('wind', 'fire'): 1.5,
    ('fire', 'earth'): 1.5,
    ('earth', 'water'): 1.5,
    ('light', 'dark'): 1.5,
    ('dark', 'light'): 1.5,
}

def get_damage_multiplier(attacker_element, defender_element):
    if attacker_element == defender_element:
        return 1.0
    # свет/тьма против остальных – 1.0
    if attacker_element in ('light', 'dark') and defender_element not in ('dark', 'light'):
        return 1.0
    return ELEMENT_ADVANTAGE.get((attacker_element, defender_element), 1.0)

    """Пример полиморфизма и рекурсии"""
class ChainLightning(Card):
    def use(self, user, battle):
        def recursive_strike(damage, target_health):
            if target_health <= 0 or damage <= 0:
                return 0
            battle.damage_enemy(damage)
            if battle.enemy_health <= 0:
                return damage
            return damage + recursive_strike(damage - 5, battle.enemy_health)
        total = recursive_strike(self.base_value, battle.enemy_health)
        return f"Молния бьёт по всем, нанося {total} урона!"
