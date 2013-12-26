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

"""Contains the command line entry point(s)."""

import argparse
import logging
import os
import tempfile

from flask import Flask

DEFAULT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "simplepypicache")


def get_app(
        static_folder, index_view, single_package_view, download_package_view):
    app = Flask(__name__, static_folder=static_folder)
    app.add_url_rule(
        "/simple/", view_func=index_view)
    app.add_url_rule(
        "/simple/<string:package>/", view_func=single_package_view)
    app.add_url_rule(
        "/packages/<path:package>", view_func=download_package_view)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cached-packages",
        default=os.environ.get("SCPYPI_ROOT", DEFAULT_CACHE_DIR),
        help="Location where package files are cached")
    parser.add_argument(
        "--cached-dists-file",
        default=os.environ.get(
            "CACHED_DISTS_FILE",
            os.path.join(DEFAULT_CACHE_DIR, "cached_dists.json")),
        help="The directory to cache files in")
    parser.add_argument(
        "--pypi-index",
        default=os.environ.get(
            "PYPI_INDEX", "https://pypi.python.org/simple/"),
        help="The default location to load packages from")

    parsed = parser.parse_args()

    if not os.path.isdir(parsed.cached_packages):
        os.makedirs(parsed.cached_packages)

    # set the environment variables so we can use them
    # elsewhere....it's a bit of a hack but does what we
    # need for now
    os.environ["SCPYPI_ROOT"] = parsed.cached_packages
    os.environ["SCPYPI_DISTS_FILE"] = parsed.cached_dists_file or ""
    os.environ["SCPYPI_INDEX"] = parsed.pypi_index

    from simplepypicache.logger import logger
    logger.setLevel(logging.getLevelName(
        os.environ.get("SCPYPI_LOG_LEVEL", logging.DEBUG)))

    from simplepypicache.server import (
        Index, single_package_index, download_package)

    app = get_app(
        os.path.join(os.environ["SCPYPI_ROOT"], "static"),
        Index(), single_package_index, download_package)
    app.run()
