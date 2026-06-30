from flask import Flask, session, redirect, request, send_from_directory
import secrets
import time
import json
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ORDERS_FILE = 'orders.json'
PRODUCTS_FILE = 'products.json'
INVENTORY_FILE = 'inventory.json'
DISPATCHERS_FILE = 'dispatchers.json'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'store123'
STORE_NAME = "Nash Fashion"
STORE_EMOJI = "👗✨"
MAX_IMAGES = 5

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DELIVERY_ZONES = {"Douala": 2000, "Yaounde": 3000, "Buea": 2500, "Bamenda": 3000, "Other": 5000}
FREE_DELIVERY_THRESHOLD = 50000
SPECIAL_TAGS = ["Deal", "Clearance", "New Arrival", "Best Seller", "Limited Edition"]
STORE_WHATSAPP = "237677063461"
STORE_LOGO_TEXT = "<img src='/uploads/Nash_Fashion_Premium_Logo_4.png' style='max-height:120px;' alt='Nash Fashion'>"

# WhatsApp API Credentials
WHATSAPP_PHONE_ID = "1157595814106467"
WHATSAPP_ACCESS_TOKEN = "EAAOw79Xci0cBR2PVRuPvK6GueBM0Sd1PmjRJf6ZAHthW5HzPx1KreVAGuelmUIj90E2g8NuQ3ZASxsCcGWI0hcENT2CMx661JragmvIqG9yUYB9mD8iWicZByfZCUZCKv4ayWJLAzgHRvDQTIoMz5C9mkATP1Rnq6iYH4kA6rHqJyoYjx7FvM5BEInAcJlk1XfkVZBgHCctHWDAQSvJ9vxQK1ziZA8q3J0IR6aiH3tIelQw30ByFgODmmQfJvSIMKXpYj3jt0skJl0TkSMJYYHn"
CATEGORIES = {
    "Men's Wear": {"attributes": ["Brand", "Style"], "variant_fields": ["Size", "Color"]},
    "Women's Wear": {"attributes": ["Brand", "Style"], "variant_fields": ["Size", "Color"]},
    "Children's Wear": {"attributes": ["Brand", "Age Group"], "variant_fields": ["Size", "Color"]},
    "Accessories": {"attributes": ["Brand", "Type", "Material"], "variant_fields": ["Color"]},
    "Cosmetics": {"attributes": ["Brand", "Type", "Skin Type", "Volume"], "variant_fields": ["Size/Volume"]},
    "Appliances": {"attributes": ["Brand", "Model", "Power", "Capacity", "Warranty"], "variant_fields": ["Model"]},
    "Other": {"attributes": ["Custom Info"], "variant_fields": []}
}

ORDER_STATUSES = ["Paid", "Confirmed", "Packed", "Dispatcher Assigned", "Shipped", "Delivered", "RTO", "CR", "Cancelled"]
INVENTORY_STATUSES = ["Ordered", "In Transit", "Received", "Partial"]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_json(filename, default=[]):
    if os.path.exists(filename):
        with open(filename, 'r') as f: return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=2)

def load_products(): return load_json(PRODUCTS_FILE, [])
def save_products(p): save_json(PRODUCTS_FILE, p)
def load_orders(): return load_json(ORDERS_FILE, [])
def save_orders(o): save_json(ORDERS_FILE, o)
def save_order(order):
    orders = load_orders()
    orders.append(order)
    save_orders(orders)
def load_inventory(): return load_json(INVENTORY_FILE, [])
def save_inventory(i): save_json(INVENTORY_FILE, i)
def load_dispatchers(): return load_json(DISPATCHERS_FILE, [])
def save_dispatchers(d): save_json(DISPATCHERS_FILE, d)

def find_dispatcher(phone, plate):
    dispatchers = load_dispatchers()
    return next((d for d in dispatchers if d['phone'] == phone and d['plate'] == plate), None)

def generate_sku(category, product_id, variant_key=""):
    prefix = ''.join([w[0] for w in category.split()[:2]]).upper()
    return f"{prefix}-{product_id:04d}{'-'+variant_key if variant_key else ''}"

def get_discounted_price(product):
    price = product.get('price', 0)
    dt = product.get('discount_type', 'None')
    dv = product.get('discount_value', 0)
    if dt == 'Percentage': return int(price - (price * dv / 100))
    elif dt == 'Fixed Amount': return max(0, price - dv)
    return price

def get_stock_level(product_id, variant_key=""):
    inv = load_inventory()
    orders = load_orders()
    received = sum(i['quantity_received'] for i in inv if i['product_id']==product_id and i.get('variant_key','')==variant_key and i['status'] in ['Received','Partial'])
    sold = sum(item['qty'] for o in orders for item in o.get('items',[]) if item.get('product_id')==product_id and item.get('variant_key','')==variant_key)
    return received - sold

def get_product_by_id(pid):
    return next((p for p in load_products() if p['id']==pid), None)

def get_cart():
    if 'cart' not in session: session['cart'] = {}
    return session['cart']

def cart_count(): return sum(get_cart().values())
def is_admin(): return session.get('admin_logged_in')==True

def get_image_html(images, size_class="h-48 w-full", alt="Product"):
    if not images: return f'<div class="bg-gray-200 {size_class} rounded flex items-center justify-center text-5xl">📷</div>'
    return f'<img src="/{images[0]}" class="{size_class} object-cover rounded" alt="{alt}">'

def get_gallery_html(images, product_name):
    if len(images) <= 1: return ""
    thumbs = ""
    for idx, img in enumerate(images):
        active = "	border-yellow-500 opacity-100" if idx==0 else "border-gray-300 opacity-60"
        thumbs += f'<img src="/{img}" class="w-16 h-16 object-cover rounded border-2 {active} cursor-pointer" onclick="document.getElementById(\'mainImage\').src=this.src;this.parentElement.querySelectorAll(\'img\').forEach(i=>i.classList.remove(\'	border-yellow-500\',\'opacity-100\'));this.classList.add(\'	border-yellow-500\',\'opacity-100\');" alt="{product_name}">'
    return f'<div class="flex gap-2 mt-3 flex-wrap">{thumbs}</div>'

def get_product_price_display(product):
    original = product.get('price', 0)
    discounted = get_discounted_price(product)
    if discounted < original:
        return f'<span class="text-gray-400 line-through text-sm">{original:,} XAF</span> <span class="text-yellow-500 font-bold text-lg">{discounted:,} XAF</span>'
    return f'<span class="text-yellow-500 font-bold text-lg">{original:,} XAF</span>'

def get_product_tags_html(product):
    tags = product.get('tags', [])
    if not tags: return ""
    tag_html = ""
    colors = {"Deal": "bg-red-500", "Clearance": "bg-orange-500", "New Arrival": "bg-green-500", "Best Seller": "bg-yellow-500", "Limited Edition": "bg-purple-500"}
    for tag in tags:
        c = colors.get(tag, "bg-gray-500")
        tag_html += f'<span class="{c} text-white text-xs px-2 py-0.5 rounded mr-1">{tag}</span>'
    return f'<div class="flex flex-wrap mt-1">{tag_html}</div>'


# ─── Report Helpers ───
def get_today_orders():
    today = datetime.now().strftime('%Y-%m-%d')
    return [o for o in load_orders() if o['date'].startswith(today)]

def get_week_orders():
    week_ago = datetime.now() - timedelta(days=7)
    return [o for o in load_orders() if o['date'] >= week_ago.strftime('%Y-%m-%d')]

def get_month_orders():
    month_start = datetime.now().strftime('%Y-%m') + '-01'
    return [o for o in load_orders() if o['date'] >= month_start]

