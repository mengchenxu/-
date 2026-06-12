# 群聊 AI 机器人（基于 WeChatFerry + WeFlow）

微信群聊 AI 对话机器人，支持 **群上下文记忆** 和 **用户识别记忆**。

## 功能

- 🤖 **AI 对话**：@机器人 即可进行多轮对话，上下文连贯
- 🧠 **群上下文记忆**：记住群聊中讨论过的话题，跨重启持久化
- 👤 **用户识别记忆**：识别并记住每个群成员的特征、偏好、说过的话
- 🗂️ **多群隔离**：每个群的对话历史独立，互不干扰
- 📋 **命令系统**：`/help`、`/reset`、`/status`、`/whois`、`/memory`、`/remember`
- 🛡️ **群过滤**：白名单/黑名单控制响应的群
- 🔄 **Watchdog 守护**：崩溃自动重启
- 🌐 **Web 控制面板**：http://127.0.0.1:8766

## 环境要求

- **Windows**
- Python >= 3.10
- 微信 Windows 客户端

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

编辑 `config/config.yaml`，填入你的 LLM API Key：

```yaml
llm:
  provider: "deepseek"
  api_key: "sk-your-key-here"
  model: "deepseek-chat"

bot:
  name: "鼠鼠"                 # 机器人名字，用于 @ 检测
  system_prompt: "你是一个..."   # 角色设定
```

### 3. 运行

```bash
python main.py
```

### 4. 使用

在群里 **@机器人** 然后发送问题：

```
@鼠鼠 今天天气怎么样？
@鼠鼠 /help          — 查看帮助
@鼠鼠 /whois @小明    — 查看小明的信息
@鼠鼠 /memory        — 查看群聊记忆
@鼠鼠 /remember @小明 喜欢: 打篮球  — 手动教机器人记住
```

### 用户记忆系统

机器人会自动：
1. **识别群成员** — 通过微信 ID 识别每个人
2. **追踪显示名** — 即使你改昵称，机器人也能追踪
3. **学习特征** — 当你说"我叫小明，喜欢打篮球"，机器人会记住
4. **持久化存储** — 所有记忆保存在 `data/users.json`，重启不丢失

LLM 也可以在回复中自动使用 `/remember @名字 事实: 值` 指令来记住新信息。

## 生产部署（Windows VPS）

### 使用 nssm 注册 Windows Service

```cmd
nssm install WeChatBot
# Application: python 的完整路径
# Startup directory: 本项目根目录
# Arguments: watchdog.py
nssm start WeChatBot
```

## 目录结构

```
├── main.py              # 入口
├── watchdog.py          # 守护进程（生产用）
├── sender_daemon.py     # 消息发送守护进程
├── requirements.txt     # Python 依赖
├── config/
│   └── config.yaml      # 配置文件
├── src/
│   ├── bot_core.py       # 消息路由 & 会话管理
│   ├── llm_client.py     # LLM API 调用
│   ├── user_memory.py    # 用户记忆系统
│   ├── context_builder.py # 上下文构建器
│   ├── weflow_client.py  # WeFlow API 客户端
│   ├── config_loader.py  # 配置加载
│   ├── state.py          # 全局状态
│   └── web_panel.py      # Web 控制面板
├── data/
│   └── users.json        # 用户记忆数据（自动生成）
└── logs/
    └── bot.log           # 运行日志
```

## 风险提示

⚠️ WeChatFerry 通过注入 DLL 方式 Hook 微信客户端，**违反微信用户协议**，存在封号风险。请使用小号，不要发敏感内容。
