-- Benchmark the optimiser against the spread that was available each day.
--
-- For a battery of duration D hours cycling once a day, the most it can earn per MW is
-- roughly TB_D: the sum of the D dearest hours minus the D cheapest. So we compare the
-- optimiser's realised £/MW/day with TB_D and call the ratio the capture rate. It can't
-- reach 100%: TB_D ignores round-trip losses and the cycle cost.
--
-- Parameters: $power_mw, $capacity_mwh, $efficiency select the battery; $hours = D.

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
),
spread AS (
    SELECT settlement_date,
           sum(price) FILTER (WHERE rank_high <= $hours)
         - sum(price) FILTER (WHERE rank_low  <= $hours) AS tb_d
    FROM ranked
    GROUP BY settlement_date
    HAVING count(*) = 24
)
SELECT r.settlement_date,
       round(s.tb_d, 2)                          AS tb_d,
       round(r.net_profit / r.power_mw, 2)       AS gbp_per_mw,
       round(r.net_profit / r.power_mw / s.tb_d, 3) AS capture_rate,
       round(r.cycles, 2)                        AS cycles
FROM runs r
JOIN spread s USING (settlement_date)
WHERE r.power_mw = $power_mw
  AND r.capacity_mwh = $capacity_mwh
  AND r.efficiency = $efficiency
ORDER BY r.settlement_date;
