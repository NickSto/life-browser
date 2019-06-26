#!/usr/bin/env python3
import argparse
import datetime
import logging
import math
import os
import sys
import zipfile
import dateutil.parser
import defusedxml.ElementTree

EARTH_RADIUS = 6371  # Radius of Earth in km.

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
  meta = {'subformat':None, 'title':None, 'description':None, 'start':None, 'end':None,
          'distance':None}
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
      meta['subformat'] = parse_subformat(element[0].text)
    # <Folder>
    elif element.tag == '{http://www.opengis.net/kml/2.2}Folder':
      # Get markers for My Tracks files.
      if meta['subformat'] == 'mytracks':
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
          # <TimeSpan>: Get start/end timestamps for Geo Tracker files.
          elif (subelement.tag == '{http://www.opengis.net/kml/2.2}TimeSpan' and
              meta['subformat'] == 'geotracker'):
            for sub2element in subelement:
              if sub2element.tag == '{http://www.opengis.net/kml/2.2}begin':
                meta['start'] = dateutil.parser.parse(sub2element.text).timestamp()
              elif sub2element.tag == '{http://www.opengis.net/kml/2.2}end':
                meta['end'] = dateutil.parser.parse(sub2element.text).timestamp()
          # <gx:MultiTrack>
          elif subelement.tag == '{http://www.google.com/kml/ext/2.2}MultiTrack':
            meta['distance'] = parse_track(subelement)
      # Get start/end timestamps for My Tracks files.
      elif meta['subformat'] == 'mytracks':
        timestamp, placemark_type = parse_mytracks_timestamp(element)
        if timestamp and placemark_type in ('start', 'end'):
          meta[placemark_type] = timestamp
      # Get markers for Geo Tracker files.
      elif meta['subformat'] == 'geotracker':
        marker = parse_marker(element)
        if marker is not None:
          markers.append(marker)
    # If there's no start/end timestamps, infer them from the title.
    if meta['start'] is None and meta['title']:
      logging.warning('Warning: Could not find start/end times. Inferring from title..')
      start, end = parse_timestamps_from_title(meta['title'])
      if start and end:
        meta['start'] = start
        meta['end'] = end
  return meta, markers


def parse_subformat(name):
  if name == 'Created by Google My Tracks on Android':
    return 'mytracks'
  elif name == 'Recorded in Geo Tracker for Android from Ilya Bogdanovich':
    return 'geotracker'
  else:
    return None


def parse_mytracks_timestamp(placemark_element):
  placemark_type = None
  timestamp = None
  for subelement in placemark_element:
    if (subelement.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(subelement) > 0
        and subelement[0].tag == '{http://www.opengis.net/kml/2.2}when'):
      timestamp = dateutil.parser.parse(subelement[0].text).timestamp()
    elif subelement.tag == '{http://www.opengis.net/kml/2.2}styleUrl':
      placemark_type = subelement.text[1:]
  return timestamp, placemark_type


def parse_timestamps_from_title(title):
  # Sometimes there's no start/end timestamps, or any timestamps at all in the file.
  # I've only encountered this with My Tracks. In this case, there's still usually a date in the
  # title. If so, use that, and say the timespan is from the start of that day to the end of it.
  fields = title.split()
  try:
    dt = dateutil.parser.parse(fields[0])
  except ValueError:
    dt = None
  if dt:
    start = dt.timestamp()
    end = (dt + datetime.timedelta(days=1)).timestamp()
    return start, end
  else:
    return None, None


def parse_marker(marker_element):
  marker = {'name':None, 'description':None, 'timestamp':None, 'lat':None, 'long':None}
  for element in marker_element:
    if element.tag == '{http://www.opengis.net/kml/2.2}name':
      marker['name'] = element.text
    elif element.tag == '{http://www.opengis.net/kml/2.2}description':
      marker['description'] = element.text
    elif (element.tag == '{http://www.opengis.net/kml/2.2}Point' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}coordinates'):
      marker['lat'], marker['long'], dummy = parse_coord(element[0].text, 'kml')
    elif (element.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}when'):
      marker['timestamp'] = dateutil.parser.parse(element[0].text).timestamp()
  if any([v is None for v in marker.values()]):
    return None
  else:
    return marker


def parse_track(track_element):
  distance = 0
  last_lat = last_lon = None
  for element in track_element:
    # <gx:Track>
    if element.tag == '{http://www.google.com/kml/ext/2.2}Track':
      for subelement in element:
        # <gx:coord>
        if subelement.tag == '{http://www.google.com/kml/ext/2.2}coord':
          lat, lon, alt = parse_coord(subelement.text, 'gx')
          if last_lat is not None and last_lon is not None:
            distance += get_lat_long_distance(lat, lon, last_lat, last_lon)
          last_lat = lat
          last_lon = lon
  if lat is None or last_lat is None or lon is None or last_lon is None:
    return None
  else:
    return distance


def parse_coord(coord_str, type):
  if type == 'kml':
    fields = coord_str.split(',')
  elif type == 'gx':
    fields = coord_str.split()
  assert 2 <= len(fields) <= 3, coord_str
  longitude = float(fields[0])
  latitude = float(fields[1])
  #TODO: Might have to check the <altitudeMode> before knowing if this is relative or absolute.
  if len(fields) == 3:
    altitude = float(fields[2])
  return latitude, longitude, altitude


def get_lat_long_distance(lat1, lon1, lat2, lon2):
  """Use haversine formula to calculate the distance between two points on Earth.
  Takes two latitude/longitude pairs and returns the distance in kilometers."""
  # Taken from https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points/45395941#45395941
  #TODO: Use geopy: https://geopy.readthedocs.io/en/stable/#module-geopy.distance
  lat_delta = math.radians(lat2 - lat1)
  lon_delta = math.radians(lon2 - lon1)
  lat1 = math.radians(lat1)
  lat2 = math.radians(lat2)
  a = math.sin(lat_delta/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(lon_delta/2)**2
  c = 2*math.asin(math.sqrt(a))
  return EARTH_RADIUS * c


def make_argparser():
  parser = argparse.ArgumentParser(description='Parse a .kml or .kmz track.')
  parser.add_argument('kml', metavar='kml/kmz', nargs='+',
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
      duration = datetime.timedelta(seconds=round(meta['end']-meta['start']))
      print("""title:\t{title}
subformat:\t{subformat}
duration:\t{}
distance:\t{}mi
markers:\t{}
description:
{description}""".format(duration, round(meta['distance']*0.6213, 2), len(markers), **meta))
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