def get_product_sales():
    products = load_products()
    orders = load_orders()
    sales = {}
    for p in products:
        pid = p['id']
        sq = sum(item['qty'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        sr = sum(item['subtotal'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        if sq > 0: sales[pid] = {"name": p['name'], "sku": p.get('sku','N/A'), "qty": sq, "revenue": sr}
    return dict(sorted(sales.items(), key=lambda x: x[1]['qty'], reverse=True))

def get_inventory_value():
    inv = load_inventory()
    products = load_products()
    total_value = 0
    details = []
    for p in products:
        pid = p['id']
        stock = get_stock_level(pid)
        if stock > 0:
            costs = [i['unit_cost'] for i in inv if i['product_id']==pid and i['status'] in ['Received','Partial']]
            avg_cost = sum(costs)/len(costs) if costs else 0
            value = stock * avg_cost
            total_value += value
            details.append({"name": p['name'], "sku": p.get('sku','N/A'), "stock": stock, "avg_cost": avg_cost, "value": value})
    return total_value, details

def get_profit_data():
    products = load_products()
    orders = load_orders()
    inv = load_inventory()
    profit_data = []
    total_profit = 0
    for p in products:
        pid = p['id']
        sq = sum(item['qty'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        sr = sum(item['subtotal'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        costs = [i['unit_cost'] for i in inv if i['product_id']==pid and i['status'] in ['Received','Partial']]
        avg_cost = sum(costs)/len(costs) if costs else 0
        profit = sr - (sq * avg_cost)
        margin = (profit/sr*100) if sr>0 else 0
        total_profit += profit
        if sq > 0: profit_data.append({"name": p['name'], "qty": sq, "revenue": sr, "cost": avg_cost, "profit": profit, "margin": margin})
    return total_profit, sorted(profit_data, key=lambda x: x['profit'], reverse=True)

def get_top_customers():
    orders = load_orders()
    customers = {}
    for o in orders:
        name = o['name']
        if name not in customers: customers[name] = {"name": name, "phone": o['phone'], "orders": 0, "total": 0}
        customers[name]['orders'] += 1
        customers[name]['total'] += o['total']
    return sorted(customers.values(), key=lambda x: x['total'], reverse=True)[:20]


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ═══════════════════════════════════
#  CUSTOMER PAGES
# ═══════════════════════════════════

@app.route('/')
def home():
    products = load_products()
    count = cart_count()
    
    # Get filter params
    search_query = request.args.get('search', '').strip().lower()
    filter_category = request.args.get('category', '').strip()
    filter_tag = request.args.get('tag', '').strip()
    
    # Apply filters
    if search_query:
        products = [p for p in products if search_query in p['name'].lower() or search_query in p.get('description','').lower() or search_query in p.get('sku','').lower()]
    if filter_category:
        products = [p for p in products if p.get('category','') == filter_category]
    if filter_tag:
        products = [p for p in products if filter_tag in p.get('tags',[])]
    
    # Build category options
    cat_opts = '<option value="">All Categories</option>'
    for c in CATEGORIES:
        selected = 'selected' if filter_category == c else ''
        cat_opts += f'<option value="{c}" {selected}>{c}</option>'
    
    # Build tag options
    tag_opts = '<option value="">All Tags</option>'
    for t in SPECIAL_TAGS:
        selected = 'selected' if filter_tag == t else ''
        tag_opts += f'<option value="{t}" {selected}>{t}</option>'
    
    # Sections
    deal_products = [p for p in products if 'Deal' in p.get('tags', [])]
    clearance_products = [p for p in products if 'Clearance' in p.get('tags', [])]
    regular_products = [p for p in products if p not in deal_products and p not in clearance_products]
    
    def product_card(p):
        imgs = p.get('images',[])
        ih = get_image_html(imgs, "h-48 w-full", p['name'])
        variants = p.get('variants',[])
        total_stock = sum(get_stock_level(p['id'],v.get('key','')) for v in variants) if variants else get_stock_level(p['id'])
        sb = '<p class="text-red-500 text-xs font-medium mt-1">Out of Stock</p>' if total_stock<=0 else (f'<p class="text-orange-500 text-xs font-medium mt-1">Only {total_stock} left</p>' if total_stock<=5 else '')
        tags_html = get_product_tags_html(p)
        price_html = get_product_price_display(p)
        return f'''<div class="bg-white rounded-lg shadow p-4 hover:shadow-md transition">{ih}{tags_html}<span class="text-xs bg-black text-yellow-400 px-2 py-1 rounded mt-1 inline-block">{p.get('category','Other')}</span><h3 class="font-semibold text-lg mt-1">{p['name']}</h3><p class="text-gray-400 text-xs font-mono">SKU: {p.get('sku','N/A')}</p><p class="text-gray-500 text-sm mb-1">{p['description']}</p><div class="mb-1">{price_html}</div>{sb}<div class="flex gap-2 mt-3"><a href="/product/{p['id']}" class="text-yellow-500 border 	border-yellow-500 px-4 py-2 rounded flex-1 text-center text-sm hover:bg-gray-800 hover:text-yellow-400">Details</a></div></div>'''
    
    sections_html = ""
    if not search_query and not filter_category and not filter_tag:
        if deal_products:
            sections_html += '<div class="mb-8"><h2 class="text-xl font-bold text-red-600 mb-4">🔥 Hot Deals</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">' + "".join([product_card(p) for p in deal_products]) + '</div></div>'
        if clearance_products:
            sections_html += '<div class="mb-8"><h2 class="text-xl font-bold text-orange-600 mb-4">🏷️ Clearance Sale</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">' + "".join([product_card(p) for p in clearance_products]) + '</div></div>'
        sections_html += '<h2 class="text-xl font-semibold mb-4">All Products</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">' + "".join([product_card(p) for p in regular_products]) + '</div>'
    else:
        sections_html = '<h2 class="text-xl font-semibold mb-4">Results (' + str(len(products)) + ')</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">' + "".join([product_card(p) for p in products]) + '</div>'
    
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script><link rel="manifest" href="/static/manifest.json"></head><body class="bg-gray-50"><header class="bg-white shadow p-2 flex justify-between items-center border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1><nav class="flex items-center gap-2"><a href="/" class="text-gray-600 mx-2 hover:text-yellow-500">Home</a><a href="/cart" class="text-gray-600 mx-2 hover:text-yellow-500">Cart ({count})</a><a href="/my-orders" class="text-gray-600 mx-2 hover:text-yellow-500">My Orders</a></nav></header><main class="max-w-6xl mx-auto p-4">
    <!-- Search & Filter Bar -->
    <div class="bg-white rounded-lg shadow p-4 mb-6">
    <form method="GET" action="/" class="flex flex-wrap gap-3 items-end">
    <div class="flex-1 min-w-[200px]">
    <label class="block text-xs text-gray-500 mb-1">Search</label>
    <input type="text" name="search" value="{search_query}" placeholder="Search products..." class="w-full border rounded px-3 py-2 text-sm">
    </div>
    <div>
    <label class="block text-xs text-gray-500 mb-1">Category</label>
    <select name="category" class="border rounded px-3 py-2 text-sm" onchange="this.form.submit()">{cat_opts}</select>
    </div>
    <div>
    <label class="block text-xs text-gray-500 mb-1">Tag</label>
    <select name="tag" class="border rounded px-3 py-2 text-sm" onchange="this.form.submit()">{tag_opts}</select>
    </div>
    <button type="submit" class="	bg-black text-white px-4 py-2 rounded text-sm hover:bg-gray-800">Filter</button>
    <a href="/" class="text-gray-500 text-sm hover:underline">Clear</a>
    </form></div>
    
    <div class="bg-black border border-yellow-400 rounded-lg p-4 mb-6 text-center"><h2 class="text-xl font-semibold text-yellow-400">Welcome to {STORE_NAME}</h2><p class="text-yellow-300 text-sm">Fashion · Cosmetics · Appliances — Free delivery over {FREE_DELIVERY_THRESHOLD:,} XAF</p></div>
    {sections_html or '<p class="text-gray-500 col-span-full text-center py-12">No products found</p>'}
    
    <!-- Footer -->
    <div class="text-center mt-8 py-4 border-t text-sm text-gray-500">
    <p>📞 WhatsApp: <a href="https://wa.me/{STORE_WHATSAPP}" class="text-green-600 hover:underline">{STORE_WHATSAPP}</a></p>
    <div class="text-center my-4"><img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=https://nash-fashion.onrender.com" alt="Scan to visit Nash Fashion" class="mx-auto rounded shadow"><p class="text-xs text-gray-500 mt-1">📱 Scan to open our store</p></div>
    <p class="mt-1">{STORE_NAME} © 2026</p>
    </div>
    </main></body></html>'''

@app.route('/product/<int:pid>')
def product_detail(pid):
    p = get_product_by_id(pid)
    if not p: return redirect('/')
    count = cart_count()
    imgs = p.get('images',[])
    variants = p.get('variants',[])
    vfields = CATEGORIES.get(p.get('category','Other'),{}).get('variant_fields',[])
    vhtml = ""; vpjs = "{}"
    if variants and vfields:
        vhtml = '<div class="space-y-3 mb-4">'
        for f in vfields:
            vals = sorted(set(v.get('attrs',{}).get(f,'') for v in variants if v.get('attrs',{}).get(f,'')))
            if vals:
                opts = "".join([f'<option value="{v}">{v}</option>' for v in vals])
                vhtml += f'<div><label class="block text-sm text-gray-600 mb-1">{f}</label><select class="variant-select border rounded px-3 py-2 w-full" onchange="updateVariant()"><option value="">Select {f}</option>{opts}</select></div>'
        vhtml += '</div>'
        vmap = {}
        for v in variants:
            key = "|".join([v.get('attrs',{}).get(f,'') for f in vfields])
            vmap[key] = {"price": get_discounted_price(v) if v.get('price') else get_discounted_price(p), "stock": get_stock_level(pid,v.get('key','')), "key": v.get('key','')}
        vpjs = json.dumps(vmap)
    
    main_img = f'<img src="/{imgs[0]}" id="mainImage" class="w-full md:w-96 h-96 object-cover rounded">' if imgs else '<div class="bg-gray-200 w-full md:w-96 h-96 rounded flex items-center justify-center text-8xl">📷</div>'
    gallery = get_gallery_html(imgs, p['name'])
    attrs = p.get('attributes',{})
    arows = "".join([f'<tr class="border-b"><td class="py-2 px-4 bg-gray-50 font-medium text-sm">{k}</td><td class="py-2 px-4 text-sm">{v}</td></tr>' for k,v in attrs.items() if v]) or '<tr><td colspan="2" class="py-2 px-4 text-sm text-gray-400">No specifications</td></tr>'
    tags_html = get_product_tags_html(p)
    price_display = get_product_price_display(p)
    discounted = get_discounted_price(p)
    
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{p['name']} — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({count})</a></nav></header><main class="max-w-4xl mx-auto p-4"><a href="/" class="text-yellow-500 text-sm mb-2 inline-block">&larr; Back</a><div class="bg-white rounded-lg shadow p-6"><div class="flex flex-col md:flex-row gap-6"><div>{main_img}{gallery}</div><div class="flex-1">{tags_html}<span class="text-xs bg-black text-yellow-400 px-2 py-1 rounded">{p.get('category','Other')}</span><h2 class="text-2xl font-bold mt-2">{p['name']}</h2><p class="text-gray-400 text-sm font-mono">SKU: {p.get('sku','N/A')}</p><p class="text-gray-600 my-3">{p['description']}</p><p class="text-3xl font-bold text-yellow-500 mb-2" id="variant-price">{discounted:,} XAF</p>{price_display if discounted < p.get('price',0) else ''}<p class="text-sm mb-2" id="variant-stock"></p>{vhtml}<h3 class="font-semibold mb-2 mt-4">Specifications</h3><table class="w-full border rounded overflow-hidden mb-4"><tbody>{arows}</tbody></table><form method="POST" action="/add-to-cart"><input type="hidden" name="product_id" value="{p['id']}"><input type="hidden" name="variant_key" id="variant-key" value=""><button type="submit" class="	bg-black text-white px-8 py-3 rounded-lg text-lg hover:bg-gray-800 w-full" id="add-btn">Add to Cart</button></form></div></div></div></main><script>var vd={vpjs};var vf={json.dumps(vfields)};function updateVariant(){{var s=document.querySelectorAll('.variant-select');var k=[];s.forEach(x=>k.push(x.value));var fk=k.join('|');var d=vd[fk];var pe=document.getElementById('variant-price');var se=document.getElementById('variant-stock');var ki=document.getElementById('variant-key');var b=document.getElementById('add-btn');if(d){{pe.textContent=d.price.toLocaleString()+' XAF';se.textContent='In Stock ('+d.stock+' available)';se.className='text-sm mb-2 text-green-600';ki.value=d.key;b.disabled=d.stock<=0;b.textContent=d.stock<=0?'Out of Stock':'Add to Cart';}}else if(k.every(x=>x!=='')){{b.disabled=true;b.textContent='Unavailable';}}else{{b.disabled=true;}}}}updateVariant();</script></body></html>'''


@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    pid = str(request.form.get('product_id'))
    vk = request.form.get('variant_key','')
    cart = get_cart()
    ck = f"{pid}|{vk}" if vk else pid
    cart[ck] = cart.get(ck,0) + 1
    session['cart'] = cart
    return redirect('/cart')

@app.route('/cart')
def view_cart():
    products = load_products()
    cart = get_cart()
    items = ""; total = 0
    for ck, qty in cart.items():
        parts = ck.split('|'); pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = get_discounted_price(v) if v and v.get('price') else get_discounted_price(p)
        st = price * qty; total += st
        imgs = p.get('images',[])
        ih = f'<img src="/{imgs[0]}" class="w-12 h-12 object-cover rounded">' if imgs else '<span class="text-3xl">📷</span>'
        items += f'''<div class="bg-white rounded-lg shadow p-4 flex justify-between items-center mb-3"><div class="flex items-center gap-3">{ih}<div><h3 class="font-semibold">{name}</h3><p class="text-gray-400 text-xs font-mono">SKU: {(v.get("sku",p.get("sku")) if v else p.get("sku","N/A"))}</p><p class="text-gray-500 text-sm">{price:,} XAF</p></div></div><div class="text-right"><p class="text-sm text-gray-500">Qty: {qty}</p><p class="font-bold text-yellow-500">{st:,} XAF</p></div></div>'''
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Cart</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Your Cart</h2>{items or '<p class="text-gray-500 text-center py-8">Cart is empty. <a href="/" class="text-yellow-500 underline">Shop</a></p>'}{"<p class='text-right text-xl font-bold mt-4'>Subtotal: "+f"{total:,} XAF</p>" if cart else ""}{'<div class="text-center mt-6"><a href="/checkout" class="	bg-black text-white px-8 py-3 rounded-lg text-lg hover:bg-gray-800 inline-block">Proceed to Checkout</a></div>' if cart else ''}</main></body></html>'''


@app.route('/checkout')
def checkout():
    products = load_products()
    cart = get_cart()
    subtotal = 0; summary = ""
    for ck, qty in cart.items():
        parts = ck.split('|'); pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = get_discounted_price(v) if v and v.get('price') else get_discounted_price(p)
        st = price * qty; subtotal += st
        summary += f'<div class="flex justify-between text-sm py-1"><span>{name} × {qty}</span><span>{st:,} XAF</span></div>'
    if not cart: return redirect('/cart')
    zones = "".join([f'<option value="{z}">{z} - {p:,} XAF</option>' for z,p in DELIVERY_ZONES.items()])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Checkout</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Checkout</h2><div class="bg-white rounded-lg shadow p-4 mb-6"><h3 class="font-semibold mb-2">Order Summary</h3>{summary}<hr class="my-2"><p class="text-right font-medium">Subtotal: {subtotal:,} XAF</p><p class="text-xs text-gray-500 text-right">Free delivery over {FREE_DELIVERY_THRESHOLD:,} XAF</p></div><form method="POST" action="/initiate-payment" class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Your Details</h3><label class="block mb-1 text-sm">Full Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Phone (MoMo) *</label><input type="tel" name="phone" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Delivery Zone *</label><select name="delivery_zone" required class="w-full border rounded px-3 py-2 mb-3" id="zone-select" onchange="updateTotal()"><option value="">-- Select Zone --</option>{zones}</select><label class="block mb-1 text-sm">Delivery Address</label><textarea name="address" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm font-semibold">Payment *</label><div class="mb-2"><label class="inline-flex items-center mr-4"><input type="radio" name="payment_method" value="mtn_momo" checked class="mr-2">MTN MoMo</label><label class="inline-flex items-center"><input type="radio" name="payment_method" value="orange_money" class="mr-2">Orange</label></div><hr class="my-3"><div id="total-display"><p class="text-right text-sm">Delivery: <span id="delivery-cost">—</span></p><p class="text-right text-xl font-bold text-yellow-500">Total: <span id="grand-total">{subtotal:,}</span> XAF</p></div><input type="hidden" name="delivery_cost" id="delivery-cost-input" value="0"><input type="hidden" name="final_total" id="final-total-input" value="{subtotal}"><button type="submit" class="	bg-black text-white px-6 py-3 rounded-lg w-full text-lg hover:bg-gray-800 mt-3">Confirm & Pay</button></form></main><script>var subtotal={subtotal};var zones={json.dumps(DELIVERY_ZONES)};var freeThreshold={FREE_DELIVERY_THRESHOLD};function updateTotal(){{var zone=document.getElementById('zone-select').value;var cost=zones[zone]||0;if(subtotal>=freeThreshold)cost=0;document.getElementById('delivery-cost').textContent=cost.toLocaleString()+' XAF';var total=subtotal+cost;document.getElementById('grand-total').textContent=total.toLocaleString();document.getElementById('delivery-cost-input').value=cost;document.getElementById('final-total-input').value=total;}}updateTotal();</script></body></html>'''


@app.route('/initiate-payment', methods=['POST'])
def initiate_payment():
    products = load_products()
    cart = get_cart()
    subtotal = 0; items = []
    delivery_zone = request.form.get('delivery_zone','')
    delivery_cost = int(request.form.get('delivery_cost',0))
    final_total = int(request.form.get('final_total',0))
    
    for ck, qty in cart.items():
        parts = ck.split('|'); pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = get_discounted_price(v) if v and v.get('price') else get_discounted_price(p)
        st = price * qty; subtotal += st
        items.append({"product_id":pid,"sku":v.get("sku",p.get("sku")) if v else p.get("sku","N/A"),"name":name,"qty":qty,"price":price,"subtotal":st,"variant_key":vk})
    if not cart: return redirect('/cart')
    ref = f"MOMO-TEST-{int(time.time())}"
    label = "MTN Mobile Money" if request.form.get('payment_method')=="mtn_momo" else "Orange Money"
    session['pending_order'] = {"ref":ref,"name":request.form.get('name'),"phone":request.form.get('phone'),"address":request.form.get('address'),"delivery_zone":delivery_zone,"delivery_cost":delivery_cost,"payment_label":label,"items":items,"subtotal":subtotal,"total":final_total}
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Confirm Payment</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1></header><main class="max-w-lg mx-auto p-4"><div class="bg-white rounded-lg shadow p-6 text-center"><div class="text-5xl mb-4">📱</div><h2 class="text-xl font-semibold mb-2">Confirm Payment</h2><p>Payment of <strong>{final_total:,} XAF</strong> via <strong>{label}</strong>.</p><p class="text-xs text-gray-500">Subtotal: {subtotal:,} XAF | Delivery: {delivery_cost:,} XAF</p><div class="bg-gray-100 rounded p-4 my-4"><p class="text-sm">Ref: {ref}</p><p class="text-xs text-gray-400">TEST MODE</p></div><form method="POST" action="/verify-payment"><label class="block mb-2 text-sm">Enter MoMo PIN (any 4 digits)</label><input type="password" name="pin" maxlength="6" required class="border rounded px-3 py-2 text-center text-lg w-32 mb-4"><br><button type="submit" class="	bg-black text-white px-8 py-3 rounded-lg text-lg hover:bg-gray-800">Confirm</button></form></div></main></body></html>'''


@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    pending = session.get('pending_order')
    if not pending or len(request.form.get('pin',''))<4: return redirect('/checkout')
    order = {"ref":pending['ref'],"name":pending['name'],"phone":pending['phone'],"address":pending['address'],"delivery_zone":pending.get('delivery_zone',''),"delivery_cost":pending.get('delivery_cost',0),"payment_method":pending['payment_label'],"items":pending['items'],"subtotal":pending['subtotal'],"total":pending['total'],"status":"Paid","date":time.strftime('%Y-%m-%d %H:%M:%S')}
    save_order(order)
    session['cart'] = {}
    ref = pending['ref']
    session.pop('pending_order',None)
    # Send WhatsApp confirmation
    try:
        whatsapp_msg = f"🎉 *Order Confirmed!*\n\nThank you {order['name']} for your order at {STORE_NAME}!\n\n*Ref:* {ref}\n*Total:* {order['total']:,} XAF\n*Delivery:* {order.get('delivery_zone','')}\n\nWe'll notify you when your order ships. 🚚\n\nQuestions? Reply here!"
        send_whatsapp_message(order['phone'], whatsapp_msg)
    except:
        pass
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Success</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1></header><main class="max-w-lg mx-auto p-4 text-center"><div class="bg-white rounded-lg shadow p-6"><div class="text-6xl mb-4">✅</div><h2 class="text-2xl font-bold text-yellow-500 mb-2">Payment Successful!</h2><p>Thank you, <strong>{order['name']}</strong>!</p><div class="bg-gray-100 rounded p-4 my-4 text-left"><p class="text-sm">Ref: <strong>{ref}</strong></p><p class="text-sm">Subtotal: {order['subtotal']:,} XAF</p><p class="text-sm">Delivery: {order['delivery_cost']:,} XAF</p><p class="font-bold text-yellow-500 text-xl mt-2">Total: {order['total']:,} XAF</p></div><a href="/" class="	bg-black text-white px-8 py-3 rounded-lg text-lg hover:bg-gray-800 inline-block">Continue Shopping</a><p class="text-sm text-gray-500 mt-4">Questions? <a href="https://wa.me/{STORE_WHATSAPP}" class="text-green-600 underline">WhatsApp us</a></p></div></main></body></html>'''
        # Send WhatsApp confirmation
    whatsapp_msg = f"""🎉 *Order Confirmed!*

Thank you {order['name']} for your order at {STORE_NAME}!

*Ref:* {ref}
*Total:* {order['total']:,} XAF
*Delivery:* {order.get('delivery_zone','')}

We'll notify you when your order ships. 🚚

Questions? Reply here!"""
    send_whatsapp_message(order['phone'], whatsapp_msg)
    session['cart'] = {}
    ref = pending['ref']
    session.pop('pending_order',None)
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Success</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1></header><main class="max-w-lg mx-auto p-4 text-center"><div class="bg-white rounded-lg shadow p-6"><div class="text-6xl mb-4">✅</div><h2 class="text-2xl font-bold text-yellow-500 mb-2">Payment Successful!</h2><p>Thank you, <strong>{order['name']}</strong>!</p><div class="bg-gray-100 rounded p-4 my-4 text-left"><p class="text-sm">Ref: <strong>{ref}</strong></p><p class="text-sm">Subtotal: {order['subtotal']:,} XAF</p><p class="text-sm">Delivery: {order['delivery_cost']:,} XAF</p><p class="font-bold text-yellow-500 text-xl mt-2">Total: {order['total']:,} XAF</p></div><a href="/" class="	bg-black text-white px-8 py-3 rounded-lg text-lg hover:bg-gray-800 inline-block">Continue Shopping</a><p class="text-sm text-gray-500 mt-4">Questions? <a href="https://wa.me/{STORE_WHATSAPP}" class="text-green-600 underline">WhatsApp us</a></p></div></main></body></html>'''

@app.route('/my-orders', methods=['GET', 'POST'])
def customer_orders():
    phone = request.form.get('phone', '').strip() if request.method == 'POST' else ''
    ref = request.form.get('ref', '').strip() if request.method == 'POST' else ''
    found_order = None
    error = ""
    
    if phone and ref:
        all_orders = load_orders()
        found_order = next((o for o in all_orders if (o.get('phone','') == phone or o.get('phone','') == f'+{phone}') and o['ref'].upper() == ref.upper()), None)
        if not found_order:
            error = '<p class="text-red-500 text-center py-3">No order found. Check your phone and order reference.</p>'
    elif phone or ref:
        error = '<p class="text-orange-500 text-center py-3">Please enter both phone number AND order reference.</p>'
    
    result_html = ""
    if found_order:
        o = found_order
        statuses = ["Paid", "Confirmed", "Packed", "Shipped", "Delivered"]
        current_idx = statuses.index(o["status"]) if o["status"] in statuses else 0
        progress = "".join([f'<div class="flex-1 {"	bg-black" if i<=current_idx else "bg-gray-300"} h-2 rounded mx-0.5"></div>' for i in range(len(statuses))])
        disp_html = ""
        if o.get('dispatcher',{}).get('name'):
            disp_html = f'''<div class="mt-3 bg-green-50 border border-green-200 rounded p-3"><h4 class="text-sm font-semibold mb-1">🛵 Dispatcher</h4><p class="text-sm">Name: <strong>{o["dispatcher"]["name"]}</strong></p><p class="text-sm">Plate: <strong>{o["dispatcher"]["plate"]}</strong></p><p class="text-sm">Phone: <strong>{o["dispatcher"]["phone"]}</strong></p></div>'''
        result_html = f'''<div class="bg-white rounded-lg shadow p-6"><div class="flex justify-between mb-2"><span class="font-bold">{o["ref"]}</span><span class="bg-black text-yellow-400 px-3 py-1 rounded text-sm">{o["status"]}</span></div><div class="flex mb-4">{progress}</div><p class="text-xs text-gray-500 mb-3">{o["date"]}</p><div class="grid grid-cols-2 gap-2 text-sm mb-3"><div><p class="text-xs text-gray-500">Customer</p><p class="font-medium">{o["name"]}</p></div><div><p class="text-xs text-gray-500">Delivery Zone</p><p>{o.get("delivery_zone","")}</p></div></div>{disp_html}<h4 class="font-semibold text-sm mb-2 mt-3">Items</h4><table class="w-full text-xs mb-3"><thead><tr class="border-b"><th class="py-1 text-left">Item</th><th class="py-1">Qty</th><th class="py-1">Price</th></tr></thead><tbody>''' + "".join([f'<tr class="border-b"><td class="py-1">{i["name"]}</td><td class="py-1 text-center">{i["qty"]}</td><td class="py-1 text-right">{i["price"]:,} XAF</td></tr>' for i in o["items"]]) + f'''</tbody></table><div class="text-right"><p class="text-sm">Subtotal: {o.get("subtotal",o["total"]):,} XAF</p><p class="text-sm">Delivery: {o.get("delivery_cost",0):,} XAF</p><p class="text-lg font-bold text-yellow-500">Total: {o["total"]:,} XAF</p></div></div>'''
    
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Track Order — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-yellow-500"><h1 class="text-2xl font-bold text-yellow-500">{STORE_LOGO_TEXT}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">📋 Track Your Order</h2><p class="text-sm text-gray-500 mb-4">Enter phone number and order reference from your confirmation.</p><form method="POST" class="bg-white rounded-lg shadow p-4 mb-4"><label class="block mb-1 text-sm">Phone Number *</label><input type="tel" name="phone" value="{phone}" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Order Reference *</label><input type="text" name="ref" value="{ref}" required class="w-full border rounded px-3 py-2 mb-3"><button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full">Track Order</button></form>{error}{result_html}<div class="text-center mt-6"><a href="/" class="text-yellow-500 underline text-sm">Back to Shop</a></div></main></body></html>'''
#  ADMIN
# ═══════════════════════════════════

@app.route('/admin')
def admin_login_page():
    if is_admin(): return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 w-full max-w-sm"><h1 class="text-2xl font-bold text-yellow-500 text-center mb-6">🔐 Admin Login</h1><form method="POST" action="/admin/login"><label class="block mb-1 text-sm">Username</label><input type="text" name="username" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Password</label><input type="password" name="password" required class="w-full border rounded px-3 py-2 mb-4"><button type="submit" class="	bg-black text-white px-4 py-2 rounded w-full">Login</button></form></div></body></html>'''

@app.route('/admin/login', methods=['POST'])
def admin_login():
    if request.form.get('username')==ADMIN_USERNAME and request.form.get('password')==ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Failed</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 text-center"><div class="text-4xl mb-4">❌</div><h2 class="text-xl mb-2">Login Failed</h2><a href="/admin" class="text-yellow-500 underline">Try Again</a></div></body></html>'''

def admin_header(active=""):
    links = [("Dashboard","/admin/dashboard"),("Products","/admin/products"),("Inventory","/admin/inventory"),("Orders","/admin/orders"),("Marketing","/admin/marketing"),("Reports","/admin/reports"),("Settings","/admin/settings"),("Help","/admin/help"),("Logout","/admin/logout")]
    nav = "".join([f'<a href="{u}" class="	text-yellow-100 mx-2 hover:text-white {"font-bold underline" if l==active else ""}">{l}</a>' for l,u in links])
    return f'''<header class="	bg-black text-white p-4 flex justify-between items-center flex-wrap"><h1 class="text-xl font-bold">{STORE_LOGO_TEXT} Admin</h1><nav class="flex flex-wrap">{nav}</nav></header>'''
    
@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    products = load_products()
    today = get_today_orders()
    week = get_week_orders()
    revenue = sum(o['total'] for o in orders)
    low = ''.join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2 font-mono text-xs">{p.get("sku","N/A")}</td><td class="py-2"><span class="text-red-600">{get_stock_level(p["id"])}</span></td></tr>' for p in products if get_stock_level(p['id'])<=5]) or '<tr><td colspan="3" class="py-2 text-center text-gray-400">All well stocked</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Dashboard")}<main class="max-w-5xl mx-auto p-4"><div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-yellow-500">{len(today)}</p><p class="text-gray-500 text-sm">Today</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-yellow-500">{len(week)}</p><p class="text-gray-500 text-sm">This Week</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-yellow-500">{len(orders)}</p><p class="text-gray-500 text-sm">Total Orders</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-yellow-500">{revenue:,}</p><p class="text-gray-500 text-sm">Revenue</p></div></div><div class="grid grid-cols-1 lg:grid-cols-2 gap-4"><div class="bg-white rounded-lg shadow p-4"><h2 class="font-semibold mb-3">Low Stock</h2><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th></tr></thead><tbody>{low}</tbody></table></div><div class="bg-white rounded-lg shadow p-4"><h2 class="font-semibold mb-3">Quick Links</h2><div class="space-y-2"><a href="/admin/reports" class="block bg-yellow-50 text-yellow-500 p-3 rounded">View Reports</a><a href="/admin/products/add" class="block bg-green-50 text-green-700 p-3 rounded">Add Product</a><a href="/admin/inventory/add" class="block bg-blue-50 text-blue-700 p-3 rounded">Add Inventory</a></div></div></div></main></body></html>'''

# ─── Marketing ───
@app.route('/admin/marketing')
def admin_marketing():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    deals = [p for p in products if 'Deal' in p.get('tags',[])]
    clearance = [p for p in products if 'Clearance' in p.get('tags',[])]
    discounted = [p for p in products if p.get('discount_type','None') != 'None']
    
    deals_rows = "".join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2">{p.get("sku","N/A")}</td><td class="py-2">{p["price"]:,} XAF</td><td class="py-2"><span class="text-green-600">{get_discounted_price(p):,} XAF</span></td><td class="py-2"><a href="/admin/products/edit/{p["id"]}" class="text-blue-600 text-xs">Edit</a></td></tr>' for p in deals]) or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No deals</td></tr>'
    clearance_rows = "".join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2">{p.get("sku","N/A")}</td><td class="py-2">{p["price"]:,} XAF</td><td class="py-2"><a href="/admin/products/edit/{p["id"]}" class="text-blue-600 text-xs">Edit</a></td></tr>' for p in clearance]) or '<tr><td colspan="4" class="py-4 text-center text-gray-400">No clearance items</td></tr>'
    disc_rows = "".join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2">{p.get("discount_type","")} {p.get("discount_value",0)}{"%" if p.get("discount_type")=="Percentage" else " XAF"}</td><td class="py-2"><span class="line-through text-gray-400">{p["price"]:,}</span> <span class="text-green-600 font-medium">{get_discounted_price(p):,} XAF</span></td><td class="py-2"><a href="/admin/products/edit/{p["id"]}" class="text-blue-600 text-xs">Edit</a></td></tr>' for p in discounted]) or '<tr><td colspan="4" class="py-4 text-center text-gray-400">No discounts</td></tr>'
    
    zones_rows = "".join([f'<tr class="border-b"><td class="py-2 font-medium">{z}</td><td class="py-2">{p:,} XAF</td></tr>' for z,p in DELIVERY_ZONES.items()])
    
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Marketing</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Marketing")}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">📢 Marketing & Promotions</h2>
    
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
    <div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-red-600">{len(deals)}</p><p class="text-gray-500 text-sm">Active Deals</p></div>
    <div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-orange-600">{len(clearance)}</p><p class="text-gray-500 text-sm">Clearance Items</p></div>
    <div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-green-600">{len(discounted)}</p><p class="text-gray-500 text-sm">Discounted Products</p></div></div>
    
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
    <div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">🔥 Hot Deals</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Original</th><th class="py-2">Now</th><th class="py-2">Act</th></tr></thead><tbody>{deals_rows}</tbody></table></div>
    <div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">🏷️ Clearance</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Price</th><th class="py-2">Act</th></tr></thead><tbody>{clearance_rows}</tbody></table></div></div>
    
    <div class="bg-white rounded-lg shadow p-4 mb-6"><h3 class="font-semibold mb-3">💰 Discounted Products</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">Discount</th><th class="py-2">Price</th><th class="py-2">Act</th></tr></thead><tbody>{disc_rows}</tbody></table></div>
    
    <div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">🚚 Delivery Zones</h3><table class="w-full text-sm mb-3"><thead><tr class="border-b text-left"><th class="py-2">Zone</th><th class="py-2">Cost</th></tr></thead><tbody>{zones_rows}</tbody></table><p class="text-xs text-gray-500">Free delivery on orders over <strong>{FREE_DELIVERY_THRESHOLD:,} XAF</strong>. Edit in app.py configuration.</p></div>
    
    <div class="bg-yellow-50 border border-yellow-200 rounded p-4 mt-4"><h3 class="font-semibold text-sm mb-2">💡 How to Manage</h3><ul class="text-sm text-gray-600 space-y-1"><li>• <strong>Discounts:</strong> Edit a product → set Discount Type & Value</li><li>• <strong>Deals/Clearance:</strong> Edit a product → check the tag boxes</li><li>• <strong>Bulk actions:</strong> Use CSV Bulk Upload with discount_type, discount_value, tags columns</li><li>• <strong>Delivery:</strong> Edit DELIVERY_ZONES and FREE_DELIVERY_THRESHOLD in app.py</li></ul></div></main></body></html>'''
# ─── Reports (abbreviated) ───
@app.route('/admin/reports')
def admin_reports():
    if not is_admin(): return redirect('/admin')
    cards = ""
    for title, desc, url, emoji in [("Sales Summary","Daily, weekly, monthly","/admin/reports/sales","💰"),("Product Performance","Best sellers","/admin/reports/products","🏆"),("Inventory Status","Stock & value","/admin/reports/inventory","📦"),("Profit Analysis","Revenue vs cost","/admin/reports/profit","📈"),("Top Customers","Rankings","/admin/reports/customers","👥")]:
        cards += f'<a href="{url}" class="bg-white rounded-lg shadow p-6 hover:shadow-md transition text-center"><div class="text-4xl mb-3">{emoji}</div><h3 class="font-semibold text-lg">{title}</h3><p class="text-gray-500 text-sm">{desc}</p></a>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Reports</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Reports</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{cards}</div></main></body></html>'''

@app.route('/admin/reports/sales')
def report_sales():
    if not is_admin(): return redirect('/admin')
    today = get_today_orders(); week = get_week_orders(); month = get_month_orders()
    tr = sum(o['total'] for o in today); wr = sum(o['total'] for o in week); mr = sum(o['total'] for o in month)
    all_orders = load_orders()
    rows = "".join([f'<tr class="border-b"><td class="py-2 text-xs">{o["date"]}</td><td class="py-2">{o["name"]}</td><td class="py-2">{o["total"]:,} XAF</td><td class="py-2">{o.get("delivery_zone","")}</td><td class="py-2"><span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs">{o["status"]}</span></td></tr>' for o in reversed(all_orders)])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Sales</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">Sales Summary</h2><div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6"><div class="bg-white rounded-lg shadow p-4"><p class="text-sm text-gray-500">Today</p><p class="text-3xl font-bold text-yellow-500">{tr:,} XAF</p><p class="text-sm text-gray-400">{len(today)} orders</p></div><div class="bg-white rounded-lg shadow p-4"><p class="text-sm text-gray-500">This Week</p><p class="text-3xl font-bold text-yellow-500">{wr:,} XAF</p><p class="text-sm text-gray-400">{len(week)} orders</p></div><div class="bg-white rounded-lg shadow p-4"><p class="text-sm text-gray-500">This Month</p><p class="text-3xl font-bold text-yellow-500">{mr:,} XAF</p><p class="text-sm text-gray-400">{len(month)} orders</p></div></div><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">All Orders</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Date</th><th class="py-2">Customer</th><th class="py-2">Total</th><th class="py-2">Zone</th><th class="py-2">Status</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No orders</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/reports/products')
def report_products():
    if not is_admin(): return redirect('/admin')
    sales = get_product_sales()
    rows = ""; rank = 0
    for pid, d in sales.items(): rank += 1; rows += f'<tr class="border-b"><td class="py-2">#{rank}</td><td class="py-2 font-medium">{d["name"]}</td><td class="py-2 text-xs font-mono">{d["sku"]}</td><td class="py-2">{d["qty"]} sold</td><td class="py-2">{d["revenue"]:,} XAF</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Products</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">Product Performance</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Rank</th><th class="py-3 px-4">Product</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Sold</th><th class="py-3 px-4">Revenue</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No sales</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/reports/inventory')
def report_inventory():
    if not is_admin(): return redirect('/admin')
    tv, details = get_inventory_value()
    rows = "".join([f'<tr class="border-b"><td class="py-2">{d["name"]}</td><td class="py-2 text-xs font-mono">{d["sku"]}</td><td class="py-2">{d["stock"]}</td><td class="py-2">{d["avg_cost"]:,.0f} XAF</td><td class="py-2 font-medium">{d["value"]:,.0f} XAF</td></tr>' for d in details])
    products = load_products()
    low = "".join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2 text-xs font-mono">{p.get("sku","N/A")}</td><td class="py-2"><span class="text-red-600 font-medium">{get_stock_level(p["id"])}</span></td></tr>' for p in products if get_stock_level(p['id'])<=5]) or '<tr><td colspan="3" class="py-2 text-center text-gray-400">All well stocked</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">Inventory</h2><div class="bg-white rounded-lg shadow p-4 mb-4 text-center"><p class="text-sm text-gray-500">Total Value</p><p class="text-4xl font-bold text-yellow-500">{tv:,.0f} XAF</p></div><div class="grid grid-cols-1 lg:grid-cols-2 gap-4"><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Stock Valuation</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th><th class="py-2">Avg Cost</th><th class="py-2">Value</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No stock</td></tr>'}</tbody></table></div><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Low Stock</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th></tr></thead><tbody>{low}</tbody></table></div></div></main></body></html>'''

@app.route('/admin/reports/profit')
def report_profit():
    if not is_admin(): return redirect('/admin')
    tp, data = get_profit_data()
    rows = "".join([f'<tr class="border-b"><td class="py-2">{d["name"]}</td><td class="py-2">{d["qty"]} sold</td><td class="py-2">{d["revenue"]:,.0f}</td><td class="py-2">{d["cost"]:,.0f}</td><td class="py-2 {"text-green-600" if d["profit"]>0 else "text-red-600"} font-medium">{d["profit"]:,.0f}</td><td class="py-2">{d["margin"]:.1f}%</td></tr>' for d in data])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Profit</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">Profit Analysis</h2><div class="bg-white rounded-lg shadow p-4 mb-4 text-center"><p class="text-sm text-gray-500">Total Profit</p><p class="text-4xl font-bold text-green-600">{tp:,.0f} XAF</p></div><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Product</th><th class="py-3 px-4">Sold</th><th class="py-3 px-4">Revenue</th><th class="py-3 px-4">Cost/Unit</th><th class="py-3 px-4">Profit</th><th class="py-3 px-4">Margin</th></tr></thead><tbody>{rows or '<tr><td colspan="6" class="py-4 text-center text-gray-400">No data</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/reports/customers')
def report_customers():
    if not is_admin(): return redirect('/admin')
    customers = get_top_customers()
    rows = ""; rank = 0
    for c in customers: rank += 1; rows += f'<tr class="border-b"><td class="py-2">#{rank}</td><td class="py-2 font-medium">{c["name"]}</td><td class="py-2">{c["phone"]}</td><td class="py-2">{c["orders"]}</td><td class="py-2">{c["total"]:,} XAF</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Customers</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">Top Customers</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Rank</th><th class="py-3 px-4">Name</th><th class="py-3 px-4">Phone</th><th class="py-3 px-4">Orders</th><th class="py-3 px-4">Total</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No customers</td></tr>'}</tbody></table></div></main></body></html>'''


# ─── Products ───
@app.route('/admin/products')
def admin_products():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    rows = ""
    for p in products:
        imgs = p.get('images',[])
        ih = f'<img src="/{imgs[0]}" class="w-10 h-10 object-cover rounded">' if imgs else '<span class="text-2xl">📷</span>'
        s = sum(get_stock_level(p['id'],v.get('key','')) for v in p.get('variants',[])) if p.get('variants') else get_stock_level(p['id'])
        sc = 'text-green-600' if s>5 else ('text-orange-500' if s>0 else 'text-red-600')
        tags_str = ", ".join(p.get('tags',[])) or "—"
        disc = p.get('discount_type','None')
        disc_str = f'{disc} {p.get("discount_value",0)}{"%" if disc=="Percentage" else " XAF"}' if disc != 'None' else '—'
        rows += f'''<tr class="border-b"><td class="py-3 px-4">{ih}</td><td class="py-3 px-4 text-xs font-mono">{p.get('sku','N/A')}</td><td class="py-3 px-4 font-medium">{p['name']}</td><td class="py-3 px-4"><span class="text-xs bg-gray-100 px-2 py-1 rounded">{p.get('category','Other')}</span></td><td class="py-3 px-4">{p['price']:,} XAF</td><td class="py-3 px-4 text-xs">{disc_str}</td><td class="py-3 px-4 text-xs">{tags_str}</td><td class="py-3 px-4 font-medium {sc}">{s}</td><td class="py-3 px-4"><a href="/admin/products/edit/{p['id']}" class="text-blue-600 mr-2 text-xs">Edit</a><a href="/admin/products/{p['id']}/barcode" class="text-purple-600 mr-2 text-xs">🏷️</a><a href="/admin/products/delete/{p['id']}" class="text-red-600 text-xs" onclick="return confirm('Delete?')">Del</a></td></tr>'''
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Products</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Products")}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between mb-4"><h2 class="text-xl font-semibold">Products ({len(products)})</h2><div class="flex gap-2"><a href="/admin/products/bulk" class="bg-blue-600 text-white px-4 py-2 rounded text-sm">CSV Bulk</a><a href="/admin/products/add" class="	bg-black text-white px-4 py-2 rounded">+ Add</a></div></div><div class="bg-white rounded-lg shadow overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Img</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Name</th><th class="py-3 px-4">Cat</th><th class="py-3 px-4">Price</th><th class="py-3 px-4">Discount</th><th class="py-3 px-4">Tags</th><th class="py-3 px-4">Stock</th><th class="py-3 px-4">Actions</th></tr></thead><tbody>{rows or '<tr><td colspan="9" class="py-4 text-center text-gray-400">No products</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/products/add')
def admin_add_product_form():
    if not is_admin(): return redirect('/admin')
    cat_opts = "".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    cdata = json.dumps({c:{"attrs":d["attributes"],"variants":d["variant_fields"]} for c,d in CATEGORIES.items()})
    tag_checkboxes = "".join([f'<label class="text-xs mr-2"><input type="checkbox" name="tag_{t}" value="1" class="mr-1">{t}</label>' for t in SPECIAL_TAGS])
    html = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Add Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">''' + admin_header("Products") + '''<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Product</h2><form method="POST" action="/admin/products/add" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Category *</label><select name="category" required class="w-full border rounded px-3 py-2 mb-3" id="cat-select" onchange="showFields()"><option value="">-- Select --</option>''' + cat_opts + '''</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Base Price (XAF) *</label><input type="number" name="price" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Discount Type</label><select name="discount_type" class="w-full border rounded px-3 py-2 mb-2"><option value="None">None</option><option value="Percentage">Percentage (%)</option><option value="Fixed Amount">Fixed Amount (XAF)</option></select><label class="block mb-1 text-sm">Discount Value</label><input type="number" name="discount_value" value="0" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Tags</label><div class="flex flex-wrap mb-3">''' + tag_checkboxes + '''</div><label class="block mb-1 text-sm">Images (up to 5)</label><input type="file" name="image_1" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_2" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_3" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_4" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_5" accept="image/*" class="w-full border rounded px-3 py-2 mb-3"><p class="text-xs text-gray-400 mb-3">First image is the main one.</p><div id="variant-area" class="mb-4 border rounded p-3 bg-gray-50"><p class="text-sm text-gray-400">Select a category to add variants</p></div><div id="attributes-area" class="mb-4"><p class="text-sm text-gray-400">Select a category for attributes</p></div><button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full hover:bg-gray-800">Add Product</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main><script>var cd=''' + cdata + ''';var vc=0;var cvf=[];function showFields(){var cat=document.getElementById("cat-select").value;var va=document.getElementById("variant-area");var aa=document.getElementById("attributes-area");var d=cd[cat];if(!d){va.innerHTML='<p class="text-sm text-gray-400">Select a category first</p>';aa.innerHTML='<p class="text-sm text-gray-400">Select a category first</p>';return;}var ah='<h3 class="font-semibold text-sm mb-2">Attributes</h3>';d.attrs.forEach(function(x){ah+='<label class="block mb-1 text-sm">'+x+'</label><input type="text" name="attr_'+x+'" class="w-full border rounded px-3 py-2 mb-2">';});aa.innerHTML=ah;if(d.variants.length>0){cvf=d.variants;var vh='<h3 class="font-semibold text-sm mb-2">Variants</h3><div id="variant-list"></div><button type="button" onclick="addVariant()" class="mt-2 text-yellow-500 text-sm border 	border-yellow-500 px-3 py-1 rounded hover:bg-gray-800 hover:text-yellow-400">+ Add Variant</button>';va.innerHTML=vh;vc=0;addVariant();}else{va.innerHTML='<p class="text-sm text-gray-400">No variants for this category</p>';}}function addVariant(){if(cvf.length===0)return;vc++;var idx=vc;var h='<div class="border rounded p-2 mb-2 bg-white" id="var-'+idx+'"><p class="text-xs font-semibold mb-1">Variant #'+idx+'</p>';cvf.forEach(function(f){h+='<label class="block mb-1 text-xs">'+f+'</label><input type="text" name="var_'+idx+'_'+f+'" class="w-full border rounded px-2 py-1 mb-1 text-sm">';});h+='<label class="block mb-1 text-xs">Price (blank=base)</label><input type="number" name="var_'+idx+'_price" class="w-full border rounded px-2 py-1 mb-1 text-sm" min="0">';h+='<button type="button" onclick="document.getElementById(\\'var-'+idx+'\\').remove()" class="text-red-500 text-xs mt-1">Remove</button></div>';document.getElementById("variant-list").insertAdjacentHTML("beforeend",h);}</script></body></html>'''
    return html

@app.route('/admin/products/add', methods=['POST'])
def admin_add_product():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    nid = max([p['id'] for p in products], default=0) + 1
    cat = request.form.get('category','Other')
    attrs = {k:request.form.get(f'attr_{k}','') for k in CATEGORIES.get(cat,{}).get('attributes',[])}
    images = []
    for i in range(1, MAX_IMAGES+1):
        f = request.files.get(f'image_{i}')
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f"{nid}_{i}_{int(time.time())}_{f.filename}")
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            images.append(f"uploads/{fn}")
    vfields = CATEGORIES.get(cat,{}).get('variant_fields',[])
    variants = []
    bp = int(request.form.get('price',0))
    if vfields:
        for key in request.form:
            if key.startswith('var_') and key.endswith(f'_{vfields[0]}'):
                idx = key.split('_')[1]
                vattrs = {vf:request.form.get(f'var_{idx}_{vf}','') for vf in vfields}
                vp = request.form.get(f'var_{idx}_price','').strip()
                vprice = int(vp) if vp else bp
                vkey = "-".join([vattrs[vf] for vf in vfields if vattrs.get(vf)])
                if vkey: variants.append({"key":vkey,"sku":generate_sku(cat,nid,vkey),"attrs":vattrs,"price":vprice})
    products.append({
        "id":nid,"sku":generate_sku(cat,nid),"name":request.form.get('name'),
        "description":request.form.get('description',''),"price":bp,
        "discount_type":request.form.get('discount_type','None'),
        "discount_value":int(request.form.get('discount_value',0)),
        "tags":[t for t in SPECIAL_TAGS if request.form.get(f'tag_{t}')],
        "images":images,"category":cat,"attributes":attrs,"variants":variants
    })
    save_products(products)
    return redirect('/admin/products')

@app.route('/admin/products/edit/<int:pid>')
def admin_edit_product_form(pid):
    if not is_admin(): return redirect('/admin')
    p = get_product_by_id(pid)
    if not p: return redirect('/admin/products')
    cat_opts = "".join([f'<option value="{c}" {"selected" if c==p.get("category") else ""}>{c}</option>' for c in CATEGORIES])
    attrs_html = "".join([f'<label class="block mb-1 text-sm">{k}</label><input type="text" name="attr_{k}" value="{v}" class="w-full border rounded px-3 py-2 mb-2">' for k,v in p.get('attributes',{}).items()])
    imgs = p.get('images',[])
    ih = f'<img src="/{imgs[0]}" class="w-32 h-32 object-cover rounded mb-2">' if imgs else '<span class="text-5xl">📷</span>'
    dt_opts = "".join([f'<option value="{d}" {"selected" if d==p.get("discount_type","None") else ""}>{d}</option>' for d in ["None","Percentage","Fixed Amount"]])
    tag_checks = "".join([f'<label class="text-xs mr-2"><input type="checkbox" name="tag_{t}" value="1" class="mr-1" {"checked" if t in p.get("tags",[]) else ""}>{t}</label>' for t in SPECIAL_TAGS])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Edit Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Products")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Product</h2><form method="POST" action="/admin/products/edit/{pid}" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6">{ih}<p class="text-xs text-gray-500 mb-3">SKU: <strong>{p.get("sku")}</strong></p><label class="block mb-1 text-sm">Category</label><select name="category" class="w-full border rounded px-3 py-2 mb-3">{cat_opts}</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required value="{p["name"]}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3">{p["description"]}</textarea><label class="block mb-1 text-sm">Base Price *</label><input type="number" name="price" required value="{p["price"]}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Discount Type</label><select name="discount_type" class="w-full border rounded px-3 py-2 mb-2">{dt_opts}</select><label class="block mb-1 text-sm">Discount Value</label><input type="number" name="discount_value" value="{p.get("discount_value",0)}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Tags</label><div class="flex flex-wrap mb-3">{tag_checks}</div><label class="block mb-1 text-sm">Add More Images</label><input type="file" name="image_1" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_2" accept="image/*" class="w-full border rounded px-3 py-2 mb-3"><div id="attributes-area" class="mb-4"><h3 class="font-semibold text-sm mb-2">Attributes</h3>{attrs_html}</div><button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full hover:bg-gray-800">Update</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/products/edit/<int:pid>', methods=['POST'])
def admin_edit_product(pid):
    if not is_admin(): return redirect('/admin')
    products = load_products()
    for p in products:
        if p['id']==pid:
            cat = request.form.get('category',p.get('category','Other'))
            p['category'] = cat
            p['attributes'] = {k:request.form.get(f'attr_{k}','') for k in CATEGORIES.get(cat,{}).get('attributes',[])}
            p['name'] = request.form.get('name')
            p['description'] = request.form.get('description','')
            p['price'] = int(request.form.get('price',0))
            p['sku'] = generate_sku(cat,pid)
            p['discount_type'] = request.form.get('discount_type', p.get('discount_type','None'))
            p['discount_value'] = int(request.form.get('discount_value', p.get('discount_value',0)))
            p['tags'] = [t for t in SPECIAL_TAGS if request.form.get(f'tag_{t}')]
            imgs = p.get('images',[])
            for i in range(1,3):
                f = request.files.get(f'image_{i}')
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"{pid}_extra_{i}_{int(time.time())}_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    imgs.append(f"uploads/{fn}")
            p['images'] = imgs[:MAX_IMAGES]
            break
    save_products(products)
    return redirect('/admin/products')

@app.route('/admin/products/delete/<int:pid>')
def admin_delete_product(pid):
    if not is_admin(): return redirect('/admin')
    save_products([p for p in load_products() if p['id']!=pid])
    return redirect('/admin/products')

# ─── CSV Bulk Upload ───
@app.route('/admin/products/template')
def download_template():
    if not is_admin(): return redirect('/admin')
    csv_content = "name,category,description,base_price,image_url,discount_type,discount_value,tags,brand,style,size,color,variant_price\n"
    csv_content += 'CK Jean,Men\'s Wear,Regular fit blue jeans,15000,https://example.com/jean.jpg,Percentage,10,Deal,Calvin Klein,Regular,"32,34,36,38","Blue,Brown","15000,15000,14000,14000"\n'
    csv_content += 'Summer Dress,Women\'s Wear,Light floral dress,12000,https://example.com/dress.jpg,None,0,New Arrival,Zara,Casual,"S,M,L","Red,White,Black","12000,12000,12000"\n'
    from flask import Response
    return Response(csv_content, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=nash_fashion_template.csv"})

@app.route('/admin/products/bulk', methods=['GET', 'POST'])
def admin_bulk_upload():
    if not is_admin(): return redirect('/admin')
    result = ""
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename or not file.filename.endswith('.csv'):
            result = '<p class="text-red-500 text-sm">Please select a valid CSV file.</p>'
        else:
            import io, csv
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)
            products = load_products()
            next_id = max([p['id'] for p in products], default=0) + 1
            created = 0; errors = []
            for row_num, row in enumerate(reader, start=2):
                name = row.get('name','').strip()
                category = row.get('category','').strip()
                bp_str = row.get('base_price','0').strip()
                if not name or category not in CATEGORIES: errors.append(f'Row {row_num}: Invalid name/category'); continue
                try: bp = int(bp_str)
                except: errors.append(f'Row {row_num}: Invalid price'); continue
                attrs = {k:row.get(k.lower(),'').strip() for k in CATEGORIES[category]['attributes']}
                vfields = CATEGORIES[category]['variant_fields']
                sizes_str = row.get('size','').strip(); colors_str = row.get('color','').strip(); vp_str = row.get('variant_price','').strip()
                variants = []
                if vfields and sizes_str:
                    sizes = [s.strip() for s in sizes_str.split(',') if s.strip()]
                    colors = [c.strip() for c in colors_str.split(',') if c.strip()] if 'Color' in vfields else ['']
                    vprices = [int(p.strip()) for p in vp_str.split(',') if p.strip()] if vp_str else []
                    vi = 0
                    for size in sizes:
                        for color in colors:
                            vattrs = {}
                            if 'Size' in vfields: vattrs['Size'] = size
                            if 'Color' in vfields and color: vattrs['Color'] = color
                            vkey = "-".join([v for v in [size, color] if v])
                            vprice = vprices[vi] if vi < len(vprices) else bp
                            variants.append({"key":vkey,"sku":generate_sku(category,next_id,vkey),"attrs":vattrs,"price":vprice})
                            vi += 1
                tags_str = row.get('tags','').strip()
                tags = [t.strip() for t in tags_str.split(',') if t.strip() in SPECIAL_TAGS] if tags_str else []
                products.append({
                    "id":next_id,"sku":generate_sku(category,next_id),"name":name,
                    "description":row.get('description','').strip(),"price":bp,
                    "discount_type":row.get('discount_type','None').strip(),
                    "discount_value":int(row.get('discount_value',0)),
                    "tags":tags,
                    "images":[row.get('image_url','').strip()] if row.get('image_url','').strip() else [],
                    "category":category,"attributes":attrs,"variants":variants
                })
                next_id += 1; created += 1
            save_products(products)
            result = f'<p class="text-green-600 font-medium">✅ {created} products created!</p>'
            if errors: result += '<div class="text-red-500 text-sm mt-2">' + '<br>'.join(errors) + '</div>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Bulk Upload</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Products")}<main class="max-w-2xl mx-auto p-4"><a href="/admin/products" class="text-yellow-500 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">CSV Bulk Upload</h2><div class="bg-white rounded-lg shadow p-6 mb-4"><h3 class="font-semibold mb-2">Step 1: Download Template</h3><a href="/admin/products/template" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm">Download Template</a></div><div class="bg-white rounded-lg shadow p-6 mb-4"><h3 class="font-semibold mb-2">Step 2: Upload CSV</h3><form method="POST" enctype="multipart/form-data"><input type="file" name="csv_file" accept=".csv" required class="w-full border rounded px-3 py-2 mb-3"><button type="submit" class="	bg-black text-white px-6 py-2 rounded hover:bg-gray-800">Upload & Import</button></form></div>{result}</main></body></html>'''


# ─── Orders (with RTO/CR) ───
@app.route('/admin/orders')
def admin_orders():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    rows = ""
    for idx, o in enumerate(reversed(orders)):
        ri = len(orders)-1-idx
        sc_map = {"Paid":"rose","Confirmed":"blue","Packed":"indigo","Shipped":"yellow","Delivered":"green","RTO":"orange","CR":"red","Cancelled":"gray"}
        sc = sc_map.get(o['status'],"rose")
        rows += f'<tr class="border-b"><td class="py-3 px-4 text-xs">{o["ref"]}</td><td class="py-3 px-4">{o["name"]}</td><td class="py-3 px-4">{o["phone"]}</td><td class="py-3 px-4">{o["total"]:,}</td><td class="py-3 px-4">{o.get("delivery_zone","")}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{o["status"]}</span></td><td class="py-3 px-4 text-xs">{o["date"]}</td><td class="py-3 px-4"><a href="/admin/orders/{ri}" class="text-yellow-500 text-xs mr-2">View</a><a href="/admin/orders/{ri}/delete" class="text-red-600 text-xs" onclick="return confirm(\'Delete this order permanently?\')">Del</a></td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Orders</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Orders")}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Orders ({len(orders)})</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Ref</th><th class="py-3 px-4">Customer</th><th class="py-3 px-4">Phone</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Zone</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Date</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="8" class="py-4 text-center text-gray-400">No orders</td></tr>'}</tbody></table></div></main></body></html>'''
def get_order_actions(current_status, oi):
    actions = ""
    orders = load_orders()
    o = None
    if 0 <= oi < len(orders):
        o = orders[oi]
    disp = {}
    if o:
        disp = o.get('dispatcher', {})
    disp_assigned = True if disp.get('name') else False
    
    workflow = {
        "Paid": ("Confirm Order", "Confirmed", "bg-blue-600 hover:bg-blue-700"),
        "Confirmed": ("Pack Order", "Packed", "bg-indigo-600 hover:bg-indigo-700"),
        "Packed": ("Assign Dispatcher", "Dispatcher Assigned", "bg-purple-600 hover:bg-purple-700") if not disp_assigned else ("Ship Order", "Shipped", "bg-yellow-600 hover:bg-yellow-700"),
        "Dispatcher Assigned": ("Ship Order", "Shipped", "bg-yellow-600 hover:bg-yellow-700"),
        "Shipped": ("Mark Delivered", "Delivered", "bg-green-600 hover:bg-green-700"),
    }
    
    if current_status in workflow:
        label, next_status, color = workflow[current_status]
        actions += f'<form method="POST" action="/admin/orders/{oi}/update" class="inline"><input type="hidden" name="status" value="{next_status}"><button type="submit" class="{color} text-white px-4 py-2 rounded text-sm">{label}</button></form> '
    
    # RTO - available when Shipped
    if current_status == "Shipped":
        actions += f'<form method="POST" action="/admin/orders/{oi}/update" class="inline"><input type="hidden" name="status" value="RTO"><button type="submit" class="bg-orange-600 text-white px-4 py-2 rounded text-sm">RTO - Return to Origin</button></form> '
    
    # CR - available when Delivered
    if current_status == "Delivered":
        actions += f'<form method="POST" action="/admin/orders/{oi}/update" class="inline"><input type="hidden" name="status" value="CR"><button type="submit" class="bg-red-600 text-white px-4 py-2 rounded text-sm">CR - Customer Return</button></form> '
    
    # Cancel - only at early stages
    if current_status in ["Paid", "Confirmed"]:
        actions += f'<form method="POST" action="/admin/orders/{oi}/update" class="inline"><input type="hidden" name="status" value="Cancelled"><button type="submit" class="bg-gray-600 text-white px-4 py-2 rounded text-sm">Cancel Order</button></form> '
    
    if not actions:
        actions = '<p class="text-gray-500 text-sm">No further actions available for this order.</p>'
    
    return actions

@app.route('/admin/orders/<int:oi>')
def admin_order_detail(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if oi<0 or oi>=len(orders): return redirect('/admin/orders')
    o = orders[oi]
    items = "".join([f'<tr class="border-b"><td class="py-2 text-xs font-mono">{i.get("sku","N/A")}</td><td class="py-2">{i["name"]}</td><td class="py-2">{i["qty"]}</td><td class="py-2">{i["price"]:,}</td><td class="py-2">{i["subtotal"]:,}</td></tr>' for i in o['items']])
    cs = o.get('status','Paid')
    ri = o.get('return_info',{})
    disp = o.get('dispatcher',{})
    
    # Pre-build dynamic parts
    delivery_info = f'<p class="text-xs text-gray-500">Delivery Zone</p><p>{o.get("delivery_zone","")} ({o.get("delivery_cost",0):,} XAF)</p>'
    actions_html = get_order_actions(cs, oi)
    
    # Dispatcher assigned info
    disp_assigned = ""
    if disp.get('name'):
        disp_assigned = f'<div class="mt-3 bg-green-50 border border-green-200 rounded p-3"><h4 class="text-sm font-semibold mb-1">🛵 Dispatcher Assigned</h4><p class="text-sm">Name: <strong>{disp["name"]}</strong></p><p class="text-sm">Plate: <strong>{disp["plate"]}</strong></p><p class="text-sm">Phone: <strong>{disp["phone"]}</strong></p></div>'
    
    # Dispatcher form visibility
    disp_visible = "block" if cs == 'Packed' and not disp.get('name') else "none"
    rto_visible = "block" if cs == 'RTO' else "none"
    cr_visible = "block" if cs == 'CR' else "none"
    
    html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Order {o["ref"]}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Orders")}<main class="max-w-3xl mx-auto p-4"><a href="/admin/orders" class="text-yellow-500 text-sm">&larr; Back</a>
<div class="bg-white rounded-lg shadow p-6 my-4">
<div class="flex justify-between mb-4"><div><h2 class="text-xl font-bold">{o["ref"]}</h2><p class="text-gray-500 text-sm">{o["date"]}</p></div><span class="bg-black text-yellow-400 px-3 py-1 rounded text-sm">{o["status"]}</span></div>
<div class="grid grid-cols-2 gap-4 mb-4"><div><p class="text-xs text-gray-500">Customer</p><p class="font-medium">{o["name"]}</p></div><div><p class="text-xs text-gray-500">Phone</p><p>{o["phone"]}</p></div><div><p class="text-xs text-gray-500">Payment</p><p>{o["payment_method"]}</p></div><div>{delivery_info}</div></div>
{disp_assigned}
<h3 class="font-semibold mb-2">Items</h3>
<table class="w-full text-sm mb-4"><thead><tr class="border-b"><th class="py-2 text-left">SKU</th><th class="py-2 text-left">Item</th><th class="py-2">Qty</th><th class="py-2">Price</th><th class="py-2">Subtotal</th></tr></thead><tbody>{items}</tbody></table>
<div class="text-right"><p class="text-sm">Subtotal: {o.get("subtotal",o["total"]):,} XAF</p><p class="text-sm">Delivery: {o.get("delivery_cost",0):,} XAF</p><p class="text-xl font-bold text-yellow-500">Total: {o["total"]:,} XAF</p></div>
</div>

<div class="bg-white rounded-lg shadow p-6 mb-4"><h3 class="font-semibold mb-3">Order Actions</h3><div class="flex flex-wrap gap-2">{actions_html}</div></div>

<div id="dispatcher-form" class="bg-white rounded-lg shadow p-6 mb-4" style="display:{disp_visible}">
<h3 class="font-semibold mb-3">🛵 Assign Dispatcher</h3>
<form method="POST" action="/admin/orders/{oi}/dispatcher" enctype="multipart/form-data">
<label class="block mb-1 text-sm">Dispatcher Name *</label>
<input type="text" name="disp_name" id="disp_name" value="{disp.get('name','')}" required class="w-full border rounded px-3 py-2 mb-3">
<label class="block mb-1 text-sm">Phone Number *</label>
<input type="tel" name="disp_phone" id="disp_phone" value="{disp.get('phone','')}" required class="w-full border rounded px-3 py-2 mb-3" onblur="checkDispatcher()">
<label class="block mb-1 text-sm">Bike Plate Number *</label>
<input type="text" name="disp_plate" id="disp_plate" value="{disp.get('plate','')}" required class="w-full border rounded px-3 py-2 mb-3" onblur="checkDispatcher()">
<div id="id-upload-section">
<label class="block mb-1 text-sm">ID Card - Front</label>
<input type="file" name="id_front" accept="image/*" capture="environment" class="w-full border rounded px-3 py-2 mb-2 text-sm">
<label class="block mb-1 text-sm">ID Card - Back</label>
<input type="file" name="id_back" accept="image/*" capture="environment" class="w-full border rounded px-3 py-2 mb-2 text-sm">
</div>
<div id="dispatcher-status" class="text-sm mb-3"></div>
<label class="block mb-1 text-sm">Dispatcher Pay (XAF) *</label>
<input type="number" name="disp_pay" value="{disp.get('pay',0)}" required class="w-full border rounded px-3 py-2 mb-3">
<button type="submit" class="bg-green-600 text-white px-6 py-2 rounded w-full hover:bg-green-700">✅ Assign Dispatcher</button>
</form></div>

<div id="rto-form" class="bg-white rounded-lg shadow p-6 mb-4" style="display:{rto_visible}"><h3 class="font-semibold mb-3">RTO Details</h3><form method="POST" action="/admin/orders/{oi}/return"><input type="hidden" name="return_type" value="RTO"><label class="block mb-1 text-sm">Reason</label><select name="reason" class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option><option value="Customer not available" {"selected" if ri.get('reason')=='Customer not available' else ""}>Customer not available</option><option value="Wrong address" {"selected" if ri.get('reason')=='Wrong address' else ""}>Wrong address</option><option value="Customer refused" {"selected" if ri.get('reason')=='Customer refused' else ""}>Customer refused delivery</option><option value="Address not found" {"selected" if ri.get('reason')=='Address not found' else ""}>Address not found</option></select><label class="block mb-1 text-sm">Notes</label><textarea name="notes" rows="2" class="w-full border rounded px-3 py-2 mb-3">{ri.get('notes','')}</textarea><button type="submit" class="bg-orange-600 text-white px-6 py-2 rounded w-full">Save</button></form></div>

<div id="cr-form" class="bg-white rounded-lg shadow p-6 mb-4" style="display:{cr_visible}"><h3 class="font-semibold mb-3">CR Details</h3><form method="POST" action="/admin/orders/{oi}/return"><input type="hidden" name="return_type" value="CR"><label class="block mb-1 text-sm">Reason</label><select name="reason" class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option><option value="Wrong size" {"selected" if ri.get('reason')=='Wrong size' else ""}>Wrong size</option><option value="Damaged" {"selected" if ri.get('reason')=='Damaged' else ""}>Damaged product</option><option value="Not as described" {"selected" if ri.get('reason')=='Not as described' else ""}>Not as described</option><option value="Changed mind" {"selected" if ri.get('reason')=='Changed mind' else ""}>Changed mind</option></select><label class="block mb-1 text-sm">Package Condition</label><select name="package_condition" class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option><option value="Intact" {"selected" if ri.get('package_condition')=='Intact' else ""}>Intact</option><option value="Opened" {"selected" if ri.get('package_condition')=='Opened' else ""}>Opened</option><option value="Damaged" {"selected" if ri.get('package_condition')=='Damaged' else ""}>Damaged</option></select><label class="block mb-1 text-sm">Product Condition</label><select name="product_condition" class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option><option value="New/Unused" {"selected" if ri.get('product_condition')=='New/Unused' else ""}>New/Unused</option><option value="Used" {"selected" if ri.get('product_condition')=='Used' else ""}>Used</option><option value="Damaged" {"selected" if ri.get('product_condition')=='Damaged' else ""}>Damaged</option></select><label class="block mb-1 text-sm">Resolution</label><select name="resolution" class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option><option value="Refund" {"selected" if ri.get('resolution')=='Refund' else ""}>Refund</option><option value="Replacement" {"selected" if ri.get('resolution')=='Replacement' else ""}>Replacement</option></select><label class="block mb-1 text-sm">Refund Channel</label><input type="text" name="refund_channel" value="{ri.get('refund_channel','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Notes</label><textarea name="notes" rows="2" class="w-full border rounded px-3 py-2 mb-4">{ri.get('notes','')}</textarea><button type="submit" class="bg-blue-600 text-white px-6 py-2 rounded w-full">Save</button></form></div>

<div class="text-center mt-4"><a href="/admin/orders/{oi}/receipt" class="text-green-600 underline text-sm">PDF Receipt</a></div>
</main>
<script>
var dispatchers = {{}};
function checkDispatcher() {{
    var phone = document.getElementById('disp_phone').value;
    var plate = document.getElementById('disp_plate').value;
    if (phone && plate) {{
        fetch('/admin/dispatcher/check?phone=' + encodeURIComponent(phone) + '&plate=' + encodeURIComponent(plate))
        .then(r => r.json())
        .then(data => {{
            if (data.found) {{
                document.getElementById('disp_name').value = data.name;
                document.getElementById('id-upload-section').style.display = 'none';
                document.getElementById('dispatcher-status').innerHTML = '<span class="text-green-600">✅ Returning dispatcher — ID verified</span>';
            }} else {{
                document.getElementById('id-upload-section').style.display = 'block';
                document.getElementById('dispatcher-status').innerHTML = '<span class="text-orange-500">🆕 New dispatcher — ID required</span>';
            }}
        }});
    }}
}}
</script></body></html>'''
    return html
@app.route('/admin/orders/<int:oi>/update', methods=['POST'])
def admin_update_order(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0<=oi<len(orders):
        orders[oi]['status'] = request.form.get('status','Paid')
        save_orders(orders)
        # Send receipt if status changed to Shipped
        if request.form.get('status') == 'Shipped':
            try:
                send_whatsapp_receipt(orders[oi]['phone'], orders[oi])
            except:
                pass
    return redirect(f'/admin/orders/{oi}')

@app.route('/admin/orders/<int:oi>/return', methods=['POST'])
def admin_update_return(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0<=oi<len(orders):
        orders[oi]['return_info'] = {
            "type":request.form.get('return_type','CR'),"reason":request.form.get('reason',''),
            "package_condition":request.form.get('package_condition',''),"product_condition":request.form.get('product_condition',''),
            "resolution":request.form.get('resolution',''),"refund_channel":request.form.get('refund_channel',''),
            "refund_status":"Pending" if request.form.get('resolution')=='Refund' else '',
            "notes":request.form.get('notes','')
        }
        save_orders(orders)
    return redirect(f'/admin/orders/{oi}')
@app.route('/admin/orders/<int:oi>/delete')
def admin_delete_order(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0<=oi<len(orders):
        orders.pop(oi)
        save_orders(orders)
    return redirect('/admin/orders')

@app.route('/admin/orders/<int:oi>/dispatcher', methods=['POST'])
def admin_update_dispatcher(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0<=oi<len(orders):
        name = request.form.get('disp_name','')
        phone = request.form.get('disp_phone','')
        plate = request.form.get('disp_plate','')
        pay = int(request.form.get('disp_pay', 0))
        
        existing = find_dispatcher(phone, plate)
        id_front = ''
        id_back = ''
        
        if not existing:
            dispatchers = load_dispatchers()
            if 'id_front' in request.files:
                f = request.files['id_front']
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"disp_{int(time.time())}_front_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    id_front = f"uploads/{fn}"
            if 'id_back' in request.files:
                f = request.files['id_back']
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"disp_{int(time.time())}_back_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    id_back = f"uploads/{fn}"
            dispatchers.append({
                "name": name,
                "phone": phone,
                "plate": plate,
                "id_front": id_front,
                "id_back": id_back
            })
            save_dispatchers(dispatchers)
        
        orders[oi]['dispatcher'] = {
            "name": name,
            "phone": phone,
            "plate": plate,
            "pay": pay,
            "id_img": existing.get('id_front','') if existing else id_front
        }
        save_orders(orders)
    return redirect(f'/admin/orders/{oi}')
        
        # Save to dispatchers database
    existing = find_dispatcher(phone, plate)
    if not existing:
            dispatchers = load_dispatchers()
            # Handle ID images
            id_front = ''
            id_back = ''
            if 'id_front' in request.files:
                f = request.files['id_front']
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"disp_{int(time.time())}_front_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    id_front = f"uploads/{fn}"
            if 'id_back' in request.files:
                f = request.files['id_back']
                if f and f.filename and allowed_file(f.filename):
                    fn = secure_filename(f"disp_{int(time.time())}_back_{f.filename}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    id_back = f"uploads/{fn}"
            dispatchers.append({
                "name": name, "phone": phone, "plate": plate,
                "id_front": id_front, "id_back": id_back
            })
            save_dispatchers(dispatchers)
        
        # Assign to order
    orders[oi]['dispatcher'] = {
            "name": name, "phone": phone, "plate": plate,
            "id_img": existing.get('id_front','') if existing else id_front
        }
    save_orders(orders)
    return redirect(f'/admin/orders/{oi}')

@app.route('/admin/orders/<int:oi>/receipt')
def order_receipt(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if oi<0 or oi>=len(orders): return redirect('/admin/orders')
    o = orders[oi]
    ir = "".join([f'<tr><td>{i["name"]}</td><td>{i["qty"]}</td><td>{i["price"]:,} XAF</td><td>{i["subtotal"]:,} XAF</td></tr>' for i in o['items']])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Receipt</title><style>body{{font-family:Arial;padding:20px;max-width:600px;margin:auto}}h1{{color:#e11d48}}.header{{border-bottom:2px solid #e11d48;padding-bottom:10px;margin-bottom:20px}}table{{width:100%;border-collapse:collapse}}th,td{{border-bottom:1px solid #ddd;padding:8px;text-align:left}}.total{{font-size:18px;font-weight:bold;text-align:right}}@media print{{.print-btn{{display:none}}}}</style></head><body><button class="print-btn" onclick="window.print()" style="background:#e11d48;color:white;padding:10px 20px;border:none;cursor:pointer;border-radius:5px;margin-bottom:20px">Print</button><div class="header"><h1>{STORE_NAME}</h1>{STORE_LOGO_TEXT} · Cosmetics · Appliances</p></div><h2>Order Receipt</h2><p><strong>Ref:</strong> {o["ref"]}</p><p><strong>Date:</strong> {o["date"]}</p><p><strong>Customer:</strong> {o["name"]}</p><p><strong>Phone:</strong> {o["phone"]}</p><p><strong>Payment:</strong> {o["payment_method"]}</p><p><strong>Delivery:</strong> {o.get("delivery_zone","")} ({o.get("delivery_cost",0):,} XAF)</p><h3>Items</h3><table><thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Subtotal</th></tr></thead><tbody>{ir}</tbody></table><p style="text-align:right">Subtotal: {o.get("subtotal",o["total"]):,} XAF</p><p style="text-align:right">Delivery: {o.get("delivery_cost",0):,} XAF</p><p class="total">Total: {o["total"]:,} XAF</p><div style="border-top:1px solid #ccc;margin-top:20px;padding-top:10px;font-size:12px;color:#666"><p>Thank you for shopping at {STORE_NAME}!</p><p>📞 WhatsApp: {STORE_WHATSAPP}</p></div></body></html>'''

# ─── Inventory ───
@app.route('/admin/inventory')
def admin_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    rows = ""
    for i in inv:
        prod = get_product_by_id(i['product_id']); pn = prod['name'] if prod else f"#{i['product_id']}"
        sku = prod.get('sku','N/A') if prod else 'N/A'; tc = i['quantity_ordered']*i['unit_cost']; bo = i['quantity_ordered']-i['quantity_received']
        sc = "green" if i['status']=="Received" else ("blue" if i['status']=="In Transit" else "yellow")
        rows += f'<tr class="border-b"><td class="py-3 px-4 text-xs">{i.get("date_purchased","")}</td><td class="py-3 px-4">{pn}</td><td class="py-3 px-4 text-xs font-mono">{sku}</td><td class="py-3 px-4">{i["quantity_ordered"]}</td><td class="py-3 px-4">{i["quantity_received"]}</td><td class="py-3 px-4 text-orange-500">{bo}</td><td class="py-3 px-4">{i["unit_cost"]:,}</td><td class="py-3 px-4">{tc:,}</td><td class="py-3 px-4 text-xs">{i.get("supplier_name","")}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{i["status"]}</span></td><td class="py-3 px-4"><a href="/admin/inventory/edit/{i["id"]}" class="text-blue-600 text-xs mr-2">Edit</a><a href="/admin/inventory/delete/{i["id"]}" class="text-red-600 text-xs" onclick="return confirm(\'Delete?\')">Del</a></td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between mb-4"><h2 class="text-xl font-semibold">Inventory ({len(inv)})</h2><a href="/admin/inventory/add" class="	bg-black text-white px-4 py-2 rounded">+ Add</a></div><div class="bg-white rounded-lg shadow overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Date</th><th class="py-3 px-4">Product</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Ord</th><th class="py-3 px-4">Rec</th><th class="py-3 px-4">Back</th><th class="py-3 px-4">Cost</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Supplier</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="11" class="py-4 text-center text-gray-400">No entries</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/inventory/add')
def admin_add_inventory_form():
    if not is_admin(): return redirect('/admin')
    products = load_products(); popts = ""
    for p in products:
        for v in p.get('variants',[]) or [{"key":"","sku":p.get("sku","N/A")}]:
            vl = " / ".join([f"{k}:{v}" for k,v in v.get('attrs',{}).items()]) if v.get('attrs') else "Base"
            popts += f'<option value="{p["id"]}|{v["key"]}">{p["name"]} — {vl} ({v.get("sku",p["sku"])})</option>'
    sopts = "".join([f'<option value="{s}">{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Add Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Inventory</h2><form method="POST" action="/admin/inventory/add" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product/Variant *</label><select name="product_ref" required class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option>{popts}</select><label class="block mb-1 text-sm">Qty Ordered *</label><input type="number" name="quantity_ordered" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="0" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost *</label><input type="number" name="unit_cost" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full">Add</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/add', methods=['POST'])
def admin_add_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory(); nid = max([i['id'] for i in inv], default=0) + 1
    pref = request.form.get('product_ref','|'); ps, vk = pref.split('|',1) if '|' in pref else (pref,'')
    pid = int(ps) if ps else 0
    inv.append({"id":nid,"product_id":pid,"variant_key":vk,"quantity_ordered":int(request.form.get('quantity_ordered',0)),"quantity_received":int(request.form.get('quantity_received',0)),"unit_cost":int(request.form.get('unit_cost',0)),"date_purchased":request.form.get('date_purchased',''),"date_received":request.form.get('date_received',''),"supplier_name":request.form.get('supplier_name',''),"supplier_phone":request.form.get('supplier_phone',''),"supplier_address":request.form.get('supplier_address',''),"status":request.form.get('status','Ordered')})
    save_inventory(inv); return redirect('/admin/inventory')

@app.route('/admin/inventory/edit/<int:iid>')
def admin_edit_inventory_form(iid):
    if not is_admin(): return redirect('/admin')
    i = next((x for x in load_inventory() if x['id']==iid), None)
    if not i: return redirect('/admin/inventory')
    products = load_products(); popts = ""
    for p in products:
        for v in p.get('variants',[]) or [{"key":"","sku":p.get("sku","N/A")}]:
            sel = 'selected' if p['id']==i['product_id'] and v['key']==i.get('variant_key','') else ''
            vl = " / ".join([f"{k}:{v}" for k,v in v.get('attrs',{}).items()]) if v.get('attrs') else "Base"
            popts += f'<option value="{p["id"]}|{v["key"]}" {sel}>{p["name"]} — {vl}</option>'
    sopts = "".join([f'<option value="{s}" {"selected" if s==i["status"] else ""}>{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Edit Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Inventory</h2><form method="POST" action="/admin/inventory/edit/{iid}" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product</label><select name="product_ref" class="w-full border rounded px-3 py-2 mb-3">{popts}</select><label class="block mb-1 text-sm">Qty Ordered</label><input type="number" name="quantity_ordered" value="{i['quantity_ordered']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="{i['quantity_received']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost</label><input type="number" name="unit_cost" value="{i['unit_cost']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" value="{i.get('date_purchased','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" value="{i.get('date_received','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" value="{i.get('supplier_name','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" value="{i.get('supplier_phone','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3">{i.get('supplier_address','')}</textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full">Update</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/edit/<int:iid>', methods=['POST'])
def admin_edit_inventory(iid):
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    for i in inv:
        if i['id']==iid:
            pref = request.form.get('product_ref','|'); ps, vk = pref.split('|',1) if '|' in pref else (pref,'')
            i['product_id'] = int(ps) if ps else i['product_id']; i['variant_key'] = vk
            for fld in ['quantity_ordered','quantity_received','unit_cost']: i[fld] = int(request.form.get(fld,i[fld]))
            for fld in ['date_purchased','date_received','supplier_name','supplier_phone','supplier_address','status']: i[fld] = request.form.get(fld,i.get(fld,''))
            break
    save_inventory(inv); return redirect('/admin/inventory')

@app.route('/admin/inventory/delete/<int:iid>')
def admin_delete_inventory(iid):
    if not is_admin(): return redirect('/admin')
    save_inventory([i for i in load_inventory() if i['id']!=iid])
    return redirect('/admin/inventory')

# ─── WhatsApp Messaging ───
def send_whatsapp_message(to_number, message):
    """Send a WhatsApp message using the Cloud API"""
    import requests
    url = f"https://graph.facebook.com/v25.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    # For test mode, use the hello_world template with a custom body
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        print(f"WhatsApp response: {result}")
        return result
    except Exception as e:
        print(f"WhatsApp error: {e}")
        return None


def send_whatsapp_receipt(to_number, order):
    """Send order receipt via WhatsApp"""
    import requests
    items_text = "\n".join([f"• {i['name']} x{i['qty']} — {i['subtotal']:,} XAF" for i in order['items']])
    message_body = f"🛍️ *{STORE_NAME} — Order Receipt*\n\n*Ref:* {order['ref']}\n*Date:* {order['date']}\n*Customer:* {order['name']}\n\n📦 *Items:*\n{items_text}\n\n💰 *Subtotal:* {order.get('subtotal', order['total']):,} XAF\n🚚 *Delivery:* {order.get('delivery_cost', 0):,} XAF\n⭐ *Total:* {order['total']:,} XAF\n\nThank you for shopping at {STORE_NAME}! 👗✨"
    
    url = f"https://graph.facebook.com/v25.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        print(f"WhatsApp receipt response: {result}")
        return result
    except Exception as e:
        print(f"WhatsApp error: {e}")
        return None
    finally:
        print(f"WhatsApp API called: to={to_number}, message={message[:50]}...")


def send_whatsapp_receipt(to_number, order):
    """Send order receipt via WhatsApp"""
    items_text = "\n".join([f"• {i['name']} x{i['qty']} — {i['subtotal']:,} XAF" for i in order['items']])
    message = f"""🛍️ *{STORE_NAME} — Order Receipt*

*Ref:* {order['ref']}
*Date:* {order['date']}
*Customer:* {order['name']}

📦 *Items:*
{items_text}

💰 *Subtotal:* {order.get('subtotal', order['total']):,} XAF
🚚 *Delivery:* {order.get('delivery_cost', 0):,} XAF
⭐ *Total:* {order['total']:,} XAF

Thank you for shopping at {STORE_NAME}! 👗✨"""
    return send_whatsapp_message(to_number, message)
# ─── Settings ───
@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not is_admin(): return redirect('/admin')
    settings_file = 'settings.json'
    
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            current = json.load(f)
    else:
        current = {}
    
    store_name = current.get('store_name', STORE_NAME)
    store_whatsapp = current.get('store_whatsapp', STORE_WHATSAPP)
    free_threshold = current.get('free_delivery_threshold', FREE_DELIVERY_THRESHOLD)
    zones = current.get('delivery_zones', DELIVERY_ZONES)
    
    msg = ""
    if request.method == 'POST':
        store_name = request.form.get('store_name', STORE_NAME)
        store_whatsapp = request.form.get('store_whatsapp', STORE_WHATSAPP)
        free_threshold = int(request.form.get('free_threshold', FREE_DELIVERY_THRESHOLD))
        
        zone_names = request.form.getlist('zone_name')
        zone_costs = request.form.getlist('zone_cost')
        zones = {}
        for i in range(len(zone_names)):
            if zone_names[i].strip():
                zones[zone_names[i].strip()] = int(zone_costs[i]) if i < len(zone_costs) else 0
        
        settings = {
            'store_name': store_name,
            'store_whatsapp': store_whatsapp,
            'free_delivery_threshold': free_threshold,
            'delivery_zones': zones
        }
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)
        
        msg = '<p class="text-green-600 font-medium">✅ Settings saved! Restart server to apply.</p>'
    
    zone_rows = ""
    for z, p in zones.items():
        zone_rows += f'<tr class="border-b"><td><input type="text" name="zone_name" value="{z}" class="border rounded px-2 py-1 w-full text-sm"></td><td><input type="number" name="zone_cost" value="{p}" class="border rounded px-2 py-1 w-24 text-sm"></td></tr>'
    
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Settings</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Settings")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Store Settings</h2>{msg}
    <form method="POST" class="bg-white rounded-lg shadow p-6">
    <label class="block mb-1 text-sm">Store Name</label>
    <input type="text" name="store_name" value="{store_name}" class="w-full border rounded px-3 py-2 mb-3">
    <label class="block mb-1 text-sm">WhatsApp Number</label>
    <input type="text" name="store_whatsapp" value="{store_whatsapp}" class="w-full border rounded px-3 py-2 mb-3">
    <label class="block mb-1 text-sm">Free Delivery Threshold (XAF)</label>
    <input type="number" name="free_threshold" value="{free_threshold}" class="w-full border rounded px-3 py-2 mb-4">
    <h3 class="font-semibold mb-2">Delivery Zones</h3>
    <table class="w-full text-sm mb-2"><thead><tr class="border-b"><th class="py-1 text-left">Zone Name</th><th class="py-1 text-left">Cost (XAF)</th></tr></thead><tbody id="zone-table">{zone_rows}</tbody></table>
    <button type="button" onclick="addZone()" class="text-yellow-500 text-sm border 	border-yellow-500 px-3 py-1 rounded mb-4">+ Add Zone</button>
    <button type="submit" class="	bg-black text-white px-6 py-2 rounded w-full hover:bg-gray-800">Save Settings</button>
    </form></main>
    <script>
    function addZone() {{
        var t = document.getElementById('zone-table');
        var r = document.createElement('tr');
        r.className = 'border-b';
        r.innerHTML = '<td><input type="text" name="zone_name" class="border rounded px-2 py-1 w-full text-sm"></td><td><input type="number" name="zone_cost" value="0" class="border rounded px-2 py-1 w-24 text-sm"></td>';
        t.appendChild(r);
    }}
    </script></body></html>'''

@app.route('/admin/dispatcher/check')
def check_dispatcher():
    if not is_admin(): return {'found': False}
    phone = request.args.get('phone','')
    plate = request.args.get('plate','')
    d = find_dispatcher(phone, plate)
    if d:
        return {"found": True, "name": d['name'], "phone": d['phone'], "plate": d['plate']}
    return {"found": False}
# ─── Help / VSOP ───
@app.route('/admin/help')
def admin_help():
    if not is_admin(): return redirect('/admin')
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Help Guide</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Help")}<main class="max-w-4xl mx-auto p-4">
    <h2 class="text-2xl font-bold mb-6">📖 Admin Help Guide — {STORE_NAME}</h2>
    
    <div class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">📋 Table of Contents</h3>
    <ul class="text-sm text-blue-600 space-y-1">
    <li><a href="#dashboard">1. Dashboard Overview</a></li>
    <li><a href="#add-product">2. Adding a Product</a></li>
    <li><a href="#variants">3. Product Variants (Size & Color)</a></li>
    <li><a href="#discounts">4. Discounts & Tags (Deals/Clearance)</a></li>
    <li><a href="#bulk">5. Bulk CSV Upload</a></li>
    <li><a href="#inventory">6. Managing Inventory</a></li>
    <li><a href="#orders">7. Processing Orders</a></li>
    <li><a href="#returns">8. Returns (RTO & CR)</a></li>
    <li><a href="#marketing">9. Marketing & Promotions</a></li>
    <li><a href="#reports">10. Reports</a></li>
    <li><a href="#barcode">11. Barcode Printing</a></li>
    </ul></div>
    
    <div id="dashboard" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">1. 📊 Dashboard Overview</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Dashboard</p>
    <p class="text-sm text-gray-600 mb-2"><strong>What you see:</strong> Today's orders, weekly orders, total revenue, low stock alerts.</p>
    <p class="text-sm text-gray-600 mb-2"><strong>Quick Actions:</strong> Use the Quick Links to jump to Reports, Add Product, or Add Inventory.</p>
    <div class="bg-gray-100 rounded p-3 text-xs text-gray-500 italic">[Screenshot: Dashboard overview]</div>
    </div>
    
    <div id="add-product" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">2. ➕ Adding a Product</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Products → + Add</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1">
    <li>Select a <strong>Category</strong> (e.g., Men's Wear)</li>
    <li>Enter <strong>Product Name</strong> (e.g., CK Jean)</li>
    <li>Add a <strong>Description</strong></li>
    <li>Set the <strong>Base Price</strong> in XAF</li>
    <li>Optionally set a <strong>Discount</strong> (Percentage or Fixed Amount)</li>
    <li>Check <strong>Tags</strong> (Deal, Clearance, New Arrival, etc.)</li>
    <li>Upload <strong>Images</strong> (up to 5, first one is the main image)</li>
    <li>Add <strong>Attributes</strong> (Brand, Style, etc.)</li>
    <li>Click <strong>+ Add Variant</strong> to add sizes/colors</li>
    <li>Click <strong>Add Product</strong></li>
    </ol>
    <div class="bg-gray-100 rounded p-3 text-xs text-gray-500 italic mt-2">[Screenshot: Add Product form filled out]</div>
    </div>
    
    <div id="variants" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">3. 📏 Product Variants (Size & Color)</h3>
    <p class="text-sm text-gray-600 mb-2">Variants let you sell one product in multiple sizes and colors without creating separate products.</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1">
    <li>When adding a product, select a category first</li>
    <li>The <strong>Variants</strong> section appears</li>
    <li>Click <strong>+ Add Variant</strong> for each combination</li>
    <li>Fill in Size, Color, and Price (leave price blank to use base price)</li>
    <li>Example: Size: 32, Color: Blue, Price: 15000</li>
    <li>Add more variants for 34/Blue, 32/Brown, etc.</li>
    </ol>
    <p class="text-sm text-gray-600 mt-2"><strong>Important:</strong> Each variant gets its own SKU and stock tracking.</p>
    <div class="bg-gray-100 rounded p-3 text-xs text-gray-500 italic mt-2">[Screenshot: Variants section with multiple entries]</div>
    </div>
    
    <div id="discounts" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">4. 💰 Discounts & Tags</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Discount Types:</strong></p>
    <ul class="text-sm text-gray-600 list-disc ml-4 space-y-1">
    <li><strong>Percentage:</strong> e.g., 20% off → Discount Value: 20</li>
    <li><strong>Fixed Amount:</strong> e.g., 2000 XAF off → Discount Value: 2000</li>
    </ul>
    <p class="text-sm text-gray-600 mt-2"><strong>Tags:</strong></p>
    <ul class="text-sm text-gray-600 list-disc ml-4 space-y-1">
    <li><strong>Deal:</strong> Appears in the Hot Deals section on homepage</li>
    <li><strong>Clearance:</strong> Appears in Clearance Sale section</li>
    <li><strong>New Arrival / Best Seller:</strong> Visual badges</li>
    </ul>
    <p class="text-sm text-gray-600 mt-2">Apply discounts and tags when adding or editing a product.</p>
    </div>
    
    <div id="bulk" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">5. 📋 Bulk CSV Upload</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Products → CSV Bulk</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1">
    <li>Click <strong>Download Template</strong> to get a CSV file</li>
    <li>Open in Excel or Google Sheets</li>
    <li>Fill in your products (see column guide on the page)</li>
    <li>Save as CSV</li>
    <li>Click <strong>Choose File</strong> → select your CSV</li>
    <li>Click <strong>Upload & Import</strong></li>
    </ol>
    <p class="text-sm text-gray-600 mt-2"><strong>Columns:</strong> name, category, description, base_price, image_url, discount_type, discount_value, tags, brand, style, size, color, variant_price</p>
    </div>
    
    <div id="inventory" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">6. 📦 Managing Inventory</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Inventory → + Add</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1">
    <li>Select the <strong>Product / Variant</strong></li>
    <li>Enter <strong>Quantity Ordered</strong> from supplier</li>
    <li>Enter <strong>Quantity Received</strong> (what actually arrived)</li>
    <li>Enter <strong>Unit Cost</strong> (how much you paid per item)</li>
    <li>Fill in <strong>Supplier details</strong> (name, phone, address)</li>
    <li>Set <strong>Status:</strong> Ordered, In Transit, Received, Partial</li>
    <li>Click <strong>Add</strong></li>
    </ol>
    <p class="text-sm text-gray-600 mt-2"><strong>Stock Level = Received - Sold.</strong> Backorder = Ordered - Received.</p>
    </div>
    
    <div id="orders" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">7. 📋 Processing Orders</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Orders → View</p>
    <p class="text-sm text-gray-600 mb-2"><strong>Order Status Flow:</strong></p>
    <p class="text-sm text-gray-600">Paid → Confirmed → Packed → Shipped → Delivered</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1 mt-2">
    <li>When a new order arrives, status is <strong>Paid</strong></li>
    <li>Review the order → change to <strong>Confirmed</strong></li>
    <li>When packing → <strong>Packed</strong></li>
    <li>When shipped → <strong>Shipped</strong></li>
    <li>After delivery → <strong>Delivered</strong></li>
    </ol>
    <p class="text-sm text-gray-600 mt-2">Click <strong>PDF Receipt</strong> to download/print the order receipt.</p>
    </div>
    
    <div id="returns" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">8. ↩️ Returns (RTO & CR)</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>RTO (Return to Origin):</strong> Delivery failed. Change order status to RTO and fill the RTO form with the failure reason.</p>
    <p class="text-sm text-gray-600 mb-2"><strong>CR (Customer Return):</strong> Customer returned the product. Change status to CR and fill:</p>
    <ul class="text-sm text-gray-600 list-disc ml-4 space-y-1">
    <li>Return Reason</li>
    <li>Package Condition (Intact/Opened/Damaged)</li>
    <li>Product Condition (New/Used/Damaged)</li>
    <li>Resolution: Refund or Replacement</li>
    <li>Refund Channel (e.g., MTN MoMo to 237 6XX XXX XXX)</li>
    </ul>
    </div>
    
    <div id="marketing" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">9. 📢 Marketing & Promotions</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Marketing</p>
    <p class="text-sm text-gray-600">This page shows all your active deals, clearance items, discounted products, and delivery zones in one place. Use it to quickly review your promotions.</p>
    <p class="text-sm text-gray-600 mt-2">To create a promotion: Edit a product → set Discount + check a Tag.</p>
    </div>
    
    <div id="reports" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">10. 📊 Reports</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Reports</p>
    <ul class="text-sm text-gray-600 list-disc ml-4 space-y-1">
    <li><strong>Sales Summary:</strong> Daily, weekly, monthly revenue</li>
    <li><strong>Product Performance:</strong> Best-selling products ranked</li>
    <li><strong>Inventory Status:</strong> Stock levels and total value</li>
    <li><strong>Profit Analysis:</strong> Revenue vs cost per product</li>
    <li><strong>Top Customers:</strong> Customer spending rankings</li>
    </ul>
    </div>
    
    <div id="barcode" class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="text-lg font-semibold mb-2">11. 🏷️ Barcode Printing</h3>
    <p class="text-sm text-gray-600 mb-2"><strong>Path:</strong> Admin → Products → Click 🏷️ on any product</p>
    <ol class="text-sm text-gray-600 list-decimal ml-4 space-y-1">
    <li>Set the number of copies</li>
    <li>Click <strong>Generate</strong></li>
    <li>Click <strong>Print</strong> (or Ctrl+P)</li>
    <li>Scan with any barcode scanner app</li>
    </ol>
    <p class="text-sm text-gray-600 mt-2">Each variant gets its own barcode with unique SKU.</p>
    </div>
    
    <div class="text-center mt-6 mb-10">
    <a href="/admin" class="	bg-black text-white px-6 py-3 rounded-lg hover:bg-gray-800 inline-block">Back to Admin</a>
    </div>
    </main></body></html>'''
# ─── Barcode ───
@app.route('/admin/products/<int:pid>/barcode')
def product_barcode(pid):
    if not is_admin(): return redirect('/admin')
    p = get_product_by_id(pid)
    if not p: return redirect('/admin/products')
    variants = p.get('variants',[]) or [{"key":"","sku":p.get('sku','N/A'),"price":p['price'],"attrs":{}}]
    boxes = ""
    for v in variants:
        sku = v.get('sku',p.get('sku','N/A'))
        label = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v.get('attrs') else "")
        boxes += f'<div class="barcode-box"><p style="font-weight:bold;margin:0 0 5px;font-size:14px;">{label}</p><p style="font-size:12px;color:#666;">SKU: {sku}</p><svg id="bc_{sku}"></svg><p style="font-size:16px;font-weight:bold;color:#e11d48;">{get_discounted_price(v) if v.get("price") else get_discounted_price(p):,} XAF</p></div>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Barcodes</title><script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script><style>@media print{{body{{margin:0}}}}.barcode-box{{border:2px dashed #ccc;padding:20px;text-align:center;display:inline-block;margin:10px;}}</style></head><body style="font-family:Arial;text-align:center;padding:20px;"><div style="margin-bottom:20px;"><p>Barcodes for <strong>{p['name']}</strong></p><label>Copies: <input type="number" id="copies" value="1" min="1" max="100" style="width:60px;"></label><button onclick="location.reload()" style="padding:8px 16px;background:#e11d48;color:white;border:none;border-radius:4px;">Generate</button><button onclick="window.print()" style="padding:8px 16px;background:#16a34a;color:white;border:none;border-radius:4px;">Print</button><a href="/admin/products" style="margin-left:10px;color:#666;">Back</a></div><div id="barcode-area">{boxes}</div><script>document.querySelectorAll('svg[id^="bc_"]').forEach(s=>{{JsBarcode(s,s.id.replace("bc_",""),{{format:"CODE128",width:2,height:60,displayValue:true,fontSize:12,margin:5}});}});</script></body></html>'''

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in',None)
    return redirect('/admin')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)