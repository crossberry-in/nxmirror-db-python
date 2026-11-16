"""02 — SQL in full: exec, query, and the query builder

    python examples/02_sql_crud.py

Every NxDB SQL database is a real, isolated SQLite engine behind the API:
genuine DDL, prepared statements, JOINs, transactions, indexes.
"""
from config import sql_creds, banner   # also puts the repo root on sys.path
from nxmirror_db import connect

db = connect(**sql_creds())

# ---------- 1. DDL with exec() (multi-statement batch, no parameters) ----------
banner("exec() — CREATE TABLE + INDEX")
db.exec("""
  CREATE TABLE IF NOT EXISTS products (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    price    REAL NOT NULL,
    stock    INTEGER NOT NULL DEFAULT 0,
    active   INTEGER NOT NULL DEFAULT 1
  );
  CREATE INDEX IF NOT EXISTS products_price ON products(price);
""")

# ---------- 2. INSERT with query() + prepared parameters ----------
banner("query() — parameterized INSERT")
ins = db.query("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", ["Coffee 250g", 7.5, 120])
print("changes:", ins["changes"], "lastInsertRowid:", ins["lastInsertRowid"])

ids = [int(ins["lastInsertRowid"])]
for name, price, stock in [("Tea 100g", 3.25, 80), ("Sugar 1kg", 1.99, 200), ("Milk 1L", 1.49, 0)]:
    r = db.query("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", [name, price, stock])
    ids.append(int(r["lastInsertRowid"]))
print("inserted ids:", ", ".join(map(str, ids)))

# ---------- 3. SELECT: WHERE / ORDER BY / aggregate ----------
banner("query() — SELECT with parameters")
cheap = db.query("SELECT id, name, price FROM products WHERE price < ? AND stock > ? ORDER BY price ASC", [5, 0])
for row in cheap["rows"]:
    print(row)

stats = db.query("SELECT COUNT(*) AS products, ROUND(SUM(price * stock), 2) AS stock_value, "
                 "MIN(price) AS cheapest FROM products")
for row in stats["rows"]:
    print(row)

# ---------- 4. JOIN ----------
banner("query() — JOIN demo")
db.exec(f"""
  CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty        INTEGER NOT NULL
  );
  INSERT INTO orders (product_id, qty) VALUES ({ids[0]}, 2), ({ids[1]}, 5);
""")
joined = db.query("""
  SELECT o.id AS order_id, p.name, p.price, o.qty, ROUND(p.price * o.qty, 2) AS total
  FROM orders o JOIN products p ON p.id = o.product_id
  ORDER BY total DESC
""")
for row in joined["rows"]:
    print(row)

# ---------- 5. Transaction as an exec() batch ----------
banner("exec() — BEGIN … COMMIT transaction")
db.exec(f"""
  BEGIN;
  UPDATE products SET stock = stock - 2 WHERE id = {ids[0]};
  UPDATE products SET stock = stock - 5 WHERE id = {ids[1]};
  INSERT INTO orders (product_id, qty) VALUES ({ids[0]}, 2);
  COMMIT;
""")
after = db.query("SELECT id, name, stock FROM products WHERE id IN (?, ?)", [ids[0], ids[1]])
for row in after["rows"]:
    print(row)

# ---------- 6. Query builder — same thing, no SQL strings ----------
banner("table() — query builder")
db.table("products").insert({"name": "Honey 500g", "price": 4.75, "stock": 30})
db.table("products").insert([
    {"name": "Salt 500g", "price": 0.99, "stock": 500},
    {"name": "Pepper 50g", "price": 2.5, "stock": 45},
])

all_rows = db.table("products").select()
print("all rows:", len(all_rows["rows"]))   # select() returns the full result object — rows live in ["rows"]

cols = db.table("products").select(["name", "price"])
print("column pick:", cols["rows"][0])

filtered = (db.table("products")
            .where("price", ">", 2)          # eq | ne | gt | lt | gte | lte | like | in
            .where({"active": True})         # object form (AND-combined)
            .order_by("price", "DESC")
            .limit(3)
            .offset(0)
            .select())
for row in filtered["rows"]:
    print(row)

n = db.table("products").where("stock", ">", 10).count()
print("count(stock > 10):", n)

db.table("products").update({"price": 7.99}, {"id": ids[0]})   # SET … WHERE
db.table("products").delete({"name": "Salt 500g"})

print("final row count:", db.table("products").count())

# ---------- 7. Clean up this demo's tables ----------
db.exec("DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products;")
print("\nOK — SQL demo finished (demo tables dropped).")
