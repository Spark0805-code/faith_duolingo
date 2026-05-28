from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'cotc_secret_key_2026'

# 🌟 MongoDB 雲端連線設定：已整合獨立資料庫與安全密碼，直接複製貼上即可
MONGO_URL = os.environ.get('MONGO_URI', 'mongodb+srv://Spark:180805@cluster0.b2usebv.mongodb.net/faith_duolingo?retryWrites=true&w=majority&appName=Cluster0')
app.config["MONGO_URI"] = MONGO_URL

mongo = PyMongo(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 獲取台灣本地時間字串 (YYYY-MM-DD)
def get_taiwan_date_str():
    return (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d')

def get_taiwan_time_str():
    return (datetime.utcnow() + timedelta(hours=8)).strftime('%m-%d %H:%M')

# --- Flask-Login 帳號適配器 ---
class MongoUser(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc['_id'])
        self.username = user_doc['username']
        self.password = user_doc['password']
        self.is_admin = user_doc.get('is_admin', False)

@login_manager.user_loader
def load_user(user_id):
    user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    return MongoUser(user_doc) if user_doc else None

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
        
        if password != confirm_password:
            flash('兩次輸入的密碼不相同！')
            return render_template('register.html')
        if mongo.db.users.find_one({"username": username}):
            flash('這個帳號已經有人使用了！')
            return render_template('register.html')
        
        # 🌟 極致優化：新契友自帶空紀錄陣列與空關心陣列，不開新資料表
        new_user = {
            "username": username,
            "password": password,
            "is_admin": False,
            "completed_missions": [],  # 內嵌打勾紀錄：{"mission_id": "xxx", "date": "2026-05-28", "time": "05-28 11:00"}
            "care_logs": []            # 內嵌關心筆記：{"notes": "xxx", "time": "2026-05-28 11:00"}
        }
        result = mongo.db.users.insert_one(new_user)
        login_user(MongoUser(mongo.db.users.find_one({"_id": result.inserted_id})))
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        user_doc = mongo.db.users.find_one({"username": username})
        if not user_doc:
            flash('找不到該帳號，請檢查名字是否輸入正確！')
            return render_template('forgot_password.html')
        if new_password != confirm_password:
            flash('兩次輸入的新密碼不相同！')
            return render_template('forgot_password.html')
            
        mongo.db.users.update_one({"username": username}, {"$set": {"password": new_password}})
        flash('密碼重設成功！請使用新密碼登入。')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/')
@app.route('/index')
@login_required
def index():
    # 撈出三大類型任務
    daily_missions = list(mongo.db.missions.find({"mission_type": "daily"}))
    weekly_missions = list(mongo.db.missions.find({"mission_type": "weekly"}))
    special_missions = list(mongo.db.missions.find({"mission_type": "special"}))
    
    # 轉換成原本前端需要的 string id 格式
    for m in daily_missions + weekly_missions + special_missions:
        m['id'] = str(m['_id'])
        
    today_str = get_taiwan_date_str()
    completed_ids = []
    
    # 🌟 撈出當前契友自己 Document 內的打勾紀錄，進行今日過濾
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    for record in user_doc.get('completed_missions', []):
        m_id = record['mission_id']
        m_doc = mongo.db.missions.find_one({"_id": ObjectId(m_id)})
        if m_doc:
            if m_doc['mission_type'] == 'daily':
                if record['date'] == today_str:
                    completed_ids.append(m_id)
            else:
                completed_ids.append(m_id)
                
    return render_template('index.html', user=current_user, daily=daily_missions, weekly=weekly_missions, special=special_missions, completed_ids=completed_ids)

@app.route('/complete_mission/<string:mission_id>', methods=['POST'])
@login_required
def complete_mission(mission_id):
    today_str = get_taiwan_date_str()
    time_str = get_taiwan_time_str()
    
    user_doc = mongo.db.users.find_one({"_id": ObjectId(current_user.id)})
    m_doc = mongo.db.missions.find_one({"_id": ObjectId(mission_id)})
    if not m_doc:
        return jsonify({'success': False, 'message': '找不到此任務'})
        
    # 驗證重複打勾
    history = user_doc.get('completed_missions', [])
    if m_doc['mission_type'] == 'daily':
        if any(h['mission_id'] == mission_id and h['date'] == today_str for h in history):
            return jsonify({'success': False, 'message': '今日已完成過此任務'})
    else:
        if any(h['mission_id'] == mission_id for h in history):
            return jsonify({'success': False, 'message': '此任務已完成過'})
            
    # 🌟 使用 $push 直接將新紀錄壓進 User 文件內的陣列，效率極高、不增新文件
    new_record = {"mission_id": mission_id, "date": today_str, "time": time_str}
    mongo.db.users.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$push": {"completed_missions": new_record}}
    )
    return jsonify({'success': True})

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("您沒有權限進入管理後台！")
        return redirect(url_for('index'))
        
    users = list(mongo.db.users.find({"is_admin": False}))
    missions = list(mongo.db.missions.find({}))
    
    for u in users:
        u['id'] = str(u['_id'])
        # 為了迎合原本前端的歷史顯示格式，對歷史紀錄做倒序排列
        u['care_logs'] = sorted(u.get('care_logs', []), key=lambda x: x.get('time', ''), reverse=True)
        
    for m in missions:
        m['id'] = str(m['_id'])
        
    # 建立原本前端對應的狀態字典
    user_status = {}
    for u in users:
        user_status[u['id']] = {}
        history = u.get('completed_missions', [])
        for m in missions:
            match = next((h for h in history if h['mission_id'] == m['id']), None)
            user_status[u['id']][m['id']] = match['time'] if match else None

    return render_template('admin.html', users=users, missions=missions, user_status=user_status)

@app.route('/admin/add_mission', methods=['POST'])
@login_required
def add_mission():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    title = request.form.get('title')
    mission_type = request.form.get('mission_type')
    if title:
        mongo.db.missions.insert_one({"title": title, "mission_type": mission_type})
        flash("新任務上架成功！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_mission/<string:mission_id>', methods=['POST'])
@login_required
def delete_mission(mission_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    mongo.db.missions.delete_one({"_id": ObjectId(mission_id)})
    flash("任務已成功下架刪除！")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_care_log', methods=['POST'])
@login_required
def add_care_log():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    target_user_id = request.form.get('target_user_id')
    notes = request.form.get('notes')
    if notes:
        log_entry = {"notes": notes, "time": (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')}
        # 🌟 關心紀錄也一樣，直接 $push 進使用者的 Document 陣列中
        mongo.db.users.update_one(
            {"_id": ObjectId(target_user_id)},
            {"$push": {"care_logs": log_entry}}
        )
        flash("關心記錄儲存成功！")
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- 專門給雲端環境的強制初始化（每次重開會自動檢査管理員是否存在） ---
with app.app_context():
    try:
        admin_name = "光之城 青年牧區"
        admin = mongo.db.users.find_one({"username": admin_name})
        if admin:
            mongo.db.users.update_one({"username": admin_name}, {"$set": {"password": "cotc2026", "is_admin": True}})
        else:
            mongo.db.users.insert_one({
                "username": admin_name,
                "password": "cotc2026",
                "is_admin": True,
                "completed_missions": [],
                "care_logs": []
            })
    except Exception as e:
        print("資料庫初始化中...", e)

if __name__ == '__main__':
    app.run(debug=True)