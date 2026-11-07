"""Bounded native UI input on the two retained dedicated trading AVDs only."""
import argparse
import re

from native_trade_fixture import safe_path
from startup_capture_device import Device, PACKAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['trade-primary', 'trade-peer'], required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ['launch', 'stop']:
        sub.add_parser(name)
    for name in ['tap', 'hold']:
        command = sub.add_parser(name)
        command.add_argument('x', type=int)
        command.add_argument('y', type=int)
        command.add_argument('--milliseconds', type=int, default=160)
    screen = sub.add_parser('screen')
    screen.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.action in ['tap', 'hold'] and not (
        0 <= args.x < 1280 and 0 <= args.y < 720 and 50 <= args.milliseconds <= 2500
    ):
        parser.error('Require on-screen coordinates and bounded 50..2500ms input')
    output = None
    if args.action == 'screen':
        output = safe_path(args.output)
        if output.suffix != '.png' or output.exists() or not re.fullmatch(r'[A-Za-z0-9_-]+\.png', output.name):
            parser.error('Require a fresh PNG path under ignored .research')
    device = Device(args.role)
    device.verify()
    if args.action == 'launch':
        device.adb('shell', 'monkey', '-p', PACKAGE, '-c', 'android.intent.category.LAUNCHER', '1')
    elif args.action == 'stop':
        device.adb('shell', 'am', 'force-stop', PACKAGE)
    elif args.action in ['tap', 'hold']:
        device.adb('shell', 'input', 'swipe', str(args.x), str(args.y), str(args.x), str(args.y), str(args.milliseconds))
    else:
        raw = device.adb('exec-out', 'screencap', '-p').stdout
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid screenshot')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(raw)
        print(output)


if __name__ == '__main__':
    main()
