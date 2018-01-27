## What is this?

This is a project I began to try to collate all the digital breadcrumbs of my life and show them in an easily viewable timeline.

Over the years I've collected lots of digital data like text messages, chat messages, phone calls, photos, calendar events, geolocation tracks, even credit card purchases. These are all available as computer-readable files.

All of this data is timestamped, and when collated into one continuous timeline it forms an evocative personal history to look back on. It's an invaluable resource to jog my ailing memory.

## Organization

The heart of this is the `drivers`, which are parsers built to read the various files and export the data via a common API.

For now, the entry point is `view.py`, which uses the drivers to read input files, sort them by time, and display them chronologically, as human-readable text. You can also view one slice of time or filter events by who participated in them.

Eventually I'd like to export the parsed data to a persistent database, and even build a web interface to browse it.
