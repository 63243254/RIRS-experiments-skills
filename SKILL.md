---
name: rirs-experiment-agent
description: "Operate WHU RIRS DL cloud (no SSH, Web only). User states experiment; Agent auto-names, creates container, uploads code/data, creates project venv (install missing pkgs), installs tmux if needed, picks GPU, runs training, polls long jobs every 15 min. Use for RIRS / campus GPU / 202.114.114.19 experiments."
user-invocable: true
allowed-tools: Read, Bash
argument-hint: "[experiment goal / code path / data path / train cmd]"
---

# RIRS Experiment Agent

校园网深度学习云平台（**无 SSH**）。前端 `http://202.114.114.19:8001`，API `http://202.114.114.19:8002`，容器 IDE 为 code-server。

用户只需说明「要做哪个实验、代码/数据在哪、怎么训」。  
**Agent 全权负责命名、建容器、上传、环境、训练与巡检**，不必手点网页。

## 何时使用

- 在 RIRS 上跑实验 / 训练
- 「用实验 Agent」「上服务器跑」「容器里训练」
- 新建/复用容器、上传、venv、等 GPU、长训练

## 端到端标准流程（必须遵守）

### 0. 收集输入（可合理自拟）

| 项 | 来源 |
|----|------|
| 实验目标 / 训练命令 | 用户必给，或可从代码推断 |
| 代码路径 | 本机路径或服务器路径 |
| 数据路径 | 本机 / 服务器 / 下载 URL |
| 容器名 | **Agent 自拟**：`exp-<主题>-<MMDD>` |
| 镜像 | 默认 `pytorch:1.13_11.6_8` |
| 复用旧容器 | 未说明则新建；用户指定则复用 |

容器名正则：`^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$`

### 1. 登录

`rirs_cli.py login`（token：`~/.rirs/token.json`）

### 2. 构建 / 复用容器

`ensure --name <名>` → 等待 RUNNING（约 30–180s）。  
CPU/内存/GPU 申请保持默认 2/4/1。

### 3. 打开 code-server，装基础工具

1. **确保 tmux**（没有就装）：`ensure_tmux(install=True)`
   - 非交互 `apt-get install -y tmux`（root 或 `sudo -n`）
   - 带 `timeout`，避免卡在密码提示
   - 装不上 → 长任务自动 **nohup+setsid** 回退
2. 工作目录：`/data/user/<实验名>/`

### 4. 上传代码与数据

| 规模 | 策略 |
|------|------|
| 小文件 / 代码 | `upload` / base64 / tar.gz |
| 中等 | tar 或容器内 `wget`/`git clone` |
| **>10GB** | 不阻塞硬传；后台 `wget`/网盘 + **每 15 分钟巡检** |

### 5. 项目虚拟环境（缺什么装什么）

**必须在项目自建 venv 中装依赖，不污染系统 site-packages。**

推荐：`/data/user/<实验名>/.venv`

1. `setup_venv(venv_path, requirements=...)` 创建并装 requirements
2. 缺包（`ModuleNotFoundError`）→ `ensure_pip_packages([...], venv_path=...)` 立刻装进该 venv
3. torch/CUDA 优先用镜像预装；冲突在 venv 内解决
4. 训练前：`source <venv>/bin/activate`

### 6. GPU

训练前 `nvidia-smi`。无空闲卡：**每 30 分钟**再查。  
有空闲：`CUDA_VISIBLE_DEVICES=<id>`。

### 7. 启动实验

- **短任务**（<10 分钟）：可前台执行
- **长任务**（任一满足）→ 后台 + 巡检：
  - 预估 ≥10 分钟
  - 多次训练 / 多阶段
  - 数据 >10GB
  - 用户要求挂机

`long_job_start(..., prefer_tmux=True, install_tmux=True)`  
双终端：A/tmux 长训；B 快操作（日志、nvidia-smi、补包）。

### 8. 长任务巡检（计时器）

1. 启动后告知用户：日志路径、session/pid、mode
2. **每 15 分钟**巡检（`sleep 900` 后再查）：
   - `long_job_status`
   - 读日志 tail
   - 失败：读 traceback → 缺包则装 → 同错误最多自动重试 2 次
   - 成功：汇总产物回报
3. 未完成则继续等；每次巡检简短状态，不刷屏
4. 等空闲 GPU 仍用 **30 分钟** 间隔

### 9. 结束回报

容器名、URL、venv、tmux/nohup、GPU、命令、日志、最终状态与指标。

## CLI

```powershell
$PY = "D:\Program files\anaconda3\python.exe"
$SK = "$env:USERPROFILE\.codex\skills\rirs-experiment-agent"
& $PY "$SK\scripts\rirs_cli.py" --config "$SK\config.yaml" login
& $PY "$SK\scripts\rirs_cli.py" --config "$SK\config.yaml" ensure --name exp-demo
& $PY "$SK\scripts\rirs_cli.py" --config "$SK\config.yaml" run-exp --name exp-demo --path D:\code\proj --setup-venv --wait-gpu --cmd "python train.py"
```

API：`ensure_tmux` / `setup_venv` / `ensure_pip_packages` / `long_job_*` / `new_terminal`

## 失败处理

| 现象 | 处理 |
|------|------|
| 无 tmux | 安装；失败 → nohup |
| 缺包 | venv 内 pip 安装 |
| 大数据 | 后台传 + 15min 巡检 |
| 无 GPU | 30min 轮询 |
| 训练崩溃 | 读日志、补依赖、有限重启 |

## 安全

账号仅本机 config；仅校园网。

## 参考

- `references/api.md`
- `references/workflow.md`
