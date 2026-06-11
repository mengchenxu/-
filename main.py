"""
群聊 AI 机器人 — 入口（WeFlow + UIA 版）
用法: python main.py
"""
import logging
import sys
import time

from src.config_loader import load_config
from src.weflow_client import WeFlowClient, WeFlowMessage
from src.bot_core import BotCore
from src.llm_client import LLMClient


def setup_logging():
    """配置日志：控制台 + 文件（按天轮转）。"""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG)

    from logging.handlers import TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        "logs/bot.log", when="midnight", backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def main():
    setup_logging()
    logger = logging.getLogger("main")

    # 1. 加载配置
    config = load_config()
    logger.info("配置加载完成: llm=%s/%s, bot=%s", config.llm.provider, config.llm.model, config.bot.name)

    # 2. 初始化各模块
    llm = LLMClient(config)
    weflow = WeFlowClient(config)
    bot = BotCore(config, weflow)

    # 3. 注册消息回调
    def on_msg(msg: WeFlowMessage):
        logger.debug(
            "消息: session=%s, sender=%s, content=%s",
            msg.session_id, msg.sender_name, msg.content[:80],
        )

        # BotCore 处理：过滤 + 命令
        cmd_result = bot.handle(msg)
        if cmd_result is not None:
            reply_text, roomid = cmd_result
            logger.info("命令回复: roomid=%s, reply=%s", roomid, reply_text[:50])
            weflow.send_text(reply_text, roomid, msg.sender_name)
            return

        # 需要 LLM 处理的消息
        if msg.is_group and bot._is_at_bot(msg):
            roomid = msg.roomid
            history = bot.get_history(roomid)
            logger.info("LLM 请求: roomid=%s, rounds=%d", roomid, len(history) // 2)

            reply = llm.chat(history)
            bot.add_reply(roomid, reply)

            success = weflow.send_text(reply, roomid, msg.sender_name)
            if success:
                logger.info("回复成功: roomid=%s, reply=%s", roomid, reply[:50])
            else:
                logger.warning("回复失败: roomid=%s", roomid)

    weflow.on_message(on_msg)
    weflow.start_receiving()

    logger.info("✅ 机器人已启动（WeFlow + UIA 模式）")
    logger.info("   确保已启动 WeFlow 并开启 API 服务（端口 5031）")
    logger.info("   按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        weflow.stop()


if __name__ == "__main__":
    main()
