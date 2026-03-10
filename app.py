from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import sqlite3, os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production!

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def get_db_connection():
    conn = sqlite3.connect('recipes.db')
    conn.row_factory = sqlite3.Row
    return conn


# -------------------- AUTH DECORATOR --------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash("You must log in first!", "danger")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# -------------------- ROUTES --------------------
@app.route('/')
def home():
    return render_template('index.html', logged_in=bool(session.get('user_id')))


@app.route('/browse')
def browse():
    category = request.args.get("category", '').strip()
    cuisine = request.args.get("cuisine", '').strip()
    search = request.args.get("search", '').strip()
    conn = get_db_connection()

    query = "SELECT * FROM recipes WHERE 1=1"
    params = []

    if category:
        query += " AND LOWER(category) = ?"
        params.append(category.lower())

    if cuisine:
        query += " AND LOWER(cuisine) = ?"
        params.append(cuisine.lower())

    if search:
        query += " AND (LOWER(title) LIKE ? OR LOWER(cuisine) LIKE ? OR LOWER(category) LIKE ?)"
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%", f"%{search.lower()}%"])

    recipes = conn.execute(query, params).fetchall()

    # find which recipes are favorited by this user
    user_favorites = set()
    if session.get("user_id"):
        favs = conn.execute("SELECT recipe_id FROM favorites WHERE user_id = ?", (session['user_id'],)).fetchall()
        user_favorites = {f['recipe_id'] for f in favs}

    conn.close()
    return render_template('browse.html', recipes=recipes,
                           selected_category=category,
                           selected_cuisine=cuisine,
                           search=search, page_title="Browse Recipes",
                           logged_in=bool(session.get('user_id')),
                           user_favorites=user_favorites)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        title = request.form['title']
        cuisine = request.form['cuisine']
        category = request.form['category']
        ingredients = request.form['ingredients']
        steps = request.form['steps']

        file = request.files['image']
        image_filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO recipes (title, cuisine, category, image_filename, ingredients, steps)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, cuisine, category, image_filename, ingredients, steps))
        conn.commit()
        conn.close()
        return redirect(url_for('browse'))

    return render_template('add.html', edit=False, logged_in=bool(session.get('user_id')))


@app.route('/recipe/<int:recipe_id>')
@login_required
def recipe_detail(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    conn.close()
    if recipe is None:
        return "Recipe not found", 404
    return render_template('recipe.html', recipe=recipe, logged_in=bool(session.get('user_id')))


@app.route('/edit/<int:recipe_id>', methods=['GET', 'POST'])
@login_required
def edit(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()

    if request.method == 'POST':
        title = request.form['title']
        cuisine = request.form['cuisine']
        category = request.form['category']
        ingredients = request.form['ingredients']
        steps = request.form['steps']

        file = request.files['image']
        image_filename = recipe['image_filename']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename

        conn.execute('''
            UPDATE recipes
            SET title=?, cuisine=?, category=?, image_filename=?, ingredients=?, steps=?
            WHERE id=?
        ''', (title, cuisine, category, image_filename, ingredients, steps, recipe_id))
        conn.commit()
        conn.close()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    conn.close()
    return render_template('add.html', recipe=recipe, edit=True, logged_in=bool(session.get('user_id')))


@app.route('/delete/<int:recipe_id>')
@login_required
def delete(recipe_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()
    flash("Recipe deleted successfully!", "success")
    return redirect(url_for('browse'))


@app.route('/toggle_favorite/<int:recipe_id>', methods=['POST'])
def toggle_favorite(recipe_id):
    if not session.get('user_id'):
        # Store pending favorite in session if not logged in
        session['pending_favorite'] = recipe_id
        return jsonify({'redirect': url_for('login', next=request.referrer)})

    conn = get_db_connection()
    fav = conn.execute("SELECT * FROM favorites WHERE user_id=? AND recipe_id=?",
                       (session['user_id'], recipe_id)).fetchone()
    if fav:
        conn.execute("DELETE FROM favorites WHERE user_id=? AND recipe_id=?",
                     (session['user_id'], recipe_id))
        conn.commit()
        conn.close()
        return jsonify({'favorited': False})
    else:
        conn.execute("INSERT INTO favorites (user_id, recipe_id) VALUES (?, ?)",
                     (session['user_id'], recipe_id))
        conn.commit()
        conn.close()
        return jsonify({'favorited': True})


@app.route('/favorites')
@login_required
def favorites():
    user_id = session['user_id']
    search = request.args.get('search', '').strip()
    conn = get_db_connection()
    if search:
        recipes = conn.execute(
            """SELECT r.* FROM recipes r
               JOIN favorites f ON r.id = f.recipe_id
               WHERE f.user_id = ? AND (r.title LIKE ? OR r.cuisine LIKE ? OR r.category LIKE ?)""",
            (user_id, f'%{search}%', f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        recipes = conn.execute(
            """SELECT r.* FROM recipes r
               JOIN favorites f ON r.id = f.recipe_id
               WHERE f.user_id = ?""", (user_id,)
        ).fetchall()
    favs = conn.execute("SELECT recipe_id FROM favorites WHERE user_id=?", (user_id,)).fetchall()
    user_favorites = {f['recipe_id'] for f in favs}
    conn.close()
    return render_template('browse.html', recipes=recipes, page_title="Favorites",
                           search=search, logged_in=True, user_favorites=user_favorites)


# -------------------- USER AUTH --------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (email, password) VALUES (?, ?)",
                         (email, hashed_pw))
            conn.commit()
            flash("Signup successful! Please login.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Email already exists!", "danger")
        finally:
            conn.close()
    return render_template('signup.html', logged_in=bool(session.get('user_id')))


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['email'] = user['email']
            flash("Logged in successfully!", "success")

            # ✅ Apply pending favorite
            pending_fav = session.pop('pending_favorite', None)
            if pending_fav:
                conn = get_db_connection()
                conn.execute("INSERT OR IGNORE INTO favorites (user_id, recipe_id) VALUES (?, ?)",
                             (user['id'], pending_fav))
                conn.commit()
                conn.close()

            return redirect(next_page or url_for('home'))
        else:
            flash("Invalid Email or password!", "danger")

    return render_template("login.html", next=next_page)


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))


# -------------------- DB INIT --------------------
def init_db():
    conn = sqlite3.connect('recipes.db')
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                category TEXT NOT NULL,
                image_filename TEXT,
                ingredients TEXT NOT NULL,
                steps TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                recipe_id INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(recipe_id) REFERENCES recipes(id),
                UNIQUE(user_id, recipe_id)
            )
        ''')
        conn.commit()
        print("✅ Database ready")
    except Exception as e:
        print(f"⚠️ Error setting up database: {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
