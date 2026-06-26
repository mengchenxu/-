"""游戏意图检测 — 非@消息命中关键词 → 轻量 LLM 意图分类 → 回复游戏列表"""
import logging
from typing import Optional

from src.config import AppConfig
from src.parse import ParsedMsg

logger = logging.getLogger(__name__)

# 意图分类 prompt
_INTENT_PROMPT = """你是一个意图分类器。判断用户消息是否表达"想玩游戏"的意图。

规则：
- 用户明确表示想玩游戏、想打发时间、觉得无聊想找点乐子 → 回复"想玩"
- 用户只是在聊天中提到了游戏相关词，但不是想现在玩游戏 → 回复"不想玩"
- 用户聊到游戏但无关紧要（如"昨天玩了游戏"）→ 回复"不想玩"
- 只回复"想玩"或"不想玩"，不要有任何其他文字

用户消息：{content}

回复："""


class GameIntentDetector:
    """游戏意图检测器。扫描关键词 → LLM 轻量分类 → 返回检测结果。"""

    def __init__(self, config: AppConfig, llm_chat_fn=None):
        """
        Args:
            config: 应用配置，读取 game 段。
            llm_chat_fn: 可选的 LLM 调用函数，签名 (messages, model, temperature, max_tokens) -> str。
                         用于测试注入 mock。为 None 时使用默认（需要 LLMClient）。
        """
        self.config = config
        self.game_cfg = config.game
        self.keywords = [kw.lower() for kw in self.game_cfg.keywords]
        self._llm_chat_fn = llm_chat_fn

    def has_keywords(self, content: str) -> bool:
        """检查消息是否包含游戏关键词。"""
        lower = content.lower()
        return any(kw in lower for kw in self.keywords)

    def classify_intent(self, content: str) -> str:
        """调用轻量 LLM 判断用户意图。返回 '想玩' 或 '不想玩'。"""
        prompt = _INTENT_PROMPT.format(content=content[:200])

        if self._llm_chat_fn:
            # 使用注入的 mock（测试用）
            raw = self._llm_chat_fn(
                messages=[{"role": "user", "content": prompt}],
                model=self.game_cfg.intent_model,
                temperature=self.game_cfg.intent_temperature,
                max_tokens=self.game_cfg.intent_max_tokens,
            )
        else:
            # 生产环境：创建临时 LLM client
            from src.llm import LLMClient
            llm = LLMClient(self.config)
            raw = self._call_intent(llm, prompt)

        result = raw.strip()
        if "不想玩" in result:
            return "不想玩"
        if "想玩" in result:
            return "想玩"
        return "不想玩"  # 失败/未知时保守处理，不误触发

    def _call_intent(self, llm, prompt: str) -> str:
        """通过标准 LLMClient 调用意图分类。"""
        try:
            messages = [
                {"role": "system", "content": "你是一个意图分类器。只回复'想玩'或'不想玩'。"},
                {"role": "user", "content": prompt},
            ]
            resp = llm.client.chat.completions.create(
                model=self.game_cfg.intent_model,
                messages=messages,
                max_tokens=self.game_cfg.intent_max_tokens,
                temperature=self.game_cfg.intent_temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            logger.exception("Game intent LLM call failed")
            return "不想玩"  # 失败时保守处理，不误触发

    def detect(self, parsed: ParsedMsg) -> Optional[str]:
        """完整检测流程：关键词 → 意图分类 → 返回结果。
        返回 '想玩' / '不想玩' / None（无关键词不触发）。
        """
        if not self.game_cfg.enabled:
            return None
        if not self.has_keywords(parsed.content):
            return None
        return self.classify_intent(parsed.content)

    def get_game_list(self) -> str:
        """返回格式化的游戏列表文本。"""
        cmds = self.game_cfg.commands
        if not cmds:
            return "暂时还没有可用的游戏喵~"

        lines = ["人家可以陪你玩这些游戏喵~ 🎮"]
        for cmd in cmds:
            name = cmd.get("name", "")
            desc = cmd.get("description", "")
            if desc:
                lines.append(f"  {name} — {desc}")
            else:
                lines.append(f"  {name}")
        lines.append("\n在群里 @鼠鼠 加上命令就可以玩了哟 ✨")
        return "\n".join(lines)
