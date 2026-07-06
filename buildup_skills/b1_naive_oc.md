## strategy

- **Distinguish between product identifier columns carefully.** Trial 1 (1253 vs 1832, 2-star or below reviews) shows undercounting when comparing distinct values between "primary" vs "non-primary" product IDs; explicitly verify column names and ensure proper filtering on rating ≤ 2.0.
- **Use LENGTH() for character counts with AVG aggregation.** Trial 2 (correct: 101.8) succeeded by computing `AVG(LENGTH(review_body))` grouped by star rating and comparing 1-star vs 5-star; verify review text column contains actual character data, not NULLs.
- **Computing category-wide averages: exclude zeros and handle NULLs explicitly.** Trial 3 (25.91 vs 17.27) overestimated percentage—the category average must be computed from actual priced products only; likely included zeros or NULLs in denominator, or comparison logic was inverted.
- **Match exact answer formatting requirements.** Trial 4 failed on quotes—output `'2020-01'` when answer required `2020-01`; never wrap string answers in quotes unless explicitly instructed.
- **Anti-join or NOT EXISTS for "present in X but absent in Y" patterns.** Trial 5 (188 vs 267) undercounted products with reviews but no attributes; likely used INNER JOIN or incorrect exclusion logic instead of `NOT EXISTS` or `LEFT JOIN ... WHERE attributes.product_id IS NULL`.
- **For presence/absence checks, prefer `LEFT JOIN ... IS NULL` or `NOT EXISTS` over `NOT IN` (which fails on NULLs).** Trial 5 pattern suggests possible NULL handling issue with NOT IN.
- **Query budget awareness: avoid excessive exploratory queries.** Trials indicate 14-15 queries used per question; budget-conscious approach needed. Question 11 exceeded budget completely—prioritize efficient schema inspection and targeted queries.
- **Date filtering: verify date column format and extraction method.** Trial 2 (841 vs 1867, Q4 2021 reviews): undercount suggests possible date parsing issue—verify month extraction yields correct values (e.g., `STRFTIME('%m', date)` vs `strftime('%m', date, 'unixepoch')` or string parsing on `YYYY-MM-DD` format).
- **"Zero reviews" means explicit anti-join on reviews table, not NULL star rating.** Trial 3 (37.26 vs 29.93): likely misidentified "zero reviews"—must use `NOT EXISTS` or `LEFT JOIN reviews IS NULL` to find products lacking any review records, not `star_rating = 0` or NULL ratings.
- **Multi-category reviewer queries: join reviews→products→categories correctly.** Trial 5 (5.14 vs 1.03, multi-category reviewers): massive overestimate suggests denominator error—likely counted reviewers instead of percentage, or failed to properly count distinct reviewers vs distinct reviewer-category pairs.
- **Price filter boundary conditions: verify if NULL prices are "with price" or "without price".** Trial 2 (0.15 vs 0.12): 0.03 difference suggests misclassification—products with `NULL` price should be "without price", but check if `price = 0` or empty string also counts as "without price".
- **Percentage calculation: ensure numerator and denominator filters are identical except rating.** Trial 1 (10.45 vs 10.22): small error suggests filter mismatch—verify same `review_body > 500` AND `list_price <= 40` constraints applied to both 1-star subset and total.
- **Column name precision: verify `list_price` vs `price` and other variants.** Trial 1 used "list price" in question but schema may have `list_price` or similar; always confirm exact column names.
- **Median calculation requires proper percentile computation, not averaging.** Trial 1 (19.32 vs 22.09): likely used `AVG()` or incorrect percentile method; use `PERCENTILE_CONT(0.5)` within a subquery or proper median algorithm, and verify inclusion of "at least one catalog image" and "positive list price" filters.
- **Mean/median baseline calculations must exclude NULLs/zeros consistently.** Trial 3 (110 vs 1049): massive undercount suggests baseline mean was computed incorrectly or filter misapplied—"15% higher than mean" requires precise mean of "positive list price" products only.
- **"Positive list price" strictly means `> 0`, not `>= 0` or `IS NOT NULL`.** Trials 1, 3, 5 show pattern: electronics with "positive list price" must exclude zeros explicitly; `NULL` and `0` are both non-positive.
- **Image count filters: verify column name (likely `images`, `image_count`, `num_images`, etc.).** Trial 5 (52.94 vs 101.8): "at least three images" filter may have used wrong column or comparison; schema inspection critical before aggregation.
- **Missing timestamp detection: check for NULL or empty string, not just malformed dates.** Trial 2 (10.3 vs 16.3): "missing full event timestamp" likely means `NULL` or empty in timestamp column; verify against products priced above category mean with positive prices.

