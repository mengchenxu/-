# 群聊 AI 机器人（WeFlow + DeepSeek + UIA）

微信群聊 AI 机器人，支持 **三层记忆体系**、**联网热梗理解**、**群风格学习**。

## 功能

### 核心对话
- 🤖 **AI 对话**：@机器人 即可多轮对话，上下文连贯
- 🎭 **可定制人格**：修改 `config.yaml` 即可切换风格（支持孙吧/温柔/毒舌等）
- 🗂️ **多群隔离**：每个群独立会话历史，互不干扰
- 🔍 **联网搜索**：遇到不懂的网络梗自动搜索再回复，自然接梗
- 📋 **命令系统**：`/help`、`/reset`、`/status`、`/whois`、`/memory`、`/remember`

### 三层记忆体系
| 层级 | 作用 | 存储 |
|------|------|------|
| 🧠 工作记忆 | 当前对话的话题追踪、最近 20 条消息 | 内存 |
| 📖 情景记忆 | 跨会话值得记住的事件/决定/趣事 | `data/group_memories.json` |
| 👤 语义记忆 | 用户特征、偏好、关系、说话风格 | `data/users.json` |

### 风格学习系统
- 👀 **观察所有群消息**：偷偷看群里的真实聊天，学习说话方式
- 📊 **实时统计**：词频、表情偏好、句式特征
- 🤖 **LLM 定期分析**：每 30 条消息自动提取群风格 + 核心成员风格
- 🎯 **风格注入**：回复时参考群风格上下文，越来越像真人

### 其他
- 🛡️ **群过滤**：白名单/黑名单控制响应的群
- 🌐 **Web 控制面板**：`http://127.0.0.1:8766`

## 环境要求

- **Windows**
- Python >= 3.10
- 微信 Windows 客户端
- WeFlow API 服务（`http://127.0.0.1:5031`）

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
  max_tokens: 1024
  temperature: 0.7

bot:
  name: "鼠鼠"              # 机器人名字，用于 @ 检测
  system_prompt: |           # 角色设定（五层结构：人格/记忆/交互/工具/约束）
    你是微信群里的 AI 助手...
  reply_cooldown_seconds: 3  # 回复冷却（防刷屏）
  enable_search: true        # 是否启用联网搜索

groups:
  whitelist: []              # 白名单（空=所有群）
  # blacklist: ["群名"]      # 或黑名单

session:
  max_history_rounds: 15      # 最多保留轮数
  context_summary_interval: 15

weflow_token: "your-token"   # WeFlow API token
```

### 3. 运行

```bash
python main.py
```

### 4. 使用

在群里 @机器人：

```
@鼠鼠 今天天气怎么样？
@鼠鼠 /help              — 查看帮助
@鼠鼠 /whois @小明        — 查看小明的信息
@鼠鼠 /memory            — 查看群聊记忆
@鼠鼠 /remember @小明 喜欢: 打篮球 — 手动教机器人记住
```

机器人会自动：
- 记住每个群成员的特征和偏好
- 联想之前聊过的相关内容
- 学习群里的说话风格（不用任何操作，自动）
- 遇到不懂的网络梗自动搜索后接住

## 目录结构

```
├── main.py                # 入口
├── requirements.txt       # Python 依赖
├── config/
│   └── config.yaml        # 配置文件（不提交git）
├── src/
│   ├── bot_core.py         # 消息路由 & 会话管理
│   ├── llm_client.py       # LLM API + Tool Use + 风格分析
│   ├── context_builder.py  # 上下文组装（三层记忆检索）
│   ├── group_memory.py     # 群情景记忆存储
│   ├── user_memory.py      # 用户记忆系统（特征+关系+风格）
│   ├── style_observer.py   # 风格观察器（群消息监听+统计）
│   ├── web_search.py       # 联网搜索（DuckDuckGo）
│   ├── weflow_client.py    # WeFlow API 客户端（REST轮询）
│   ├── uia_sender.py       # UIA 键盘模拟发送
│   ├── uia_receiver.py     # UIA 消息接收
│   ├── config_loader.py    # 配置加载
│   ├── state.py            # 全局状态
│   └── web_panel.py        # Web 控制面板
├── data/                   # 持久化数据（不提交git）
│   ├── users.json          # 用户档案
│   └── group_memories.json # 群情景记忆
├── logs/                   # 运行日志（不提交git）
└── docs/
    └── superpowers/
        ├── specs/          # 设计文档
        └── plans/          # 实施计划
```

## 风险提示

⚠️ UIA 键盘模拟方式可能受微信版本更新影响。建议使用小号，不要发敏感内容。
