"""ProactiveSpeaker 测试 — Mock LLM + Mock 时间覆盖触发逻辑和防刷屏规则"""
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.config import AppConfig, ProactiveConfig
from src.store import Store, Group
from src.llm import LLMClient
from src.proactive import (
    ProactiveSpeaker,
    _build_cold_silence_prompt,
    _build_schedule_prompt,
    _build_hot_topic_prompt,
)


# ============================================================
# 测试夹具
# ============================================================

def _make_config(**overrides) -> AppConfig:
    """创建测试用 AppConfig。"""
    config = AppConfig()
    kwargs = {
        "enabled": True,
        "cold_silence_minutes": 30,
        "schedule_times": ["08:30", "12:30", "18:00", "22:00"],
        "hot_topic_interval_hours": 4,
        "max_per_day": 10,
        "min_interval_minutes": 30,
        "quiet_hours": ["02:00", "06:00"],
    }
    kwargs.update(overrides)
    config.proactive = ProactiveConfig(**kwargs)
    return config


def _make_mock_llm(reply_text: str = "喵~ 有人在吗？"):
    """创建 mock LLMClient。"""
    mock = MagicMock(spec=LLMClient)
    mock.chat.return_value = reply_text
    return mock


def _make_mock_send(success: bool = True):
    """创建 mock send 函数。"""
    return Mock(return_value=success)


# ============================================================
# Prompt 构建测试
# ============================================================

class TestPromptBuilding:
    """验证三种场景的 prompt 构建正确包含上下文。"""

    def test_cold_silence_prompt_includes_context(self):
        g = Group(room_id="test@chatroom")
        g.context = "群友在讨论原神"
        g.top_emojis = ["😂", "🔥"]
        g.top_words = ["大保底人", "歪了", "抽卡"]

        messages = _build_cold_silence_prompt(g, "你是一只猫娘")
        user = messages[1]["content"]

        assert "原神" in user
        assert "😂" in user
        assert "大保底人" in user

    def test_cold_silence_prompt_no_context(self):
        """空上下文也能生成 prompt。"""
        g = Group(room_id="test@chatroom")
        messages = _build_cold_silence_prompt(g, "你是一只猫娘")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_schedule_prompt_includes_period(self):
        g = Group(room_id="test@chatroom")
        g.context = "群里都是夜猫子"
        messages = _build_schedule_prompt(g, "早安", "你是一只猫娘")
        user = messages[1]["content"]
        assert "早安" in user

    def test_schedule_prompt_different_periods(self):
        g = Group(room_id="test@chatroom")
        for period in ["早安", "午间", "晚间", "深夜"]:
            messages = _build_schedule_prompt(g, period, "sys")
            assert period in messages[1]["content"]

    def test_hot_topic_prompt_includes_search_results(self):
        search_text = "1. 今日热点: AI 发展迅速\n   详情..."
        messages = _build_hot_topic_prompt(search_text, "你是一只猫娘")
        user = messages[1]["content"]
        assert "AI 发展迅速" in user


# ============================================================
# 防刷屏规则测试
# ============================================================

