"""
群聊 AI 机器人 — 入口 (Akasha-WeFlow 方案)
├─ WeFlow SSE 接收微信消息
├─ BotCore 过滤/路由/会话管理
├─ LLMClient DeepSeek 回复
└─ UIA 自动化发送消息

用法: python main.py
"""
import logging
import sys
import time
import threading

from src.config_loader import load_config
from src.weflow_client import WeFlowClient, WeFlowMessage
from src.bot_core import BotCore
from src.llm_client import LLMClient
from src.state import BotState
from src.web_panel import start_web, set_bot_state


def setup_logging():
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
    logger.info("配置: llm=%s/%s, bot=%s", config.llm.provider, config.llm.model, config.bot.name)

    # 2. 全局状态
    state = BotState()
    set_bot_state(state)

    # 3. 初始化模块
    llm = LLMClient(config)
    weflow = WeFlowClient(
        base_url="http://127.0.0.1:5031",
        access_token=config.weflow_token,
    )
    weflow.set_bot_identity(
        nicknames=[config.bot.name],
        wxid=getattr(config, 'bot_wxid', ''),
    )
    bot = BotCore(config, weflow)

    # 4. 消息回调
    def on_msg(msg: WeFlowMessage):
        logger.debug(
            "消息: session=%s, sender=%s, content=%s",
            msg.session_id, msg.sender_name, msg.content[:80],
        )

        # 命令处理
        cmd_result = bot.handle(msg)
        if cmd_result is not None:
            reply_text, roomid = cmd_result
            logger.info("命令回复: roomid=%s, reply=%s", roomid, reply_text[:50])
            weflow.send_text(reply_text, roomid, msg.sender_name)
            return

        # LLM 处理
        if msg.is_group and weflow.is_at_bot(msg):
            roomid = msg.roomid
            history = bot.get_history(roomid)
            logger.info("LLM: roomid=%s, rounds=%d", roomid, len(history)//2)

            reply = llm.chat(history)
            bot.add_reply(roomid, reply)

            weflow.send_text(reply, roomid, msg.sender_name)
            logger.info("回复: roomid=%s, text=%s", roomid, reply[:50])

    weflow.on_message(on_msg)

    # 5. 回调注册
    state.set_callbacks(
        restart_fn=lambda: None,  # SSE 自动重连，无需手动重启
        stop_fn=lambda: weflow.stop(),
    )

    # 6. 启动
    weflow.start_receiving()
    start_web(8766)
    state.running = True
    state.weflow_connected = True

    logger.info("=" * 50)
    logger.info("✅ 机器人已启动 (WeFlow + UIA 模式)")
    logger.info("   Web 面板: http://127.0.0.1:8766")
    logger.info("   确保 WeFlow 已启动并开启 API 服务 (端口 5031)")
    logger.info("   按 Ctrl+C 退出")
    logger.info("=" * 50)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到退出信号")
    finally:
        state.running = False
        weflow.stop()


if __name__ == "__main__":
    main()
