"""游戏会话系统测试 — Pipeline 集成 + GameSessionManager 单元测试"""
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from src.game_session import (
    GameSession,
    GameSessionManager,
    _EXIT_KEYWORDS,
    _RERUN_KEYWORDS,
)
from src.store import Store, ChatMsg
from src.parse import ParsedMsg
from src.decode import DecodedReply


# ============================================================
# 测试夹具
# ============================================================

ROOM_ID = "123@chatroom"


def _make_parsed(
    content: str = "",
    is_at_bot: bool = False,
    is_command: bool = False,
    command: str = "",
    command_args: str = "",
    room_id: str = ROOM_ID,
    sender_wxid: str = "wxid_test",
    sender_name: str = "测试用户",
) -> ParsedMsg:
    return ParsedMsg(
        room_id=room_id,
        sender_wxid=sender_wxid,
        sender_name=sender_name,
        content=content,
        raw_mentions=[],
        is_at_bot=is_at_bot,
        is_command=is_command,
        command=command,
        command_args=command_args,
    )


def _make_pipeline() -> MagicMock:
    """创建一个 mock Pipeline，保留 game_manager + store + weflow 的真实行为。"""
    from src.game_session import GameSessionManager
    from src.pipeline import Pipeline

    pipeline = MagicMock()
    pipeline.store = Store()
    pipeline.store.get_group(ROOM_ID)
    pipeline.config = MagicMock()
    pipeline.config.bot.name = "鼠鼠"
    pipeline.weflow = MagicMock()
    pipeline.weflow.get_display_name.return_value = "测试用户"
    pipeline.game_manager = GameSessionManager(timeout_minutes=5)

    # Wire up real Pipeline methods that we test
    pipeline._handle_dice = lambda parsed: Pipeline._handle_dice(pipeline, parsed)
    pipeline._handle_game_message = lambda parsed: Pipeline._handle_game_message(pipeline, parsed)
    pipeline._check_game_timeout = lambda room_id: Pipeline._check_game_timeout(pipeline, room_id)

    return pipeline


def _setup_game_mode(pipeline: MagicMock, room_id: str = ROOM_ID):
    """快捷方法：进入游戏模式。"""
    pipeline.game_manager.enter(room_id, "/骰子", "骰子")


# ============================================================
# GameSession 单元测试
# ============================================================

class TestGameSession:
    def test_create_session(self):
        now = time.time()
        session = GameSession(
            game_name="/骰子",
            display_name="骰子",
            started_at=now,
            last_input_at=now,
        )
        assert session.game_name == "/骰子"
        assert session.display_name == "骰子"
        assert session.started_at == now
        assert session.last_input_at == now

    def test_touch_updates_last_input(self):
        session = GameSession("/骰子", "骰子", time.time(), time.time() - 100)
        old = session.last_input_at
        session.touch()
        assert session.last_input_at > old

    def test_is_expired_true(self):
        session = GameSession("/骰子", "骰子", time.time(), time.time() - 600)
        assert session.is_expired(timeout_minutes=5) is True

    def test_is_expired_false(self):
        session = GameSession("/骰子", "骰子", time.time(), time.time())
        assert session.is_expired(timeout_minutes=5) is False

    def test_is_expired_at_boundary(self):
        """刚好 5 分钟时不算过期（使用 > 比较）。"""
        session = GameSession("/骰子", "骰子", time.time(), time.time() - 300)
        assert session.is_expired(timeout_minutes=5) is False


# ============================================================
# GameSessionManager 单元测试
# ============================================================

