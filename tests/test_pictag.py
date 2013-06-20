#!/usr/bin/python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (C) 2012 Thomas Bechtold <thomasbechtold@jpberlin.de>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 3, as published 
# by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

import sys
import os.path
import unittest
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

import pyexiv2
from pictag.PictagImage import PictagImage
import tempfile
import shutil

#plain image without any tags
TEST_PLAIN = os.path.realpath(os.path.join(os.path.dirname(__file__), "plain.png"))
TEST_WITH_TAGS = os.path.realpath(os.path.join(os.path.dirname(__file__), "with-tags.jpg"))

class TestPictagImage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='pictag_tests_')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_image_plain(self):
        """ read image without tags """
        img = PictagImage(TEST_PLAIN)
        self.assertEqual(img.path_full, TEST_PLAIN)
        #no lat/lon/dt set on the image
        lat, lon = img.position_get()
        self.assertEqual(lat, None)
        self.assertEqual(lon, None)
        self.assertEqual(img.dt, None)
    
    def test_image_with_tags(self):
        """ read image with tags """
        img = PictagImage(TEST_WITH_TAGS)
        self.assertEqual(img.path_full, TEST_WITH_TAGS)
        lat, lon = img.position_get()
        self.assertEqual(lat, 52.918533333333336)
        self.assertEqual(lon, 10.900019444444444)
        self.assertEqual(img.dt, "28 April 2012, 15:25:39")

    def test_image_write_tags(self):
        """ write tags to an image """
        shutil.copy(TEST_PLAIN, self.tmpdir)
        img = PictagImage(os.path.join(self.tmpdir, os.path.basename(TEST_PLAIN)))
        #no lat/lon/dt set on the image
        lat, lon = img.position_get()
        self.assertEqual(lat, None)
        self.assertEqual(lon, None)
        #change data (but still not written to file)
        img.position_set(10.0, 20.0)
        lat, lon = img.position_get()
        self.assertEqual(lat, 10)
        self.assertEqual(lon, 20)
        #open a new pictag with the same file. data is not written to file so tags should be unavailable
        img2 = PictagImage(os.path.join(self.tmpdir, os.path.basename(TEST_PLAIN)))
        lat, lon = img2.position_get()
        self.assertEqual(lat, None)
        self.assertEqual(lon, None)
        #write data of img
        img.save()
        #load file again. data should be written now
        img3 = PictagImage(os.path.join(self.tmpdir, os.path.basename(TEST_PLAIN)))
        lat, lon = img3.position_get()
        self.assertEqual(lat, 10)
        self.assertEqual(lon, 20)
            

if __name__ == '__main__':    
    unittest.main()
