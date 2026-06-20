# 主动发言系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 机器人能够主动在群里找话题、发起对话——冷场暖场、定时推送、热点分享。

**Architecture:** 新增 ProactiveSpeaker 模块负责判断触发条件 + LLM 生成话题文案；后台线程每分钟检查一次；启动时先查冷场时长再决定是否立即发言。

**Tech Stack:** Python 3.x, threading, deepseek-chat

## Global Constraints

- 新增文件放入 `src/`
- 所有 LLM 调用通过 `LLMClient` 统一管理
- 主动发言不带 @mention，发给整个群
- 不可在静音时段发言

## File Map

| 文件 | 职责 | 改动 |
|------|------|------|
| `src/proactive_speaker.py` | 触发判断 + 话题生成 + 频率控制 | 新建 |
| `config/config.yaml` | proactive 配置段 + system prompt 补充 | 修改 |
| `src/config_loader.py` | ProactiveConfig dataclass | 修改 |
| `main.py` | 初始化 ProactiveSpeaker + 后台线程 + 启动检测 | 修改 |

---

### Task 1: ProactiveSpeaker 模块

**Files:**
- Create: `src/proactive_speaker.py`

**Interfaces:**
- Produces: `ProactiveSpeaker` class
  - `ProactiveSpeaker(config, llm_client, weflow_client, group_memory, user_memory)`
  - `.check_and_speak(room_id: str, session, last_msg_time: float) -> bool` — 检查条件 + 发言
  - `.on_startup(room_id: str, session, last_msg_time: float)` — 启动时冷场检测
  - `.record_sent()` — 记录一次发言
  - `.is_quiet_hours() -> bool` — 是否在静音时段

- [ ] **Step 1: 创建 `src/proactive_speaker.py`**

