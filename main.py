import asyncio
import base64
import hashlib
import json
import pathlib
import random
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

from curl_cffi.requests import AsyncSession
from PIL import Image as PILImage

from astrbot.api.all import Image, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain, At
from astrbot.api.star import Context, Star, register
from astrbot.core.star.star_tools import StarTools

try:
    import pykakasi
    _KAKASI = pykakasi.kakasi()
    _HAS_KAKASI = True
except ImportError:
    _KAKASI = None
    _HAS_KAKASI = False


LOG_PREFIX = "[GalWife]"
PLUGIN_NAME = "astrbot_plugin_galwife"
PLUGIN_VERSION = "1.0.0"

LOLICON_API = "https://api.lolicon.app/setu/v2"
SAFEBOORU_API = "https://safebooru.org/index.php"
DANBOORU_API = "https://danbooru.donmai.us/posts.json"
YANDERE_API = "https://yande.re/post.json"
GETPX_PLUGIN_NAME = "astrbot_plugin_get_px"
GETPX_DB_NAME = "checkin.sqlite3"

IMAGE_PROXIES = [
    "https://i.pixiv.re",
    "https://i.pixiv.cat",
    "https://proxy.pixivel.moe",
]

IMPERSONATE = "chrome120"
PIXIV_REFERER = "https://www.pixiv.net/"

FORTUNES = ["超大吉", "大吉", "中吉", "小吉", "末吉", "平", "凶"]

BG_RETRY_PER_TAG = 3
LOLICON_MIN_INTERVAL = 2.0
LOLICON_429_BACKOFF = 30.0
LOLICON_429_MAX_RETRY = 2

HISTORY_MAX = 30
FAVORITES_MAX = 200
PAGE_SIZE = 10

SENSITIVE_TERMS = [
    "r18", "r-18", "r18g", "r-18g", "nsfw",
    "裸体", "全裸", "裸露", "露出", "成人", "色情", "性交", "性爱", "性器",
    "乳首", "乳房", "触手", "猎奇", "血腥", "断肢", "肢解", "内脏", "尸体",
    "guro", "gore", "grotesque",
    "グロ", "グロテスク", "リョナ", "猟奇", "欠損", "切断", "内臓", "死体",
]


