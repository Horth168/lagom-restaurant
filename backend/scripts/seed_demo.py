"""Load DEMO data for development: categories, menu, options, tables, ingredients, recipes, staff.

    python -m scripts.seed_demo

Refuses to run when ENVIRONMENT=production. Safe to run twice (skips if a menu exists).
Khmer and Chinese names are a starting point – have a native speaker review them.
Product photos are left empty on purpose: upload real LAGOM photography in the admin.

Demo staff accounts all use the password in DEMO_STAFF_PASSWORD (default below, development only):
    owner@lagom.test, admin@lagom.test, cashier@lagom.test,
    kitchen@lagom.test, drinks@lagom.test, inventory@lagom.test
"""
import os
import sys
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    Category, DiningTable, Ingredient, Option, OptionGroup, Product, Promotion, RecipeItem, Supplier, User,
)
from app.models.enums import OptionSelection, Role, Station

DEMO_PASSWORD = os.environ.get("DEMO_STAFF_PASSWORD", "Lagom-demo-2026")

# slug, en, km, zh, station
CATEGORIES = [
    ("cambodian", "Cambodian Food", "ម្ហូបខ្មែរ", "柬埔寨菜", Station.KITCHEN),
    ("chinese", "Chinese Food", "ម្ហូបចិន", "中餐", Station.KITCHEN),
    ("rice", "Rice", "បាយ", "饭类", Station.KITCHEN),
    ("noodles", "Noodles", "មី និង គុយទាវ", "面类", Station.KITCHEN),
    ("western", "Western Food", "ម្ហូបបស្ចិមប្រទេស", "西餐", Station.KITCHEN),
    ("snacks", "Snacks", "អាហារសម្រន់", "小吃", Station.KITCHEN),
    ("coffee", "Coffee", "កាហ្វេ", "咖啡", Station.DRINKS),
    ("milk-tea", "Milk Tea", "តែទឹកដោះគោ", "奶茶", Station.DRINKS),
    ("juice", "Fresh Juice", "ទឹកផ្លែឈើស្រស់", "鲜榨果汁", Station.DRINKS),
    ("soft-drinks", "Soft Drinks", "ភេសជ្ជៈ", "软饮料", Station.DRINKS),
    ("desserts", "Desserts", "បង្អែម", "甜品", Station.DESSERT),
]

