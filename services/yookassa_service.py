# services/yookassa_service.py
import uuid
from yookassa import Configuration, Payment
import logging

class YookassaService:
    def __init__(self, shop_id, secret_key):
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key

    def create_payment(self, order_id, amount_cents, description, email, return_url, receipt_items=None):
        """Создаёт платёж в ЮKassa и возвращает confirmation_url"""
        idempotence_key = str(uuid.uuid4())
        payment_data = {
            'amount': {
                'value': f'{amount_cents / 100:.2f}',
                'currency': 'RUB'
            },
            'confirmation': {
                'type': 'redirect',
                'return_url': return_url
            },
            'capture': True,
            'description': description,
            'metadata': {
                'order_id': order_id
            },
            'receipt': {
                'customer': {'email': email},
                'items': receipt_items or []
            }
        }
        payment = Payment.create(payment_data, idempotence_key)
        return {
            'id': payment.id,
            'status': payment.status,
            'confirmation_url': payment.confirmation.confirmation_url
        }

    def get_payment(self, payment_id):
        return Payment.find_one(payment_id)