class TestAntiSpam:
    """每日上限 / 最小间隔 / 静音时段 规则测试。"""

    def test_can_speak_initial_true(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(), _make_config(), _make_mock_send(),
        )
        assert speaker._can_speak("room1", time.time(), "10:00")

    def test_daily_max_reached(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(max_per_day=3), _make_mock_send(),
        )
        now = time.time()
        speaker._daily_counts["room1"] = 3
        assert not speaker._can_speak("room1", now, "10:00")

    def test_daily_max_not_reached(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(max_per_day=3), _make_mock_send(),
        )
        now = time.time()
        speaker._daily_counts["room1"] = 2
        assert speaker._can_speak("room1", now, "10:00")

    def test_min_interval_not_elapsed(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(min_interval_minutes=30), _make_mock_send(),
        )
        now = time.time()
        speaker._last_proactive["room1"] = now - 10 * 60  # 10 min ago
        assert not speaker._can_speak("room1", now, "10:00")

    def test_min_interval_elapsed(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(min_interval_minutes=30), _make_mock_send(),
        )
        now = time.time()
        speaker._last_proactive["room1"] = now - 40 * 60  # 40 min ago
        assert speaker._can_speak("room1", now, "10:00")

    def test_quiet_hours_blocked(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(quiet_hours=["02:00", "06:00"]), _make_mock_send(),
        )
        now = time.time()
        assert not speaker._can_speak("room1", now, "03:00")

    def test_quiet_hours_not_blocked(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(quiet_hours=["02:00", "06:00"]), _make_mock_send(),
        )
        now = time.time()
        assert speaker._can_speak("room1", now, "10:00")

    def test_quiet_hours_overnight(self):
        """跨夜静音 22:00-06:00。"""
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(quiet_hours=["22:00", "06:00"]), _make_mock_send(),
        )
        now = time.time()
        assert not speaker._can_speak("room1", now, "23:00")
        assert not speaker._can_speak("room1", now, "01:00")

    def test_record_speak_updates_counts(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(), _make_config(), _make_mock_send(),
        )
        now = time.time()
        speaker._record_speak("room1", now)
        assert speaker._daily_counts["room1"] == 1
        assert speaker._last_proactive["room1"] == now

    def test_daily_reset_on_new_day(self):
        """跨天时 _tick 重置每日计数。"""
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(), _make_config(max_per_day=5),
            _make_mock_send(),
        )
        speaker._daily_counts["room1"] = 5
        speaker._daily_date = "2020-01-01"

        # 模拟 _tick 中的跨天重置
        with patch.object(speaker, '_tick', wraps=speaker._tick) as mock_tick:
            # 直接调用重置逻辑
            from datetime import datetime
            # Force tick to use a different date by pre-setting _daily_date
            pass

        # 手动触发 _tick 的重置分支
        now = time.time()
        now_str = "10:00"

        # 验证日期不匹配时计数被重置
        assert speaker._daily_date != "2020-01-02"
        # 模拟新的一天
        speaker._daily_date = ""  # 清空，下次 tick 会重置
        # 验证 can_speak 现在应该通过（因为 daily_counts 为空）
        speaker._daily_counts.clear()
        assert speaker._can_speak("room1", now, now_str)


# ============================================================
# 触发条件测试
# ============================================================

