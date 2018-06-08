#!/usr/bin/env python3
import argparse
import csv
import logging
import sys
assert sys.version_info.major >= 3, 'Python 3 required'
try:
  from contacts import ContactBook, Contact, ContactValues, ContactValue
except ImportError:
  pass


DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('contacts', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='')
  parser.add_argument('-n', '--name',
    help='Print the whole contact info for this person.')
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

  for row in read_csv(args.contacts):
    print(row['Name'])


def get_contacts(csv_file):
  #TODO: Allow adding to existing ContactBook.
  contacts = ContactBook()
  #TODO: Some special handling for phone numbers, emails, addresses to put the preferred one first.
  for row in read_csv(csv_file):
    contact = Contact()
    # Name
    if row.get('Name'):
      contact.name = row['Name']
    elif row.get('Organization 1 - Name'):
      contact.name = row['Organization 1 - Name']
    # Phone numbers
    i = 1
    while row.get('Phone {} - Value'.format(i)):
      type = row['Phone {} - Type'.format(i)]
      for value in split_values(row.get('Phone {} - Value'.format(i))):
        value = Contact.normalize_phone(value)
        contact_value = ContactValue(value=value, attributes={'type':type})
        contact['phones'].append(contact_value)
      i += 1
    # Emails
    i = 1
    while row.get('E-mail {} - Value'.format(i)):
      type = row['E-mail {} - Type'.format(i)]
      for value in split_values(row.get('E-mail {} - Value'.format(i))):
        contact_value = ContactValue(value=value, attributes={'type':type})
        contact['emails'].append(contact_value)
      i += 1
    # Addresses
    i = 1
    while row.get('Address {} - Formatted'.format(i)):
      if 'addresses' not in contact:
        contact['addresses'] = ContactValues(contact=contact, key='addresses')
      type = row['Address {} - Type'.format(i)]
      for value in split_values(row.get('Address {} - Formatted'.format(i))):
        contact_value = ContactValue(value=value, attributes={'type':type})
        contact['addresses'].append(contact_value)
      i += 1
    # Organization
    if row.get('Organization 1 - Name'):
      contact['organization'] = row['Organization 1 - Name']
    # Relationship
    if row.get('Relationship 1 - Value') or row.get('Relationship 1 - Type'):
      type = row.get('Relationship 1 - Type')
      value = row.get('Relationship 1 - Value') or type
      contact_value = ContactValue(contact=contact, key='relationship', value=value)
      if type:
        contact_value.attributes['type'] = type
      contact['relationship'] = contact_value
    # Note
    if row.get('Note'):
      contact['note'] = row['Notes']
    contacts.add(contact)
  return contacts


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
