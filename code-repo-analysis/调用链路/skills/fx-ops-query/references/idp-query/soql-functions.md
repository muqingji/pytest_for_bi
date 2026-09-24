# fx-ops idp query — SOQL 函数

Object Query 的 SOQL 支持在 SELECT、WHERE、GROUP BY、HAVING、ORDER BY 中使用函数表达式。

## 快速参考

### 聚合函数

只能在 SELECT 和 HAVING 中使用。必须使用 AS 别名。

```sql
SELECT COUNT(*) AS total FROM AccountObj
SELECT owner, COUNT(*) AS total FROM AccountObj GROUP BY owner
SELECT COUNT_DISTINCT(name) AS nameCount FROM AccountObj
SELECT COUNT_IF(status = 'in_progress') AS activeCount FROM AccountObj
SELECT COUNT_IF(status = 'Active' AND amount > 100) AS highValue FROM AccountObj
```

`COUNT_IF` 支持全部 WHERE 条件操作符：`=`, `!=`, `>`, `<`, `>=`, `<=`, `AND`, `OR`, `NOT`, `IN`, `BETWEEN`, `LIKE`, `IS NULL`。

### 字符串函数

```sql
SELECT LOWER(name) AS normalizedName FROM AccountObj
SELECT UPPER(name) AS upperName FROM AccountObj
SELECT TRIM(name) AS trimmed FROM AccountObj
SELECT LENGTH(name) AS nameLength FROM AccountObj
SELECT SUBSTRING(name, 1, 3) AS shortName FROM AccountObj
SELECT LEFT(name, 5) AS prefix FROM AccountObj
SELECT RIGHT(name, 3) AS suffix FROM AccountObj
SELECT REPLACE(name, 'old', 'new') AS replaced FROM AccountObj
SELECT CONCAT(name, '-', id) AS combined FROM AccountObj
```

可以在 WHERE 和 ORDER BY 中使用：

```sql
SELECT id FROM AccountObj WHERE LOWER(name) LIKE 'acme%' ORDER BY LOWER(name) ASC
```

### 日期时间函数

```sql
SELECT CALENDAR_YEAR(create_time) AS year FROM AccountObj
SELECT CALENDAR_MONTH(create_time) AS month FROM AccountObj
SELECT CALENDAR_QUARTER(create_time) AS quarter FROM AccountObj
SELECT DAY_IN_MONTH(create_time) AS day FROM AccountObj
SELECT DAY_IN_WEEK(create_time) AS weekday FROM AccountObj
SELECT DAY_IN_YEAR(create_time) AS yearday FROM AccountObj
SELECT DAY_ONLY(create_time) AS dateOnly FROM AccountObj
SELECT HOUR_IN_DAY(create_time) AS hour FROM AccountObj
SELECT WEEK_IN_YEAR(create_time) AS week FROM AccountObj
SELECT WEEK_IN_MONTH(create_time) AS weekOfMonth FROM AccountObj
```

常用模式 — 按时间维度分组统计：

```sql
SELECT CALENDAR_YEAR(create_time) AS year,
    CALENDAR_MONTH(create_time) AS month,
    COUNT(*) AS total
FROM AccountObj
GROUP BY CALENDAR_YEAR(create_time), CALENDAR_MONTH(create_time)
ORDER BY year DESC, month DESC
LIMIT 20
```

`CONVERTTIMEZONE` 只能嵌套在日期函数中：

```sql
-- 正确：嵌套在日期函数内
SELECT CALENDAR_YEAR(CONVERTTIMEZONE(create_time)) AS year FROM AccountObj

-- 错误：不能单独使用
SELECT CONVERTTIMEZONE(create_time) FROM AccountObj
```

### 数学函数

```sql
SELECT ABS(amount) AS absAmount FROM AccountObj
SELECT ROUND(amount, 2) AS rounded FROM AccountObj
SELECT CEIL(amount) AS ceiling FROM AccountObj
SELECT FLOOR(amount) AS floor_val FROM AccountObj
SELECT MOD(amount, 10) AS remainder FROM AccountObj
SELECT POWER(amount, 2) AS squared FROM AccountObj
```

### 条件函数

```sql
SELECT COALESCE(email, 'N/A') AS contactEmail FROM AccountObj
SELECT NULLIF(status, '') AS statusOrNull FROM AccountObj
```

## 位置限制

| 位置 | 聚合 | 字符串/数学/条件 | 日期时间 | NOW() |
| --- | --- | --- | --- | --- |
| SELECT | 是 | 是 | 是 | 否 |
| WHERE | 否 | 是 | 是 | 是 |
| GROUP BY | 否 | 是 | 是 | 否 |
| HAVING | 是 | 是 | 是 | 是 |
| ORDER BY | 否 | 是 | 是 | 否 |

## CLI 示例

```bash
# 字符串函数过滤
fx-ops idp --profile <profile> object query -t 74164 \
 --soql "SELECT id, name FROM AccountObj WHERE LOWER(name) LIKE 'acme%' LIMIT 20" -j

# 按时间分组统计
fx-ops idp --profile <profile> object query -t 74164 \
 --soql "SELECT CALENDAR_YEAR(create_time) AS year, COUNT(*) AS total FROM AccountObj GROUP BY CALENDAR_YEAR(create_time)" -j

# 条件聚合
fx-ops idp --profile <profile> object query -t 74164 \
 --soql "SELECT COUNT_IF(status = 'in_progress') AS activeCount FROM AccountObj" -j
```
