import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class RunnerError(ValueError):
    pass


def normalize(value: str) -> str:
    return value.replace("-", "_")


def load_registry(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "keymap" / "profiles.json").read_text())


def resolve_target(registry: dict[str, Any], requested: str) -> tuple[str, dict[str, Any]]:
    targets = registry["targets"]
    profiles = registry["profiles"]
    if requested in profiles:
        for name, target in targets.items():
            if target.get("profile") == requested:
                return name, target
        return requested, {"profile": requested, "all": False}
    wanted = normalize(requested)
    for name, target in targets.items():
        if wanted in {normalize(alias) for alias in [name, *target.get("aliases", [])]}:
            return name, target
    choices = ", ".join(targets)
    raise RunnerError(f"unknown target {requested!r}; choose one of: {choices}, or a profile name")


def profile_for(registry: dict[str, Any], target: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    name = target.get("profile")
    return name, registry["profiles"].get(name, {})


def available_backends(registry: dict[str, Any], target: dict[str, Any]) -> list[str]:
    _, profile = profile_for(registry, target)
    inferred = [backend for backend in ("zmk", "qmk") if backend in profile]
    if target.get("zmk_keyboard") and "zmk" not in inferred:
        inferred.insert(0, "zmk")
    return target.get("backends", inferred)


def selected_backends(registry: dict[str, Any], name: str, target: dict[str, Any], requested: str) -> list[str]:
    available = available_backends(registry, target)
    requested = {"wired": "qmk", "wireless": "zmk"}.get(requested, requested)
    if requested == "default":
        return target.get("default_backends", available)
    if requested == "all":
        return available
    if requested not in available:
        choices = ", ".join(available) or "none"
        raise RunnerError(f"target {name!r} does not support {requested}; available: {choices}")
    return [requested]


def zmk_output(zmk: dict[str, Any]) -> str:
    if output := zmk.get("output_keyboard"):
        return output
    keyboard = zmk["keyboard"]
    keymap = zmk.get("keymap")
    return f"{keyboard}_{keymap}" if keymap and keymap != keyboard else keyboard


def run_backend(repo: Path, registry: dict[str, Any], name: str, target: dict[str, Any], backend: str, action: str) -> None:
    profile_name, profile = profile_for(registry, target)
    env = os.environ.copy()
    if profile_name:
        env["KEYMAP_PROFILE"] = profile_name
    else:
        env.pop("KEYMAP_PROFILE", None)
    if backend == "zmk":
        zmk = profile.get("zmk", {})
        keyboard = target.get("zmk_keyboard") or zmk.get("keyboard")
        if not keyboard:
            raise RunnerError(f"target {name!r} has no ZMK keyboard")
        output = zmk_output(zmk) if zmk else keyboard
        if output != keyboard:
            env["ZMK_OUTPUT_KEYBOARD"] = output
        command = [str(repo / "build.sh"), keyboard]
        if action not in {"build", "both"}:
            command.append(action)
    elif backend == "qmk":
        qmk = profile.get("qmk")
        if not qmk:
            raise RunnerError(f"target {name!r} has no QMK keyboard")
        env["QMK_KEYBOARD"] = qmk["keyboard"]
        env["QMK_KEYMAP"] = qmk.get("keymap", "razen")
        if output := qmk.get("output_keyboard"):
            env["QMK_OUTPUT_KEYBOARD"] = output
        if convert_to := qmk.get("convert_to"):
            if "QMK_CONVERT_TO" not in env and "CONVERT_TO" not in env:
                env["QMK_CONVERT_TO"] = convert_to
        command = [str(repo / "qmk-build.sh"), action]
    else:
        raise RunnerError(f"unknown backend {backend!r}")
    print(f"→ {name} {backend} {action}", flush=True)
    subprocess.run(command, cwd=repo, env=env, check=True)


def run_targets(repo: Path, registry: dict[str, Any], requested_target: str, requested_backend: str, action: str) -> None:
    if requested_target == "all":
        selected = [(name, target) for name, target in registry["targets"].items() if target.get("all", True)]
        backend = {"wired": "qmk", "wireless": "zmk"}.get(requested_backend, requested_backend)
        for name, target in selected:
            if backend not in {"default", "all"} and backend not in available_backends(registry, target):
                continue
            for item in selected_backends(registry, name, target, backend):
                run_backend(repo, registry, name, target, item, action)
        return
    name, target = resolve_target(registry, requested_target)
    for backend in selected_backends(registry, name, target, requested_backend):
        run_backend(repo, registry, name, target, backend, action)


def draw(repo: Path, registry: dict[str, Any], requested: str) -> None:
    command = [str(repo / "scripts" / "generate"), "draw"]
    if requested == "all":
        subprocess.run(command, cwd=repo, check=True)
        return
    name, target = resolve_target(registry, requested)
    profiles = target.get("draw_profiles")
    if profiles is None:
        profiles = [target["profile"]] if target.get("profile") else []
    if not profiles:
        raise RunnerError(f"target {name!r} has no drawing")
    for profile in profiles:
        subprocess.run([*command, "--profile", profile], cwd=repo, check=True)


def clean_generated(repo: Path) -> None:
    for path in (repo / ".cache" / "keymap", repo / "build"):
        if path.exists():
            shutil.rmtree(path)
            print(f"removed {path.relative_to(repo)}")
    tracked = set(subprocess.check_output(["git", "ls-files", "draw/generated/*.svg"], cwd=repo, text=True).splitlines())
    for path in (repo / "draw" / "generated").glob("*.svg"):
        if str(path.relative_to(repo)) not in tracked:
            path.unlink()
            print(f"removed {path.relative_to(repo)}")


def list_targets(registry: dict[str, Any]) -> None:
    print(f"{'target':<20} {'supports':<8} {'default':<8} profile")
    for name, target in registry["targets"].items():
        profile = target.get("profile", "standalone")
        available = available_backends(registry, target)
        defaults = target.get("default_backends", available)
        print(f"{name:<20} {','.join(available):<8} {','.join(defaults):<8} {profile}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("targets")
    draw_parser = subparsers.add_parser("draw")
    draw_parser.add_argument("target", nargs="?", default="all")
    for command in ("build", "setup"):
        action_parser = subparsers.add_parser(command)
        action_parser.add_argument("target", nargs="?", default="all")
        action_parser.add_argument("--backend", default="default", choices=("default", "all", "zmk", "qmk", "wired", "wireless"))
    clean_parser = subparsers.add_parser("clean")
    clean_parser.add_argument("target", nargs="?", default="generated")
    clean_parser.add_argument("--backend", default="default", choices=("default", "all", "zmk", "qmk", "wired", "wireless"))
    for command in ("left", "right", "reset", "flash", "distclean"):
        action_parser = subparsers.add_parser(command)
        action_parser.add_argument("target")
    zmk_parser = subparsers.add_parser("zmk")
    zmk_parser.add_argument("target")
    zmk_parser.add_argument("action", nargs="?", default="both")
    qmk_parser = subparsers.add_parser("qmk")
    qmk_parser.add_argument("target")
    qmk_parser.add_argument("action", nargs="?", default="build", choices=("setup", "build", "flash", "clean", "distclean"))
    return result


def main() -> None:
    args = parser().parse_args()
    repo = Path(__file__).resolve().parents[1]
    registry = load_registry(repo)
    if args.command == "targets":
        list_targets(registry)
    elif args.command == "draw":
        draw(repo, registry, args.target)
    elif args.command in {"build", "setup"}:
        run_targets(repo, registry, args.target, args.backend, args.command)
    elif args.command == "clean":
        if args.target == "generated":
            clean_generated(repo)
        else:
            run_targets(repo, registry, args.target, args.backend, "clean")
    elif args.command in {"left", "right", "reset"}:
        run_targets(repo, registry, args.target, "zmk", args.command)
    elif args.command in {"flash", "distclean"}:
        run_targets(repo, registry, args.target, "qmk", args.command)
    elif args.command in {"zmk", "qmk"}:
        run_targets(repo, registry, args.target, args.command, args.action)


if __name__ == "__main__":
    try:
        main()
    except RunnerError as error:
        print(f"keyboard: {error}", file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
