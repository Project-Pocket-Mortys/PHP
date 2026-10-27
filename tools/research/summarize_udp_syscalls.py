"""Export payload-free relative timing from a bounded Android raw strace.

The caller must establish the selected UDP descriptor independently. Descriptor
reuse is not detected. recvmsg/sendmsg return lengths, but without decoding their
structures this tool does not classify their datagrams; recvmmsg returns a message
count. Only recvfrom/sendto produce byte and 24-byte packet events here.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re


LINE = re.compile(r'^\s*(?:(?:\[pid\s+(\d+)\]|(\d+))\s+)?(\d+\.\d+)\s+(.*)$')
CALL = re.compile(r'^(recvfrom|sendto|recvmsg|sendmsg|recvmmsg)\((0x[0-9a-fA-F]+|\d+)(?:,|\))')
RESUMED = re.compile(r'^<\.\.\. (recvfrom|sendto|recvmsg|sendmsg|recvmmsg) resumed>')
RESULT = re.compile(r'\)\s+=\s+(0x[0-9a-fA-F]+|\d+)(?:\s|$)')
KINDS = ('recvfrom', 'sendto', 'recvmsg', 'sendmsg', 'recvmmsg')


def number(value):
    return int(value, 16 if value.lower().startswith('0x') else 10)


def summarize(trace, fd):
    if fd < 0:
        raise ValueError('Descriptor must be nonnegative')
    origin = last = None
    pending = {}
    events = []
    others = {kind: 0 for kind in KINDS[2:]}
    for line in trace.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        thread = match[1] or match[2] or ''
        stamp, body = Decimal(match[3]), match[4]
        if origin is None:
            origin = stamp
        last = stamp
        call = CALL.match(body)
        resumed = RESUMED.match(body)
        if call:
            kind, descriptor = call[1], number(call[2])
            pending.pop(thread, None)
            if '<unfinished ...>' in body:
                pending[thread] = (kind, descriptor)
                continue
        elif resumed:
            previous = pending.pop(thread, None)
            if previous is None or previous[0] != resumed[1]:
                continue
            kind, descriptor = previous
        else:
            continue
        result = RESULT.search(body)
        if descriptor != fd or result is None:
            continue
        count = number(result[1])
        if count <= 0:
            continue
        if kind in others:
            others[kind] += 1
            continue
        events.append({'offset_seconds': float(stamp - origin),
                       'syscall': kind, 'bytes': count})
    totals = {}
    for kind in KINDS[:2]:
        selected = [event for event in events if event['syscall'] == kind]
        totals[kind] = {'count': len(selected), 'bytes': sum(event['bytes'] for event in selected),
                        'first_offset_seconds': selected[0]['offset_seconds'] if selected else None,
                        'last_offset_seconds': selected[-1]['offset_seconds'] if selected else None}
    return {
        'provenance': 'Android syscall results; selected UDP descriptor mapped independently. '
                      'Relative origin is first timestamped trace line, including other descriptors. '
                      'Resumed calls use completion timestamp. Descriptor reuse is not detected. '
                      'Syscall receipt does not prove game processing.',
        'observed_span_seconds': float(last - origin) if origin is not None else 0,
        'summary': totals,
        'events': events,
        'packet_events': [event for event in events if event['bytes'] == 24],
        'other_positive_completions': others,
        'limitations': 'recvmsg/sendmsg/recvmmsg are counted as positive completions only; '
                       'their structures and datagram sizes are not decoded. '
                       'Trace duration and UDP descriptor identity require separate evidence.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--fd', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.fd < 0:
        parser.error('--fd must be nonnegative')
    report = summarize(args.input.read_text(), args.fd)
    args.output.write_text(json.dumps(report, indent=2) + '\n', newline='\n')
    print(f"Exported {len(report['events'])} successful byte-count events")


if __name__ == '__main__':
    main()
