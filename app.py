from flask import Flask, session, redirect, request, send_from_directory
import secrets
import time
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ─── Configuration ───
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ORDERS_FILE = 'orders.json'
PRODUCTS_FILE = 'products.json'
INVENTORY_FILE = 'inventory.json'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'store123'

STORE_NAME = "Nash Fashion"
STORE_EMOJI = "👗✨"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

CATEGORIES = {
    "Men's Wear": {"attributes": ["Brand", "Size", "Color", "Material", "Style"]},
    "Women's Wear": {"attributes": ["Brand", "Size", "Color", "Material", "Style"]},
    "Children's Wear": {"attributes": ["Brand", "Age Group", "Size", "Color", "Material"]},
    "Accessories": {"attributes": ["Brand", "Type", "Color", "Material"]},
    "Cosmetics": {"attributes": ["Brand", "Type", "Skin Type", "Size/Volume", "Ingredients"]},
    "Appliances": {"attributes": ["Brand", "Model", "Power", "Capacity", "Warranty"]},
    "Other": {"attributes": ["Custom Info"]}
}

ORDER_STATUSES = ["Paid", "Confirmed", "Shipped", "Delivered", "Cancelled"]
INVENTORY_STATUSES = ["Ordered", "In Transit", "Received", "Partial"]

def load_json(filename, default=[]):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def load_products():
    return load_json(PRODUCTS_FILE, [])

def save_products(products):
    save_json(PRODUCTS_FILE, products)

def load_orders():
    return load_json(ORDERS_FILE, [])

def save_orders(orders):
    save_json(ORDERS_FILE, orders)

def save_order(order):
    orders = load_orders()
    orders.append(order)
    save_orders(orders)

def load_inventory():
    return load_json(INVENTORY_FILE, [])

def save_inventory(inventory):
    save_json(INVENTORY_FILE, inventory)

def generate_sku(category, product_id):
    prefix = ''.join([word[0] for word in category.split()[:2]]).upper()
    return f"{prefix}-{product_id:04d}"

def get_stock_level(product_id):
    inventory = load_inventory()
    orders = load_orders()
    received = sum(inv['quantity_received'] for inv in inventory if inv['product_id'] == product_id and inv['status'] in ['Received', 'Partial'])
    sold = 0
    for order in orders:
        for item in order.get('items', []):
            if item.get('product_id') == product_id:
                sold += item['qty']
    return received - sold

def get_backorder(product_id):
    inventory = load_inventory()
    ordered = sum(inv['quantity_ordered'] for inv in inventory if inv['product_id'] == product_id)
    received = sum(inv['quantity_received'] for inv in inventory if inv['product_id'] == product_id)
    return ordered - received

def get_product_by_id(product_id):
    products = load_products()
    return next((p for p in products if p['id'] == product_id), None)

def get_cart():
    if 'cart' not in session:
        session['cart'] = {}
    return session['cart']

def cart_count():
    return sum(get_cart().values())

def is_admin():
    return session.get('admin_logged_in') == True

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ─── Barcode Generation (Code 128 using CSS) ───
@app.route('/admin/products/<int:product_id>/barcode')
def product_barcode(product_id):
    if not is_admin():
        return redirect('/admin')
    product = get_product_by_id(product_id)
    if not product:
        return redirect('/admin/products')
    sku = product.get('sku', 'N/A')
    return f'''
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Barcode: {sku}</title>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script>
    <style>
        @media print {{ body {{ margin: 0; }} .no-print {{ display: none; }} }}
        .barcode-box {{ border: 2px dashed #ccc; padding: 20px; text-align: center; display: inline-block; margin: 10px; }}
    </style></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
        <div class="no-print" style="margin-bottom: 20px;">
            <p style="font-size: 14px; color: #666;">Print barcodes for <strong>{product['name']}</strong></p>
            <label>Copies: <input type="number" id="copies" value="1" min="1" max="100" style="width: 60px; padding: 5px;"></label>
            <button onclick="generateBarcodes()" style="padding: 8px 16px; background: #e11d48; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px;">Generate</button>
            <button onclick="window.print()" style="padding: 8px 16px; background: #16a34a; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px;">Print</button>
            <a href="/admin/products" style="display: inline-block; margin-left: 10px; color: #666; font-size: 14px;">Back to Products</a>
        </div>
        <div id="barcode-area"></div>
        <script>
            function generateBarcodes() {{
                const copies = parseInt(document.getElementById('copies').value) || 1;
                const area = document.getElementById('barcode-area');
                area.innerHTML = '';
                for (let i = 0; i < copies; i++) {{
                    const box = document.createElement('div');
                    box.className = 'barcode-box';
                    box.innerHTML = `
                        <p style="font-weight: bold; margin: 0 0 5px 0; font-size: 14px;">{product['name']}</p>
                        <p style="font-size: 12px; color: #666; margin: 0 0 8px 0;">SKU: ${{'{sku}'}}</p>
                        <svg id="barcode${{i}}"></svg>
                        <p style="font-size: 16px; font-weight: bold; color: #e11d48; margin: 5px 0 0 0;">{product['price']:,} XAF</p>
                    `;
                    area.appendChild(box);
                    JsBarcode(`#barcode${{i}}`, `{sku}`, {{ format: 'CODE128', width: 2, height: 60, displayValue: true, fontSize: 12, margin: 5 }});
                }}
            }}
            generateBarcodes();
        </script>
    </body></html>'''