class TestGameSessionManager:
    def test_enter_creates_session(self):
        mgr = GameSessionManager()
        session = mgr.enter(ROOM_ID, "/骰子", "骰子")
        assert session.game_name == "/骰子"
        assert mgr.is_in_game(ROOM_ID) is True

    def test_enter_overwrites_existing(self):
        mgr = GameSessionManager()
        mgr.enter(ROOM_ID, "/骰子", "骰子")
        mgr.enter(ROOM_ID, "/猜拳", "猜拳")
        assert mgr.get(ROOM_ID).game_name == "/猜拳"

    def test_leave_returns_session(self):
        mgr = GameSessionManager()
        mgr.enter(ROOM_ID, "/骰子", "骰子")
        session = mgr.leave(ROOM_ID)
        assert session is not None
        assert session.game_name == "/骰子"
        assert mgr.is_in_game(ROOM_ID) is False

    def test_leave_nonexistent_returns_none(self):
        mgr = GameSessionManager()
        assert mgr.leave(ROOM_ID) is None

    def test_get_returns_session(self):
        mgr = GameSessionManager()
        session = mgr.enter(ROOM_ID, "/骰子", "骰子")
        assert mgr.get(ROOM_ID) is session

    def test_get_nonexistent_returns_none(self):
        mgr = GameSessionManager()
        assert mgr.get(ROOM_ID) is None

    def test_is_in_game(self):
        mgr = GameSessionManager()
        assert not mgr.is_in_game(ROOM_ID)
        mgr.enter(ROOM_ID, "/骰子", "骰子")
        assert mgr.is_in_game(ROOM_ID)

    def test_check_timeout_no_session(self):
        mgr = GameSessionManager()
        assert mgr.check_timeout(ROOM_ID) is None

    def test_check_timeout_active_session(self):
        mgr = GameSessionManager()
        mgr.enter(ROOM_ID, "/骰子", "骰子")
        assert mgr.check_timeout(ROOM_ID) is None  # 刚创建不过期

    def test_check_timeout_expired(self):
        mgr = GameSessionManager(timeout_minutes=5)
        mgr.enter(ROOM_ID, "/骰子", "骰子")
        # 手动回拨 last_input_at 来模拟超时
        mgr._sessions[ROOM_ID].last_input_at = time.time() - 600
        expired = mgr.check_timeout(ROOM_ID)
        assert expired is not None
        assert expired.game_name == "/骰子"
        assert mgr.is_in_game(ROOM_ID) is False  # 已清除

    def test_active_rooms(self):
        mgr = GameSessionManager()
        assert mgr.active_rooms == []
        mgr.enter("room_a", "/骰子", "骰子")
        mgr.enter("room_b", "/骰子", "骰子")
        assert set(mgr.active_rooms) == {"room_a", "room_b"}

    def test_is_exit_command(self):
        mgr = GameSessionManager()
        assert mgr.is_exit_command("不玩了")
        assert mgr.is_exit_command("退出")
        assert mgr.is_exit_command("算了")
        assert mgr.is_exit_command("我不玩了，去吃饭")
        assert mgr.is_exit_command("算了不玩了")  # 任意关键词命中即退出
        assert not mgr.is_exit_command("继续玩")
        assert not mgr.is_exit_command("不玩")  # "不玩"不在关键词列表中，防止"玩不玩"误触发

    def test_is_rerun_command(self):
        mgr = GameSessionManager()
        assert mgr.is_rerun_command("再来一次")
        assert mgr.is_rerun_command("再掷一次")
        assert mgr.is_rerun_command("再来一发")
        assert mgr.is_rerun_command("重来")
        assert mgr.is_rerun_command("再来一次吧")
        assert not mgr.is_rerun_command("你好")
        assert not mgr.is_rerun_command("再来")  # "再来"不在关键词列表中，太宽泛
        assert not mgr.is_rerun_command("again")  # 英文不在关键词列表中

    def test_make_exit_message_contains_game_name(self):
        mgr = GameSessionManager()
        msg = mgr.make_exit_message("骰子")
        assert "骰子" in msg
        assert "喵~" in msg
        assert "@" in msg


# ============================================================
# Pipeline 集成测试 — 游戏模式进入/退出
# ============================================================

