"""
群聊 AI 机器人 — WeFlow SSE 版
三层记忆体系：工作记忆 + 情景记忆 + 语义记忆
支持 tool use 联网搜索热梗
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
from src.group_memory import GroupMemoryStore
from src.context_builder import (
    build_llm_context,
    extract_facts_from_reply,
    extract_context_from_reply,
    auto_extract_facts,
)
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
    logger.info("Config: llm=%s/%s, bot=%s, search=%s",
                config.llm.provider, config.llm.model,
                config.bot.name, getattr(config.bot, 'enable_search', True))

    # 用户记忆（语义记忆）
    user_memory = UserMemoryStore(data_dir="data")
    logger.info("User memory: %d users loaded", user_memory.user_count)

    # 群情景记忆（新增）
    group_memory = GroupMemoryStore(data_dir="data")
    logger.info("Group memory: %d memories loaded", group_memory.memory_count)

    state = BotState()
    set_bot_state(state)

    llm = LLMClient(config)
    client = WeFlowClient(access_token=config.weflow_token)
    client.set_bot_identity(nicknames=[config.bot.name], wxid="wxid_hgla5drf0k8119")
    bot = BotCore(config, client, user_memory=user_memory, data_dir="data")

    def on_msg(msg: WeFlowMessage):
        logger.debug("Msg: room=%s, sender=%s, text=%s",
                     msg.session_id, msg.sender_name, msg.content[:80])
        if not msg.is_group:
            return

        roomid = msg.roomid
        speaker_wxid = msg.sender_name

        # 先用 BotCore 处理（记录用户、检查命令、冷却、过滤等）
        result = bot.handle(msg)
        if result is not None:
            reply, _ = result
            logger.info("Cmd: %s -> %s", roomid, reply[:50])
            client.send_text(reply, roomid, msg.sender_name)
            return

        # 需要 LLM 处理的消息（@bot 且非命令）
        if client.is_at_bot(msg):
            session = bot.get_session(roomid)

            # ---- 构建带完整上下文的消息 ----
            enriched_content = build_llm_context(
                msg=msg,
                session=session,
                user_memory=user_memory,
                group_memory=group_memory,
                bot_nicknames=client.bot_nicknames,
            )

            # 替换 session 中最后一条 user 消息的内容为增强版
            if session.history:
                last_msg = session.history[-1]
                if last_msg.role == "user" and last_msg.sender_wxid == speaker_wxid:
                    last_msg.content = enriched_content

            logger.info("LLM: room=%s, user=%s, rounds=%d, mem=%d, topic=%s",
                        roomid, msg.display_name, len(session.history) // 2,
                        group_memory.memory_count if group_memory else 0,
                        (session.topic_summary or "")[:30])

            # ---- 调用 LLM（含 tool use 搜索） ----
            history_list = list(session.history)
            reply = llm.chat(history_list)

            # ---- 自动提取用户事实 ----
            auto_extract_facts(reply, speaker_wxid, msg.content, user_memory)

            # ---- 提取 /remember 指令 ----
            reply = extract_facts_from_reply(reply, speaker_wxid, user_memory)

            # ---- 提取 /context 指令 ----
            reply, context_update = extract_context_from_reply(reply)
            if context_update:
                bot.update_group_context(roomid, context_update)

            # ---- 记录回复到会话历史 ----
            bot.add_reply(roomid, reply)

            # ---- 发送 ----
            display = client.get_display_name(msg.sender_name)
            client.send_text(reply, roomid, display)
            logger.info("Reply: @%s -> %s", display, reply[:80])

            # ---- 定期更新话题摘要（工作记忆） ----
            if bot.should_update_topic(roomid):
                logger.info("触发话题摘要更新: room=%s", roomid[:20])
                try:
                    recent = list(session.history)
                    new_summary, new_keywords = llm.summarize_topic(
                        recent, session.topic_summary
                    )
                    if new_summary:
                        session.topic_summary = new_summary
                        session.topic_keywords = new_keywords
                        logger.info("话题摘要: %s | 关键词: %s",
                                    new_summary[:60], new_keywords)
                except Exception:
                    logger.exception("话题摘要失败: room=%s", roomid[:20])
                bot.reset_summary_counter(roomid)

            # ---- 定期提取情景记忆 ----
            if bot.should_extract_memory(roomid):
                logger.info("触发情景记忆提取: room=%s, msgs=%d",
                            roomid[:20], session.message_count)
                try:
                    recent = list(session.history)
                    new_mems = group_memory.consolidate(roomid, recent, llm)
                    if new_mems:
                        logger.info("新情景记忆: %d 条", len(new_mems))
                except Exception:
                    logger.exception("情景记忆提取失败: room=%s", roomid[:20])
                bot.reset_memory_counter(roomid)

            # ---- 定期更新群背景 ----
            if bot.should_summarize_context(roomid):
                logger.info("触发群上下文摘要: room=%s, msgs=%d",
                            roomid[:20], session.message_count)
                try:
                    summary = llm.summarize_context(
                        history=list(session.history),
                        existing_context=session.group_context,
                    )
                    if summary:
                        bot.update_group_context(roomid, summary)
                except Exception:
                    logger.exception("群上下文摘要失败: room=%s", roomid[:20])

    client.on_message(on_msg)
    client.start_receiving()
    start_web(8766)
    state.running = True

    logger.info("=" * 50)
    logger.info("Bot started (WeFlow + DeepSeek + 3-tier Memory + Search)")
    logger.info("  Web:    http://127.0.0.1:8766")
    logger.info("  Memory: %d users, %d group memories",
                user_memory.user_count, group_memory.memory_count)
    logger.info("  Search: %s", "enabled" if getattr(config.bot, 'enable_search', True) else "disabled")
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
        group_memory.save()
        logger.info("Memory saved: %d users, %d group memories",
                    user_memory.user_count, group_memory.memory_count)
        client.stop()


if __name__ == "__main__":
    main()
