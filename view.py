#!/usr/bin/env python3
import re
import os
import sys
import time
import errno
import logging
import argparse
from datetime import datetime
import drivers
import drivers.contacts
from contacts import ContactBook, Contact
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Parse many different formats and print events in an interleaved, chronological
manner."""
EPILOG = """Info on data formats:
"""


def make_argparser(drivers):
  parser = argparse.ArgumentParser(description=DESCRIPTION,
                                   epilog=EPILOG+format_driver_info(drivers),
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('-d', '--data', nargs=2, action='append', metavar=('FORMAT', 'PATH'),
    help='The input file/directory for a data source. Give two arguments: the format, and the path '
         'to the data. The available formats are: "'+'", "'.join(drivers.keys())+'".')
  parser.add_argument('-c', '--contacts', type=argparse.FileType('r'),
    help='Contacts file. At the moment, this only accepts the "Google CSV" format exported by '
         'Google Contacts.')
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
  parser.add_argument('-C', '--print-contacts', action='store_true',
    help='Just print all the contacts discovered in the input data.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  parser.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  parser.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  all_drivers = drivers.discover_drivers()
  parser = make_argparser(all_drivers)
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  for format, path in args.data:
    if format not in all_drivers:
      parser.print_help()
      fail(f'Driver for format {format!r} not found.')

  try:
    begin = int(args.begin)
  except ValueError:
    begin = human_time_to_timestamp(args.begin)
  try:
    end = int(args.end)
  except ValueError:
    end = human_time_to_timestamp(args.end)

  if args.contacts:
    contacts = drivers.contacts.get_contacts(args.contacts, 'google-browser-google-csv')
  else:
    contacts = ContactBook()
  parse_aliases(args.aliases, contacts)
  parse_mynumbers(args.mynumbers, contacts)

  # Read in the events from each dataset.
  events = []
  for format, path in args.data:
    # Load the driver.
    driver = all_drivers[format]
    # Check the path exists and looks right.
    path_type = 'file'
    if 'format' in driver and 'path_type' in driver['format']:
      path_type = driver['format']['path_type']
    verify_path(path, type=path_type)
    # Read the data.
    new_events = list(drivers.get_events(driver, path, contacts))
    logging.info(f"Found {len(new_events)} events in {driver['name']} data.")
    events.extend(new_events)

  sorted_events = sorted(events, key=lambda event: event.start)
  events = dedup_events(sorted_events)

  if not events:
    fail('Error: No events found! Make sure you provide at least one data source.')
  logging.warning(f'Found {len(events)} events.')

  if args.print_contacts:
    print(contacts.formatted())
    return

  current_day_stamp = None
  for event in events:
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


def format_driver_info(drivers):
  descriptions = []
  for name, driver in drivers.items():
    if 'human' not in driver:
      continue
    if 'name' in driver['human']:
      human_name_str = f" ({driver['human']['name']})"
    else:
      human_name_str = ''
    if 'path' in driver['human']:
      path_str = f": Give {driver['human']['path']}."
    else:
      path_str = ''
    if not (human_name_str or path_str):
      continue
    descriptions.append(f'{name!r}{human_name_str}{path_str}')
  return '\n'.join(descriptions)


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


def dedup_events(old_events):
  """Remove duplicate events from a sorted list."""
  duplicates = 0
  new_events = []
  last_event = None
  for event in old_events:
    if last_event is None:
      duplicate = False
    else:
      duplicate = event == last_event
    if duplicate:
      duplicates += 1
    else:
      new_events.append(event)
      last_event = event
  if duplicates:
    logging.warning('Removed {} duplicate events.'.format(duplicates))
  return new_events


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
