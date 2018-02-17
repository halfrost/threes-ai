''' adb shell wrapper.

Compatible with Python 2.6, 2.7 and Python 3.'''

from subprocess import Popen, PIPE
import fcntl
import os
import time
import errno
import sys
import re
import select
import signal
try:
    from pipes import quote as shellquote
except ImportError:
    from shlex import quote as shellquote
import select
import threading

__author__ = 'Robert Xiao <nneonneo@gmail.com>'

def read_timed(f, n=None, timeout=None):
    if timeout is None:
        res = select.select([f.fileno()], [], [])
    else:
        res = select.select([f.fileno()], [], [], timeout)

    if not res[0]:
        return b''

    if n is None:
        return f.read()
    else:
        return f.read(n)

def read_nonblock(f, n=None):
    try:
        if n is None:
            return f.read()
        else:
            return f.read(n)
    except IOError as e:
        if e.errno == errno.EAGAIN:
            return b''
        else:
            raise

def warn(x):
    sys.stderr.write('Warning: %s\n' % x)
    sys.stderr.flush()

CTRL_C = b'\x03'
CTRL_D = b'\x04'

class ShellCommandException(OSError):
    def __init__(self, cmd, status, msg):
        self.cmd = cmd
        self.status = status
        self.msg = msg
        self.args = (status, msg)
    def __str__(self):
        if self.status > 128:
            return "Command '%s' was killed by signal %d" % (self.cmd, self.status - 128)
        else:
            return "Command '%s' returned non-zero exit status %d" % (self.cmd, self.status)

class _ADBPopenStdout:
    def __init__(self, popen, text, nonblocking):
        self.popen = popen
        self.text = text
        self.nonblocking = nonblocking
        self._closed = False
        self._buffer = bytearray()
        self._datacond = threading.Condition()
        self._done = False

    def _push(self, data):
        with self._datacond:
            if data is None:
                # EOF encountered
                self._done = True
            else:
                self._buffer.extend(data)
            self._datacond.notify_all()

    def close(self):
        self._closed = True

    def flush(self):
        pass

    def next(self):
        next = self.readline()
        if not next:
            raise StopIteration
        return next

    def __next__(self):
        return self.next()

    def __iter__(self):
        return self

    def _grab_locked(self, size=None):
        data = self._buffer[:size]
        del self._buffer[:size]
        if self.text:
            return data.decode()
        else:
            return data

    def read(self, size=None):
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if size is None:
            size = 0

        with self._datacond:
            while True:
                if self._done:
                    return self._grab_locked()

                if size > 0 and len(self._buffer) >= size:
                    return self._grab_locked(size)

                if self.nonblocking:
                    # Return whatever we've got.
                    return self._grab_locked()
                else:
                    self._datacond.wait(1000)

    def readline(self, size=None):
        if size is None:
            size = 0

        with self._datacond:
            while True:
                if self._done:
                    return self._grab_locked()

                if size > 0 and len(self._buffer) >= size:
                    return self._grab_locked(size)

                pos = self._buffer.find(b'\n')
                if pos >= 0:
                    return self._grab_locked(pos+1)

                if self.nonblocking:
                    # Return complete lines or nothing.
                    return self._grab_locked(0)
                else:
                    self._datacond.wait(1000)

    def readlines(self, sizehint=None):
        return list(self)

    def xreadlines(self):
        return self

    @property
    def closed(self):
        return self._closed

    @property
    def mode(self):
        if self.text:
            return 'r'
        else:
            return 'rb'

class _ADBPopenStdin:
    def __init__(self, popen, text, nonblocking):
        self.popen = popen
        self.text = text
        self.nonblocking = nonblocking
        self._stdin = self.popen.shell.proc.stdin
        self._closed = False
        self._wrote_newline = False

    def _write(self, data):
        # _write ignores closed state.
        self._stdin.write(data)
        self._stdin.flush()
        self._wrote_newline = (len(data) > 0 and data[-1] in b'\n\r\x04')

    def write(self, data):
        if self._closed:
            raise ValueError("I/O operation on closed file")

        if self.text:
            data = data.encode()
        self._write(data)

    def writelines(self, seq):
        for line in seq:
            self.write(line)

    def flush(self):
        # Send Ctrl+D, but only if we didn't just send a newline
        if not self._wrote_newline:
            self._write(CTRL_D)

    def close(self):
        if self._closed:
            return

        # Send Ctrl+D to remote end
        if not self._wrote_newline:
            self._write(CTRL_D)
        self._write(CTRL_D)
        self._closed = True

    @property
    def closed(self):
        return self._closed

    @property
    def mode(self):
        if self.text:
            return 'w'
        else:
            return 'wb'

