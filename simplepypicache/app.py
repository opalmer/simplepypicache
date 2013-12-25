# No shebang line, this module is meant to be imported
#
# The MIT License (MIT)
# Copyright (c) 2013 Oliver Palmer
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

"""
This file is the entry point for the WSGI server.  It does not
have any command line options and relies on environment variables instead.
"""

import logging
import os
import sys

from flask import Flask

assert "SCPYPI_ROOT" in os.environ
assert "SCPYPI_INDEX" in os.environ

SCPYPI_ROOT = os.environ["SCPYPI_ROOT"]
SCPYPI_STATIC = os.environ.get(
    "SCPYPI_STATIC", os.path.join(SCPYPI_ROOT, "static"))

assert os.path.isdir(SCPYPI_ROOT), \
    "%s is not a directory" % SCPYPI_ROOT

assert os.path.isdir(SCPYPI_STATIC), \
    "%s is not a directory" % SCPYPI_STATIC

# logger setup
logger = logging.getLogger("simplepypicache")
logger_format = logging.Formatter(
    "%(asctime)-15s %(levelname)s %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logger_format)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

from simplepypicache.server import (
    Index, single_package_index, download_package)

app = Flask(__name__, static_folder=SCPYPI_STATIC)
app.add_url_rule("/simple/", view_func=Index())
app.add_url_rule("/simple/<string:package>/",
                 view_func=single_package_index)
app.add_url_rule("/packages/<path:package>",
                 view_func=download_package)

if __name__ == "__main__":
    app.run()