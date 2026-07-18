"""code-server ??????????????GPU ???"""
from __future__ import annotations

import base64
import shlex
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from playwright.sync_api import Browser, Page, Playwright, sync_playwright


class CodeServerError(RuntimeError):
    pass


class CodeServerSession:
    def __init__(
        self,
        url: str,
        *,
        headless: bool = True,
        slow_mo: int = 0,
        timeout_ms: int = 120_000,
        workdir: str = "/data/user",
    ) -> None:
        self.url = url
        self.headless = headless
        self.slow_mo = slow_mo
        self.timeout_ms = timeout_ms
        self.workdir = workdir.rstrip("/") or "/data/user"
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._terminal_ready = False

    def __enter__(self) -> "CodeServerSession":
        self.open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def open(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=["--ignore-certificate-errors"],
        )
        context = self._browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
            permissions=["clipboard-read", "clipboard-write"],
        )
        self.page = context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self.page.goto(self.url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_selector(".monaco-workbench", timeout=self.timeout_ms)
        except Exception:
            self.page.wait_for_selector("body", timeout=self.timeout_ms)
        self.page.wait_for_timeout(3000)
        self._dismiss_popups()
        self._close_welcome()

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            self._browser = None
            if self._pw:
                self._pw.stop()
            self._pw = None
            self.page = None
            self._terminal_ready = False

    def _require_page(self) -> Page:
        if not self.page:
            raise CodeServerError("session ???")
        return self.page

    def _dismiss_popups(self) -> None:
        page = self._require_page()
        for text in (
            "Don't Show Again",
            "Dont Show Again",
            "Got it",
            "Dismiss",
            "Skip Tour",
            "Skip",
            "Close",
            "??",
            "??",
        ):
            try:
                loc = page.get_by_text(text, exact=False).first
                if loc.is_visible(timeout=300):
                    loc.click(timeout=800)
            except Exception:
                pass
        for _ in range(2):
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    def _close_welcome(self) -> None:
        page = self._require_page()
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)
        except Exception:
            pass
        self._dismiss_popups()

    def _command_palette(self, command: str) -> None:
        page = self._require_page()
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        page.keyboard.press("Control+Shift+P")
        page.wait_for_timeout(450)
        # insert_text ???????????? type
        page.keyboard.type(command, delay=18)
        page.wait_for_timeout(450)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)


    def focus_terminal(self) -> None:
        page = self._require_page()
        self._dismiss_popups()
        # ?????????? + ??????
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.keyboard.press("Control+Shift+P")
        page.wait_for_timeout(500)
        page.keyboard.type("Terminal: Create New Terminal", delay=18)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        if page.locator(".xterm-helper-textarea").count() == 0:
            page.keyboard.press("Control+Shift+P")
            page.wait_for_timeout(400)
            page.keyboard.type("Create New Terminal", delay=18)
            page.wait_for_timeout(400)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)

        # ?? xterm ??
        for _ in range(25):
            if page.locator(".xterm-helper-textarea").count() > 0:
                break
            page.wait_for_timeout(400)
        if page.locator(".xterm-helper-textarea").count() == 0:
            raise CodeServerError("???? code-server ?? (xterm ???)")

        self._focus_xterm()
        smoke = f"RIRS_SMOKE_{int(time.time())}"
        self._send_keys(f"echo {smoke}")
        ok = self._wait_xterm_contains(smoke, timeout=25)
        if not ok:
            self._focus_xterm()
            self._send_keys(f"echo {smoke}")
            ok = self._wait_xterm_contains(smoke, timeout=25)
        if not ok:
            try:
                shot = Path.home() / ".rirs" / "terminal_fail.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            # xterm ?????????? rows ??????
            has = page.evaluate("() => !!document.querySelector('.xterm-helper-textarea')")
            if not has:
                raise CodeServerError("????????????")
        self._terminal_ready = True



    def _focus_xterm(self) -> None:
        page = self._require_page()
        try:
            page.locator(".xterm").last.click(timeout=2000, force=True)
        except Exception:
            pass
        page.evaluate(
            """() => {
              const nodes = document.querySelectorAll('.xterm-helper-textarea');
              const el = nodes[nodes.length - 1];
              if (!el) return false;
              el.focus();
              return true;
            }"""
        )

    def _send_keys(self, text: str) -> None:
        page = self._require_page()
        page.keyboard.press("Escape")
        page.wait_for_timeout(80)
        self._focus_xterm()
        page.keyboard.press("Control+C")
        page.wait_for_timeout(80)
        page.keyboard.press("Control+C")
        page.wait_for_timeout(120)
        # type ? xterm ?????????
        if len(text) < 180:
            page.keyboard.type(text, delay=10)
        else:
            try:
                page.evaluate("async (t) => { try { await navigator.clipboard.writeText(t); } catch(e){} }", text)
                page.keyboard.press("Control+V")
            except Exception:
                page.keyboard.type(text, delay=5)
        page.keyboard.press("Enter")


    def _xterm_text(self) -> str:
        page = self._require_page()
        try:
            return page.evaluate(
                """() => {
                  const rows = Array.from(document.querySelectorAll('.xterm-rows'));
                  if (!rows.length) return '';
                  return rows.map(r => r.innerText || '').join(String.fromCharCode(10));
                }"""
            ) or ""
        except Exception:
            return ""

    def _wait_xterm_contains(self, needle: str, timeout: float = 30.0) -> bool:
        page = self._require_page()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self._xterm_text():
                return True
            page.wait_for_timeout(400)
        return False




    def run(
        self,
        command: str,
        *,
        wait: float = 0.6,
        marker: Optional[str] = None,
        timeout: float = 120.0,
    ) -> str:
        """??????????+??????????? xterm ???"""
        try:
            out = self.run_to_file(command, timeout=timeout)
            if out.strip():
                return out.strip()
        except Exception:
            pass
        # fallback: inline markers in xterm
        page = self._require_page()
        if not self._terminal_ready:
            self.focus_terminal()
        token = marker or ("RIRS%d" % int(time.time() * 1000))
        start = "__START_%s__" % token
        end = "__END_%s__" % token
        line = "echo %s; %s; echo %s" % (start, command, end)
        self._send_keys(line)
        deadline = time.time() + timeout
        text = ""
        while time.time() < deadline:
            page.wait_for_timeout(int(max(wait, 0.3) * 1000))
            text = self._xterm_text()
            if start in text and end in text:
                body = text.split(start, 1)[1].split(end, 1)[0]
                return body.strip()
        return (text or "")[-4000:]

    
    def read_remote_text(self, remote_path: str, timeout: float = 20.0) -> str:
        """Copy remote file to a unique snapshot, open it, read Monaco text."""
        page = self._require_page()
        path = self._abs(remote_path)
        if not self._terminal_ready:
            self.focus_terminal()
        token = "rd%d" % int(time.time() * 1000)
        snap = "/tmp/rirs_read_%s.txt" % token
        done = "__RDONE_%s__" % token
        # Fresh unique snapshot avoids stale Monaco tabs.
        self._send_keys(
            "cp %s %s 2>/dev/null || cat %s > %s; echo %s"
            % (shlex.quote(path), shlex.quote(snap), shlex.quote(path), shlex.quote(snap), done)
        )
        self._wait_xterm_contains(done, timeout=min(20.0, timeout))
        page.wait_for_timeout(300)
        try:
            page.keyboard.press("Control+K")
            page.wait_for_timeout(80)
            page.keyboard.press("Control+W")
            page.wait_for_timeout(200)
        except Exception:
            pass
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        page.keyboard.press("Control+P")
        page.wait_for_timeout(400)
        page.keyboard.type(snap, delay=8)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        deadline = time.time() + timeout
        text = ""
        js = (
            "() => {"
            " const lines = [...document.querySelectorAll('.view-lines .view-line')]"
            ".map(e => e.innerText || '');"
            " if (lines.length) return lines.join(String.fromCharCode(10));"
            " const ed = document.querySelector('.monaco-editor .view-lines');"
            " return ed ? ed.innerText : '';"
            "}"
        )
        while time.time() < deadline:
            page.wait_for_timeout(350)
            text = page.evaluate(js) or ""
            if text.strip():
                return text
        return text

    def run_to_file(self, command: str, *, out_file: Optional[str] = None, timeout: float = 180.0) -> str:
        """Run command via a remote script file, capture stdout/stderr, read back."""
        if not self._terminal_ready:
            self.focus_terminal()
        token = "R%d" % int(time.time() * 1000)
        out_file = self._abs(out_file or f"/tmp/rirs_out_{token}.txt")
        parent = str(Path(out_file).parent).replace("\\", "/")
        script_path = f"/tmp/rirs_cmd_{token}.sh"
        # Write command as a script to avoid quote breakage when typing into xterm.
        script_body = (
            "#!/bin/bash\n"
            "set +e\n"
            "mkdir -p %s\n"
            "{\n"
            "%s\n"
            "} > %s 2>&1\n"
            "echo __RIRS_DONE_%s__\n"
        ) % (parent, command, out_file, token)
        self.write_text(script_path, script_body)
        self._send_keys("chmod +x %s && bash %s; echo __RIRS_DONE_%s__" % (
            shlex.quote(script_path), shlex.quote(script_path), token
        ))
        wait_t = min(max(float(timeout), 15.0), 90.0)
        self._wait_xterm_contains("__RIRS_DONE_%s__" % token, timeout=wait_t)
        page = self._require_page()
        page.wait_for_timeout(500)
        return self.read_remote_text(out_file, timeout=min(30.0, wait_t))



    def mkdir(self, remote_path: str) -> None:
        self.run(f"mkdir -p {shlex.quote(self._abs(remote_path))}")

    def write_bytes(self, remote_path: str, content: bytes) -> None:
        path = self._abs(remote_path)
        if not self._terminal_ready:
            self.focus_terminal()
        b64 = base64.b64encode(content).decode("ascii")
        parent = str(Path(path).parent).replace("\\", "/")
        if len(b64) <= 3000:
            self._send_keys(
                "mkdir -p %s; printf %s > %s.b64 && base64 -d %s.b64 > %s && rm -f %s.b64 && ls -l %s"
                % (
                    shlex.quote(parent),
                    shlex.quote(b64),
                    shlex.quote(path),
                    shlex.quote(path),
                    shlex.quote(path),
                    shlex.quote(path),
                    shlex.quote(path),
                )
            )
            time.sleep(0.5)
            return
        self._send_keys("mkdir -p %s; : > %s.b64" % (shlex.quote(parent), shlex.quote(path)))
        chunk = 2800
        for i in range(0, len(b64), chunk):
            part = b64[i : i + chunk]
            self._send_keys("printf %s >> %s.b64" % (shlex.quote(part), shlex.quote(path)))
            time.sleep(0.2)
        self._send_keys(
            "base64 -d %s.b64 > %s && rm -f %s.b64 && ls -l %s"
            % (shlex.quote(path), shlex.quote(path), shlex.quote(path), shlex.quote(path))
        )
        time.sleep(0.6)

    def write_text(self, remote_path: str, content: str, *, executable: bool = False) -> None:
        self.write_bytes(remote_path, content.encode("utf-8"))
        if executable:
            self._send_keys(f"chmod +x {shlex.quote(self._abs(remote_path))}")


    def upload_via_explorer(self, local_paths: Sequence[str | Path]) -> None:
        """???? VS Code ??????? file input ???"""
        page = self._require_page()
        paths = [str(Path(p).resolve()) for p in local_paths]
        for pth in paths:
            if not Path(pth).exists():
                raise CodeServerError(f"???????: {pth}")
        # ???? input
        inputs = page.locator('input[type="file"]')
        if inputs.count() == 0:
            # ??????????
            try:
                page.keyboard.press("Control+Shift+P")
                page.wait_for_timeout(400)
                page.keyboard.type("File: Upload", delay=15)
                page.wait_for_timeout(400)
                page.keyboard.press("Enter")
                page.wait_for_timeout(800)
            except Exception:
                pass
        inputs = page.locator('input[type="file"]')
        if inputs.count() == 0:
            raise CodeServerError("??? file input??? UI ??")
        inputs.last.set_input_files(paths)
        page.wait_for_timeout(1500)

    def upload_file(self, local_path: str | Path, remote_path: Optional[str] = None) -> str:
        local_path = Path(local_path)
        if not local_path.is_file():
            raise CodeServerError(f"???????: {local_path}")
        if remote_path is None:
            remote_path = f"{self.workdir}/{local_path.name}"
        remote_path = self._abs(remote_path)
        size = local_path.stat().st_size
        # ?? UI ????????/data/user????????????????
        try:
            self.upload_via_explorer([local_path])
            if Path(remote_path).name == local_path.name and remote_path.rstrip("/").endswith(local_path.name):
                # ???? mv ??????????
                try:
                    if not self._terminal_ready:
                        self.focus_terminal()
                    default_dst = f"{self.workdir}/{local_path.name}"
                    if self._abs(default_dst) != remote_path:
                        self._send_keys(f"mkdir -p {shlex.quote(str(Path(remote_path).parent).replace(chr(92), '/'))} && mv -f {shlex.quote(default_dst)} {shlex.quote(remote_path)}")
                except Exception:
                    pass
                return remote_path
        except Exception:
            pass
        if size > 8 * 1024 * 1024:
            raise CodeServerError(
                f"??? {local_path.name} ??({size} bytes)??? upload_paths() ???? wget/git?"
            )
        self.write_bytes(remote_path, local_path.read_bytes())
        return remote_path

    def upload_paths(
        self,
        paths: Sequence[str | Path],
        *,
        remote_dir: Optional[str] = None,
        remote_archive_name: str = "upload_bundle.tar.gz",
    ) -> str:
        remote_dir = self._abs(remote_dir or self.workdir)
        paths = [Path(p) for p in paths]
        for p in paths:
            if not p.exists():
                raise CodeServerError(f"?????: {p}")
        with tempfile.TemporaryDirectory(prefix="rirs_up_") as td:
            tar_path = Path(td) / remote_archive_name
            with tarfile.open(tar_path, "w:gz") as tar:
                for p in paths:
                    tar.add(p, arcname=p.name)
            size = tar_path.stat().st_size
            if size > 40 * 1024 * 1024:
                raise CodeServerError(f"??????? ({size} bytes > 40MB)?")
            remote_tar = f"{remote_dir}/{remote_archive_name}"
            self.write_bytes(remote_tar, tar_path.read_bytes())
            return self.run(
                f"mkdir -p {shlex.quote(remote_dir)} && "
                f"tar -xzf {shlex.quote(remote_tar)} -C {shlex.quote(remote_dir)} && "
                f"rm -f {shlex.quote(remote_tar)} && ls -la {shlex.quote(remote_dir)}",
                timeout=300,
            )

    def nvidia_smi(self) -> str:
        return self.run("nvidia-smi", timeout=60)

    def pick_free_gpu(
        self,
        *,
        max_util: int = 10,
        max_mem_mb: int = 1024,
        prefer: Optional[list[int]] = None,
    ) -> Optional[int]:
        raw = self.run(
            "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,name "
            "--format=csv,noheader,nounits",
            timeout=60,
        )
        gpus: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("__"):
                continue
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 4:
                continue
            try:
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "util": int(float(parts[1])),
                        "mem_used": int(float(parts[2])),
                        "mem_total": int(float(parts[3])),
                        "name": parts[4] if len(parts) > 4 else "",
                    }
                )
            except ValueError:
                continue
        free = [g for g in gpus if g["util"] <= max_util and g["mem_used"] <= max_mem_mb]
        if prefer:
            for idx in prefer:
                for g in free:
                    if g["index"] == idx:
                        return idx
        if free:
            free.sort(key=lambda g: (g["util"], g["mem_used"]))
            return int(free[0]["index"])
        return None

    def wait_for_free_gpu(
        self,
        *,
        poll_seconds: int = 1800,
        max_wait: float = 6 * 3600,
        max_util: int = 10,
        max_mem_mb: int = 1024,
    ) -> int:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            gpu = self.pick_free_gpu(max_util=max_util, max_mem_mb=max_mem_mb)
            if gpu is not None:
                return gpu
            self.nvidia_smi()
            time.sleep(poll_seconds)
        raise CodeServerError("???? GPU ??")


    def new_terminal(self, *, name=None):
        """新建一个 code-server 终端并聚焦。"""
        page = self._require_page()
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
        page.keyboard.press("Control+Shift+P")
        page.wait_for_timeout(450)
        page.keyboard.type("Terminal: Create New Terminal", delay=15)
        page.wait_for_timeout(400)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        try:
            page.wait_for_selector(".xterm-helper-textarea", state="attached", timeout=15000)
        except Exception as exc:
            raise CodeServerError("新建终端失败: %s" % exc) from exc
        self._focus_xterm()
        self._terminal_ready = True
        if name:
            self._send_keys("echo RIRS_TERM_%s" % name)

    def focus_existing_terminal_panel(self):
        page = self._require_page()
        page.keyboard.press("Control+J")
        page.wait_for_timeout(300)
        page.keyboard.press("Control+`")
        page.wait_for_timeout(500)
        self._focus_xterm()
        self._terminal_ready = True

    def ensure_tmux(self, *, install: bool = True, timeout: float = 180.0) -> str:
        """Ensure tmux is available. Prefer install when missing; never hang forever."""
        if not self._terminal_ready:
            self.focus_terminal()
        check = self.run_to_file(
            "command -v tmux >/dev/null 2>&1 && tmux -V && echo HAS_TMUX=1 || echo HAS_TMUX=0",
            out_file="/data/user/rirs_trial/has_tmux.txt",
            timeout=30,
        ) or ""
        if "HAS_TMUX=1" in check:
            return check
        if not install:
            return check + "\nINSTALL_SKIPPED=1"
        # Non-interactive install with hard timeout to avoid sudo password hangs.
        install_cmd = (
            "export DEBIAN_FRONTEND=noninteractive; "
            "if command -v tmux >/dev/null 2>&1; then tmux -V; echo HAS_TMUX=1; exit 0; fi; "
            "echo TRY_INSTALL_TMUX; "
            "if [ \"$(id -u)\" = \"0\" ]; then "
            "  (timeout 90 apt-get update -qq || true); "
            "  timeout 120 apt-get install -y -qq tmux || true; "
            "elif command -v sudo >/dev/null 2>&1; then "
            "  (timeout 90 sudo -n apt-get update -qq || true); "
            "  timeout 120 sudo -n apt-get install -y -qq tmux || true; "
            "else "
            "  echo NO_ROOT_OR_PASSWORDLESS_SUDO; "
            "fi; "
            "command -v tmux >/dev/null 2>&1 && tmux -V && echo HAS_TMUX=1 || echo HAS_TMUX=0; "
            "echo INSTALL_DONE"
        )
        out = self.run_to_file(
            install_cmd,
            out_file="/data/user/rirs_trial/tmux_install.txt",
            timeout=timeout,
        ) or ""
        return out

    def tmux_start(self, command, *, session="rirs-train", cwd=None, log_file="/data/user/rirs_trial/tmux_train.log"):
        if not self._terminal_ready:
            self.focus_terminal()
        cwd = self._abs(cwd or self.workdir)
        log_file = self._abs(log_file)
        parent = str(Path(log_file).parent).replace("\\", "/")
        inner = "cd %s && ( %s ) > %s 2>&1" % (shlex.quote(cwd), command, shlex.quote(log_file))
        prep = (
            "tmux has-session -t %s 2>/dev/null && tmux kill-session -t %s || true; "
            "mkdir -p %s; "
            "tmux new-session -d -s %s bash -lc %s; "
            "sleep 1; tmux ls; echo TMUX_STARTED; "
            "tmux capture-pane -t %s -p 2>/dev/null | tail -n 20 || true"
        ) % (
            shlex.quote(session),
            shlex.quote(session),
            shlex.quote(parent),
            shlex.quote(session),
            shlex.quote(inner),
            shlex.quote(session),
        )
        return self.run_to_file(prep, out_file="/data/user/rirs_trial/tmux_start.txt", timeout=90)

    def tmux_status(self, session="rirs-train"):
        cmd = (
            "tmux ls 2>&1 || true; "
            "tmux has-session -t %s 2>/dev/null && echo HAS_SESSION=1 || echo HAS_SESSION=0; "
            "tmux capture-pane -t %s -p 2>/dev/null | tail -n 40 || true; "
            "wc -l /data/user/rirs_trial/tmux_train.log 2>/dev/null || true; "
            "tail -n 20 /data/user/rirs_trial/tmux_train.log 2>/dev/null || true"
        ) % (shlex.quote(session), shlex.quote(session))
        return self.run_to_file(cmd, out_file="/data/user/rirs_trial/tmux_status.txt", timeout=60)

    def tmux_stop(self, session="rirs-train"):
        return self.run_to_file(
            "tmux kill-session -t %s 2>&1 || true; tmux ls 2>&1 || echo NO_SESSIONS" % shlex.quote(session),
            out_file="/data/user/rirs_trial/tmux_stop.txt",
            timeout=30,
        )

    def long_job_start(self, command, *, session="rirs-train", cwd=None, log_file="/data/user/rirs_trial/tmux_train.log", prefer_tmux=True, install_tmux=True):
        """Long job: try install+tmux first, else nohup/setsid launcher."""
        if not self._terminal_ready:
            self.focus_terminal()
        cwd = self._abs(cwd or self.workdir)
        log_file = self._abs(log_file)
        parent = str(Path(log_file).parent).replace("\\", "/")
        has = ""
        if prefer_tmux:
            has = self.ensure_tmux(install=install_tmux)
        if prefer_tmux and "HAS_TMUX=1" in (has or ""):
            out = self.tmux_start(command, session=session, cwd=cwd, log_file=log_file)
            return "MODE=tmux\n" + (out or "")
        pid_file = parent + "/long_job_" + session + ".pid"
        hb_file = parent + "/long_job_" + session + ".hb"
        launcher = parent + "/long_job_" + session + "_start.sh"
        inner = (
            "echo START_TS=$(date) >> {hb}; "
            "{cmd}; "
            "ec=$?; "
            "echo END_TS=$(date) ec=$ec >> {hb}; "
            "echo END_TS=$(date) ec=$ec >> {log}"
        ).format(hb=hb_file, cmd=command, log=log_file)
        script = "\n".join(
            [
                "#!/bin/bash",
                "set +e",
                "mkdir -p " + parent,
                "cd " + cwd + " || exit 1",
                ": > " + hb_file,
                ": > " + log_file,
                "nohup setsid bash -c " + shlex.quote(inner) + " > " + log_file + " 2>&1 < /dev/null &",
                "echo $! > " + pid_file,
                "sleep 2",
                "echo NOHUP_PID=$(cat " + pid_file + ")",
                "if kill -0 $(cat " + pid_file + ") 2>/dev/null; then echo ALIVE=1; else echo ALIVE=0; fi",
                "ps -p $(cat " + pid_file + ") -o pid,etime,cmd 2>/dev/null || true",
                "wc -l " + log_file + " 2>/dev/null || true",
                "tail -n 40 " + log_file + " 2>/dev/null || true",
                "echo MODE=nohup",
                "",
            ]
        )
        self.write_text(launcher, script)
        self._send_keys("chmod +x %s" % shlex.quote(launcher))
        time.sleep(0.4)
        out = self.run_to_file(
            "bash %s" % shlex.quote(launcher),
            out_file="/data/user/rirs_trial/nohup_start.txt",
            timeout=60,
        )
        note = ""
        if prefer_tmux and "HAS_TMUX=1" not in (has or ""):
            note = "TMUX_UNAVAILABLE_FALLBACK_NOHUP=1\n"
        return "MODE=nohup\n" + note + (out or "")

    def long_job_status(self, session="rirs-train", log_file="/data/user/rirs_trial/tmux_train.log"):
        log_file = self._abs(log_file)
        parent = str(Path(log_file).parent).replace("\\", "/")
        pid_file = parent + "/long_job_" + session + ".pid"
        hb_file = parent + "/long_job_" + session + ".hb"
        cmd = (
            "echo ---tmux---; tmux ls 2>&1 || true; "
            "tmux has-session -t %s 2>/dev/null && echo HAS_SESSION=1 || echo HAS_SESSION=0; "
            "echo ---pid---; cat %s 2>/dev/null || true; "
            "PID=$(cat %s 2>/dev/null || true); "
            "if [ -n \"$PID\" ]; then ps -p \"$PID\" -o pid,etime,cmd 2>/dev/null || echo PID_DEAD; else echo NO_PID; fi; "
            "echo ---hb---; cat %s 2>/dev/null || true; "
            "echo ---log---; wc -l %s 2>/dev/null || true; tail -n 25 %s 2>/dev/null || true"
        ) % (
            shlex.quote(session),
            shlex.quote(pid_file),
            shlex.quote(pid_file),
            shlex.quote(hb_file),
            shlex.quote(log_file),
            shlex.quote(log_file),
        )
        return self.run_to_file(cmd, out_file="/data/user/rirs_trial/long_job_status.txt", timeout=60)


    def long_job_stop(self, session="rirs-train", log_file="/data/user/rirs_trial/tmux_train.log"):
        log_file = self._abs(log_file)
        parent = str(Path(log_file).parent).replace("\\", "/")
        pid_file = parent + "/long_job_" + session + ".pid"
        cmd = (
            "tmux kill-session -t %s 2>/dev/null || true; "
            "PID=$(cat %s 2>/dev/null || true); "
            "if [ -n \"$PID\" ]; then kill \"$PID\" 2>/dev/null || true; fi; "
            "echo STOPPED; tmux ls 2>&1 || echo NO_TMUX_SESSIONS"
        ) % (shlex.quote(session), shlex.quote(pid_file))
        return self.run_to_file(cmd, out_file="/data/user/rirs_trial/long_job_stop.txt", timeout=30)

    def setup_venv(
        self,
        venv_path: str = "/data/user/.venv",
        *,
        requirements: Optional[str | Path] = None,
        pip_packages: Optional[Sequence[str]] = None,
        python_bin: str = "python3",
    ) -> str:
        """Create project venv and install deps. Missing packages are installed into this venv only."""
        venv_path = self._abs(venv_path)
        cmds = [
            f"{python_bin} -m venv {shlex.quote(venv_path)} || true",
            f"source {shlex.quote(venv_path)}/bin/activate && python -m pip install -U pip setuptools wheel",
        ]
        if requirements:
            req = Path(requirements)
            remote_req = f"{self.workdir}/requirements.rirs.txt"
            if req.exists():
                self.upload_file(req, remote_req)
            else:
                self.write_text(remote_req, str(requirements))
            cmds.append(
                f"source {shlex.quote(venv_path)}/bin/activate && pip install -r {shlex.quote(remote_req)}"
            )
        if pip_packages:
            pkgs = " ".join(shlex.quote(p) for p in pip_packages)
            cmds.append(f"source {shlex.quote(venv_path)}/bin/activate && pip install {pkgs}")
        return self.run(" && ".join(cmds), timeout=1800)

    def ensure_pip_packages(
        self,
        packages: Sequence[str],
        *,
        venv_path: str = "/data/user/.venv",
    ) -> str:
        """Install any missing pip packages into the project venv (缺什么装什么)."""
        if not packages:
            return "NO_PACKAGES"
        venv_path = self._abs(venv_path)
        # Ensure venv exists first
        self.run_to_file(
            f"test -x {shlex.quote(venv_path)}/bin/python || python3 -m venv {shlex.quote(venv_path)}",
            out_file="/data/user/rirs_trial/venv_ensure.txt",
            timeout=120,
        )
        results = []
        for pkg in packages:
            # package name may be 'opencv-python' while import is cv2; agent should pass pip name.
            name = pkg.strip()
            if not name:
                continue
            cmd = (
                f"source {shlex.quote(venv_path)}/bin/activate && "
                f"python -m pip show {shlex.quote(name)} >/dev/null 2>&1 && echo HAS_{name}=1 || "
                f"(python -m pip install {shlex.quote(name)} && echo INSTALLED_{name}=1)"
            )
            out = self.run_to_file(
                cmd,
                out_file="/data/user/rirs_trial/pip_%s.txt" % ''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in name),
                timeout=900,
            )
            results.append(out or "")
        return "\n".join(results)

    def start_training(
        self,
        command: str,
        *,
        gpu: Optional[int] = None,
        log_file: str = "/data/user/train.log",
        venv_path: Optional[str] = "/data/user/.venv",
        cwd: Optional[str] = None,
    ) -> str:
        log_file = self._abs(log_file)
        cwd = self._abs(cwd or self.workdir)
        env_prefix = f"CUDA_VISIBLE_DEVICES={gpu} " if gpu is not None else ""
        activate = f"source {shlex.quote(self._abs(venv_path))}/bin/activate && " if venv_path else ""
        full = (
            f"cd {shlex.quote(cwd)} && {activate}{env_prefix}nohup bash -lc {shlex.quote(command)} "
            f"> {shlex.quote(log_file)} 2>&1 & echo $!"
        )
        return self.run(full, timeout=60)

    def _abs(self, path: str) -> str:
        path = path.replace("\\", "/")
        if path.startswith("/"):
            return path
        return f"{self.workdir}/{path}"


def open_codeserver(url: str, **kwargs: Any) -> CodeServerSession:
    sess = CodeServerSession(url, **kwargs)
    sess.open()
    return sess
