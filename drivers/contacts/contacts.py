from . import google_browser_google_csv


def get_contacts(contacts_file, format, contacts_book=None):
  if format == 'google-browser-google-csv':
    return google_browser_google_csv.get_contacts(contacts_file)
