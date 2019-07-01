#!/usr/bin/env python3
"""Parser for the KML format output by Google's My Tracks, plus derivative formats."""
import argparse
import collections
import datetime
import logging
import os
import pathlib
import re
import sys
import tarfile
import xml.dom.minidom
import dateutil.parser
import yaml
import kml


def parse(kml_root, parse_track=True):
  meta = {'dialect':None, 'title':None, 'description':None, 'start':None, 'end':None,
          'distance':None, 'start_lat':None, 'start_lon':None, 'end_lat':None, 'end_lon':None}
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
          elif subelement.tag == '{http://www.google.com/kml/ext/2.2}MultiTrack' and parse_track:
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
    # Get the location of the start and end of the track.
    if track:
      meta['start_lat'], meta['start_lon'] = track[0][1:3]
      if track[-1] != track[0]:
        meta['end_lat'], meta['end_lon'] = track[-1][1:3]
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
  marker = {'name':None, 'description':None, 'timestamp':None, 'lat':None, 'long':None,
            'meta':{}}
  for element in marker_element:
    if element.tag == '{http://www.opengis.net/kml/2.2}name':
      name = element.text
      if name.lower().replace(' ', '') == '!unknown':
        marker['name'] = None
      else:
        marker['name'] = element.text
    elif element.tag == '{http://www.opengis.net/kml/2.2}description':
      marker['description'] = element.text
    elif (element.tag == '{http://www.opengis.net/kml/2.2}Point' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}coordinates'):
      marker['lat'], marker['long'], dummy = kml.parse_coord(element[0].text, 'kml')
    elif (element.tag == '{http://www.opengis.net/kml/2.2}TimeStamp' and len(element) > 0 and
        element[0].tag == '{http://www.opengis.net/kml/2.2}when'):
      marker['timestamp'] = dateutil.parser.parse(element[0].text).timestamp()
  if marker['description'] is not None:
    marker['meta'] = parse_meta_markup(marker['description'])
  if any([v is None for v in marker.values()]):
    return None
  else:
    return marker


def parse_meta_markup(text):
  """Parse out my metadata notation from a string."""
  # Note: I first started using the key/value notation at 1511921476 (2017-11-28). Before that, it
  # was just a value (with the assumed key "type"). I only did that for about a month, though:
  # the first occurrence of the ! notation was on 1509495819 (2017-10-31). There are only 23
  # annotations from this period. I could manually correct them all. Note that I think there are
  # some exceptions beyond this period, like !home.
  meta = {}
  for line_raw in text.splitlines():
    line = line_raw.strip()
    if not line.startswith('!'):
      continue
    fields = line[1:].split(':')
    if len(fields)<= 0:
      continue
    elif len(fields) == 1:
      value = True
    elif len(fields) == 2:
      value = fields[1].strip()
    elif len(fields) > 2:
      value = ':'.join(fields[1:]).strip()
    key = fields[0].strip().lower()
    try:
      value_list = [element.strip() for element in value.split(';')]
    except AttributeError:
      value_list = [value]
    if len(value_list) > 1:
      meta[key] = value_list
    else:
      meta[key] = value
  return meta


########## Command line interface ##########


MI_PER_KM = 0.6213


