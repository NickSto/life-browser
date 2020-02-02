
# Drivers

This is where the code for the drivers lives.

Each driver is a parser for a particular input format.

## API

The main application uses a driver by executing it as a separate subprocess, and reading its output from its stdout. This way, drivers can be written in any language. The output is plain text JSON. Each JSON object is a serialization of an `Event` or `Contact` object. Each line should consist of one of these objects. So the output as a whole will not be valid JSON (but the driver can add an option to add commas and enclosing brackets to make it valid JSON).

### `Contact` objects

Many formats, like `hangouts`, or `voice`, contain contact info for participants. The `Contact` JSON output is so these drivers can include this data in their output. Their `Event`s will usually reference certain contacts. Instead of including the contact data directly inside the `Event` objects, they will just list a unique id to identify the `Contact`. This id will refer to the `id` key of a `Contact` object returned on a different line. But this is not a globally unique id; it's only valid within the context of this execution of the driver. Normally, the driver will be executed, start parsing the input, and the first `Contact` it encounters and creates will get the `id` `1`, the next `2`, and so on.