class AndroidSignal:
    # Android signal numbers
    SIGHUP = 1
    SIGINT = 2
    SIGQUIT = 3
    SIGILL = 4
    SIGTRAP = 5
    SIGABRT = 6
    SIGBUS = 7
    SIGFPE = 8
    SIGKILL = 9
    SIGUSR1 = 10
    SIGSEGV = 11
    SIGUSR2 = 12
    SIGPIPE = 13
    SIGALRM = 14
    SIGTERM = 15
    SIGSTKFLT = 16
    SIGCHLD = 17
    SIGCONT = 18
    SIGSTOP = 19
    SIGTSTP = 20
    SIGTTIN = 21
    SIGTTOU = 22
    SIGURG = 23
    SIGXCPU = 24
    SIGXFSZ = 25
    SIGVTALRM = 26
    SIGPROF = 27
    SIGWINCH = 28
    SIGIO = 29
    SIGPWR = 30
    SIGSYS = 31

class ADBPopen:
    def __init__(self, shell, text=False, nonblocking=False):
        self.shell = shell
        self.text = text
        self.nonblocking = nonblocking
        self.stdin = _ADBPopenStdin(self, text, nonblocking)
        self.stdout = _ADBPopenStdout(self, text, nonblocking)
        self._status = None

        self._status_cond = threading.Condition()

    def _push_stdout(self, data):
        ''' Called by ADBShell '''
        self.stdout._push(data)

    def _notify_exit(self, status):
        ''' Called by ADBShell '''
        with self._status_cond:
            if status > 128:
                # Killed by signal
                status = 128-status

            self.stdout._push(None)
            self._status = status
            self._status_cond.notify_all()

    def poll(self):
        return self._status

    def wait(self):
        with self._status_cond:
            while self._status is None:
                self._status_cond.wait(1000)
            return self._status

    def communicate(self, input=None):
        if input:
            self.stdin.write(input)

        stderr = b''
        if self.text:
            stderr = stderr.decode()

        self.stdout.set_nonblocking(False)

        return (self.stdout.read(), stderr)

    def send_signal(self, signo):
        if signo in (signal.SIGINT, signal.SIGKILL, signal.SIGTERM):
            # XXX Ctrl+C seems to be the only thing we can send to kill a process...
            self.stdin._write(CTRL_C)

    def terminate(self):
        self.send_signal(signal.SIGTERM)

    def kill(self):
        self.send_signal(signal.SIGKILL)

    @property
    def pid(self):
        return 0

    @property
    def returncode(self):
        return self._status

