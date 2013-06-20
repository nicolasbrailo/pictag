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

import gettext
from gettext import gettext as _
gettext.textdomain('pictag')

import pyexiv2
import math
import os

from gi.repository import GObject, Champlain, Clutter # pylint: disable=E0611

import logging
logger = logging.getLogger('pictag')


class PictagImage(GObject.GObject):
    """
    A Pictag image
    """
    __gtype_name__ = "PictagImage"

    __gsignals__ = {
        'position-changed': (GObject.SIGNAL_RUN_FIRST, None,
                             (float, float,)),
    }


    def __init__(self, path_full):
        GObject.GObject.__init__(self)

        #Variables
        self.__path_full = path_full
        self.__dt = None
        self.__longitude = None
        self.__latitude = None
        self.__marker = None
        #initial read image metadata
        self.__metadata = pyexiv2.ImageMetadata(self.__path_full)
        self.__metadata.read()

        #update the data from image metadata
        self.__metadata_datetime_get()
        self.__metadata_longitude_get()
        self.__metadata_latitude_get()

        self.__marker_update()
        self.__texture = None

    def __marker_update(self):
        """ update the marker """
        if self.__latitude and self.__longitude:
            color = Clutter.Color.new(0, 0, 255, 255)
            self.__marker = Champlain.CustomMarker()
            self.__marker.set_background_color(color)
            self.__marker.set_size(10, 10)
            self.__marker.set_anchor_point_from_gravity(Clutter.Gravity.CENTER)
            self.__marker.set_location(self.__latitude, self.__longitude)
            self.__marker.connect("enter-event", self.__marker_enter)
            self.__marker.connect("leave-event", self.__marker_leave)
        else:
            self.__marker = None

    def __marker_enter(self, marker, data):
        logger.debug("mouse enter '%s'" % (self.__path_full))
        text = Clutter.Text()
        text.set_markup("<small><b>%s</b>\n" \
                            "%f N / %f E" \
                            "</small>" % (os.path.splitext(os.path.basename(self.__path_full))[0],
                        float(self.__latitude), float(self.__longitude)))
        self.__marker.add_actor(text)
        #a big texture seems to crash mesa. see bug lp:1017243
        #texture = Clutter.Texture.new_from_file(self.__path_full)
        #texture.set_keep_aspect_ratio(True)
        #if texture.get_width() > texture.get_height():
        #    texture.set_width(128)
        #else:
        #    texture.set_height(128)
        #self.__marker.add_actor(texture)
        self.__marker.show_all()
        

    def __marker_leave(self, marker, data):
        self.__marker.get_children()[0].remove_all()


    def save(self):
        """ write the metadata to image file """
        self.__metadata.write()
        logger.debug("metadata written for '%s'" % (self.path_full))


    def position_get(self):
        """ get the image position """
        return (self.__latitude, self.__longitude)


    def position_set(self, latitude, longitude):
        """ set the image position. don't forget to write the metadata! """
        #latitude
        self.__latitude = float(latitude)
        self.__metadata_latitude_set(self.__latitude)
        #longitude
        self.__longitude = float(longitude)
        self.__metadata_longitude_set(self.__longitude)
        #update the marker
        self.__marker_update()
        #emit signal
        self.emit('position-changed', self.__latitude, self.__longitude)

    @property
    def marker(self):
        """ getter for marker """
        return self.__marker

    @property
    def path_full(self):
        """ path full getter """
        return self.__path_full

    @property
    def dt(self):
        """ date/time getter """
        return self.__dt

    def __dec_to_sex(self, x):
        degrees = int(math.floor(x))
        minutes = int(math.floor(60 * (x - degrees)))
        seconds = int(math.floor(6000 * (60 * (x - degrees) - minutes)))
        return (pyexiv2.utils.make_fraction(degrees, 1), pyexiv2.utils.make_fraction(minutes, 1), pyexiv2.utils.make_fraction(seconds, 100))

    def __sex_to_dec(self, fractions):
        degrees = float(fractions[0])
        minutes = float(fractions[1])
        seconds = float(fractions[2])    
        minutes = minutes + (seconds/60)
        degrees = degrees + (minutes/60)
        return degrees

    def __metadata_datetime_get(self):
        """ get date/time metadata """
        key = "Exif.Photo.DateTimeOriginal"
        try:
            self.__dt = self.__metadata[key].value.strftime('%d %B %Y, %H:%M:%S')
        except KeyError:
            pass
        except Exception, e:
            logger.warning("can not get date/time '%s' for image '%s': %s" % (self.__metadata[key].raw_value, self.path_full, str(e)))


    def __metadata_latitude_set(self, latitude):
        """ set the latitude on the given image metadata. don't forget to write the metadata! """
        key_ref = 'Exif.GPSInfo.GPSLatitudeRef'
        if latitude < 0:
            self.__metadata[key_ref] = pyexiv2.ExifTag(key_ref, 'S')
        else:
            self.__metadata[key_ref] = pyexiv2.ExifTag(key_ref, 'N')
        # exiv2 requires lat/long in degrees, minutes and seconds
        key = 'Exif.GPSInfo.GPSLatitude'
        self.__metadata[key] = pyexiv2.ExifTag(key, self.__dec_to_sex(abs(float(latitude))))

    def __metadata_longitude_set(self, longitude):
        """ set the longitude on the given image metadata. don't forget to write the metadata! """
        key_ref = 'Exif.GPSInfo.GPSLongitudeRef'
        if longitude < 0:
            self.__metadata[key_ref] = pyexiv2.ExifTag(key_ref, 'W')
        else:
            self.__metadata[key_ref] = pyexiv2.ExifTag(key_ref, 'E')
        # exiv2 requires lat/long in degrees, minutes and seconds
        key = 'Exif.GPSInfo.GPSLongitude'
        self.__metadata[key] = pyexiv2.ExifTag(key, self.__dec_to_sex(abs(float(longitude))))

    def __metadata_latitude_get(self):
        """ get the latitude from the given metadata """
        key_ref = 'Exif.GPSInfo.GPSLatitudeRef'
        key = 'Exif.GPSInfo.GPSLatitude'
    
        try:
            par = 1
            if self.__metadata[key_ref].raw_value == 'S':
                par = -1
            elif self.__metadata[key_ref].raw_value == 'N':
                par = 1
            else:
                raise Exception("invalid '%s' '%s' in metadata found" % (key_ref, self.__metadata[key_ref]))
        except KeyError:
            #latitude not available
            pass
        else:
            self.__latitude = par * self.__sex_to_dec(self.__metadata[key].value)

    def __metadata_longitude_get(self):
        """ get the longitude from the given metadata or None """
        key_ref = 'Exif.GPSInfo.GPSLongitudeRef'
        key = 'Exif.GPSInfo.GPSLongitude'
    
        try:
            par = 1
            if self.__metadata[key_ref].raw_value == 'W':
                par = -1
            elif self.__metadata[key_ref].raw_value == 'E':
                par = 1
            else:
                raise Exception("invalid '%s' '%s' in metadata found" % (key_ref, self.__metadata[key_ref]))
        except KeyError:
            #longitude not available
            pass
        else:
            self.__longitude = par * self.__sex_to_dec(self.__metadata[key].value)

