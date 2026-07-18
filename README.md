# RIRS Experiment Skill (Codex)

Codex skill for operating the Wuhan University **RIRS** deep-learning cloud platform **without SSH** (Web + API + Playwright code-server).

## Install

1. Clone or copy this folder to:
   - Windows: `%USERPROFILE%\.codex\skills\rirs-experiment-agent`
   - macOS/Linux: `~/.codex/skills/rirs-experiment-agent`

2. Python deps:

```bash
pip install -r requirements.txt
playwright install chromium
```

3. Config (local only, do **not** commit):

```bash
cp config.example.yaml config.yaml
# edit username / password
```

4. Campus network required. Platform: `http://202.114.114.19:8001`

## Usage (Codex)

Tell the agent, for example:

```text
Use RIRS experiment agent:
- goal: train XXX
- code: D:/research/xxx
- data: D:/research/xxx/data
- cmd: python train.py
```

Or CLI:

```powershell
$py = "python"   # or your Anaconda python
$root = "C:\Users\c6324\.codex\skills\rirs-experiment-agent"
& $py "$root\scripts\rirs_cli.py" --config "$root\config.yaml" login
& $py "$root\scripts\rirs_cli.py" --config "$root\config.yaml" containers
```

## Layout

```text
SKILL.md                 # Codex skill instructions
config.example.yaml      # template (safe to commit)
config.yaml              # local secrets (gitignored)
requirements.txt
scripts/                 # API + Playwright automation
references/              # API & workflow notes
agents/                  # Codex agent metadata
```

## Security

- Never commit `config.yaml` or real passwords.
- Prefer a **private** repo if it might ever contain campus credentials.
- Token cache default: `~/.rirs/token.json`

## Notes

- No SSH; code-server via browser automation.
- Prefer project venv; install missing pip packages into that venv.
- Prefer tmux for long jobs (auto-install when possible); fallback nohup.
- Long jobs / large uploads: poll about every 15 minutes.
