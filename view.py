#!/usr/bin/env python3
import os
import sys
import imp
import time
import errno
import logging
import argparse
from datetime import datetime
import drivers
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Parse many different formats and print events in an interleaved, chronological
manner."""
EPILOG = """Info on data formats:
"""


def make_argparser():
  driver_names = discover_drivers()
  parser = argparse.ArgumentParser(description=DESCRIPTION,
                                   epilog=EPILOG+format_driver_info(driver_names),
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('-d', '--data', nargs=2, action='append', metavar=('FORMAT', 'PATH'),
    help='The input file/directory for a data source. Give two arguments: the format, and the path '
         'to the data. The available formats are: "'+'", "'.join(driver_names)+'".')
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

  # Read in the events from each dataset.
  events = []
  for format, path in args.data:
    # Load the driver.
    driver = load_driver(format)
    # Check the path exists and looks right.
    path_type = 'file'
    if hasattr(driver, 'METADATA') and 'format' in driver.METADATA:
      path_type = driver.METADATA['format'].get('path_type', path_type)
    verify_path(path, type=path_type)
    # Add any special-case arguments.
    kwargs = {}
    if format == 'voice':
      if args.mynumbers is None:
        kwargs['mynumbers'] = []
      else:
        kwargs['mynumbers'] = args.mynumbers.split(',')
    # Read the data.
    events.extend(driver.get_events(path, **kwargs))

  if not events:
    fail('Error: No events! Make sure you provide at least one data source.')

  current_day_stamp = None
  for event in sorted(events, key=lambda e: e.start):
    if event.start < begin or event.start > end:
      continue
    if args.person and not person_match(event, args.person, args.exact_person):
      continue
    if current_day_stamp is None or event.start > current_day_stamp + 24*60*60:
      current_day_stamp = get_day_start(event.start)
      dt = datetime.fromtimestamp(current_day_stamp)
      date = dt.strftime('%a, {:2d} %b %Y').format(dt.day)
      print('========== '+date+' ==========')
    print_event(event, aliases)


def discover_drivers():
  driver_names = []
  parent = drivers.__path__[0]
  for candidate in os.listdir(parent):
    if os.path.isfile(os.path.join(parent, candidate, '__init__.py')):
      driver_names.append(candidate)
  return driver_names


def format_driver_info(driver_names):
  descriptions = []
  for driver_name in driver_names:
    driver = load_driver(driver_name)
    description = '"'+driver_name+'"'
    if not hasattr(driver, 'METADATA') or 'human' not in driver.METADATA:
      descriptions.append(description)
      continue
    human_strings = driver.METADATA['human']
    if 'name' in human_strings:
      description += ' ({name})'.format(**human_strings)
    if 'path' in human_strings:
      description += ': Give {path}.'.format(**human_strings)
    descriptions.append(description)
  return '\n'.join(descriptions)


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


def verify_path(path, type='file'):
  if type == 'file' and not os.path.isfile(path):
    fail('Error: File not found or not a regular file: "{}".'.format(path))
  if type == 'dir' and not os.path.isdir(path):
    fail('Error: Directory not found or not a directory: "{}".'.format(path))
  if type == 'either' and not (os.path.isfile(path) or os.path.isdir(path)):
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
  time_str = datetime.fromtimestamp(event.start).strftime('%H:%M:%S')
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
    print('{start}{type} {sender} -> {recipients}: {message}'.format(
      start=time_str,
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
