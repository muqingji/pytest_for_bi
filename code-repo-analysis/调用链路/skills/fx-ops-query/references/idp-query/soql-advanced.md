# fx-ops idp query — SOQL 高级用法

SOQL 函数在排查场景中的组合用法。函数速查表见 soql-functions.md。

## 场景 1：按时间维度统计趋势

排查"最近一周新增了多少客户"或"按月统计新增趋势"。

```bash
# 按月统计新增客户数
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT CALENDAR_YEAR(create_time) AS y, CALENDAR_MONTH(create_time) AS m, COUNT(*) AS total
  FROM AccountObj
  GROUP BY CALENDAR_YEAR(create_time), CALENDAR_MONTH(create_time)
  ORDER BY y DESC, m DESC LIMIT 24" -j

# 按季度统计
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT CALENDAR_YEAR(create_time) AS y, CALENDAR_QUARTER(create_time) AS q, COUNT(*) AS total
  FROM AccountObj
  GROUP BY CALENDAR_YEAR(create_time), CALENDAR_QUARTER(create_time)
  ORDER BY y DESC, q DESC LIMIT 12" -j
```

日期函数也支持 WHERE 过滤，缩小统计范围：

```bash
# 只看 2026 年的数据，按周统计
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT WEEK_IN_YEAR(create_time) AS week, COUNT(*) AS total
  FROM AccountObj
  WHERE CALENDAR_YEAR(create_time) = 2026
  GROUP BY WEEK_IN_YEAR(create_time)
  ORDER BY week DESC" -j
```

## 场景 2：条件计数 — 状态分布

排查"各个状态有多少条数据"，不需要多次查询。

```bash
# 一次查询得到多个状态计数
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT COUNT_IF(status = 'in_progress') AS active,
     COUNT_IF(status = 'completed') AS done,
     COUNT_IF(status = 'cancelled') AS cancelled,
     COUNT(*) AS total
  FROM AccountObj" -j
```

按分组维度做条件计数 — "每个负责人的进行中任务数"：

```bash
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT owner,
     COUNT(*) AS total,
     COUNT_IF(status = 'in_progress') AS active,
     COUNT_IF(status = 'completed') AS done
  FROM AccountObj
  GROUP BY owner
  ORDER BY active DESC LIMIT 20" -j
```

`COUNT_IF` 支持组合条件：

```bash
# 统计高价值活跃客户
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT COUNT_IF(status = 'Active' AND amount > 10000) AS highValueActive
  FROM AccountObj" -j

# 统计"活跃或待审核"的数量
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT COUNT_IF(status = 'Active' OR status = 'Pending') AS openCount
  FROM AccountObj" -j

# 排除某个状态
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT COUNT_IF(NOT status = 'Closed') AS notClosed
  FROM AccountObj" -j
```

## 场景 3：大小写模糊匹配

客户名可能混用大小写（"ACME"、"acme"、"Acme"），用 LOWER 统一后匹配。

```bash
# 忽略大小写搜索客户名
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT id, name FROM AccountObj
  WHERE LOWER(name) LIKE 'acme%'
  LIMIT 20" -j

# 按统一格式排序
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT id, name, LOWER(name) AS sortKey
  FROM AccountObj
  ORDER BY LOWER(name) ASC LIMIT 50" -j

# 查重：同名（忽略大小写）有多少条
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT LOWER(name) AS normalizedName, COUNT(*) AS cnt
  FROM AccountObj
  GROUP BY LOWER(name)
  HAVING COUNT(*) > 1
  ORDER BY cnt DESC LIMIT 20" -j
```

## 场景 4：去重计数

排查"有多少不同的负责人"或"字段值的唯一数"。

```bash
# 负责人去重计数
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT COUNT_DISTINCT(owner) AS ownerCount FROM AccountObj" -j

# 按年统计新增去重客户数
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT CALENDAR_YEAR(create_time) AS year,
     COUNT_DISTINCT(name) AS uniqueNames
  FROM AccountObj
  GROUP BY CALENDAR_YEAR(create_time)
  ORDER BY year DESC" -j

# HAVING 过滤：只看去重数 > 5 的年份
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT CALENDAR_YEAR(create_time) AS year,
     COUNT_DISTINCT(name) AS uniqueNames
  FROM AccountObj
  GROUP BY CALENDAR_YEAR(create_time)
  HAVING COUNT_DISTINCT(name) > 5
  ORDER BY year DESC" -j
```

## 场景 5：字符串截取与拼接

排查时需要截取字段前几位做分组，或拼接多个字段做展示。

```bash
# 按名称首字母分组统计
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT UPPER(LEFT(name, 1)) AS initial, COUNT(*) AS total
  FROM AccountObj
  GROUP BY UPPER(LEFT(name, 1))
  ORDER BY total DESC" -j

# 拼接展示字段
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT CONCAT(name, ' (', id, ')') AS displayName FROM AccountObj LIMIT 20" -j

# 清理空格后匹配
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT id, TRIM(name) AS cleanName FROM AccountObj
  WHERE TRIM(name) = 'Acme' LIMIT 20" -j
```

## 场景 6：数值处理

对金额、数量字段做数学运算和分组统计。

```bash
# 按金额区间统计
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT ROUND(amount, -2) AS bracket, COUNT(*) AS total
  FROM AccountObj
  GROUP BY ROUND(amount, -2)
  ORDER BY bracket DESC" -j

# 字符串字段中的数值做数学运算
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT AVG(amount) AS avgAmount,
     MIN(amount) AS minAmount,
     MAX(amount) AS maxAmount,
     SUM(amount) AS totalAmount
  FROM AccountObj" -j
```

## 场景 7：空值处理

排查时遇到空值需要降级显示。

```bash
# 空值降级为默认值
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT id, COALESCE(email, 'no-email') AS contactEmail FROM AccountObj LIMIT 20" -j

# 空字符串转 NULL
fx-ops idp --profile <profile> object query -t 74164 --soql \
 "SELECT id, NULLIF(status, '') AS statusOrNull FROM AccountObj LIMIT 20" -j
```

## 常见错误

| 错误信息 | 原因 | 修复 |
| --- | --- | --- |
| `Function COUNT_IF requires an alias` | SELECT 中的 COUNT_IF 没有写 `AS name` | 加 `AS activeCount` 等别名 |
| `Function COUNT_IF cannot be used in filter` | 在 WHERE 中使用了聚合函数 | 把 COUNT_IF 放在 SELECT 或 HAVING 中 |
| `Function CONVERTTIMEZONE can only be used inside a date function` | CONVERTTIMEZONE 单独使用 | 改为 `CALENDAR_YEAR(CONVERTTIMEZONE(field))` |
| `Function NOW cannot be used in select` | NOW() 只能在 WHERE/HAVING 中 | 改为 `WHERE create_time > NOW()` |
| `Function XXX expects N arguments` | 参数数量不对 | 查速查表确认参数个数 |
| `COUNT_IF requires a boolean condition` | COUNT_IF() 括号内为空 | 写入条件表达式 |

## 限制

- 聚合函数（COUNT、SUM、AVG、MIN、MAX、COUNT_DISTINCT、COUNT_IF）不能用在 WHERE 中，HAVING 中可以使用
- `SELECT *` 不能和聚合函数同时使用
- 函数嵌套层数没有硬限制，但建议不超过 3 层
- `COUNT_IF` 的条件中不能嵌套聚合函数
- 没有 CASE/WHEN 表达式，条件计数用 `COUNT_IF` 替代
- 没有子查询