# category, en, km, zh, price (USD), prep minutes, flags, description, option-set
PRODUCTS = [
    ("cambodian", "Fish Amok", "អាម៉ុកត្រី", "阿莫克鱼", 6.50, 15, "FB",
     "Steamed fish curry with kroeung, coconut and noni leaf, served in banana leaf.", "food"),
    ("cambodian", "Beef Lok Lak", "ឡុកឡាក់សាច់គោ", "柬式牛肉粒", 6.90, 12, "B",
     "Wok-seared beef with Kampot pepper and lime dip.", "food"),
    ("cambodian", "Samlor Korko", "សម្លកកូរ", "柬式什锦汤", 5.50, 15, "",
     "Traditional stirred soup with green papaya, pumpkin and toasted rice.", "food"),
    ("chinese", "Kung Pao Chicken", "មាន់ខុងប៉ាវ", "宫保鸡丁", 6.00, 12, "",
     "Chicken, peanuts and dried chilli in a glossy Sichuan sauce.", "food"),
    ("chinese", "Mapo Tofu", "តៅហ៊ូម៉ាប៉ូ", "麻婆豆腐", 5.00, 10, "",
     "Silken tofu in a numbing chilli bean sauce.", "food"),
    ("rice", "Fried Rice", "បាយឆា", "炒饭", 4.50, 10, "B",
     "Jasmine rice fried with egg, spring onion and your choice of protein.", "rice"),
    ("rice", "Bai Sach Chrouk", "បាយសាច់ជ្រូក", "柬式猪肉饭", 4.00, 8, "F",
     "Coconut-marinated grilled pork over broken rice with pickles.", "food"),
    ("noodles", "Kuy Teav", "គុយទាវ", "粿条汤", 4.50, 10, "B",
     "Clear pork-bone broth, rice noodles and fresh herbs.", "food"),
    ("noodles", "Lort Cha", "លតឆា", "炒米虫粉", 3.50, 8, "",
     "Short rice noodles stir-fried with bean sprouts and a fried egg.", "food"),
    ("western", "LAGOM Beef Burger", "ប៊ឺហ្គឺសាច់គោ LAGOM", "LAGOM 牛肉汉堡", 8.50, 15, "F",
     "Grilled beef patty, aged cheddar, house pickles, brioche bun.", "food"),
    ("western", "Spaghetti Carbonara", "ស្ប៉ាហ្គេទីកាបូណារ៉ា", "培根奶油意面", 7.50, 14, "",
     "Egg yolk, pecorino, black pepper and crisp bacon.", "food"),
    ("snacks", "French Fries", "ដំឡូងបារាំងបំពង", "炸薯条", 2.50, 6, "",
     "Crisp fries with sea salt.", "none"),
    ("snacks", "Crispy Spring Rolls", "ណែមចៀន", "炸春卷", 3.00, 8, "",
     "Pork and vegetable rolls with sweet chilli sauce.", "none"),
    ("coffee", "Iced Latte", "ឡាតេទឹកកក", "冰拿铁", 2.75, 4, "FB",
     "Double espresso over cold milk and ice.", "coffee"),
    ("coffee", "Khmer Iced Coffee", "កាហ្វេទឹកដោះគោទឹកកក", "柬式冰奶咖啡", 2.00, 3, "B",
     "Strong drip coffee with sweetened condensed milk.", "coffee"),
    ("coffee", "Americano", "អាមេរិកាណូ", "美式咖啡", 2.25, 3, "",
     "Espresso lengthened with water. Hot or iced.", "coffee"),
    ("milk-tea", "Brown Sugar Boba Milk Tea", "តែទឹកដោះគោស្ករត្នោតគុជ", "黑糖珍珠奶茶", 3.00, 5, "FB",
     "Fresh milk, brown sugar syrup and chewy tapioca pearls.", "tea"),
    ("milk-tea", "Matcha Latte", "ម៉ាតឆាឡាតេ", "抹茶拿铁", 3.25, 4, "",
     "Stone-ground Japanese matcha with milk.", "tea"),
    ("juice", "Mango Smoothie", "ទឹកក្រឡុកស្វាយ", "芒果冰沙", 3.00, 5, "F",
     "Ripe Cambodian mango blended with ice.", "juice"),
    ("juice", "Passion Fruit Juice", "ទឹកផ្លែសាវម៉ាវ", "百香果汁", 2.50, 4, "",
     "Fresh passion fruit, lightly sweetened.", "juice"),
    ("juice", "Fresh Coconut", "ដូងស្រស់", "新鲜椰子", 2.00, 2, "",
     "Chilled young coconut.", "none"),
    ("soft-drinks", "Cola", "កូឡា", "可乐", 1.25, 1, "", "Chilled can.", "none"),
    ("soft-drinks", "Sparkling Water", "ទឹករ៉ែមានហ្គាស", "苏打水", 1.50, 1, "", "Chilled bottle.", "none"),
    ("soft-drinks", "Mineral Water", "ទឹកសុទ្ធ", "矿泉水", 0.75, 1, "", "500 ml bottle.", "none"),
    ("desserts", "Basque Cheesecake", "នំឈីសខេក", "巴斯克芝士蛋糕", 3.75, 3, "FB",
     "Caramelised top, soft creamy centre.", "none"),
    ("desserts", "Mango Sticky Rice", "បាយដំណើបស្វាយ", "芒果糯米饭", 3.50, 5, "",
     "Sweet coconut sticky rice with fresh mango.", "none"),
]


def g(name, km, zh, sel, required, options, max_select=1, min_select=None):
    return dict(name=(name, km, zh), sel=sel, required=required, options=options,
                max_select=max_select, min_select=(1 if required else 0) if min_select is None else min_select)


SIZE = g("Size", "ទំហំ", "杯型", OptionSelection.SINGLE, True, [
    ("Small", "តូច", "小杯", 0, False, "1"), ("Medium", "មធ្យម", "中杯", 50, True, "1.3"),
    ("Large", "ធំ", "大杯", 100, False, "1.6")])
SUGAR = g("Sugar", "ស្ករ", "甜度", OptionSelection.SINGLE, True, [
    ("0%", "0%", "0%", 0, False, "1"), ("25%", "25%", "25%", 0, False, "1"), ("50%", "50%", "50%", 0, True, "1"),
    ("75%", "75%", "75%", 0, False, "1"), ("100%", "100%", "100%", 0, False, "1")])
ICE = g("Ice", "ទឹកកក", "冰量", OptionSelection.SINGLE, True, [
    ("No ice", "គ្មានទឹកកក", "去冰", 0, False, "1"), ("Less ice", "ទឹកកកតិច", "少冰", 0, False, "1"),
    ("Normal ice", "ទឹកកកធម្មតា", "正常冰", 0, True, "1"), ("Extra ice", "ទឹកកកច្រើន", "多冰", 0, False, "1")])
