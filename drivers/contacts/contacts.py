#!/usr/bin/env python3
import argparse
import logging
import vobject
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('contacts', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  contacts_str = ''.join(fix_format(args.contacts))

  for vcard in vobject.readComponents(contacts_str):
    names = vcard.contents.get('fn')
    if names:
      print(names[0].value)


def fix_format(lines):
  """Workarounds for some non-standard quirks in Google Contacts vCard files."""
  # Google's VCF files include fields named "ADR;ENCODING=QUOTED-PRINTABLE".
  # The values are encoded strings which can be multi-line.
  # vobject doesn't like that, and fails. This is a workaround.
  quoted = False
  for line in lines:
    # Fix empty TEL type field issue.
    if line.startswith('TEL;:'):
      line = 'TEL;CUSTOM:'+line[5:]
    # Fix multi-line value indenting issue.
    indent = False
    if quoted:
      if line.startswith('=') or line.startswith(';'):
        indent = True
      else:
        quoted = False
    if not quoted:
      fields = line.split(';')
      for field in fields:
        if 'ENCODING=QUOTED-PRINTABLE' in field.split(':'):
          quoted = True
    if indent:
      yield ' '+line
    else:
      yield line


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
