-- TBX spreads per settlement day: the sum of the X dearest hours minus the sum of the
-- X cheapest. TB2 is the standard proxy for what a 2-hour battery can earn per MW from one
-- cycle a day; TB4 for a 4-hour battery. Computed on hourly-average prices, as the
-- industry convention is, and only for complete days (clock-change days are skipped).

WITH hourly AS (
    SELECT settlement_date,
           (settlement_period - 1) // 2 AS hour,
           avg(price)                  AS price
    FROM prices
    GROUP BY settlement_date, hour
),
ranked AS (
    SELECT settlement_date,
           price,
           row_number() OVER (PARTITION BY settlement_date ORDER BY price DESC) AS rank_high,
           row_number() OVER (PARTITION BY settlement_date ORDER BY price ASC)  AS rank_low
    FROM hourly
)
SELECT settlement_date,
       round(avg(price), 2)                                                            AS mean_price,
       round(sum(price) FILTER (WHERE rank_high <= 1) - sum(price) FILTER (WHERE rank_low <= 1), 2) AS tb1,
       round(sum(price) FILTER (WHERE rank_high <= 2) - sum(price) FILTER (WHERE rank_low <= 2), 2) AS tb2,
       round(sum(price) FILTER (WHERE rank_high <= 4) - sum(price) FILTER (WHERE rank_low <= 4), 2) AS tb4
FROM ranked
GROUP BY settlement_date
HAVING count(*) = 24
ORDER BY settlement_date;
