from switchautopresence.cli import make_parser


def test_probe_parser():
    args = make_parser().parse_args(["probe", "--device", "2", "--seconds", "10", "--json"])
    assert args.device == 2
    assert args.seconds == 10
    assert args.backend == "dshow"
    assert args.json is True


def test_devices_parser():
    args = make_parser().parse_args(["devices"])
    assert args.command == "devices"
