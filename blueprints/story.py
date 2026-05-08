from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database as db
import uuid
import rewards
from battle import Battle
from story_data import STORY_CHAPTERS
from utils.helpers import get_user_by_id, get_card_by_id
from utils.cache import active_battles

story_bp = Blueprint('story', __name__)

@story_bp.route('/story')
def story():
    """ Отображение текущего сюжетного боя.
    Получение прогресса игрока, Проверка завершения игры, Загрузка данных текущей главы, Проверка, не закончилась ли текущая глава, Получение данных текущего боя, Рендеринг шаблона story.html"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    current_user = get_user_by_id(session['user_id'])   
    with db.get_db() as conn:
        prog = conn.execute('SELECT chapter, battle_index FROM story_progress WHERE user_id = ?', (session['user_id'],)).fetchone()
    chapter = prog['chapter']
    battle_idx = prog['battle_index']
    if chapter not in STORY_CHAPTERS:
        conn.execute('UPDATE users SET coins = coins + 500 WHERE id = ?', (session['user_id'],))
        conn.commit()
        return "Поздравляем! Вы прошли всю игру!"
    chapter_data = STORY_CHAPTERS[chapter]
    if battle_idx >= len(chapter_data['battles']):
        with db.get_db() as conn:
            conn.execute('UPDATE story_progress SET chapter = ?, battle_index = 0 WHERE user_id = ?', (chapter+1, session['user_id']))
            conn.commit()
        return redirect(url_for('story.story'))
    current_battle = chapter_data['battles'][battle_idx]
    current_battle['max_health'] = current_battle['health']
    return render_template('story.html', chapter=chapter, battle=current_battle, current_user=current_user, chapter_data=chapter_data)

@story_bp.route('/story/battle')
def start_battle():
    """ Сюжетный бой: создаёт экземпляр класса Battle с данными текущего сражения из STORY_CHAPTERS и сохраняет его в глобальном словаре active_battles, после чего отображает страницу боя/
    Получение прогресса игрока из story_progress.
    Загрузка данных битвы из глобального словаря STORY_CHAPTERS[chapter]['battles'][battle_idx].
    Здоровье игрока - 100
    Формирование пула карт игрока (>0, Строится словарь player_card_pool = {card_id: quantity})
    Создание экземпляра Battle с параметрами: current_user – объект игрока (с его здоровьем, элементом и т.д.), battle_data['health'] – здоровье врага, battle_data['cards'] – список карт врага, battle_data['element'] – элемент врага, player_card_pool – словарь доступных карт, player_cards_list – список карт игрока, get_card_by_id – функция для получения карты по ID, enemy_name=battle_data['enemy'] – имя врага/
    Генерация уникального battle_id (через uuid.uuid4()) и сохранение объекта битвы в глобальный словарь active_battles[battle_id].
    Сохранение battle_id в сессию пользователя (session['battle_id'] = battle_id)
    Рендеринг шаблона story_battle.html с передачей: battle – объект битвы (используется в интерфейсе для отображения здоровья, карт и т.д.), story_text – текст перед битвой из chapter_data.get('text_before', ''), chapter_name – название главы, current_user – объект пользователя"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    current_user = get_user_by_id(session['user_id'])
    with db.get_db() as conn:
        prog = conn.execute('SELECT chapter, battle_index FROM story_progress WHERE user_id = ?', (session['user_id'],)).fetchone()
    chapter = prog['chapter']
    battle_idx = prog['battle_index']
    chapter_data = STORY_CHAPTERS[chapter]
    battle_data = chapter_data['battles'][battle_idx]

    current_user.health = 100
    with db.get_db() as conn:
        rows = conn.execute('SELECT card_id, quantity FROM user_cards WHERE user_id = ? AND quantity > 0', (session['user_id'],)).fetchall()
    player_card_pool = {row['card_id']: row['quantity'] for row in rows}
    player_cards_list = [get_card_by_id(cid) for cid in player_card_pool.keys()]

    battle = Battle(current_user, battle_data['health'], battle_data['cards'], battle_data['element'],
                player_card_pool, player_cards_list, get_card_by_id, enemy_name=battle_data['enemy'])
    battle_id = str(uuid.uuid4())
    active_battles[battle_id] = battle
    session['battle_id'] = battle_id

    return render_template('story_battle.html',
                           battle=battle,
                           story_text=chapter_data.get('text_before', ''),
                           chapter_name=chapter_data['name'],
                           current_user=current_user)