# ═══════════════════════════════════════════
#  CUSTOMER PAGES
# ═══════════════════════════════════════════

@app.route('/')
def home():
    products = load_products()
    count = cart_count()
    product_cards = ""
    if not products:
        product_cards = '<p class="text-gray-500 text-center py-12 col-span-full">No products yet. Check back soon!</p>'
    else:
        for product in products:
            attrs = product.get('attributes', {})
            key_attrs = " · ".join([f"{k}: {v}" for k, v in attrs.items() if v]) or ""
            image_html = get_product_image_html(product)
            stock = get_stock_level(product['id'])
            stock_badge = ''
            if stock <= 0:
                stock_badge = '<p class="text-red-500 text-xs font-medium mt-1">Out of Stock</p>'
            elif stock <= 5:
                stock_badge = f'<p class="text-orange-500 text-xs font-medium mt-1">Only {stock} left</p>'
            product_cards += f'''
                <div class="bg-white rounded-lg shadow p-4 hover:shadow-md transition">
                    {image_html}
                    <span class="text-xs bg-rose-100 text-rose-700 px-2 py-1 rounded">{product.get('category', 'Other')}</span>
                    <h3 class="font-semibold text-lg mt-1">{product['name']}</h3>
                    <p class="text-gray-400 text-xs font-mono">SKU: {product.get('sku', 'N/A')}</p>
                    <p class="text-gray-500 text-sm mb-1">{product['description']}</p>
                    {"<p class='text-gray-400 text-xs mb-2'>" + key_attrs + "</p>" if key_attrs else ""}
                    <p class="text-rose-600 font-bold text-lg mb-1">{product['price']:,} XAF</p>
                    {stock_badge}
                    <div class="flex gap-2 mt-3">
                        <a href="/product/{product['id']}" class="text-rose-600 border border-rose-600 px-4 py-2 rounded flex-1 text-center text-sm hover:bg-rose-50">Details</a>
                        <form method="POST" action="/add-to-cart" class="flex-1">
                            <input type="hidden" name="product_id" value="{product['id']}">
                            <button class="bg-rose-600 text-white px-2 py-2 rounded w-full text-sm hover:bg-rose-700" {'disabled' if stock <= 0 else ''}>{'Out of Stock' if stock <= 0 else 'Add to Cart'}</button>
                        </form>
                    </div>
                </div>'''
    return f'''
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{STORE_NAME} — Home</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-50">
        <header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2 hover:text-rose-600">Home</a><a href="/cart" class="text-gray-600 mx-2 hover:text-rose-600">Cart ({count})</a></nav></header>
        <main class="max-w-6xl mx-auto p-4"><div class="bg-rose-50 border border-rose-200 rounded-lg p-4 mb-6 text-center"><h2 class="text-xl font-semibold text-rose-700">Welcome to {STORE_NAME}</h2><p class="text-rose-500 text-sm">Fashion · Cosmetics · Appliances — All in One Place</p></div>
        <h2 class="text-xl font-semibold mb-4">Our Products</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">{product_cards}</div></main></body></html>'''