T2I_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { width: 960px; height: 540px; overflow: hidden; }
  body {
    width: 960px; height: 540px; margin: 0; padding: 0;
    overflow: hidden; display: flex; align-items: center; justify-content: center;
    font-family: "LXGW WenKai Lite", "PingFang SC", "Microsoft YaHei", serif;
    background: var(--bg);
    color: var(--fg);
  }
  body.theme-warm {
    --bg: radial-gradient(circle at top left, #fdfaf4 0%, #f5efe3 100%);
    --fg: #3a2e22;
    --paper-bg: #fffdf7;
    --paper-border: #e4d5bd;
    --paper-inner: #efe3cc;
    --label: #a09078;
    --accent: #8a9a7b;
    --red: #c45a4a;
    --gold: #c9a24b;
    --frame-bg: #f0ece2;
    --quote-bg: rgba(255, 255, 255, 0.3);
    --shadow: 0 20px 60px rgba(90, 70, 40, 0.18), 0 2px 8px rgba(90, 70, 40, 0.08);
  }
  body.theme-dark {
    --bg: radial-gradient(ellipse at top, rgba(233,69,96,0.18) 0%, transparent 60%),
          radial-gradient(ellipse at bottom right, rgba(120,80,255,0.18) 0%, transparent 60%),
          linear-gradient(160deg, #1a1a2e 0%, #16162a 50%, #0f0f1e 100%);
    --fg: #e8e8f0;
    --paper-bg: #1a1a2e;
    --paper-border: rgba(233,69,96,0.35);
    --paper-inner: rgba(233,69,96,0.18);
    --label: #8b9dc3;
    --accent: #e94560;
    --red: #ff6b9d;
    --gold: #ffd700;
    --frame-bg: #0a0a14;
    --quote-bg: rgba(0, 0, 0, 0.35);
    --shadow: 0 24px 80px rgba(0,0,0,0.7), 0 0 0 1px rgba(233,69,96,0.25), 0 0 60px rgba(233,69,96,0.15);
  }
  .paper-sheet {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 48fr) minmax(0, 45fr);
    gap: 22px;
    width: 928px; height: 508px;
    padding: 20px 26px;
    overflow: hidden;
    border: 1px solid var(--paper-border);
    background: var(--paper-bg);
    box-shadow: var(--shadow);
  }
  .paper-sheet::before {
    position: absolute; inset: 9px;
    border: 1px solid var(--paper-inner);
    content: ""; pointer-events: none;
  }
  .info-column {
    position: relative; z-index: 1;
    display: flex; flex-direction: column; gap: 10px; min-width: 0;
  }
  .card-header {
    position: relative;
    display: flex; padding-bottom: 10px;
    align-items: flex-start; justify-content: space-between;
    gap: 12px; border-bottom: 1px solid var(--paper-border);
    flex-shrink: 0;
  }
  .heading-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; overflow: hidden; }
  .date-label {
    max-width: 100%; overflow: hidden;
    color: var(--label); font-size: 16px; letter-spacing: 0.08em;
    line-height: 1; text-overflow: ellipsis; white-space: nowrap;
  }
  .card-header h1 {
    max-width: 100%; overflow: hidden; margin: 0;
    color: var(--fg); font-size: 30px; font-weight: 600;
    line-height: 1; text-overflow: ellipsis; white-space: nowrap;
  }
  .identity { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
  .avatar {
    display: grid; width: 42px; height: 42px; flex: 0 0 42px;
    place-items: center; overflow: hidden;
    border: 1px solid var(--accent); border-radius: 50%;
    background: var(--frame-bg); color: var(--accent); font-size: 22px;
  }
  .identity-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
  .identity-copy strong {
    max-width: 100%; overflow: hidden;
    color: var(--fg); font-size: 22px; font-weight: 600;
    line-height: 1.1; text-overflow: ellipsis; white-space: nowrap;
  }
  .identity-copy span {
    overflow: hidden; color: var(--label); font-size: 16px;
    text-overflow: ellipsis; white-space: nowrap;
  }
  .greeting {
    position: relative; flex: 1; min-height: 0;
    padding: 10px 14px; border-left: 3px solid var(--accent);
    background: var(--quote-bg); overflow: hidden;
  }
  .greeting blockquote {
    max-width: 100%; max-height: 100%; overflow: hidden; margin: 0;
    color: var(--fg); font-size: 16px; line-height: 1.6;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 8;
  }
  .rewards {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
    border-top: 1px solid var(--paper-border);
    border-bottom: 1px solid var(--paper-border);
    flex-shrink: 0;
  }
  .rewards.two-cols { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .reward-item { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; }
  .reward-item + .reward-item { border-left: 1px dashed var(--paper-border); }
  .reward-item span { color: var(--label); font-size: 13px; white-space: nowrap; }
  .reward-item strong {
    overflow: hidden; color: var(--accent); font-size: 19px;
    line-height: 1.1; text-overflow: ellipsis; white-space: nowrap;
  }
  .reward-item:nth-child(2) strong { color: var(--red); }
  .reward-item:nth-child(3) strong { color: var(--gold); }
  .artwork-column {
    display: flex; align-items: center; flex-direction: column;
    justify-content: center; gap: 8px; min-width: 0;
  }
  .artwork-frame {
    position: relative; width: 100%; max-width: 300px;
    aspect-ratio: 3 / 4; overflow: hidden;
    border: 6px solid var(--paper-border);
    outline: 1px solid var(--paper-inner);
    background: var(--frame-bg);
    box-shadow: var(--shadow);
  }
  .artwork-frame img {
    display: block; width: 100%; height: 100%;
    object-fit: contain; object-position: center; background: var(--frame-bg);
  }
  .artwork-credit {
    width: 100%; min-height: 16px; overflow: hidden;
    color: var(--label); font-size: 13px; line-height: 1.1;
    text-align: center; text-overflow: ellipsis; white-space: nowrap;
  }
</style>
</head>
<body class="theme-{{ theme }}">
  <article class="paper-sheet">
    <section class="info-column">
      <header class="card-header">
        <div class="heading-copy">
          <p class="date-label">{{ date }}</p>
          <h1>今日老婆</h1>
        </div>
      </header>
      <section class="identity">
        <div class="avatar">{{ user_initial }}</div>
        <div class="identity-copy">
          <strong>{{ name }}</strong>
          <span>{{ game }}</span>
        </div>
      </section>
      <section class="greeting">
        <blockquote>{{ intro }}</blockquote>
      </section>
      <section class="rewards{% if not cost_text %} two-cols{% endif %}">
        <div class="reward-item">
          <span>今日签运</span>
          <strong>{{ fortune }}</strong>
        </div>
        <div class="reward-item">
          <span>召唤者</span>
          <strong>{{ user_name }}</strong>
        </div>
        {% if cost_text %}
        <div class="reward-item">
          <span>金币余额</span>
          <strong>{{ balance }}</strong>
        </div>
        {% endif %}
      </section>
    </section>
    <section class="artwork-column">
      <div class="artwork-frame">
        <img src="{{ img_b64 }}" alt="{{ name }}">
      </div>
      <p class="artwork-credit">{{ game }} · {{ name }}</p>
    </section>
  </article>
</body>
</html>
"""


HELP_TEXT = """✨ Gal 今日老婆 帮助 ✨

【抽卡】
/今日老婆 — 每天固定一位，不扣金币
/换老婆 — 换一个（消耗金币）
/换背景 — 不换角色只换图（消耗金币）
/随机老婆 — 真随机（消耗金币）

【角色】
/搜老婆 <关键词> — 搜索角色
/老婆详情 — 查看当前老婆的完整介绍

【收藏】
/收藏老婆 — 收藏当前老婆
/我的收藏 [页码] — 查看收藏
/取消收藏 <序号> — 移除收藏

【记录】
/老婆历史 — 查看最近抽过的
/老婆排行 — 群内抽卡排行
/老婆统计 — 群内抽卡统计

【管理】
/重载老婆数据 — 管理员
/老婆失败记录 — 管理员
/清空失败记录 — 管理员

【图源】Lolicon / Danbooru / Safebooru / Yande.re
【数据】Bangumi 万级女角色库
"""


# ───────────────────── 工具函数 ─────────────────────

def to_romaji(text: str) -> str:
    if not text or not _HAS_KAKASI:
        return ""
    try:
        return "".join(i.get("hepburn", "") for i in _KAKASI.convert(text)).strip().lower()
    except Exception:
        return ""


def make_booru_tags(text: str):
    if not text:
        return []
    text = text.strip().lower()
    tags = {text, text.replace(" ", "_"), text.replace(" ", "")}
    for sep in ("·", "・", "-", "_"):
        if sep in text:
            tags.add(text.replace(sep, ""))
    return [t for t in tags if t]


def has_sensitive(text: str, terms) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(t in low for t in terms)


# ───────────────────── 主类 ─────────────────────

@register(PLUGIN_NAME, "西柚薄荷糖", "Gal今日老婆", PLUGIN_VERSION)
class GalWifePlugin(Star):

    def __init__(self, context: Context, config):
        super().__init__(context, config)
        self.config = config
        self.base_path = pathlib.Path(__file__).parent
        self.data_dir = None
        self.heroines = []
        self.session = None
        self._failed_cache = set()
        self._getpx_db_path = None
        self._today_state = {}
        self._romaji_cache = {}
        self._lolicon_lock = None
        self._lolicon_last_req = 0.0
        self._lolicon_backoff_until = 0.0
        self._user_data_lock = None
        self._cleanup_task = None

    # ───────────────────── 生命周期 ─────────────────────

    async def initialize(self):
        try:
            self.data_dir = pathlib.Path(StarTools.get_data_dir(PLUGIN_NAME))
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 获取数据目录失败，回退到插件目录: {e}")
            self.data_dir = self.base_path / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "user_data").mkdir(exist_ok=True)
        (self.data_dir / "img_cache").mkdir(exist_ok=True)

        self._lolicon_lock = asyncio.Lock()
        self._user_data_lock = asyncio.Lock()
        self.session = AsyncSession()

        self._load_failed_cache()
        self._reload()
        self._load_today_state()
        self._load_romaji_cache()

        if not _HAS_KAKASI:
            logger.warning(
                f"{LOG_PREFIX} 未安装 pykakasi，Danbooru/Safebooru/Yande.re 备用源将不可用"
            )

        db = self._resolve_getpx_db()
        if db:
            logger.info(f"{LOG_PREFIX} 找到 get_px 数据库: {db}")
        else:
            logger.warning(f"{LOG_PREFIX} 未找到 get_px 数据库，金币联动将不生效")

        self._cleanup_task = asyncio.create_task(self._daily_cleanup_loop())
        logger.info(f"{LOG_PREFIX} 插件已加载 v{PLUGIN_VERSION}")

    async def terminate(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._cleanup_task = None

        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None

        self._save_romaji_cache()
        logger.info(f"{LOG_PREFIX} 插件已停止")

    async def _daily_cleanup_loop(self):
        """每小时检查一次，到了清理时间就清理。"""
        target_hour = self._cfg_int("daily_cleanup_hour", 4)
        last_clean_date = ""
        while True:
            try:
                await asyncio.sleep(3600)
                now = datetime.now()
                today = now.strftime("%Y%m%d")
                if now.hour == target_hour and last_clean_date != today:
                    await self._do_cleanup(today)
                    last_clean_date = today
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} 定时清理出错: {type(e).__name__}: {e}")

    async def _do_cleanup(self, today: str):
        # 清理过期图片缓存（保留今天）
        removed = 0
        try:
            cutoff = datetime.now() - timedelta(days=7)
            for p in (self.data_dir / "img_cache").glob("*.jpg"):
                try:
                    if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
                        p.unlink()
                        removed += 1
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 清理图片缓存出错: {type(e).__name__}")

        # 清理过期的今日状态
        try:
            if self._today_state:
                before = len(self._today_state)
                self._today_state = {
                    k: v for k, v in self._today_state.items()
                    if k.endswith(f"_{today}")
                }
                if len(self._today_state) != before:
                    self._save_today_state()
        except Exception:
            pass

        logger.info(f"{LOG_PREFIX} 定时清理完成: 删除 {removed} 张过期图片")

    # ───────────────────── 配置 ─────────────────────

    def _cfg(self, key, default=None):
        try:
            return self.config.get(key, default) if self.config else default
        except Exception:
            return default

    def _cfg_float(self, key, default):
        try:
            return float(self._cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _cfg_int(self, key, default):
        try:
            return int(self._cfg(key, default))
        except (TypeError, ValueError):
            return default

    def _cfg_bool(self, key, default):
        v = self._cfg(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v) if v is not None else default

    # ───────────────────── 数据加载 ─────────────────────

    def _resolve_wives_path(self):
        wives_file = str(self._cfg("wives_file", "wives_rich.jsonl")).strip()
        if not wives_file:
            return None
        p = pathlib.Path(wives_file)
        if p.is_absolute() and p.exists():
            return p
        # 数据目录优先
        d = self.data_dir / wives_file
        if d.exists():
            return d
        # 插件目录
        b = self.base_path / wives_file
        if b.exists():
            return b
        return None

    def _reload(self):
        path = self._resolve_wives_path()
        self.heroines = []

        if not path:
            logger.error(
                f"{LOG_PREFIX} 找不到角色数据文件，请把 wives_rich.jsonl "
                f"放到 {self.data_dir}"
            )
            return

        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = (obj.get("name") or obj.get("cn_name") or "").strip()
                if not name:
                    continue
                self.heroines.append({
                    "name": name,
                    "cn_name": (obj.get("cn_name") or "").strip(),
                    "game_name": (obj.get("game_name") or "").strip(),
                    "intro": (obj.get("intro") or "").strip(),
                    "main_img": (obj.get("main_img") or "").strip(),
                })

        has_img = sum(1 for h in self.heroines if h["main_img"])
        logger.info(
            f"{LOG_PREFIX} 已加载 {len(self.heroines)} 个角色"
            f"（{has_img} 个有本地图）"
        )

    def _wife_key(self, wife) -> str:
        return f"{wife.get('name', '')} ({wife.get('game_name') or '未知'})"

    def _load_failed_cache(self):
        path = self.data_dir / "failed_wives.txt"
        self._failed_cache = set()
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    key = line.strip().split("#")[0].strip()
                    if key:
                        self._failed_cache.add(key)
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 读取失败记录出错: {type(e).__name__}")

    def _record_failure(self, wife, reason=""):
        key = self._wife_key(wife)
        if not key or key in self._failed_cache:
            return
        self._failed_cache.add(key)
        try:
            with (self.data_dir / "failed_wives.txt").open("a", encoding="utf-8") as f:
                f.write(f"{key}  # {reason}\n" if reason else f"{key}\n")
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 写入失败记录出错: {type(e).__name__}")

    # ───────────────────── 用户档案 / 群统计 ─────────────────────

    def _user_data_path(self, uid: str) -> pathlib.Path:
        return self.data_dir / "user_data" / f"{uid}.json"

    def _load_user_data(self, uid: str) -> dict:
        p = self._user_data_path(uid)
        default = {
            "uid": uid,
            "favorites": [],
            "history": [],
            "stats": {"total_draws": 0, "unique_wives": 0},
            "seen_keys": [],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        if not p.exists():
            return default
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default.items():
                data.setdefault(k, v)
            return data
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 读取用户档案出错: {type(e).__name__}")
            return default

    def _save_user_data(self, uid: str, data: dict):
        try:
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            with self._user_data_path(uid).open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 保存用户档案出错: {type(e).__name__}")

    def _group_stats_path(self) -> pathlib.Path:
        return self.data_dir / "group_stats.json"

    def _load_group_stats(self) -> dict:
        p = self._group_stats_path()
        if not p.exists():
            return {}
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_group_stats(self, data: dict):
        try:
            with self._group_stats_path().open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 保存群统计出错: {type(e).__name__}")

    async def _record_draw(self, uid: str, gid: str, wife, source: str):
        """记录抽卡：更新用户档案 + 群统计。"""
        async with self._user_data_lock:
            data = self._load_user_data(uid)
            data["stats"]["total_draws"] = int(data["stats"].get("total_draws", 0)) + 1
            key = self._wife_key(wife)
            seen = set(data.get("seen_keys", []))
            if key not in seen:
                seen.add(key)
                data["seen_keys"] = list(seen)[-500:]
                data["stats"]["unique_wives"] = len(seen)
            data["history"].insert(0, {
                "wife_key": key,
                "name": wife.get("cn_name") or wife.get("name", ""),
                "game_name": wife.get("game_name", ""),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": source,
            })
            data["history"] = data["history"][:HISTORY_MAX]
            self._save_user_data(uid, data)

        if gid:
            stats = self._load_group_stats()
            g = stats.setdefault(gid, {"user_counts": {}, "total_draws": 0})
            g["user_counts"][uid] = int(g["user_counts"].get(uid, 0)) + 1
            g["total_draws"] = int(g.get("total_draws", 0)) + 1
            g["last_update"] = datetime.now().isoformat(timespec="seconds")
            self._save_group_stats(stats)

    def _group_id(self, event) -> str:
        try:
            return str(event.get_group_id() or "").strip()
        except Exception:
            return ""

    # ───────────────────── 图片缓存 ─────────────────────

    def _cache_img_path(self, uid: str, date: str) -> pathlib.Path:
        return self.data_dir / "img_cache" / f"{uid}_{date}.jpg"

    @staticmethod
    def _file_hash(path) -> str:
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    # ───────────────────── 今日状态 ─────────────────────

    def _today_state_file(self) -> pathlib.Path:
        return self.data_dir / "today_wife_state.json"

    def _load_today_state(self):
        path = self._today_state_file()
        self._today_state = {}
        today = datetime.now().strftime("%Y%m%d")
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if not isinstance(k, str) or not k.endswith(f"_{today}"):
                        continue
                    if isinstance(v, dict):
                        self._today_state[k] = v
                    elif isinstance(v, str):
                        self._today_state[k] = {"wife_key": v}
            except Exception as e:
                logger.warning(f"{LOG_PREFIX} 读取今日老婆状态失败: {type(e).__name__}")

    def _save_today_state(self):
        try:
            with self._today_state_file().open("w", encoding="utf-8") as f:
                json.dump(self._today_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 保存今日老婆状态失败: {type(e).__name__}")

    def _find_wife_by_key(self, key):
        for w in self.heroines:
            if self._wife_key(w) == key:
                return w
        return None

    # ───────────────────── 罗马音缓存 ─────────────────────

    def _load_romaji_cache(self):
        p = self.data_dir / "romaji_cache.json"
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    self._romaji_cache = json.load(f)
            except Exception:
                self._romaji_cache = {}

    def _save_romaji_cache(self):
        if not self._romaji_cache:
            return
        try:
            with (self.data_dir / "romaji_cache.json").open("w", encoding="utf-8") as f:
                json.dump(self._romaji_cache, f, ensure_ascii=False)
        except Exception:
            pass

    def _get_romaji(self, wife: dict) -> str:
        if not _HAS_KAKASI:
            return ""
        key = wife.get("name", "")
        if not key:
            return ""
        if key in self._romaji_cache:
            return self._romaji_cache[key]
        r = to_romaji(key)
        self._romaji_cache[key] = r
        return r

    # ───────────────────── 金币联动 ─────────────────────

    def _resolve_getpx_db(self):
        if self._getpx_db_path is not None:
            return self._getpx_db_path if str(self._getpx_db_path) else None

        custom = str(self._cfg("getpx_db_path", "")).strip()
        if custom:
            p = pathlib.Path(custom)
            if p.exists():
                self._getpx_db_path = p
                return p
            logger.warning(f"{LOG_PREFIX} 配置的 getpx_db_path 不存在: {p}")

        for cand in (
            self.data_dir.parent / GETPX_PLUGIN_NAME / GETPX_DB_NAME,
            self.data_dir.parent.parent / GETPX_PLUGIN_NAME / GETPX_DB_NAME,
            self.base_path.parent / "plugin_data" / GETPX_PLUGIN_NAME / GETPX_DB_NAME,
        ):
            if cand.exists():
                self._getpx_db_path = cand
                return cand

        self._getpx_db_path = ""
        return None

    @staticmethod
    def _sqlite_spend(db_path: str, user_id: str, cost: int):
        now = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(db_path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO checkin_users (
                        user_id, coins, affection, total_days, streak_days,
                        last_checkin_date, boost_start_date, boost_until_date,
                        repeat_penalty_date, repeat_penalty_total,
                        created_at, updated_at
                    ) VALUES (?, 0, 0, 0, 0, '', '', '', '', 0, ?, ?)""",
                    (user_id, now, now),
                )
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO checkin_user_themes
                           (user_id, theme_id, price_paid, acquired_at)
                           VALUES (?, 'default', 0, ?)""",
                        (user_id, now),
                    )
                except sqlite3.OperationalError:
                    pass
                row = conn.execute(
                    "SELECT coins FROM checkin_users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    conn.rollback()
                    return False, 0, "用户档案不存在"
                coins = int(row["coins"] or 0)
                if coins < cost:
                    conn.commit()
                    return False, coins, f"金币不足，需要 {cost}，当前只有 {coins}"
                remaining = coins - cost
                conn.execute(
                    "UPDATE checkin_users SET coins = ?, updated_at = ? WHERE user_id = ?",
                    (remaining, now, user_id),
                )
                conn.commit()
                return True, remaining, f"花费 {cost} 金币，余额 {remaining}"
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _sqlite_add(db_path: str, user_id: str, amount: int):
        now = datetime.now().isoformat(timespec="seconds")
        with closing(sqlite3.connect(db_path, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO checkin_users (
                        user_id, coins, affection, total_days, streak_days,
                        last_checkin_date, boost_start_date, boost_until_date,
                        repeat_penalty_date, repeat_penalty_total,
                        created_at, updated_at
                    ) VALUES (?, 0, 0, 0, 0, '', '', '', '', 0, ?, ?)""",
                    (user_id, now, now),
                )
                conn.execute(
                    "UPDATE checkin_users SET coins = coins + ?, updated_at = ? WHERE user_id = ?",
                    (amount, now, user_id),
                )
                row = conn.execute(
                    "SELECT coins FROM checkin_users WHERE user_id = ?", (user_id,)
                ).fetchone()
                conn.commit()
                return True, int(row["coins"] or 0) if row else 0
            except Exception:
                conn.rollback()
                raise

    async def _charge_coins(self, event, cost: int):
        if cost <= 0 or not self._cfg_bool("enable_coin_cost", True):
            return True, "", None
        db = self._resolve_getpx_db()
        if db is None:
            return True, "", None
        uid = str(event.get_sender_id() or "")
        if not uid:
            return True, "", None
        try:
            ok, balance, msg = await asyncio.to_thread(
                self._sqlite_spend, str(db), uid, int(cost)
            )
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 扣费出错，放行: {type(e).__name__}: {e}")
            return True, "", None
        if not ok:
            return False, msg, balance
        return True, msg, balance

    async def _refund_coins(self, event, amount: int):
        if amount <= 0 or not self._cfg_bool("enable_coin_cost", True):
            return
        db = self._resolve_getpx_db()
        if db is None:
            return
        uid = str(event.get_sender_id() or "")
        if not uid:
            return
        try:
            ok, balance = await asyncio.to_thread(self._sqlite_add, str(db), uid, int(amount))
            if ok:
                logger.info(f"{LOG_PREFIX} 已退还 {amount} 金币，余额 {balance} uid={uid}")
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 退还金币失败: {type(e).__name__}: {e}")

    # ───────────────────── 图片处理 ─────────────────────

    def _process_image_sync(self, data: bytes):
        max_kb = self._cfg_int("max_image_kb", 800)
        try:
            with PILImage.open(BytesIO(data)) as im:
                im.verify()
            with PILImage.open(BytesIO(data)) as im:
                if im.mode != "RGB":
                    im = im.convert("RGB")
                max_side = self._cfg_int("max_side", 1600)
                if max(im.size) > max_side:
                    ratio = max_side / max(im.size)
                    im = im.resize((int(im.width * ratio), int(im.height * ratio)), PILImage.LANCZOS)
                quality = 88
                buf = BytesIO()
                while quality > 30:
                    buf.seek(0); buf.truncate()
                    im.save(buf, format="JPEG", quality=quality, optimize=True)
                    if buf.tell() <= max_kb * 1024:
                        break
                    quality -= 10
        except Exception as e:
            logger.debug(f"{LOG_PREFIX} 图片处理失败 {type(e).__name__}")
            return None
        tmp = pathlib.Path(tempfile.gettempdir()) / f"galwife_{uuid.uuid4().hex}.jpg"
        tmp.write_bytes(buf.getvalue())
        return tmp

    async def _process_image(self, data: bytes):
        return await asyncio.to_thread(self._process_image_sync, data)

    async def _download(self, url: str, referer: str = ""):
        if not url:
            return None
        timeout = self._cfg_float("download_timeout", 15.0)
        max_mb = self._cfg_float("max_image_mb", 8.0)
        headers = {"Referer": referer} if referer else {}
        try:
            async with self.session.stream(
                "GET", url, headers=headers, impersonate=IMPERSONATE, timeout=timeout,
            ) as resp:
                if resp.status_code != 200:
                    logger.debug(f"{LOG_PREFIX} 图片 HTTP {resp.status_code}")
                    return None
                data = await resp.acontent()
        except Exception as e:
            logger.debug(f"{LOG_PREFIX} 图片下载失败 {type(e).__name__}")
            return None
        if len(data) < 200:
            return None
        if max_mb > 0 and len(data) > max_mb * 1024 * 1024:
            return None
        return await self._process_image(data)

    def _path_to_data_url(self, img_path) -> str:
        with open(img_path, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

    def _rewrite_to_proxy(self, url: str) -> str:
        if not url:
            return url
        proxies = [
            str(self._cfg("image_proxy_origin", IMAGE_PROXIES[0])).rstrip("/")
        ] + IMAGE_PROXIES[1:]
        if any(url.startswith(p) for p in proxies):
            return url
        if "i.pximg.net" in url:
            image = urlsplit(url)
            p = urlsplit(proxies[0])
            return urlunsplit((p.scheme, p.netloc, image.path, image.query, image.fragment))
        return url

    # ───────────────────── 图源 ─────────────────────

    async def _search_lolicon(self, tag: str, num: int = 50, rng: random.Random = None):
        if not tag:
            return None
        api = str(self._cfg("lolicon_api", LOLICON_API))
        params = {"tag": tag, "num": num, "r18": 0, "size": "regular", "excludeAI": "true"}
        timeout = self._cfg_float("api_timeout", 5.0)

        async with self._lolicon_lock:
            now = time.monotonic()
            if now < self._lolicon_backoff_until:
                await asyncio.sleep(self._lolicon_backoff_until - now)
            now = time.monotonic()
            gap = now - self._lolicon_last_req
            if gap < LOLICON_MIN_INTERVAL:
                await asyncio.sleep(LOLICON_MIN_INTERVAL - gap)

            resp = None
            for attempt in range(LOLICON_429_MAX_RETRY + 1):
                try:
                    resp = await self.session.get(
                        api, params=params, impersonate=IMPERSONATE, timeout=timeout
                    )
                except Exception as e:
                    logger.debug(f"{LOG_PREFIX} lolicon 失败 {type(e).__name__} tag={tag}")
                    self._lolicon_last_req = time.monotonic()
                    return None
                self._lolicon_last_req = time.monotonic()
                if resp.status_code == 429:
                    self._lolicon_backoff_until = time.monotonic() + LOLICON_429_BACKOFF
                    logger.warning(
                        f"{LOG_PREFIX} lolicon 429 tag={tag} "
                        f"attempt={attempt+1}/{LOLICON_429_MAX_RETRY+1}"
                    )
                    if attempt < LOLICON_429_MAX_RETRY:
                        await asyncio.sleep(LOLICON_429_BACKOFF)
                        continue
                    return None
                break

        if resp is None or resp.status_code != 200:
            return None
        text = resp.text
        if text.strip() == ":D":
            self._lolicon_backoff_until = time.monotonic() + LOLICON_429_BACKOFF
            logger.warning(f"{LOG_PREFIX} lolicon :D tag={tag}")
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if data.get("error"):
            return None
        items = data.get("data") or []
        if not items:
            return None
        chooser = rng or random
        item = chooser.choice(items)
        urls = item.get("urls") or {}
        url = urls.get("regular") or urls.get("original")
        return self._rewrite_to_proxy(url)

    async def _search_danbooru(self, tag: str, rng=None):
        if not tag:
            return None
        params = {"tags": f"{tag} rating:general", "limit": 20}
        try:
            resp = await self.session.get(
                DANBOORU_API, params=params, impersonate=IMPERSONATE,
                timeout=self._cfg_float("api_timeout", 5.0),
            )
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if not isinstance(data, list) or not data:
            return None
        items = [i for i in data if i.get("file_url") or i.get("large_file_url")]
        if not items:
            return None
        item = (rng or random).choice(items)
        return item.get("large_file_url") or item.get("file_url")

    async def _search_safebooru(self, tag: str, rng=None):
        if not tag:
            return None
        params = {"page": "dapi", "s": "post", "q": "index", "json": "1", "limit": "20", "tags": tag}
        try:
            resp = await self.session.get(
                SAFEBOORU_API, params=params, impersonate=IMPERSONATE,
                timeout=self._cfg_float("api_timeout", 5.0),
            )
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if not isinstance(data, list) or not data:
            return None
        item = (rng or random).choice(data)
        url = item.get("file_url") or item.get("sample_url") or ""
        if url and not url.startswith("http"):
            url = "https:" + url
        return url or None

    async def _search_yandere(self, tag: str, rng=None):
        if not tag:
            return None
        params = {"tags": f"{tag} rating:safe", "limit": 20}
        try:
            resp = await self.session.get(
                YANDERE_API, params=params, impersonate=IMPERSONATE,
                timeout=self._cfg_float("api_timeout", 5.0),
            )
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if not isinstance(data, list) or not data:
            return None
        items = [i for i in data if i.get("file_url") or i.get("sample_url")]
        if not items:
            return None
        item = (rng or random).choice(items)
        return item.get("file_url") or item.get("sample_url")

    # ───────────────────── 统一取图 ─────────────────────

    async def _try_url(self, url: str, referer: str, tried_hashes: set):
        if not url:
            return None, ""
        path = await self._download(url, referer=referer)
        if not path:
            return None, ""
        h = self._file_hash(path)
        if h and tried_hashes and h in tried_hashes:
            try:
                pathlib.Path(path).unlink()
            except Exception:
                pass
            return None, ""
        return path, h or ""

    async def _fetch_wife_image_path(self, wife: dict, rng=None, exclude_hash: str = ""):
        if not self._cfg_bool("send_image", True):
            return None, ""
        chooser = rng or random
        tried_urls = set()
        tried_hashes = set()
        if exclude_hash:
            tried_hashes.add(exclude_hash)

        name = (wife.get("name") or "").strip()
        cn_name = (wife.get("cn_name") or "").strip()
        game = (wife.get("game_name") or "").strip()

        # 1. Lolicon
        for tag in (name, cn_name, game):
            tag = (tag or "").strip()
            if not tag:
                continue
            for _ in range(BG_RETRY_PER_TAG):
                url = await self._search_lolicon(tag, num=50, rng=chooser)
                if not url:
                    break
                if url in tried_urls:
                    continue
                tried_urls.add(url)
                path, h = await self._try_url(url, PIXIV_REFERER, tried_hashes)
                if path:
                    if h:
                        tried_hashes.add(h)
                    logger.info(f"{LOG_PREFIX} 命中 lolicon tag={tag}")
                    return path, h

        # 2. Danbooru/Safebooru/Yande.re
        if _HAS_KAKASI:
            romaji_name = self._get_romaji(wife)
            romaji_game = to_romaji(game) if game else ""
            booru_tags = []
            for base in (romaji_name, romaji_game):
                for t in make_booru_tags(base):
                    if t and t not in booru_tags:
                        booru_tags.append(t)

            for source_name, fn in (
                ("danbooru", self._search_danbooru),
                ("safebooru", self._search_safebooru),
                ("yandere", self._search_yandere),
            ):
                for tag in booru_tags:
                    url = await fn(tag, rng=chooser)
                    if not url or url in tried_urls:
                        continue
                    tried_urls.add(url)
                    path, h = await self._try_url(url, "", tried_hashes)
                    if path:
                        if h:
                            tried_hashes.add(h)
                        logger.info(f"{LOG_PREFIX} 命中 {source_name} tag={tag}")
                        return path, h

        # 3. main_img
        main_img = (wife.get("main_img") or "").strip()
        if main_img:
            path, h = await self._try_url(main_img, "", tried_hashes)
            if path:
                logger.info(f"{LOG_PREFIX} 兜底 main_img name={name}")
                return path, h

        return None, ""

    async def _draw_wife(self, rng, exclude_keys=None):
        exclude_keys = exclude_keys or set()
        max_attempts = max(1, self._cfg_int("max_retry_per_wife", 5))
        filter_sensitive = self._cfg_bool("enable_sensitive_filter", False)

        candidates = [w for w in self.heroines if self._wife_key(w) not in exclude_keys]
        rng.shuffle(candidates)
        candidates.sort(key=lambda w: 1 if self._wife_key(w) in self._failed_cache else 0)

        tried = 0
        for wife in candidates:
            if tried >= max_attempts:
                break
            tried += 1
            if filter_sensitive and has_sensitive(wife.get("intro", ""), SENSITIVE_TERMS):
                logger.debug(f"{LOG_PREFIX} 敏感词跳过 name={wife['name']}")
                continue
            img_path, _ = await self._fetch_wife_image_path(wife, rng=rng)
            if img_path:
                return wife, img_path
            logger.info(f"{LOG_PREFIX} 第 {tried} 个角色失败，换下一个")
            self._record_failure(wife, reason="send_failed")
        return None, None

    # ───────────────────── T2I ─────────────────────

    async def _render_card(self, wife, img_path, user_name, fortune, cost_text="", balance=None):
        img_b64 = await asyncio.to_thread(self._path_to_data_url, img_path)
        max_len = self._cfg_int("intro_max_len", 300)
        intro = wife["intro"] or "暂无介绍"
        if max_len > 0 and len(intro) > max_len:
            intro = intro[:max_len] + "……"
        display_name = wife.get("cn_name") or wife["name"]
        now = datetime.now()
        user_initial = (user_name or "你").strip()[:1] or "你"
        data = {
            "user_name": user_name,
            "user_initial": user_initial,
            "name": display_name,
            "game": wife.get("game_name") or "未知",
            "intro": intro,
            "fortune": fortune,
            "img_b64": img_b64,
            "date": now.strftime("%Y-%m-%d %A"),
            "cost_text": cost_text or "",
            "balance": balance if balance is not None else "",
            "theme": str(self._cfg("card_theme", "warm") or "warm"),
        }
        options = {"type": "jpeg", "quality": 95, "full_page": True}
        img_url = await self.html_render(T2I_TEMPLATE, data, options=options)
        return str(img_url)

    # ───────────────────── 发送 ─────────────────────

    def _make_at(self, uid):
        try:
            return At(qq=uid)
        except TypeError:
            return At(user_id=uid)

    async def _send_wife(self, event, wife, img_path, fortune="", cost_text="", balance=None):
        if not img_path or not pathlib.Path(img_path).exists():
            return False
        uid = event.get_sender_id()
        try:
            user_name = event.get_sender_name() or "你"
        except Exception:
            user_name = "你"
        try:
            card_url = await self._render_card(
                wife, img_path, user_name, fortune,
                cost_text=cost_text, balance=balance,
            )
            img_comp = (
                Image.fromURL(card_url)
                if card_url.startswith("http")
                else Image.fromFileSystem(card_url)
            )
            await event.send(event.chain_result([self._make_at(uid), img_comp]))
            logger.info(f"{LOG_PREFIX} 卡片已发送 name={wife['name']}")
            return True
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} T2I 渲染失败 {type(e).__name__}: {str(e)[:120]}")

        # 降级
        try:
            max_len = self._cfg_int("intro_max_len", 200)
            intro = wife["intro"] or "暂无介绍"
            if max_len > 0 and len(intro) > max_len:
                intro = intro[:max_len] + "……"
            display_name = wife.get("cn_name") or wife["name"]
            text = (
                f"✨ --- 今日 Gal 运势 --- ✨\n"
                f"👤 羁绊角色：{display_name}\n"
                f"📖 作品出处：{wife.get('game_name') or '未知'}\n"
                f"📝 角色介绍：{intro}\n"
                f"🧧 签运：【{fortune}】"
            )
            if cost_text:
                text += f"\n💰 {cost_text}"
            await event.send(event.chain_result([
                self._make_at(uid),
                Image.fromFileSystem(str(img_path)),
                Plain(text),
            ]))
            return True
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 降级发送失败 {type(e).__name__}")
            return False

    async def _send_text_at(self, event, text: str):
        uid = event.get_sender_id()
        try:
            await event.send(event.chain_result([self._make_at(uid), Plain(text)]))
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 文字发送失败 {type(e).__name__}")

    async def _send_text(self, event, text: str):
        try:
            await event.send(event.chain_result([Plain(text)]))
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 文字发送失败 {type(e).__name__}")

    def _extract_keyword(self, event, cmd_name: str) -> str:
        raw = event.get_message_str().strip()
        for p in (f"/{cmd_name}", cmd_name):
            idx = raw.find(p)
            if idx >= 0:
                return raw[idx + len(p):].strip()
        return ""

    # ───────────────────── 指令：抽卡 ─────────────────────

    @filter.command("今日老婆")
    async def cmd_daily(self, event: AstrMessageEvent):
        event.stop_event()
        if not self.heroines:
            await self._send_text_at(event, "❌ 老婆数据为空，请检查 wives_rich.jsonl")
            return
        uid = event.get_sender_id()
        gid = self._group_id(event)
        today = datetime.now().strftime("%Y%m%d")
        state_key = f"{uid}_{today}"
        cache_path = self._cache_img_path(uid, today)

        saved = self._today_state.get(state_key)
        if saved and cache_path.exists():
            wife = self._find_wife_by_key(saved.get("wife_key", ""))
            if wife:
                fortune = saved.get("fortune", "大吉")
                if await self._send_wife(event, wife, cache_path, fortune=fortune):
                    logger.info(f"{LOG_PREFIX} 今日老婆 缓存命中 name={wife['name']}")
                    return

        rng = random.Random(f"{uid}_{today}")
        wife, img_path = await self._draw_wife(rng)
        if wife is None:
            await self._send_text_at(event, "😢 换了好几个都发不出去，稍后再试试吧")
            return
        try:
            shutil.copy(str(img_path), str(cache_path))
        except Exception as e:
            logger.warning(f"{LOG_PREFIX} 缓存图失败: {type(e).__name__}")
        fortune = rng.choice(FORTUNES)
        self._today_state[state_key] = {
            "wife_key": self._wife_key(wife),
            "fortune": fortune,
        }
        self._save_today_state()
        self._save_romaji_cache()
        await self._record_draw(uid, gid, wife, "daily")
        await self._send_wife(event, wife, cache_path, fortune=fortune)

    @filter.command("换老婆")
    async def cmd_reroll(self, event: AstrMessageEvent):
        event.stop_event()
        if not self.heroines:
            await self._send_text_at(event, "❌ 老婆数据为空")
            return
        uid = event.get_sender_id()
        gid = self._group_id(event)
        today = datetime.now().strftime("%Y%m%d")
        state_key = f"{uid}_{today}"
        cache_path = self._cache_img_path(uid, today)

        cost = self._cfg_int("reroll_cost", 20)
        allowed, msg, balance = await self._charge_coins(event, cost)
        if not allowed:
            await self._send_text_at(event, f"❌ {msg}")
            return

        rng = random.Random()
        wife, img_path = await self._draw_wife(rng)
        if wife is None:
            if cost > 0:
                await self._refund_coins(event, cost)
            await self._send_text_at(event, "😢 换了好几个都发不出去，金币已退还")
            return
        try:
            shutil.copy(str(img_path), str(cache_path))
        except Exception:
            pass
        fortune = rng.choice(FORTUNES)
        self._today_state[state_key] = {"wife_key": self._wife_key(wife), "fortune": fortune}
        self._save_today_state()
        self._save_romaji_cache()
        await self._record_draw(uid, gid, wife, "reroll")
        await self._send_wife(event, wife, cache_path, fortune=fortune,
                             cost_text=msg, balance=balance)

    @filter.command("换背景")
    async def cmd_change_bg(self, event: AstrMessageEvent):
        event.stop_event()
        uid = event.get_sender_id()
        today = datetime.now().strftime("%Y%m%d")
        state_key = f"{uid}_{today}"
        cache_path = self._cache_img_path(uid, today)
        saved = self._today_state.get(state_key)
        if not saved:
            await self._send_text_at(event, "❌ 先发 /今日老婆 再换背景")
            return
        wife = self._find_wife_by_key(saved.get("wife_key", ""))
        if wife is None:
            await self._send_text_at(event, "❌ 存档角色找不到，请重新 /今日老婆")
            return
        cost = self._cfg_int("bg_cost", 10)
        allowed, msg, balance = await self._charge_coins(event, cost)
        if not allowed:
            await self._send_text_at(event, f"❌ {msg}")
            return
        old_hash = self._file_hash(cache_path) if cache_path.exists() else ""
        rng = random.Random(time.time_ns())
        img_path, _ = await self._fetch_wife_image_path(wife, rng=rng, exclude_hash=old_hash)
        if not img_path:
            if cost > 0:
                await self._refund_coins(event, cost)
            await self._send_text_at(event, "😢 找不到更多不同的图了，金币已退还")
            return
        try:
            shutil.copy(str(img_path), str(cache_path))
        except Exception:
            pass
        fortune = saved.get("fortune", "大吉")
        await self._send_wife(event, wife, cache_path, fortune=fortune,
                             cost_text=msg, balance=balance)

    @filter.command("随机老婆")
    async def cmd_random(self, event: AstrMessageEvent):
        event.stop_event()
        if not self.heroines:
            await self._send_text_at(event, "❌ 老婆数据为空")
            return
        uid = event.get_sender_id()
        gid = self._group_id(event)
        today = datetime.now().strftime("%Y%m%d")
        state_key = f"{uid}_{today}"
        cache_path = self._cache_img_path(uid, today)

        cost = self._cfg_int("random_cost", 20)
        allowed, msg, balance = await self._charge_coins(event, cost)
        if not allowed:
            await self._send_text_at(event, f"❌ {msg}")
            return

        rng = random.Random()
        wife, img_path = await self._draw_wife(rng)
        if wife is None:
            if cost > 0:
                await self._refund_coins(event, cost)
            await self._send_text_at(event, "😢 抽不出来，金币已退还")
            return
        try:
            shutil.copy(str(img_path), str(cache_path))
        except Exception:
            pass
        fortune = rng.choice(FORTUNES)
        self._today_state[state_key] = {"wife_key": self._wife_key(wife), "fortune": fortune}
        self._save_today_state()
        self._save_romaji_cache()
        await self._record_draw(uid, gid, wife, "random")
        await self._send_wife(event, wife, cache_path, fortune=fortune,
                             cost_text=msg, balance=balance)

    # ───────────────────── 指令：角色 ─────────────────────

    @filter.command("搜老婆")
    async def cmd_search(self, event: AstrMessageEvent, keyword: str = ""):
        event.stop_event()
        keyword = (keyword or "").strip() or self._extract_keyword(event, "搜老婆")
        if not keyword:
            await self._send_text_at(event, "用法：/搜老婆 <关键词>")
            return
        if not self.heroines:
            await self._send_text_at(event, "❌ 老婆数据为空")
            return
        kw = keyword.lower()
        matches = []
        for w in self.heroines:
            name = (w.get("name") or "").lower()
            cn = (w.get("cn_name") or "").lower()
            game = (w.get("game_name") or "").lower()
            if kw in name or kw in cn or kw in game:
                matches.append(w)
            if len(matches) >= 10:
                break
        if not matches:
            await self._send_text_at(event, f"🔍 没找到《{keyword}》相关角色")
            return
        lines = [f"🔍 找到 {len(matches)} 个相关角色："]
        for i, w in enumerate(matches, 1):
            display = w.get("cn_name") or w.get("name")
            lines.append(f"{i}. {display} — {w.get('game_name') or '未知'}")
        lines.append(f"\n用 /今日老婆 抽卡")
        await self._send_text_at(event, "\n".join(lines))

    @filter.command("老婆详情")
    async def cmd_detail(self, event: AstrMessageEvent):
        event.stop_event()
        uid = event.get_sender_id()
        today = datetime.now().strftime("%Y%m%d")
        saved = self._today_state.get(f"{uid}_{today}")
        if not saved:
            await self._send_text_at(event, "❌ 还没抽过，先发 /今日老婆")
            return
        wife = self._find_wife_by_key(saved.get("wife_key", ""))
        if not wife:
            await self._send_text_at(event, "❌ 存档角色找不到")
            return
        display = wife.get("cn_name") or wife.get("name")
        intro = wife.get("intro") or "暂无介绍"
        if len(intro) > 2000:
            intro = intro[:2000] + "……"
        text = (
            f"📖 角色详情\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 {display}\n"
            f"🎮 {wife.get('game_name') or '未知'}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{intro}"
        )
        await self._send_text_at(event, text)

    # ───────────────────── 指令：收藏 ─────────────────────

    @filter.command("收藏老婆")
    async def cmd_favorite(self, event: AstrMessageEvent):
        event.stop_event()
        uid = event.get_sender_id()
        today = datetime.now().strftime("%Y%m%d")
        saved = self._today_state.get(f"{uid}_{today}")
        if not saved:
            await self._send_text_at(event, "❌ 先发 /今日老婆")
            return
        wife = self._find_wife_by_key(saved.get("wife_key", ""))
        if not wife:
            await self._send_text_at(event, "❌ 存档角色找不到")
            return
        async with self._user_data_lock:
            data = self._load_user_data(uid)
            key = self._wife_key(wife)
            favs = data.get("favorites", [])
            if any(f.get("wife_key") == key for f in favs):
                await self._send_text_at(event, "💡 已经收藏过了")
                return
            if len(favs) >= FAVORITES_MAX:
                await self._send_text_at(event, f"❌ 收藏已满（{FAVORITES_MAX} 个），请先取消一些")
                return
            favs.append({
                "wife_key": key,
                "name": wife.get("cn_name") or wife.get("name"),
                "game_name": wife.get("game_name"),
                "intro": wife.get("intro"),
                "added_at": datetime.now().isoformat(timespec="seconds"),
            })
            data["favorites"] = favs
            self._save_user_data(uid, data)
        await self._send_text_at(event, f"❤️ 已收藏：{wife.get('cn_name') or wife.get('name')}")

    @filter.command("我的收藏")
    async def cmd_my_favorites(self, event: AstrMessageEvent, page: str = ""):
        event.stop_event()
        uid = event.get_sender_id()
        page = (page or "").strip() or self._extract_keyword(event, "我的收藏")
        try:
            page_num = max(1, int(page)) if page else 1
        except ValueError:
            page_num = 1
        data = self._load_user_data(uid)
        favs = data.get("favorites", [])
        if not favs:
            await self._send_text_at(event, "📭 还没有收藏，用 /收藏老婆 添加")
            return
        total_pages = max(1, (len(favs) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_num = min(page_num, total_pages)
        start = (page_num - 1) * PAGE_SIZE
        items = favs[start:start + PAGE_SIZE]
        lines = [f"❤️ 我的收藏（{len(favs)} 个，第 {page_num}/{total_pages} 页）"]
        for i, f in enumerate(items, start + 1):
            lines.append(f"{i}. {f.get('name')} — {f.get('game_name') or '未知'}")
        if total_pages > 1:
            lines.append(f"\n用 /我的收藏 {page_num + 1 if page_num < total_pages else 1} 翻页")
        await self._send_text_at(event, "\n".join(lines))

    @filter.command("取消收藏")
    async def cmd_unfavorite(self, event: AstrMessageEvent, index: str = ""):
        event.stop_event()
        uid = event.get_sender_id()
        index = (index or "").strip() or self._extract_keyword(event, "取消收藏")
        try:
            idx = int(index)
        except ValueError:
            await self._send_text_at(event, "用法：/取消收藏 <序号>")
            return
        async with self._user_data_lock:
            data = self._load_user_data(uid)
            favs = data.get("favorites", [])
            if idx < 1 or idx > len(favs):
                await self._send_text_at(event, f"❌ 序号超出范围（1-{len(favs)}）")
                return
            removed = favs.pop(idx - 1)
            data["favorites"] = favs
            self._save_user_data(uid, data)
        await self._send_text_at(event, f"🗑️ 已移除收藏：{removed.get('name')}")

    # ───────────────────── 指令：记录 ─────────────────────

    @filter.command("老婆历史")
    async def cmd_history(self, event: AstrMessageEvent):
        event.stop_event()
        uid = event.get_sender_id()
        data = self._load_user_data(uid)
        hist = data.get("history", [])
        if not hist:
            await self._send_text_at(event, "📭 还没有抽卡记录")
            return
        lines = [f"📜 最近抽卡记录（共 {len(hist)} 条）"]
        for i, h in enumerate(hist[:15], 1):
            lines.append(f"{i}. {h.get('name')} — {h.get('game_name') or '未知'}  [{h.get('date', '')[-5:]}]")
        await self._send_text_at(event, "\n".join(lines))

    @filter.command("老婆排行")
    async def cmd_ranking(self, event: AstrMessageEvent):
        event.stop_event()
        gid = self._group_id(event)
        if not gid:
            await self._send_text_at(event, "❌ 该指令只能在群聊使用")
            return
        stats = self._load_group_stats()
        g = stats.get(gid)
        if not g or not g.get("user_counts"):
            await self._send_text_at(event, "📭 本群还没有抽卡记录")
            return
        counts = sorted(g["user_counts"].items(), key=lambda x: -x[1])[:10]
        lines = [f"🏆 本群抽卡排行（共 {g.get('total_draws', 0)} 次）"]
        for i, (uid, cnt) in enumerate(counts, 1):
            lines.append(f"{i}. UID {uid} — {cnt} 次")
        await self._send_text_at(event, "\n".join(lines))

    @filter.command("老婆统计")
    async def cmd_stats(self, event: AstrMessageEvent):
        event.stop_event()
        gid = self._group_id(event)
        uid = event.get_sender_id()
        data = self._load_user_data(uid)
        user_stats = data.get("stats", {})
        lines = [
            f"📊 个人统计",
            f"抽卡总次数：{user_stats.get('total_draws', 0)}",
            f"抽到不同角色：{user_stats.get('unique_wives', 0)}",
            f"收藏数量：{len(data.get('favorites', []))}",
        ]
        if gid:
            stats = self._load_group_stats()
            g = stats.get(gid) or {}
            lines.extend([
                f"",
                f"📊 本群统计",
                f"总抽卡次数：{g.get('total_draws', 0)}",
                f"活跃用户数：{len(g.get('user_counts', {}))}",
            ])
        await self._send_text_at(event, "\n".join(lines))

    # ───────────────────── 指令：帮助 ─────────────────────

    @filter.command("老婆帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        event.stop_event()
        await self._send_text(event, HELP_TEXT)

    # ───────────────────── 指令：管理 ─────────────────────

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("调试联动")
    async def cmd_debug_link(self, event: AstrMessageEvent):
        event.stop_event()
        lines = ["🔍 调试 galwife"]
        self._getpx_db_path = None
        db = self._resolve_getpx_db()
        lines.append(f"1. 数据库: {'✅' if db else '❌'}")
        if db is not None:
            uid = str(event.get_sender_id() or "")
            lines.append(f"2. UID: {uid}")
            try:
                _, balance, _ = await asyncio.to_thread(self._sqlite_spend, str(db), uid, 0)
                lines.append(f"3. 余额: {balance}")
            except Exception as e:
                lines.append(f"3. 读余额出错: {type(e).__name__}")
        lines.append(f"4. pykakasi: {'✅' if _HAS_KAKASI else '❌'}")
        uid = str(event.get_sender_id() or "")
        today = datetime.now().strftime("%Y%m%d")
        saved = self._today_state.get(f"{uid}_{today}")
        lines.append(f"5. 存档: {saved}")
        cache_path = self._cache_img_path(uid, today)
        lines.append(f"6. 本地图: {'✅' if cache_path.exists() else '❌'}")
        lines.append(f"7. 数据目录: {self.data_dir}")
        await self._send_text_at(event, "\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重载老婆数据")
    async def cmd_reload(self, event: AstrMessageEvent):
        event.stop_event()
        self._reload()
        self._load_failed_cache()
        self._load_today_state()
        await self._send_text_at(event, f"🔄 已重载 {len(self.heroines)} 个角色")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("老婆失败记录")
    async def cmd_failed(self, event: AstrMessageEvent):
        event.stop_event()
        if not self._failed_cache:
            await self._send_text_at(event, "✅ 目前没有失败记录")
            return
        lines = sorted(self._failed_cache)
        text = f"📋 失败角色共 {len(lines)} 个：\n" + "\n".join(lines[:50])
        if len(lines) > 50:
            text += f"\n…… 还有 {len(lines) - 50} 个"
        await self._send_text_at(event, text)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("清空失败记录")
    async def cmd_clear_failed(self, event: AstrMessageEvent):
        event.stop_event()
        try:
            p = self.data_dir / "failed_wives.txt"
            if p.exists():
                p.unlink()
            self._failed_cache = set()
            await self._send_text_at(event, "🗑️ 失败记录已清空")
        except Exception as e:
            await self._send_text_at(event, f"❌ 清空失败：{type(e).__name__}")