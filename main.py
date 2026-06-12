"""
群聊 AI 机器人 — WeFlow SSE 版
WeFlow SSE 收 → BotCore → DeepSeek → UIA 发

功能：
- 群聊上下文记忆（跨重启持久化）
- 用户识别与记忆（记住每个群成员的特征、偏好、历史）
- Web 控制面板
"""
import logging
import sys
import time

from src.config_loader import load_config
from src.weflow_client import WeFlowClient, WeFlowMessage
from src.bot_core import BotCore
from src.llm_client import LLMClient
from src.state import BotState
from src.user_memory import UserMemoryStore
from src.context_builder import build_llm_context, extract_facts_from_reply
from src.web_panel import start_web, set_bot_state


def setup_logging():
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG)
    logging.getLogger("comtypes").setLevel(logging.WARNING)

    from logging.handlers import TimedRotatingFileHandler
    fh = TimedRotatingFileHandler("logs/bot.log", when="midnight", backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(fh)


def main():
    setup_logging()
    logger = logging.getLogger("main")

    config = load_config()
    logger.info("Config: llm=%s/%s, bot=%s", config.llm.provider, config.llm.model, config.bot.name)

    # 初始化用户记忆（持久化到 data/users.json）
    user_memory = UserMemoryStore(data_dir="data")
    logger.info("User memory: %d users loaded", user_memory.user_count)

    state = BotState()
    set_bot_state(state)

    llm = LLMClient(config)
    client = WeFlowClient(access_token=config.weflow_token)
    client.set_bot_identity(nicknames=[config.bot.name], wxid="wxid_hgla5drf0k8119")
    bot = BotCore(config, client, user_memory=user_memory)

    def on_msg(msg: WeFlowMessage):
        logger.debug("Msg: room=%s, sender=%s, text=%s", msg.session_id, msg.sender_name, msg.content[:80])
        if not msg.is_group:
            return

        roomid = msg.roomid
        speaker_wxid = msg.sender_name

        # 先用 BotCore 处理（记录用户、检查命令等）
        result = bot.handle(msg)
        if result is not None:
            reply, _ = result
            logger.info("Cmd: %s -> %s", roomid, reply[:50])
            client.send_text(reply, roomid, msg.sender_name)
            return

        # 需要 LLM 处理的消息（@bot 且非命令）
        if client.is_at_bot(msg):
            session = bot.get_session(roomid)

            # ---- 构建带上下文的消息 ----
            enriched_content = build_llm_context(
                msg=msg,
                session=session,
                user_memory=user_memory,
                bot_nicknames=client.bot_nicknames,
            )

            # 替换 session 中最后一条 user 消息的内容为增强版
            # （bot.handle 已经添加了原始消息，我们替换它）
            if session.history:
                last_msg = session.history[-1]
                if last_msg.role == "user" and last_msg.sender_wxid == speaker_wxid:
                    last_msg.content = enriched_content

            logger.info("LLM: room=%s, user=%s, rounds=%d, users=%d",
                        roomid, msg.display_name, len(session.history) // 2,
                        len(session.active_users))

            # ---- 调用 LLM ----
            history_list = list(session.history)
            reply = llm.chat(history_list)

            # ---- 提取用户事实（/remember 指令） ----
            reply = extract_facts_from_reply(reply, speaker_wxid, user_memory)

            # ---- 记录回复到会话历史 ----
            bot.add_reply(roomid, reply)

            # ---- 发送 ----
            display = client.get_display_name(msg.sender_name)
            client.send_text(reply, roomid, display)
            logger.info("Reply: @%s -> %s", display, reply[:80])

    client.on_message(on_msg)
    client.start_receiving()
    start_web(8766)
    state.running = True

    logger.info("=" * 50)
    logger.info("Bot started (WeFlow SSE + DeepSeek + UIA)")
    logger.info("  Web:    http://127.0.0.1:8766")
    logger.info("  Memory: %d users loaded", user_memory.user_count)
    logger.info("  Ctrl+C to exit")
    logger.info("=" * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        state.running = False
        user_memory.save()
        logger.info("User memory saved: %d users", user_memory.user_count)
        client.stop()


if __name__ == "__main__":
    main()