COFFEE_EXTRAS = g("Extras", "បន្ថែម", "加料", OptionSelection.MULTIPLE, False, [
    ("Extra espresso shot", "បន្ថែមអេសប្រេសូ", "加浓缩", 50, False, "1"),
    ("Oat milk", "ទឹកដោះស្រូវអូត", "燕麦奶", 50, False, "1"),
    ("Whipped cream", "ក្រែម", "奶油", 30, False, "1")], max_select=3)
TEA_TOPPINGS = g("Toppings", "គ្រឿងបន្ថែម", "小料", OptionSelection.MULTIPLE, False, [
    ("Extra pearls", "គុជបន្ថែម", "加珍珠", 40, False, "1"), ("Grass jelly", "ចាហួយ", "仙草", 40, False, "1"),
    ("Cheese foam", "ពពុះឈីស", "芝士奶盖", 60, False, "1")], max_select=3)
SPICE = g("Spice level", "កម្រិតហឹរ", "辣度", OptionSelection.SINGLE, False, [
    ("Not spicy", "មិនហឹរ", "不辣", 0, True, "1"), ("Mild", "ហឹរតិច", "微辣", 0, False, "1"),
    ("Spicy", "ហឹរ", "辣", 0, False, "1")])
PROTEIN = g("Protein", "សាច់", "配料", OptionSelection.SINGLE, True, [
    ("Chicken", "សាច់មាន់", "鸡肉", 0, True, "1"), ("Pork", "សាច់ជ្រូក", "猪肉", 0, False, "1"),
    ("Beef", "សាច់គោ", "牛肉", 100, False, "1"), ("Shrimp", "បង្គា", "虾", 150, False, "1")])
FOOD_EXTRAS = g("Extras", "បន្ថែម", "加料", OptionSelection.MULTIPLE, False, [
    ("Fried egg", "ពងទាចៀន", "煎蛋", 50, False, "1"), ("Extra rice", "បាយបន្ថែម", "加饭", 50, False, "1")],
    max_select=2)

OPTION_SETS = {
    "coffee": [SIZE, SUGAR, ICE, COFFEE_EXTRAS],
    "tea": [SIZE, SUGAR, ICE, TEA_TOPPINGS],
    "juice": [SIZE, SUGAR, ICE],
    "food": [SPICE, FOOD_EXTRAS],
    "rice": [PROTEIN, SPICE, FOOD_EXTRAS],
    "none": [],
}

# name, unit, qty on hand, low threshold, cost per unit in USD
INGREDIENTS = [
    ("Coffee beans", "g", 5000, 1000, 0.025), ("Fresh milk", "ml", 20000, 4000, 0.0018),
    ("Condensed milk", "ml", 5000, 1000, 0.004), ("Oat milk", "ml", 3000, 1000, 0.004),
    ("Tapioca pearls", "g", 3000, 800, 0.006), ("Brown sugar syrup", "ml", 3000, 600, 0.003),
    ("Matcha powder", "g", 800, 200, 0.12), ("Plastic cup", "pcs", 800, 150, 0.06),
    ("Straw", "pcs", 1000, 200, 0.01), ("Jasmine rice", "g", 30000, 5000, 0.0012),
    ("Egg", "pcs", 300, 60, 0.12), ("Chicken breast", "g", 8000, 2000, 0.006),
    ("Mango", "pcs", 60, 15, 0.5),
]

RECIPES = {
    "Iced Latte": [("Coffee beans", 18), ("Fresh milk", 180), ("Plastic cup", 1), ("Straw", 1)],
    "Khmer Iced Coffee": [("Coffee beans", 20), ("Condensed milk", 40), ("Plastic cup", 1), ("Straw", 1)],
    "Americano": [("Coffee beans", 18), ("Plastic cup", 1)],
    "Brown Sugar Boba Milk Tea": [("Fresh milk", 200), ("Tapioca pearls", 60), ("Brown sugar syrup", 30),
                                  ("Plastic cup", 1), ("Straw", 1)],
    "Matcha Latte": [("Matcha powder", 4), ("Fresh milk", 200), ("Plastic cup", 1), ("Straw", 1)],
    "Mango Smoothie": [("Mango", 1), ("Plastic cup", 1), ("Straw", 1)],
    "Fried Rice": [("Jasmine rice", 200), ("Egg", 1), ("Chicken breast", 120)],
    "Mango Sticky Rice": [("Mango", 1)],
}
OPTION_RECIPES = {("Iced Latte", "Extra espresso shot"): [("Coffee beans", 9)],
                  ("Iced Latte", "Oat milk"): [("Oat milk", 180)],
                  ("Fried Rice", "Fried egg"): [("Egg", 1)]}