def get_product_image_html(product):
    image = product.get('image', '')
    if image.startswith('uploads/'):
        return f'<img src="/{image}" class="h-48 w-full object-cover rounded mb-3" alt="{product["name"]}">'
    return f'<div class="bg-gray-200 h-48 rounded mb-3 flex items-center justify-center text-gray-400 text-5xl">{image}</div>'

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return redirect('/')
    count = cart_count()
    attrs = product.get('attributes', {})
    attr_rows = "".join([f'<tr class="border-b"><td class="py-2 px-4 bg-gray-50 font-medium text-sm">{k}</td><td class="py-2 px-4 text-sm">{v}</td></tr>' for k, v in attrs.items() if v]) or '<tr><td colspan="2" class="py-2 px-4 text-sm text-gray-400">No specifications</td></tr>'
    image_html = get_product_detail_image_html(product)
    stock = get_stock_level(product_id)
    stock_info = f'<p class="text-green-600 text-sm">In Stock ({stock} available)</p>' if stock > 0 else '<p class="text-red-600 text-sm font-medium">Out of Stock</p>'
    return f'''
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{product['name']} — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-gray-50">
        <header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2 hover:text-rose-600">Home</a><a href="/cart" class="text-gray-600 mx-2 hover:text-rose-600">Cart ({count})</a></nav></header>
        <main class="max-w-4xl mx-auto p-4"><a href="/" class="text-rose-600 text-sm mb-2 inline-block">&larr; Back</a>
        <div class="bg-white rounded-lg shadow p-6"><div class="flex flex-col md:flex-row gap-6"><div class="flex-shrink-0">{image_html}</div>
        <div class="flex-1"><span class="text-xs bg-rose-100 text-rose-700 px-2 py-1 rounded">{product.get('category', 'Other')}</span>
        <h2 class="text-2xl font-bold mt-2">{product['name']}</h2><p class="text-gray-400 text-sm font-mono">SKU: {product.get('sku', 'N/A')}</p>
        <p class="text-gray-600 my-3">{product['description']}</p><p class="text-3xl font-bold text-rose-600 mb-2">{product['price']:,} XAF</p>{stock_info}
        <h3 class="font-semibold mb-2 mt-4">Specifications</h3><table class="w-full border rounded overflow-hidden mb-4"><tbody>{attr_rows}</tbody></table>
        <form method="POST" action="/add-to-cart"><input type="hidden" name="product_id" value="{product['id']}"><button class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 w-full" {'disabled' if stock <= 0 else ''}>{'Out of Stock' if stock <= 0 else 'Add to Cart'}</button></form></div></div></div></main></body></html>'''

def get_product_detail_image_html(product):
    image = product.get('image', '')
    if image.startswith('uploads/'):
        return f'<img src="/{image}" class="w-full md:w-64 h-64 object-cover rounded" alt="{product["name"]}">'
    return f'<div class="bg-gray-200 w-full md:w-64 h-64 rounded flex items-center justify-center text-7xl">{image}</div>'

@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    product_id = str(request.form.get('product_id'))
    cart = get_cart()
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart
    return redirect('/')

@app.route('/cart')
def view_cart():
    products = load_products()
    cart = get_cart()
    count = cart_count()
    cart_items = ""
    total = 0
    if not cart:
        cart_items = '<p class="text-gray-500 text-center py-8">Your cart is empty. <a href="/" class="text-rose-600 underline">Start shopping!</a></p>'
    else:
        for product in products:
            pid = str(product['id'])
            if pid in cart:
                qty = cart[pid]
                subtotal = product['price'] * qty
                total += subtotal
                image = product.get('image', '')
                img_html = f'<img src="/{image}" class="w-12 h-12 object-cover rounded">' if image.startswith('uploads/') else f'<span class="text-3xl">{image}</span>'
                cart_items += f'''
                <div class="bg-white rounded-lg shadow p-4 flex justify-between items-center mb-3"><div class="flex items-center gap-3">{img_html}<div><h3 class="font-semibold">{product['name']}</h3><p class="text-gray-400 text-xs font-mono">SKU: {product.get("sku", "N/A")}</p><p class="text-gray-500 text-sm">{product["price"]:,} XAF each</p></div></div><div class="text-right"><p class="text-sm text-gray-500">Qty: {qty}</p><p class="font-bold text-rose-600">{subtotal:,} XAF</p></div></div>'''
    checkout = '<div class="text-center mt-6"><a href="/checkout" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 inline-block">Proceed to Checkout</a></div>' if cart else ''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Cart — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({count})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Your Cart</h2>{cart_items}{"<p class='text-right text-xl font-bold mt-4'>Total: " + f"{total:,} XAF</p>" if cart else ""}{checkout}</main></body></html>'''

@app.route('/checkout')
def checkout():
    products = load_products()
    cart = get_cart()
    total = 0
    summary = ""
    for product in products:
        pid = str(product['id'])
        if pid in cart:
            qty = cart[pid]
            st = product['price'] * qty
            total += st
            summary += f'<div class="flex justify-between text-sm py-1"><span>{product["name"]} × {qty}</span><span>{st:,} XAF</span></div>'
    if not cart:
        return redirect('/cart')
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Checkout — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Checkout</h2><div class="bg-white rounded-lg shadow p-4 mb-6"><h3 class="font-semibold mb-2">Order Summary</h3>{summary}<hr class="my-2"><p class="text-right font-bold text-rose-600 text-lg">Total: {total:,} XAF</p></div><form method="POST" action="/initiate-payment" class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Your Details</h3><label class="block mb-1 text-sm text-gray-600">Full Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm text-gray-600">Phone (MoMo) *</label><input type="tel" name="phone" required class="w-full border rounded px-3 py-2 mb-3" placeholder="e.g. 237 6XX XXX XXX"><label class="block mb-1 text-sm text-gray-600">Address</label><textarea name="address" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm text-gray-600 font-semibold">Payment *</label><div class="mb-2"><label class="inline-flex items-center mr-4"><input type="radio" name="payment_method" value="mtn_momo" checked class="mr-2"> MTN MoMo</label><label class="inline-flex items-center"><input type="radio" name="payment_method" value="orange_money" class="mr-2"> Orange Money</label></div><button type="submit" class="bg-rose-600 text-white px-6 py-3 rounded-lg w-full text-lg hover:bg-rose-700 mt-3">Confirm & Pay</button></form></main></body></html>'''

