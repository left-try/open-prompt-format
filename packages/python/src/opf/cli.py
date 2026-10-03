"""Command-line interface for validating and rendering OPF files."""

import argparse
import json
import sys
from pathlib import Path

from .core import OPFError, load, load_collection
from .registry import Registry
from .publish import langfuse_plan, publish_langfuse
from .discovery import scan
from .migrate import apply_migration, plan_migration
from .check import check as run_check
from .init import initialize
from .diff import compare as compare_prompts


def main() -> None:
    parser = argparse.ArgumentParser(prog="opf")
    sub = parser.add_subparsers(dest="command", required=True)
    init_cmd = sub.add_parser("init", help="create an OPF starter prompt and agent guidance")
    init_cmd.add_argument("path", nargs="?", default=".")
    init_cmd.add_argument("--id", default="example.prompt")
    init_cmd.add_argument("--prompt", default="prompts/example.prompt.md")
    init_cmd.add_argument("--agents", choices=["auto", "yes", "no"], default="auto")
    check_cmd = sub.add_parser("check", help="validate prompts and registry locally")
    check_cmd.add_argument("path", nargs="?", default=".")
    check_cmd.add_argument("--registry")
    check_cmd.add_argument("--format", choices=["text", "json"], default="text")
    check_cmd.add_argument("--strict", action="store_true", help="treat warnings as failures")
    check_cmd.add_argument("--no-safety", action="store_true", help="skip heuristic safety advisories")
    diff_cmd = sub.add_parser("diff", help="compare prompt releases and report stable-prefix evidence")
    diff_cmd.add_argument("id")
    diff_cmd.add_argument("--base", required=True, help="release version or channel:NAME")
    diff_cmd.add_argument("--target", required=True, help="release version, channel:NAME, or working-tree")
    diff_cmd.add_argument("--registry", default="opf.yaml")
    diff_cmd.add_argument("--format", choices=["text", "json"], default="text")
    discover = sub.add_parser("scan", help="find likely prompt sources without changing files")
    discover.add_argument("path", nargs="?", default=".")
    discover.add_argument("--format", choices=["text", "json"], default="text")
    discover.add_argument("--include", action="append", default=[], metavar="GLOB")
    discover.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    migrate = sub.add_parser("migrate", help="inspect or apply a local prompt migration")
    migrate_sub = migrate.add_subparsers(dest="migration_action", required=True)
    inspect_migration = migrate_sub.add_parser("inspect", help="preview a migration without writing files")
    apply_migration_cmd = migrate_sub.add_parser("apply", help="write generated files without overwriting existing files")
    for command in (inspect_migration, apply_migration_cmd):
        command.add_argument("path")
        command.add_argument("--id")
        command.add_argument("--role", choices=["system", "developer", "user", "assistant"])
        command.add_argument("--kind", choices=["markdown", "jinja2", "openai", "langchain", "crewai", "autogen"])
        command.add_argument("--root", default=".")
        command.add_argument("--strict", action="store_true")
        command.add_argument("--format", choices=["text", "json"], default="text")
    apply_migration_cmd.add_argument("--output-dir", help="migration root for generated files (default: --root)")
    apply_migration_cmd.add_argument("--register", action="store_true", help="add the prompt and provenance to a local registry")
    apply_migration_cmd.add_argument("--registry", default="opf.yaml", help="registry path used with --register")
    validate = sub.add_parser("validate", help="validate a prompt file")
    validate.add_argument("file")
    validate.add_argument("--strict", action="store_true", help="fail if a required extension is unknown to the core renderer")
    compat = sub.add_parser("compat", help="report OPF extension compatibility")
    compat.add_argument("file")
    compat.add_argument("--strict", action="store_true")
    compat.add_argument("--supports-extension", action="append", default=[], metavar="ID=VERSION")
    compat.add_argument("--format", choices=["text", "json"], default="text")
    collection = sub.add_parser("validate-collection", help="validate all prompts in a directory")
    collection.add_argument("directory")
    render = sub.add_parser("render", help="render a prompt to role/content JSON")
    render.add_argument("file")
    render.add_argument("--input", action="append", default=[], metavar="NAME=VALUE")
    render.add_argument("--registry", metavar="OPF_YAML", help="resolve file argument as a registry prompt id")
    render.add_argument("--channel")
    render.add_argument("--version")
    render.add_argument("--receipt", action="store_true", help="include prompt and render digests")
    release = sub.add_parser("release", help="tag a committed prompt release")
    release.add_argument("id")
    release.add_argument("--version", required=True)
    release.add_argument("--registry", default="opf.yaml")
    promote = sub.add_parser("promote", help="point a channel at a release in opf.yaml")
    promote.add_argument("release", metavar="ID@VERSION")
    promote.add_argument("--channel", required=True)
    promote.add_argument("--registry", default="opf.yaml")
    verify = sub.add_parser("verify", help="verify a released prompt or channel")
    verify.add_argument("id")
    verify.add_argument("--channel")
    verify.add_argument("--version")
    verify.add_argument("--registry", default="opf.yaml")
    verify_all = sub.add_parser("verify-all", help="verify every configured registry channel")
    verify_all.add_argument("--registry", default="opf.yaml")
    export = sub.add_parser("export", help="write a portable release bundle")
    export.add_argument("release", metavar="ID@VERSION")
    export.add_argument("--output", required=True)
    export.add_argument("--registry", default="opf.yaml")
    publish = sub.add_parser("publish", help="publish a verified release to an external registry")
    publish.add_argument("release", metavar="ID@VERSION")
    publish.add_argument("--to", choices=["langfuse"], required=True)
    publish.add_argument("--registry", default="opf.yaml")
    publish.add_argument("--dry-run", action="store_true", help="show compatibility and payload without a network request")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args.path, prompt_id=args.id, prompt_path=args.prompt, update_agents=args.agents != "no")
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return
        if args.command == "check":
            root = Path(args.path).resolve()
            registry_path = args.registry
            if registry_path and not Path(registry_path).is_absolute():
                registry_path = root / registry_path
            findings = run_check(root, registry_path=registry_path, safety=not args.no_safety)
            if args.format == "json":
                print(json.dumps([item.to_dict() for item in findings], ensure_ascii=False, indent=2))
            else:
                for item in findings:
                    location = item.path or "<project>"
                    if item.line is not None:
                        location += ":{}".format(item.line)
                        if item.column is not None:
                            location += ":{}".format(item.column)
                    print("{} {} {}: {}".format(item.severity.upper(), item.code, location, item.message))
                errors = sum(item.severity == "error" for item in findings)
                warnings = sum(item.severity == "warning" for item in findings)
                print("{} error(s), {} warning(s)".format(errors, warnings))
            if any(item.severity == "error" for item in findings) or args.strict and findings:
                raise SystemExit(2)
            return
        if args.command == "diff":
            report = compare_prompts(args.id, args.base, args.target, registry_path=args.registry)
            if args.format == "json":
                print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            else:
                print("{}: {} -> {} ({})".format(report.id, report.base, report.target, "changed" if report.changed else "unchanged"))
                for change in report.changes:
                    print("- {}: {}".format(change["kind"], json.dumps(change, ensure_ascii=False)))
                print("stable leading messages: {}".format(report.stable_prefix_messages if report.stable_prefix_messages is not None else "unknown"))
                print("cacheability evidence: {} (not a provider cache-hit claim)".format(report.cacheability))
                for note in report.limitations:
                    print("note: {}".format(note))
            return
        if args.command == "validate-collection":
            prompts = load_collection(args.directory)
            print("valid: {} prompt(s)".format(len(prompts)))
            return
        if args.command == "scan":
            findings = scan(args.path, include=args.include, exclude=args.exclude)
            if args.format == "json":
                print(json.dumps([item.to_dict() for item in findings], ensure_ascii=False, indent=2))
            else:
                for item in findings:
                    print("{}  {}  {}  {}".format(item.path, item.source_kind, item.confidence, item.reason))
                print("{} candidate(s)".format(len(findings)))
            return
        if args.command == "migrate":
            plan = plan_migration(args.path, root=args.root, prompt_id=args.id, role=args.role, kind=args.kind)
            if args.migration_action == "inspect":
                result = plan.to_dict()
            else:
                result = apply_migration(plan, root=args.output_dir or args.root, strict=args.strict, register=args.register, registry_path=args.registry)
            if args.format == "json":
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif args.migration_action == "inspect":
                report = plan.compatibility
                print("{} -> {} (lossless={}, can_apply={})".format(report.source_kind, report.target_kind, report.lossless, report.can_apply))
                print("prompt id: {}".format(plan.prompt_id))
                print("source: {} ({})".format(plan.source.relative_path, plan.source.source_digest))
                for path in plan.output.files:
                    print("generated: {}".format(path))
                if plan.output.registry_entry:
                    print("registry entry: {}".format(json.dumps(plan.output.registry_entry, ensure_ascii=False)))
                for finding in report.findings:
                    print("{} {} [{}]: {}".format(finding.severity.upper(), finding.code, finding.disposition, finding.message))
                if not report.findings:
                    print("no compatibility findings")
            else:
                print("applied migration for {}".format(result["prompt_id"]))
                for path in result["written"]:
                    print("  {}".format(path))
            if args.migration_action == "inspect" and args.strict and (not plan.compatibility.can_apply or any(f.disposition in {"dropped", "manual"} or f.severity == "error" for f in plan.compatibility.findings)):
                raise SystemExit(2)
            return
        if args.command == "compat":
            supported = {}
            for value in args.supports_extension:
                if "=" not in value:
                    raise OPFError("--supports-extension must use ID=VERSION")
                identifier, version = value.split("=", 1)
                if not identifier or not version:
                    raise OPFError("--supports-extension must use non-empty ID=VERSION")
                supported.setdefault(identifier, []).append(version)
            report = load(args.file).compatibility(strict=args.strict, supported_extensions=supported)
            if args.format == "json":
                print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
            else:
                print("{} -> {} (lossless={}, can_apply={})".format(report.source_kind, report.target_kind, report.lossless, report.can_apply))
                for finding in report.findings:
                    print("{} {} [{}]: {}".format(finding.severity.upper(), finding.code, finding.disposition, finding.message))
                if not report.findings:
                    print("all extensions are supported")
            if not report.can_apply:
                raise SystemExit(2)
            return
        if args.command in {"release", "promote", "verify", "verify-all", "export", "publish"}:
            registry = Registry.local(args.registry)
            if args.command in {"promote", "export", "publish"}:
                if "@" not in args.release:
                    raise OPFError("release must use ID@VERSION")
                prompt_id, version = args.release.rsplit("@", 1)
            if args.command == "release":
                result = registry.release(args.id, args.version)
            elif args.command == "promote":
                result = registry.promote(prompt_id, version, args.channel)
            elif args.command == "verify":
                if bool(args.channel) == bool(args.version):
                    raise OPFError("verify requires exactly one of --channel or --version")
                prompt = registry.get(args.id, channel=args.channel, version=args.version)
                result = {"id": args.id, "version": prompt.version, "channel": prompt.channel, "digest": prompt.bundle["digest"]}
            elif args.command == "verify-all":
                result = registry.verify_all()
            elif args.command == "export":
                result = registry.export(prompt_id, version, args.output)
                result = {"id": prompt_id, "version": version, "digest": result["digest"], "output": args.output}
            else:
                plan = langfuse_plan(registry, prompt_id, version)
                result = plan if args.dry_run else publish_langfuse(plan)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.command == "render" and args.registry:
            prompt = Registry.local(args.registry).get(args.file, channel=args.channel, version=args.version)
        else:
            if args.command == "render" and (args.channel or args.version):
                raise OPFError("--channel and --version require --registry")
            prompt = load(args.file)
        if args.command == "validate":
            report = prompt.compatibility(strict=args.strict)
            if not report.can_apply:
                raise OPFError("strict compatibility failed; run 'opf compat {} --strict' for details".format(args.file))
            print("valid: {}@{} {}".format(prompt.id, prompt.version or "draft", prompt.source_digest))
            return
        inputs = {}
        for item in args.input:
            if "=" not in item:
                raise OPFError("--input must use NAME=VALUE")
            name, value = item.split("=", 1)
            if name in inputs:
                raise OPFError("input {!r} was supplied more than once".format(name))
            inputs[name] = value
        if args.registry:
            prepared = prompt.render(inputs)
            result = {"messages": prepared.messages, "receipt": prepared.receipt} if args.receipt else prepared.messages
        else:
            if args.receipt:
                raise OPFError("--receipt requires --registry")
            result = prompt.render(**inputs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except OPFError as exc:
        print("opf: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
