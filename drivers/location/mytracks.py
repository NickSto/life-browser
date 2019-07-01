#!/usr/bin/env python3
"""Parser for the KML format output by Google's My Tracks, plus derivative formats."""
import argparse
import datetime
import logging
import os
import pathlib
import re
import sys
import tarfile
import xml.dom.minidom
import dateutil.parser
import kml


def parse(kml_root):
  meta = {'dialect':None, 'title':None, 'description':None, 'start':None, 'end':None,
          'distance':None}
  markers = []
  track = []
  # <kml>
  if len(kml_root) == 0:
    return None
  # <Document>
  for element in kml_root[0]:
    if len(element) == 0:
      continue
    # <atom:author>
    elif (element.tag == '{http://www.w3.org/2005/Atom}author' and
        element[0].tag == '{http://www.w3.org/2005/Atom}name'):
      meta['dialect'] = parse_dialect(element[0].text)
    # <Folder>
    elif element.tag == '{http://www.opengis.net/kml/2.2}Folder':
      # Get markers for My Tracks files.
      if meta['dialect'] == 'mytracks':
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
              meta['dialect'] == 'geotracker'):
            for sub2element in subelement:
              if sub2element.tag == '{http://www.opengis.net/kml/2.2}begin':
                meta['start'] = dateutil.parser.parse(sub2element.text).timestamp()
              elif sub2element.tag == '{http://www.opengis.net/kml/2.2}end':
                meta['end'] = dateutil.parser.parse(sub2element.text).timestamp()
          # <gx:MultiTrack>
          elif subelement.tag == '{http://www.google.com/kml/ext/2.2}MultiTrack':
            track = kml.parse_track(subelement)
            #TODO: Measure distance elsewhere?
            meta['distance'] = kml.get_total_distance(track)
      # Get start/end timestamps for My Tracks files.
      elif meta['dialect'] == 'mytracks':
        timestamp, placemark_type = parse_mytracks_timestamp(element)
        if timestamp and placemark_type in ('start', 'end'):
          meta[placemark_type] = timestamp
      # Get markers for Geo Tracker files.
      elif meta['dialect'] == 'geotracker':
        marker = parse_marker(element)
        if marker is not None:
          markers.append(marker)
    # If there's no start/end timestamps, get them from the first and last points in the track.
    if meta['start'] is None or meta['end'] is None:
      logging.debug('Debug: Could not find start/end times in metadata. Extracting from track..')
      if track:
        if track[0][0] is not None:
          meta['start'] = track[0][0]
        if track[-1][0] is not None:
          meta['end'] = track[-1][0]
    # If there's no start/end timestamps, infer them from the title.
    if meta['title'] and (meta['start'] is None or meta['end'] is None):
      logging.warning('Warning: Could not find start/end times. Inferring from title..')
      title_start, title_end = parse_timestamps_from_title(meta['title'])
      if meta['start'] is None:
        meta['start'] = title_start
      if meta['end'] is None:
        meta['end'] = title_end
  return meta, track, markers


def parse_dialect(name):
  if name in ('Created by My Tracks on Android.', 'Created by Google My Tracks on Android'):
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
      marker['lat'], marker['long'], dummy = kml.parse_coord(element[0].text, 'kml')
    elif (element.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}when'):
      marker['timestamp'] = dateutil.parser.parse(element[0].text).timestamp()
  if any([v is None for v in marker.values()]):
    return None
  else:
    return marker


########## Command line interface ##########