```python
"""
主动发言系统 — 冷场暖场 / 定时推送 / 热点分享。
后台线程每分钟检查一次触发条件。
"""
import logging
import random
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class ProactiveSpeaker:
    """主动发言控制器"""

    def __init__(self, config, llm_client, weflow_client, group_memory, user_memory):
        llm = config.llm
        proactive = config.proactive

        self.enabled = proactive.enabled
        self.cold_silence_minutes = proactive.cold_silence_minutes
        self.schedule_times = proactive.schedule_times
        self.hot_topic_interval_hours = proactive.hot_topic_interval_hours
        self.max_per_day = proactive.max_per_day
        self.min_interval_minutes = proactive.min_interval_minutes
        self.quiet_hours = proactive.quiet_hours  # ["02:00", "06:00"]

        self.llm = llm_client
        self.weflow = weflow_client
        self.group_memory = group_memory
        self.user_memory = user_memory

        # 内部状态
        self._sent_today = 0
        self._last_sent_at: float = 0.0
        self._last_hot_check_at: float = 0.0
        self._day_reset_at: str = ""  # 日期，用于每日重置

    # ----------------------------------------------------------------
    # 公共方法
    # ----------------------------------------------------------------
    def check_and_speak(self, room_id: str, session, last_msg_time: float) -> bool:
        """
        检查所有触发条件，满足则发言。返回 True 表示发了言。
        在后台线程中每分钟调用一次。
        """
        if not self.enabled:
            return False

        # 每日重置
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._day_reset_at:
            self._sent_today = 0
            self._day_reset_at = today

        # 上限检查
        if self._sent_today >= self.max_per_day:
            return False

        # 静音时段
        if self.is_quiet_hours():
            return False

        # 最小间隔
        if self._last_sent_at > 0:
            elapsed_min = (time.time() - self._last_sent_at) / 60
            if elapsed_min < self.min_interval_minutes:
                return False

        # 判断触发原因
        reason = self._get_trigger_reason(room_id, last_msg_time)
        if not reason:
            return False

        # 生成话题并发送
        try:
            topic = self._generate_topic(room_id, reason, session)
            if topic:
                self.weflow.send_text(topic, room_id)  # 不 @ 任何人
                self.record_sent()
                logger.info("主动发言 [%s]: room=%s, topic=%s",
                            reason, room_id[:20], topic[:60])
                return True
        except Exception:
            logger.exception("主动发言失败: room=%s", room_id[:20])
        return False

    def on_startup(self, room_id: str, session, last_msg_time: float):
        """启动时检查冷场时长，如果超阈值则等待后发言。"""
        if not self.enabled or self.is_quiet_hours():
            return
        if self._sent_today >= self.max_per_day:
            return

        silence_min = (time.time() - last_msg_time) / 60 if last_msg_time > 0 else float('inf')
        if silence_min >= self.cold_silence_minutes:
            logger.info("启动冷场检测: room=%s, silence=%.0fmin, 等待90s后发言",
                        room_id[:20], silence_min)
            # 等待 90 秒让 WeFlow 连接稳定后发言
            time.sleep(90)
            try:
                session_obj = session
                topic = self._generate_topic(room_id, "cold_silence", session_obj)
                if topic:
                    self.weflow.send_text(topic, room_id)
                    self.record_sent()
                    logger.info("启动暖场: room=%s, topic=%s",
                                room_id[:20], topic[:60])
            except Exception:
                logger.exception("启动暖场失败: room=%s", room_id[:20])

    def record_sent(self):
        """记录一次发言，更新计数和时间。"""
        self._sent_today += 1
        self._last_sent_at = time.time()

    def is_quiet_hours(self) -> bool:
        """判断当前是否在静音时段。"""
        if not self.quiet_hours or len(self.quiet_hours) < 2:
            return False
        now = datetime.now().strftime("%H:%M")
        start = self.quiet_hours[0]   # e.g. "02:00"
        end = self.quiet_hours[1]     # e.g. "06:00"
        if start <= end:
            return start <= now < end
        else:
            # 跨午夜的情况，如 22:00-08:00
            return now >= start or now < end

    # ----------------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------------
    def _get_trigger_reason(self, room_id: str, last_msg_time: float) -> str | None:
        """
        判断触发原因。优先级：定时 > 冷场 > 热点。
        返回 "scheduled" | "cold_silence" | "hot_topic" | None
        """
        now = datetime.now()
        now_str = now.strftime("%H:%M")

        # 1. 定时推送（±2 分钟内）
        for t in self.schedule_times:
            h1, m1 = int(now_str[:2]), int(now_str[3:5])
            h2, m2 = int(t[:2]), int(t[3:5])
            diff = abs((h1 * 60 + m1) - (h2 * 60 + m2))
            if diff <= 2:
                # 该时段今天还没发过
                return "scheduled"

        # 2. 冷场检测
        if last_msg_time > 0:
            silence_min = (time.time() - last_msg_time) / 60
            if silence_min >= self.cold_silence_minutes:
                return "cold_silence"
        else:
            # 没有 last_msg_time 记录，当做冷场
            return "cold_silence"

        # 3. 热点检测
        if self._last_hot_check_at == 0:
            self._last_hot_check_at = time.time()
        hot_elapsed = (time.time() - self._last_hot_check_at) / 3600
        if hot_elapsed >= self.hot_topic_interval_hours:
            self._last_hot_check_at = time.time()
            return "hot_topic"

        return None

    def _generate_topic(self, room_id: str, reason: str, session) -> str:
        """LLM 生成话题文案。"""
        # 检索上下文
        topic_keywords = getattr(session, 'topic_keywords', []) or []
        memories = []
        if self.group_memory and topic_keywords:
            memories = self.group_memory.search(room_id, topic_keywords, limit=3)

        # 检索用户偏好
        active_users = getattr(session, 'active_users', set()) or set()
        user_ctx = ""
        if self.user_memory and active_users:
            profiles = []
            for wxid in list(active_users)[:5]:
                p = self.user_memory.get(wxid)
                if p and p.get_context_summary():
                    profiles.append(p.get_context_summary())
            if profiles:
                user_ctx = "群成员:\n" + "\n".join(profiles)

        # 群风格
        group_style = getattr(session, 'group_style', '') or ''

        # 热点搜索
        hot_content = ""
        if reason == "hot_topic":
            try:
                from src.web_search import search_web, search_format_for_llm
                results = search_web("今日热点新闻")
                if results:
                    hot_content = "热点新闻:\n" + search_format_for_llm(results[:3])
            except Exception:
                pass

        # 构建 prompt
        reason_text = {
            "cold_silence": "群里已经冷场很久了，抛个话题暖暖场",
            "scheduled": "到点了，发个日常闲聊/问候",
            "hot_topic": "分享一下最近的热点，引发讨论",
        }.get(reason, "自然地说点什么")

        prompt = f"""你是微信群里的"鼠鼠"。现在需要你主动说句话。

原因: {reason_text}

{hot_content}
群风格: {group_style}
群记忆:
{chr(10).join(f'  · {m.content}' for m in memories) if memories else '  暂无'}
{user_ctx}

请生成 1-2 句话，发给群里。要求：
- 自然不突兀，像真人聊天，不要说自己"我来活跃气氛"之类的话
- 保持群的说话风格
- 如果有群记忆中没聊完的话题，优先续那个
- 不要 @ 任何人，是群发
- 直接返回发言内容，不要前缀"""

        resp = self.llm.client.chat.completions.create(
            model=self.llm.model,
            messages=[
                {"role": "system", "content": "你是一个群聊成员，自然地发起话题。只返回要发的消息内容。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.8,  # 稍高温度，话题多样化
        )
        return resp.choices[0].message.content.strip()
```

- [ ] **Step 2: 验证**

```bash
cd D:/chatbot && python -c "from src.proactive_speaker import ProactiveSpeaker; print('Import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/proactive_speaker.py
git commit -m "feat: add proactive speaker module"
```

