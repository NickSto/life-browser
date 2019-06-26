#!/usr/bin/env python3
"""Parser for Google's location history export KML format."""
import argparse
import logging
import sys
import kml

def parse(kml_tree):
  # <kml>
  if len(kml_tree) != 1:
    logging.warning('Warning: <kml> element contained {} children.'.format(len(kml_tree)))
    return None
  # <Document>
  if kml_tree[0].tag != '{http://www.opengis.net/kml/2.2}Document' or len(kml_tree[0]) != 1:
    logging.warning('Warning: <Document> element not found or contained {} children.'
                    .format(len(kml_tree[0])))
    return None
  # <Placemark>
  if kml_tree[0][0].tag != '{http://www.opengis.net/kml/2.2}Placemark' or len(kml_tree[0][0]) < 1:
    logging.warning('Warning: <Placemark> element not found or contained {} children.'
                    .format(len(kml_tree[0])))
    return None
  distance = kml.parse_track(kml_tree[0][0])
  return distance

def make_argparser():
  parser = argparse.ArgumentParser(description='Parse a .kml or .kmz track.')
  parser.add_argument('kml', metavar='kml/kmz',
    help='The .kml or .kmz file(s).')
  parser.add_argument('-k', '--key',
    help='Print the value of this key from the metadata.')
  parser.add_argument('-l', '--key-len',
    help='Print the length of this value for this key from the metadata.')
  parser.add_argument('-L', '--log', type=argparse.FileType('w'), default=sys.stderr,
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
  if args.kml.endswith('.kmz'):
    kml_tree = kml.read_kmz(args.kml)
  else:
    kml_tree = kml.read_kml(args.kml)
  distance = parse(kml_tree)
  if distance is None:
    fail('Error: Did not find location data.')
  else:
    print(round(distance*0.6213))

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