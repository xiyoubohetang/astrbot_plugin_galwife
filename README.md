<div align="center">

# Gal 今日老婆

**每天抽一位二次元老婆，附带立绘、介绍、作品出处**

[![AstrBot](https://img.shields.io/badge/AstrBot-plugin-5865f2?style=flat-square)](https://github.com/AstrBotDevs/AstrBot)
[![Version](https://img.shields.io/badge/version-1.0.0-22c55e?style=flat-square)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square)]()
[![License](https://img.shields.io/badge/license-MIT-3b82f6?style=flat-square)]()

</div>

## ✨ 功能

- 🎴 **每日老婆**：每天固定一位，同一人同一天结果一致
- 🔁 **换老婆 / 换背景**：不满意随时换，换背景只换图不换角色
- 🎲 **随机老婆**：真随机，2 万角色库
- 🔍 **搜老婆**：按角色名/作品名搜索
- ❤️ **收藏系统**：收藏喜欢的角色，永久保留
- 📜 **抽卡记录**：查看历史、群排行、个人统计
- 🖼️ **多图源**：Lolicon / Danbooru / Safebooru / Yande.re 自动降级
- 💰 **金币联动**：与[画境拾珍](https://github.com/shitianyaa/astrbot_plugin_get_px)联动，扣金币抽卡
- 🎨 **精美卡片**：T2I 渲染，米黄纸质 / 深紫夜光两种主题
- 🔒 **安全过滤**：可选的敏感词过滤
- 🧹 **自动清理**：每天定时清理过期缓存

## 📦 安装

### 1. 从插件市场安装

在 AstrBot 管理面板 → 插件 → 插件市场，搜索 "Gal今日老婆" 安装。

### 2. 手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/xiyoubohetang/astrbot_plugin_galwife
cd astrbot_plugin_galwife
pip install -r requirements.txt
```

### 3. 导入角色数据

本插件依赖角色数据文件 `wives_rich.jsonl`（约 2 万条，含名字/作品/介绍/立绘）。

**数据已随仓库附带**，clone 下来即可使用，无需额外下载。把 `wives_rich.jsonl` 放到插件目录或 AstrBot 数据目录：

```text
AstrBot/data/plugin_data/astrbot_plugin_galwife/wives_rich.jsonl
```

> 数据来源：[Bangumi 番组计划](https://bgm.tv/) 角色数据库，筛选知名女角色。

重启 AstrBot 即可。

## 🎮 指令

| 指令 | 说明 | 费用 |
|---|---|---|
| `/今日老婆` | 每天固定一位 | 免费 |
| `/换老婆` | 换一个 | 消耗金币 |
| `/换背景` | 不换角色只换图 | 消耗金币 |
| `/随机老婆` | 真随机 | 消耗金币 |
| `/搜老婆 <关键词>` | 搜索角色 | 免费 |
| `/老婆详情` | 查看完整介绍 | 免费 |
| `/收藏老婆` | 收藏当前老婆 | 免费 |
| `/我的收藏 [页码]` | 查看收藏列表 | 免费 |
| `/取消收藏 <序号>` | 移除收藏 | 免费 |
| `/老婆历史` | 最近抽卡记录 | 免费 |
| `/老婆排行` | 群内抽卡排行 | 免费 |
| `/老婆统计` | 个人 + 群统计 | 免费 |
| `/老婆帮助` | 显示帮助 | 免费 |

**管理员指令**：

| 指令 | 说明 |
|---|---|
| `/重载老婆数据` | 重载角色数据 |
| `/老婆失败记录` | 查看搜图失败的角色 |
| `/清空失败记录` | 清空失败记录 |
| `/调试联动` | 调试金币联动状态 |

## ⚙️ 配置

在 AstrBot 管理面板 → 插件 → Gal今日老婆 → 配置：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `card_theme` | `warm` | 卡片主题：`warm` 米黄 / `dark` 深紫 |
| `enable_coin_cost` | `true` | 是否启用金币联动 |
| `reroll_cost` | `20` | `/换老婆` 消耗金币 |
| `bg_cost` | `10` | `/换背景` 消耗金币 |
| `random_cost` | `20` | `/随机老婆` 消耗金币 |
| `enable_sensitive_filter` | `false` | 敏感词过滤 |
| `intro_max_len` | `300` | 卡片上介绍截断长度 |
| `daily_cleanup_hour` | `4` | 每天清理小时 |
| `max_retry_per_wife` | `5` | 单次抽卡最多尝试几个角色 |

完整配置项见插件配置页。

## 💰 金币联动

本插件可与[画境拾珍](https://github.com/shitianyaa/astrbot_plugin_get_px)联动：

- 用户 `/换老婆` `/换背景` `/随机老婆` 时，自动扣除画境拾珍的金币
- 未装画境拾珍时，自动跳过扣费
- 抽卡失败（搜不到图）时，自动退还金币
- 金币余额显示在卡片下方

**工作原理**：直接读写 `astrbot_plugin_get_px/checkin.sqlite3` 的 `checkin_users` 表，与画境拾珍内部扣费逻辑一致。

## 🖼️ 图源策略

按优先级降级搜索：

```text
1. Lolicon API（Pixiv 代理）— 用日文名/中文名/作品名搜
   ↓ 失败
2. Danbooru — 用罗马音 tag 搜（需 pykakasi）
   ↓ 失败
3. Safebooru — 同上
   ↓ 失败
4. Yande.re — 同上
   ↓ 失败
5. main_img 兜底 — 用 Bangumi 自带立绘
```

**限流保护**：

- Lolicon 全局锁 + 最小间隔 2 秒
- 429 自动退避 30 秒 + 重试 2 次
- 图片本地缓存，同一天同一用户只搜一次

## 🗂️ 数据目录

```text
AstrBot/data/plugin_data/astrbot_plugin_galwife/
├── wives_rich.jsonl       # 角色数据
├── failed_wives.txt       # 搜图失败记录
├── today_wife_state.json  # 今日抽卡状态
├── romaji_cache.json      # 日文→罗马音缓存
├── group_stats.json       # 群统计
├── img_cache/             # 图片缓存
│   └── {uid}_{date}.jpg
└── user_data/             # 用户档案
    └── {uid}.json
```

## 🛠️ 开发

### 依赖

```bash
pip install -r requirements.txt
```

- `curl_cffi`：模拟浏览器 TLS 指纹，绕过 Cloudflare
- `Pillow`：图片压缩
- `pykakasi`：日文转罗马音（备用图源必需）

### 项目结构

```text
astrbot_plugin_galwife/
├── main.py               # 主逻辑
├── _conf_schema.json     # 配置 schema
├── metadata.yaml         # 插件元信息
├── requirements.txt      # 依赖
├── README.md
├── LICENSE
├── .gitignore
└── wives_rich.jsonl      # 角色数据（约 2 万条）
```

## 🙏 致谢

- 角色数据：[Bangumi 番组计划](https://bgm.tv/)
- 图源：[Lolicon API](https://api.lolicon.app/)、[Danbooru](https://danbooru.donmai.us/)、[Safebooru](https://safebooru.org/)、[Yande.re](https://yande.re/)
- 金币联动：[astrbot_plugin_get_px](https://github.com/shitianyaa/astrbot_plugin_get_px)（作者 Sham1k0）
- T2I 渲染：[AstrBot](https://github.com/AstrBotDevs/AstrBot)

## 📄 License

MIT