STAFF = [
    ("owner@lagom.test", "Demo Owner", Role.OWNER), ("admin@lagom.test", "Demo Admin", Role.ADMIN),
    ("cashier@lagom.test", "Demo Cashier", Role.CASHIER), ("kitchen@lagom.test", "Demo Kitchen", Role.KITCHEN),
    ("drinks@lagom.test", "Demo Drinks", Role.DRINKS), ("inventory@lagom.test", "Demo Inventory", Role.INVENTORY),
]


def cents(usd: float) -> int:
    return int(round(usd * 100))


def seed(db, with_staff: bool = True) -> dict:
    if db.scalar(select(Category.id).limit(1)):
        return {"skipped": True}

    cats = {}
    for i, (slug, en, km, zh, station) in enumerate(CATEGORIES):
        cats[slug] = Category(slug=slug, name_en=en, name_km=km, name_zh=zh, sort_order=i, default_station=station)
        db.add(cats[slug])

    products = {}
    for i, (cat, en, km, zh, price, prep, flags, desc, optset) in enumerate(PRODUCTS):
        p = Product(category=cats[cat], name_en=en, name_km=km, name_zh=zh, description_en=desc,
                    price_usd_cents=cents(price), prep_minutes=prep, sort_order=i,
                    is_featured="F" in flags, is_best_seller="B" in flags)
        for gi, grp in enumerate(OPTION_SETS[optset]):
            og = OptionGroup(name_en=grp["name"][0], name_km=grp["name"][1], name_zh=grp["name"][2],
                             selection=grp["sel"], is_required=grp["required"], min_select=grp["min_select"],
                             max_select=grp["max_select"], sort_order=gi)
            for oi, (oen, okm, ozh, delta, default, mult) in enumerate(grp["options"]):
                og.options.append(Option(name_en=oen, name_km=okm, name_zh=ozh, price_delta_usd_cents=delta,
                                         is_default=default, recipe_multiplier=Decimal(mult), sort_order=oi))
            p.option_groups.append(og)
        db.add(p)
        products[en] = p

    supplier = Supplier(name="Phnom Penh Fresh Supply (demo)", phone="")
    db.add(supplier)
    ingredients = {}
    for name, unit, qty, low, cost in INGREDIENTS:
        ingredients[name] = Ingredient(name=name, unit=unit, quantity=Decimal(qty), low_stock_threshold=Decimal(low),
                                       unit_cost_usd_millicents=int(round(cost * 100 * 1000)), supplier=supplier)
        db.add(ingredients[name])
    db.flush()

    for pname, lines in RECIPES.items():
        for iname, qty in lines:
            db.add(RecipeItem(product_id=products[pname].id, ingredient_id=ingredients[iname].id, quantity=Decimal(qty)))
    for (pname, oname), lines in OPTION_RECIPES.items():
        opt = next(o for gr in products[pname].option_groups for o in gr.options if o.name_en == oname)
        for iname, qty in lines:
            db.add(RecipeItem(product_id=products[pname].id, ingredient_id=ingredients[iname].id,
                              option_id=opt.id, quantity=Decimal(qty)))

    for n in range(1, 13):
        db.add(DiningTable(label=f"Table {n:02d}", seats=4 if n <= 8 else 6,
                           area="Indoor" if n <= 8 else "Terrace", sort_order=n))

    db.add(Promotion(title_en="Afternoon coffee hour", title_km="ម៉ោងកាហ្វេពេលរសៀល", title_zh="下午咖啡时光",
                     subtitle_en="Pair any coffee with a Basque cheesecake.",
                     product_id=products["Basque Cheesecake"].id))

    if with_staff:
        pw = hash_password(DEMO_PASSWORD)
        for email, name, role in STAFF:
            if not db.scalar(select(User.id).where(User.email == email)):
                db.add(User(email=email, full_name=name, role=role, password_hash=pw))
    db.commit()
    return {"categories": len(CATEGORIES), "products": len(PRODUCTS), "tables": 12, "ingredients": len(INGREDIENTS)}


def main() -> int:
    if get_settings().is_production:
        print("Refusing to load demo data in production.")
        return 1
    with SessionLocal() as db:
        result = seed(db)
    if result.get("skipped"):
        print("Menu already exists – demo data not loaded again.")
    else:
        print(f"Demo data loaded: {result}")
        print("Demo staff accounts: owner@ / admin@ / cashier@ / kitchen@ / drinks@ / inventory@lagom.test")
        print("Password: value of DEMO_STAFF_PASSWORD (see scripts/seed_demo.py). Development only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
