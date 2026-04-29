from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user

from models import Usuario

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = Usuario.query.filter_by(username=username, activo=True).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash(f'Bienvenido, {user.nombre}!', 'success')
            return redirect(next_page or url_for('dashboard'))
        flash('Usuario o contrasena incorrectos.', 'danger')
    return render_template('login.html')


@bp.route('/logout')
def logout():
    logout_user()
    flash('Sesion cerrada.', 'info')
    return redirect(url_for('auth.login'))
