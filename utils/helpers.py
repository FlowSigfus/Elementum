import os
from werkzeug.utils import secure_filename
import database as db
from models.card import Card, ChainLightning
from utils.cache import CARDS_CACHE
from models.user import User

def get_card_by_id(card_id):
    if card_id in CARDS_CACHE:
        return CARDS_CACHE[card_id]
    with db.get_db() as conn:
        row = conn.execute('SELECT * FROM cards WHERE id = ?', (card_id,)).fetchone()
    if not row:
        return None
    if card_id == 7:
        card = ChainLightning(row['id'], row['name'], row['action_type'], row['element'],
                              row['base_value'], row['mana_cost'], row['description'], row['rarity'])
    else:
        card = Card(row['id'], row['name'], row['action_type'], row['element'],
                    row['base_value'], row['mana_cost'], row['description'], row['rarity'])
    CARDS_CACHE[card_id] = card
    return card

def get_user_by_id(user_id):
    with db.get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        return None
    row_dict = dict(row)
    allow_duels = row_dict.get('allow_duels', 1)
    user = User(
        row_dict['id'], row_dict['username'], row_dict['element'], row_dict['last_element_change'],
        bool(row_dict['trained']), row_dict['curse_end'], row_dict['avatar'], row_dict['last_nickname_change'],
        allow_duels
    )
    with db.get_db() as conn:
        rows = conn.execute('SELECT c.*, uc.quantity, uc.level FROM user_cards uc JOIN cards c ON uc.card_id = c.id WHERE uc.user_id = ?', (user_id,)).fetchall()
    for row in rows:
        card = Card(row['id'], row['name'], row['action_type'], row['element'],
                    row['base_value'], row['mana_cost'], row['description'], row['rarity'])
        user.add_card(card)
    return user

def get_card_by_nfc_hash(nfc_hash):
    with db.get_db() as conn:
        row = conn.execute('SELECT * FROM cards WHERE nfc_hash = ?', (nfc_hash,)).fetchone()
    if row:
        return get_card_by_id(row['id'])
    return None

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS