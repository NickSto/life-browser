#!/usr/bin/env python3
import argparse
import csv
import logging
import pathlib
import sys
assert sys.version_info.major >= 3, 'Python 3 required'
try:
  from contacts import ContactBook, Contact
except ImportError:
  root = pathlib.Path(__file__).resolve().parent.parent.parent
  sys.path.insert(0, str(root))
  from contacts import ContactBook, Contact


DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('contacts', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='')
  parser.add_argument('-n', '--name',
    help='Find this person and print their whole contact info.')
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

  for contact in get_contacts(args.contacts):
    if args.name:
      if contact.name and contact.name.lower() == args.name.lower():
        print(contact.format())
    else:
      print(contact)


def get_contacts(csv_file):
  #TODO: Allow adding to existing ContactBook.
  book = ContactBook()
  #TODO: Some special handling for phone numbers, emails, addresses to put the preferred one first.
  for row in read_csv(csv_file):
    contact = Contact()
    # Name
    if row.get('Name'):
      contact.name = row['Name']
    elif row.get('Organization 1 - Name'):
      contact.name = row['Organization 1 - Name']
    # Phone numbers
    parse_values(row, contact, 'phones', 'Phone', converter=Contact.normalize_phone)
    # Emails
    parse_values(row, contact, 'emails', 'E-mail')
    # Addresses
    parse_values(row, contact, 'addresses', 'Address', value_label='Formatted')
    # Organization
    parse_values(row, contact, 'organizations', 'Organization', value_label='Name')
    # Relationship
    # Note: There are instances where there's no Type, but there is a Value.
    # But currently no instances where there's a Value but no Type.
    parse_values(row, contact, 'relations', 'Relation')
    # Note
    if row.get('Note'):
      contact['notes'].add(row['Notes'])
    book.add(contact)
  return book


def parse_values(row, contact, key, name, value_label='Value', converter=None):
  i = 1
  while row.get(f'{name} {i} - Type') or row.get(f'{name} {i} - {value_label}'):
    label = row.get(f'{name} {i} - Type', '')
    if not label.strip():
      label = None
    for value in split_values(row.get(f'{name} {i} - {value_label}')):
      if converter:
        value = converter(value)
      contact[key].add(value, label=label)
    i += 1


def read_csv(csv_file):
  header = None
  for fields in csv.reader(csv_file):
    if header is None:
      header = fields
    else:
      row = {}
      assert len(header) == len(fields)
      for label, value in zip(header, fields):
        row[label] = value
      yield row


def split_values(raw_value):
  if raw_value is None:
    return []
  else:
    return raw_value.split(' ::: ')


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
