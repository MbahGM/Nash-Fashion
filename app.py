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
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'store123'
STORE_NAME = "Nash Fashion"
STORE_EMOJI = "👗✨"
MAX_IMAGES = 5

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

CATEGORIES = {
    "Men's Wear": {"attributes": ["Brand", "Style"], "variant_fields": ["Size", "Color"]},
    "Women's Wear": {"attributes": ["Brand", "Style"], "variant_fields": ["Size", "Color"]},
    "Children's Wear": {"attributes": ["Brand", "Age Group"], "variant_fields": ["Size", "Color"]},
    "Accessories": {"attributes": ["Brand", "Type", "Material"], "variant_fields": ["Color"]},
    "Cosmetics": {"attributes": ["Brand", "Type", "Skin Type", "Volume"], "variant_fields": ["Size/Volume"]},
    "Appliances": {"attributes": ["Brand", "Model", "Power", "Capacity", "Warranty"], "variant_fields": ["Model"]},
    "Other": {"attributes": ["Custom Info"], "variant_fields": []}
}

ORDER_STATUSES = ["Paid", "Confirmed", "Shipped", "Delivered", "Cancelled"]
INVENTORY_STATUSES = ["Ordered", "In Transit", "Received", "Partial"]

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

def generate_sku(category, product_id, variant_key=""):
    prefix = ''.join([w[0] for w in category.split()[:2]]).upper()
    return f"{prefix}-{product_id:04d}{'-'+variant_key if variant_key else ''}"

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
        active = "border-rose-600 opacity-100" if idx==0 else "border-gray-300 opacity-60"
        thumbs += f'<img src="/{img}" class="w-16 h-16 object-cover rounded border-2 {active} cursor-pointer" onclick="document.getElementById(\'mainImage\').src=this.src;this.parentElement.querySelectorAll(\'img\').forEach(i=>i.classList.remove(\'border-rose-600\',\'opacity-100\'));this.classList.add(\'border-rose-600\',\'opacity-100\');" alt="{product_name}">'
    return f'<div class="flex gap-2 mt-3 flex-wrap">{thumbs}</div>'

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
        sold_qty = sum(item['qty'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        sold_rev = sum(item['subtotal'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        if sold_qty > 0:
            sales[pid] = {"name": p['name'], "sku": p.get('sku','N/A'), "qty": sold_qty, "revenue": sold_rev, "price": p['price']}
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
            # Get average unit cost from inventory
            costs = [i['unit_cost'] for i in inv if i['product_id']==pid and i['status'] in ['Received','Partial']]
            avg_cost = sum(costs) / len(costs) if costs else 0
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
        sold_qty = sum(item['qty'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        sold_rev = sum(item['subtotal'] for o in orders for item in o.get('items',[]) if item.get('product_id')==pid)
        costs = [i['unit_cost'] for i in inv if i['product_id']==pid and i['status'] in ['Received','Partial']]
        avg_cost = sum(costs) / len(costs) if costs else 0
        profit = sold_rev - (sold_qty * avg_cost)
        margin = (profit / sold_rev * 100) if sold_rev > 0 else 0
        total_profit += profit
        if sold_qty > 0:
            profit_data.append({"name": p['name'], "qty": sold_qty, "revenue": sold_rev, "cost": avg_cost, "profit": profit, "margin": margin})
    return total_profit, sorted(profit_data, key=lambda x: x['profit'], reverse=True)

def get_top_customers():
    orders = load_orders()
    customers = {}
    for o in orders:
        name = o['name']
        if name not in customers:
            customers[name] = {"name": name, "phone": o['phone'], "orders": 0, "total": 0}
        customers[name]['orders'] += 1
        customers[name]['total'] += o['total']
    return sorted(customers.values(), key=lambda x: x['total'], reverse=True)[:20]


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ═══════════════════════════════════
#  CUSTOMER PAGES (unchanged from previous version — abbreviated for length)
# ═══════════════════════════════════

@app.route('/')
def home():
    products = load_products()
    count = cart_count()
    cards = ""
    for p in products:
        imgs = p.get('images',[])
        ih = get_image_html(imgs, "h-48 w-full", p['name'])
        variants = p.get('variants',[])
        total_stock = sum(get_stock_level(p['id'],v.get('key','')) for v in variants) if variants else get_stock_level(p['id'])
        sb = '<p class="text-red-500 text-xs font-medium mt-1">Out of Stock</p>' if total_stock<=0 else (f'<p class="text-orange-500 text-xs font-medium mt-1">Only {total_stock} left</p>' if total_stock<=5 else '')
        prices = [v.get('price',p['price']) for v in variants] if variants else [p['price']]
        pt = f"{min(prices):,} - {max(prices):,} XAF" if min(prices)!=max(prices) else f"{prices[0]:,} XAF"
        ka = " · ".join([f"{k}: {v}" for k,v in p.get('attributes',{}).items() if v]) or ""
        cards += f'''<div class="bg-white rounded-lg shadow p-4 hover:shadow-md transition">{ih}<span class="text-xs bg-rose-100 text-rose-700 px-2 py-1 rounded mt-2 inline-block">{p.get('category','Other')}</span><h3 class="font-semibold text-lg mt-1">{p['name']}</h3><p class="text-gray-400 text-xs font-mono">SKU: {p.get('sku','N/A')}</p><p class="text-gray-500 text-sm mb-1">{p['description']}</p>{"<p class='text-gray-400 text-xs mb-2'>"+ka+"</p>" if ka else ""}<p class="text-rose-600 font-bold text-lg mb-1">{pt}</p>{sb}<div class="flex gap-2 mt-3"><a href="/product/{p['id']}" class="text-rose-600 border border-rose-600 px-4 py-2 rounded flex-1 text-center text-sm hover:bg-rose-50">Details</a></div></div>'''
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({count})</a></nav></header><main class="max-w-6xl mx-auto p-4"><div class="bg-rose-50 border border-rose-200 rounded-lg p-4 mb-6 text-center"><h2 class="text-xl font-semibold text-rose-700">Welcome to {STORE_NAME}</h2><p class="text-rose-500 text-sm">Fashion · Cosmetics · Appliances</p></div><h2 class="text-xl font-semibold mb-4">Our Products</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">{cards or '<p class="text-gray-500 col-span-full text-center py-12">No products yet</p>'}</div></main></body></html>'''


@app.route('/product/<int:pid>')
def product_detail(pid):
    p = get_product_by_id(pid)
    if not p: return redirect('/')
    count = cart_count()
    imgs = p.get('images',[])
    variants = p.get('variants',[])
    vfields = CATEGORIES.get(p.get('category','Other'),{}).get('variant_fields',[])
    vhtml = ""
    vpjs = "{}"
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
            vmap[key] = {"price":v.get('price',p['price']),"stock":get_stock_level(pid,v.get('key','')),"key":v.get('key','')}
        vpjs = json.dumps(vmap)
    if imgs:
        main_img = f'<img src="/{imgs[0]}" id="mainImage" class="w-full md:w-96 h-96 object-cover rounded">'
        gallery = get_gallery_html(imgs, p['name'])
    else:
        main_img = '<div class="bg-gray-200 w-full md:w-96 h-96 rounded flex items-center justify-center text-8xl">📷</div>'
        gallery = ""
    attrs = p.get('attributes',{})
    arows = "".join([f'<tr class="border-b"><td class="py-2 px-4 bg-gray-50 font-medium text-sm">{k}</td><td class="py-2 px-4 text-sm">{v}</td></tr>' for k,v in attrs.items() if v]) or '<tr><td colspan="2" class="py-2 px-4 text-sm text-gray-400">No specifications</td></tr>'
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>{p['name']} — {STORE_NAME}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({count})</a></nav></header><main class="max-w-4xl mx-auto p-4"><a href="/" class="text-rose-600 text-sm mb-2 inline-block">&larr; Back</a><div class="bg-white rounded-lg shadow p-6"><div class="flex flex-col md:flex-row gap-6"><div>{main_img}{gallery}</div><div class="flex-1"><span class="text-xs bg-rose-100 text-rose-700 px-2 py-1 rounded">{p.get('category','Other')}</span><h2 class="text-2xl font-bold mt-2">{p['name']}</h2><p class="text-gray-400 text-sm font-mono">SKU: {p.get('sku','N/A')}</p><p class="text-gray-600 my-3">{p['description']}</p><p class="text-3xl font-bold text-rose-600 mb-2" id="variant-price">{p['price']:,} XAF</p><p class="text-sm mb-2" id="variant-stock"></p>{vhtml}<h3 class="font-semibold mb-2 mt-4">Specifications</h3><table class="w-full border rounded overflow-hidden mb-4"><tbody>{arows}</tbody></table><form method="POST" action="/add-to-cart"><input type="hidden" name="product_id" value="{p['id']}"><input type="hidden" name="variant_key" id="variant-key" value=""><button type="submit" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 w-full" id="add-btn">Add to Cart</button></form></div></div></div></main><script>var vd={vpjs};var vf={json.dumps(vfields)};function updateVariant(){{var s=document.querySelectorAll('.variant-select');var k=[];s.forEach(x=>k.push(x.value));var fk=k.join('|');var d=vd[fk];var pe=document.getElementById('variant-price');var se=document.getElementById('variant-stock');var ki=document.getElementById('variant-key');var b=document.getElementById('add-btn');if(d){{pe.textContent=d.price.toLocaleString()+' XAF';se.textContent='In Stock ('+d.stock+' available)';se.className='text-sm mb-2 text-green-600';ki.value=d.key;b.disabled=d.stock<=0;b.textContent=d.stock<=0?'Out of Stock':'Add to Cart';}}else if(k.every(x=>x!=='')){{b.disabled=true;b.textContent='Unavailable';}}else{{b.disabled=true;}}}}updateVariant();</script></body></html>'''


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
    items = ""
    total = 0
    for ck, qty in cart.items():
        parts = ck.split('|')
        pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = v.get('price',p['price']) if v else p['price']
        st = price * qty; total += st
        imgs = p.get('images',[])
        ih = f'<img src="/{imgs[0]}" class="w-12 h-12 object-cover rounded">' if imgs else '<span class="text-3xl">📷</span>'
        items += f'''<div class="bg-white rounded-lg shadow p-4 flex justify-between items-center mb-3"><div class="flex items-center gap-3">{ih}<div><h3 class="font-semibold">{name}</h3><p class="text-gray-400 text-xs font-mono">SKU: {(v.get("sku",p.get("sku")) if v else p.get("sku","N/A"))}</p><p class="text-gray-500 text-sm">{price:,} XAF</p></div></div><div class="text-right"><p class="text-sm text-gray-500">Qty: {qty}</p><p class="font-bold text-rose-600">{st:,} XAF</p></div></div>'''
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Cart</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Your Cart</h2>{items or '<p class="text-gray-500 text-center py-8">Cart is empty. <a href="/" class="text-rose-600 underline">Shop</a></p>'}{"<p class='text-right text-xl font-bold mt-4'>Total: "+f"{total:,} XAF</p>" if cart else ""}{'<div class="text-center mt-6"><a href="/checkout" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 inline-block">Proceed to Checkout</a></div>' if cart else ''}</main></body></html>'''

@app.route('/checkout')
def checkout():
    products = load_products()
    cart = get_cart()
    total = 0; summary = ""
    for ck, qty in cart.items():
        parts = ck.split('|'); pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = v.get('price',p['price']) if v else p['price']
        st = price * qty; total += st
        summary += f'<div class="flex justify-between text-sm py-1"><span>{name} × {qty}</span><span>{st:,} XAF</span></div>'
    if not cart: return redirect('/cart')
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Checkout</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 flex justify-between items-center border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1><nav><a href="/" class="text-gray-600 mx-2">Home</a><a href="/cart" class="text-gray-600 mx-2">Cart ({cart_count()})</a></nav></header><main class="max-w-2xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Checkout</h2><div class="bg-white rounded-lg shadow p-4 mb-6"><h3 class="font-semibold mb-2">Order Summary</h3>{summary}<hr class="my-2"><p class="text-right font-bold text-rose-600 text-lg">Total: {total:,} XAF</p></div><form method="POST" action="/initiate-payment" class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Your Details</h3><label class="block mb-1 text-sm">Full Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Phone (MoMo) *</label><input type="tel" name="phone" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Address</label><textarea name="address" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm font-semibold">Payment *</label><div class="mb-2"><label class="inline-flex items-center mr-4"><input type="radio" name="payment_method" value="mtn_momo" checked class="mr-2">MTN MoMo</label><label class="inline-flex items-center"><input type="radio" name="payment_method" value="orange_money" class="mr-2">Orange</label></div><button type="submit" class="bg-rose-600 text-white px-6 py-3 rounded-lg w-full text-lg hover:bg-rose-700 mt-3">Confirm & Pay</button></form></main></body></html>'''

@app.route('/initiate-payment', methods=['POST'])
def initiate_payment():
    products = load_products()
    cart = get_cart()
    total = 0; items = []
    for ck, qty in cart.items():
        parts = ck.split('|'); pid = int(parts[0]); vk = parts[1] if len(parts)>1 else ""
        p = get_product_by_id(pid)
        if not p: continue
        v = next((v for v in p.get('variants',[]) if v.get('key','')==vk), None) if vk else None
        name = p['name'] + ((" - "+"/".join(v['attrs'].values())) if v and v.get('attrs') else "")
        price = v.get('price',p['price']) if v else p['price']
        st = price * qty; total += st
        items.append({"product_id":pid,"sku":v.get("sku",p.get("sku")) if v else p.get("sku","N/A"),"name":name,"qty":qty,"price":price,"subtotal":st,"variant_key":vk})
    if not cart: return redirect('/cart')
    ref = f"MOMO-TEST-{int(time.time())}"
    label = "MTN Mobile Money" if request.form.get('payment_method')=="mtn_momo" else "Orange Money"
    session['pending_order'] = {"ref":ref,"name":request.form.get('name'),"phone":request.form.get('phone'),"address":request.form.get('address'),"payment_label":label,"items":items,"total":total}
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Confirm Payment</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1></header><main class="max-w-lg mx-auto p-4"><div class="bg-white rounded-lg shadow p-6 text-center"><div class="text-5xl mb-4">📱</div><h2 class="text-xl font-semibold mb-2">Confirm Payment</h2><p>Payment of <strong>{total:,} XAF</strong> via <strong>{label}</strong>.</p><div class="bg-gray-100 rounded p-4 my-4"><p class="text-sm">Ref: {ref}</p><p class="text-xs text-gray-400">TEST MODE</p></div><form method="POST" action="/verify-payment"><label class="block mb-2 text-sm">Enter MoMo PIN (any 4 digits)</label><input type="password" name="pin" maxlength="6" required class="border rounded px-3 py-2 text-center text-lg w-32 mb-4"><br><button type="submit" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700">Confirm</button></form></div></main></body></html>'''

@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    pending = session.get('pending_order')
    if not pending or len(request.form.get('pin',''))<4: return redirect('/checkout')
    order = {"ref":pending['ref'],"name":pending['name'],"phone":pending['phone'],"address":pending['address'],"payment_method":pending['payment_label'],"items":pending['items'],"total":pending['total'],"status":"Paid","date":time.strftime('%Y-%m-%d %H:%M:%S')}
    save_order(order)
    session['cart'] = {}
    ref = pending['ref']
    session.pop('pending_order',None)
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Success</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50"><header class="bg-white shadow p-4 border-t-4 border-rose-600"><h1 class="text-2xl font-bold text-rose-600">{STORE_EMOJI} {STORE_NAME}</h1></header><main class="max-w-lg mx-auto p-4 text-center"><div class="bg-white rounded-lg shadow p-6"><div class="text-6xl mb-4">✅</div><h2 class="text-2xl font-bold text-rose-600 mb-2">Payment Successful!</h2><p>Thank you, <strong>{order['name']}</strong>!</p><div class="bg-gray-100 rounded p-4 my-4 text-left"><p class="text-sm">Ref: <strong>{ref}</strong></p><p class="font-bold text-rose-600 text-xl mt-2">{order['total']:,} XAF</p></div><a href="/" class="bg-rose-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-rose-700 inline-block">Continue Shopping</a></div></main></body></html>'''


# ═══════════════════════════════════
#  ADMIN
# ═══════════════════════════════════

@app.route('/admin')
def admin_login_page():
    if is_admin(): return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 w-full max-w-sm"><h1 class="text-2xl font-bold text-rose-600 text-center mb-6">🔐 Admin Login</h1><form method="POST" action="/admin/login"><label class="block mb-1 text-sm">Username</label><input type="text" name="username" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Password</label><input type="password" name="password" required class="w-full border rounded px-3 py-2 mb-4"><button type="submit" class="bg-rose-600 text-white px-4 py-2 rounded w-full">Login</button></form></div></body></html>'''

@app.route('/admin/login', methods=['POST'])
def admin_login():
    if request.form.get('username')==ADMIN_USERNAME and request.form.get('password')==ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return redirect('/admin/dashboard')
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Failed</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-100 flex items-center justify-center min-h-screen"><div class="bg-white rounded-lg shadow p-8 text-center"><div class="text-4xl mb-4">❌</div><h2 class="text-xl mb-2">Login Failed</h2><a href="/admin" class="text-rose-600 underline">Try Again</a></div></body></html>'''

def admin_header(active=""):
    links = [
        ("Dashboard", "/admin/dashboard"),
        ("Products", "/admin/products"),
        ("Inventory", "/admin/inventory"),
        ("Orders", "/admin/orders"),
        ("Reports", "/admin/reports"),
        ("Logout", "/admin/logout"),
    ]
    nav = "".join([f'<a href="{url}" class="text-rose-100 mx-2 hover:text-white {"font-bold underline" if label==active else ""}">{label}</a>' for label, url in links])
    return f'''<header class="bg-rose-600 text-white p-4 flex justify-between items-center flex-wrap"><h1 class="text-xl font-bold">{STORE_EMOJI} {STORE_NAME} Admin</h1><nav class="flex flex-wrap">{nav}</nav></header>'''


@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    products = load_products()
    today = get_today_orders()
    week = get_week_orders()
    revenue = sum(o['total'] for o in orders)
    low = ''.join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2 font-mono text-xs">{p.get("sku","N/A")}</td><td class="py-2"><span class="text-red-600">{get_stock_level(p["id"])}</span></td></tr>' for p in products if get_stock_level(p['id'])<=5]) or '<tr><td colspan="3" class="py-2 text-center text-gray-400">All well stocked</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Dashboard</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Dashboard")}<main class="max-w-5xl mx-auto p-4"><div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6"><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(today)}</p><p class="text-gray-500 text-sm">Today</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(week)}</p><p class="text-gray-500 text-sm">This Week</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{len(orders)}</p><p class="text-gray-500 text-sm">Total Orders</p></div><div class="bg-white rounded-lg shadow p-4 text-center"><p class="text-3xl font-bold text-rose-600">{revenue:,}</p><p class="text-gray-500 text-sm">Revenue</p></div></div><div class="grid grid-cols-1 lg:grid-cols-2 gap-4"><div class="bg-white rounded-lg shadow p-4"><h2 class="font-semibold mb-3">Low Stock Alerts</h2><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th></tr></thead><tbody>{low}</tbody></table></div><div class="bg-white rounded-lg shadow p-4"><h2 class="font-semibold mb-3">Quick Links</h2><div class="space-y-2"><a href="/admin/reports" class="block bg-rose-50 text-rose-700 p-3 rounded hover:bg-rose-100">📊 View Full Reports</a><a href="/admin/products/add" class="block bg-green-50 text-green-700 p-3 rounded hover:bg-green-100">➕ Add New Product</a><a href="/admin/inventory/add" class="block bg-blue-50 text-blue-700 p-3 rounded hover:bg-blue-100">📦 Add Inventory</a></div></div></div></main></body></html>'''


# ─── Reports ───
@app.route('/admin/reports')
def admin_reports():
    if not is_admin(): return redirect('/admin')
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Reports</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">📊 Reports</h2><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">''' + report_card("Sales Summary", "Daily, weekly, monthly sales", "/admin/reports/sales", "💰") + report_card("Product Performance", "Best-selling products", "/admin/reports/products", "🏆") + report_card("Inventory Status", "Stock levels & value", "/admin/reports/inventory", "📦") + report_card("Profit Analysis", "Revenue vs cost", "/admin/reports/profit", "📈") + report_card("Top Customers", "Customer rankings", "/admin/reports/customers", "👥") + '''</div></main></body></html>'''

def report_card(title, desc, url, emoji):
    return f'''<a href="{url}" class="bg-white rounded-lg shadow p-6 hover:shadow-md transition text-center"><div class="text-4xl mb-3">{emoji}</div><h3 class="font-semibold text-lg">{title}</h3><p class="text-gray-500 text-sm">{desc}</p></a>'''


@app.route('/admin/reports/sales')
def report_sales():
    if not is_admin(): return redirect('/admin')
    today = get_today_orders()
    week = get_week_orders()
    month = get_month_orders()
    all_orders = load_orders()
    today_rev = sum(o['total'] for o in today)
    week_rev = sum(o['total'] for o in week)
    month_rev = sum(o['total'] for o in month)
    avg_today = today_rev / len(today) if today else 0
    avg_week = week_rev / len(week) if week else 0
    avg_month = month_rev / len(month) if month else 0
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Sales Report</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-rose-600 text-sm">&larr; Back to Reports</a><h2 class="text-xl font-semibold my-4">💰 Sales Summary</h2><div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6"><div class="bg-white rounded-lg shadow p-4"><h3 class="text-sm text-gray-500">Today</h3><p class="text-3xl font-bold text-rose-600">{today_rev:,} XAF</p><p class="text-sm text-gray-400">{len(today)} orders · Avg {avg_today:,.0f} XAF</p></div><div class="bg-white rounded-lg shadow p-4"><h3 class="text-sm text-gray-500">This Week</h3><p class="text-3xl font-bold text-rose-600">{week_rev:,} XAF</p><p class="text-sm text-gray-400">{len(week)} orders · Avg {avg_week:,.0f} XAF</p></div><div class="bg-white rounded-lg shadow p-4"><h3 class="text-sm text-gray-500">This Month</h3><p class="text-3xl font-bold text-rose-600">{month_rev:,} XAF</p><p class="text-sm text-gray-400">{len(month)} orders · Avg {avg_month:,.0f} XAF</p></div></div><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">All Orders ({len(all_orders)})</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Date</th><th class="py-2">Customer</th><th class="py-2">Total</th><th class="py-2">Status</th></tr></thead><tbody>{"".join([f'<tr class="border-b"><td class="py-2 text-xs">{o["date"]}</td><td class="py-2">{o["name"]}</td><td class="py-2">{o["total"]:,} XAF</td><td class="py-2"><span class="bg-green-100 text-green-700 px-2 py-1 rounded text-xs">{o["status"]}</span></td></tr>' for o in reversed(all_orders)]) or '<tr><td colspan="4" class="py-4 text-center text-gray-400">No orders</td></tr>'}</tbody></table></div></main></body></html>'''


@app.route('/admin/reports/products')
def report_products():
    if not is_admin(): return redirect('/admin')
    sales = get_product_sales()
    rows = ""
    rank = 0
    for pid, data in sales.items():
        rank += 1
        rows += f'<tr class="border-b"><td class="py-2">#{rank}</td><td class="py-2 font-medium">{data["name"]}</td><td class="py-2 text-xs font-mono">{data["sku"]}</td><td class="py-2">{data["qty"]} sold</td><td class="py-2">{data["revenue"]:,} XAF</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Product Performance</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-rose-600 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">🏆 Product Performance</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Rank</th><th class="py-3 px-4">Product</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Units Sold</th><th class="py-3 px-4">Revenue</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No sales yet</td></tr>'}</tbody></table></div></main></body></html>'''


@app.route('/admin/reports/inventory')
def report_inventory():
    if not is_admin(): return redirect('/admin')
    total_value, details = get_inventory_value()
    products = load_products()
    rows = ""
    for d in details:
        rows += f'<tr class="border-b"><td class="py-2">{d["name"]}</td><td class="py-2 text-xs font-mono">{d["sku"]}</td><td class="py-2">{d["stock"]}</td><td class="py-2">{d["avg_cost"]:,.0f} XAF</td><td class="py-2 font-medium">{d["value"]:,.0f} XAF</td></tr>'
    low = "".join([f'<tr class="border-b"><td class="py-2">{p["name"]}</td><td class="py-2 text-xs font-mono">{p.get("sku","N/A")}</td><td class="py-2"><span class="text-red-600 font-medium">{get_stock_level(p["id"])}</span></td></tr>' for p in products if get_stock_level(p['id'])<=5]) or '<tr><td colspan="3" class="py-2 text-center text-gray-400">All well stocked</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Inventory Report</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-rose-600 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">📦 Inventory Status</h2><div class="bg-white rounded-lg shadow p-4 mb-4 text-center"><p class="text-sm text-gray-500">Total Inventory Value</p><p class="text-4xl font-bold text-rose-600">{total_value:,.0f} XAF</p></div><div class="grid grid-cols-1 lg:grid-cols-2 gap-4"><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Stock Valuation</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th><th class="py-2">Avg Cost</th><th class="py-2">Value</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No stock</td></tr>'}</tbody></table></div><div class="bg-white rounded-lg shadow p-4"><h3 class="font-semibold mb-3">Low Stock Alerts</h3><table class="w-full text-sm"><thead><tr class="border-b text-left"><th class="py-2">Product</th><th class="py-2">SKU</th><th class="py-2">Stock</th></tr></thead><tbody>{low}</tbody></table></div></div></main></body></html>'''


@app.route('/admin/reports/profit')
def report_profit():
    if not is_admin(): return redirect('/admin')
    total_profit, data = get_profit_data()
    rows = ""
    for d in data:
        color = "text-green-600" if d['profit']>0 else "text-red-600"
        rows += f'<tr class="border-b"><td class="py-2">{d["name"]}</td><td class="py-2">{d["qty"]} sold</td><td class="py-2">{d["revenue"]:,.0f}</td><td class="py-2">{d["cost"]:,.0f}</td><td class="py-2 {color} font-medium">{d["profit"]:,.0f}</td><td class="py-2">{d["margin"]:.1f}%</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Profit Report</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-rose-600 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">📈 Profit Analysis</h2><div class="bg-white rounded-lg shadow p-4 mb-4 text-center"><p class="text-sm text-gray-500">Total Profit</p><p class="text-4xl font-bold text-green-600">{total_profit:,.0f} XAF</p></div><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Product</th><th class="py-3 px-4">Sold</th><th class="py-3 px-4">Revenue</th><th class="py-3 px-4">Cost/Unit</th><th class="py-3 px-4">Profit</th><th class="py-3 px-4">Margin</th></tr></thead><tbody>{rows or '<tr><td colspan="6" class="py-4 text-center text-gray-400">No sales data</td></tr>'}</tbody></table></div></main></body></html>'''


@app.route('/admin/reports/customers')
def report_customers():
    if not is_admin(): return redirect('/admin')
    customers = get_top_customers()
    rows = ""
    rank = 0
    for c in customers:
        rank += 1
        rows += f'<tr class="border-b"><td class="py-2">#{rank}</td><td class="py-2 font-medium">{c["name"]}</td><td class="py-2">{c["phone"]}</td><td class="py-2">{c["orders"]}</td><td class="py-2">{c["total"]:,} XAF</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Top Customers</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Reports")}<main class="max-w-5xl mx-auto p-4"><a href="/admin/reports" class="text-rose-600 text-sm">&larr; Back</a><h2 class="text-xl font-semibold my-4">👥 Top Customers</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Rank</th><th class="py-3 px-4">Name</th><th class="py-3 px-4">Phone</th><th class="py-3 px-4">Orders</th><th class="py-3 px-4">Total Spent</th></tr></thead><tbody>{rows or '<tr><td colspan="5" class="py-4 text-center text-gray-400">No customers yet</td></tr>'}</tbody></table></div></main></body></html>'''
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
        rows += f'''<tr class="border-b"><td class="py-3 px-4">{ih}</td><td class="py-3 px-4 text-xs font-mono">{p.get('sku','N/A')}</td><td class="py-3 px-4 font-medium">{p['name']}</td><td class="py-3 px-4"><span class="text-xs bg-gray-100 px-2 py-1 rounded">{p.get('category','Other')}</span></td><td class="py-3 px-4">{p['price']:,} XAF</td><td class="py-3 px-4 text-xs">{len(p.get('variants',[]))} var / {len(imgs)} img</td><td class="py-3 px-4 font-medium {sc}">{s}</td><td class="py-3 px-4"><a href="/admin/products/edit/{p['id']}" class="text-blue-600 mr-2 text-xs">Edit</a><a href="/admin/products/{p['id']}/barcode" class="text-purple-600 mr-2 text-xs">🏷️</a><a href="/admin/products/delete/{p['id']}" class="text-red-600 text-xs" onclick="return confirm('Delete?')">Del</a></td></tr>'''
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Products</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Products")}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between mb-4"><h2 class="text-xl font-semibold">Products ({len(products)})</h2><div class="flex gap-2"><a href="/admin/products/bulk" class="bg-blue-600 text-white px-4 py-2 rounded text-sm">CSV Bulk</a><a href="/admin/products/add" class="bg-rose-600 text-white px-4 py-2 rounded">+ Add</a></div></div><div class="bg-white rounded-lg shadow overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Img</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Name</th><th class="py-3 px-4">Cat</th><th class="py-3 px-4">Price</th><th class="py-3 px-4">Details</th><th class="py-3 px-4">Stock</th><th class="py-3 px-4">Actions</th></tr></thead><tbody>{rows or '<tr><td colspan="8" class="py-4 text-center text-gray-400">No products</td></tr>'}</tbody></table></div></main></body></html>'''
@app.route('/admin/products/add')
def admin_add_product_form():
    if not is_admin(): return redirect('/admin')
    cat_opts = "".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    cdata = json.dumps({c:{"attrs":d["attributes"],"variants":d["variant_fields"]} for c,d in CATEGORIES.items()})
    html = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Add Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">''' + admin_header("Products") + '''<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Product</h2><form method="POST" action="/admin/products/add" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Category *</label><select name="category" required class="w-full border rounded px-3 py-2 mb-3" id="cat-select" onchange="showFields()"><option value="">-- Select --</option>''' + cat_opts + '''</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Base Price (XAF) *</label><input type="number" name="price" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Images (up to 5)</label><input type="file" name="image_1" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_2" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_3" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_4" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_5" accept="image/*" class="w-full border rounded px-3 py-2 mb-3"><p class="text-xs text-gray-400 mb-3">First image is the main one.</p><label class="block mb-1 text-sm">Or Emoji</label><input type="text" name="image_emoji" class="w-full border rounded px-3 py-2 mb-4"><div id="variant-area" class="mb-4 border rounded p-3 bg-gray-50"><p class="text-sm text-gray-400">Select a category to add variants</p></div><div id="attributes-area" class="mb-4"><p class="text-sm text-gray-400">Select a category for attributes</p></div><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Add Product</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main><script>var cd=''' + cdata + ''';var vc=0;var cvf=[];function showFields(){var cat=document.getElementById("cat-select").value;var va=document.getElementById("variant-area");var aa=document.getElementById("attributes-area");var d=cd[cat];if(!d){va.innerHTML='<p class="text-sm text-gray-400">Select a category first</p>';aa.innerHTML='<p class="text-sm text-gray-400">Select a category first</p>';return;}var ah='<h3 class="font-semibold text-sm mb-2">Attributes</h3>';d.attrs.forEach(function(x){ah+='<label class="block mb-1 text-sm">'+x+'</label><input type="text" name="attr_'+x+'" class="w-full border rounded px-3 py-2 mb-2">';});aa.innerHTML=ah;if(d.variants.length>0){cvf=d.variants;var vh='<h3 class="font-semibold text-sm mb-2">Variants <span class="text-xs text-gray-400">(add at least one)</span></h3><div id="variant-list"></div><button type="button" onclick="addVariant()" class="mt-2 text-rose-600 text-sm border border-rose-600 px-3 py-1 rounded hover:bg-rose-50">+ Add Variant</button>';va.innerHTML=vh;vc=0;addVariant();}else{va.innerHTML='<p class="text-sm text-gray-400">No variants for this category</p>';}}function addVariant(){if(cvf.length===0)return;vc++;var idx=vc;var h='<div class="border rounded p-2 mb-2 bg-white" id="var-'+idx+'"><p class="text-xs font-semibold mb-1">Variant #'+idx+'</p>';cvf.forEach(function(f){h+='<label class="block mb-1 text-xs">'+f+'</label><input type="text" name="var_'+idx+'_'+f+'" class="w-full border rounded px-2 py-1 mb-1 text-sm">';});h+='<label class="block mb-1 text-xs">Price (blank=base)</label><input type="number" name="var_'+idx+'_price" class="w-full border rounded px-2 py-1 mb-1 text-sm" min="0">';h+='<button type="button" onclick="document.getElementById(\\'var-'+idx+'\\').remove()" class="text-red-500 text-xs mt-1">Remove</button></div>';document.getElementById("variant-list").insertAdjacentHTML("beforeend",h);}</script></body></html>'''
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
    if not images:
        em = request.form.get('image_emoji','').strip()
        if em: images = [em]
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
                if vkey:
                    variants.append({"key":vkey,"sku":generate_sku(cat,nid,vkey),"attrs":vattrs,"price":vprice})
    products.append({"id":nid,"sku":generate_sku(cat,nid),"name":request.form.get('name'),"description":request.form.get('description',''),"price":bp,"images":images,"category":cat,"attributes":attrs,"variants":variants})
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
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Edit Product</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Products")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Product</h2><form method="POST" action="/admin/products/edit/{pid}" enctype="multipart/form-data" class="bg-white rounded-lg shadow p-6">{ih}<p class="text-xs text-gray-500 mb-3">SKU: <strong>{p.get("sku")}</strong> | {len(imgs)} image(s)</p><label class="block mb-1 text-sm">Category</label><select name="category" class="w-full border rounded px-3 py-2 mb-3">{cat_opts}</select><label class="block mb-1 text-sm">Name *</label><input type="text" name="name" required value="{p["name"]}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Description</label><textarea name="description" rows="3" class="w-full border rounded px-3 py-2 mb-3">{p["description"]}</textarea><label class="block mb-1 text-sm">Base Price *</label><input type="number" name="price" required value="{p["price"]}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Add More Images</label><input type="file" name="image_1" accept="image/*" class="w-full border rounded px-3 py-2 mb-1"><input type="file" name="image_2" accept="image/*" class="w-full border rounded px-3 py-2 mb-3"><p class="text-xs text-gray-400 mb-3">Adds to existing images.</p><div id="attributes-area" class="mb-4"><h3 class="font-semibold text-sm mb-2">Attributes</h3>{attrs_html}</div><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full hover:bg-rose-700">Update</button><a href="/admin/products" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

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
csv_content = "name,category,description,base_price,image_url,brand,style,size,color,variant_price\n"
csv_content += 'CK Jean,Men\'s Wear,Regular fit blue jeans,15000,https://example.com/jean.jpg,Calvin Klein,Regular,"32,34,36,38","Blue,Brown","15000,15000,14000,14000"\n'
csv_content += 'Summer Dress,Women\'s Wear,Light floral dress,12000,https://example.com/dress.jpg,Zara,Casual,"S,M,L","Red,White,Black","12000,12000,12000"\n'
@app.route('/admin/products/template')
def download_template():
    if not is_admin(): return redirect('/admin')
    csv_content = "name,category,description,base_price,image_url,brand,style,size,color,variant_price\n"
    csv_content += 'CK Jean,Men\'s Wear,Regular fit blue jeans,15000,https://example.com/jean.jpg,Calvin Klein,Regular,"32,34,36,38","Blue,Brown","15000,15000,14000,14000"\n'
    csv_content += 'Summer Dress,Women\'s Wear,Light floral dress,12000,https://example.com/dress.jpg,Zara,Casual,"S,M,L","Red,White,Black","12000,12000,12000"\n'
    from flask import Response
    return Response(csv_content, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=nash_fashion_template.csv"})
@app.route('/admin/products/bulk', methods=['GET', 'POST'])
def admin_bulk_upload():
    if not is_admin(): return redirect('/admin')
    result = ""
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename:
            result = '<p class="text-red-500 text-sm">Please select a CSV file.</p>'
        elif not file.filename.endswith('.csv'):
            result = '<p class="text-red-500 text-sm">Only .csv files allowed.</p>'
        else:
            import io, csv
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)
            products = load_products()
            next_id = max([p['id'] for p in products], default=0) + 1
            created = 0
            errors = []
            for row_num, row in enumerate(reader, start=2):
                name = row.get('name', '').strip()
                category = row.get('category', '').strip()
                base_price_str = row.get('base_price', '0').strip()
                if not name:
                    errors.append(f'Row {row_num}: Missing product name')
                    continue
                if category not in CATEGORIES:
                    errors.append(f'Row {row_num}: Invalid category "{category}"')
                    continue
                try:
                    base_price = int(base_price_str)
                except:
                    errors.append(f'Row {row_num}: Invalid base price')
                    continue
                
                # Attributes
                attr_keys = CATEGORIES[category]['attributes']
                attrs = {}
                for k in attr_keys:
                    attrs[k] = row.get(k.lower(), '').strip()
                
                # Variants
                variant_fields = CATEGORIES[category]['variant_fields']
                sizes_str = row.get('size', '').strip()
                colors_str = row.get('color', '').strip()
                variant_prices_str = row.get('variant_price', '').strip()
                
                variants = []
                if variant_fields and sizes_str:
                    sizes = [s.strip() for s in sizes_str.split(',') if s.strip()]
                    colors = [c.strip() for c in colors_str.split(',') if c.strip()] if 'Color' in variant_fields else ['']
                    vprices = [int(p.strip()) for p in variant_prices_str.split(',') if p.strip()] if variant_prices_str else []
                    
                    vi = 0
                    for size in sizes:
                        for color in colors:
                            vattrs = {}
                            if 'Size' in variant_fields:
                                vattrs['Size'] = size
                            if 'Color' in variant_fields and color:
                                vattrs['Color'] = color
                            vkey = "-".join(v for v in [size, color] if v)
                            vprice = vprices[vi] if vi < len(vprices) else base_price
                            variants.append({
                                "key": vkey,
                                "sku": generate_sku(category, next_id, vkey),
                                "attrs": vattrs,
                                "price": vprice
                            })
                            vi += 1
                
                products.append({
                    "id": next_id,
                    "sku": generate_sku(category, next_id),
                    "name": name,
                    "description": row.get('description', '').strip(),
                    "price": base_price,
                    "images": [row.get('image_url', '').strip()] if row.get('image_url', '').strip() else [],
                    "category": category,
                    "attributes": attrs,
                    "variants": variants
                })
                next_id += 1
                created += 1
            
            save_products(products)
            result = f'<p class="text-green-600 font-medium">✅ {created} products created successfully!</p>'
            if errors:
                result += '<div class="text-red-500 text-sm mt-2">' + '<br>'.join(errors) + '</div>'
    
    return f'''<!DOCTYPE html><html<h2 class="text-xl font-semibold my-4">CSV Bulk Upload Products</h2>
    <div class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="font-semibold mb-2">Step 1: Download Template</h3>
    <p class="text-sm text-gray-500 mb-3">Download the CSV template and fill in your products in Excel.</p>
    <a href="/admin/products/template" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm">📥 Download Template</a>
    </div>
    <div class="bg-white rounded-lg shadow p-6 mb-4">
    <h3 class="font-semibold mb-2">Step 2: Upload Filled CSV</h3>
    <form method="POST" enctype="multipart/form-data">
    <input type="file" name="csv_file" accept=".csv" required class="w-full border rounded px-3 py-2 mb-3">
    <button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded hover:bg-rose-700">Upload & Import</button>
    </form>
    </div>
    {result}
    <div class="bg-yellow-50 border border-yellow-200 rounded p-4 mt-4">
    <h3 class="font-semibold text-sm mb-2">📝 CSV Columns Guide</h3>
    <table class="w-full text-xs"><thead><tr class="border-b"><th class="py-1 text-left">Column</th><th class="py-1 text-left">Required</th><th class="py-1 text-left">Example</th></tr></thead>
    <tbody><tr class="border-b">><td class="py-1 font-medium">base_price</td><td class="py-1">Yes</td><td class="py-1">15000</td></tr>
<tr class="border-b"><td class="py-1 font-medium">image_url</td><td class="py-1">No</td><td class="py-1">https://example.com/photo.jpg</td></tr>
<tr class="border-b"><td class="py-1 font-medium">brand</td><td class="py-1">No</td><td class="py-1">Calvin Klein</td></tr>
    <tr class="border-b"><td class="py-1 font-medium">style</td><td class="py-1">No</td><td class="py-1">Regular Jean</td></tr>
    <tr class="border-b"><td class="py-1 font-medium">size</td><td class="py-1">No</td><td class="py-1">32,34,36,38</td></tr>
    <tr class="border-b"><td class="py-1 font-medium">color</td><td class="py-1">No</td><td class="py-1">Blue,Brown</td></tr>
    <tr><td class="py-1 font-medium">variant_price</td><td class="py-1">No</td><td class="py-1">15000,15000,14000,14000</td></tr></tbody></table>
    </div></main></body></html>'''
@app.route('/admin/products/delete/<int:pid>')
def admin_delete_product(pid):
    if not is_admin(): return redirect('/admin')
    save_products([p for p in load_products() if p['id']!=pid])
    return redirect('/admin/products')

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
        boxes += f'<div class="barcode-box"><p style="font-weight:bold;margin:0 0 5px;font-size:14px;">{label}</p><p style="font-size:12px;color:#666;">SKU: {sku}</p><svg id="bc_{sku}"></svg><p style="font-size:16px;font-weight:bold;color:#e11d48;">{v.get("price",p["price"]):,} XAF</p></div>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Barcodes</title><script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script><style>@media print{{body{{margin:0}}.no-print{{display:none}}}}.barcode-box{{border:2px dashed #ccc;padding:20px;text-align:center;display:inline-block;margin:10px;}}</style></head><body style="font-family:Arial;text-align:center;padding:20px;"><div class="no-print"><p>Barcodes for <strong>{p['name']}</strong></p><label>Copies: <input type="number" id="copies" value="1" min="1" max="100" style="width:60px;"></label><button onclick="generateAll()" style="padding:8px 16px;background:#e11d48;color:white;border:none;border-radius:4px;">Generate</button><button onclick="window.print()" style="padding:8px 16px;background:#16a34a;color:white;border:none;border-radius:4px;">Print</button><a href="/admin/products" style="margin-left:10px;color:#666;">Back</a></div><div id="barcode-area">{boxes}</div><script>document.querySelectorAll('svg[id^="bc_"]').forEach(s=>{{JsBarcode(s,s.id.replace("bc_",""),{{format:"CODE128",width:2,height:60,displayValue:true,fontSize:12,margin:5}});}});function generateAll(){{location.reload();}}</script></body></html>'''

# Inventory & Orders (kept from previous version)
@app.route('/admin/inventory')
def admin_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    rows = ""
    for i in inv:
        prod = get_product_by_id(i['product_id'])
        pn = prod['name'] if prod else f"#{i['product_id']}"
        sku = i.get('variant_sku', prod.get('sku','N/A') if prod else 'N/A')
        tc = i['quantity_ordered'] * i['unit_cost']
        bo = i['quantity_ordered'] - i['quantity_received']
        sc = "green" if i['status']=="Received" else ("blue" if i['status']=="In Transit" else "yellow")
        rows += f'''<tr class="border-b"><td class="py-3 px-4 text-xs">{i.get('date_purchased','')}</td><td class="py-3 px-4">{pn}</td><td class="py-3 px-4 text-xs font-mono">{sku}</td><td class="py-3 px-4">{i['quantity_ordered']}</td><td class="py-3 px-4">{i['quantity_received']}</td><td class="py-3 px-4 text-orange-500">{bo}</td><td class="py-3 px-4">{i['unit_cost']:,}</td><td class="py-3 px-4">{tc:,}</td><td class="py-3 px-4 text-xs">{i.get('supplier_name','')}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{i['status']}</span></td><td class="py-3 px-4"><a href="/admin/inventory/edit/{i['id']}" class="text-blue-600 text-xs mr-2">Edit</a><a href="/admin/inventory/delete/{i['id']}" class="text-red-600 text-xs" onclick="return confirm('Delete?')">Del</a></td></tr>'''
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-6xl mx-auto p-4"><div class="flex justify-between mb-4"><h2 class="text-xl font-semibold">Inventory ({len(inv)})</h2><a href="/admin/inventory/add" class="bg-rose-600 text-white px-4 py-2 rounded">+ Add</a></div><div class="bg-white rounded-lg shadow overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Date</th><th class="py-3 px-4">Product</th><th class="py-3 px-4">SKU</th><th class="py-3 px-4">Ord</th><th class="py-3 px-4">Rec</th><th class="py-3 px-4">Back</th><th class="py-3 px-4">Cost</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Supplier</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="11" class="py-4 text-center text-gray-400">No entries</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/inventory/add')
def admin_add_inventory_form():
    if not is_admin(): return redirect('/admin')
    products = load_products()
    popts = ""
    for p in products:
        for v in p.get('variants',[]) or [{"key":"","sku":p.get("sku","N/A")}]:
            vlabel = " / ".join([f"{k}:{v}" for k,v in v.get('attrs',{}).items()]) if v.get('attrs') else "Base"
            popts += f'<option value="{p["id"]}|{v["key"]}">{p["name"]} — {vlabel} ({v.get("sku",p["sku"])})</option>'
    sopts = "".join([f'<option value="{s}">{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Add Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Add Inventory</h2><form method="POST" action="/admin/inventory/add" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product / Variant *</label><select name="product_ref" required class="w-full border rounded px-3 py-2 mb-3"><option value="">-- Select --</option>{popts}</select><label class="block mb-1 text-sm">Qty Ordered *</label><input type="number" name="quantity_ordered" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="0" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost *</label><input type="number" name="unit_cost" required class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3"></textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full">Add</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/add', methods=['POST'])
def admin_add_inventory():
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    nid = max([i['id'] for i in inv], default=0) + 1
    pref = request.form.get('product_ref','|')
    pid_str, vk = pref.split('|',1) if '|' in pref else (pref,'')
    pid = int(pid_str) if pid_str else 0
    inv.append({"id":nid,"product_id":pid,"variant_key":vk,"quantity_ordered":int(request.form.get('quantity_ordered',0)),"quantity_received":int(request.form.get('quantity_received',0)),"unit_cost":int(request.form.get('unit_cost',0)),"date_purchased":request.form.get('date_purchased',''),"date_received":request.form.get('date_received',''),"supplier_name":request.form.get('supplier_name',''),"supplier_phone":request.form.get('supplier_phone',''),"supplier_address":request.form.get('supplier_address',''),"status":request.form.get('status','Ordered')})
    save_inventory(inv)
    return redirect('/admin/inventory')

@app.route('/admin/inventory/edit/<int:iid>')
def admin_edit_inventory_form(iid):
    if not is_admin(): return redirect('/admin')
    i = next((x for x in load_inventory() if x['id']==iid), None)
    if not i: return redirect('/admin/inventory')
    products = load_products()
    popts = ""
    for p in products:
        for v in p.get('variants',[]) or [{"key":"","sku":p.get("sku","N/A")}]:
            sel = 'selected' if p['id']==i['product_id'] and v['key']==i.get('variant_key','') else ''
            vlabel = " / ".join([f"{k}:{v}" for k,v in v.get('attrs',{}).items()]) if v.get('attrs') else "Base"
            popts += f'<option value="{p["id"]}|{v["key"]}" {sel}>{p["name"]} — {vlabel}</option>'
    sopts = "".join([f'<option value="{s}" {"selected" if s==i["status"] else ""}>{s}</option>' for s in INVENTORY_STATUSES])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Edit Inventory</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Inventory")}<main class="max-w-lg mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Edit Inventory</h2><form method="POST" action="/admin/inventory/edit/{iid}" class="bg-white rounded-lg shadow p-6"><label class="block mb-1 text-sm">Product</label><select name="product_ref" class="w-full border rounded px-3 py-2 mb-3">{popts}</select><label class="block mb-1 text-sm">Qty Ordered</label><input type="number" name="quantity_ordered" value="{i['quantity_ordered']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Qty Received</label><input type="number" name="quantity_received" value="{i['quantity_received']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Unit Cost</label><input type="number" name="unit_cost" value="{i['unit_cost']}" class="w-full border rounded px-3 py-2 mb-3" min="0"><label class="block mb-1 text-sm">Date Purchased</label><input type="date" name="date_purchased" value="{i.get('date_purchased','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Date Received</label><input type="date" name="date_received" value="{i.get('date_received','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Name</label><input type="text" name="supplier_name" value="{i.get('supplier_name','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Phone</label><input type="tel" name="supplier_phone" value="{i.get('supplier_phone','')}" class="w-full border rounded px-3 py-2 mb-3"><label class="block mb-1 text-sm">Supplier Address</label><textarea name="supplier_address" rows="2" class="w-full border rounded px-3 py-2 mb-3">{i.get('supplier_address','')}</textarea><label class="block mb-1 text-sm">Status</label><select name="status" class="w-full border rounded px-3 py-2 mb-4">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-6 py-2 rounded w-full">Update</button><a href="/admin/inventory" class="block text-center mt-2 text-sm text-gray-500">Cancel</a></form></main></body></html>'''

@app.route('/admin/inventory/edit/<int:iid>', methods=['POST'])
def admin_edit_inventory(iid):
    if not is_admin(): return redirect('/admin')
    inv = load_inventory()
    for i in inv:
        if i['id']==iid:
            pref = request.form.get('product_ref','|')
            ps, vk = pref.split('|',1) if '|' in pref else (pref,'')
            i['product_id'] = int(ps) if ps else i['product_id']
            i['variant_key'] = vk
            i['quantity_ordered'] = int(request.form.get('quantity_ordered',i['quantity_ordered']))
            i['quantity_received'] = int(request.form.get('quantity_received',i['quantity_received']))
            i['unit_cost'] = int(request.form.get('unit_cost',i['unit_cost']))
            i['date_purchased'] = request.form.get('date_purchased',i.get('date_purchased',''))
            i['date_received'] = request.form.get('date_received',i.get('date_received',''))
            i['supplier_name'] = request.form.get('supplier_name',i.get('supplier_name',''))
            i['supplier_phone'] = request.form.get('supplier_phone',i.get('supplier_phone',''))
            i['supplier_address'] = request.form.get('supplier_address',i.get('supplier_address',''))
            i['status'] = request.form.get('status',i['status'])
            break
    save_inventory(inv)
    return redirect('/admin/inventory')

@app.route('/admin/inventory/delete/<int:iid>')
def admin_delete_inventory(iid):
    if not is_admin(): return redirect('/admin')
    save_inventory([i for i in load_inventory() if i['id']!=iid])
    return redirect('/admin/inventory')

@app.route('/admin/orders')
def admin_orders():
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    rows = ""
    for idx, o in enumerate(reversed(orders)):
        ri = len(orders)-1-idx
        sc = "rose" if o['status']=="Paid" else ("blue" if o['status']=="Confirmed" else ("yellow" if o['status']=="Shipped" else "green"))
        rows += f'<tr class="border-b"><td class="py-3 px-4 text-xs">{o["ref"]}</td><td class="py-3 px-4">{o["name"]}</td><td class="py-3 px-4">{o["phone"]}</td><td class="py-3 px-4">{o["total"]:,}</td><td class="py-3 px-4"><span class="bg-{sc}-100 text-{sc}-700 px-2 py-1 rounded text-xs">{o["status"]}</span></td><td class="py-3 px-4 text-xs">{o["date"]}</td><td class="py-3 px-4"><a href="/admin/orders/{ri}" class="text-rose-600 text-xs">View</a></td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Orders</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Orders")}<main class="max-w-5xl mx-auto p-4"><h2 class="text-xl font-semibold mb-4">Orders ({len(orders)})</h2><div class="bg-white rounded-lg shadow overflow-hidden"><table class="w-full text-sm"><thead><tr class="border-b text-left bg-gray-50"><th class="py-3 px-4">Ref</th><th class="py-3 px-4">Customer</th><th class="py-3 px-4">Phone</th><th class="py-3 px-4">Total</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Date</th><th class="py-3 px-4">Act</th></tr></thead><tbody>{rows or '<tr><td colspan="7" class="py-4 text-center text-gray-400">No orders</td></tr>'}</tbody></table></div></main></body></html>'''

@app.route('/admin/orders/<int:oi>')
def admin_order_detail(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if oi<0 or oi>=len(orders): return redirect('/admin/orders')
    o = orders[oi]
    items = "".join([f'<tr class="border-b"><td class="py-2 text-xs font-mono">{i.get("sku","N/A")}</td><td class="py-2">{i["name"]}</td><td class="py-2">{i["qty"]}</td><td class="py-2">{i["price"]:,}</td><td class="py-2">{i["subtotal"]:,}</td></tr>' for i in o['items']])
    sopts = "".join([f'<option value="{s}" {"selected" if s==o["status"] else ""}>{s}</option>' for s in ORDER_STATUSES])
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Order {o["ref"]}</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-gray-50">{admin_header("Orders")}<main class="max-w-3xl mx-auto p-4"><a href="/admin/orders" class="text-rose-600 text-sm">&larr; Back</a><div class="bg-white rounded-lg shadow p-6 my-4"><div class="flex justify-between mb-4"><div><h2 class="text-xl font-bold">{o["ref"]}</h2><p class="text-gray-500 text-sm">{o["date"]}</p></div><span class="bg-rose-100 text-rose-700 px-3 py-1 rounded text-sm">{o["status"]}</span></div><div class="grid grid-cols-2 gap-4 mb-4"><div><p class="text-xs text-gray-500">Customer</p><p class="font-medium">{o["name"]}</p></div><div><p class="text-xs text-gray-500">Phone</p><p>{o["phone"]}</p></div><div><p class="text-xs text-gray-500">Payment</p><p>{o["payment_method"]}</p></div><div><p class="text-xs text-gray-500">Address</p><p>{o.get("address","")}</p></div></div><h3 class="font-semibold mb-2">Items</h3><table class="w-full text-sm mb-4"><thead><tr class="border-b"><th class="py-2 text-left">SKU</th><th class="py-2 text-left">Item</th><th class="py-2">Qty</th><th class="py-2">Price</th><th class="py-2">Subtotal</th></tr></thead><tbody>{items}</tbody></table><p class="text-right text-xl font-bold text-rose-600">Total: {o["total"]:,} XAF</p></div><div class="bg-white rounded-lg shadow p-6"><h3 class="font-semibold mb-3">Update Status</h3><form method="POST" action="/admin/orders/{oi}/update" class="flex gap-3"><select name="status" class="border rounded px-3 py-2 flex-1">{sopts}</select><button type="submit" class="bg-rose-600 text-white px-4 py-2 rounded">Update</button></form></div></main></body></html>'''

@app.route('/admin/orders/<int:oi>/update', methods=['POST'])
def admin_update_order(oi):
    if not is_admin(): return redirect('/admin')
    orders = load_orders()
    if 0<=oi<len(orders):
        orders[oi]['status'] = request.form.get('status','Paid')
        save_orders(orders)
    return redirect(f'/admin/orders/{oi}')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in',None)
    return redirect('/admin')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)