@app.route('/initiate-payment', methods=['POST'])
def initiate_payment():
    products = load_products()
    cart = get_cart()
    total = 0
    order_items = []
    for product in products:
        pid = str(product['id'])
        if pid in cart:
            qty = cart[pid]
            st = product['price'] * qty
            total += st
            order_items.append({"product_id": product['id'], "sku": product.get('sku', 'N/A'), "name": product['name'], "qty": qty, "price": product['price'], "subtotal": st})
    if not cart:
        return redirect('/cart')
    ref = f"MOMO-TEST-{int(time.time())}"
    label = "MTN Mobile Money" if request.form.get('payment_method') == "mtn_momo" else "Orange Money"
    session['pending_order'] = {"ref": ref, "name": request.form.get('name'), "phone": request.form.get('phone'), "address": request.form.get('address'), "payment_method": request.form.get('payment_method'), "payment_label": label, "items": order_items, "total": total}
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Confirm Payment</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1></header><main class="max-w-lg mx-auto p-4"><div class="bg-white rounded-lg shadow p-6 text-center"><div class="text-5xl mb-4">📱</div><h2 class="text-xl font-semibold mb-2">Confirm Payment</h2><p class="text-gray-600 mb-2">Payment of <strong>{total:,} XAF</strong> to <strong>{request.form.get('phone')}</strong> via <strong>{label}</strong>.</p><div class="bg-gray-100 rounded p-4 mb-4"><p class="text-sm">Ref: {ref}</p><p class="text-xs text-gray-400">🔬 TEST MODE</p></div><form method="POST" action="/verify-payment"><label class="block mb-2 text-sm">Enter MoMo PIN (any 4 digits)</label><input type="password" name="pin" maxlength="6" required class="border rounded px-3 py-2 text-center text-lg w-32 mb-4" placeholder="****"><br><button type="submit" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700">Confirm</button></form></div></main></body></html>'''

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    pending = session.get('pending_order')
    if not pending or len(request.form.get('pin', '')) < 4:
        return redirect('/checkout')
    order = {"ref": pending['ref'], "name": pending['name'], "phone": pending['phone'], "address": pending['address'], "payment_method": pending['payment_label'], "items": pending['items'], "total": pending['total'], "status": "Paid", "date": time.strftime('%Y-%m-%d %H:%M:%S')}
    save_order(order)
    session['cart'] = {}
    ref = pending['ref']
    session.pop('pending_order', None)
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Payment Successful</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1></header><main class="max-w-lg mx-auto p-4 text-center"><div class="bg-white rounded-lg shadow p-6"><div class="text-6xl mb-4">✅</div><h2 class="text-2xl font-bold text-rose-600 mb-2">Payment Successful!</h2><p>Thank you, <strong>{order['name']}</strong>!</p><div class="bg-gray-100 rounded p-4 text-left my-4"><p class="text-sm text-gray-500">Order Ref:</p><p class="font-bold text-lg">{ref}</p><hr class="my-2"><p class="font-bold text-rose-600 text-xl">{order['total']:,} XAF</p></div><a href="/" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 inline-block">Continue Shopping</a></div></main></body></html>'''


# ═══════════════════════════════════════════
#  ADMIN
# ═══════════════════════════════════════════

@app.route('/admin')
def admin_login_page():
    if is_admin(): return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Admin Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 w-full max-w-sm"><h1 class="text-2xl font-bold text-rose-600 text-center mb-6">🔐 Admin Login</h1><form method="POST" action="/admin/login"><label class="block mb-1 text-sm">Username</label><input type="text" name="username" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Password</label><input type="password" name="password" required class="w-full border rounded px-3 py-2 mb-4"><button type="submit" class="bg-rose-600 text-white px-4 py-2 rounded w-full hover:bg-rose-700">Login</button></form></div></body></html>'''

@app.route('/admin/login', methods=['POST'])
def admin_login():
    if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Login Failed</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 w-full max-w-sm text-center"><div class="text-4xl mb-4">❌</div><h2 class="text-xl font-semibold mb-2">Login Failed</h2><a href="/admin" class="text-rose-600 underline">Try Again</a></div></body></html>'''