def make_argparser():
  parser = argparse.ArgumentParser(description='Parse a .kml or .kmz track.')
  parser.add_argument('inputs', metavar='kml/kmz', nargs='+',
    help='The inputs. Can be kml or kmz files, or directories containing them.')
  output = parser.add_argument_group('Output')
  output.add_argument('-k', '--key',
    help='Print the value of this key from the metadata. Special keys: "markers" - print the name '
         'of each marker.')
  output.add_argument('-l', '--key-len',
    help='Print the string length of this value for this key from the metadata.')
  output.add_argument('-K', '--marker-key',
    help='Print the value of this key from marker metadata.')
  output.add_argument('--marker-meta', action='store_true',
    help='Print all marker metadata.')
  output.add_argument('--marker-keys', action='store_true',
    help='Print all keys used in marker metadata.')
  output.add_argument('-D', '--dump', action='store_true',
    help='Extract the xml content, format it, and print to stdout. Warning: The formatted xml may '
         'not be valid or equivalent to the input. Mainly useful for human readers.')
  output.add_argument('-o', '--outfile', default=sys.stdout, type=argparse.FileType('w'),
    help='Write output to this file instead of stdout.')
  output.add_argument('-r', '--ref-points', type=load_reference_points,
    help='A YAML file containing GPS coordinates of reference points to use in summaries '
         'describing where the track is.')
  filters = parser.add_argument_group('Filtering')
  filters.add_argument('-F', '--filename',
    help='Only match the track matching this filename. Useful when reading a tarball.')
  filters.add_argument('-L', '--location', nargs=2, type=float,
    help='Only match tracks that went near this location, given by a latitude/longitude '
         'pair.')
  filters.add_argument('-d', '--distance', type=float, default=2,
    help='When using --location, only match tracks that went within this many miles of the '
         'location. Default: %(default)s mi')
  filters.add_argument('-s', '--start', type=int,
    help='Only match tracks that start after this timestamp.')
  filters.add_argument('-e', '--end', type=int,
    help='Only match tracks that end before this timestamp.')
  filters.add_argument('-M', '--marker-filt-meta', nargs=2, metavar=('KEY', 'VALUE'),
    help='Only match tracks with markers whose metadata matches this key/value pair. '
         'If the metadata value is a list, only one element needs to match your query (case-'
         'insensitive).')
  filters.add_argument('--marker-filt-key',
    help='Only match tracks with markers that use this key.')
  log = parser.add_argument_group('Logging')
  log.add_argument('-g', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = log.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):
  parser = make_argparser()
  args = parser.parse_args(argv[1:])
  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  summarize = not (args.key or args.key_len or args.marker_key or args.marker_keys or args.marker_meta)
  if (summarize or args.key in ('distance', 'start', 'end', 'duration') or
      args.location or args.start or args.end):
    parse_track = True
  else:
    parse_track = False
  if len(args.inputs) == 1 and (args.inputs[0].endswith('.kml') or args.inputs[0].endswith('.kmz')):
    single_input = True
  else:
    single_input = None
  if args.marker_filt_meta:
    marker_key, marker_value = args.marker_filt_meta
    if marker_value.lower() == 'true':
      marker_value = True
    elif marker_value.lower() == 'false':
      marker_value = False
  if args.dump:
    out_format = 'str'
  else:
    out_format = 'xml'
  # Process each input file.
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
    meta, track, markers = parse(kml_root, parse_track=parse_track)
    track = kml.filter_track(track)
    # Apply filters.
    if args.marker_filt_meta:
      if not markers_match_metavalue(markers, marker_key, marker_value):
        continue
    if args.marker_filt_key:
      if not markers_match_metakey(markers, args.marker_filt_key):
        continue
    if args.location:
      if not kml.is_track_near(track, args.location, args.distance):
        continue
    if args.start and meta['start'] and meta['start'] < args.start:
      continue
    if args.end and meta['end'] and meta['end'] > args.end:
      continue
    # Print the values requested.
    if summarize and not single_input:
      print(filename, file=args.outfile)
    outputs = []
    if args.key:
      outputs.append(format_key_value(args.key, meta, markers))
    if args.key_len:
      outputs.append(format_key_len(args.key_len, meta, markers))
    if args.marker_meta:
      outputs.append(format_marker_metadata(markers))
    if args.marker_key:
      outputs.append(format_marker_value(args.marker_key, markers))
    if args.marker_keys:
      outputs.append(format_marker_keys(markers))
    for output in outputs:
      if output:
        print(output, file=args.outfile)
    # If no specific values were requested, print a summary.
    if summarize:
      print(format_summary(meta, markers, track, args.ref_points), file=args.outfile)
    if summarize and not single_input:
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
        for member in sorted(tarball.getnames()):
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
        kml_bytes = kml.extract_from_zip(file_path, 'doc.kml')
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
    for filename in sorted(filenames):
      if filename.endswith('.kml') or filename.endswith('.kmz'):
        kml_paths.append(os.path.join(dirpath, filename))
  return kml_paths


