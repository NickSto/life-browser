#!/usr/bin/env python3
import os
import sys
import time
import errno
import logging
import argparse
from datetime import datetime
import Event
from drivers import hangouts
from drivers import voice
assert sys.version_info.major >= 3, 'Python 3 required'

#TODO: Load the drivers and use them to parse the files and slice, dice, and filter the events.

DESCRIPTION = """Parse many different formats and print events in an interleaved, chronological
manner."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('--hangouts', nargs='+',
    help='Google Hangouts data. Give any number of files (.json, .json.gz, Google Takeout .zip '
         'or tarball)')
  parser.add_argument('--voice', nargs='+',
    help='Google Voice data. Give any number of paths to the Voice directory of unzipped Takeout '
         'data.')
  parser.add_argument('-s', '--start', default=0,
    help='Only show events from after this timestamp or date ("YYYY-MM-DD" or '
         '"YYYY-MM-DD HH:MM:DD"). If the date doesn\'t include a time, it\'s assumed to be the '
         'start of that day.')
  parser.add_argument('-e', '--end', default=9999999999,
    help='Only events from before this timestamp or date (see --start for format).')
  # parser.add_argument('-p', '--person',
  #   help='Only show events involving this person. This can be a fuzzy match. If any part of a '
  #        'participant\'s name matches this (case-insensitive), it\'s considered a hit.')
  # parser.add_argument('--exact-person', action='store_true',
  #   help='Make --person require an exact match. It\'s still case-insensitive.')
  parser.add_argument('-a', '--aliases', default='',
    help='Comma-separated key=values.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  parser.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  parser.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  tone_down_logger()

  try:
    start = int(args.start)
  except ValueError:
    start = human_time_to_timestamp(args.start)
  try:
    end = int(args.end)
  except ValueError:
    end = human_time_to_timestamp(args.end)

  aliases = parse_aliases(args.aliases)

  events = []

  if args.hangouts:
    verify_paths(args.hangouts)
    events.extend(Event.make_events(hangouts, args.hangouts))

  if args.voice:
    verify_paths(args.voice, type='dirs')
    events.extend(Event.make_events(voice, args.voice))

  current_day_stamp = None
  for event in sorted(events, key=lambda e: e.timestamp):
    if event.timestamp < start or event.timestamp > end:
      continue
    if current_day_stamp is None or event.timestamp > current_day_stamp + 24*60*60:
      current_day_stamp = get_day_start(event.timestamp)
      dt = datetime.fromtimestamp(current_day_stamp)
      date = dt.strftime('%a, {:2d} %b %Y').format(dt.day)
      print('========== '+date+' ==========')
    print_event(event, aliases)


def human_time_to_timestamp(human_time):
  try:
    dt = datetime.strptime(human_time, '%Y-%m-%d %H:%M:%S')
  except ValueError:
    dt = datetime.strptime(human_time + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
  return int(time.mktime(dt.timetuple()))


def parse_aliases(aliases_str):
  aliases = {}
  for keyvalue in aliases_str.split(','):
    try:
      alias, name = keyvalue.split('=')
    except ValueError:
      continue
    aliases[alias] = name
  return aliases


def verify_paths(paths, type='files'):
  for path in paths:
    if type == 'files' and not os.path.isfile(path):
      fail('Error: File not found or not a regular file: "{}".'.format(path))
    if type == 'dirs' and not os.path.isdir(path):
      fail('Error: Directory not found or not a directory: "{}".'.format(path))


def get_day_start(timestamp):
  dt = datetime.fromtimestamp(timestamp)
  day_start_dt = datetime(dt.year, dt.month, dt.day)
  return int(time.mktime(day_start_dt.timetuple()))


def print_event(event, aliases):
  time_str = datetime.fromtimestamp(event.timestamp).strftime('%H:%M:%S')
  if event.type == 'hangouts' or event.type == 'voice':
    if event.subtype == 'chat':
      subtype = ' Chat:'
    elif event.subtype == 'sms':
      subtype = ' SMS:'
    else:
      subtype = ':'
    recipients = []
    for recipient in event.recipients:
      recipients.append(aliases.get(recipient, recipient))
    print('{timestamp}{type} {sender} -> {recipients}: {message}'.format(
      timestamp=time_str,
      type=subtype,
      sender=aliases.get(event.sender, event.sender),
      recipients=', '.join(recipients),
      message=event.message
    ))


def tone_down_logger():
  """Change the logging level names from all-caps to capitalized lowercase.
  E.g. "WARNING" -> "Warning" (turn down the volume a bit in your log files)"""
  for level in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG):
    level_name = logging.getLevelName(level)
    logging.addLevelName(level, level_name.capitalize())


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except IOError as ioe:
    if ioe.errno != errno.EPIPE:
      raise
