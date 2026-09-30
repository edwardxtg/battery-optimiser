-- Benchmark the optimiser against the spread that was available each day.
--
-- For a battery of duration D hours cycling once a day, the most it can earn per MW is
-- roughly TB_D: the sum of the D dearest hours minus the D cheapest. So we compare the
-- optimiser's realised £/MW/day with TB_D and call the ratio the capture rate. TB_D ignores
-- round-trip losses and cycle cost, which pull capture down, but it also assumes one cycle
-- on hourly averages, so on double-peak days the optimiser can capture more than 100%.
--
-- Parameters: $power_mw, $capacity_mwh, $efficiency select the battery; $hours = D.

WITH complete_days AS (
    -- Normal 24-hour UK days with all 48 half-hours. Excludes days with missing
    -- (zero-volume) periods and clock-change days (46 or 50 periods) - including a 50-period
    -- autumn day that happens to be missing two periods and so has 48 rows.
    SELECT settlement_date
    FROM prices
    GROUP BY settlement_date
    HAVING count(*) = 48
       AND date_diff('minute', timezone('Europe/London', settlement_date::TIMESTAMP),
                     timezone('Europe/London', (settlement_date + 1)::TIMESTAMP)) = 1440
),
hourly AS (
    SELECT settlement_date,
           (settlement_period - 1) // 2 AS hour,
           avg(price)                  AS price
    FROM prices
    WHERE settlement_date IN (SELECT settlement_date FROM complete_days)
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
