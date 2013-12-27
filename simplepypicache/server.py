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
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Main entry points which mimics behavior similar to PyPi's simple
web pages.
"""

import logging
import os
import sys
import shutil
import urllib2
from httplib import OK
from urlparse import urlparse

from distlib.locators import SimpleScrapingLocator
from flask import Flask, Response, render_template, redirect
from flask.ext.cache import Cache

PYPI_INDEX = os.environ.get("SCPYPI_INDEX", "https://pypi.python.org/simple/")
SCPYPI_TEMP = os.environ.get("SCPYPI_TEMP")
SCPYPI_STATIC = os.environ.get("SCPYPI_STATIC")
PYPI_ROOT = PYPI_INDEX.replace("/simple", "")
HOMEPAGE_URL_TYPES = {"homepage", "ext-homepage"}
DOWNLOAD_URL_TYPES = {"download", "ext-download"}

if PYPI_INDEX.endswith("/"):
    PYPI_INDEX = PYPI_INDEX[:-1]

assert "SCPYPI_TEMP" in os.environ
assert "SCPYPI_STATIC" in os.environ
assert os.path.isdir(SCPYPI_TEMP)
assert os.path.isdir(SCPYPI_STATIC)

# logger setup
logger = logging.getLogger("simplepypicache")
logger_format = logging.Formatter(
    "%(asctime)-15s %(levelname)s %(message)s")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logger_format)
logger.addHandler(handler)
logger.setLevel(logging.getLevelName(
    os.environ.get("SCPYPI_LOG_LEVEL", "DEBUG")))

scraper = SimpleScrapingLocator(PYPI_INDEX)
app = Flask(__name__)
app.config["DEBUG"] = True
app.config["CACHE_TYPE"] = os.environ.get("CACHE_TYPE", "simple")

if app.config["CACHE_TYPE"] == "redis":
    assert "CACHE_REDIS_URL" in os.environ
    app.config["CACHE_REDIS_URL"] = os.environ["CACHE_REDIS_URL"]

cache = Cache(app)


@app.route("/simple/")
@cache.memoize(300)
def index():
    data = list(scraper.get_distribution_names())
    data.sort()
    return render_template("simple.html", package_names=data)


@app.route("/simple/<string:package>/")
@cache.memoize(120)
def single_package_index(package):
    """returns the web page for individual package (ex. /simple/foo/)"""
    remote_page = scraper.get_page("/".join([PYPI_INDEX, package]))

    if remote_page is None:
        return "Not Found (%s does not have any releases)" % package

    project = scraper.get_project(package)
    project_versions = project.keys()
    project_versions.sort(reverse=True)

    # various kinds types of urls
    internal_urls = []
    basic_links = []
    homepages = []
    downloads = []

    # scrape the remote index and retrieve all links
    for remote_url, url_type in remote_page.links:
        parsed_url = urlparse(remote_url)
        local_url = parsed_url.path

        # internal links (packages hosted on PyPi [what we're caching])
        if url_type == "internal":
            if parsed_url.fragment:
                local_url += "#%s" % parsed_url.fragment

            internal_urls.insert(
                0, (url_type, local_url, parsed_url.path.split("/")[-1]))

        # unspecified url
        elif url_type == "":
            basic_links.extend([(
                url_type, remote_url, remote_url)] * len(project_versions))

        # direct links to a project's homepage(s)
        elif url_type in HOMEPAGE_URL_TYPES:
            for version in project_versions:
                homepages.append(
                    (url_type, remote_url, "%s home_page" % version))

        # direct remote download links
        elif url_type in DOWNLOAD_URL_TYPES:
            for version in project_versions:
                if version in remote_url:
                    downloads.append(
                        (url_type, local_url, "%s download_url" % version))
                    break

    # pass it all along to the template and have
    # it render the page
    return render_template(
        "package.html",
        data=internal_urls + basic_links + homepages + downloads,
        package=package,
        versions=project_versions)


@app.route("/packages/<path:package>")
def download_package(package):
    """
    This endpoint will either redirect to a remote url, a static file, or
    download and cache the requested package.  See below for some more
    detailed behavioral information.

    * if the package is not cached
        * open the remote url, begin download to a local file
        * while downloading locally stream the data to the requesting client
        * when complete move the cached file into the static file directory
    * if the package is being downloaded, redirect to the remote url
    * if there are any error im the above process, redirect to the remote url
    """
    temp_placeholder = os.path.join(SCPYPI_TEMP, package) + ".download"

    # the download placeholder file exists so for now
    # we just tell the request to come from the external url
    remote_url = "/".join([PYPI_ROOT, "packages", package])
    if os.path.isfile(temp_placeholder):
        logger.info("%s is being downloaded, redirecting to remote" % package)
        return redirect(remote_url)

    # Not in progress or already downloaded?  Try to request the file
    # so we can download it.
    try:
        download = urllib2.urlopen(remote_url)

        if download.code != OK:
            raise urllib2.HTTPError(
                remote_url, download.code, "failed to connect",
                download.headers, download.fp)

    # on failure however, redirect instead so the client can choose what
    # to do instead
    except urllib2.HTTPError, e:
        logger.error("falling back on pypi url %s" % e)
        return redirect(remote_url)

    try:
        # download the file
        def download_data():
            temp_dirname = os.path.dirname(temp_placeholder)
            logger.debug("downloading %s to %s" % (remote_url, temp_dirname))

            if not os.path.isdir(temp_dirname):
                os.makedirs(temp_dirname)

            with open(temp_placeholder, "wb") as placeholder_file:
                for data in download:
                    placeholder_file.write(data)
                    yield data

            static_path = os.path.join(SCPYPI_STATIC, "packages", package)

            # parent directory may need to be created
            static_dirname = os.path.dirname(static_path)
            if not os.path.isdir(static_dirname):
                os.makedirs(static_dirname)

            # move temp file into a final location
            shutil.move(placeholder_file.name, static_path)
            logger.info("saved %s" % static_path)

        # return streaming response with the file from the
        # remote server (this is also going to write the file locally)
        return Response(
            download_data(),
            content_type=download.headers.get("content-type"))

    # something went wrong, redirect
    except Exception, e:
        logger.error(str(e))
        if os.path.isfile(temp_placeholder):
            os.remove(temp_placeholder)

        logger.debug("falling back on pypi url")
        return redirect(remote_url)


if __name__ == "__main__":
    app.run()
