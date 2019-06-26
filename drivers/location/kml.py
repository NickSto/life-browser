#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import sys
import zipfile
import dateutil.parser
import defusedxml.ElementTree


def read_kml(kml_path):
  """Give the path to a .kml file or an open filehandle and this will return an ElementTree.
  The ElementTree will be from defusedxml."""
  tree = defusedxml.ElementTree.parse(kml_path)
  return tree.getroot()


def read_kmz(kmz_path):
  """Give the path to a .kmz file and this will return an ElementTree of the doc.kml.
  The ElementTree will be from defusedxml."""
  kmz_file = zipfile.ZipFile(kmz_path, 'r')
  kml_string = kmz_file.open('doc.kml', 'r').read()
  return defusedxml.ElementTree.fromstring(kml_string)


def parse(kml):
  meta = {'subformat':None, 'title':None, 'description':None, 'start':None, 'end':None}
  markers = []
  # <kml> = kml
  if len(kml) == 0:
    return None
  # <Document> = kml[0]
  for element in kml[0]:
    if len(element) == 0:
      continue
    # <atom:author>
    elif (element.tag == '{http://www.w3.org/2005/Atom}author' and
        element[0].tag == '{http://www.w3.org/2005/Atom}name'):
      name = element[0].text
      if name == 'Created by Google My Tracks on Android':
        meta['subformat'] = 'mytracks'
      elif name == 'Recorded in Geo Tracker for Android from Ilya Bogdanovich':
        meta['subformat'] = 'geotracker'
    # <Folder>
    elif (element.tag == '{http://www.opengis.net/kml/2.2}Folder':
      # Get markers for My Tracks files.
      if meta['subformat'] == 'mytracks')
        for subelement in element:
          if subelement.tag == '{http://www.opengis.net/kml/2.2}name':
            assert subelement.text.endswith(' Markers'), subelement.text
          elif subelement.tag == '{http://www.opengis.net/kml/2.2}Placemark':
            marker = parse_marker(subelement)
            if marker is not None:
              markers.append(marker)
    # <Placemark>
    elif element.tag == '{http://www.opengis.net/kml/2.2}Placemark':
      # <Placemark id="tour">
      if element.attrib.get('id') == 'tour':
        for subelement in element:
          # <name>
          if subelement.tag == '{http://www.opengis.net/kml/2.2}name':
            meta['title'] = subelement.text
          # <description>
          elif subelement.tag == '{http://www.opengis.net/kml/2.2}description':
            meta['description'] = subelement.text
          elif (subelement.tag == '{http://www.opengis.net/kml/2.2}TimeSpan' and
              meta['subformat'] == 'geotracker'):
            for sub2element in subelement:
              if sub2element.tag == '{http://www.opengis.net/kml/2.2}begin':
                meta['start'] = dateutil.parser.parse(sub2element.text).timestamp()
              elif sub2element.tag == '{http://www.opengis.net/kml/2.2}end':
                meta['end'] = dateutil.parser.parse(sub2element.text).timestamp()
      # Get start/end timestamps for My Tracks files.
      elif meta['subformat'] == 'mytracks':
        placemark_type = None
        timestamp = None
        for subelement in element:
          if (subelement.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(subelement) > 0
              and subelement[0].tag == '{http://www.opengis.net/kml/2.2}when'):
            timestamp = dateutil.parser.parse(subelement[0].text).timestamp()
          elif subelement.tag == '{http://www.opengis.net/kml/2.2}styleUrl':
            placemark_type = subelement.text
        if placemark_type == '#start' and timestamp:
          meta['start'] = timestamp
        elif placemark_type == '#end' and timestamp:
          meta['end'] = timestamp
      # Get markers for Geo Tracker files.
      elif meta['subformat'] == 'geotracker':
        marker = parse_marker(element)
        if marker is not None:
          markers.append(marker)
    # Sometimes there's no start/end timestamps, or any timestamps at all in the file.
    # I've only encountered this with My Tracks. In this case, there's still usually a date in the
    # title. If so, use that, and say the timespan is from the start of that day to the end of it.
    if meta['start'] is None and meta['title']:
      fields = meta['title'].split()
      try:
        dt = dateutil.parser.parse(fields[0])
      except ValueError:
        dt = None
      if dt:
        meta['start'] = dt.timestamp()
        meta['end'] = (dt + datetime.timedelta(days=1)).timestamp()
  return meta, markers


def parse_marker(marker_element):
  marker = {'name':None, 'description':None, 'timestamp':None, 'lat':None, 'long':None}
  for element in marker_element:
    if element.tag == '{http://www.opengis.net/kml/2.2}name':
      marker['name'] = element.text
    elif element.tag == '{http://www.opengis.net/kml/2.2}description':
      marker['description'] = element.text
    elif (element.tag == '{http://www.opengis.net/kml/2.2}Point' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}coordinates'):
      fields = element[0].text.split(',')
      assert 2 <= len(fields) <= 3, element[0].text
      marker['long'] = float(fields[0])
      marker['lat'] = float(fields[1])
    elif (element.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}when'):
      marker['timestamp'] = dateutil.parser.parse(element[0].text).timestamp()
  if any([v is None for v in marker.values()]):
    return None
  else:
    return marker


def make_argparser():
  parser = argparse.ArgumentParser(description='Parse a .kml or .kmz track.')
  parser.add_argument('kml', metavar='kml/kmz', nargs='+',
    help='The .kml or .kmz file(s).')
  parser.add_argument('-k', '--key',
    help='Print the value of this key from the metadata.')
  parser.add_argument('-l', '--key-len',
    help='Print the length of this value for this key from the metadata.')
  return parser


def main(argv):
  parser = make_argparser()
  args = parser.parse_args(argv[1:])
  for i, kml_path in enumerate(args.kml):
    if len(args.kml) > 1:
      print(os.path.basename(kml_path))
    if kml_path.endswith('.kmz') or kml_path.endswith('.zip'):
      kml = read_kmz(kml_path)
    else:
      kml = read_kml(kml_path)
    meta, markers = parse(kml)
    if args.key:
      if args.key == 'markers':
        for marker in markers:
          print(marker['name'])
      else:
        print(meta[args.key])
    elif args.key_len:
      if args.key_len == 'markers':
        print(len(markers))
      else:
        value = meta[args.key_len]
        if value is None:
          print(0)
        else:
          print(len(value))
    else:
      print("""subformat:\t{subformat}
title:\t{title}
description:
{description}""".format(**meta))
    if len(args.kml) > 1 and i < len(args.kml)-1:
      print()

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