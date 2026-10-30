---
name: disk-cleanup
description: Analyze disk usage and clean reclaimable caches with the mangodisk-cli binary. Use when asked to analyze disk consumption, find space hogs, free up disk space, scan cleanup candidates, or apply cache cleanup. Works on macOS and Linux.
---

# Disk Cleanup (mangodisk-cli)

Drive a read-only analysis, then an optionally applied cleanup, through the
`mangodisk-cli` binary. The CLI is safe by default: `clean` only scans, and
deletion happens exclusively through `clean --apply` after a preflight check.

## Step 0: Locate or build the binary

Resolve in this order, from the repository root:

```sh
# 1. Bundled binary (macOS arm64 build; only works on matching platforms)
.claude/skills/disk-cleanup/bin/mangodisk --version 2>/dev/null
# 2. Previously built workspace binary (same path on macOS and Linux)
target/release/mangodisk --version 2>/dev/null
# 3. Build from source
cargo build --manifest-path src-tauri/Cargo.toml -p mangodisk-cli --release
```

Use the first candidate that prints a version. A platform mismatch fails with
"exec format error" or "bad CPU type" — treat that as "binary unusable" and
continue down the list. On the wrong platform, refresh the bundled binary
after a successful build only with the user's approval, since replacing it
affects other machines.

If the machine has no Rust toolchain and no usable binary, fall back to
standard tools (`du -sh`, `df -h`) for analysis only, and say so.

## Step 0b: Building from source when no binary is available

The upstream source lives at https://github.com/harry0703/MangoDisk
(this skill's `src-tauri/` is that repository when you are already inside it).
On a machine without the repo, clone and build the CLI directly:

```sh
git clone https://github.com/harry0703/MangoDisk.git
cargo build --manifest-path MangoDisk/src-tauri/Cargo.toml \
  -p mangodisk-cli --release
# binary: MangoDisk/target/release/mangodisk (workspace root, not src-tauri/)
```

Prerequisites: a Rust toolchain (`rustup`). The CLI does not require the
Node.js frontend or Tauri packaging — `cargo build` of the workspace is
enough because `mangodisk-cli` depends only on `mangodisk-core` and
`mangodisk-platform`.

Linux note: `mangodisk-platform` ships a `linux` module, but a Linux build is
not routinely validated. If `cargo build` fails on Linux, do not patch the
workspace; fall back to the standard-tools path.

## Step 1: Read-only scan and analysis

```sh
MANGODISK=<path resolved in Step 0>
$MANGODISK clean --format json --no-progress > /tmp/mangodisk-scan.json
python3 .claude/skills/disk-cleanup/scripts/mangodisk_report.py scan /tmp/mangodisk-scan.json
```

Present to the user: total disk state, `reclaimableBytes` vs `safeBytes`,
top rules by size, and which large rules are `requiresAppClose`.

## Step 2: Dry-run preflight

Never skip this before an apply:

```sh
$MANGODISK clean --apply --selection recommended --dry-run --yes \
  --format json --no-progress > /tmp/mangodisk-dryrun.json
python3 .claude/skills/disk-cleanup/scripts/mangodisk_report.py apply /tmp/mangodisk-dryrun.json
```

Rules whose owning app is running are reported `blocked`
(`reasonCode: runningProcesses`) and will not be deleted. Tell the user which
apps to quit to unlock those bytes, and confirm the apply scope before running
it for real. Deletion requires explicit user confirmation.

## Step 3: Apply

```sh
$MANGODISK clean --apply --selection recommended --yes \
  --format json --no-progress > /tmp/mangodisk-apply.json
python3 .claude/skills/disk-cleanup/scripts/mangodisk_report.py apply /tmp/mangodisk-apply.json
```

`--selection recommended` mirrors the desktop app's smart selection.
`--selection all` exists but requires extra review; prefer `recommended`.
Re-running the same command after quitting apps picks up the previously
blocked rules; already-cleaned rules simply report zero bytes.

If an apply is interrupted or times out, it keeps running detached; re-check
`ps aux | grep mangodisk` and the JSON output file before assuming failure.

## Step 4: Verify and report

Compare `df` before/after and summarize `releasedBytes` per rule
(`completed` / `partial` / `blocked`). Explain gaps:

- `partial` + `reasonCode: runningProcesses` — owning app restarted mid-run
  (e.g. Lark relaunches helpers); re-run after quitting it again.
- `partial` + `reasonCode: itemsSkipped` on package-manager stores — a
  build/daemon holds the store; wait for it to finish or verify with
  `lsof +D <store>` that nothing holds it, then re-run.
- `du` vs `df` gaps — hard-linked cache entries (uv `archive-v0`, pnpm
  `store/v10/files`) release only unreferenced bytes; project `.venv` and
  `node_modules` keep their inodes. This is correct behavior, not data loss.

## Known blind spots to check manually

The rule set misses caches outside default tool locations. After the CLI pass,
check and report (analysis first, delete only on explicit approval):

- Custom Go paths: `go env GOMODCACHE GOCACHE`, then `du -sh` each. The
  `cache/vcs/` bare-clone caches can hold multi-GB stale repos; a leftover
  `tmp_pack_*` inside `objects/pack/` is an aborted fetch and is safe to
  delete. Extracted module copies in the mod cache stay because builds use
  them.
- pnpm store: prefer `pnpm store prune` (unreferenced packages only) over
  full deletion; both leave hard-linked `node_modules` intact.
- uv cache: full deletion leaves `.venv`s intact (hard links); re-installs
  re-download.
- Large Rust `target/` dirs of inactive projects: `cargo clean` in the
  project, not through this CLI.

## Safety rules

- Never run `--apply` without a prior `--dry-run` in the same session, and
  never without explicit user confirmation of the scope.
- Never delete paths outside the CLI's reported rules without a separate,
  explicit approval for each path.
- `--include-full-paths` is for machine-readable output only; keep raw
  private paths out of committed reports.
