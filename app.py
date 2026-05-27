from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cotc_secret_key_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'cotc_faith.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 獲取台灣本地時間
def taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

# --- 資料庫模型 (Models) ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    mission_type = db.Column(db.String(20), nullable=False) # 'daily', 'weekly', 'special'
    created_at = db.Column(db.DateTime, default=taiwan_now)

class UserMission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    mission_id = db.Column(db.Integer, db.ForeignKey('mission.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=taiwan_now)
    
    user = db.relationship('User', backref=db.backref('completed_missions', lazy=True))
    mission = db.relationship('Mission', backref=db.backref('completion_records', cascade="all, delete-orphan", lazy=True))

class CareLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=taiwan_now)
    target_user = db.relationship('User', backref=db.backref('care_logs', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 路由邏輯 (Routes) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('帳號或密碼錯誤！')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('兩次輸入的密碼不相同！')
            return render_template('register.html')
        if User.query.filter_by(username=username).first():
            flash('這個帳號已經有人使用了！')
            return render_template('register.html')
        
        new_user = User(username=username, password=password, is_admin=False)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('找不到該帳號，請檢查名字是否輸入正確！')
            return render_template('forgot_password.html')
        if new_password != confirm_password:
            flash('兩次輸入的新密碼不相同！')
            return render_template('forgot_password.html')
            
        user.password = new_password
        db.session.commit()
        flash('密碼重設成功！請使用新密碼登入。')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/')
@login_required
def index():
    daily_missions = Mission.query.filter_by(mission_type='daily').all()
    weekly_missions = Mission.query.filter_by(mission_type='weekly').all()
    special_missions = Mission.query.filter_by(mission_type='special').all()
    
    today_date = taiwan_now().date()
    completed_ids = []
    completed_records = UserMission.query.filter_by(user_id=current_user.id).all()
    
    for r in completed_records:
        if r.mission.mission_type == 'daily':
            if r.completed_at.date() == today_date:
                completed_ids.append(r.mission_id)
        else:
            completed_ids.append(r.mission_id)
    
    return render_template('index.html', user=current_user, daily=daily_missions, weekly=weekly_missions, special=special_missions, completed_ids=completed_ids)

@app.route('/complete_mission/<int:mission_id>', methods=['POST'])
@login_required
def complete_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    today_date = taiwan_now().date()
    
    if mission.mission_type == 'daily':
        already_done = UserMission.query.filter_by(user_id=current_user.id, mission_id=mission_id).all()
        for r in already_done:
            if r.completed_at.date() == today_date:
                return jsonify({'success': False, 'message': '今日已完成過此任務'})
    else:
        already_done = UserMission.query.filter_by(user_id=current_user.id, mission_id=mission_id).first()
        if already_done:
            return jsonify({'success': False, 'message': '此任務已完成過'})
    
    record = UserMission(user_id=current_user.id, mission_id=mission_id)
    db.session.add(record)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("您沒有權限進入管理後台！")
        return redirect(url_for('index'))
    
    users = User.query.filter_by(is_admin=False).all()
    missions = Mission.query.all()
    
    user_status = {}
    for u in users:
        user_status[u.id] = {}
        for m in missions:
            record = UserMission.query.filter_by(user_id=u.id, mission_id=m.id).first()
            if record:
                user_status[u.id][m.id] = record.completed_at.strftime('%m-%d %H:%M')
            else:
                user_status[u.id][m.id] = None

    return render_template('admin.html', users=users, missions=missions, user_status=user_status)

@app.route('/admin/add_mission', methods=['POST'])
@login_required
def add_mission():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    title = request.form.get('title')
    mission_type = request.form.get('mission_type')
    if title:
        new_mission = Mission(title=title, mission_type=mission_type)
        db.session.add(new_mission)
        db.session.commit()
        flash("新任務上架成功！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_mission/<int:mission_id>', methods=['POST'])
@login_required
def delete_mission(mission_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    mission = Mission.query.get_or_404(mission_id)
    db.session.delete(mission)
    db.session.commit()
    flash("任務已成功下架刪除！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_care_log', methods=['POST'])
@login_required
def add_care_log():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    target_user_id = int(request.form.get('target_user_id'))
    notes = request.form.get('notes')
    if notes:
        new_log = CareLog(target_user_id=target_user_id, notes=notes)
        db.session.add(new_log)
        db.session.commit()
        flash("關心記錄儲存成功！")
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

with app.app_context():
    db.create_all()
    admin_name = "光之城 青年牧區"
    admin = User.query.filter_by(username=admin_name).first()
    if admin:
        admin.password = "cotc2026"
        admin.is_admin = True
    else:
        admin = User(username=admin_name, password="cotc2026", is_admin=True)
        db.session.add(admin)
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)