def admin_header():
    return f'''<header class="bg-rose-600 text-white p-4 flex justify-between items-center"><h1 class="text-xl font-bold">{STORE_EMOJI} {STORE_NAME} Admin</h1><nav><a href="/admin/dashboard" class="text-rose-100 mx-2 hover:text-white">Dashboard</a><a href="/admin/products" class="text-rose-100 mx-2 hover:text-white">Products</a><a href="/admin/inventory" class="text-rose-100 mx-2 hover:text-white">Inventory</a><a href="/admin/orders" class="text-rose-100 mx-2 hover:text-white">Orders</a><a href="/admin/logout" class="text-rose-100 mx-2 hover:text-white">Logout</a></nav></header>'''

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    products = load_products()
    inventory = load_inventory()
    revenue = sum(o['total'] for o in orders)
    low = ''.join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2 font-mono text-xs">{p.get("sku","N/A")}</td><td class="py-2"><span class="text-red-600 font-medium">{get_stock_level(p["id"])}</span></td><td class="py-2"><span class="text-orange-500">{get_backorder(p["id"])}</span></td></tr>' for p in products if get_stock_level(p['id']) <= 5]) or '<tr><td colspan="4" class="py-2 text-center text-gray-400">All well stocked</td></tr>'
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-4xl mx-auto p-4"><div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(orders)}</p><p class="text-gray-500 text-sm">Orders</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{revenue:,}</p><p class="text-gray-500 text-sm">Revenue</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(products)}</p><p class="text-gray-500 text-sm">Products</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(inventory)}</p><p class="text-gray-500 text-sm">Batc...</p></div></div><div class="bg-white rounded-lg shadow p-4"><h2 class="font-semibold mb-3">⚠️ Low Stock & Backorders</h2><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th><th class="py-2">Backorder</th></tr></thead><tbody>{low}</tbody></table></div></main></body></html>'''

# ─── Products ───
@app.route('/admin/products')
def admin_products():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    rows = ""
    for p in products:
        img = p.get('image','')
        ih = f'<img src="/{img}" class="w-10 h-10 object-cover rounded">' if img.startswith('uploads/') else f'<span class="text-2xl">{img}</span>'
        s = get_stock_level(p['id'])
        sc = 'text-green-600' if s > 5 else ('text-orange-500' if s > 0 else 'text-red-600')
        rows += f'''<tr class="border-b"><td class="py-3 px-4">{ih}</td><td class="py-3 px-4 text-xs font-mono">{p.get('sku','N/A')}</td><td class="py-3 px-4 font-medium">{p['name']}</td><td class="py-3 px-4"><span class="text-xs bg-gray-100 px-2 py-1 rounded">{p.get('category','Other')}</span></td><td class="py-3 px-4">{p['price']:,} XAF</td><td class="py-3 px-4 font-medium {sc}">{s}</td><td class="py-3 px-4"><a href="/admin/products/edit/{p['id']}" class="text-blue-600 mr-2 text-xs">Edit</a><a href="/admin/products/{p['id']}/barcode" class="text-purple-600 mr-2 text-xs">🏷️ Barcode</a><a href="/admin/products/delete/{p['id']}" class="text-red-600 text-xs" onclick="return confirm('Delete?')">Del</a></td></tr>'''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Products</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between items-center mb-4"><h2 class="text-xl font-semibold">Products ({len(products)})</h2><a href="/admin/products/add" class="bg-rose-600 text-white px-4 py-2 rounded hover:bg-rose-700">+ Add Product</a></div><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Img</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Name</th><th class="py-3 px-4">Cat</th><th class="py-3 px-4">Price</th><th class="py-3 px-4">Stock</th><th class="py-3 px-4">Actions</th></tr></thead><tbody>{rows or '<tr><td colspan="7" class="py-4 text-center text-gray-400">No products</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/products/add')
