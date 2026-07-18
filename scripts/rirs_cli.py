#!/usr/bin/env python3
"""RIRS 实验 Agent CLI。

示例:
  python rirs_cli.py login
  python rirs_cli.py images
  python rirs_cli.py containers
  python rirs_cli.py ensure --name exp-demo --image pytorch:1.13_11.6_8
  python rirs_cli.py open-url --name exp-demo
  python rirs_cli.py exec --name exp-demo --cmd "nvidia-smi"
  python rirs_cli.py upload --name exp-demo --path ./train.py --path ./data
  python rirs_cli.py run-exp --name exp-demo --path ./proj --cmd "python train.py" --wait-gpu
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# 保证可导入同目录模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rirs_client import RirsClient, RirsError, client_from_config, load_config  # noqa: E402
from codeserver_ops import CodeServerSession, CodeServerError  # noqa: E402


def _print(data: Any) -> None:
    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(data)


def _client(args: argparse.Namespace) -> RirsClient:
    cfg = load_config(getattr(args, "config", None))
    if getattr(args, "username", None):
        cfg["username"] = args.username
    if getattr(args, "password", None):
        cfg["password"] = args.password
    return client_from_config(cfg)


def cmd_login(args: argparse.Namespace) -> int:
    c = _client(args)
    me = c.me()
    token_path = Path.home() / ".rirs" / "token.json"
    c.save_token(token_path)
    _print({"ok": True, "user": me.get("username"), "token_cache": str(token_path)})
    c.close()
    return 0


def cmd_images(args: argparse.Namespace) -> int:
    c = _client(args)
    imgs = c.list_user_images(size=100) if args.user_only else c.list_all_images(size=100)
    rows = [
        {
            "id": i.id,
            "ref": i.ref,
            "access": i.access,
            "code_server": i.support_code_server,
        }
        for i in imgs
    ]
    _print(rows)
    c.close()
    return 0


def cmd_containers(args: argparse.Namespace) -> int:
    c = _client(args)
    rows = []
    for x in c.list_containers(size=100):
        rows.append(
            {
                "id": x.id,
                "name": x.name,
                "status": x.status,
                "imageId": x.image_id,
                "podName": x.pod_name,
                "cpu": x.cpu_requests,
                "mem": x.memory_requests,
                "gpu": x.gpu_requests,
                "codeServerUrl": x.code_server_url,
            }
        )
    _print(rows)
    c.close()
    return 0


def cmd_ensure(args: argparse.Namespace) -> int:
    c = _client(args)
    cont = c.ensure_container(
        args.name,
        image=args.image,
        image_id=args.image_id,
        reuse=not args.no_reuse,
        cpu=args.cpu,
        memory=args.memory,
        gpu=args.gpu,
        wait=not args.no_wait,
        wait_timeout=args.wait_timeout,
    )
    url = cont.code_server_url
    if cont.running and cont.id:
        try:
            url = c.get_code_server_url(cont.id)
        except RirsError:
            pass
    _print(
        {
            "id": cont.id,
            "name": cont.name,
            "status": cont.status,
            "podName": cont.pod_name,
            "codeServerUrl": url,
        }
    )
    c.close()
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    c = _client(args)
    cont = c.get_container(args.name)
    c.delete_container(cont.id)
    _print({"deleted": cont.name, "id": cont.id})
    c.close()
    return 0


def cmd_open_url(args: argparse.Namespace) -> int:
    c = _client(args)
    cont = c.get_container(args.name)
    if not cont.running:
        raise SystemExit(f"容器未运行: {cont.status}")
    url = c.get_code_server_url(cont.id)
    _print({"name": cont.name, "url": url})
    c.close()
    return 0


def _open_session(args: argparse.Namespace) -> tuple[RirsClient, Any, CodeServerSession]:
    c = _client(args)
    cont = c.get_container(args.name)
    if not cont.running:
        cont = c.wait_running(args.name, timeout=args.wait_timeout)
    url = c.get_code_server_url(cont.id)
    sess = CodeServerSession(
        url,
        headless=not args.headed,
        workdir=args.workdir,
        timeout_ms=args.pw_timeout,
    )
    sess.open()
    return c, cont, sess


def cmd_exec(args: argparse.Namespace) -> int:
    c, cont, sess = _open_session(args)
    try:
        out = sess.run(args.cmd, timeout=args.cmd_timeout)
        print(out)
    finally:
        sess.close()
        c.close()
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    c, cont, sess = _open_session(args)
    try:
        if len(args.path) == 1 and Path(args.path[0]).is_file() and args.remote:
            remote = sess.upload_file(args.path[0], args.remote)
            _print({"uploaded": remote})
        else:
            out = sess.upload_paths(args.path, remote_dir=args.remote or args.workdir)
            print(out)
    finally:
        sess.close()
        c.close()
    return 0


def cmd_gpu(args: argparse.Namespace) -> int:
    c, cont, sess = _open_session(args)
    try:
        smi = sess.nvidia_smi()
        print(smi)
        free = sess.pick_free_gpu(max_util=args.max_util, max_mem_mb=args.max_mem)
        _print({"free_gpu": free})
    finally:
        sess.close()
        c.close()
    return 0


def cmd_run_exp(args: argparse.Namespace) -> int:
    c = _client(args)
    cont = c.ensure_container(
        args.name,
        image=args.image,
        image_id=args.image_id,
        reuse=not args.no_reuse,
        cpu=args.cpu,
        memory=args.memory,
        gpu=args.gpu,
        wait=True,
        wait_timeout=args.wait_timeout,
    )
    url = c.get_code_server_url(cont.id)
    sess = CodeServerSession(
        url,
        headless=not args.headed,
        workdir=args.workdir,
        timeout_ms=args.pw_timeout,
    )
    sess.open()
    try:
        if args.path:
            print("[upload]", args.path)
            print(sess.upload_paths(args.path, remote_dir=args.remote_dir or args.workdir))
        if args.setup_venv:
            print("[venv] creating...")
            print(
                sess.setup_venv(
                    args.venv,
                    requirements=args.requirements,
                    pip_packages=args.pip or None,
                )
            )
        gpu = args.cuda_device
        if args.wait_gpu:
            print("[gpu] waiting for free device...")
            gpu = sess.wait_for_free_gpu(
                poll_seconds=args.gpu_poll,
                max_wait=args.gpu_wait_max,
                max_util=args.max_util,
                max_mem_mb=args.max_mem,
            )
            print(f"[gpu] selected cuda device {gpu}")
        elif gpu is None and args.auto_gpu:
            gpu = sess.pick_free_gpu(max_util=args.max_util, max_mem_mb=args.max_mem)
            print(f"[gpu] auto selected {gpu}")
        if args.cmd:
            if args.foreground:
                env = f"CUDA_VISIBLE_DEVICES={gpu} " if gpu is not None else ""
                activate = (
                    f"source {args.venv}/bin/activate && " if args.setup_venv or args.use_venv else ""
                )
                cwd = args.remote_dir or args.workdir
                out = sess.run(
                    f"cd {cwd} && {activate}{env}{args.cmd}",
                    timeout=args.cmd_timeout,
                )
                print(out)
            else:
                pid = sess.start_training(
                    args.cmd,
                    gpu=gpu,
                    log_file=args.log_file,
                    venv_path=args.venv if (args.setup_venv or args.use_venv) else None,
                    cwd=args.remote_dir or args.workdir,
                )
                _print(
                    {
                        "started": True,
                        "pid_output": pid,
                        "log_file": args.log_file,
                        "gpu": gpu,
                        "container": cont.name,
                        "codeServerUrl": url,
                    }
                )
        else:
            _print({"container": cont.name, "codeServerUrl": url, "gpu": gpu})
    finally:
        sess.close()
        c.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RIRS 云平台实验 Agent CLI")
    p.add_argument("--config", help="配置文件路径 yaml/json")
    p.add_argument("--username", help="覆盖配置中的用户名")
    p.add_argument("--password", help="覆盖配置中的密码")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("login", help="登录并缓存 token")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("images", help="列出镜像")
    s.add_argument("--user-only", action="store_true")
    s.set_defaults(func=cmd_images)

    s = sub.add_parser("containers", help="列出我的容器")
    s.set_defaults(func=cmd_containers)

    s = sub.add_parser("ensure", help="确保容器存在并运行")
    s.add_argument("--name", required=True)
    s.add_argument("--image", default="pytorch:1.13_11.6_8")
    s.add_argument("--image-id")
    s.add_argument("--cpu", type=int, default=2)
    s.add_argument("--memory", type=int, default=4)
    s.add_argument("--gpu", type=int, default=1)
    s.add_argument("--no-reuse", action="store_true")
    s.add_argument("--no-wait", action="store_true")
    s.add_argument("--wait-timeout", type=float, default=180)
    s.set_defaults(func=cmd_ensure)

    s = sub.add_parser("delete", help="删除容器")
    s.add_argument("--name", required=True)
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("open-url", help="获取 code-server URL")
    s.add_argument("--name", required=True)
    s.set_defaults(func=cmd_open_url)

    def add_cs_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--name", required=True, help="容器名或 id")
        sp.add_argument("--workdir", default="/data/user")
        sp.add_argument("--headed", action="store_true", help="显示浏览器窗口")
        sp.add_argument("--wait-timeout", type=float, default=180)
        sp.add_argument("--pw-timeout", type=int, default=120000)
        sp.add_argument("--cmd-timeout", type=float, default=600)

    s = sub.add_parser("exec", help="在 code-server 终端执行命令")
    add_cs_args(s)
    s.add_argument("--cmd", required=True)
    s.set_defaults(func=cmd_exec)

    s = sub.add_parser("upload", help="上传文件/目录到容器")
    add_cs_args(s)
    s.add_argument("--path", action="append", required=True, help="可重复")
    s.add_argument("--remote", help="远程路径或目录")
    s.set_defaults(func=cmd_upload)

    s = sub.add_parser("gpu", help="查看 GPU 并挑选空闲卡")
    add_cs_args(s)
    s.add_argument("--max-util", type=int, default=10)
    s.add_argument("--max-mem", type=int, default=1024)
    s.set_defaults(func=cmd_gpu)

    s = sub.add_parser("run-exp", help="一键：确保容器+上传+环境+等GPU+启动训练")
    add_cs_args(s)
    s.add_argument("--image", default="pytorch:1.13_11.6_8")
    s.add_argument("--image-id")
    s.add_argument("--cpu", type=int, default=2)
    s.add_argument("--memory", type=int, default=4)
    s.add_argument("--gpu", type=int, default=1, help="申请显卡张数(平台参数)")
    s.add_argument("--no-reuse", action="store_true")
    s.add_argument("--path", action="append", help="要上传的本地路径，可重复")
    s.add_argument("--remote-dir", help="上传目标目录，默认 workdir")
    s.add_argument("--setup-venv", action="store_true")
    s.add_argument("--use-venv", action="store_true")
    s.add_argument("--venv", default="/data/user/.venv")
    s.add_argument("--requirements", help="requirements.txt 本地路径")
    s.add_argument("--pip", action="append", help="额外 pip 包，可重复")
    s.add_argument("--cmd", help="训练命令，如 python train.py --epochs 10")
    s.add_argument("--foreground", action="store_true", help="前台跑命令（会阻塞）")
    s.add_argument("--log-file", default="/data/user/train.log")
    s.add_argument("--wait-gpu", action="store_true", help="轮询直到有空闲 GPU")
    s.add_argument("--auto-gpu", action="store_true", help="若当前有空闲卡则选用")
    s.add_argument("--cuda-device", type=int, help="强制 CUDA_VISIBLE_DEVICES")
    s.add_argument("--gpu-poll", type=int, default=1800, help="等卡轮询秒数，默认 30min")
    s.add_argument("--gpu-wait-max", type=float, default=6 * 3600)
    s.add_argument("--max-util", type=int, default=10)
    s.add_argument("--max-mem", type=int, default=1024)
    s.set_defaults(func=cmd_run_exp)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (RirsError, CodeServerError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