def markers_match_metavalue(markers, query_key, query_value):
  for marker in markers:
    if query_key in marker['meta']:
      value = marker['meta'][query_key]
      if isinstance(value, collections.abc.Iterable) and not isinstance(value, str):
        for element in value:
          if element.lower() == query_value:
            return True
      else:
        try:
          if value.lower() == query_value:
            return True
        except AttributeError:
          if value == query_value:
            return True
  return False


def markers_match_metakey(markers, query_key):
  for marker in markers:
    if query_key in marker['meta']:
      return True
  return False


def load_reference_points(ref_path):
  with open(ref_path) as ref_file:
    return yaml.safe_load(ref_file)


def find_closest_ref_point(lat, lon, ref_points):
  if ref_points is None or lat is None or lon is None:
    return None, None
  min_dist = 999999
  min_name = None
  for name, ref_point in ref_points.items():
    dist = kml.get_lat_long_distance(lat, lon, ref_point[0], ref_point[1])
    if dist < min_dist:
      min_dist = dist
      min_name = name
  return min_name, min_dist


def format_key_value(key, meta, markers):
  if key == 'markers':
    return '\n'.join([str(marker['name']) for marker in markers])
  else:
    return meta[key]


def format_key_len(key, meta, markers):
  if key == 'markers':
    return len(markers)
  else:
    value = meta[key]
    if value is None:
      return 0
    else:
      return len(value)


def format_marker_metadata(markers):
  lines = []
  for marker in markers:
    for key, value in marker['meta'].items():
      if isinstance(value, collections.abc.Iterable) and not isinstance(value, str):
        value_str = ';'.join(value)
      else:
        value_str = value
      lines.append('!{}:{}'.format(key, value_str))
  return '\n'.join(lines)


def format_marker_value(key, markers):
  values = []
  for marker in markers:
    for key, value in marker['meta'].items():
      if isinstance(value, collections.abc.Iterable) and not isinstance(value, str):
        values.append(';'.join(value))
      else:
        values.append(value)
  return '\n'.join(values)


def format_marker_keys(markers):
  keys = []
  for marker in markers:
    for key in marker['meta'].keys():
      keys.append(key)
  return '\n'.join(keys)


def format_summary(meta, markers, track, ref_points=None):
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
    distance = '{:0.2f}mi'.format(meta['distance']*MI_PER_KM)
  reflines = ''
  if ref_points:
    start_ref, start_dist = find_closest_ref_point(meta['start_lat'], meta['start_lon'], ref_points)
    end_ref, end_dist = find_closest_ref_point(meta['end_lat'], meta['end_lon'], ref_points)
    if start_ref == end_ref and start_ref is not None and end_ref is not None:
      start_dist_str = '{:0.1f}'.format(start_dist*MI_PER_KM)
      end_dist_str = '{:0.1f}'.format(end_dist*MI_PER_KM)
      if start_dist_str == end_dist_str:
        dist_str = start_dist_str
      else:
        dist_str = start_dist_str+'/'+end_dist_str
      reflines += '\nstart/end:\t{}mi from {}'.format(dist_str, start_ref)
    else:
      if start_ref is not None:
        reflines += '\nstart:\t\t{:0.1f}mi from {}'.format(start_dist*MI_PER_KM, start_ref)
      if end_ref is not None:
        reflines += '\nend:\t\t{:0.1f}mi from {}'.format(end_dist*MI_PER_KM, end_ref)
  return """title:\t{title}{}
dialect:\t{dialect}
duration:\t{}
distance:\t{}{}
markers:\t{}
description:
{description}""".format(dateline, duration, distance, reflines, len(markers), **meta)


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except (BrokenPipeError, KeyboardInterrupt):
    pass
