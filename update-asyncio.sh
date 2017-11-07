#!/bin/bash

# Run after editing files that use trollius and have asyncio counterparts

set -e

function fixup() {
    echo "# Automatically generated by update-asyncio.sh. Do not edit" > "$2"
    cat "$1" >> "$2"
}

fixup katsdpsigproc/resource.py katsdpsigproc/asyncio/resource.py
fixup katsdpsigproc/test/test_resource.py katsdpsigproc/test/asyncio/test_resource.py
trollius2asyncio -n -w --no-diffs katsdpsigproc/asyncio/*.py katsdpsigproc/test/asyncio/*.py
sed -i 's/katsdpsigproc\.resource/katsdpsigproc.asyncio.resource/' katsdpsigproc/test/asyncio/*.py
