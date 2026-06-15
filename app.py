from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os
import random

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'cotc_secret_key_2026'

# 🌟 保持 MongoDB Atlas 雲端連線字串
MONGO_URL = os.environ.get('MONGO_URI', 'mongodb+srv://Spark:180805@cluster0.b2usebv.mongodb.net/faith_duolingo?retryWrites=true&w=majority&appName=Cluster0')
app.config["MONGO_URI"] = MONGO_URL
mongo = PyMongo(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- 🎯 台灣時間工具 ---
def get_taiwan_now():
    return datetime.utcnow() + timedelta(hours=8)

def get_current_week_str():
    return get_taiwan_now().strftime('%Y-W%W')

def get_taiwan_time_str():
    return get_taiwan_now().strftime('%m-%d %H:%M')

def get_current_month_prefix():
    return get_taiwan_now().strftime('%m-')

# --- Flask-Login 帳號配接器 ---
class MongoUser(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc['_id'])
        self.username = user_doc['username']
        self.is_admin = user_doc.get('is_admin', False)

@login_manager.user_loader
def load_user(user_id):
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    return MongoUser(user_doc) if user_doc else None

# --- 🔄 隨機抽取本週任務核心邏輯 ---
def check_and_assign_weekly_missions(user_id):
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        return
    
    current_week = get_current_week_str()
    assignment = user_doc.get('current_weekly_assignment', {})
    
    if not assignment or assignment.get('week_identifier') != current_week:
        general_pool = list(mongo.db.missions_pool.find({"mission_type": "general"}))
        chosen_general = random.sample(general_pool, min(len(general_pool), 4))
        special_pool = list(mongo.db.missions_pool.find({"mission_type": "special"}))
        
        assigned_list = []
        for m in chosen_general:
            assigned_list.append({
                "mission_id": str(m['_id']),
                "title": m['title'],
                "target_count": int(m.get('target_count', 1)),
                "current_count": 0,
                "is_completed": False,
                "mission_type": "general"
            })
        for m in special_pool:
            assigned_list.append({
                "mission_id": str(m['_id']),
                "title": m['title'],
                "target_count": int(m.get('target_count', 1)),
                "current_count": 0,
                "is_completed": False,
                "mission_type": "special"
            })
            
        new_assignment = {
            "week_identifier": current_week,
            "assigned_missions": assigned_list
        }
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"current_weekly_assignment": new_assignment}}
        )

# --- 路由邏輯 ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user_doc = mongo.db.users.find_one({"username": username})
        if user_doc and user_doc['password'] == password:
            login_user(MongoUser(user_doc))
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
        security_answer = request.form.get('security_answer').strip()
        
        if password != confirm_password:
            flash('兩次輸入的密碼不相同！')
            return render_template('register.html')
        if not security_answer:
            flash('請填寫密碼提示答案以保護帳號安全！')
            return render_template('register.html')
            
        if mongo.db.users.find_one({"username": username}):
            flash('這個名字已經有人註冊過囉！')
            return render_template('register.html')
            
        new_user = {
            "username": username,
            "password": password,
            "security_question": "最喜歡的聖經人物",
            "security_answer": security_answer,
            "is_admin": False,
            "current_weekly_assignment": {},
            "care_logs": [],
            "history_logs": [],
            "reminder_time": "12:00",
            "notebook": ""
        }
        res = mongo.db.users.insert_one(new_user)
        user_doc = mongo.db.users.find_one({"_id": res.inserted_id})
        login_user(MongoUser(user_doc))
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        security_answer = request.form.get('security_answer').strip()
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        user_doc = mongo.db.users.find_one({"username": username})
        if not user_doc:
            flash('找不到該帳號，請檢查名字是否輸入正確！')
            return render_template('forgot_password.html')
            
        if user_doc.get('security_answer') != security_answer:
            flash('安全問題答案錯誤！驗證失敗，無法重設密碼。')
            return render_template('forgot_password.html')
            
        if new_password != confirm_password:
            flash('兩次輸入的新密碼不相同！')
            return render_template('forgot_password.html')
            
        mongo.db.users.update_one({"username": username}, {"$set": {"password": new_password}})
        flash('密碼防盜重設成功！請使用新密碼登入。')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/')