---

### Task 2: 配置更新

**Files:**
- Modify: `config/config.yaml`
- Modify: `src/config_loader.py`

**Interfaces:**
- Produces: `ProactiveConfig` dataclass, `config.proactive` 访问

- [ ] **Step 1: 在 config_loader.py 中添加 ProactiveConfig**

```python
@dataclass
class ProactiveConfig:
    enabled: bool = False
    cold_silence_minutes: int = 30
    schedule_times: list = field(default_factory=lambda: ["08:30", "12:30", "18:00", "22:00"])
    hot_topic_interval_hours: int = 4
    max_per_day: int = 10
    min_interval_minutes: int = 30
    quiet_hours: list = field(default_factory=lambda: ["02:00", "06:00"])
```

在 `AppConfig` 中添加：
```python
proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
```

在 `load_config()` 中添加：
```python
if "proactive" in data:
    config.proactive = ProactiveConfig(**data["proactive"])
```

- [ ] **Step 2: 在 config.yaml 中添加 proactive 配置段**

```yaml
# --- 主动发言 ---
proactive:
  enabled: true
  cold_silence_minutes: 30
  schedule_times: ["08:30", "12:30", "18:00", "22:00"]
  hot_topic_interval_hours: 4
  max_per_day: 10
  min_interval_minutes: 30
  quiet_hours: ["02:00", "06:00"]
```

- [ ] **Step 3: 在 system_prompt 追加主动发言段落**

在 `[硬约束]` 之前插入：
```yaml
    [主动发言]
    有时你会根据情况主动在群里说话（没人@你也可能开口）：
    - 冷场时抛个话题活跃气氛
    - 到点了发个日常问候
    - 看到有意思的热点分享一下
    主动发言也要保持你的风格——你是群里的一员，自然说话，别突兀也别废话。
```

- [ ] **Step 4: 验证**

```bash
cd D:/chatbot && python -c "from src.config_loader import load_config; c = load_config(); print('Proactive:', c.proactive.enabled, 'cold:', c.proactive.cold_silence_minutes); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add config/config.yaml src/config_loader.py
git commit -m "feat: add proactive speaker config and system prompt update"
```

---

### Task 3: Main 集成

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 在 main.py 中集成 ProactiveSpeaker**

```python
from src.proactive_speaker import ProactiveSpeaker

def main():
    ...
    # 主动发言系统
    speaker = ProactiveSpeaker(config, llm, client, group_memory, user_memory)
    logger.info("Proactive speaker: %s", "enabled" if config.proactive.enabled else "disabled")

    # 记录群最后一条消息时间（用于冷场检测）
    last_msg_times: dict[str, float] = {}

    def on_msg(msg: WeFlowMessage):
        ...
        # 更新最后消息时间
        last_msg_times[msg.roomid] = time.time()
        ...
        # 现有逻辑不变

    client.on_message(on_msg)
    client.start_receiving()

    # ---- 启动后台线程 ----
    def _proactive_loop():
        """每分钟检查一次主动发言条件。"""
        time.sleep(5)  # 启动后先等 5 秒
        while state.running:
            try:
                for room_id in list(bot._sessions.keys()):
                    session = bot.get_session(room_id)
                    last_time = last_msg_times.get(room_id, 0.0)
                    speaker.check_and_speak(room_id, session, last_time)
            except Exception:
                logger.exception("proactive loop error")
            time.sleep(60)

    import threading
    threading.Thread(target=_proactive_loop, daemon=True, name="proactive").start()
    logger.info("Proactive loop started")

    # ---- 启动暖场 ----
    # 对每个已知群做启动冷场检测
    for room_id in list(bot._sessions.keys()):
        session = bot.get_session(room_id)
        last_time = last_msg_times.get(room_id, 0.0)
        # 在另一个线程中延时执行，不阻塞启动
        def _delayed_startup(rid=room_id, sess=session, lt=last_time):
            time.sleep(90)
            speaker.on_startup(rid, sess, lt)
        threading.Thread(target=_delayed_startup, daemon=True).start()

    ...
```

- [ ] **Step 2: 验证**

```bash
cd D:/chatbot && python -c "from main import main; print('Import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: integrate proactive speaker into main loop"
```

---

## 验证方案

1. **启动测试**：
```bash
cd D:/chatbot && python main.py
```
预期日志：`Proactive speaker: enabled` + `Proactive loop started`

2. **冷场测试**：等群里 30 分钟没人说话，日志出现 `主动发言 [cold_silence]`

3. **定时测试**：在配置的时段（如 12:30 ± 2 分钟），日志出现 `主动发言 [scheduled]`

4. **防刷屏测试**：连续触发时，`min_interval_minutes` 阻止第二次发言

5. **静音时段**：凌晨 2-6 点不发言