def admin_add_product_form():
    if not is_admin(): return redirect('/admin')
    cat_opt = "".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Add Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Product</h2><form method="POST" action="/admin/products/add" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Category *</label><select name="category" required class="w-full border rounded px-3 py-2 mb-3" onchange="showAttributes(this.value)"><option value="">-- Select --</option>{cat_opt}</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Price (XAF) *</label><input type="number" name="price" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Image</label><input type="file" name="image_file" accept="image/*" class="w-full border rounded px-3 py-2 mb-2"><p class="text-xs text-gray-400 mb-3">JPG, PNG, WebP. Max 5MB.</p><label class="block mb-1 text-sm">Or Emoji</label><input type="text" name="image_emoji" class="w-full border rounded px-3 py-2 mb-4" placeholder="👗"><div id="attributes-container" class="mb-4"><p class="text-sm text-gray-400">Select a category to see attributes</p></div><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Add</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main><script>const ca=''' + json.dumps({c: d['attributes'] for c, d in CATEGORIES.items()}) + ''';function showAttributes(c){const co=document.getElementById('attributes-container');const a=ca[c];if(!a){co.innerHTML='<p class="text-sm text-gray-400">Select a category first</p>';return;}let h='<h3 class="font-semibold text-sm mb-2">Attributes</h3>';a.forEach(x=>{h+=`<label class="block mb-1 text-sm">${x}</label><input type="text" name="attr_${x}" class="w-full border rounded px-3 py-2 mb-2" placeholder="${x.toLowerCase()}">`;});co.innerHTML=h;}</script></body></html>'''

@app.route('/admin/products/add', methods=['POST'])
def admin_add_product():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    nid = max([p['id'] for p in products], default=0) + 1
    cat = request.form.get('category', 'Other')
    attrs = {k: request.form.get(f'attr_{k}', '') for k in CATEGORIES.get(cat, {}).get('attributes', [])}
    img = '🖼️ Product Image'
    if 'image_file' in request.files:
        f = request.files['image_file']
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f"{nid}_{int(time.time())}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            img = f"uploads/{fn}"
    if img == '🖼️ Product Image':
        em = request.form.get('image_emoji', '').strip()
        if em: img = em
    products.append({"id": nid, "sku": generate_sku(cat, nid), "name": request.form.get('name'), "description": request.form.get('description', ''), "price": int(request.form.get('price', 0)), "image": img, "category": cat, "attributes": attrs})
    save_products(products)
    return redirect('/admin/products')

@app.route('/admin/products/edit/<int:pid>')
def admin_edit_product_form(pid):
    if not is_admin(): return redirect('/admin')
    p = get_product_by_id(pid)
    if not p: return redirect('/admin/products')
    cat_opt = "".join([f'<option value="{c}" {"selected" if c == p.get("category") else ""}>{c}</option>' for c in CATEGORIES])
    attrs_html = "".join([f'<label class="block mb-1 text-sm">{k}</label><input type="text" name="attr_{k}" value="{v}" class="w-full border rounded px-3 py-2 mb-2">' for k, v in p.get('attributes', {}).items()])
    img_html = f'<img src="/{p["image"]}" class="w-32 h-32 object-cover rounded mb-2">' if p.get('image','').startswith('uploads/') else f'<span class="text-5xl">{p["image"]}</span>'
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Edit Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Product</h2><form method="POST" action="/admin/products/edit/{pid}" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6">{img_html}<p class="text-xs text-gray-500 mb-3">SKU: <strong>{p.get('sku')}</strong></p><label class="block mb-1 text-sm">Category</label><select name="category" class="w-full border rounded px-3 py-2 mb-3" onchange="showAttributes(this.value)">{cat_opt}</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required value="{p['name']}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3">{p['description']}</textarea><label class="block mb-1 text-sm">Price *</label><input type="number" name="price" required value="{p['price']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Replace Image</label><input type="file" name="image_file" accept="image/*" class="w-full border rounded px-3 py-2 mb-2"><p class="text-xs text-gray-400 mb-3">Leave empty to keep current.</p><div id="attributes-container" class="mb-4"><h3 class="font-semibold text-sm mb-2">Attributes</h3>{attrs_html}</div><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Update</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main><script>const ca=''' + json.dumps({c: d['attributes'] for c, d in CATEGORIES.items()}) + ''';function showAttributes(c){const co=document.getElementById('attributes-container');const a=ca[c];if(!a)return;let h='<h3 class="font-semibold text-sm mb-2">Attributes</h3>';a.forEach(x=>{h+=`<label class="block mb-1 text-sm">${x}</label><input type="text" name="attr_${x}" class="w-full border rounded px-3 py-2 mb-2" placeholder="${x.toLowerCase()}">`;});co.innerHTML=h;}</script></body></html>'''

@app.route('/admin/products/edit/<int:pid>', methods=['POST'])
def admin_edit_product(pid):
    if not is_admin(): return redirect('/admin')
    products = load_products()
    for p in products:
        if p['id'] == pid:
            cat = request.form.get('category', p.get('category', 'Other'))
            p['category'] = cat
            p['attributes'] = {k: request.form.get(f'attr_{k}', '') for k in CATEGORIES.get(cat, {}).get('attributes', [])}
            p['name'] = request.form.get('name')
            p['description'] = request.form.get('description', '')
            p['price'] = int(request.form.get('price', 0))
            p['sku'] = generate_sku(cat, pid)
            if 'image_file' in request.files:
                f = request.files['image_file']
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"{pid}_{int(time.time())}_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    p['image'] = f"uploads/{fn}"
            break
    save_products(products)
    return redirect('/admin/products')

@app.route('/admin/products/delete/<int:pid>')
def admin_delete_product(pid):
    if not is_admin(): return redirect('/admin')
    products = [p for p in load_products() if p['id'] != pid]
    save_products(products)
    return redirect('/admin/products')

