from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3


app = Flask(__name__)
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect('recipes.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return render_template('index.html')
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
    conn.close()
    return render_template('browse.html', recipes=recipes, selected_category=category,
        selected_cuisine=cuisine,search=search, page_title="Browse Recipes")

@app.route('/add', methods=['GET', 'POST'])
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

    return render_template('add.html',edit=False)

@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()
    conn.close()
    if recipe is None:
        return "Recipe not found", 404
    return render_template('recipe.html', recipe=recipe)

@app.route('/edit/<int:recipe_id>', methods=['GET', 'POST'])
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
        image_filename = recipe['image_filename']  # keep old one by default
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
    return render_template('add.html', recipe=recipe, edit=True)

@app.route('/delete/<int:recipe_id>')
def delete(recipe_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
    conn.commit()
    conn.close()
    flash("Recipe deleted successfully!", "success")
    return redirect(url_for('browse'))
@app.route('/toggle_favorite/<int:recipe_id>', methods=['POST'])
def toggle_favorite(recipe_id):
    conn = get_db_connection()
    recipe = conn.execute('SELECT is_favorite FROM recipes WHERE id = ?', (recipe_id,)).fetchone()

    if recipe:
        new_status = 0 if recipe['is_favorite'] else 1
        conn.execute('UPDATE recipes SET is_favorite = ? WHERE id = ?', (new_status, recipe_id))
        conn.commit()
    conn.close()
    #return redirect(url_for('browse')) 
    return jsonify(success=True, new_status=new_status)
@app.route('/favorites')
def favorites():
    search = request.args.get('search', '').strip()
    conn = get_db_connection()
    if search:
        recipes = conn.execute(
            "SELECT * FROM recipes WHERE is_favorite = 1 AND (title LIKE ? OR cuisine LIKE ? OR category LIKE ?)",
            (f'%{search}%', f'%{search}%', f'%{search}%')
        ).fetchall()
    else:
        recipes = conn.execute('SELECT * FROM recipes WHERE is_favorite = 1').fetchall()
    conn.close()
    return render_template('browse.html', recipes=recipes, page_title="Favorites",search=search)

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
                steps TEXT NOT NULL,
                is_favorite INTEGER DEFAULT 0
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