def make_argparser():
  parser = argparse.ArgumentParser(description='Parse a .kml or .kmz track.')
  parser.add_argument('inputs', metavar='kml/kmz', nargs='+',
    help='The inputs. Can be kml or kmz files, or directories containing them.')
  parser.add_argument('-k', '--key',
    help='Print the value of this key from the metadata.')
  parser.add_argument('-l', '--key-len',
    help='Print the length of this value for this key from the metadata.')
  parser.add_argument('-F', '--filename',
    help='Only print data from the track matching this filename. Useful when reading a tarball.')
  parser.add_argument('-L', '--location', nargs=2, type=float,
    help='Only print data from tracks that went near this location, given by a latitude/longitude '
         'pair.')
  parser.add_argument('-d', '--distance', type=float, default=2,
    help='When using --location, only print tracks that went within this many miles of the '
         'location. Default: %(default)s mi')
  parser.add_argument('-D', '--dump', action='store_true',
    help='Extract the xml content, format it, and print to stdout. Warning: The formatted xml may '
         'not be valid or equivalent to the input. Mainly useful for human readers.')
  parser.add_argument('-o', '--outfile', default=sys.stdout, type=argparse.FileType('w'),
    help='Write output to this file instead of stdout.')
  parser.add_argument('-g', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):
  parser = make_argparser()
  args = parser.parse_args(argv[1:])
  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  if len(args.inputs) == 1 and (args.inputs[0].endswith('.kml') or args.inputs[0].endswith('.kmz')):
    single_input = True
  else:
    single_input = None
  # Process each input file.
  if args.dump:
    out_format = 'str'
  else:
    out_format = 'xml'
  for i, (kml_path, kml_data) in enumerate(extract_inputs(args.inputs, out_format)):
    filename = os.path.basename(kml_path)
    if args.filename and filename != args.filename:
      continue
    # If --dump, format and print the xml and continue.
    if args.dump:
      kml_str = kml_data
      args.outfile.write(format_xml(kml_str))
      continue
    else:
      kml_root = kml_data
    # Parse the kml.
    meta, track, markers = parse(kml_root)
    track = kml.filter_track(track)
    # Filter by location, if requested.
    if args.location:
      if not kml.is_track_near(track, args.location, args.distance):
        continue
    # Print the requested output.
    if not (single_input or args.key or args.key_len):
      print(filename, file=args.outfile)
    if args.key:
      if args.key == 'markers':
        for marker in markers:
          print(marker['name'], file=args.outfile)
      else:
        print(meta[args.key], file=args.outfile)
    elif args.key_len:
      if args.key_len == 'markers':
        print(len(markers), file=args.outfile)
      else:
        value = meta[args.key_len]
        if value is None:
          print(0, file=args.outfile)
        else:
          print(len(value), file=args.outfile)
    else:
      if meta['title'] and not re.search(r'^\d{4}-\d{2}-\d{2}[ _]', meta['title']) and meta['start']:
        date = datetime.datetime.fromtimestamp(meta['start']).strftime('%Y-%m-%d')
        dateline = '\ndate:\t{}'.format(date)
      else:
        dateline = ''
      if meta['end'] and meta['start']:
        duration = datetime.timedelta(seconds=round(meta['end']-meta['start']))
      else:
        duration = None
      if meta['distance'] is None:
        distance = None
      else:
        distance = '{:0.2f}mi'.format(meta['distance']*0.6213)
      print("""title:\t{title}{}
dialect:\t{dialect}
duration:\t{}
distance:\t{}
markers:\t{}
description:
{description}""".format(dateline, duration, distance, len(markers), **meta), file=args.outfile)
    if not(single_input or args.key or args.key_len):
      print(file=args.outfile)


def path_is_kmz(path):
  if path.endswith('.kmz') or path.endswith('.zip'):
    return True
  else:
    return False


def format_xml(input_str):
  """Quick and dirty way of prettifying XML.
  Uses xml.dom.minidom's toprettyxml() method, fixing some of the quirks of its output.
  WARNING: This uses some regex hacks and may not yield output equivalent to the input."""
  output = []
  dom_str = xml.dom.minidom.parseString(input_str).toprettyxml(indent='  ')
  # Remove newlines inserted at the start of string content.
  dom_str = re.sub(r'<([^>\n\t]+)>\n<!\[CDATA\[', r'<\1><![CDATA[', dom_str)
  for line in dom_str.splitlines():
    # Remove empty lines.
    if not line.strip():
      continue
    # Remove randomly inserted indents at the end of string content.
    old_line = None
    while line != old_line:
      old_line = line
      line = line.replace(']]>  ', ']]>')
    output.append(line)
  return '\n'.join(output)


def extract_inputs(input_paths, out_format='xml'):
  """Take a list of paths containing kml data and return parsed kml objects."""
  file_paths = []
  # Expand directories into the files they contain.
  for input_path in input_paths:
    if os.path.isdir(input_path):
      file_paths.extend(find_kmls(input_path))
    else:
      file_paths.append(input_path)
  # Read each file.
  for file_path in file_paths:
    ext = os.path.splitext(file_path)[1]
    if (ext in ('.tgz', '.tbz', '.txz') or file_path.endswith('.tar.gz') or
        file_path.endswith('.tar.bz') or file_path.endswith('.tar.xz')):
      with tarfile.open(file_path) as tarball:
        for member in tarball.getnames():
          if member.endswith('.kml') or member.endswith('.kmz'):
            file = tarball.extractfile(member)
            contents = str(file.read(), 'utf8')
            if out_format == 'xml':
              yield member, kml.parse_kml_str(contents)
            elif out_format == 'str':
              yield member, contents
    elif ext in ('.kmz', '.zip'):
      if out_format == 'xml':
        yield file_path, kml.read_kmz(file_path)
      elif out_format == 'str':
        kml_bytes = kml.extract_from_zip(kml_path, 'doc.kml')
        yield file_path, str(kml_bytes, 'utf8')
    else:
      if out_format == 'xml':
        yield file_path, kml.read_kml(file_path)
      elif out_format == 'str':
        with open(file_path, 'r') as file:
          yield file_path, file.read()



def find_kmls(root_dir):
  kml_paths = []
  for dirpath, dirnames, filenames in os.walk(root_dir):
    for filename in filenames:
      if filename.endswith('.kml') or filename.endswith('.kmz'):
        kml_paths.append(os.path.join(dirpath, filename))
  return kml_paths


def extract_kmls(tar_path):
  with tarfile.open(tar_path) as tarball:
    for member in tarball.getnames():
      if member.endswith('.kml') or member.endswith('.kmz'):
        filehandle = tarball.extractfile(member)
        contents = str(filehandle.read(), 'utf8')


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