class TestPipelineGameEnterExit:
    """测试 Pipeline.handle() 的游戏模式进入/退出全链路。"""

    def test_at_bot_dice_enters_game_mode(self):
        """@bot + /骰子 → 进入游戏模式 + 掷骰子。"""
        pipeline = _make_pipeline()

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline
            # 直接测试核心逻辑：进入 + 掷骰子
            pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True

            parsed = _make_parsed(
                content="/骰子", is_at_bot=True,
                is_command=True, command="/骰子",
            )
            reply = Pipeline._handle_dice(pipeline, parsed)
            assert "🎲" in reply
            assert "喵~" in reply

    def test_at_bot_dice_while_in_game_overwrites(self):
        """在游戏模式中 @bot + /骰子 → 覆盖当前游戏会话。"""
        pipeline = _make_pipeline()
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")

        # @bot 再次 /骰子
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        assert pipeline.game_manager.is_in_game(ROOM_ID) is True

    def test_game_mode_intercepts_non_at_messages(self):
        """游戏模式中非 @ 消息被拦截，不调 LLM（enrich 不应被调用）。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        with patch("src.pipeline.send", return_value=True):
            with patch("src.pipeline.enrich") as mock_enrich:
                # 模拟游戏模式路由：非 @ + 游戏中 → 走 _handle_game_message
                parsed = _make_parsed("无关消息", is_at_bot=False)
                assert pipeline.game_manager.is_in_game(parsed.room_id) is True

                # enrich 不应被调用（游戏模式拦截在 enrich 之前）
                mock_enrich.assert_not_called()

    def test_game_mode_rerun_dice(self):
        """游戏模式中"再来一次" → 重掷骰子（不 @bot）。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline
            parsed = _make_parsed("再来一次", is_at_bot=False)

            # 验证 rerun 关键词命中
            assert pipeline.game_manager.is_rerun_command(parsed.content) is True

            reply = Pipeline._handle_dice(pipeline, parsed)
            assert "🎲" in reply
            assert "喵~" in reply

    def test_game_mode_exit_by_keyword(self):
        """游戏模式中"不玩了" → 退出 + 猫娘公告。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        with patch("src.pipeline.send", return_value=True):
            parsed = _make_parsed("不玩了", is_at_bot=False)

            # 验证退出关键词命中
            assert pipeline.game_manager.is_exit_command(parsed.content) is True

            # 执行退出逻辑
            session = pipeline.game_manager.get(parsed.room_id)
            display_name = session.display_name
            pipeline.game_manager.leave(parsed.room_id)
            msg = pipeline.game_manager.make_exit_message(display_name)

            assert pipeline.game_manager.is_in_game(parsed.room_id) is False
            assert "骰子" in msg
            assert "喵~" in msg

    def test_game_mode_exit_by_keyword_退出发送公告(self):
        """手动退出时通过 send() 发送公告（不调 LLM）。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        with patch("src.pipeline.send", return_value=True) as mock_send:
            from src.pipeline import Pipeline
            parsed = _make_parsed("退出", is_at_bot=False)

            # 调用完整 _handle_game_message
            reply = Pipeline._handle_game_message(pipeline, parsed)
            assert reply is not None
            assert "骰子" in reply
            assert "喵~" in reply
            assert pipeline.game_manager.is_in_game(parsed.room_id) is False

    def test_game_mode_other_messages_touch_session(self):
        """游戏模式中其他消息被拦截但保持会话活跃（touch）。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        old_last_input = pipeline.game_manager.get(ROOM_ID).last_input_at
        time.sleep(0.01)  # 确保时间戳不同

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline
            parsed = _make_parsed("今天天气真好", is_at_bot=False)
            reply = Pipeline._handle_game_message(pipeline, parsed)
            assert reply is None  # 被拦截，不回复

            # 会话被 touch
            assert pipeline.game_manager.get(ROOM_ID).last_input_at > old_last_input
            # 仍在游戏中
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True

    def test_exit_keyword_with_compound_content(self):
        """包含退出关键词的消息也能触发退出。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline
            parsed = _make_parsed("算了不玩了，我走了", is_at_bot=False)
            reply = Pipeline._handle_game_message(pipeline, parsed)
            assert reply is not None
            assert pipeline.game_manager.is_in_game(ROOM_ID) is False

    def test_rerun_keyword_touch_and_reroll(self):
        """rerun 命令刷新会话并重掷。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        old_last_input = pipeline.game_manager.get(ROOM_ID).last_input_at
        time.sleep(0.01)

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline
            parsed = _make_parsed("再来一次", is_at_bot=False)
            reply = Pipeline._handle_game_message(pipeline, parsed)
            assert reply is not None
            assert "🎲" in reply
            assert pipeline.game_manager.get(ROOM_ID).last_input_at > old_last_input
            # 仍在游戏中
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True


# ============================================================
# Pipeline 集成测试 — 超时
# ============================================================

class TestPipelineGameTimeout:
    """测试 5 分钟超时自动退出。"""

    def test_timeout_auto_exit(self):
        """超时后 _check_game_timeout 自动退出。"""
        pipeline = _make_pipeline()
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        # 手动回拨 last_input_at 模拟超时
        pipeline.game_manager._sessions[ROOM_ID].last_input_at = time.time() - 600

        with patch("src.pipeline.send", return_value=True) as mock_send:
            from src.pipeline import Pipeline
            Pipeline._check_game_timeout(pipeline, ROOM_ID)
            assert pipeline.game_manager.is_in_game(ROOM_ID) is False
            # 应该发送了退出公告
            assert mock_send.called

    def test_timeout_message_contains_catgirl_style(self):
        """超时公告包含猫娘风格文本。"""
        pipeline = _make_pipeline()
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        pipeline.game_manager._sessions[ROOM_ID].last_input_at = time.time() - 600

        sent_messages = []

        def capture_send(reply, room_id, at_sender):
            sent_messages.append(reply.clean_text)
            return True

        with patch("src.pipeline.send", side_effect=capture_send):
            from src.pipeline import Pipeline
            Pipeline._check_game_timeout(pipeline, ROOM_ID)
            assert len(sent_messages) == 1
            assert "骰子" in sent_messages[0]
            assert "喵~" in sent_messages[0]

    def test_no_timeout_for_active_session(self):
        """活跃会话不触发超时。"""
        pipeline = _make_pipeline()
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")

        with patch("src.pipeline.send", return_value=True) as mock_send:
            from src.pipeline import Pipeline
            Pipeline._check_game_timeout(pipeline, ROOM_ID)
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True
            assert not mock_send.called

    def test_timeout_check_no_session_is_noop(self):
        """无活跃会话时超时检查是无操作。"""
        pipeline = _make_pipeline()

        with patch("src.pipeline.send", return_value=True) as mock_send:
            from src.pipeline import Pipeline
            Pipeline._check_game_timeout(pipeline, ROOM_ID)
            assert not mock_send.called


# ============================================================
# Pipeline 集成测试 — 正常模式恢复
# ============================================================

class TestPipelineNormalModeRecovery:
    """测试退出游戏后恢复正常 @ 触发模式。"""

    def test_after_exit_non_at_goes_to_enrich(self):
        """退出游戏后，非 @ 消息走正常 enrich 路径（返回 None）。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        # 退出
        pipeline.game_manager.leave(ROOM_ID)
        assert pipeline.game_manager.is_in_game(ROOM_ID) is False

        # 非 @ 消息 → 不在游戏模式 → 走 enrich → 返回 None
        parsed = _make_parsed("你好", is_at_bot=False)
        assert not parsed.is_at_bot
        assert not pipeline.game_manager.is_in_game(parsed.room_id)
        # enrich 会返回 None（因为不是 @bot）

    def test_after_exit_at_bot_works_normally(self):
        """退出游戏后，@bot 消息走正常管道。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)
        pipeline.game_manager.leave(ROOM_ID)

        # @bot 消息应该正常处理
        parsed = _make_parsed("@鼠鼠 你好", is_at_bot=True)
        assert parsed.is_at_bot is True
        assert pipeline.game_manager.is_in_game(parsed.room_id) is False

    def test_reenter_after_exit(self):
        """退出后立即可以重新进入游戏。"""
        pipeline = _make_pipeline()

        # 进入 → 退出 → 再进入
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        pipeline.game_manager.leave(ROOM_ID)
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        assert pipeline.game_manager.is_in_game(ROOM_ID) is True


# ============================================================
# Pipeline 集成测试 — @bot 在游戏模式中
# ============================================================

class TestAtBotInGameMode:
    """@bot 消息在游戏模式中正常处理（可 @bot 选其他游戏覆盖当前）。"""

    def test_at_bot_in_game_mode_not_intercepted(self):
        """@bot 消息在游戏模式中不被游戏处理器拦截。"""
        pipeline = _make_pipeline()
        _setup_game_mode(pipeline)

        parsed = _make_parsed("@鼠鼠 今天天气怎么样", is_at_bot=True)
        assert parsed.is_at_bot is True
        # @bot → 不走游戏模式路由（路由仅对 non-@ 生效）
        # 走 enrich → 正常管道

    def test_at_bot_switch_game_in_game_mode(self):
        """@bot 在游戏模式中可以用 /骰子 覆盖当前游戏。"""
        pipeline = _make_pipeline()
        pipeline.game_manager.enter(ROOM_ID, "/猜拳", "猜拳")

        # @bot 选 /骰子 → 覆盖
        pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
        assert pipeline.game_manager.get(ROOM_ID).game_name == "/骰子"


# ============================================================
# 游戏模式端到端全链路（mock send）
# ============================================================

class TestGameModeFullPipeline:
    """端到端测试：游戏模式全链路。"""

    def test_full_flow_enter_rerun_exit(self):
        """完整流程：进入 → 掷骰子 → 再来一次 → 退出。"""
        pipeline = _make_pipeline()

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline

            # Step 1: 进入游戏模式
            pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True

            # Step 2: 第一次掷骰子
            parsed_cmd = _make_parsed(
                content="/骰子", is_at_bot=True,
                is_command=True, command="/骰子",
            )
            reply1 = Pipeline._handle_dice(pipeline, parsed_cmd)
            assert "🎲" in reply1

            # Step 3: 再来一次（非 @）
            parsed_rerun = _make_parsed("再来一次", is_at_bot=False)
            reply2 = Pipeline._handle_game_message(pipeline, parsed_rerun)
            assert reply2 is not None
            assert "🎲" in reply2

            # Step 4: 不玩了（非 @）
            parsed_exit = _make_parsed("不玩了", is_at_bot=False)
            reply3 = Pipeline._handle_game_message(pipeline, parsed_exit)
            assert reply3 is not None
            assert "骰子" in reply3
            assert "喵~" in reply3
            assert pipeline.game_manager.is_in_game(ROOM_ID) is False

    def test_full_flow_with_timeout(self):
        """完整流程含超时退出。"""
        pipeline = _make_pipeline()

        with patch("src.pipeline.send", return_value=True):
            from src.pipeline import Pipeline

            # 进入
            pipeline.game_manager.enter(ROOM_ID, "/骰子", "骰子")
            assert pipeline.game_manager.is_in_game(ROOM_ID) is True

            # 模拟超时
            pipeline.game_manager._sessions[ROOM_ID].last_input_at = time.time() - 600

            # 超时检查
            Pipeline._check_game_timeout(pipeline, ROOM_ID)
            assert pipeline.game_manager.is_in_game(ROOM_ID) is False

            # 退出后正常
            parsed = _make_parsed("你好", is_at_bot=False)
            assert not pipeline.game_manager.is_in_game(parsed.room_id)
