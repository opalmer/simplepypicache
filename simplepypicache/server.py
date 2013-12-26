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

import json
import os
import re
import shutil
import urllib2
from httplib import OK
from datetime import datetime, timedelta

from distlib.locators import SimpleScrapingLocator
from flask import Response, render_template, redirect

from simplepypicache.logger import logger

PYPI_INDEX = os.environ["SCPYPI_INDEX"]
CACHED_PACKAGES = os.environ["SCPYPI_ROOT"]
STATIC_PACKAGES = os.environ.get(
    "SCPYPI_STATIC", os.path.join(CACHED_PACKAGES, "static"))
CACHED_DISTS_FILES = os.environ.get("SCPYPI_DISTS_FILE")
PYPI_ROOT = PYPI_INDEX.replace("/simple", "")
SCRAPER = SimpleScrapingLocator(PYPI_INDEX)
REGEX_URL = re.compile("^.*/(.+)#md5=([a-z0-9]{32})$")


class Index(object):
    """constructs ain index which mimics https://pypi.python.org/simple"""
    __name__ = "index"
    MAX_AGE = timedelta(days=1)

    def __init__(self):
        self._dists = None
        self._dists = self.load_cached_dists()
        self.last_hit = datetime.now()

    @property
    def dists(self):
        """returns a list of all distributions"""
        now = datetime.now()
        if now - self.last_hit > self.MAX_AGE:
            self._dists = list(SCRAPER.get_distribution_names())
            self._dists.sort()

        self.last_hit = datetime.now()
        return self._dists

    def load_cached_dists(self):
        """
        load cached distributions from a file or write them out
        to $CACHED_DISTS_FILES
        """
        if CACHED_DISTS_FILES is not None \
                and os.path.isfile(CACHED_DISTS_FILES):
            with open(CACHED_DISTS_FILES, "r") as stream:
                try:
                    return json.loads(stream.read().strip())
                except ValueError:
                    os.remove(CACHED_DISTS_FILES)

        logger.info("retrieving dists using the scraper")
        data = list(SCRAPER.get_distribution_names())
        data.sort()

        if CACHED_DISTS_FILES is not None:
            with open(CACHED_DISTS_FILES, "w") as stream:
                stream.write(json.dumps(data))

        return data

    def __call__(self):
        """renders the template which produces the index"""
        return render_template("simple.html", package_names=self.dists)


def single_package_index(package):
    """returns the web page for individual package (ex. /simple/foo/)"""
    remote_page = SCRAPER.get_page(PYPI_INDEX + package)

    if remote_page is None:
        return "Not Found (%s does not have any releases)" % package

    project = SCRAPER.get_project(package)
    project_versions = project.keys()
    project_versions.sort(reverse=True)

    # various kinds types of urls
    internal_urls = []
    basic_links = []
    homepages = []
    downloads = []

    # scrape the remote index and retrieve all links
    for remote_url, url_type in remote_page.links:
        local_url = remote_url.replace(PYPI_ROOT, "")

        # internal links (packages hosted on PyPi [what we're caching])
        if url_type == "internal":
            link_name, md5 = REGEX_URL.match(remote_url).groups()
            internal_urls.insert(0, (url_type, local_url, link_name))

        # unspecified url
        elif url_type == "":
            basic_links.extend([(
                url_type, remote_url, remote_url)] * len(project_versions))

        # direct links to a project's homepage(s)
        elif url_type == "homepage":
            for version in project_versions:
                homepages.append(
                    (url_type, remote_url, "%s home_page" % version))

        # direct remote download links
        elif url_type == "download":
            for version in project_versions:
                if version in remote_url:
                    downloads.append(
                        (url_type, local_url, "%s download" % version))
                    break

    # pass it all along to the template and have
    # it render the page
    return render_template(
        "package.html",
        data=internal_urls + basic_links + homepages + downloads,
        package=package,
        versions=project_versions)


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
    filename = os.path.basename(package)
    placeholder = os.path.join(CACHED_PACKAGES, filename + ".download")

    # the download placeholder file exists so for now
    # we just tell the request to come from the external url
    pypi_url = "/".join([PYPI_ROOT, "packages", package])
    if os.path.isfile(placeholder):
        logger.info("%s is being downloaded, redirecting to remote" % package)
        return redirect(pypi_url)

    # Not in progress or already downloaded?  Try to request the file
    # so we can download it.
    try:
        download = urllib2.urlopen(pypi_url)

        if download.code != OK:
            raise urllib2.HTTPError(
                pypi_url, download.code, "failed to connect",
                download.headers, download.fp)

    # on failure however, redirect instead so the client can choose what
    # to do instead
    except urllib2.HTTPError, e:
        logger.error(str(e))
        logger.debug("falling back on pypi url")
        return redirect(pypi_url)

    try:
        # download the file
        def download_data():
            logger.debug("downloading %s" % pypi_url)

            with open(placeholder, "wb") as placeholder_file:
                for data in download:
                    placeholder_file.write(data)
                    yield data

            logger.info("saved %s" % placeholder_file.name)
            full_static_path = os.path.join(
                STATIC_PACKAGES, package)

            # parent directory may need to be created
            dirname = os.path.dirname(full_static_path)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
                logger.debug("created %s" % dirname)

            # move temp file into a final location
            shutil.move(placeholder_file.name, full_static_path)
            logger.debug(
                "moved %s -> %s" % (placeholder_file.name, full_static_path))

        # return streaming response with the file from the
        # remote server (this is also going to write the file locally)
        return Response(
            download_data(),
            content_type=download.headers.get("content-type"))

    # something went wrong, redirect
    except Exception, e:
        logger.error(str(e))
        if os.path.isfile(placeholder):
            os.remove(placeholder)

        logger.debug("falling back on pypi url")
        return redirect(pypi_url)