@app.route('/index')
@login_required
def index():
    check_and_assign_weekly_missions(current_user.id)
    
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    assignment = user_doc.get('current_weekly_assignment', {})
    assigned_missions = assignment.get('assigned_missions', [])
    
    history_logs = user_doc.get('history_logs', [])
    month_prefix = get_current_month_prefix()
    month_completed_count = sum(1 for log in history_logs if log.get('time', '').startswith(month_prefix))
    
    reminder_time = user_doc.get('reminder_time', '12:00')
    notebook = user_doc.get('notebook', '')
    
    return render_template('index.html', 
                           user=current_user, 
                           assigned_missions=assigned_missions,
                           month_completed_count=month_completed_count,
                           reminder_time=reminder_time,
                           notebook=notebook)

@app.route('/save_reminder', methods=['POST'])
@login_required
def save_reminder():
    reminder_time = request.form.get('reminder_time')
    if reminder_time:
        mongo.db.users.update_one({"_id": ObjectId(current_user.id)}, {"$set": {"reminder_time": reminder_time}})
        flash("提醒時間設定成功！")
    return redirect(url_for('index'))

@app.route('/save_notebook', methods=['POST'])
@login_required
def save_notebook():
    notebook_content = request.form.get('notebook')
    mongo.db.users.update_one({"_id": ObjectId(current_user.id)}, {"$set": {"notebook": notebook_content}})
    flash("靈修筆記已成功儲存！")
    return redirect(url_for('index'))

@app.route('/update_progress/<string:mission_id>/<string:action>', methods=['POST'])
@login_required
def update_progress(mission_id, action):
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    assignment = user_doc.get('current_weekly_assignment', {})
    assigned_missions = assignment.get('assigned_missions', [])
    
    updated = False
    for m in assigned_missions:
        if m['mission_id'] == mission_id:
            if action == 'increase':
                if m['current_count'] < m['target_count']:
                    m['current_count'] += 1
                    if m['current_count'] == m['target_count']:
                        m['is_completed'] = True
                        mongo.db.users.update_one(
                            {"_id": ObjectId(current_user.id)},
                            {"$push": {"history_logs": {"title": m['title'], "time": get_taiwan_time_str()}}}
                        )
                    updated = True
            elif action == 'decrease':
                if m['current_count'] > 0:
                    m['current_count'] -= 1
                    m['is_completed'] = False
                    updated = True
            break
            
    if updated:
        mongo.db.users.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": {"current_weekly_assignment.assigned_missions": assigned_missions}}
        )
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': '無法更動進度'})

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("您沒有權限進入管理後台！")
        return redirect(url_for('index'))
        
    users = list(mongo.db.users.find({"is_admin": False}))
    missions_pool = list(mongo.db.missions_pool.find())
    
    for m in missions_pool:
        m['id'] = str(m['_id'])
        m['total_completed_count'] = 0
        for u in users:
            history = u.get('history_logs', [])
            m['total_completed_count'] += sum(1 for log in history if log.get('title') == m['title'])
            
    for u in users:
        u['id'] = str(u['_id'])
        u['care_logs'] = sorted(u.get('care_logs', []), key=lambda x: x.get('time', ''), reverse=True)
        u['current_list'] = u.get('current_weekly_assignment', {}).get('assigned_missions', [])
        
    return render_template('admin.html', users=users, missions_pool=missions_pool)

@app.route('/admin/add_mission_pool', methods=['POST'])
@login_required
def add_mission_pool():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    title = request.form.get('title').strip()
    target_count = int(request.form.get('target_count', 1))
    mission_type = request.form.get('mission_type')
    
    if title:
        mongo.db.missions_pool.insert_one({
            "title": title,
            "target_count": target_count,
            "mission_type": mission_type
        })
        flash("成功加入大任務庫！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_mission_pool/<string:m_id>', methods=['POST'])
@login_required
def delete_mission_pool(m_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    mongo.db.missions_pool.delete_one({"_id": ObjectId(m_id)})
    flash("已從大任務庫中徹底下架刪除！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_care_log', methods=['POST'])
@login_required
def add_care_log():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    target_user_id = request.form.get('target_user_id')
    notes = request.form.get('notes').strip()
    if notes:
        mongo.db.users.update_one(
            {"_id": ObjectId(target_user_id)},
            {"$push": {"care_logs": {"notes": notes, "time": get_taiwan_time_str()}}}
        )
        flash("關心記錄儲存成功！")
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.before_request
def init_admin():
    admin_name = "光之城 青年牧區"
    if not mongo.db.users.find_one({"username": admin_name}):
        mongo.db.users.insert_one({
            "username": admin_name,
            "password": "cotc2026",
            "is_admin": True,
            "security_question": "最喜歡的聖經人物",
            "security_answer": "耶穌"
        })

if __name__ == '__main__':
    app.run(debug=True)