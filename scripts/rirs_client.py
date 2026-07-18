"""RIRS 云平台 HTTP API 客户端（逆向自前端 Vue SPA）。

前端: http://202.114.114.19:8001
后端: http://202.114.114.19:8002
code-server: https://202.114.114.19:8003/code-server/{podName}/
认证头: satoken
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

DEFAULT_WEB_BASE = "http://202.114.114.19:8001"
DEFAULT_API_BASE = "http://202.114.114.19:8002"
DEFAULT_CS_BASE = "https://202.114.114.19:8003"

# 容器名: 字母数字开头结尾，允许 -_. 中间
NAME_RE = re.compile(r"^(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$")


class RirsError(RuntimeError):
    pass


@dataclass
class ImageInfo:
    id: str
    name: str
    tag: str
    description: Optional[str] = None
    access: Optional[int] = None
    support_code_server: int = 1
    support_web_top: int = 0
    user_id: Optional[str] = None

    @property
    def ref(self) -> str:
        return f"{self.name}:{self.tag}"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ImageInfo":
        return cls(
            id=str(d.get("id")),
            name=d.get("name") or "",
            tag=d.get("tag") or "",
            description=d.get("description"),
            access=d.get("access"),
            support_code_server=int(d.get("supportCodeServer") or 0),
            support_web_top=int(d.get("supportWebTop") or 0),
            user_id=str(d.get("userId")) if d.get("userId") is not None else None,
        )


@dataclass
class ContainerInfo:
    id: str
    name: str
    pod_name: Optional[str]
    image_id: Optional[str]
    status: str
    cpu_requests: int = 2
    memory_requests: int = 4
    gpu_requests: int = 1
    code_server_url: Optional[str] = None
    web_top_url: Optional[str] = None
    jupyter_url: Optional[str] = None
    audit_status: Optional[int] = None
    support_code_server: int = 1
    support_web_top: int = 0
    create_time: Optional[int] = None
    last_access_time: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def running(self) -> bool:
        return (self.status or "").upper() == "RUNNING"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContainerInfo":
        return cls(
            id=str(d.get("id")),
            name=d.get("name") or "",
            pod_name=d.get("podName"),
            image_id=str(d.get("imageId")) if d.get("imageId") is not None else None,
            status=str(d.get("status") or ""),
            cpu_requests=int(d.get("cpuRequests") or 0),
            memory_requests=int(d.get("memoryRequests") or 0),
            gpu_requests=int(d.get("gpuRequests") or 0),
            code_server_url=d.get("codeServerUrl"),
            web_top_url=d.get("webTopUrl"),
            jupyter_url=d.get("jupyterUrl"),
            audit_status=d.get("auditStatus"),
            support_code_server=int(d.get("supportCodeServer") or 0),
            support_web_top=int(d.get("supportWebTop") or 0),
            create_time=d.get("createTime"),
            last_access_time=d.get("lastAccessTime"),
            raw=d,
        )


class RirsClient:
    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        web_base: str = DEFAULT_WEB_BASE,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.web_base = web_base.rstrip("/")
        self.username = username or os.environ.get("RIRS_USERNAME", "")
        self.password = password or os.environ.get("RIRS_PASSWORD", "")
        self.token = token or os.environ.get("RIRS_TOKEN", "")
        self._client = httpx.Client(
            base_url=self.api_base,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RirsClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            raise RirsError("未登录：缺少 satoken，请先 login()")
        return {"satoken": self.token}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Any = None,
        auth: bool = True,
    ) -> Any:
        headers = self._auth_headers() if auth else {}
        resp = self._client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=headers,
        )
        if resp.status_code >= 400:
            raise RirsError(f"HTTP {resp.status_code} {method} {path}: {resp.text[:500]}")
        try:
            data = resp.json()
        except Exception as exc:
            raise RirsError(f"响应非 JSON: {resp.text[:300]}") from exc
        code = data.get("code")
        if code != 200:
            raise RirsError(f"业务错误 code={code} msg={data.get('msg')} path={path}")
        return data.get("data")

    # ---------- auth ----------
    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> dict[str, Any]:
        username = username or self.username
        password = password or self.password
        if not username or not password:
            raise RirsError("需要 username/password，或设置 RIRS_USERNAME / RIRS_PASSWORD")
        data = self._request(
            "POST",
            "/auth/login",
            json_body={"username": username, "password": password},
            auth=False,
        )
        token = (((data or {}).get("tokenInfo") or {}).get("tokenValue"))
        if not token:
            raise RirsError(f"登录成功但未返回 token: {data}")
        self.token = token
        self.username = username
        self.password = password
        return data

    def ensure_login(self) -> None:
        if self.token:
            try:
                self.me()
                return
            except RirsError:
                self.token = ""
        self.login()

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/system/user/self")

    def save_token(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "token": self.token,
                    "username": self.username,
                    "api_base": self.api_base,
                    "saved_at": int(time.time()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def load_token(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self.token = data.get("token") or ""
        self.username = data.get("username") or self.username
        return bool(self.token)

    # ---------- images ----------
    def list_user_images(self, page: int = 1, size: int = 50) -> list[ImageInfo]:
        data = self._request("GET", "/k8s/image/user", params={"page": page, "size": size})
        return [ImageInfo.from_dict(x) for x in (data or {}).get("records") or []]

    def list_all_images(self, page: int = 1, size: int = 100) -> list[ImageInfo]:
        data = self._request("GET", "/k8s/image/all", params={"page": page, "size": size})
        return [ImageInfo.from_dict(x) for x in (data or {}).get("records") or []]

    def get_image(self, image_id: str) -> ImageInfo:
        data = self._request("GET", f"/k8s/image/{image_id}")
        return ImageInfo.from_dict(data)

    def find_image(
        self,
        *,
        image_id: Optional[str] = None,
        name: Optional[str] = None,
        tag: Optional[str] = None,
        ref: Optional[str] = None,
        prefer_user: bool = True,
    ) -> ImageInfo:
        if image_id:
            return self.get_image(image_id)
        if ref and ":" in ref:
            name, tag = ref.split(":", 1)
        pools: list[ImageInfo] = []
        if prefer_user:
            pools.extend(self.list_user_images(size=100))
        # 再扫 all
        page = 1
        while True:
            batch = self.list_all_images(page=page, size=100)
            if not batch:
                break
            pools.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        # 去重
        seen = set()
        uniq: list[ImageInfo] = []
        for img in pools:
            if img.id in seen:
                continue
            seen.add(img.id)
            uniq.append(img)
        if name and tag:
            for img in uniq:
                if img.name == name and img.tag == tag:
                    return img
        if name:
            cands = [i for i in uniq if i.name == name]
            if len(cands) == 1:
                return cands[0]
            if cands:
                # 优先 pytorch 新版 / 用户自有
                cands.sort(key=lambda x: (x.access or 0, x.tag), reverse=True)
                return cands[0]
        raise RirsError(f"未找到镜像: id={image_id} name={name} tag={tag} ref={ref}")

    # ---------- containers ----------
    def list_containers(self, page: int = 1, size: int = 50) -> list[ContainerInfo]:
        data = self._request("GET", "/k8s/container/user", params={"page": page, "size": size})
        return [ContainerInfo.from_dict(x) for x in (data or {}).get("records") or []]

    def get_container(self, name_or_id: str) -> ContainerInfo:
        for c in self.list_containers(size=100):
            if c.id == name_or_id or c.name == name_or_id or c.pod_name == name_or_id:
                return c
        raise RirsError(f"未找到容器: {name_or_id}")

    def check_name_exists(self, name: str) -> bool:
        data = self._request("GET", "/k8s/container/user/checkExist", params={"name": name})
        return bool(data)

    def create_container(
        self,
        name: str,
        image_id: str,
        *,
        cpu: int = 2,
        memory: int = 4,
        gpu: int = 1,
    ) -> Any:
        if not NAME_RE.match(name):
            raise RirsError(
                f"非法容器名 '{name}'：仅允许字母数字和 -_.，且以字母数字开头结尾"
            )
        if self.check_name_exists(name):
            raise RirsError(f"容器名已存在: {name}")
        body = {
            "name": name,
            "imageId": str(image_id),
            "cpuRequests": int(cpu),
            "memoryRequests": int(memory),
            "gpuRequests": int(gpu),
        }
        return self._request("POST", "/k8s/container/", json_body=body)

    def delete_container(self, container_id: str) -> Any:
        return self._request("DELETE", f"/k8s/container/{container_id}")

    def get_code_server_url(self, container_id: str) -> str:
        data = self._request("GET", f"/k8s/container/code-server/{container_id}")
        if not data:
            raise RirsError("code-server URL 为空")
        return str(data)

    def get_web_top_url(self, container_id: str) -> str:
        data = self._request("GET", f"/k8s/container/web-top/{container_id}")
        return str(data)

    def wait_running(
        self,
        name_or_id: str,
        *,
        timeout: float = 180.0,
        interval: float = 5.0,
    ) -> ContainerInfo:
        deadline = time.time() + timeout
        last: Optional[ContainerInfo] = None
        while time.time() < deadline:
            try:
                last = self.get_container(name_or_id)
                if last.running and last.code_server_url:
                    return last
            except RirsError:
                pass
            time.sleep(interval)
        status = last.status if last else "UNKNOWN"
        raise RirsError(f"等待容器 RUNNING 超时({timeout}s)，最后状态={status}")

    def ensure_container(
        self,
        name: str,
        *,
        image: str = "pytorch:1.13_11.6_8",
        image_id: Optional[str] = None,
        reuse: bool = True,
        cpu: int = 2,
        memory: int = 4,
        gpu: int = 1,
        wait: bool = True,
        wait_timeout: float = 180.0,
    ) -> ContainerInfo:
        """获取或创建容器。reuse=True 时若同名已存在则直接复用。"""
        self.ensure_login()
        if reuse:
            try:
                existing = self.get_container(name)
                if wait and not existing.running:
                    return self.wait_running(name, timeout=wait_timeout)
                return existing
            except RirsError:
                pass
        if not image_id:
            img = self.find_image(ref=image) if ":" in image else self.find_image(name=image)
            image_id = img.id
        self.create_container(name, image_id, cpu=cpu, memory=memory, gpu=gpu)
        if wait:
            # 用户经验：刷新后约 30s 进入 RUNNING
            time.sleep(3)
            return self.wait_running(name, timeout=wait_timeout)
        return self.get_container(name)


def load_config(path: Optional[str | Path] = None) -> dict[str, Any]:
    """加载 YAML/JSON 配置。"""
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    env = os.environ.get("RIRS_CONFIG")
    if env:
        candidates.append(Path(env))
    home = Path.home() / ".rirs" / "config.yaml"
    candidates.append(home)
    skill_cfg = Path(__file__).resolve().parent.parent / "config.yaml"
    candidates.append(skill_cfg)

    for p in candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if p.suffix.lower() in {".yaml", ".yml"}:
                import yaml

                return yaml.safe_load(text) or {}
            return json.loads(text)
    return {}


def client_from_config(cfg: Optional[dict[str, Any]] = None) -> RirsClient:
    cfg = cfg if cfg is not None else load_config()
    c = RirsClient(
        api_base=cfg.get("api_base") or DEFAULT_API_BASE,
        web_base=cfg.get("web_base") or DEFAULT_WEB_BASE,
        username=cfg.get("username") or os.environ.get("RIRS_USERNAME"),
        password=cfg.get("password") or os.environ.get("RIRS_PASSWORD"),
        token=cfg.get("token") or os.environ.get("RIRS_TOKEN"),
    )
    token_path = cfg.get("token_cache") or str(Path.home() / ".rirs" / "token.json")
    token_path = os.path.expanduser(str(token_path))
    if not c.token:
        c.load_token(token_path)
    try:
        c.ensure_login()
        c.save_token(token_path)
    except RirsError:
        raise
    return c

