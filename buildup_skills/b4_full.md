## environment_facts
- Database contains three product datasets with table suffixes _g1, _g2, _g3
- Tables per group: items_gN (products), fdbk_gN (reviews), attrs_gN, taxn_gN, fdbk_stats_g1
- items_g1 schema: ref_id TEXT PK, ttl TEXT, avg_rtg REAL, avg_rtg_30d REAL, rtg_ct INTEGER, prc REAL, str_nm TEXT, main_cat TEXT, desc_txt TEXT, feat_lst TEXT, status TEXT DEFAULT 'active'
- items_g2 schema: ref_id TEXT PK, ttl TEXT, avg_rtg REAL, prc INTEGER, prc_usd REAL, str_nm TEXT, main_cat TEXT, feat_lst TEXT, img_ct INTEGER, prc_v2 INTEGER (no rtg_ct column)
- items_g3 schema: ref_id TEXT PK, ttl TEXT, avg_rtg REAL, rtg_ct INTEGER, prc REAL, str_nm TEXT, main_cat TEXT, desc_txt TEXT
- fdbk_g1 schema: id INTEGER PK AUTOINCREMENT, item_id TEXT, ref_id TEXT, uid TEXT, rtg REAL, ttl TEXT, body TEXT, ts INTEGER, hlp_ct INTEGER, vrf INTEGER, verified_status TEXT, FOREIGN KEY (ref_id) REFERENCES items_g1(ref_id)
- fdbk_g2 schema: id INTEGER PK AUTOINCREMENT, item_id TEXT, ref_id TEXT, uid TEXT, rtg REAL, ttl TEXT, body TEXT, ts INTEGER, hlp_ct INTEGER, vrf TEXT, FOREIGN KEY (ref_id) REFERENCES items_g2(ref_id)
- fdbk_g3 schema: id INTEGER PK AUTOINCREMENT, ref_id TEXT, uid TEXT, rtg REAL, ttl TEXT, body TEXT, ts TEXT, hlp_ct INTEGER, vrf INTEGER, review_year INTEGER, review_month INTEGER, FOREIGN KEY (ref_id) REFERENCES items_g3(ref_id) (no item_id column)
- attrs_g1 schema: ref_id TEXT, attr_key TEXT, attr_val TEXT
- attrs_g3_legacy schema: ref_id TEXT, attr_key TEXT, attr_val TEXT (musical instruments older attribute export)
- product_attributes_g3 schema: ref_id TEXT, attr_key TEXT, attr_val TEXT (musical instruments current attribute feed)
- taxn_g1 schema: ref_id TEXT, cat_lvl INTEGER, cat_nm TEXT, FOREIGN KEY (ref_id) REFERENCES items_g1(ref_id)
- taxn_g2 schema: ref_id TEXT, cat_lvl INTEGER, cat_nm TEXT, FOREIGN KEY (ref_id) REFERENCES items_g2(ref_id)
- ts column: INTEGER in fdbk_g1/fdbk_g2, TEXT in fdbk_g3; Unix epoch milliseconds in fdbk_g1/fdbk_g2 (confirmed: 1600000726870 → '2020-09-13 12:38:46')
- main_cat values include: 'All Electronics', 'Amazon Home', 'Office Products', 'Musical Instruments', 'Computers', 'Cell Phones & Accessories', 'Home Audio & Theater', 'GPS & Navigation', 'Camera & Photo', 'Arts, Crafts & Sewing', 'Industrial & Scientific', 'AMAZON FASHION', 'Tools & Home Improvement', 'Health & Personal Care', 'Sports & Outdoors', 'Software', 'Car Electronics', 'Amazon Devices', 'All Beauty', 'Portable Audio & Accessories', 'Automotive', NULL
- Group mappings: _g1 = Office Products (main_cat='Office Products'), _g2 = Electronics (main_cat spans 'All Electronics', 'Computers', 'Cell Phones & Accessories', 'Home Audio & Theater', 'GPS & Navigation', 'Camera & Photo', 'Car Electronics', 'Amazon Devices', 'Portable Audio & Accessories'), _g3 = Musical Instruments (main_cat='Musical Instruments')
- fdbk_gN tables: join to items_gN on ref_id (not item_id); fdbk_g3 lacks item_id column entirely
- vrf column: INTEGER 0/1 in fdbk_g1/fdbk_g3; TEXT in fdbk_g2 (values include 0/1 and false/true)
- status column in items_g1: 'active', 'archived' (DEFAULT 'active')
- items_g1 prc range: 0.18 to 2966.01 (REAL)
- items_g2 prc: INTEGER type; prc_usd and prc_v2 also present; prc_usd is the dollar price (confirmed: avg prc_usd ≈ 101.8 for img_ct >= 3, prc avg was 10158.37)
- items_g2 prc appears to be in cents (100× dollar price): avg prc ≈ 10158 vs avg prc_usd ≈ 101.8

## general
- Query budget: 15 exploratory queries per question; results capped at 50 rows
- Use aggregates (COUNT, AVG), LIMIT, or filters to inspect large tables
- Schema inspection: .tables, PRAGMA table_info(table_name), SELECT sql FROM sqlite_master WHERE name='table_name'

## strategy
- Identify table group by checking main_cat values in items_gN tables
- Join fdbk_gN to items_gN on ref_id (not item_id) for product attributes
- For electronics, filter on multiple main_cat values — not just 'All Electronics'
- For verified reviews: filter vrf = 1 (integer, not boolean strings) in fdbk_g1/fdbk_g3; in fdbk_g2 use vrf=1 or vrf='true'
- For price constraints: join to items table and filter prc <= value; note items_g2.prc is INTEGER (cents), use prc_usd for dollar amounts
- For timestamp filtering: ts is Unix epoch milliseconds in fdbk_g1/fdbk_g2; use datetime(ts/1000, 'unixepoch') for date extraction; fdbk_g3.ts is TEXT
- For taxonomy "broadest category below department": use cat_lvl = 1 (level 0 = department, level 1 = broadest subcategory)
- For mean absolute deviation: compute AVG(ABS(prc - overall_avg)) not raw sum of deviations

## failure_modes
- Joining fdbk_gN on item_id instead of ref_id causes incomplete or wrong results (fdbk_g3 lacks item_id entirely)
- Using single main_cat value for electronics ('All Electronics' only) misses products in 'Computers', 'Cell Phones & Accessories', etc.
- Assuming vrf is boolean/string ('true'/'false') instead of integer 0/1
- Using items_g2.rtg_ct column that does not exist (must count reviews from fdbk_g2)
- Computing mean absolute deviation incorrectly (e.g., using SUM instead of AVG, or wrong price column)
- Using prc from items_g2 without converting cents to dollars (prc_usd is the dollar price)
- Filtering year 2022 on ts without converting from milliseconds to seconds for datetime functions
- Confusing attrs_g3_legacy vs product_attributes_g3 for musical instruments attribute feeds

## open_questions
- Schema for fdbk_stats_g1 not yet inspected