@story_bp.route('/story/battle', methods=['POST'])
def battle_turn():
    """ Обрабатывает ход игрока в сюжетном бою
    Получение объекта битвы из глобального словаря active_battles по battle_id.
    Если card_id не передан – показываем сообщение «Выберите карту для атаки»
    Применение карты через battle.apply_player_card(card_id), получаем текстовый результат (result_msg)
    Проверка окончания боя: 
Победа (battle.enemy_health <= 0):
    В БД обновляются количества карт игрока (списываются использованные).
    Обновляется статистика побед и урона, начисляется 50 монет.
    Вызываются проверки квестов и достижений.
    Сохраняются координаты побеждённого боя в сессию.
    Бой удаляется из active_battles и из сессии.
    Редирект на страницу победы (story.victory).

Поражение (battle.player.health <= 0):
    Аналогично списываются карты (игрок теряет использованные карты).
    Увеличивается счётчик поражений в статистике.
    Бой удаляется, пользователь перенаправляется на карту сюжета с flash-сообщением.
Бой продолжается – рендерится шаблон боя с текущим состоянием и сообщением о результате хода"""
    if 'user_id' not in session or 'battle_id' not in session:
        return redirect(url_for('auth.login'))
    current_user = get_user_by_id(session['user_id'])
    battle_id = session['battle_id']
    battle = active_battles.get(battle_id)
    if not battle:
        return "Бой не найден. Начните заново."

    # Проверяем, есть ли card_id в запросе
    if 'card_id' not in request.form:
        return render_template('story_battle.html', battle=battle,
                               result_msg="Выберите карту для атаки.",
                               current_user=current_user)   

    card_id = int(request.form['card_id'])
    result_msg = battle.apply_player_card(card_id)

    if battle.enemy_health <= 0:
        with db.get_db() as conn:
            for cid, new_qty in battle.player_card_pool.items():
                conn.execute('UPDATE user_cards SET quantity = ? WHERE user_id = ? AND card_id = ?',
                             (new_qty, session['user_id'], cid))
            prog = conn.execute('SELECT chapter, battle_index FROM story_progress WHERE user_id = ?',
                                (session['user_id'],)).fetchone()
            chapter = prog['chapter']
            battle_idx = prog['battle_index']
            conn.execute('UPDATE user_stats SET wins = wins + 1, total_damage = total_damage + ? WHERE user_id = ?',
                         (battle.total_player_damage_dealt, session['user_id']))
            conn.execute('UPDATE users SET coins = coins + 50 WHERE id = ?', (session['user_id'],))
            conn.commit()
        rewards.check_and_award_quests(session['user_id'], 'win_battles', 1)
        rewards.check_achievements(session['user_id'], 'defeat_boss', 1)
        session['victory_chapter'] = chapter
        session['victory_battle_idx'] = battle_idx
        del active_battles[battle_id]
        session.pop('battle_id', None)
        return redirect(url_for('story.victory'))

    if battle.player.health <= 0:
        # Игрок проиграл – списываем использованные карты и показываем сообщение
        with db.get_db() as conn:
            for cid, new_qty in battle.player_card_pool.items():
                conn.execute('UPDATE user_cards SET quantity = ? WHERE user_id = ? AND card_id = ?',
                             (new_qty, session['user_id'], cid))
            conn.execute('UPDATE user_stats SET losses = losses + 1 WHERE user_id = ?', (session['user_id'],))
            conn.commit()
        del active_battles[battle_id]
        session.pop('battle_id', None)
        # Рендерим шаблон с сообщением о поражении 
        flash('Вы проиграли. Возвращайтесь в сюжет и попробуйте снова.', 'danger')
        return redirect(url_for('story.story'))   # перенаправляем в сюжет, где можно начать заново

    return render_template('story_battle.html',
                           battle=battle,
                           result_msg=result_msg,
                           current_user=current_user)   

