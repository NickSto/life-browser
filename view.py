#!/usr/bin/env python3
import re
import os
import sys
import imp
import time
import errno
import logging
import argparse
from datetime import datetime
import drivers
from contacts import ContactBook, Contact
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
  parser.add_argument('-c', '--print-contacts', action='store_true',
    help='Just print all the contacts discovered in the input data.')
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

  try:
    begin = int(args.begin)
  except ValueError:
    begin = human_time_to_timestamp(args.begin)
  try:
    end = int(args.end)
  except ValueError:
    end = human_time_to_timestamp(args.end)

  contacts = ContactBook()
  parse_aliases(args.aliases, contacts)
  parse_mynumbers(args.mynumbers, contacts)

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
    # Read the data.
    events.extend(driver.get_events(path, contacts=contacts))

  if not events:
    fail('Error: No events! Make sure you provide at least one data source.')

  if args.print_contacts:
    print(contacts.formatted())
    return

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
    print(event)


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


def parse_aliases(aliases_str, contacts):
  if not aliases_str:
    return
  for keyvalue in aliases_str.split(','):
    try:
      alias, name = keyvalue.split('=')
    except ValueError:
      continue
    if re.search(r'^\d{19,23}$', alias):
      contact = Contact(name=name, gaia_id=alias)
      contact['gaia_id'].indexable = True
    elif re.search(r'[0-9+() -]{7,25}', alias) and 7 <= len(re.sub(r'[^0-9]', '', alias)) <= 18:
      phone = Contact.normalize_phone(alias)
      contact = Contact(name=name, phone=phone)
    elif re.search(r'[^:/]+@[a-zA-Z0-9.-]+', alias):
      contact = Contact(name=name, email=alias)
    else:
      fail('Unrecognized alias type: {!r}'.format(alias))
    contacts.add_or_merge(contact)


def parse_mynumbers(mynumbers_str, contacts):
  if not mynumbers_str:
    return
  for number in mynumbers_str.split(','):
    phone = Contact.normalize_phone(number)
    if phone not in contacts.me['phones']:
      contacts.me['phones'].append(phone)


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
  if event.sender and event.sender.name:
    participants = [event.sender.name.value.lower()]
  if event.recipients:
    participants.extend([p.name.value.lower() for p in event.recipients if p.name])
  if exact_person:
    if person.lower() in participants:
      return True
  else:
    for participant in participants:
      if person.lower() in participant:
        return True
  return False


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
