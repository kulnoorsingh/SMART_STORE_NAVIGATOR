from flask import Flask, request, jsonify,render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import  Column, Integer, String, Numeric, ForeignKey, Text
from sqlalchemy.orm import relationship,aliased
import psycopg2


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_dTzlFPrmU3N5@ep-lucky-truth-a5tb0jg4-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Category(db.Model):
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True)
    category_name = Column(String, nullable=False)
    icon_url = Column(Text)

    products = relationship("Product", back_populates="category")

class Language(db.Model):
    __tablename__ = 'languages'
    language_id = Column(Integer, primary_key=True)
    language_name = Column(String, nullable=False)
    language_code = Column(String, nullable=False)

    localizations = relationship("ProductLocalization", back_populates="language")

class ProductLocalization(db.Model):
    __tablename__ = 'product_localizations'
    localized_name = Column(String, nullable=False)
    product_id = Column(Integer, ForeignKey('products.product_id'), primary_key=True)
    localized_description = Column(Text)
    language_id = Column(Integer, ForeignKey('languages.language_id'), primary_key=True)

    product = relationship("Product", back_populates="localizations")
    language = relationship("Language", back_populates="localizations")

class Product(db.Model):
    __tablename__ = 'products'
    product_id = Column(Integer, primary_key=True)
    product_name = Column(String, nullable=False)
    description = Column(Text)
    average_rating = Column(Numeric)
    qr_code_url = Column(Text)
    image_url = Column(Text)
    aisle_number = Column(Integer)
    floor_number = Column(Integer)
    tags = Column(Text)
    price = Column(Numeric, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'))
    map_coordinates = Column(String)
    stock_status = Column(String)
    location_description = Column(Text)
    row_number = Column(Integer)

    category = relationship("Category", back_populates="products")
    localizations = relationship("ProductLocalization", back_populates="product")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/navigator')
def navigator():
    categories = Category.query.all()
    languages = Language.query.all()
    return render_template('navigator.html', categories=categories, languages=languages)


@app.route('/search_products')
def search_products():
    language_code = request.args.get('language', 'en')
    category_id = request.args.get('category_id')
    search_text = request.args.get('searchText')
    page_no = int(request.args.get('page_no', 1))
    page_size = int(request.args.get('page_size', 10))
    
    offset = (page_no - 1) * page_size
    
    language = Language.query.filter_by(language_code=language_code).first()
    language_id = language.language_id if language else 1  
    
    sql_query = """
    WITH product_details AS (
        SELECT 
            p.product_id,
            p.price,

            p.tags,
            p.location_description,
            p.row_number,
            p.aisle_number,
            p.floor_number,
            p.stock_status,

            c.category_name,
            pl.localized_name,
            pl.localized_description,
            COALESCE(pl.localized_name, 
                (SELECT pl_fallback.localized_name 
                 FROM product_localizations pl_fallback 
                 WHERE pl_fallback.product_id = p.product_id 
                 AND pl_fallback.language_id = 1)
            ) AS final_localized_name,
            COALESCE(pl.localized_description, 
                (SELECT pl_fallback.localized_description 
                 FROM product_localizations pl_fallback 
                 WHERE pl_fallback.product_id = p.product_id 
                 AND pl_fallback.language_id = 1)
            ) AS final_localized_description
        FROM products p
        JOIN categories c ON p.category_id = c.category_id
        LEFT JOIN product_localizations pl ON pl.product_id = p.product_id AND pl.language_id = %s
        WHERE 1=1
    """
    
    params = [language_id]
    
    if category_id:
        sql_query += " AND c.category_id = %s"
        params.append(category_id)
        
    if search_text:
        sql_query += " AND ( p.tags ILIKE %s OR p.product_name ILIKE %s OR p.description ILIKE %s )"
        search_pattern = f'%{search_text}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    # if search_text:
    #     sql_query += " AND (pl.localized_name ILIKE %s OR (pl.localized_name IS NULL AND EXISTS (SELECT 1 FROM product_localizations pl_search WHERE pl_search.product_id = p.product_id AND pl_search.language_id = 1 AND pl_search.localized_name ILIKE %s)))"
    #     search_pattern = f'%{search_text}%'
    #     params.append(search_pattern)
    #     params.append(search_pattern)
    
    sql_query += """
    )
    SELECT * FROM product_details
    ORDER BY product_id
    LIMIT %s OFFSET %s
    """
    params.append(page_size)
    params.append(offset)
    
    count_query = """
    SELECT COUNT(*) FROM (
    """
    count_query += sql_query[:sql_query.find("LIMIT")-1]  
    count_query += ") AS count_table"
    
    conn = db.engine.raw_connection()
    cursor = conn.cursor()
    
    cursor.execute(sql_query, params)
    product_rows = cursor.fetchall()
    
    cursor.execute(count_query, params[:-2])  
    total_count = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    products = []
    
    for row in product_rows:
        product_dict = {
            "product_id": row[0],
            "price": float(row[1]) if row[1] is not None else None,
            
            "tags":row[2],
            "location_description":row[3],
            "row_number":row[4],
            "aisle_number":row[5],
            "floor_number":row[6],
            "stock_status":row[7],

            "category_name": row[8],
            "product_name": row[11],  
            "description": row[12]    
        }
        products.append(product_dict)
    
    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
    
    return jsonify({
        'page_no': page_no,
        'page_size': page_size,
        'total_pages': total_pages,
        'total_results': total_count,
        'products': products
    })



if __name__ == '__main__':
    app.run(debug=True)