@story_bp.route('/story/battle/quit', methods=['POST'])
def quit_battle():
    """Выход из боя"""
    if 'user_id' not in session or 'battle_id' not in session:
        return redirect(url_for('story.story'))
    battle_id = session['battle_id']
    if battle_id in active_battles:
        del active_battles[battle_id]
    session.pop('battle_id', None)
    return redirect(url_for('story.story'))   

@story_bp.route('/victory')
def victory():
    """ Отображает страницу победы
    Получение данных из сессии: victory_chapter — номер главы, в которой была одержана победа. victory_battle_idx — индекс побеждённого боя внутри главы.
    Получение данных главы из словаря STORY_CHAPTERS по номеру chapter.
    Определение текста победы"""
    current_user = get_user_by_id(session['user_id'])
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    chapter = session.get('victory_chapter')
    battle_idx = session.get('victory_battle_idx')
    if chapter is None:
        return redirect(url_for('story.story'))
    chapter_data = STORY_CHAPTERS.get(chapter)
    if not chapter_data:
        return redirect(url_for('story.story'))
    if battle_idx == len(chapter_data['battles']) - 1:
        victory_text = chapter_data.get('text_after', 'Глава пройдена!')
    else:
        victory_text = "Победа! Вы справились с врагом. Продолжайте путь."
    return render_template('victory.html', text=victory_text, current_user=current_user)

@story_bp.route('/next_battle', methods=['POST'])
def next_battle():
    """ По нажатию кнопки «Далее» на странице victory.html
    Извлечение данных о победе из сессии – victory_chapter и victory_battle_idx удаляются (через pop)
    Получение текущего прогресса из БД
    Обновление прогресса: Загружаются данные главы из STORY_CHAPTERS, 
        Если текущий бой не последний в главе – увеличивается battle_index на 1 (переход к следующему бою).
        Если текущий бой последний: Выдаётся награда за главу: карта reward_card_id в количестве reward_qty
    Прогресс переключается на следующую главу (chapter+1) с battle_index = 0.
    Очистка активного боя"""
    current_user = get_user_by_id(session['user_id'])
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    chapter = session.pop('victory_chapter', None)
    battle_idx = session.pop('victory_battle_idx', None)
    if chapter is None:
        return redirect(url_for('story.story'))
    with db.get_db() as conn:
        prog = conn.execute('SELECT chapter, battle_index FROM story_progress WHERE user_id = ?', (session['user_id'],)).fetchone()
        if prog['chapter'] == chapter and prog['battle_index'] == battle_idx:
            chapter_data = STORY_CHAPTERS[chapter]
            if battle_idx + 1 < len(chapter_data['battles']):
                conn.execute('UPDATE story_progress SET battle_index = ? WHERE user_id = ?', (battle_idx+1, session['user_id']))
            else:
                reward_card_id = chapter_data.get('reward_card')
                reward_qty = chapter_data.get('reward_quantity', 1)
                if reward_card_id:
                    conn.execute('''
                        INSERT INTO user_cards (user_id, card_id, quantity) VALUES (?, ?, ?)
                        ON CONFLICT(user_id, card_id) DO UPDATE SET quantity = quantity + ?
                    ''', (session['user_id'], reward_card_id, reward_qty, reward_qty))
                conn.execute('UPDATE story_progress SET chapter = ?, battle_index = 0 WHERE user_id = ?', (chapter+1, session['user_id']))
            conn.commit()
    if 'battle_id' in session:
        bid = session['battle_id']
        if bid in active_battles:
            del active_battles[bid]
        session.pop('battle_id', None)
    return redirect(url_for('story.story'))