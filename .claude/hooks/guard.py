#!/usr/bin/env python3
"""PreToolUse guard for AFDA Claude Code sessions (stdlib only).

Always: deny destructive, out-of-role, exfiltrating or system-changing actions.
Unattended runs (AFDA_AUTONOMOUS=1): explicitly allow shell commands whose every
segment starts with an allowlisted program, and edits inside the project or its
worktrees; deny everything else with a reason, because `claude -p` cannot prompt.
Interactive sessions: allowed actions get no decision, so normal prompts apply.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SHELL_TOOLS = {"Bash", "PowerShell"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PROTECTED = ("data/external/", "data/captures/", "data/derived/peer_reviews/", "data/derived/experiment_packets/inbox/",
             "data/derived/labels/human/", "baseline/", ".git/")
PROTECTED_FILES = ("overview.md", "evaluation.md", "data_description.md", "code submission.html", "src/baseline_inference.py",
                   "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv",
                   "data/derived/comma_subset_v1/s23_capture_ready.csv")
SELF = (".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/", "configs/agent_policy.json",
        "configs/local-exchange.json", "configs/local-agent-policy.json", "claude.local.md")
SECRETS = re.compile(r"\.credentials\.json|syncthing/(config\.xml|cert\.pem|key\.pem|https-)|\bid_(rsa|ed25519)\b|(^|[\s/\"'])\.env(\s|$|[\"'])")
TOKEN = (r"(data/external|data/captures|data/derived/peer_reviews|data/derived/experiment_packets/inbox|data/derived/labels/human"
         r"|baseline(?=[/\s\"']|$)|\.git(?=[/\s\"']|$)|overview\.md|evaluation\.md|data_description\.md|src/baseline_inference\.py)")
FILE_TOKEN = r"(stage2_review_with_metadata\.csv|s23_capture_ready\.csv|afda_exchange)"
SELF_TOKEN = r"(\.claude/settings|\.claude/hooks|agent_policy\.json|local-exchange\.json|local-agent-policy\.json|claude\.local\.md)"
WRITE_VERB = re.compile(r"^(rm|rmdir|del|erase|rd|remove-item|ri|mv|move|move-item|mi|rename-item|ren|rni|set-content|sc|add-content|ac"
                        r"|out-file|clear-content|clc|new-item|ni|tee|tee-object|truncate|shred|attrib|export-csv|unlink|ln|cipher|chmod|icacls)$")
PY_WRITE = re.compile(r"rmtree|os\.(remove|unlink|rmdir|rename|replace)|\.unlink\(|\.rmdir\(|\.write_(text|bytes)\(|\.rename\(|\.replace\("
                      r"|open\([^)]*[\"'][wax]")
ALWAYS_DENY = [
    (r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*(\s--force(-with-lease)?\b|\s-f\b|\s--mirror\b|\s--delete\b|\s-d\b|\s\+\S|\s:\S)",
     "Force/delete pushes are forbidden. Integrate with a normal fast-forward push."),
    (r"\bgit\b[^;&|\n]*\b(reset\s+--hard|clean\s+-\w*[fdx]|checkout\s+(-f\b|--\s+\.|\.(\s|$))|restore\s+(\S+\s+)*\.(\s|$)"
     r"|stash\s+(drop|clear)|branch\s+(-d|--delete)\b|filter-branch|filter-repo|update-ref\s+-d|reflog\s+expire|gc\s+--prune"
     r"|remote\s+(add|set-url|remove|rm|rename)|config\s+--(global|system))",
     "History-destroying or remote/global git changes are forbidden. Make a new commit instead."),
    (r"--dangerously-skip-permissions|bypasspermissions|--allow-dangerously", "Permission bypass is forbidden."),
    (r"(^|[\s;&|(])(shutdown|restart-computer|stop-computer|diskpart|bcdedit|schtasks|register-scheduledtask|unregister-scheduledtask"
     r"|set-scheduledtask|netsh|set-executionpolicy|set-mppreference|add-mppreference|powercfg|vssadmin|wmic|bitsadmin|runas|cmdkey"
     r"|certutil|winget|choco|scoop|takeown)(\.exe)?\b|\breg(\.exe)?\s+(add|delete|import|load|copy)\b|\b(set|new|remove)-itemproperty\b"
     r"|\bsc(\.exe)?\s+(create|delete|config|stop)\b|\b(stop|set|new)-service\b|-verb\s+runas|\bnet\s+(user|localgroup)\b"
     r"|\bformat(\.com)?\s+[a-z]:|\bnpm\s+(i|install)\s+(-g|--global)\b",
     "System, service, registry, scheduler, power and package-manager changes are forbidden for agents."),
    (r"\b(taskkill|stop-process|kill|pkill|killall)\b.*\b(syncthing|claude|node|pythonw|powershell)\b|\bspps\b",
     "Do not kill the exchange, loop or Claude processes. Cancel jobs with `python -m agent_bridge job cancel <id>`."),
    (r"\bcurl\b[^;&|\n]*(--upload-file|--data|--form|-x\s*(post|put|patch)|--request\s+(post|put|patch))"
     r"|\b(invoke-webrequest|invoke-restmethod|iwr|irm)\b[^;&|\n]*(-method\s+(post|put|patch)|-infile|-body)"
     r"|\bwget\b[^;&|\n]*--post|(^|[\s;&|(])(scp|sftp|ftp|rsync|rclone|azcopy|gsutil|ncat|nc)\b|\baws\s+s3\b|\b(huggingface-cli|hf)\s+upload\b"
     r"|requests\.(post|put|patch)\(|urlopen\([^)]*data=",
     "Uploading or posting data to external services is forbidden (data stays on the two PCs)."),
]


def norm(text):
    text = str(text).replace("\\", "/").lower()
    return re.sub(r"(^|[\s\"'=(])/([a-z])/", r"\1\2:/", text)


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()


def local_config(project):
    try:
        return json.loads((project / "configs/local-exchange.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def segments(command):
    """Split a shell line into simple commands; include $(...) bodies."""
    parts = re.split(r"\|\||&&|[;|\n]|(?<![>&0-9])&(?![>&])", command)
    parts += re.findall(r"\$\(([^()]*)\)", command)
    return [p.strip() for p in parts if p.strip()]


PREFIXES = re.compile(r"^((\w+=\S*\s+)|(env|time|nohup|exec|command|builtin|sudo)\s+|timeout\s+(-\S+\s+)*\d+\S*\s+|[({!]\s*|&\s*|\.\s+(?=[\"']))+")
ALLOWED_PROGRAMS = {
    "python", "python3", "py", "pythonw", "git", "ls", "dir", "cat", "type", "head", "tail", "wc", "grep", "egrep", "rg", "findstr",
    "find", "sort", "uniq", "cut", "awk", "sed", "tr", "diff", "cmp", "comm", "sha256sum", "sha1sum", "md5sum", "du", "df", "stat",
    "file", "echo", "printf", "pwd", "cd", "pushd", "popd", "mkdir", "touch", "cp", "mv", "rm", "rmdir", "date", "sleep", "true",
    "false", "test", "[", "[[", "which", "where", "whoami", "hostname", "uname", "nproc", "free", "nvidia-smi", "ffprobe", "ffmpeg",
    "tar", "unzip", "zip", "7z", "jq", "xargs", "basename", "dirname", "realpath", "readlink", "tree", "export", "set", "unset",
    "wait", "tee", "powershell", "pwsh", "cmd", "copy", "ln", "column", "seq", "yes", "od", "xxd", "less", "more", "sum", "exit",
    "if", "then", "else", "elif", "fi", "for", "do", "done", "while", "until", "case", "esac", "in", "function", "return", "local",
    "read", "shift", "break", "continue", "declare", "printenv", "cygpath", "curl", "wget",
}
PS_VERBS = {"get", "test", "select", "where", "foreach", "sort", "measure", "group", "format", "out", "convertto", "convertfrom",
            "import", "export", "join", "split", "resolve", "new", "copy", "move", "remove", "rename", "push", "pop", "write",
            "compare", "expand", "compress", "add", "tee", "wait", "clear"}
PS_ALLOWED = {"set-location", "set-content", "set-variable", "start-sleep", "invoke-webrequest", "invoke-restmethod", "sl", "cd",
              "gci", "gc", "ls", "select-string", "measure-object", "foreach-object", "where-object", "%", "?"}
PS_KEYWORDS = {"if", "else", "elseif", "foreach", "for", "while", "do", "try", "catch", "finally", "switch", "return", "param",
               "function", "begin", "process", "end", "exit", "break", "continue", "throw", "}", "{", ")", "(", "-not"}


def program_ok(segment):
    body = PREFIXES.sub("", segment).strip()
    if not body:
        return True, None
    first = body.split()[0].strip("\"'`")
    if first[:1] in {"$", "[", "@", "#", "-", "'", '"'} or first[:1].isdigit() or first in PS_KEYWORDS:
        return True, None
    name = first.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    if name in ALLOWED_PROGRAMS or name in PS_ALLOWED:
        return True, None
    if "-" in name and name.split("-", 1)[0] in PS_VERBS:
        return True, None
    return False, name


def protected_path(path_text, project, exchange_root):
    """Return a reason if the (normalized) absolute or relative path is protected."""
    p = norm(path_text)
    root = norm(project) + "/"
    if exchange_root and p.startswith(norm(exchange_root).rstrip("/") + "/"):
        return "The exchange folders are written only by `python -m agent_bridge publish`."
    rel = p[len(root):] if p.startswith(root) else (p[2:] if p.startswith("./") else p)
    if rel.startswith(PROTECTED) or rel in PROTECTED_FILES:
        return f"{rel} is protected source data, human labels, peer input or git internals. Write derived output under data/derived/ instead."
    return None


CASE_DENY = [(r"\bcurl\b[^;&|\n]*\s-[a-zA-Z]*[TdF]", "curl uploads (-T/-d/-F) are forbidden; data stays on the two PCs.")]


def check_shell(command, role, autonomous, project, exchange_root, cwd):
    text = norm(command)
    for pattern, reason in ALWAYS_DENY:
        if re.search(pattern, text):
            return "deny", reason
    for pattern, reason in CASE_DENY:
        if re.search(pattern, str(command)):
            return "deny", reason
    if SECRETS.search(text):
        return "deny", "Credential and Syncthing key files are off limits."
    if autonomous and (re.search(r"(setup_claude_agents|setup_exchange|start_exchange|stop_exchange|bootstrap)\.ps1", text)
                       or re.search(r"agent_bridge\b[^;&|\n]*\s(loop|pause|resume|stop|job-run|probe)\b", text)
                       or re.search(r"exchange_bridge\b[^;&|\n]*\s(worker|stop-transport|pair|configure)\b", text)):
        return "deny", "Service setup and loop control belong to the human operator; record the need in human_actions."
    if role == "pro360" and (re.search(r"harness\b.*\bexecute\b.*--kind\s+gpu", text) or re.search(r"agent_bridge\b.*\bjob\s+start\b.*--kind\s+gpu", text)):
        return "deny", "GPU work belongs to Ultra. On Pro use --kind cpu, or send Ultra a request packet."
    if re.search(r"\bpip3?(\.exe)?\b[^;&|\n]*\binstall\b|-m\s+pip\s+install", text):
        for seg in segments(text):
            if re.search(r"\bpip3?(\.exe)?\b.*\binstall\b|-m\s+pip\s+install", seg) and (".venv-" not in seg or "--user" in seg):
                return "deny", "Install packages only into the role venv: .venv-<role>/Scripts/python.exe -m pip install <pkg>==<ver>."
    project_norm = norm(project)
    for seg in segments(text):
        words = PREFIXES.sub("", seg).split()
        verb = words[0].strip("\"'").rsplit("/", 1)[-1] if words else ""
        verb = re.sub(r"\.(exe|cmd)$", "", verb)
        for target in re.findall(r"(?<![0-9&])>{1,2}\s*[\"']?([^\s\"'|;&]+)", seg):
            reason = protected_path(target, project, exchange_root)
            if reason:
                return "deny", reason
            if autonomous and re.search(SELF_TOKEN, target):
                return "deny", "Unattended agents may not change their own guardrails or policy."
        mentions = re.search(r"(^|[\s\"'=(]|" + re.escape(project_norm) + r"/|\./)" + TOKEN, seg) or re.search(FILE_TOKEN, seg)
        if WRITE_VERB.match(verb) or re.search(r"\bsed\s+(-\w+\s+)*-i", seg):
            if mentions:
                return "deny", "Deleting, moving or rewriting protected paths is forbidden. Write new files under data/derived/."
            if autonomous and re.search(SELF_TOKEN, seg):
                return "deny", "Unattended agents may not change their own guardrails or policy."
            if re.search(r"\brm\b.*\s-\w*r\w*\s+[\"']?(/|~|\.|\.\.|\*|c:/?|" + re.escape(project_norm) + r"/?)[\"']?(\s|$)", seg):
                return "deny", "Recursive delete of a root, home or the whole project is forbidden."
        if verb in {"cp", "copy", "copy-item", "cpi"} and len(words) >= 3:
            reason = protected_path(words[-1].strip("\"'"), project, exchange_root)
            if reason:
                return "deny", reason
        if re.search(r"\bpython[\w.]*\b.*\s-c\s", seg) and PY_WRITE.search(seg) and (mentions or (autonomous and re.search(SELF_TOKEN, seg))):
            return "deny", "Inline Python may not modify protected paths or guardrails."
        if autonomous and re.search(r"(^|[\s;&|(\"'/])claude(\.exe|\.cmd|\.ps1)?(\s|$)", seg):
            return "deny", "Unattended agents may not start nested Claude sessions."
    # Role git ownership binds the unattended agent; a supervised interactive session is the human's call.
    if autonomous and role == "pro360" and re.search(r"\bgit\b[^;&|\n]*\bpush\b", text):
        for seg in segments(text):
            if not re.search(r"\bgit\b.*\bpush\b", seg):
                continue
            args = [a for a in seg.split("push", 1)[1].split() if not a.startswith("-")]
            branch = args[1] if len(args) >= 2 else ""
            if not re.match(r"^(head:)?(refs/heads/)?pro/[\w./-]+$", branch):
                return "deny", "Pro pushes only to its own branches: git push -u origin pro/<topic>. Ultra integrates main."
    if autonomous and role == "pro360" and re.search(r"\bgit\b[^;&|\n]*\b(commit|merge|rebase|cherry-pick)\b", text) and _on_main(_git_dir(command, cwd or project)):
        return "deny", "On Pro, commit in a worktree branch (git worktree add ../Dacon_AFDA_Challenge_wt/<topic> -b pro/<topic>). Keep main clean for the exchange worker."
    if autonomous:
        for seg in segments(command):
            ok, name = program_ok(seg)
            if not ok:
                return "deny", (f"`{name}` is not on the unattended allowlist. Use the role venv python "
                                "(.venv-<role>/Scripts/python.exe) with a script in tools/ or scripts/, git, or standard file utilities.")
        return "allow", "AFDA guard: allowlisted command"
    return None, None


def _git_dir(command, cwd):
    """Directory a git commit in this command runs in: `git -C <dir>` or the last `cd <dir>` before it."""
    command = str(command).replace("\\", "/")
    head = re.split(r"\bgit\b[^;&|\n]*\b(commit|merge|rebase|cherry-pick)\b", command)[0]
    match = re.search(r"\bgit\s+-C\s+[\"']?([^\s\"']+)", command) or ([*re.finditer(r"(?:^|[;&|]\s*)cd\s+[\"']?([^\s\"';&|]+)", head)] or [None])[-1]
    if not match:
        return cwd
    target = match.group(1)
    target = re.sub(r"^/([a-zA-Z])/", r"\1:/", target)
    return target if os.path.isabs(target) else str(Path(cwd) / target)


def _on_main(where):
    try:
        result = subprocess.run(["git", "-C", str(where), "branch", "--show-current"], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() in {"main", "master"}
    except Exception:
        return False


def check_edit(path_text, autonomous, project, exchange_root):
    if not path_text:
        return None, None
    reason = protected_path(path_text, project, exchange_root)
    if reason:
        return "deny", reason
    p = norm(Path(path_text) if os.path.isabs(str(path_text)) else project / path_text)
    rel = p[len(norm(project)) + 1:] if p.startswith(norm(project) + "/") else None
    if autonomous:
        if rel is not None and (rel.startswith(SELF) or rel in SELF):
            return "deny", "Unattended agents may not change their own guardrails or policy."
        worktrees = norm(project.parent / (project.name.removesuffix("_git") + "_wt")) + "/"
        worktrees_alt = norm(project.parent / "Dacon_AFDA_Challenge_wt") + "/"
        temp = norm(tempfile.gettempdir()) + "/"
        if rel is not None or p.startswith((worktrees, worktrees_alt, temp)):
            return "allow", "AFDA guard: edit inside project/worktree"
        return "deny", "Unattended agents edit only inside the project, ../Dacon_AFDA_Challenge_wt worktrees, or the temp folder."
    return None, None


def decide(event, role=None, autonomous=None, project=None):
    project = Path(project) if project else project_dir()
    cfg = local_config(project)
    role = role or os.environ.get("AFDA_ROLE") or cfg.get("role")
    autonomous = os.environ.get("AFDA_AUTONOMOUS") == "1" if autonomous is None else autonomous
    exchange_root = cfg.get("exchange_root") or "C:/Dacon/AFDA_Exchange"
    tool = event.get("tool_name")
    data = event.get("tool_input") or {}
    if tool in SHELL_TOOLS:
        return check_shell(str(data.get("command", "")), role, autonomous, project, exchange_root, event.get("cwd"))
    if tool in EDIT_TOOLS:
        return check_edit(data.get("file_path") or data.get("notebook_path"), autonomous, project, exchange_root)
    return None, None


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
        decision, reason = decide(event)
    except Exception as error:  # fail closed for unattended runs
        decision, reason = ("deny", f"guard error: {type(error).__name__}: {error}") if os.environ.get("AFDA_AUTONOMOUS") == "1" else (None, None)
    if decision:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
