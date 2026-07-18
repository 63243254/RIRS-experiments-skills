# 人工 vs Agent

## 用户只需说

```
用 RIRS 实验 Agent：
- 目标：训练 XXX
- 代码：D:/research/xxx
- 数据：D:/research/xxx/data 或服务器路径/下载链接
- 训练：python train.py --epochs 50
- （可选）复用容器名
```

Agent：取名 → 建容器 → 上传 → venv（缺包就装）→ 装 tmux → 等 GPU → 后台训练 → 每 15 分钟巡检。

## 映射

| 人工 | Agent |
|------|-------|
| 登录 | login |
| 新建起名 | 自拟 exp-主题-日期 + ensure |
| 上传 | upload；>10G 后台 + 15min 巡检 |
| 配环境 | 项目 .venv；缺什么装什么 |
| 无 tmux | ensure_tmux(install=True)，否则 nohup |
| 长训练 | long_job_start |
| 盯进度 | 每 15 分钟 long_job_status |
| 等卡 | 每 30 分钟 nvidia-smi |

## 长任务判定

预估 ≥10 分钟 / 多次训练 / 数据 >10GB / 挂机 → 后台 + 15 分钟巡检。

## 巡检模板

```
[巡检 HH:MM] session=... mode=tmux|nohup alive=yes/no
日志尾部: ...
下一步: 继续等 15 分钟 / 已结束 / 失败处理
```
