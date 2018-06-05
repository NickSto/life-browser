#!/usr/bin/env python3
import os
import sys
import imp
import time
import errno
import logging
import argparse
from datetime import datetime
import Event
import drivers
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Parse many different formats and print events in an interleaved, chronological
manner."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('-s', '--stream', nargs=2, action='append', dest='streams',
    metavar=('FORMAT', 'PATH'),
    help='The source file(s) for a stream of data. Give two arguments: the format, and the path to '
         'the data.')
  parser.add_argument('-b', '--begin', default=0,
    help='Only show events from after this timestamp or date ("YYYY-MM-DD" or '
         '"YYYY-MM-DD HH:MM:DD"). If the date doesn\'t include a time, it\'s assumed to be the '
         'start of that day.')
  parser.add_argument('-e', '--end', default=9999999999,
    help='Only events from before this timestamp or date (see --begin for format).')
  parser.add_argument('-p', '--person',
    help='Only show events involving this person. This can be a fuzzy match. If any part of a '
         'participant\'s name matches this (case-insensitive), it\'s considered a hit.')
  parser.add_argument('--exact-person', action='store_true',
    help='Make --person require an exact match. It\'s still case-insensitive.')
  parser.add_argument('--mynumbers',
    help='Your phone numbers, to help identify yourself in conversations. comma-separated list.')
  parser.add_argument('-a', '--aliases', default='',
    help='Aliases for people. Use this to convert phone numbers or Google identifiers to a name. '
         'Give comma-separated key=values.')
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
    begin = int(args.begin)
  except ValueError:
    begin = human_time_to_timestamp(args.begin)
  try:
    end = int(args.end)
  except ValueError:
    end = human_time_to_timestamp(args.end)

  aliases = parse_aliases(args.aliases)

  events = []
  for format, path in args.streams:
    driver = load_driver(format)
    kwargs = {}
    path_type = 'files'
    if format == 'voice':
      path_type = 'both'
      if args.mynumbers is None:
        kwargs['mynumbers'] = []
      else:
        kwargs['mynumbers'] = args.mynumbers.split(',')
    verify_paths((path,), type=path_type)
    events.extend(Event.make_events(driver, (path,), **kwargs))

  if not events:
    fail('Error: No events! Make sure you provide at least one data source.')

  current_day_stamp = None
  for event in sorted(events, key=lambda e: e.timestamp):
    if event.timestamp < begin or event.timestamp > end:
      continue
    if args.person and not person_match(event, args.person, args.exact_person):
      continue
    if current_day_stamp is None or event.timestamp > current_day_stamp + 24*60*60:
      current_day_stamp = get_day_start(event.timestamp)
      dt = datetime.fromtimestamp(current_day_stamp)
      date = dt.strftime('%a, {:2d} %b %Y').format(dt.day)
      print('========== '+date+' ==========')
    print_event(event, aliases)


def load_driver(format):
  try:
    file, path, desc = imp.find_module(format, drivers.__path__)
  except ImportError:
    fail('Error: No driver found for format {!r}.'.format(format))
  try:
    return imp.load_module('drivers.'+format, file, path, desc)
  finally:
    if file is not None:
      file.close()


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
    if type == 'both' and not (os.path.isfile(path) or os.path.isdir(path)):
      fail('Error: Path not found or invalid path: "{}".'.format(path))


def get_day_start(timestamp):
  dt = datetime.fromtimestamp(timestamp)
  day_start_dt = datetime(dt.year, dt.month, dt.day)
  return int(time.mktime(day_start_dt.timetuple()))


def person_match(event, person, exact_person=False):
  participants = []
  if event.sender:
    participants.append(event.sender.lower())
  if event.recipients:
    participants.extend([p.lower() for p in event.recipients])
  if exact_person:
    if person.lower() in participants:
      return True
  else:
    for participant in participants:
      if person.lower() in participant:
        return True
  return False


def print_event(event, aliases):
  time_str = datetime.fromtimestamp(event.timestamp).strftime('%H:%M:%S')
  if event.format == 'hangouts' or event.format == 'voice':
    if event.stream == 'chat':
      stream = ' Chat:'
    elif event.stream == 'sms':
      stream = ' SMS:'
    else:
      stream = ':'
    recipients = []
    for recipient in event.recipients:
      recipients.append(aliases.get(recipient, recipient))
    print('{timestamp}{type} {sender} -> {recipients}: {message}'.format(
      timestamp=time_str,
      type=stream,
      sender=aliases.get(event.sender, event.sender),
      recipients=', '.join(list(set(recipients))),
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
