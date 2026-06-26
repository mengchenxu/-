"""ProactiveSpeaker — 冷场/定时/热点主动发言后台线程"""
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from src.config import AppConfig
from src.store import Store, Group
from src.llm import LLMClient
from src.decode import DecodedReply

logger = logging.getLogger(__name__)


# ============================================================
# Prompt 构建
# ============================================================

def _build_cold_silence_prompt(group: Group, system_prompt: str) -> list[dict]:
    """构建冷场话题 prompt：基于群上下文 + 高频词 + 表情生成话题。"""
    context_text = group.context or "（暂无群聊背景）"
    emojis_text = " ".join(group.top_emojis) if group.top_emojis else "（暂无）"
    words_text = " ".join(group.top_words[:5]) if group.top_words else "（暂无）"

    user = f"""群已经安静了超过 30 分钟了喵~ 人家想出来聊聊天！

[群聊背景]
{context_text}

[群内常用表情]
{emojis_text}

[群内高频词]
{words_text}

请你以猫娘的口气，自然地说一句话来暖场破冰~ 可以：
- 用群里的高频词来开启话题
- 吐槽一下群里的氛围
- 聊聊群聊背景里的事情
- 或者随便卖个萌

要求：
- 1-3 句话，自然不做作
- 不要每句都带"喵"——真猫也有懒得叫的时候
- 可以适应当群的常用表情风格
- 不要提"30分钟"或"冷场"之类的字眼——说得像是你自己想聊天了一样"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]


def _build_schedule_prompt(group: Group, period: str, system_prompt: str) -> list[dict]:
    """构建定时问候 prompt：基于时段 + 群上下文。"""
    context_text = group.context or "（暂无群聊背景）"

    period_hints = {
        "早安": "早上/上午好，新的一天开始了",
        "上午": "上午好，工作/学习进行中",
        "午间": "中午好，午饭时间到",
        "午后": "下午好，午后有点困",
        "晚间": "晚上好，一天要结束了",
        "深夜": "夜深了，注意休息",
    }
    hint = period_hints.get(period, "问候大家")

    user = f"""现在是{period}时段喵~ {hint}

[群聊背景]
{context_text}

请你以猫娘的口气，说一句自然的{period}问候。要求：
- 1-2 句话，自然不做作
- 结合群聊背景（如果有的话），不要说空洞的问候
- 不要每句都带"喵"——真猫也有懒得叫的时候
- 不要提"定时"或"被动"之类的字眼——说得像是你自己想说话了一样"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]


