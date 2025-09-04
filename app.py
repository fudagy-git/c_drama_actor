import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import hashlib
from functools import wraps
# --- [1/5] Cloudinary 라이브러리 임포트 ---
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- 기본 설정 ---
app = Flask(__name__)

# 로컬 업로드 폴더 설정은 이제 비상용으로만 사용되거나 필요 없어집니다.
# 하지만 코드는 그대로 두어도 괜찮습니다.
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///board.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_strong_and_secret_key_12345'

# --- [2/5] Cloudinary 설정 추가 ---
# Render.com의 환경 변수에서 CLOUDINARY_URL을 읽어와 자동으로 설정합니다.
cloudinary.config(secure=True)

db = SQLAlchemy(app)

# --- 데이터베이스 모델 ---
# image_filename 필드에 이제는 파일명이 아닌 전체 이미지 URL이 저장됩니다.
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_name = db.Column(db.String(100), nullable=False)
    link_url = db.Column(db.String(500), nullable=True)
    image_filename = db.Column(db.String(500), nullable=True) # URL을 저장하기 위해 길이를 늘림
    memo = db.Column(db.Text, nullable=True)
    author = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # Cloudinary에서 이미지를 삭제할 때 필요한 public_id를 저장할 필드 추가
    image_public_id = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<Post {self.actor_name}>'

with app.app_context():
    db.create_all()

# --- 기존 resize_image 함수는 이제 필요 없으므로 삭제합니다. ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- 라우팅 (index, login, logout은 변경 없음) ---
@app.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.id.desc()).paginate(page=page, per_page=10)
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == 'micyu':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('비밀번호가 올바르지 않습니다.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required
def add_post():
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
    image_url = None
    image_public_id = None

    # --- [3/5] 이미지 저장 로직을 Cloudinary 업로드로 변경 ---
    if image and image.filename != '':
        try:
            # Cloudinary에 이미지 업로드 및 리사이징 요청
            upload_result = cloudinary.uploader.upload(
                image,
                folder="actor_board", # Cloudinary 내부에 생성될 폴더 이름
                transformation=[{'width': 800, 'crop': "limit"}] # 가로 800 기준으로 리사이징
            )
            image_url = upload_result.get('secure_url')
            image_public_id = upload_result.get('public_id')
        except Exception as e:
            flash(f"이미지 업로드에 실패했습니다: {e}")
            return redirect(url_for('index'))

    new_post = Post(
        actor_name=actor_name,
        link_url=link_url,
        image_filename=image_url, # 파일명 대신 URL 저장
        image_public_id=image_public_id, # 삭제를 위한 public_id 저장
        memo=memo,
        author=author,
        password_hash=password_hash
    )
    db.session.add(new_post)
    db.session.commit()
    
    flash('게시글이 성공적으로 작성되었습니다.')
    return redirect(url_for('index'))

@app.route('/edit/<int:post_id>', methods=['POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    # ... (상단 로직은 변경 없음) ...
    submitted_password = request.form.get('password')
    if post.password_hash != hash_password(submitted_password):
        flash('비밀번호가 일치하지 않습니다.')
        return redirect(url_for('index'))

    post.actor_name = request.form.get('actor_name')
    post.link_url = request.form.get('link_url')
    post.memo = request.form.get('memo')
    post.author = request.form.get('author')
    
    image = request.files.get('image')
    # --- [4/5] 수정 시 이미지 처리 로직 변경 ---
    if image and image.filename != '':
        # 1. 기존 이미지가 Cloudinary에 있다면 삭제
        if post.image_public_id:
            try:
                cloudinary.uploader.destroy(post.image_public_id)
            except Exception as e:
                flash(f"기존 이미지 삭제에 실패했습니다: {e}")
        
        # 2. 새 이미지를 Cloudinary에 업로드
        try:
            upload_result = cloudinary.uploader.upload(
                image,
                folder="actor_board",
                transformation=[{'width': 800, 'crop': "limit"}]
            )
            post.image_filename = upload_result.get('secure_url')
            post.image_public_id = upload_result.get('public_id')
        except Exception as e:
            flash(f"새 이미지 업로드에 실패했습니다: {e}")

    db.session.commit()
    flash('게시글이 성공적으로 수정되었습니다.')
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
@login_required
def delete_post():
    post_id = request.form.get('post_id')
    password = request.form.get('password')
    post = Post.query.get_or_404(post_id)

    if post.password_hash == hash_password(password):
        # --- [5/5] 게시글 삭제 시 Cloudinary 이미지도 함께 삭제 ---
        if post.image_public_id:
            try:
                cloudinary.uploader.destroy(post.image_public_id)
            except Exception as e:
                flash(f"클라우드 이미지 삭제에 실패했습니다: {e}")
        
        db.session.delete(post)
        db.session.commit()
        flash('게시글이 삭제되었습니다.')
    else:
        flash('비밀번호가 일치하지 않습니다.')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
