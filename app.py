import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import hashlib
from functools import wraps # --- 추가된 부분 ---

# --- 기본 설정 ---
app = Flask(__name__)

# 이미지 업로드 폴더 설정
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///board.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# 세션 기능을 사용하려면 반드시 secret_key가 필요합니다.
app.secret_key = 'a_very_strong_and_secret_key_12345' # 실제 운영 시에는 더 복잡하게 변경하세요.

db = SQLAlchemy(app)

# --- 데이터베이스 모델 ---
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_name = db.Column(db.String(100), nullable=False)
    link_url = db.Column(db.String(500), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)
    memo = db.Column(db.Text, nullable=True)
    author = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<Post {self.actor_name}>'

# 모델 정의가 모두 끝난 후 테이블 생성
with app.app_context():
    db.create_all()

# --- 로그인 데코레이터 (추가된 부분) ---
# 로그인이 필요한 페이지에 붙여주는 기능
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 헬퍼 함수 ---
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- 라우팅 ---
@app.route('/')
@login_required # --- 추가된 부분: 이제 이 페이지는 로그인이 필요합니다. ---
def index():
    posts = Post.query.order_by(Post.id.desc()).all()
    return render_template('index.html', posts=posts)

# --- 로그인 라우트 (새로 추가된 부분) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'micyu':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('비밀번호가 올바르지 않습니다.')
    return render_template('login.html')

# --- 로그아웃 라우트 (새로 추가된 부분) ---
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required # --- 추가된 부분: 글쓰기도 로그인이 필요합니다. ---
def add_post():
    # ... (기존 add_post 내용은 변경 없음) ...
    actor_name = request.form.get('actor_name')
    link_url = request.form.get('link_url')
    memo = request.form.get('memo')
    author = request.form.get('author')
    password = request.form.get('password')
    image = request.files.get('image')

    if not all([actor_name, author, password]):
        flash('배우명, 작성자, 비밀번호는 필수 항목입니다.')
        return redirect(url_for('index'))

    password_hash = hash_password(password)
    image_filename = None
    if image and image.filename != '':
        image_filename = secure_filename(image.filename)
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

    new_post = Post(
        actor_name=actor_name,
        link_url=link_url,
        image_filename=image_filename,
        memo=memo,
        author=author,
        password_hash=password_hash
    )
    db.session.add(new_post)
    db.session.commit()
    
    flash('게시글이 성공적으로 작성되었습니다.')
    return redirect(url_for('index'))

@app.route('/edit/<int:post_id>', methods=['POST'])
@login_required # --- 추가된 부분: 수정도 로그인이 필요합니다. ---
def edit_post(post_id):
    # ... (기존 edit_post 내용은 변경 없음) ...
    post = Post.query.get_or_404(post_id)
    submitted_password = request.form.get('password')

    if post.password_hash != hash_password(submitted_password):
        flash('비밀번호가 일치하지 않습니다.')
        return redirect(url_for('index'))

    post.actor_name = request.form.get('actor_name')
    post.link_url = request.form.get('link_url')
    post.memo = request.form.get('memo')
    post.author = request.form.get('author')
    
    image = request.files.get('image')
    if image and image.filename != '':
        if post.image_filename:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename))
            except OSError:
                pass
        
        image_filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
        post.image_filename = image_filename

    db.session.commit()
    flash('게시글이 성공적으로 수정되었습니다.')
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
@login_required # --- 추가된 부분: 삭제도 로그인이 필요합니다. ---
def delete_post():
    # ... (기존 delete_post 내용은 변경 없음) ...
    post_id = request.form.get('post_id')
    password = request.form.get('password')
    post = Post.query.get_or_404(post_id)

    if post.password_hash == hash_password(password):
        if post.image_filename:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename))
            except OSError:
                 pass
        
        db.session.delete(post)
        db.session.commit()
        flash('게시글이 삭제되었습니다.')
    else:
        flash('비밀번호가 일치하지 않습니다.')
    
    return redirect(url_for('index'))

# --- 애플리케이션 실행 (로컬 테스트용) ---
if __name__ == '__main__':
    app.run(debug=True)