class ADBShell:
    def __init__(self, opts=None):
        # Module objects are deleted at shutdown; retain a SIGHUP reference
        # so we can use it in __del__.
        self.SIGHUP = signal.SIGHUP

        cmd = ['adb']
        if opts:
            cmd.extend(opts)
        cmd += ['shell']

        self.proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
        fd = self.proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        prompt = b''
        start = time.time()
        while time.time() - start < 0.5:
            s = read_nonblock(self.proc.stdout)
            if not s:
                res = self.proc.poll()
                if res is not None:
                    raise OSError("Failed to start '%s': process returned %d" % (' '.join(cmd), res))
                time.sleep(0.01)
                continue
            prompt += s
            if prompt.endswith(b'$ ') or prompt.endswith(b'# '):
                break
            elif prompt.endswith(b'\x1b[6n'):
                # Device status report: we need to write the window size now (rows, cols)
                self.proc.stdin.write('\x1b[%d;%dR' % (10000000, 10000000))
                self.proc.stdin.flush()
                prompt = ''
        else:
            if prompt:
                warn("nonstandard prompt %r" % prompt.decode())
            else:
                warn("timed out waiting for prompt!")

        # remove restore-cursor command
        prompt = prompt.replace('\x1b8', '')
        m = re.match(br'^(\w+)@(\w+):(.*?) ([$#]) $', prompt)
        if m:
            self.user = m.group(1).decode()
            self.host = m.group(2).decode()
            self.cwd = m.group(3).decode()
            self.hash = m.group(4).decode()
            self.prompt = prompt
            self.prompt_re = re.compile((r'(?:(?P<status>\d+)\|)?(?P<user>%s|root)@%s:(?P<cwd>.*?) (?P<hash>[$#]) $' % (self.user, self.host)).encode())
        else:
            self.user = self.host = self.cwd = None
            for hash in [b'#', b'$']:
                if prompt.endswith(hash + b' '):
                    self.hash = hash
                    self.prompt_re = re.compile(re.escape(prompt[:-2]) + br'(?:(?P<status>\d+)\|)?(?P<hash>[$#]) $')
            else:
                self.hash = None
                self.prompt_re = re.compile(re.escape(prompt) + b'$')
                # Already warned about this prompt.

            if len(prompt) != 2:
                warn("unparsed prompt %r" % prompt.decode())

            self.prompt = prompt

        self._popen = None
        # XXX HACK: Prevent readline from messing with entered text
        self.execute('COLUMNS=10000000')

    def __del__(self):
        # Can also write '\n~.', a magic ssh-derived sequence that causes an immediate disconnect.
        self.proc.send_signal(self.SIGHUP)

    @staticmethod
    def _encode_command(cmd):
        if isinstance(cmd, list):
            cmd = ' '.join(shellquote(c) for c in cmd)
        return cmd.encode().strip(b'\r').strip(b'\n')

    def _send_command(self, cmd):
        cmd = self._encode_command(cmd)
        if b'\n' in cmd or b'\r' in cmd:
            warn("newline in command: results may not be correct")

        # Flush existing input
        read_nonblock(self.proc.stdout)

        self.proc.stdin.write(cmd + b'\n')
        self.proc.stdin.flush()

        # Assume PS2="> "
        expected = re.sub(br'[\r\n]', br'\r\r\n> ', cmd) + b'\r\r\n'

        collected = bytearray()
        while len(collected) < len(expected):
            s = read_timed(self.proc.stdout, timeout=0.5)
            if not s:
                raise IOError("timed out waiting for shell echo")
            collected.extend(s)

        if collected[:len(expected)] != expected:
            warn("expected %r, got %r" % (expected, collected[:len(expected)]))
        else:
            del collected[:len(expected)]

        return collected

    def execute(self, cmd, text=False):
        ''' Run the specified command through the shell and return the result.
        
        Raises ShellCommandException if the command returns an error code.'''

        if self._popen:
            raise Exception("popen instance is active; cannot execute commands.")

        collected = self._send_command(cmd)

        while True:
            m = re.search(self.prompt_re, collected)
            if m:
                break
            s = read_timed(self.proc.stdout, timeout=None)
            collected.extend(s)

        ret = collected[:m.start()].replace(b'\r\n', b'\n')

        d = m.groupdict()
        if d.get('status'):
            raise ShellCommandException(self._encode_command(cmd), int(d['status']), ret.decode())

        # Update prompt data
        for key in ['user', 'host', 'cwd', 'hash']:
            if key in d:
                setattr(self, key, d[key].decode())

        if text:
            return ret.decode()
        else:
            return ret

    def _popen_thread(self, prompt_collected):
        ''' Push received input to a popen instance and detect subprocess exit. '''
        first_run = True
        collected = bytearray()
        popen = self._popen

        while True:
            m = re.search(self.prompt_re, collected)
            if m:
                break

            if first_run:
                s = prompt_collected
                first_run = False
            else:
                s = read_timed(self.proc.stdout, timeout=0.1)

            if not s:
                # Flush everything: the prompt has not been seen yet
                if collected:
                    popen._push_stdout(collected.replace(b'\r\n', b'\n'))
                    del collected[:]
            else:
                # Flush everything up to and including the last newline
                collected.extend(s)
                pos = collected.rfind(b'\r\n')
                if pos >= 0:
                    pos += 2
                    popen._push_stdout(collected[:pos].replace(b'\r\n', b'\n'))
                    del collected[:pos]

        popen._push_stdout(collected[:m.start()].replace(b'\r\n', b'\n'))

        d = m.groupdict()
        if d.get('status'):
            status = int(d['status'])
        else:
            status = 0

        # Mark process as done
        self._popen = None
        popen._notify_exit(status)

        # Update prompt data
        for key in ['user', 'host', 'cwd', 'hash']:
            if key in d:
                setattr(self, key, d[key].decode())

    def popen(self, cmd, text=False, nonblocking=False):
        ''' Run the specified command, returning a Popen-like object.
        
        The resulting command can be interacted with through the returned object
        as if it were a local process.

        Note: The returned stdout may include stdin input. This is unavoidable
        because the remote shell operates in echo mode.

        Caveat: Do not attempt to run a subshell using popen, as it will
        interpret the shell prompt as meaning that the command has exited.
        Further, popen may break if you attempt to run a command that uses
        raw tty input (like a shell).
        '''

        if self._popen:
            raise Exception("another popen instance is already active!")

        collected = self._send_command(cmd)

        self._popen = ADBPopen(self, text=text, nonblocking=nonblocking)
        thread = threading.Thread(target=self._popen_thread, args=(collected,))
        thread.daemon = True
        thread.start()
        return self._popen

def test_popen(shell):
    p = shell.popen("cat", text=True)
    p.stdin.write("Hey")
    p.stdin.flush()
    p.stdin.close()
    print(p.stdout.read())
    print(p.wait())

def test_false(shell):
    shell.execute('false')

def test_getevent(shell):
    nlines = 100
    p = shell.popen('getevent -l', text=True)
    for i, line in enumerate(p.stdout):
        if i >= nlines:
            break
        print(line.strip())
    p.kill()
    p.wait()

def test_true(shell):
    shell.execute('true')

if __name__ == '__main__':
    import sys

    shell = ADBShell()
    test_popen(shell)
    try:
        test_false(shell)
    except ShellCommandException:
        pass

    test_getevent(shell)
    test_true(shell)
