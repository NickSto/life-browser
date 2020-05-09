
# Drivers

This is where the code for the drivers lives.

Each driver is a parser for a particular input format.

## API

The main application uses a driver by executing it as a separate subprocess, and reading its output from its stdout. This way, drivers can be written in any language, and there's a clean separation between the main application code and driver code. The output is plain text JSON. Each JSON object is a serialization of an `Event` or `Contact` object. Each line should consist of one of these objects. So the output as a whole will not be valid JSON (but the driver can add an option to add commas and enclosing brackets to make it valid JSON).

### `Contact` objects

Many formats, like `hangouts`, or `voice`, contain contact info for participants. The `Contact` JSON output is so these drivers can include this data in their output. Their `Event`s will usually reference certain contacts. Instead of including the contact data directly inside the `Event` objects, they will just list a unique id to identify the `Contact`. This id will refer to the `id` key of a `Contact` object returned on a different line. But this is not a globally unique id; it's only valid within the context of this execution of the driver. Normally, the driver will be executed, start parsing the input, and the first `Contact` it encounters and creates will get the `id` `1`, the next `2`, and so on.

### Metadata YAML file

Drivers are registered simply be dropping a `driver.yaml` file into a subdirectory of the `drivers` directory.

The file describes the driver, and how to execute it. The 'execution' key holds the latter info. The `exe` subkey is a relative path to the driver executable (relative to the yaml file). The `args` subkey is a list giving the arguments to give the executable. A null (`~`) value indicates where to substitute the path to the input file/directory.
