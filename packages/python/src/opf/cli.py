"""Command-line interface for validating and rendering OPF files."""

import argparse
import json
import sys

from .core import OPFError, load, load_collection


def main() -> None:
    parser = argparse.ArgumentParser(prog="opf")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate a prompt file")
    validate.add_argument("file")
    collection = sub.add_parser("validate-collection", help="validate all prompts in a directory")
    collection.add_argument("directory")
    render = sub.add_parser("render", help="render a prompt to role/content JSON")
    render.add_argument("file")
    render.add_argument("--input", action="append", default=[], metavar="NAME=VALUE")
    args = parser.parse_args()
    try:
        if args.command == "validate-collection":
            prompts = load_collection(args.directory)
            print("valid: {} prompt(s)".format(len(prompts)))
            return
        prompt = load(args.file)
        if args.command == "validate":
            print("valid: {}@{} {}".format(prompt.id, prompt.version, prompt.source_digest))
            return
        inputs = {}
        for item in args.input:
            if "=" not in item:
                raise OPFError("--input must use NAME=VALUE")
            name, value = item.split("=", 1)
            if name in inputs:
                raise OPFError("input {!r} was supplied more than once".format(name))
            inputs[name] = value
        print(json.dumps(prompt.render(**inputs), ensure_ascii=False, indent=2))
    except OPFError as exc:
        print("opf: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
