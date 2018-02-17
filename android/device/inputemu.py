''' Record and playback input event gestures on Android. '''

from .adb_shell import ADBShell, ShellCommandException
import time
import re
import os
import struct

__author__ = 'Robert Xiao <nneonneo@gmail.com>'

def get_build_prop(shell):
    res = shell.execute('cat /system/build.prop', text=True).split('\n')
    out = {}
    for line in res:
        line = line.lstrip()
        if not line or line.startswith('#'):
            continue

        k, v = line.split('=', 1)
        out[k] = v

    return out

def get_model(shell):
    props = get_build_prop(shell)
    return '%(ro.product.manufacturer)s %(ro.product.model)s'%props

def get_ident(shell):
    props = get_build_prop(shell)
    return '%(ro.product.manufacturer)s %(ro.product.model)s %(ro.build.id)s'%props

def _write_events(shell, events):
    # Try using echo first, but if that fails then switch to sendevent permanently
    if getattr(shell, 'use_sendevent', False):
        for dev, type, value, code in events:
            shell.execute('sendevent %s %d %d %d' % (dev, type, value, code))
        return

    dat = {}
    for dev, type, value, code in events:
        if dev not in dat:
            dat[dev] = []
        dat[dev].append(struct.pack('<IIHHi', 0, 0, type, value, code))

    try:
        for dev in dat:
            s = ''.join('\\x%02x' % ord(c) for c in ''.join(dat[dev]))
            shell.execute("echo -ne '%s' > %s" % (s, dev))
    except ShellCommandException as e:
        print "Warning: inputemu: adb echo failed (%s), falling back to sendevent" % e
        shell.use_sendevent = True
        _write_events(shell, events)

def playback_gesture(shell, ident, gesture):
    gestfn = os.path.join('events', ident, gesture + '.txt')
    if not os.path.exists(gestfn):
        raise ValueError("Gesture %s for device '%s' does not exist." % (gesture, ident))

    start_ts = None
    start = None
    pack = []
    pack_start_ts = None
    with open(gestfn) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ts, dev, type, value, code = line.split()
            ts = float(ts)
            type = int(type)
            value = int(value)
            code = int(code)

            if start_ts is None:
                start_ts = ts
                start = time.time()

            if pack_start_ts is None or ts - pack_start_ts < 0.010:
                if pack_start_ts is None:
                    pack_start_ts = ts
                pack.append((dev, type, value, code))
            else:
                _write_events(shell, pack)
                pack = [(dev, type, value, code)]
                pack_start_ts = ts

                sleeptime = (ts - start_ts) - (time.time() - start)
                if sleeptime > 0.001:
                    time.sleep(sleeptime)

        _write_events(shell, pack)

def readlines_timed(f, tottime):
    start = time.time()
    while time.time() - start < tottime:
        line = f.readline()
        if not line:
            time.sleep(0.01)
            continue
        yield line

def parse_getevent(line):
    line = line.strip()
    m = re.match(r'^\[\s*(\d+\.\d+)\] ([/\w]+): (\w+) (\w+) (\w+)', line)
    if not m:
        raise ValueError("unparseable getevent line " + line)
    return m.groups()

def record_gestures(shell, ident, gestlist):
    outdir = os.path.join('events', ident)
    try:
        os.makedirs(outdir)
    except OSError:
        pass

    p = shell.popen('getevent -t', text=True, nonblocking=True)

    print "Collecting device info..."
    for line in readlines_timed(p.stdout, 0.2):
        pass

    skipdevs = set()

    print "Collecting background events..."
    for line in readlines_timed(p.stdout, 0.2):
        ts, dev, type, value, code = parse_getevent(line)
        if dev not in skipdevs:
            print "Skipping device", dev
            skipdevs.add(dev)

    for gest in gestlist:
        print "\aPlease do a %s gesture!" % gest

        last = None
        start_ts = None
        events = []
        while True:
            if last and time.time() - last > 0.5:
                break
            line = p.stdout.readline()
            if not line:
                time.sleep(0.01)
                continue
            ts, dev, type, value, code = parse_getevent(line)
            if dev in skipdevs:
                continue
            ts = float(ts)
            type = int(type, 16)
            value = int(value, 16)
            code = int(code, 16)
            if code & (1<<31):
                code -= 1<<32
            if last is None:
                start_ts = ts
            events.append((ts - start_ts, dev, type, value, code))
            last = time.time()

        print "Captured!"
        with open(os.path.join(outdir, gest + '.txt'), 'w') as f:
            for ev in events:
                f.write('%f %s %d %d %d\n' % ev)

def parse_args(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Record and play back gestures on the phone")
    parser.add_argument('--record', action='store_true', help="Record gestures")
    parser.add_argument('gestures', nargs='+', help="Gestures to replay or record")

    args = parser.parse_args(argv)
    return args

def main(argv):
    args = parse_args(argv)

    shell = ADBShell()
    ident = get_ident(shell)

    if args.record:
        record_gestures(shell, ident, args.gestures)
    else:
        for gest in args.gestures:
            print "Playing back %s" % gest
            playback_gesture(shell, ident, gest)
            time.sleep(0.5)

if __name__ == '__main__':
    import sys
    exit(main(sys.argv[1:]))
