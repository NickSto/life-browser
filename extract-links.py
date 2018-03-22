#!/usr/bin/env python3
import argparse
import collections
import logging
import sys
import urllib.parse
assert sys.version_info.major >= 3, 'Python 3 required'
from drivers.hangouts import hangouts

DESCRIPTION = """Extract all links from Hangouts conversations.
This finds all urls sent in Hangouts messages that Google recognized, and prints them
(one per line)."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('archive',
    help='The Hangouts Takeout file.')
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

  data = hangouts.extract_data(args.archive)
  if data is None:
    fail('No Hangouts data found!')

  convos = hangouts.read_hangouts(data)

  for convo in convos:
    for event in convo.events:
      for link in event.links:
        print(link)


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