## failure_modes

- **Undercounting distinct product IDs** when filtering on ratings (Trial 1: 1253 vs 1832)—likely wrong column selected or rating filter misapplied
- **Percentage calculation errors** from incorrect denominator or inclusion of zero/NULL prices (Trial 3: 25.91 vs 17.27)
- **Quote formatting in output** (Trial 4: `'2020-01'` vs `2020-01`)
- **Undercounting in anti-join scenarios** (Trial 5: 188 vs 267)—exclusion logic missing valid products
- **NULL handling in NOT IN or joins** causing unexpected row elimination
- **Query budget exhaustion** (Trial 11: exceeded budget)—inefficient exploration without clear query plan
- **Date extraction errors** causing undercount (Trial 2: 841 vs 1867)—format mismatch or wrong month extraction
- **Misinterpreting "zero reviews" as NULL rating vs absent review record** (Trial 3: 37.26 vs 29.93)—significantly inflates denominator
- **Overcounting in multi-category percentage** (Trial 5: 5.14 vs 1.03)—likely wrong denominator or duplicate counting in numerator
- **Small arithmetic errors in percentage calculations** (Trial 1: 10.45 vs 10.22)—filter or rounding at wrong precision
- **Misclassification of NULL vs zero prices** (Trial 2: 0.15 vs 0.12)—"with price" likely excludes NULLs but may include zeros
- **Underestimating averages** from excluding valid high-priced products (Trial 3: 44.67 vs 96.23)—massive gap suggests filtering zeros/NULLs removed most data or wrong column used
- **Overestimating averages** from insufficient filtering (Trial 4: 4.27 vs 4.11)—$50 filter may be misapplied or wrong price column used
- **Query budget exceeded on simple date filtering** (Trial 5: Q20 exceeded budget)—over-engineering simple queries
- **Median computation errors** (Trial 1: 19.32 vs 22.09)—using mean instead of median or incorrect percentile method
- **Severe undercounting with percentage threshold filters** (Trial 3: 110 vs 1049)—baseline mean computation likely wrong or filter "15% higher" misapplied

## environment_facts

- Multiple product identifier columns exist per dataset (e.g., primary vs non-primary); must verify which column contains desired ID type.
- Star ratings stored as decimal values (e.g., 2.0); use `<= 2.0` not `< 2`.
- `review_body` column contains actual review text; `LENGTH()` works for character counts.
- Answer format is exact: year-month as `YYYY-MM` without quotes, numbers without formatting.
- Attributes data is separate table; products with reviews may lack attribute records entirely.
- Price columns may contain zeros that must be explicitly excluded from average calculations.
- SQLite database with three product datasets: electronics, office products, musical instruments (reviews).
- **Musical instruments: brand column exists; "Fender" is the most common brand.**
- **Review dates stored in parseable format; verify before extracting quarters/months.**
- **"Zero reviews" requires anti-join logic: products table LEFT JOIN reviews WHERE reviews.product_id IS NULL.**
- **Reviewers identified by `reviewer_id`; may review products across categories—track per-reviewer category diversity.**
- **Attribute data exists for electronics and office products only** (two categories per Trial 4 success pattern).
- **"Listed price" likely maps to `list_price` or `price` column—verify exact name per dataset.**
- **Electronics products average price is $96.23, not ~$45**—implying many products have no price or zero price that should be excluded from "average listed price of electronics products".
- **Office products: `> $50` filter yields average rating 4.11, not 4.27**—price column and filter boundary are sensitive.
- **Date columns exist with parseable year information; 5254 office products listed before 2015**—simple `YEAR(listing_date) < 2015` or equivalent should work efficiently.
- **Electronics with "positive list price" and images: median is $22.09, not $19.32**—requires proper median calculation, not mean.
- **"At least three images" for electronics: average list price is $101.8, not $52.94**—suggests image count column may be `images` or similar, and high-price products have more images.
- **Electronics "15% above mean list price": 1049 products, not 110**—baseline mean must be computed on all positive-priced electronics, then 115% threshold applied.