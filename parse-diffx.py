#!/usr/bin/env python

from __future__ import unicode_literals

import pprint
import re
import sys
from collections import OrderedDict

import yaml


class DiffParseError(ValueError):
    pass


class DiffX(object):
    def __init__(self, options={}):
        self.options = options
        self.preamble = None
        self.preamble_options = {}
        self.meta = {}
        self.meta_options = {}
        self.changes = []

    def serialize(self):
        return {
            'options': self.options,
            'preamble': self.preamble,
            'preamble_options': self.preamble_options,
            'meta': self.meta,
            'meta_options': self.meta_options,
            'changes': [
                change.serialize()
                for change in self.changes
            ]
        }


class DiffXChange(object):
    def __init__(self, options={}):
        self.options = options
        self.preamble = None
        self.preamble_options = {}
        self.meta = {}
        self.meta_options = {}
        self.files = []

    def serialize(self):
        return {
            'options': self.options,
            'preamble': self.preamble,
            'preamble_options': self.preamble_options,
            'meta': self.meta,
            'meta_options': self.meta_options,
            'files': [
                file.serialize()
                for file in self.files
            ]
        }


class DiffXFile(object):
    def __init__(self, options={}):
        self.options = options
        self.meta = {}
        self.meta_options = {}
        self.diff = None
        self.diff_options = {}

    def serialize(self):
        return {
            'options': self.options,
            'meta': self.meta,
            'meta_options': self.meta_options,
            'diff': self.diff,
            'diff_options': self.diff_options,
        }


class DiffXParser(object):
    def __init__(self):
        pass

    def parse(self, filename):
        with open(filename, 'r') as fp:
            data = fp.read()

        i = data.find(b'\n')

        if i != -1:
            diffx_line = data[:i]
        else:
            diffx_line = b''

        if not diffx_line.startswith(b'#diffx:'):
            raise DiffParseError('Missing "#diffx:" header');

        diffx = DiffX(self._parse_section_line(diffx_line)[1])
        encoding = diffx.options.get('encoding')

        sections = self._parse_sections(data.splitlines())

        for section in sections:
            name = section['name']

            if name == 'change':
                diffx.changes.append(
                    self._process_change_section(section, encoding))
            elif name == 'preamble':
                diffx.preamble_options = section['opts']
                diffx.preamble = self._process_text(
                    content, diffx.preamble_options, encoding)
            elif name == 'meta':
                diffx.meta_options = section['opts']
                diffx.meta = self._process_meta(
                    content, diffx.meta_options, encoding)
            else:
                sys.stderr.write('Unexpected top-level section "%s"\n' % name)

        return diffx

    def _process_change_section(self, section, default_encoding):
        diffx_change = DiffXChange(options=section['opts'])
        default_encoding = (diffx_change.options.get('encoding') or
                            default_encoding)

        for subsection in section['sections']:
            name = subsection['name']
            content = b'\n'.join(subsection['lines'])

            if name == 'file':
                diffx_change.files.append(
                    self._process_file_section(subsection, default_encoding))
            elif name == 'preamble':
                diffx_change.preamble_options = subsection['opts']
                diffx_change.preamble = self._process_text(
                    content, diffx_change.preamble_options, default_encoding)
            elif name == 'meta':
                diffx_change.meta_options = subsection['opts']
                diffx_change.meta = self._process_meta(
                    content, diffx_change.meta_options, default_encoding)
            else:
                sys.stderr.write('Unexpected section "change.%s"\n' % name)

        return diffx_change

    def _process_file_section(self, section, default_encoding):
        diffx_file = DiffXFile(options=section['opts'])
        default_encoding = (diffx_file.options.get('encoding') or
                            default_encoding)

        for subsection in section['sections']:
            name = subsection['name']
            content = b'\n'.join(subsection['lines'])

            if name == 'meta':
                diffx_file.meta_options = subsection['opts']
                diffx_file.meta = self._process_meta(
                    content, diffx_file.meta_options, default_encoding)
            elif name == 'diff':
                diffx_file.diff_options = subsection['opts']
                diffx_file.diff = self._process_text(
                    content, diffx_file.diff_options, default_encoding)
            else:
                sys.stderr.write('Unexpected section "change.file.%s"\n'
                                 % name)

        return diffx_file

    def _process_meta(self, content, options, default_encoding):
        content = self._process_text(content, options, default_encoding)
        meta_format = options.get('format', 'yaml')

        if meta_format == 'yaml':
            return yaml.load(content)
        else:
            sys.stderr.write('Unexpected meta format "%s"\n' % meta_format)

    def _process_text(self, text, options, default_encoding):
        encoding = options.get('encoding', default_encoding)

        if encoding:
            return text.decode(encoding)
        else:
            return text

    def _parse_section_line(self, line):
        if not line.startswith(b'#'):
            raise ValueError('Not a section')

        header, opts_str = line.split(b':', 1)
        opts_str = opts_str.strip()
        opts = {}

        if opts_str:
            for opt_pair in opts_str.strip().split(b','):
                if opt_pair:
                    key, value = opt_pair.decode('utf-8').split(b'=', 1)
                    opts[key.strip()] = value.strip()

        return header.lstrip(b'#.'), opts

    def _parse_sections(self, lines, level=0):
        section_re = re.compile(br'^#(?P<level>\.+)[A-Za-z0-9_-]+:')
        top_sections = []
        section_stack = []
        cur_section = None

        for line in lines:
            m = section_re.match(line)

            if m:
                section_name, section_opts = self._parse_section_line(line)
                level = len(m.group('level'))
                prev_section = cur_section

                cur_section = {
                    'name': section_name,
                    'opts': section_opts,
                    'sections': [],
                    'lines': [],
                }

                if level == 1:
                    top_sections.append(cur_section)

                if prev_section:
                    prev_level = len(section_stack)

                    if level <= prev_level:
                        section_stack.pop()

                        if level < prev_level:
                            section_stack.pop()

                    if level > 1:
                        section_stack[-1]['sections'].append(cur_section)

                section_stack.append(cur_section)
            elif cur_section:
                cur_section['lines'].append(line)

        return top_sections


if __name__ == '__main__':
    parser = DiffXParser()

    diffx_data = parser.parse(sys.argv[1])

    pprint.pprint(diffx_data.serialize())
