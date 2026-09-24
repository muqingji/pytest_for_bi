# Grafana 看板 `env` 变量选项（专属云）

> **落点说明**：本文件在 skill 内可被 Agent 加载；勿依赖 `output/`（gitignore）中的临时文档。  
> 数据取自 foneshare 活跃运维看板 `templating` 的 `env`（custom）定义，联调日 2026-07-23。若看板改枚举，以 `dashboard get` 为准并回写本表。

## 用法

| 项 | 值 |
| --- | --- |
| IDP grafana profile | **固定** `foneshare`（线下 `firstshare`） |
| 看板变量 | `var-env=<下表 value>` |
| 查数 | 展开 `$env` 后再 `idp grafana query` |

**不要**用 `idp grafana --profile mengniu`；专属云无 Grafana IDP。选云靠 `env`。

## 选项全集（并集）

来源并集：`灭火全景图 - foneshare`（19）∪ `灭火全景图 - clouds`（25）→ **25** 个 value：

`ale`, `allink8s`, `chinatower`, `cloudmodel`, `cpgc`, `foneshare`, `forsharecrm`, `hexagonmi`, `hisense`, `hsyk`, `hwc`, `hws`, `iflytek`, `kehua`, `kemaicrm`, `ksc`, `mengniu`, `sbt`, `teleagi`, `ucd`, `ucd-test`, `wingd`, `wuzizui99`, `xjgc`, `yangnongchem`

## 分看板枚举

### 灭火全景图 - foneshare

- uid: `d515ee47-4818-4340-ab9b-a42c759a1e2c`
- url: `https://grafana.foneshare.cn/d/d515ee47-4818-4340-ab9b-a42c759a1e2c`
- `env` type: `custom`

| env value |
| --- |
| ale |
| chinatower |
| cloudmodel |
| foneshare |
| hexagonmi |
| hisense |
| hsyk |
| hwc |
| hws |
| iflytek |
| kemaicrm |
| ksc |
| mengniu |
| sbt |
| ucd |
| ucd-test |
| wuzizui99 |
| xjgc |
| yangnongchem |

### 灭火全景图 - clouds

- uid: `a4766984-66a2-4a00-94f1-49a7cc76958d`
- 在上一表基础上 **额外** 含：`teleagi`, `forsharecrm`, `allink8s`, `cpgc`, `wingd`, `kehua`

查「更全的专属云列表」时优先看本看板的 `env`。

### 其它

- `全网巡检`（uid `clickhouse-log-cep-clouds`）等也可能带云/集群变量；**以该看板 `dashboard get` → `templating` 为准**，不在此重复维护多份漂移表。

## env value → IDP prometheus / 业务 profile（对照）

Grafana `env` **字符串常与** IDP `--profile` **同名，但并非处处相等**。直连 `idp prometheus` / 租户云时，以 cloud-registry 与 monitoring「Profile 选择规则」为准。

| Grafana `env` | 常见含义 | 直连指标时常用 `--profile` | 备注 |
| --- | --- | --- | --- |
| foneshare | 主站 | `foneshare` | |
| mengniu | 蒙牛 | `mengniu` | |
| hsyk | 何氏眼科 | `hsyk` | |
| sbt | 双胞胎 | `sbt` | |
| iflytek | 科大讯飞 | `iflytek` | |
| hisense | 海信 | `hisense` | |
| xjgc | 许继 | `xjgc` | |
| chinatower | 铁塔 | `chinatower` | |
| yangnongchem | 扬农 | `yangnongchem` | |
| wuzizui99 | 伍子醉 | `wuzizui99` | |
| hexagonmi | 海克斯康 | `hexagonmi` | |
| kemaicrm | 北美等 | `kemaicrm` | |
| teleagi | 电信 | `teleagi` | 见 clouds 板 |
| cpgc | 中船动力 | `cpgc` | clouds |
| wingd | WinGD | `wingd` | clouds |
| kehua | 科华 | `kehua` | clouds |
| hws | 亚马逊-法兰克福等 | `hws` | |
| hwc | 华为云相关口语 | 常对应 `hwcloud` / 别名 | **勿想当然**；查 registry |
| ucd | 紫光云 | `ucd` | |
| ucd-test | 测试/性能相关短名 | 可能映射 `perftest` 等 | **以 registry 为准** |
| ksc | 亚马逊-香港等 | 见 registry | |
| ale | 钉钉云等 | 见 registry | |
| cloudmodel | 模板云 | 见 registry | |
| allink8s | allink8s | 见 registry | clouds |
| forsharecrm | 亚马逊-新加坡等 | 见 registry | clouds |

完整 source_id / 域名 / 口语别名：见共享 [cloud-registry.md](../../../../contracts/cloud-registry.md)（monitoring 路由亦引用）。

## 编排检查清单

1. `dashboard get` 确认该板是否有 `env`（或同等云变量）。  
2. 用户目标云 → 填 `var-env`（从上表选；不确定则先列选项给用户确认）。  
3. `grafana query` 前替换 `$env` / `${env}`；保留 `$__timeFilter` 等插件宏。  
4. 若走 `idp prometheus` 而非 grafana query：用上表右侧 profile（有歧义先查 cloud-registry）。
