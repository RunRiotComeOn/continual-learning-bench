## environment_facts
<!-- Concrete, reusable facts about the fixed database environment: exact table/column names (e.g., items_g1, items_g2, items_g3, attrs_g1, taxn_g1), data formats/units (e.g., price in dollars vs. local currency), join keys (e.g., ref_id), value encodings, and which table suffix (_g1, _g2, _g3) maps to which product category -->

## general
<!-- General principles and rules for database exploration and answering questions -->

## schema_exploration
<!-- Systematic approaches for discovering table schemas, column meanings, and relationships between tables (e.g., items, attrs, taxn, fdbk tables) -->

## dataset_mapping
<!-- Rules for determining which table group (_g1, _g2, _g3) corresponds to which product category (electronics, office products, musical instruments) -->

## price_column_selection
<!-- Guidelines for identifying the correct price column to use (e.g., prc vs. prc_usd) and handling different data types (INTEGER vs. REAL) across tables -->

## strategy
<!-- High-level strategies for efficiently using the limited query budget (15 queries) and avoiding common pitfalls like capped result sets -->

## failure_modes
<!-- Common failure patterns to avoid, such as using wrong price columns, wrong table groups, incorrect averaging methods, or exhausting queries without verification -->

## open_questions
<!-- Unverified or thinly-corroborated claims to confirm against authoritative sources: exact mapping of _g1/_g2/_g3 to categories, whether to use weighted or unweighted averages, handling of NULL values in price columns, and interpretation of "electronics products" (single category vs. multiple related categories) -->