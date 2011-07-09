# Copyright 2009-2011 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A mock version of the ssh binary that actually manipulates the
filesystem. This imitates only things that mrjob actually uses.

Relies on these environment variables:
MOCK_SSH_ROOTS -- specify directories for hosts in the form:
                  host1=/tmp/dir1:host2=/tmp/dir2
MOCK_SSH_VERIFY_KEY_FILE -- set to 'true' if the script should print an error
                            when the key file does not exist

This is designed to run as: python -m tests.mockssh <ssh args>

mrjob requires a single binary (no args) to stand in for ssh, so
use create_mock_hadoop_script() to write out a shell script that runs
mockssh.
"""

from __future__ import with_statement

import glob
import logging
import os
import pipes
import posixpath
import shutil
import sys

from mrjob import ssh


def create_mock_ssh_script(path):
    """Dump a wrapper script to the given file object that runs this
    python script."""
    # make this work even if $PATH or $PYTHONPATH changes
    with open(path, 'w') as f:
        f.write('#!/bin/sh\n')
        f.write('%s %s "$@"\n' % (
            pipes.quote(sys.executable),
            pipes.quote(os.path.abspath(__file__))))
    os.chmod(path, stat.S_IREAD | stat.S_IEXEC)


def path_for_host(host):
    """Get the filesystem path that the given host is being faked at"""
    for kv_pair in os.environ['MOCK_SSH_ROOTS'].split(':'):
        this_host, this_path = kv_pair.split('=')
        if this_host == host:
            return os.path.abspath(this_path)
    raise KeyError('Host %s is not specified in $MOCK_SSH_ROOTS' % host)


def make_empty_files(host, paths):
    """Touch files quickly"""
    root = path_for_host(host)
    for path in paths:
        directory, filename = os.path.split(path)
        os.makedirs(directory)
        with open(path, 'w') as f:
            pass


def slave_addresses():
    """Get the addresses for slaves based on :envvar:`MOCK_SSH_ROOTS`"""
    for kv_pair in os.environ['MOCK_SSH_ROOTS'].split(':'):
        this_host, this_path = kv_pair.split('=')
        if '!' in this_host:
            yield this_host


def receive_poor_mans_scp(host, args):
    cat_cmd = args[2]
    dest = cat_cmd.split(' > ')[1]
    with open(os.path.join(path_for_host(host), dest), 'r') as f:
        f.writelines(sys.stdin)


def ls(host, args):
    full_path = os.path.join(path_for_host(host), args[1])
    for root, dirs, files in os.walk(full_path):
        components = root.split('/')
        new_root = posixpath.join(components)
        for filename in files:
            print posixpath.join(new_root, filename)


def cat(host, args):
    full_path = os.path.join(path_for_host(host), args[1])
    with open(full_path, 'r') as f:
        print f.read()


def run(host, remote_args, slave_key_file=None):
    remote_arg_pos = 0

    if remote_args[0] == 'hadoop':
        print '\n'.join(slave_addresses())
    elif remote_args[0] == 'bash':
        receive_poor_mans_scp(host, remote_args)
    elif remote_args[0] == 'find':
        ls(host, remote_args)
    elif remote_args[0] == 'cat':
        cat(host, remote_args)
    elif remote_args[0] == 'ssh':
        while not remote_args[remote_arg_pos] == '-i':
            remote_arg_pos += 1

        slave_key_file = remote_args[remote_arg_pos+1]

        while not remote_args[remote_arg_pos].startswith('hadoop@'):
            remote_arg_pos += 1

        slave_host = host + '!%s' % remote_args[remote_arg_pos]

        # don't let slave SSH work unleses the key file is properly copied
        if not os.path.exists(os.path.join(path_for_host(slave_host), slave_key_file)):
            print >> sys.stderr, 'Warning: Identity file',
                slave_key_file, 'not accessible: No such file or directory.'
            print >> sys.stderr, 'Permission denied (publickey).'
            sys.exit(1)

        # build bang path
        run(slave_host,
            remote_args[remote_arg_pos+1:],
            slave_key_file)


def main():
    args = sys.argv

    # Find where the user's commands begin
    arg_pos = 0

    # skip to key file path
    while args[arg_pos] != '-i':
        arg_pos += 1

    arg_pos += 1

    # verify existence of key pair file if necessary
    if os.environ.get('MOCK_SSH_VERIFY_KEY_FILE', 'false') == 'true' \
       and not os.path.exists(args[arg_pos]):
        print >> sys.stderr, 'Warning: Identity file',
            args[arg_pos], 'not accessible: No such file or directory.'
        sys.exit(1)

    # skip to host address
    while not args[arg_pos].startswith('hadoop@'):
        arg_pos += 1

    host = args[arg_pos].split('@')[1]

    # the rest are arguments are what to run on the remote machine

    arg_pos += 1
    run(host, args[arg_pos:])


if __name__ == '__main__':
    main()
