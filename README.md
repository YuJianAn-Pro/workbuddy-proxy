# WorkBuddy AI Proxy

将 **WorkBuddy AI 国际版**的 API 反代为 OpenAI 兼容格式，供其他 AI Agent（Claude Code、Cursor、Codex、OpenCode 等）调用。

不需要打开 WorkBuddy 软件，直接调用云端 API，JWT Token 认证。

## 功能特性

- ✅ **OpenAI Chat Completions** 兼容（`/v1/chat/completions`）
- ✅ **OpenAI Responses API** 兼容（`/v1/responses`）
- ✅ 流式 / 非流式均支持
- ✅ 19+ 模型（GPT-6 系列、Hy3/Hy4、DeepSeek、Step-5 等）
- ✅ 自动添加 System Prompt（WorkBuddy 要求）
- ✅ 自动转换 Tools 格式（Responses ↔ Chat Completions）
- ✅ 单文件 EXE，无需安装 Python
- ✅ 一键部署脚本，支持开机自启
- ✅ 零依赖（仅用 Python 标准库）

## 快速开始

### 方式一：下载 EXE（推荐）

1. 从 [Releases](https://github.com/yourname/workbuddy-proxy/releases) 下载最新的 `workbuddy-proxy.exe`
2. 将 JWT Token 保存为 `token_live.txt`，放在 EXE 同目录
3. 双击运行，或命令行指定端口：

```bash
workbuddy-proxy.exe --port 8899
```

### 方式二：Python 运行

```bash
# 克隆项目
git clone https://github.com/yourname/workbuddy-proxy.git
cd workbuddy-proxy

# 将 JWT Token 保存为 token_live.txt

# 运行
python workbuddy_proxy.py --port 8899
```

### 方式三：一键部署（交互式）

```bash
python install.py
```

按提示配置端口、安装目录、开机自启，全自动完成部署。

## 获取 JWT Token

WorkBuddy AI 的 JWT Token 存储在桌面应用的认证文件中（加密），需要通过以下方式获取：

1. **从运行中的 WorkBuddy 进程内存提取**（推荐）
2. **通过浏览器 OAuth 登录**（参考 `@magpie-community/opencode-workbuddy-auth`）
3. **从 auth info 文件解密**（WorkBuddy 5.6+ 加密存储）

获取到 Token 后，保存为 `token_live.txt` 放在程序同目录即可。

## 配置

### 命令行参数

```bash
python workbuddy_proxy.py \
  --port 8899 \
  --jwt <JWT_TOKEN> \
  --user-id <用户UID> \
  --system-prompt "You are a helpful assistant."
```

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `WB_PROXY_PORT` | 监听端口 | 8080 |
| `WB_JWT_TOKEN` | JWT Token | 从 token_live.txt 读取 |
| `WB_USER_ID` | 用户 UID | 自动检测 |
| `WB_SYSTEM_PROMPT` | 默认 System Prompt | You are a helpful... |
| `WB_CLOUD_URL` | 上游 API | https://www.workbuddy.ai/v2/chat/completions |

## API 端点

| 端点 | 说明 |
|---|---|
| `GET /health` | 健康检查 |
| `GET /v1/models` | 模型列表 |
| `POST /v1/chat/completions` | Chat Completions（推荐） |
| `POST /v1/responses` | Responses API |

## 支持的模型

```
auto, hy4-preview, hy3, step-5-preview, deepseek-v4.1-flash,
gpt-6-sol, gpt-6-luna, gpt-5.6-terra, gpt-5.6-luna,
gpt-5.5, gpt-5.4, gpt-5.3-codex,
gemini-3.1-pro, gemini-3.5-flash,
glm-5.3, glm-5.2, kimi-k3, kimi-k2.6, minimax-m3
```

常见 OpenAI 模型名自动映射：
- `gpt-4o` / `gpt-4` / `gpt-3.5-turbo` → `gpt-5.6-luna`
- `claude-3-5-sonnet` → `gpt-5.6-luna`

## 在其他 Agent 中配置

### Claude Code / Cursor

```
Base URL: http://127.0.0.1:8899/v1
API Key: 任意值（如 sk-xxx）
模型: gpt-5.6-luna
```

### Codex（通过 CC Switch）

```
上游格式: Chat Completions（推荐）
Base URL: http://127.0.0.1:8899/v1
API Key: 任意值
```

> 注意：Responses（原生）格式对大请求（多轮对话+大量工具）可能有兼容问题，建议使用 Chat Completions 格式。

### OpenCode

在 `config.json` 中添加：

```json
{
  "providers": {
    "workbuddy-proxy": {
      "baseURL": "http://127.0.0.1:8899/v1",
      "apiKey": "sk-xxx",
      "models": ["gpt-5.6-luna", "gpt-6-sol", "deepseek-v4.1-flash"]
    }
  }
}
```

## 测试

```bash
# 健康检查
curl http://127.0.0.1:8899/health

# 模型列表
curl http://127.0.0.1:8899/v1/models

# 聊天补全
curl http://127.0.0.1:8899/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.6-luna","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

## 开机自启

### Windows

1. 运行 `python install.py`，选择设置开机自启
2. 或手动将 `start_hidden.vbs` 的快捷方式放入启动文件夹：
   `Win+R` → `shell:startup` → 放入快捷方式

## 构建 EXE

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
build.bat

# 或手动
pyinstaller --onefile --name workbuddy-proxy --console workbuddy_proxy.py
```

打包后的 EXE 在 `dist/workbuddy-proxy.exe`。

## 技术细节

- **上游 API**: WorkBuddy AI 国际版 `https://www.workbuddy.ai/v2/chat/completions`
- **认证**: JWT Bearer Token
- **关键 Header**: `X-Conversation-ID`、`X-Agent-Type: main`、`X-Product: SaaS`、`X-IDE-Type: WorkBuddy` 等
- **System Prompt**: WorkBuddy 要求第一条消息必须是 system，自动添加
- **流式**: 上游仅支持流式，非流式自动转流式再聚合
- **参考项目**: [`@magpie-community/opencode-workbuddy-auth`](https://www.npmjs.com/package/@magpie-community/opencode-workbuddy-auth)

## 常见问题

**Q: 需要打开 WorkBuddy 软件吗？**
A: 不需要。反代直接调用云端 API，只要 JWT Token 有效即可。

**Q: JWT Token 有效期多久？**
A: Keycloak 签发的 Token 通常有效期较长（1-2 年），过期后需要重新获取。

**Q: 支持国内版 CodeBuddy 吗？**
A: 目前仅支持国际版（workbuddy.ai）。国内版（copilot.tencent.com）的 API 端点和认证方式不同。

**Q: 为什么 Responses API 大请求报错？**
A: WorkBuddy 的渠道验证对复杂请求（多轮对话+大量工具）较严格。建议使用 Chat Completions 格式，兼容性更好。

## 许可证

MIT License