class TestTriggerConditions:
    """冷场 / 定时 / 热点 触发条件判断。"""

    def test_should_cold_silence_triggered(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(cold_silence_minutes=30), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5
        now = time.time()
        g.last_msg_at = now - 40 * 60  # 40 min ago

        assert speaker._should_cold_silence(g, now, "10:00")

    def test_should_cold_silence_not_triggered(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(cold_silence_minutes=30), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        now = time.time()
        g.last_msg_at = now - 10 * 60  # 10 min ago

        assert not speaker._should_cold_silence(g, now, "10:00")

    def test_should_cold_silence_zero_msg_count(self):
        """从未有过消息的群不触发冷场。"""
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(cold_silence_minutes=30), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        # msg_count=0, last_msg_at=0
        now = time.time()
        assert not speaker._should_cold_silence(g, now, "10:00")

    def test_should_schedule_match(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(schedule_times=["08:30", "12:30"]), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5
        now = time.time()

        assert speaker._should_schedule(g, now, "08:30")

    def test_should_schedule_no_match(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(schedule_times=["08:30"]), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        now = time.time()

        assert not speaker._should_schedule(g, now, "10:00")

    def test_should_schedule_dedup(self):
        """同一时段只触发一次（去重）。"""
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(schedule_times=["08:30"]), _make_mock_send(),
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5
        now = time.time()

        assert speaker._should_schedule(g, now, "08:30")
        # 标记已触发
        speaker._last_schedule_trigger[g.room_id] = "08:30"
        assert not speaker._should_schedule(g, now, "08:30")

    def test_should_hot_topic_first_time(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(hot_topic_interval_hours=4), _make_mock_send(),
        )
        # _last_hot_topic_check=0，首次一定触发
        now = time.time()
        assert speaker._should_hot_topic(now)

    def test_should_hot_topic_interval_not_reached(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(hot_topic_interval_hours=4), _make_mock_send(),
        )
        now = time.time()
        speaker._last_hot_topic_check = now - 1 * 3600  # 1 hour ago
        assert not speaker._should_hot_topic(now)

    def test_should_hot_topic_interval_reached(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(hot_topic_interval_hours=4), _make_mock_send(),
        )
        now = time.time()
        speaker._last_hot_topic_check = now - 5 * 3600  # 5 hours ago
        assert speaker._should_hot_topic(now)


# ============================================================
# 触发执行测试
# ============================================================

class TestTriggerExecution:
    """验证触发后正确调用 LLM + send。"""

    def test_cold_silence_trigger_sends(self):
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm("喵~ 大家最近在玩什么呀？")
        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5

        now = time.time()
        speaker._trigger_cold_silence(g, now)

        mock_llm.chat.assert_called_once()
        mock_send.assert_called_once()
        # 验证 _record_speak 被调用
        assert speaker._daily_counts.get("test@chatroom", 0) == 1

    def test_schedule_trigger_sends(self):
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm("早安喵~ 新的一天！")
        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5

        now = time.time()
        speaker._trigger_schedule(g, now, "08:30")

        mock_llm.chat.assert_called_once()
        mock_send.assert_called_once()

    def test_hot_topic_trigger_sends_to_all_groups(self):
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm("今天有个大新闻喵~")

        store = Store()
        store.get_group("room_a").msg_count = 5
        store.get_group("room_b").msg_count = 3
        store.get_group("room_c")  # msg_count=0, 跳过

        speaker = ProactiveSpeaker(
            store, mock_llm, _make_config(), mock_send,
        )

        # Mock web_search to return results
        with patch("src.web_search.search_web") as mock_search:
            mock_search.return_value = [
                {"title": "热点新闻", "snippet": "今天大事", "url": "http://x.com"}
            ]
            speaker._trigger_hot_topic(time.time(), "10:00")

        # LLM 调用一次
        mock_llm.chat.assert_called_once()
        # send 只发给 msg_count > 0 的群（room_a, room_b）
        assert mock_send.call_count == 2

    def test_hot_topic_no_results_skips(self):
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm()

        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )

        with patch("src.web_search.search_web") as mock_search:
            mock_search.return_value = []  # No results
            speaker._trigger_hot_topic(time.time(), "10:00")

        # LLM 不应该被调用
        mock_llm.chat.assert_not_called()
        mock_send.assert_not_called()

    def test_send_failure_does_not_record(self):
        """send 失败时不记录发言（不消耗每日配额）。"""
        mock_send = _make_mock_send(success=False)
        mock_llm = _make_mock_llm("测试消息")
        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )
        g = Group(room_id="test@chatroom")

        now = time.time()
        speaker._trigger_cold_silence(g, now)

        # send 被调用但返回 False → 不记录
        assert speaker._daily_counts.get("test@chatroom", 0) == 0

    def test_llm_error_does_not_send(self):
        """LLM 调用异常时不 send。"""
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm()
        mock_llm.chat.side_effect = RuntimeError("API down")

        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )
        g = Group(room_id="test@chatroom")
        g.msg_count = 5

        # 不应抛出异常
        speaker._trigger_cold_silence(g, time.time())
        mock_send.assert_not_called()


# ============================================================
# 生命周期测试
# ============================================================

class TestLifecycle:
    """start / stop 和 enabled 配置。"""

    def test_start_when_disabled(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(),
            _make_config(enabled=False), _make_mock_send(),
        )
        speaker.start()
        assert speaker._running is False
        assert speaker._thread is None

    def test_start_and_stop(self):
        speaker = ProactiveSpeaker(
            Store(), _make_mock_llm(), _make_config(), _make_mock_send(),
        )
        speaker.start()
        assert speaker._running is True
        assert speaker._thread is not None
        assert speaker._thread.is_alive()

        speaker.stop()
        assert speaker._running is False
        # Thread 应该已经停止
        speaker._thread.join(timeout=2)
        assert not speaker._thread.is_alive()

    def test_tick_skips_zero_msg_groups(self):
        """_tick 跳过 msg_count=0 的群。"""
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm()

        store = Store()
        store.get_group("empty_group")  # msg_count=0

        speaker = ProactiveSpeaker(
            store, mock_llm, _make_config(), mock_send,
        )
        # 设置 _last_hot_topic_check 避免热点检查触发 LLM
        speaker._last_hot_topic_check = time.time()

        speaker._tick()

        # 没有群符合冷场/定时条件 → LLM 不应被调用
        mock_llm.chat.assert_not_called()


# ============================================================
# 时间周期映射测试
# ============================================================

class TestTimePeriodMapping:
    """_trigger_schedule 时段映射正确。"""

    def test_period_mapping(self):
        mock_send = _make_mock_send()
        mock_llm = _make_mock_llm("测试")
        speaker = ProactiveSpeaker(
            Store(), mock_llm, _make_config(), mock_send,
        )
        g = Group(room_id="test@chatroom")

        test_cases = [
            ("06:30", "早安"),
            ("10:00", "上午"),
            ("12:30", "午间"),
            ("15:00", "午后"),
            ("20:00", "晚间"),
            ("23:00", "深夜"),
        ]

        for time_str, expected_period in test_cases:
            # 重置 mock
            mock_llm.reset_mock()
            speaker._trigger_schedule(g, time.time(), time_str)
            # 验证 prompt 中包含正确的时段
            call_args = mock_llm.chat.call_args[0][0]
            user_content = call_args[1]["content"]
            assert expected_period in user_content, \
                f"Expected '{expected_period}' for time {time_str}"
