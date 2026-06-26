"""配置加载 — 从 config.yaml + .env 读取并返回结构化配置"""
import os
from dataclasses import dataclass, field

import yaml


def _load_dotenv(dotenv_path: str = ".env") -> dict[str, str]:
    """从 .env 文件读取键值对（简易版，不依赖 python-dotenv）。"""
    result: dict[str, str] = {}
    if not os.path.exists(dotenv_path):
        return result
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value
    return result


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 2048
    temperature: float = 0.85


@dataclass
class BotConfig:
    name: str = "鼠鼠"
    system_prompt: str = ""
    reply_cooldown_seconds: int = 3


@dataclass
class ProactiveConfig:
    enabled: bool = True
    cold_silence_minutes: int = 30
    schedule_times: list = field(default_factory=lambda: ["08:30", "12:30", "18:00", "22:00"])
    hot_topic_interval_hours: int = 4
    max_per_day: int = 10
    min_interval_minutes: int = 30
    quiet_hours: list = field(default_factory=lambda: ["02:00", "06:00"])


@dataclass
class GameConfig:
    enabled: bool = True
    keywords: list = field(default_factory=lambda: ["游戏", "无聊", "玩", "来点"])
    commands: list = field(default_factory=lambda: [
        {"name": "/骰子", "description": "掷骰子 — 随机 1-6"},
        {"name": "/猜拳", "description": "石头剪刀布"},
        {"name": "/硬币", "description": "抛硬币 — 正面还是反面"},
    ])
    intent_model: str = "deepseek-chat"
    intent_temperature: float = 0.1
    intent_max_tokens: int = 2


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    game: GameConfig = field(default_factory=GameConfig)
    weflow_token: str = ""
    enable_search: bool = True


def load_config(path: str = "config/config.yaml") -> AppConfig:
    """从 YAML + .env 加载配置。.env 的 api_key 优先于 YAML 中的。"""
    dotenv = _load_dotenv()

    if not os.path.exists(path):
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = AppConfig()

    llm_raw = raw.get("llm", {})
    # api_key: .env > config.yaml > ""
    api_key = dotenv.get("DEEPSEEK_API_KEY") or llm_raw.get("api_key") or ""
    config.llm = LLMConfig(
        provider=llm_raw.get("provider", "deepseek"),
        api_key=api_key,
        base_url=llm_raw.get("base_url", "https://api.deepseek.com"),
        model=llm_raw.get("model", "deepseek-chat"),
        max_tokens=llm_raw.get("max_tokens", 2048),
        temperature=llm_raw.get("temperature", 0.85),
    )

    bot_raw = raw.get("bot", {})
    config.bot = BotConfig(
        name=bot_raw.get("name", "鼠鼠"),
        system_prompt=bot_raw.get("system_prompt", ""),
        reply_cooldown_seconds=bot_raw.get("reply_cooldown_seconds", 3),
    )

    proactive_raw = raw.get("proactive", {})
    config.proactive = ProactiveConfig(
        enabled=proactive_raw.get("enabled", True),
        cold_silence_minutes=proactive_raw.get("cold_silence_minutes", 30),
        schedule_times=proactive_raw.get("schedule_times", ["08:30", "12:30", "18:00", "22:00"]),
        hot_topic_interval_hours=proactive_raw.get("hot_topic_interval_hours", 4),
        max_per_day=proactive_raw.get("max_per_day", 10),
        min_interval_minutes=proactive_raw.get("min_interval_minutes", 30),
        quiet_hours=proactive_raw.get("quiet_hours", ["02:00", "06:00"]),
    )

    game_raw = raw.get("game", {})
    config.game = GameConfig(
        enabled=game_raw.get("enabled", True),
        keywords=game_raw.get("keywords", ["游戏", "无聊", "玩", "来点"]),
        commands=game_raw.get("commands", [
            {"name": "/骰子", "description": "掷骰子 — 随机 1-6"},
            {"name": "/猜拳", "description": "石头剪刀布"},
            {"name": "/硬币", "description": "抛硬币 — 正面还是反面"},
        ]),
        intent_model=game_raw.get("intent_model", "deepseek-chat"),
        intent_temperature=float(game_raw.get("intent_temperature", 0.1)),
        intent_max_tokens=int(game_raw.get("intent_max_tokens", 2)),
    )

    config.weflow_token = raw.get("weflow_token", "")
    config.enable_search = bot_raw.get("enable_search", True)

    return config
