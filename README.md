<div align="center">

# CogTutor：终身个性化辅导

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/cognisphere-space/CogTutor?style=flat-square&color=brightgreen)](https://github.com/cognisphere-space/CogTutor/releases)

[功能特性](#-功能特性) · [快速开始](#-快速开始) · [功能导览](#-功能导览) · [CLI](#%EF%B8%8F-cli--智能体原生接口) · [扩展](#-技能与扩展) · [社区](#-社区)

</div>

---

> **Fork 说明。** CogTutor 源自 [DeepTutor](https://github.com/HKUDS/DeepTutor)（香港大学 HKUDS 团队）的 fork，此后已独立演进。遵循 Apache License 2.0——版权声明见 [`LICENSE`](LICENSE)——为独立项目，与原 DeepTutor 维护方无隶属或背书关系。

> 🤝 **欢迎贡献。** 分支策略、编码规范与上手方式见 [贡献指南](CONTRIBUTING.md)。

## ✨ 功能特性

> **功能归属：** 下文「功能特性 / 功能导览 / CLI」所描述的能力与界面，**主体继承自上游 DeepTutor**；本仓库在其上做适配、加固与扩展。

当前这套软件（继承上游并经本 fork 修改后）是智能体原生学习工作区：辅导、解题、出题、研究、可视化与掌握度练习在同一可扩展系统中连通。下列条目描述**软件现状**，能力主体来自 DeepTutor。

- **统一运行时** — Chat、Quiz、Research、Visualize、Solve、Mastery Path 共用同一智能体循环；切换目标而非引擎，上下文随学习者迁移。
- **连通的学习上下文** — 知识库、书籍、Co-Writer 草稿、笔记本、题库、人设与 Memory 跨流程可用，而非孤立工具。
- **子智能体与 Partners** — 任意回合可咨询本机 Claude Code、Codex 或 Partner（也可导入历史对话）；持久 IM 伙伴共用同一大脑。
- **多引擎知识库** — 版本化 RAG：LlamaIndex、PageIndex、GraphRAG、LightRAG 或链接的 Obsidian 库，文档解析可插拔。
- **可扩展工具与技能** — 内置工具、MCP 服务、图/视/音生成模型，以及开放 Agent-Skills 格式的社区技能。
- **可审计记忆** — L1 轨迹、L2 面摘要、L3 综合使个性化可见可编辑；Memory Graph 将每条结论追溯到证据。

---

## 🚀 快速开始

三种安装路径共用同一工作区布局：设置位于启动目录下的 `data/user/settings/`（或 `DEEPTUTOR_HOME` / `deeptutor start --home`）。完整应用推荐：**选定工作区 → 安装 → `deeptutor init` → `deeptutor start`**。

> CLI 二进制当前仍为 `deeptutor`（继承上游包结构），下文命令沿用该名称。

<details>
<summary><b>方式 1 — 源码安装</b> · 基于 checkout 开发，本 fork 推荐</summary>

需 **Python 3.11+** 与 **Node.js 22 LTS**（与 CI / Docker 一致）。

```bash
git clone https://github.com/cognisphere-space/CogTutor.git
cd CogTutor

# 创建 venv（macOS/Linux）。Windows PowerShell：
#   py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip

# 安装后端 + 前端依赖
python -m pip install -e .
( cd web && npm ci --legacy-peer-deps )

deeptutor init
deeptutor start
```

`deeptutor init` 会询问：后端端口（默认 `8001`）、前端端口（默认 `3782`）、LLM 提供商 / Base URL / API Key / 模型，以及可选的 Embedding 提供商（知识库 / RAG）。

`deeptutor start` 后打开终端打印的前端地址——默认 [http://127.0.0.1:3782](http://127.0.0.1:3782)。在该终端按 `Ctrl+C` 可同时停止前后端。可跳过 `deeptutor init` 快速试用（默认端口、空模型配置）；之后在 **设置 → 模型** 中配置即可。

<details>
<summary><b>Conda 环境</b>（替代 <code>venv</code>）</summary>

```bash
conda create -n cogtutor python=3.11
conda activate cogtutor
python -m pip install --upgrade pip
```

</details>

<details>
<summary><b>可选 extras</b> — dev / partners / matrix / math-animator</summary>

```bash
pip install -e ".[dev]"             # 测试 / lint
pip install -e ".[partners]"        # Partner IM 通道 SDK + MCP 客户端
pip install -e ".[matrix]"          # Matrix 通道（无 E2EE/libolm）
pip install -e ".[matrix-e2e]"      # Matrix E2EE；需 libolm
pip install -e ".[math-animator]"   # Manim 插件；需 LaTeX/ffmpeg/系统库
```

</details>

<details>
<summary><b>前端依赖调整与开发服务器排障</b></summary>

**变更前端依赖：** 运行 `npm install --legacy-peer-deps` 刷新 `web/package-lock.json`，并提交 `web/package.json` 与 `web/package-lock.json`。

**开发服务器卡住：** 若 `deeptutor start` 提示已有前端无响应，先结束其打印的 PID。若实际无 Next.js 进程，则锁文件可能过期——删除后重试：

```bash
rm -f web/.next/dev/lock web/.next/lock
deeptutor start
```

</details>

</details>

<details>
<summary><b>方式 2 — Docker</b> · 从本仓库构建自包含镜像</summary>

本 fork 尚无已发布镜像，请用仓库内 `Dockerfile` 本地构建：

```bash
git clone https://github.com/cognisphere-space/CogTutor.git
cd CogTutor

docker build -t cogtutor:local .

docker run --rm --name cogtutor \
  -p 127.0.0.1:3782:3782 \
  -v cogtutor-data:/app/data \
  cogtutor:local
```

> 更多部署（podman / rootless / 只读 rootfs）见 [CONTAINERIZATION.md](./CONTAINERIZATION.md)。compose 文件仍引用上游镜像标签——发布自有镜像后请改为 `cogtutor:local` 或你的 registry 路径。

> **只需发布 `3782`。** 浏览器只访问前端源；容器内 Next.js 中间件（`web/proxy.ts`）将 `/api/*` 与 `/ws/*` 转发到 **容器内** FastAPI。发布 `8001`（`-p 127.0.0.1:8001:8001`）可选，仅便于 curl / 脚本直连 API。

打开 [http://127.0.0.1:3782](http://127.0.0.1:3782)。首次启动会创建 `/app/data/user/settings/*.json`；在 Web **设置** 中配置模型。配置、API Key、日志、工作区、记忆与知识库持久化在 `cogtutor-data` volume。

- **改主机端口：** 修改 `-p host:container` 左侧（如 `-p 127.0.0.1:8088:3782`）。若改了 `system.json` 中的容器侧端口，需重启并同步映射右侧。
- **后台运行：** 加 `-d`，用 `docker logs -f cogtutor` 跟日志，`docker stop cogtutor` 停止，复用名称前先 `docker rm cogtutor`。volume 跨重启保留数据。

**远程 Docker / 反向代理：** 浏览器只连前端（`:3782`）；容器内中间件在服务端转发 `/api/*`、`/ws/*`。单容器常见场景无需配置 API base——反向代理 / TLS 终结到 `:3782` 即可。仅 **前后端分离部署** 时需在 `data/user/settings/system.json` 设置 `next_public_api_base` 为前端服务端可达的后端地址（服务端读取，不下发浏览器）：

```json
{
  "next_public_api_base": "http://backend:8001"
}
```

`next_public_api_base_external`（及别名 `public_api_base`）为更低优先级回退。CORS 用前端 **origin**，不是 API URL。关闭认证时默认允许常规 HTTP/HTTPS 浏览器 origin；开启认证后需精确添加前端 origin：

```json
{
  "cors_origins": ["https://cogtutor.example.com"]
}
```

<details>
<summary><b>连接宿主机上的 Ollama / LM Studio / llama.cpp / vLLM / Lemonade</b></summary>

Docker 内 `localhost` 是容器自身。访问宿主机模型服务请用 host gateway（推荐）：

```bash
docker run --rm --name cogtutor \
  -p 127.0.0.1:3782:3782 -p 127.0.0.1:8001:8001 \
  --add-host=host.docker.internal:host-gateway \
  -v cogtutor-data:/app/data \
  cogtutor:local
```

然后在 **设置 → 模型** 将提供商 Base URL 指向 `host.docker.internal`：

- Ollama LLM：`http://host.docker.internal:11434/v1`
- Ollama embedding：`http://host.docker.internal:11434/api/embed`
- LM Studio：`http://host.docker.internal:1234/v1`
- llama.cpp：`http://host.docker.internal:8080/v1`
- Lemonade：`http://host.docker.internal:13305/api/v1`

Docker Desktop（macOS/Windows）通常无需 `--add-host` 即可解析 `host.docker.internal`。Linux 上该 flag 是在较新 Docker Engine 上创建该主机名的可移植方式。

**Linux 备选 — host 网络：** 加 `--network=host` 并去掉 `-p`。容器共享宿主机网络，直接打开 [http://127.0.0.1:3782](http://127.0.0.1:3782)（或 `system.json` 的 `frontend_port`），宿主机服务用普通 localhost URL（如 `http://127.0.0.1:11434/v1`）。注意 host 网络会把容器端口直接暴露在宿主机，可能冲突——若需保持 loopback，设置 `BACKEND_HOST=127.0.0.1` 与 `FRONTEND_HOST=127.0.0.1`（见 [CONTAINERIZATION.md](./CONTAINERIZATION.md)）。

</details>

</details>

<details>
<summary><b>方式 3 — 仅 CLI</b> · 无 Web UI，源码 checkout</summary>

不需要 Web UI 时，从源码安装 CLI-only 包：

```bash
git clone https://github.com/cognisphere-space/CogTutor.git
cd CogTutor

# 创建 venv（macOS/Linux）。Windows PowerShell：
#   py -3.11 -m venv .venv-cli ; .\.venv-cli\Scripts\Activate.ps1
python3 -m venv .venv-cli && source .venv-cli/bin/activate
python -m pip install --upgrade pip

python -m pip install -e ./packaging/deeptutor-cli
deeptutor init --cli
deeptutor chat
```

`deeptutor init --cli` 与完整应用共用 `data/user/settings/` 布局，但跳过前后端端口询问，且默认 **关闭** embedding（若要用 `deeptutor kb …` 或 RAG 工具请选 `Yes`）。仍会写入完整运行时布局（`system.json`、`auth.json`、`integrations.json`、`model_catalog.json`、`main.yaml`、`agents.yaml`），并询问当前 LLM 提供商与模型。

<details>
<summary><b>常用命令</b></summary>

```bash
deeptutor chat                                          # 交互式 REPL
deeptutor chat --capability deep_solve --tool rag --kb my-kb
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2 = 4" --tool rag --kb my-kb
deeptutor kb create my-kb --doc textbook.pdf
deeptutor memory show
deeptutor config show
```

</details>

本地 `deeptutor-cli` 不含 Web 资源与服务端依赖。请保留源码 checkout——可编辑安装指向该目录。之后若要加 Web，在同一工作区按方式 1 安装完整包并执行 `deeptutor init` + `deeptutor start`。

</details>

<details>
<summary><b>代码执行沙箱（办公技能）</b> · 运行模型生成的 docx / pdf / pptx / xlsx 代码</summary>

内置办公技能（**docx / pdf / pptx / xlsx**）流程：模型写短 Python 脚本（`python-docx`、`reportlab`、`openpyxl` 等）→ 经 `exec` / `code_execution` 执行 → 返回下载 URL。有沙箱后端时这些工具会挂载；**默认**在各部署形态均启用：

- **本地（方式 1 / 3）与 Docker 单容器（方式 2）：** 受限 subprocess 沙箱在宿主（本地）或容器内运行模型代码（容器本身即隔离边界）。
- **docker-compose：** 改为经 `DEEPTUTOR_SANDBOX_RUNNER_URL` 路由到最小权限 **runner sidecar**（`Dockerfile.runner`）——最强姿态，存在时自动优先。

subprocess 沙箱由 `data/user/settings/system.json` 的 `sandbox_allow_subprocess` 控制（默认 `true`）。在宿主执行模型生成代码是信任决策——设为 `false`（或 `DEEPTUTOR_SANDBOX_ALLOW_SUBPROCESS=0`）可禁用宿主侧执行，代价是办公技能无法产出文件。

</details>

<details>
<summary><b>配置参考</b> — <code>data/user/settings/</code> 下的 JSON/YAML</summary>

`data/user/settings/` 下均为普通 JSON/YAML。推荐在浏览器 **设置** 页编辑。

| 文件 | 用途 |
|:---|:---|
| `model_catalog.json` | LLM / embedding / 搜索提供商配置、API Key、当前模型 |
| `system.json` | 前后端端口、公共 API base、CORS、SSL 校验、附件目录 |
| `auth.json` | 可选认证开关、用户名、密码哈希、token/cookie |
| `integrations.json` | 可选 PocketBase 与 sidecar 集成 |
| `interface.json` | UI 语言 / 主题 / 侧栏偏好 |
| `main.yaml` | 运行时默认行为与路径注入 |
| `agents.yaml` | 能力/工具温度与 token 设置 |

项目根 `.env` **不会**作为应用配置读取。最小模型配置：打开 **设置 → 模型**，添加 LLM 配置（Base URL / API Key / 模型名）并保存。仅在使用知识库 / RAG 时再添加 embedding。

</details>

## 📖 功能导览

以下界面与能力主体来自上游 DeepTutor（本 fork 可能有改动）。日常主要界面：Chat、Partners、My Agents、Co-Writer、Book、知识中心、学习空间、Memory、设置——以及可选的多用户隔离部署。

<details>
<summary><b>💬 Chat — 真正在用的智能体循环</b></summary>

Chat 是默认能力，多数工作从这里开始。同一线程可正常对话、调工具、基于所选知识库 grounding、读附件、生成图片、咨询子智能体、写笔记本记录，并跨回合保持上下文。

循环刻意简单：模型分轮思考，需要时调工具，观察结果，以无工具消息结束。`ask_user` 特殊——不确定时暂停回合、提出结构化澄清问题，你回答后再继续。

用户可切换工具：`brainstorm`、`web_search`、`paper_search`、`reason`、`geogebra_analysis`；配置对应生成模型后还有 `imagegen` / `videogen`。上下文工具如 `rag`、`read_source`、`read_memory`、`write_memory`、`read_skill`、`load_tools`、`exec`、`web_fetch`、`ask_user`、`list_notebook`、`write_note`、`github`、`consult_subagent` 在回合具备相应上下文时自动挂载。

上下文两类：**粘性会话上下文**（子智能体、知识库、人设、模型、语音）在输入栏工具条，跨回合保留；**一次性引用**（文件、聊天历史、书籍、笔记本、题库、导入的智能体）来自 `+` 菜单，仅本回合。

Chat 也是更深能力的入口：**Quiz** 出题、**Research** 带引用报告、**Visualize** 图表/示意/动画，以及 *更多能力* 下的 **Solve** 推理解题与 **Mastery Path** 学习路径。

</details>

<details>
<summary><b>🤝 Partner — 同一大脑上的持久伙伴</b></summary>

Partners 是持久伙伴，自有 soul、模型策略、资料库、记忆与通道。并非独立 bot 引擎：每条 Web/IM 入站消息都变成 partner 作用域工作区内的普通 `ChatOrchestrator` 回合。可理解为「有性格、有电话号码的聊天」。

每个 partner 有 `SOUL.md`、模型选择、通道、工具策略与分配资料库。知识库、技能、笔记本复制到 `data/partners/<id>/workspace/`，同一套 RAG / skill / notebook / memory 工具无需特例。Partner 可读主人记忆，但只写自己的。

通道层为 schema 驱动，可按已装 extras 与凭证连接飞书、Telegram、Slack、Discord、钉钉、QQ/NapCat、企微、WhatsApp、Zulip、Mattermost、Matrix、Mochat、Microsoft Teams 等。Partner 也可作为子智能体，在普通 Chat 回合中被咨询——见下方 **My Agents**。

</details>

<details>
<summary><b>🧑‍🚀 My Agents — 咨询与导入其他智能体</b></summary>

My Agents 把其他智能体变成 CogTutor 的上下文，做两件事。**连接实时智能体**——本机 Claude Code / Codex CLI 或某个 Partner——在 Chat 回合中咨询：CogTutor 真正 *运行* 对方，经 `consult_subagent` 把过程流到 Activity 面板。用 Agent 芯片（或 `@`）选择，并设定咨询轮数。

**导入历史对话**——把已有 Claude Code / Codex 历史导入为可命名、可搜索、可恢复的智能体。选择导入日期；刷新会重新同步。任意 Chat 回合经 `+` → My Agents 引用；CogTutor 将其作为第三方 transcript 阅读——仍是 *对方* 的对话，而非本应用口吻。

</details>

<details>
<summary><b>✍️ Co-Writer — 选区感知 Markdown 起草</b></summary>

Co-Writer 是分栏 Markdown 工作区，适合报告、教程、笔记与长文学习产物。文档自动保存并实时预览（KaTeX 数学、图表 fence），草稿可沉淀回笔记本作可复用上下文。

核心是 **外科手术式编辑**：选中片段，让 CogTutor 改写、扩写或压缩。编辑智能体可 grounding 到知识库或网页证据，保留工具调用轨迹，每处改动以 accept/reject diff 呈现——你批准前不会落盘。

</details>

<details>
<summary><b>📖 Book — 从材料生成的活书</b></summary>

Book 把所选来源变成交互式 **活书**——不是静态 PDF，而是由类型化块构成的阅读环境。可从知识库、笔记本、题库或聊天历史起步；创建流程先提出章节大纲再生成内容，避免盲一次生成。

每章编译为类型化块——正文、提示框、测验、闪卡、时间线、代码、图、交互 HTML、动画、概念图、深潜与用户笔记——每页自有 Page Chat。块可编辑：插入、移动、重生成或改类型而无需整章重写。维护命令如 `deeptutor book health` 与 `deeptutor book refresh-fingerprints` 可检测源知识与已编译页是否漂移。

</details>

<details>
<summary><b>📚 知识中心 — 多引擎 RAG 库</b></summary>

知识库是 RAG 背后的文档集合——支撑 Chat、Co-Writer 编辑、Book 生成与 Partner 对话。特色是 **可选检索引擎**：**LlamaIndex**（默认，本地向量 + BM25）、**PageIndex**（托管，页级引用的推理检索）、**GraphRAG** 与 **LightRAG**（知识图谱检索）、**LightRAG Server**（HTTP 连接外部 LightRAG 实例卸载检索），或链接 **Obsidian** 库（就地读写）。每个 KB 绑定一个引擎。

创建时可选 **新建**（上传文档建索引）或 **链接已有**（复用他处索引、就地读、不重建）。重建写入新的扁平 `version-N` 目录并保留旧版，避免重建中毁掉可用索引。可从 **error** 状态库中删除单文档——去掉解析失败文件而无需整库删建。文档解析——纯文本、MinerU、Docling、markitdown、PyMuPDF4LLM——在 **设置 → 知识库** 选择，本地模型下载默认关闭。CLI 生命周期：`deeptutor kb list`、`info`、`create`、`add`、`search`、`set-default`、`delete`。

</details>

<details>
<summary><b>🌐 学习空间 — 技能、人设与可复用上下文</b></summary>

学习空间是资料库与个性化层——持久之物所在。**对话与材料** 保存聊天历史、笔记本与题库（每道保存题保留你的答案、参考答案与讲解）。**个性化** 含掌握路径、人设（如 *peer*、*research-assistant*、*teacher*）与技能（模型按需读取的 `SKILL.md` 剧本）。均可从 Chat、Partners、Co-Writer、Book 复用。

不必手写全部技能——**从 hub 导入** 可浏览社区目录，经安全门控下载到本地库（见 [技能与扩展](#-技能与扩展)）。

</details>

<details>
<summary><b>🧠 Memory — 可审计的个性化</b></summary>

Memory 是基于文件的三层系统，可阅读、策展、审计——刻意 *不是* 隐藏向量库。**L1** 为工作区镜像 + 仅追加事件轨迹（`trace/<surface>/<date>.jsonl`）；**L2** 为各面策展事实（`L2/<surface>.md`）；**L3** 为跨面综合（`L3/<profile|recent|scope|preferences>.md`）。L2 引用 L1、L3 引用 L2，画像中无不可追责条目。

Memory Graph 展示整金字塔——中心 L3、中环 L2、外环 L1——可将综合结论追溯到原始事件。覆盖 `chat`、`notebook`、`quiz`、`kb`、`book`、partner、`cowriter` 等面；整合器 Update / Audit / Dedup 预算在 **设置 → Memory** 调整。

</details>

<details>
<summary><b>⚙️ 设置 — 统一控制面</b></summary>

设置是运维控制面：实时状态条（后端、LLM、Embedding、搜索）+ 分区卡片：**外观**（主题 + UI 语言）、**网络**（API base、端口、CORS）、**模型**（LLM、Embedding、搜索、TTS、STT、图/视频生成）、**知识库**（文档解析引擎）、**Chat**（工具、MCP、各能力参数）、**Partners & Agents**（可咨询的子智能体）、**Memory**（整合器预算）。

多数分区为草稿-应用流，可先测提供商再提交。内置四主题：Default、Cream、Dark、Glass。项目根 `.env` 故意忽略；运行时配置在 `data/user/settings/*.json`，除非 `DEEPTUTOR_HOME` 或 `deeptutor start --home` 另行指定。

</details>

<details>
<summary><b>👥 多用户 — 共享部署</b> · 可选认证、按用户隔离工作区</summary>

认证 **默认关闭**——CogTutor 单用户运行。开启后，同一 `data/` 树并排托管管理员工作区、各用户隔离工作区与 partner 工作区：

```text
data/
├── user/                    # 管理员工作区 + 全局设置
├── users/<uid>/             # 用户作用域：聊天、记忆、笔记本、知识库
├── partners/<id>/workspace/ # Partner（合成用户）作用域
└── system/                  # auth/users.json · grants/<uid>.json · audit/usage.jsonl
```

**首位注册用户成为管理员**，拥有模型目录、提供商凭证、共享知识库、技能与用户授权。其他人获得隔离工作区与脱敏设置页——管理员分配的模型、知识库、技能以作用域只读选项出现，永不暴露原始 API Key。

**启用：** 在 `data/user/settings/auth.json` 打开认证，重启 `deeptutor start`，在 `/register` 注册首位管理员，再从 `/admin/users` 添加用户，经 grants 分配模型、知识库、技能、partners、工具/MCP 策略与代码执行权限。

> PocketBase 仍是单用户集成——多用户部署请保持 `integrations.pocketbase_url` 为空，除非已接入外部用户存储。

</details>

## ⌨️ CLI — 智能体原生接口

一个 `deeptutor` 二进制、两种用法：给人的交互式 **REPL**，以及给其他智能体驱动的结构化 **JSON**。能力、工具与知识库两侧一致。

<details>
<summary><b>自己驱动</b></summary>

`deeptutor chat` 打开交互 REPL；`deeptutor run <capability> "<message>"` 单回合后退出。均支持 `--capability`、`--tool`、`--kb`、`--config`。

```bash
deeptutor chat                                              # 交互式 REPL
deeptutor chat --capability deep_solve --kb my-kb --tool rag
deeptutor run chat "Explain the Fourier transform" --tool rag --kb textbook
deeptutor run deep_research "Survey 2026 papers on RAG" \
  --config mode=report --config depth=standard
```

Web 能力在 CLI 同样具备——知识库（`kb`）、会话（`session`）、partners（`partner`）、技能（`skill`）、笔记本、记忆与配置。完整列表见下。

</details>

<details>
<summary><b>让智能体驱动</b></summary>

CogTutor 可被 *其他智能体操作*。对任意 `run` 加 `--format json`，每回合流式输出 **NDJSON——每行一事件**（`content`、`tool_call`、`tool_result`、`done` 等），每行带 `session_id`。无头安全：无 TTY 时 `ask_user` 暂停会以空回复自动解决，不挂起。

```bash
# 单次、机器可读
deeptutor run deep_solve "Find d/dx[sin(x^2)]" --tool reason --format json

# 同一有状态会话串联回合——捕获 id 再复用
SID=$(deeptutor run deep_research "Survey 2026 papers on RAG" \
  --config mode=report --config depth=standard --format json \
  | jq -r 'select(.type=="done").session_id')
deeptutor run deep_question "Quiz me on that survey" --session "$SID" --format json
```

仓库根目录有 [`SKILL.md`](SKILL.md)——简短交接文档，一次读完即可让工具型 LLM 掌握整面。交给 Claude Code、Codex 或 OpenCode（会自动拾取 `SKILL.md`），或在 LangChain / AutoGen 循环中把 `deeptutor run` 包成工具。

</details>

<details>
<summary><b>命令参考</b></summary>

| 命令 | 说明 |
|:---|:---|
| `deeptutor init` | 为当前工作区创建或更新 `data/user/settings` |
| `deeptutor start [--home PATH]` | 同时启动后端 + 前端 |
| `deeptutor serve [--port PORT]` | 仅启动 FastAPI 后端 |
| `deeptutor run <capability> <message>` | 单能力回合（`chat`、`deep_solve`、`deep_question`、`deep_research`、`visualize`、`math_animator`、`mastery_path`）；加 `--format json` 输出 NDJSON |
| `deeptutor chat` | 交互 REPL（能力、工具、知识库、笔记本、历史） |
| `deeptutor partner list/create/start/stop` | 管理 IM 连接的 partners |
| `deeptutor kb list/info/create/add/search/set-default/delete` | 管理 LlamaIndex 知识库 |
| `deeptutor skill search/install/list/remove/login/logout/publish/update` | 管理技能并从已配置 hub 安装 |
| `deeptutor memory show/clear` | 查看 L2/L3 或清空 L1/全部记忆 |
| `deeptutor session list/show/open/rename/delete` | 管理共享会话 |
| `deeptutor notebook list/create/show/add-md/replace-md/remove-record` | 从 Markdown 管理笔记本 |
| `deeptutor book list/health/refresh-fingerprints` | 检查书籍并刷新源指纹 |
| `deeptutor plugin list/info` | 查看已注册工具与能力 |
| `deeptutor config show` | 打印配置摘要 |
| `deeptutor provider login <provider>` | 提供商认证（`openai-codex` OAuth；`github-copilot` 校验已有 Copilot 会话） |

</details>

## 🧩 技能与扩展

CogTutor 技能采用开放 **Agent-Skills** 格式——含 `SKILL.md`（YAML frontmatter + Markdown）与可选参考文件的目录。格式与产品无关，任何兼容 registry 都可作库源；活动 hub 在 `data/user/settings/skill_hubs.json` 配置。

```bash
deeptutor skill search "socratic tutor"          # 搜索已配置 hub
deeptutor skill install socratic-tutor           # 拉取 → 校验 → 注册
deeptutor skill list                             # 本地技能及 hub 溯源
```

**发布自己的技能** — 打包 `SKILL.md` 经已配置 hub 回传：

```bash
deeptutor skill login
deeptutor skill publish ./my-skill
deeptutor skill update
```

<details>
<summary><b>导入安全门控</b></summary>

无论来源，导入前均过 **同一安全门控**：

- 先检查 registry 的 **安全 verdict**——标记包默认拒绝，除非 `--allow-unverified`；
- 防御性解压（zip-slip / zip-bomb）+ 文本/脚本 **后缀白名单**，二进制不进工作区；
- frontmatter 规范化到本项目 schema，并 **剥离** `always:`，下载技能无法强制进入每个 system prompt；
- 溯源（hub、版本、verdict、安装时间）写入 `.hub-lock.json` 便于审计与更新。

多用户部署下安装仅管理员：新技能进管理员目录，授权前对其他用户不可见，便于上线前审查。

</details>

## 🌐 社区

### 贡献

CogTutor 在 [github.com/cognisphere-space/CogTutor](https://github.com/cognisphere-space/CogTutor) 开放开发。欢迎 Issue 与 PR——见 [贡献指南](CONTRIBUTING.md)；用 [GitHub Issues](https://github.com/cognisphere-space/CogTutor/issues) / [Discussions](https://github.com/cognisphere-space/CogTutor/discussions) 提建议或提问。

### 致谢

CogTutor 是 [**DeepTutor**](https://github.com/HKUDS/DeepTutor)（HKUDS，香港大学）的 fork。README 中描述的产品能力主体由上游设计与实现；感谢原作者与社区奠定的架构与功能，本项目在此基础上适配与扩展。亦站在优秀开源项目肩上：

| 项目 | 角色 |
|:---|:---|
| [**LlamaIndex**](https://github.com/run-llama/llama_index) | RAG 管线与文档索引骨干 |
| [**LightRAG**](https://github.com/HKUDS/LightRAG) | 简洁快速的 RAG |
| [**Codex**](https://github.com/openai/codex) | 启发 CLI 工作流的智能体原生编程 CLI |
| [**Claude Code**](https://github.com/anthropics/claude-code) | 启发智能体循环的 agentic 编程 CLI |
| [**ManimCat**](https://github.com/Wing900/ManimCat) | Math Animator 的 AI 数学动画生成 |

### 许可证

[Apache License 2.0](LICENSE)，继承自上游 DeepTutor。全文与原始版权声明见 [`LICENSE`](LICENSE)。
