import logging
import math
import zipfile
import dateutil
import defusedxml.ElementTree

EARTH_RADIUS = 6371  # Radius of Earth in km.


def parse_kml_str(kml_str):
  return defusedxml.ElementTree.fromstring(kml_str)


def read_kml(kml_path):
  """Give the path to a .kml file or an open filehandle and this will return an ElementTree.
  The ElementTree will be from defusedxml."""
  tree = defusedxml.ElementTree.parse(kml_path)
  return tree.getroot()


def read_kmz(kmz_path):
  """Give the path to a .kmz file and this will return an ElementTree of the doc.kml.
  The ElementTree will be from defusedxml."""
  #TODO: The .kml file can actually be named anything, as long as there's only one .kml.
  kml_str = extract_from_zip(kmz_path, 'doc.kml')
  return parse_kml_str(kml_str)


def extract_from_zip(zip_path, file_path):
  with zipfile.ZipFile(zip_path, 'r') as zip_file:
    contents = zip_file.open(file_path, 'r').read()
  return contents


def parse_track(track_element):
  """Parse the time/location points from a track element.
  Argument: the enclosing <gx:MultiTrack> containing one or more <gx:Track>s."""
  track = []
  point = (None,)
  for element in track_element:
    # <gx:Track>
    if element.tag == '{http://www.google.com/kml/ext/2.2}Track':
      for subelement in element:
        # <when>
        if subelement.tag == '{http://www.opengis.net/kml/2.2}when':
          when = dateutil.parser.parse(subelement.text).timestamp()
          point = (when,)
        # <gx:coord>
        elif subelement.tag == '{http://www.google.com/kml/ext/2.2}coord':
          point += parse_coord(subelement.text, 'gx')
        if len(point) == 4:
          track.append(point)
          point = (None,)
  return track


def filter_track(track, speed_limit=2000, alt_limit=100000):
  """Remove obviously inaccurate points from track.
  Removes points at impossible altitudes, impossibly far from neighboring points, or which occurred
  before the previous point (no time travel).
  `speed_limit` is in km/h
  `alt_limit` is in feet"""
  # See example-mytracks6.xml for the sort of errors this is designed for.
  new_track = []
  speed_limit_km_sec = speed_limit/60/60
  last_lat = last_lon = last_when = None
  for point in track:
    when, lat, lon, alt = point[:4]
    # Too high?
    if alt is not None and alt > alt_limit:
      continue
    # Too fast?
    if all([value is not None for value in (lat, lon, when, last_lat, last_lon, last_when)]):
      distance = get_lat_long_distance(lat, lon, last_lat, last_lon)
      duration = when - last_when
      # Calculate speed.
      if duration < 0:
        # Negative time (out of order points or wrong timestamps).
        continue
      elif duration == 0:
        if distance == 0:
          # Zero distance over zero time.
          speed = 0
        else:
          # Infinite speed.
          continue
      else:
        speed = distance/duration
      if speed > speed_limit_km_sec:
        continue
    last_lat = lat
    last_lon = lon
    last_when = when
    new_track.append(point)
  return new_track


def get_total_distance(track):
  distance = 0
  lat = lon = last_lat = last_lon = None
  for point in track:
    when, lat, lon = point[:3]
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
  else:
    altitude = None
  return latitude, longitude, altitude


def is_track_near(track, location, thres):
  for point in track:
    when, lat, lon = point[:3]
    distance = get_lat_long_distance(lat, lon, location[0], location[1])
    if distance <= thres:
      return True
  return False


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
