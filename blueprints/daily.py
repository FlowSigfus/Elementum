from flask import Blueprint, request, redirect, url_for, session, flash
import rewards
from decorators import login_required

daily_bp = Blueprint('daily', __name__)

@daily_bp.route('/claim_case')
@login_required
def claim_case():
    """ Эндпоинт для получения ежедневного кейса, с поддержкой принудительной выдачи через параметр запроса"""
    force = request.args.get('force', '') == '1'
    _, _, msg = rewards.claim_daily_case(session['user_id'], manual_override=force)
    flash(msg)
    return redirect(url_for('main.dashboard'))

@daily_bp.route('/daily_bonus')
@login_required
def daily_bonus():
    """ Эндпоинт для ежедневного бонуса"""
    success, msg = rewards.claim_daily_bonus(session['user_id'])
    flash(msg)
    return redirect(url_for('main.dashboard'))