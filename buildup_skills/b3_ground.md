## environment_facts
<!-- Concrete, reusable facts about the fixed environment: exact table/column names, data formats/units, join keys, value encodings -->

- Table group mapping by main category:
  - **Musical Instruments** (main_cat='Musical Instruments'): `items_g1`, `fdbk_g1`, `taxn_g1`, `attrs_g1`, `fdbk_stats_g1`
  - **All Electronics** (main_cat='All Electronics'): `items_g2`, `fdbk_g2`, `taxn_g2`
  - **Office Products** (main_cat='Office Products'): `items_g3`, `fdbk_g3`, `attrs_g3`

- Exact schema for `items_g1`: `ref_id`, `ttl`, `avg_rtg`, `avg_rtg_30d`, `rtg_ct`, `prc`, `str_nm`, `main_cat`, `desc_txt`, `feat_lst` — note `avg_rtg_30d` and `rtg_ct` present, no `prc_usd`

- Exact schema for `items_g2`: `ref_id`, `ttl`, `avg_rtg`, `prc`, `prc_usd`, `str_nm`, `main_cat`, `feat_lst`, `img_ct` — note `prc_usd` and `img_ct` present, no `avg_rtg_30d`, `rtg_ct`, or `desc_txt`

- Exact schema for `items_g3`: `ref_id`, `ttl`, `avg_rtg`, `rtg_ct`, `prc`, `str_nm`, `main_cat`, `desc_txt` — note `rtg_ct` present, no `prc_usd`, `avg_rtg_30d`, `feat_lst`, or `img_ct`

## general
<!-- General principles and rules for this task: SQL query constraints, output format requirements, category identification methodology -->

## strategy
<!-- High-level strategies and approaches: schema exploration order, how to map tables to product categories, efficient query construction -->

## failure_modes
<!-- Common failure patterns to avoid: wrong table group identification, incorrect date parsing, inefficient query usage -->

## open_questions
<!-- Unverified or thinly-corroborated claims to confirm against authoritative sources before trusting; reconstructed structures to read verbatim rather than assume -->