import math
import zipfile
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
  kml_string = extract_from_zip(kmz_path, 'doc.kml')
  return defusedxml.ElementTree.fromstring(kml_string)


def extract_from_zip(zip_path, file_path):
  with zipfile.ZipFile(zip_path, 'r') as zip_file:
    contents = zip_file.open(file_path, 'r').read()
  return contents


def parse_track(track_element):
  """Parse the time/location points from a track element.
  Argument: the enclosing <gx:MultiTrack> containing one or more <gx:Track>s."""
  track = []
  for element in track_element:
    # <gx:Track>
    if element.tag == '{http://www.google.com/kml/ext/2.2}Track':
      for subelement in element:
        # <gx:coord>
        if subelement.tag == '{http://www.google.com/kml/ext/2.2}coord':
          lat, lon, alt = parse_coord(subelement.text, 'gx')
          track.append((lat, lon, alt))
  return track


def get_total_distance(track):
  distance = 0
  lat = lon = last_lat = last_lon = None
  for point in track:
    lat, lon = point[:2]
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
