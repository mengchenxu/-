# 群聊 AI 机器人

微信群聊 AI 机器人，基于 **WeFlow + DeepSeek + UIA**，六阶段管道架构。

## 架构

```
main.py → Pipeline → Parse → Enrich → Prompt → LLM → Decode → Send
                          ↑                          ↑
                     Store (store.json)        Store.apply()
```

| 阶段 | 职责 |
|------|------|
| **Parse** | 解析 WeFlow 原始消息 → 提取发送者、@mentions、命令、去除分隔符 |
| **Enrich** | 上下文充实 → 名字解析（mention_name + aliases）、记忆检索、别名扫描 |
| **Prompt** | 四段式 prompt 组装：系统指令 + 群聊摘要 + 最近对话 + 当前消息 |
| **LLM** | DeepSeek API 调用 + tool use（search_web）+ fallback |
| **Decode** | 回复解码 → 提取内联 @mentions、/remember 指令、纠正信号 |
| **Send** | UIA 键盘模拟 → 内联 @mention 发送到微信 |

### 数据层

单文件 `data/store.json`，原子写入（temp → rename）：

```
Person   — 群成员（mention_name · aliases · facts · catchphrases）
Group    — 群（context · topic · memories · history）
ChatMsg  — 单条消息（role · content · sender_name · timestamp）
Fact     — 事实（key · value · source · confidence）
```

**名字模型**：mention_name（群昵称，定时刷新）为权威来源，旧名自动进入 aliases。名字解析绝不返回 wxid。

**置信度系统**：user_stated(0.9) > manual(0.8) > llm_extract(0.6) > auto_extract(0.4)。低置信度不能覆盖高置信度。纠正信号（"我不是xxx"）无视规则强制覆盖。

## 功能

- 🤖 **@ 触发对话**：被 @ 时回复，非 @ 消息记录到历史但不触发 LLM
- 🎭 **米线山人设**：串子大王，接梗快、损友调侃不攻击、偶尔阴阳
- 🗂️ **多群隔离**：每个群独立历史和上下文
- 🔍 **联网搜索**：遇到不懂的梗用 search_web 搜索后自然接住
- 📋 **命令系统**：`/help`、`/reset`、`/whois @某人`、`/remember @某人 key: value`
- 🔄 **启动加载**：拉取最近 20 条群消息到历史，保持上下文连贯
- ⏱️ **回复冷却**：可配置最小回复间隔，防刷屏
- 📝 **群聊摘要**：每 15 条消息自动更新摘要
- 🔄 **定时同步**：每 30 分钟刷新群成员昵称，变更自动入 aliases

## 环境要求

- **Windows**（UIA 键盘模拟依赖）
- Python >= 3.10
- 微信 Windows 客户端（已扫码登录）
- [WeFlow](https://github.com/nicko0o/WeFlow) 桌面端运行在 `http://127.0.0.1:5031`

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

编辑 `config/config.yaml`：

```yaml
llm:
  provider: "deepseek"
  api_key: "sk-your-key-here"
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"
  max_tokens: 2048
  temperature: 0.85

bot:
  name: "鼠鼠"                    # 机器人名字，用于 @ 检测
  system_prompt: |                 # 角色设定
    你是"米线山"，群里最会整活的串子大王...
  reply_cooldown_seconds: 3
  enable_search: true

weflow_token: "your-token"
```

### 3. 运行

```bash
python main.py
```

### 4. 使用

在群里 @机器人：

```
@鼠鼠 今天天气怎么样？
@鼠鼠 /help                  — 查看帮助
@鼠鼠 /whois @小明           — 查看小明的信息
@鼠鼠 /remember @小明 喜欢: 打篮球 — 手动教机器人记住
```

## 目录结构

```
├── main.py                  # 入口（≤50行）
├── requirements.txt
├── config/
│   └── config.yaml          # 配置文件
├── src/
│   ├── pipeline.py          # 主循环编排
│   ├── parse.py             # 消息解析
│   ├── enrich.py            # 上下文充实（名字解析+记忆检索）
│   ├── prompt.py            # 四段式 prompt 组装
│   ├── llm.py               # DeepSeek API + tool use + fallback
│   ├── decode.py            # 回复解码（@mentions + 指令 + 纠正信号）
│   ├── send.py              # UIA 内联 @mention 发送
│   ├── store.py             # 统一数据层（Person/Group/Memory/ChatMsg）
│   ├── config.py            # YAML 配置加载
│   ├── migrate.py           # 旧数据迁移（users.json → store.json）
│   └── weflow_client.py     # WeFlow REST 客户端
├── tests/
│   ├── test_store.py        # 28 tests
│   ├── test_parse.py        # 6 tests
│   ├── test_enrich.py       # 3 tests
│   ├── test_prompt.py       # 3 tests
│   └── test_decode.py       # 15 tests
├── data/
│   └── store.json           # 统一数据文件
├── logs/
└── docs/
    └── superpowers/
        ├── specs/           # 设计规格
        ├── plans/           # 实施计划
        └── issues/          # Issue 追踪
```

## 测试

```bash
python -m pytest tests/ -v   # 55 tests
```

## 风险提示

⚠️ UIA 键盘模拟可能受微信版本更新影响。建议使用小号，不发敏感内容。
