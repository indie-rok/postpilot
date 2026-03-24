# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from cli import parse_args


def test_parse_init():
    args = parse_args(["init"])
    assert args.command == "init"


def test_parse_serve_with_port():
    args = parse_args(["serve", "--port", "3000"])
    assert args.command == "serve"
    assert args.port == 3000


def test_parse_configure():
    args = parse_args(["configure"])
    assert args.command == "configure"


def test_parse_learn():
    args = parse_args(["learn"])
    assert args.command == "learn"