def _build_hot_topic_prompt(search_text: str, system_prompt: str) -> list[dict]:
    """构建热点改写 prompt：把搜索结果改成猫娘风格分享。"""
    user = f"""人家刚刚去网上逛了一圈，发现了一些热点喵~ 帮人家用猫娘语气分享给群友们~

[搜索结果]
{search_text}

要求：
- 选 1-2 个最有趣/最热的话题分享
- 用猫娘的语气自然转述，带点吐槽/好奇/惊讶
- 3-5 句话，不要太长
- 不要每句都带"喵"
- 如果搜索结果不相关或太少，就说"今天网上没什么好玩的喵~"之类的"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]


# ============================================================
# ProactiveSpeaker
# ============================================================

class ProactiveSpeaker:
    """后台线程：每分钟检查冷场/定时/热点，自动发言。"""

    def __init__(self, store: Store, llm: LLMClient, config: AppConfig,
                 send_fn, weflow_client=None):
        self.store = store
        self.llm = llm
        self.config = config
        self.proactive_config = config.proactive
        self.bot_name = config.bot.name
        self.system_prompt = config.bot.system_prompt
        self._send = send_fn
        self.weflow = weflow_client

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 防刷屏状态（不持久化）
        self._last_proactive: Dict[str, float] = {}   # room_id → timestamp
        self._daily_counts: Dict[str, int] = {}        # room_id → 今日计数
        self._daily_date: str = ""                      # 用于重置每日计数
        self._last_hot_topic_check: float = 0.0

        # 调度的分钟级去重——防止同一分钟 tick 多次触发
        self._last_schedule_trigger: Dict[str, str] = {}  # room_id → "HH:MM"

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self):
        """启动后台线程。如果 config 禁用则不启动。"""
        if not self.proactive_config.enabled:
            logger.info("ProactiveSpeaker disabled in config, not starting")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="proactive")
        self._thread.start()
        logger.info("ProactiveSpeaker started (interval=60s)")

    def stop(self):
        """停止后台线程。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("ProactiveSpeaker stopped")

    # ================================================================
    # 主循环
    # ================================================================

    def _run(self):
        """主循环：每 60 秒 tick 一次。"""
        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("ProactiveSpeaker tick error")
            # 每 1 秒检查 _running，最多等 60 秒 → 支持快速退出
            for _ in range(60):
                if not self._running:
                    break
                time.sleep(1)

    def _tick(self):
        """一次检查周期：遍历所有活跃群，检查三种触发条件。"""
        now = time.time()
        now_dt = datetime.now()
        now_str = now_dt.strftime("%H:%M")
        today_str = now_dt.strftime("%Y-%m-%d")

        # 跨天重置每日计数
        if self._daily_date != today_str:
            self._daily_counts.clear()
            self._daily_date = today_str

        # 取 groups 快照防止迭代时字典被修改
        groups_snapshot = list(self.store._groups.items())

        for room_id, group in groups_snapshot:
            # 跳过从未有过消息的群
            if group.msg_count == 0:
                continue

            # 1. 冷场检测
            if self._should_cold_silence(group, now, now_str):
                self._trigger_cold_silence(group, now)

            # 2. 定时推送（去重：同一时段每群只触发一次）
            if self._should_schedule(group, now, now_str):
                self._trigger_schedule(group, now, now_str)

        # 3. 热点分享（全局检查，非每群独立）
        if self._should_hot_topic(now):
            self._trigger_hot_topic(now, now_str)

    # ================================================================
    # 触发条件判断
    # ================================================================

    def _should_cold_silence(self, group: Group, now: float, now_str: str) -> bool:
        """群 last_msg_at 超过阈值 → 冷场。"""
        cfg = self.proactive_config
        if group.last_msg_at == 0:
            return False
        silence_minutes = (now - group.last_msg_at) / 60
        if silence_minutes < cfg.cold_silence_minutes:
            return False
        return self._can_speak(group.room_id, now, now_str)

    def _should_schedule(self, group: Group, now: float, now_str: str) -> bool:
        """当前时间在 schedule_times 中 且 本群本时段未触发过。"""
        cfg = self.proactive_config
        if now_str not in cfg.schedule_times:
            return False
        # 去重：同一时段只触发一次
        last_trigger = self._last_schedule_trigger.get(group.room_id, "")
        if last_trigger == now_str:
            return False
        return self._can_speak(group.room_id, now, now_str)

    def _should_hot_topic(self, now: float) -> bool:
        """距上次热点检查超过间隔 → 触发。"""
        cfg = self.proactive_config
        hours_since = (now - self._last_hot_topic_check) / 3600
        return hours_since >= cfg.hot_topic_interval_hours

    # ================================================================
    # 防刷屏规则
    # ================================================================

    def _can_speak(self, room_id: str, now: float, now_str: str) -> bool:
        """检查每日上限 / 最小间隔 / 静音时段。"""
        cfg = self.proactive_config

        # 静音时段
        if cfg.quiet_hours and len(cfg.quiet_hours) >= 2:
            quiet_start = cfg.quiet_hours[0]
            quiet_end = cfg.quiet_hours[1]
            if quiet_start <= quiet_end:
                if quiet_start <= now_str <= quiet_end:
                    return False
            else:
                # 跨夜静音（如 22:00 - 06:00）
                if now_str >= quiet_start or now_str <= quiet_end:
                    return False

        # 每日上限
        if self._daily_counts.get(room_id, 0) >= cfg.max_per_day:
            return False

        # 最小间隔
        last = self._last_proactive.get(room_id, 0)
        if last > 0 and (now - last) < cfg.min_interval_minutes * 60:
            return False

        return True

    def _record_speak(self, room_id: str, now: float):
        """记录一次主动发言。"""
        self._last_proactive[room_id] = now
        self._daily_counts[room_id] = self._daily_counts.get(room_id, 0) + 1

    # ================================================================
    # 发言
    # ================================================================

    def _speak(self, room_id: str, text: str, now: float):
        """构造 DecodedReply 并通过 send() 发送。"""
        if not text or not text.strip():
            return
        decoded = DecodedReply(clean_text=text.strip())
        try:
            success = self._send(decoded, room_id, "")
            if success:
                self._record_speak(room_id, now)
                logger.info("Proactive sent: room=%s text=%s...",
                            room_id[:20], text[:60])
        except Exception:
            logger.exception("Proactive send failed: room=%s", room_id[:20])

    # ================================================================
    # 触发执行
    # ================================================================

    def _trigger_cold_silence(self, group: Group, now: float):
        """冷场 → LLM 生成话题 → 发送。"""
        try:
            messages = _build_cold_silence_prompt(group, self.system_prompt)
            reply = self.llm.chat(messages, tools_enabled=False)
            if reply:
                self._speak(group.room_id, reply, now)
        except Exception:
            logger.exception("Cold silence trigger failed: room=%s", group.room_id[:20])

    def _trigger_schedule(self, group: Group, now: float, now_str: str):
        """定时 → LLM 生成问候 → 发送。"""
        hour = int(now_str.split(":")[0])
        if 5 <= hour < 9:
            period = "早安"
        elif 9 <= hour < 12:
            period = "上午"
        elif 12 <= hour < 14:
            period = "午间"
        elif 14 <= hour < 18:
            period = "午后"
        elif 18 <= hour < 22:
            period = "晚间"
        else:
            period = "深夜"

        self._last_schedule_trigger[group.room_id] = now_str

        try:
            messages = _build_schedule_prompt(group, period, self.system_prompt)
            reply = self.llm.chat(messages, tools_enabled=False)
            if reply:
                self._speak(group.room_id, reply, now)
        except Exception:
            logger.exception("Schedule trigger failed: room=%s", group.room_id[:20])

    def _trigger_hot_topic(self, now: float, now_str: str):
        """热点分享 → web_search → LLM 改写 → 发送到所有活跃群。"""
        self._last_hot_topic_check = now

        try:
            from src.web_search import search_web, search_format_for_llm
            results = search_web("今日热点")
            if not results:
                logger.info("Hot topic: no search results")
                return

            result_text = search_format_for_llm(results)
            messages = _build_hot_topic_prompt(result_text, self.system_prompt)
            reply = self.llm.chat(messages, tools_enabled=False)
            if not reply:
                return

            # 发送到所有活跃群（每个群独立检查防刷屏）
            sent_count = 0
            groups_snapshot = list(self.store._groups.items())
            for room_id, group in groups_snapshot:
                if group.msg_count > 0 and self._can_speak(room_id, now, now_str):
                    self._speak(room_id, reply, now)
                    sent_count += 1

            logger.info("Hot topic sent to %d groups", sent_count)
        except Exception:
            logger.exception("Hot topic trigger failed")