# ─── Inventory ───
@app.route('/admin/inventory')
def admin_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    rows = ""
    for i in inv:
        prod = get_product_by_id(i['product_id'])
        pn = prod['name'] if prod else f"#{i['product_id']}"
        sku = prod.get('sku', 'N/A') if prod else 'N/A'
        tc = i['quantity_ordered'] * i['unit_cost']
        bo = i['quantity_ordered'] - i['quantity_received']
        sc = "green" if i['status'] == "Received" else ("blue" if i['status'] == "In Transit" else "yellow")
        rows += f'''<tr class="border-b"><td class="py-3 px-4 text-xs">{i.get('date_purchased','')}</td><td class="py-3 px-4">{pn}</td><td class="py-3 px-4 text-xs font-mono">{sku}</td><td class="py-3 px-4">{i['quantity_ordered']}</td><td class="py-3 px-4">{i['quantity_received']}</td><td class="py-3 px-4"><span class="text-orange-500 font-medium">{bo}</span></td><td class="py-3 px-4">{i['unit_cost']:,}</td><td class="py-3 px-4">{tc:,}</td><td class="py-3 px-4 text-xs">{i.get('supplier_name','')}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{i['status']}</span></td><td class="py-3 px-4"><a href="/admin/inventory/edit/{i['id']}" class="text-blue-600 text-xs mr-2">Edit</a><a href="/admin/inventory/delete/{i['id']}" class="text-red-600 text-xs" onclick="return confirm('Delete?')">Del</a></td></tr>'''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between items-center mb-4"><h2 class="text-xl font-semibold">Inventory ({len(inv)})</h2><a href="/admin/inventory/add" class="bg-rose-600 text-white px-4 py-2 rounded hover:bg-rose-700">+ Add</a></div><div class="bg-white rounded-lg shadow overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Date</th><th class="py-3 px-4">Product</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Ord</th><th class="py-3 px-4">Rec</th><th class="py-3 px-4">Back</th><th class="py-3 px-4">Cost</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Supplier</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="11" class="py-4 text-center text-gray-400">No entries</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/inventory/add')
def admin_add_inventory_form():
    if not is_admin(): return redirect('/admin')
    popts = "".join([f'<option value="{p["id"]}">{p["name"]} ({p.get("sku","N/A")})</option>' for p in load_products()])
    sopts = "".join([f'<option value="{s}">{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Add Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Inventory</h2><form method="POST" action="/admin/inventory/add" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product *</label><select name="product_id" required class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option>{popts}</select><label class="block mb-1 text-sm">Qty Ordered *</label><input type="number" name="quantity_ordered" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="0" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost (XAF) *</label><input type="number" name="unit_cost" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Add</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/add', methods=['POST'])
def admin_add_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    nid = max([i['id'] for i in inv], default=0) + 1
    inv.append({"id": nid, "product_id": int(request.form.get('product_id',0)), "quantity_ordered": int(request.form.get('quantity_ordered',0)), "quantity_received": int(request.form.get('quantity_received',0)), "unit_cost": int(request.form.get('unit_cost',0)), "date_purchased": request.form.get('date_purchased',''), "date_received": request.form.get('date_received',''), "supplier_name": request.form.get('supplier_name',''), "supplier_phone": request.form.get('supplier_phone',''), "supplier_address": request.form.get('supplier_address',''), "status": request.form.get('status','Ordered')})
    save_inventory(inv)
    return redirect('/admin/inventory')

@app.route('/admin/inventory/edit/<int:iid>')
def admin_edit_inventory_form(iid):
    if not is_admin(): return redirect('/admin')
    inv = next((i for i in load_inventory() if i['id'] == iid), None)
    if not inv: return redirect('/admin/inventory')
    popts = "".join([f'<option value="{p["id"]}" {"selected" if p["id"]==inv["product_id"] else ""}>{p["name"]} ({p.get("sku","N/A")})</option>' for p in load_products()])
    sopts = "".join([f'<option value="{s}" {"selected" if s==inv["status"] else ""}>{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Edit Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Inventory</h2><form method="POST" action="/admin/inventory/edit/{iid}" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product</label><select name="product_id" class="w-full border rounded px-3 py-2 mb-3">{popts}</select><label class="block mb-1 text-sm">Qty Ordered</label><input type="number" name="quantity_ordered" value="{inv['quantity_ordered']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="{inv['quantity_received']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost</label><input type="number" name="unit_cost" value="{inv['unit_cost']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" value="{inv.get('date_purchased','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" value="{inv.get('date_received','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" value="{inv.get('supplier_name','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" value="{inv.get('supplier_phone','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3">{inv.get('supplier_address','')}</textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Update</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/edit/<int:iid>', methods=['POST'])
def admin_edit_inventory(iid):
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    for i in inv:
        if i['id'] == iid:
            i['product_id'] = int(request.form.get('product_id', i['product_id']))
            i['quantity_ordered'] = int(request.form.get('quantity_ordered', i['quantity_ordered']))
            i['quantity_received'] = int(request.form.get('quantity_received', i['quantity_received']))
            i['unit_cost'] = int(request.form.get('unit_cost', i['unit_cost']))
            i['date_purchased'] = request.form.get('date_purchased', i.get('date_purchased',''))
            i['date_received'] = request.form.get('date_received', i.get('date_received',''))
            i['supplier_name'] = request.form.get('supplier_name', i.get('supplier_name',''))
            i['supplier_phone'] = request.form.get('supplier_phone', i.get('supplier_phone',''))
            i['supplier_address'] = request.form.get('supplier_address', i.get('supplier_address',''))
            i['status'] = request.form.get('status', i['status'])
            break
    save_inventory(inv)
    return redirect('/admin/inventory')

@app.route('/admin/inventory/delete/<int:iid>')
def admin_delete_inventory(iid):
    if not is_admin(): return redirect('/admin')
    inv = [i for i in load_inventory() if i['id'] != iid]
    save_inventory(inv)
    return redirect('/admin/inventory')

# ─── Orders ───
@app.route('/admin/orders')
def admin_orders():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    rows = ""
    for idx, o in enumerate(reversed(orders)):
        ri = len(orders) - 1 - idx
        sc = "rose" if o['status']=="Paid" else ("blue" if o['status']=="Confirmed" else ("yellow" if o['status']=="Shipped" else "green"))
        rows += f'<tr class="border-b"><td class="py-3 px-4 text-xs">{o["ref"]}</td><td class="py-3 px-4">{o["name"]}</td><td class="py-3 px-4">{o["phone"]}</td><td class="py-3 px-4">{o["total"]:,}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{o["status"]}</span></td><td class="py-3 px-4 text-xs">{o["date"]}</td><td class="py-3 px-4"><a href="/admin/orders/{ri}" class="text-rose-600 text-xs">View</a></td></tr>'
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Orders</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Orders ({len(orders)})</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Ref</th><th class="py-3 px-4">Customer</th><th class="py-3 px-4">Phone</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Date</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="7" class="py-4 text-center text-gray-400">No orders</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/orders/<int:oi>')
def admin_order_detail(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if oi < 0 or oi >= len(orders): return redirect('/admin/orders')
    o = orders[oi]
    items = "".join([f'<tr class="border-b"><td class="py-2 text-xs font-mono">{i.get("sku","N/A")}</td><td class="py-2">{i["name"]}</td><td class="py-2">{i["qty"]}</td><td class="py-2">{i["price"]:,}</td><td class="py-2">{i["subtotal"]:,}</td></tr>' for i in o['items']])
    sopts = "".join([f'<option value="{s}" {"selected" if s==o["status"] else ""}>{s}</option>' for s in ORDER_STATUSES])
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Order {o["ref"]}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header()}<main class="max-w-3xl mx-auto p-4"><a href="/admin/orders" class="text-rose-600 text-sm">&larr; Back</a><div class="bg-white rounded-lg shadow p-6 my-4"><div class="flex justify-between mb-4"><div><h2 class="text-xl font-bold">{o["ref"]}</h2><p class="text-gray-500 text-sm">{o["date"]}</p></div><span class="bg-rose-100 text-rose-700 px-3 py-1 rounded text-sm">{o["status"]}</span></div><div class="grid grid-cols-2 gap-4 mb-4"><div><p class="text-xs text-gray-500">Customer</p><p class="font-medium">{o["name"]}</p></div><div><p class="text-xs text-gray-500">Phone</p><p>{o["phone"]}</p></div><div><p class="text-xs text-gray-500">Payment</p><p>{o["payment_method"]}</p></div><div><p class="text-xs text-gray-500">Address</p><p>{o.get("address","")}</p></div></div><h3 class="font-semibold mb-2">Items</h3><table class="w-full text-sm mb-4"><thead><tr class="border-b"><th class="py-2 text-left">SKU</th><th class="py-2 text-left">Item</th><th class="py-2">Qty</th><th class="py-2">Price</th><th class="py-2">Subtotal</th></tr></thead><tbody>{items}</tbody></table><p class="text-right text-xl font-bold text-rose-600">Total: {o["total"]:,} XAF</p></div><div class="bg-white rounded-lg shadow p-6"><h3 class="font-semibold mb-3">Update Status</h3><form method="POST" action="/admin/orders/{oi}/update" class="flex gap-3"><select name="status" class="border rounded px-3 py-2 flex-1">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-4 py-2 rounded">Update</button></form></div></main></body></html>'''

@app.route('/admin/orders/<int:oi>/update', methods=['POST'])
def admin_update_order(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0 <= oi < len(orders):
        orders[oi]['status'] = request.form.get('status', 'Paid')
        save_orders(orders)
    return redirect(f'/admin/orders/{oi}')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)