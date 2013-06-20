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

import sys
import os
import datetime
import math
import pyexiv2
import glob

from gi.repository import GtkClutter, Clutter, GObject, GLib # pylint: disable=E0611
from gi.repository import GObject, Gtk, Champlain, GtkChamplain, Gdk, GdkPixbuf, Gio # pylint: disable=E0611

import logging
logger = logging.getLogger('pictag')

from pictag_lib import Window
from pictag.AboutPictagDialog import AboutPictagDialog
from pictag.PreferencesPictagDialog import PreferencesPictagDialog
from pictag.PictagImage import PictagImage


# See pictag_lib.Window.py for more details about how this class works
class PictagWindow(Window):
    __gtype_name__ = "PictagWindow"

    
    def finish_initializing(self, builder): # pylint: disable=E1002
        """Set up the main window """
        super(PictagWindow, self).finish_initializing(builder)

        self.AboutDialog = AboutPictagDialog
        self.PreferencesDialog = PreferencesPictagDialog

        box_map = self.builder.get_object("box_map")
        #buttons on top of the map
        box_map_buttons = self.builder.get_object("box_map_buttons")
        #treeview and liststore on the left side
        self.liststore = Gtk.ListStore(PictagImage, GdkPixbuf.Pixbuf, str, str)
        self.treeview_images = self.builder.get_object("treeview_images")
        self.treeview_images.set_model(self.liststore)
        self.treeview_images.set_tooltip_column(3)
        selection = self.treeview_images.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        selection.connect("changed", self.treeview_images_selection_changed)

        #image preview on the bottom left corner
        self.image_preview = self.builder.get_object("image_preview")
        self.image_preview_label = self.builder.get_object("image_preview_label")
        #statusbar at the bottom
        self.statusbar = self.builder.get_object("statusbar")

        #cell renderers for image and image name
        renderer_pixbuf = Gtk.CellRendererPixbuf()
        column_pixbuf = Gtk.TreeViewColumn("Image", renderer_pixbuf, pixbuf=1)
        self.treeview_images.append_column(column_pixbuf)
        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=2)
        self.treeview_images.append_column(column_text)

        #map embed and view
        embed = GtkChamplain.Embed()
        embed.set_size_request(640, 480)
        #the map view
        self.view = embed.get_view()
        self.view.set_reactive(True)
        self.view.connect('button-release-event', self.view_mouse_click_cb, self.view)
        self.view.connect('motion-event', self.view_motion_event_cb, self.view)
        self.view.connect('leave-event', self.view_leave_event_cb, self.view)
        self.view.set_property('kinetic-mode', True)
        self.view.set_property('zoom-level', 5)

        scale = Champlain.Scale()
        scale.connect_view(self.view)
        self.view.bin_layout_add(scale, Clutter.BinAlignment.START, Clutter.BinAlignment.END)

        #center map on current position
        try:
                lat_cur, long_cur = self.get_current_location()
                logger.debug("your current position is: %s °N/%s °E" % (lat_cur, long_cur))
                self.view.center_on(float(lat_cur), float(long_cur))
        except Exception, e:
                logger.info("can not find your current position: %s" % (str(e)))

        #layer for image markers
        self.marker_layer_images = Champlain.MarkerLayer()
        self.view.add_layer(self.marker_layer_images)

        #layer for position marker
        self.marker_layer_position = Champlain.MarkerLayer()
        self.view.add_layer(self.marker_layer_position)

        #button to show/hide image markers
        button = Gtk.ToggleButton(label="Image markers")
        button.set_active(True)
        button.connect("toggled", self.marker_layer_images_toggle)
        box_map_buttons.add(button)

        #zoom in button and signal
        button = Gtk.Button.new_from_stock(Gtk.STOCK_ZOOM_IN)
        button.connect("clicked", self.view_zoom_in)
        box_map_buttons.add(button)

        #zoom out button and signal
        button = Gtk.Button(stock=Gtk.STOCK_ZOOM_OUT)
        button.connect("clicked", self.view_zoom_out)
        box_map_buttons.add(button)

        #map layer combo box #FIXME: not all sources work. Fill a bug against libchamplain!
        combo = Gtk.ComboBox()
        map_source_factory = Champlain.MapSourceFactory.dup_default()
        liststore = Gtk.ListStore(str, str)
        for source in map_source_factory.get_registered():
            liststore.append([source.get_id(), source.get_name()])
        combo.set_model(liststore)
        cell = Gtk.CellRendererText()
        combo.pack_start(cell, False)
        combo.add_attribute(cell, 'text', 1)
        combo.connect("changed", self.map_source_changed)
        combo.set_active(0)
        box_map_buttons.add(combo)

        button = Gtk.Image()
        self.view.connect("notify::state", self.view_state_changed, button)
        box_map_buttons.pack_end(button, False, False, 0)

        box_map.pack_start(box_map_buttons, expand=False, fill=False, padding=0)
        box_map.add(embed)
        box_map.show_all()

        #use latest used image path to fill liststore
        if self.settings.get_string("image-path-latest") == '~':
            d = os.path.expanduser(self.settings.get_string("image-path-latest"))
        else:
            d = os.path.abspath(self.settings.get_string("image-path-latest"))
        self.liststore_update(d)

        self.image_preview.hide()
        self.image_preview_label.hide()


    def treeview_images_selection_changed(self, selection):
        """ handle the preview image and preview label """
        (model, pathlist) = selection.get_selected_rows()
        if len(pathlist) == 1:
            tree_iter = model.get_iter(pathlist[0])
            pictag_image = model.get_value(tree_iter,0)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(pictag_image.path_full, 128, 128)
            self.image_preview.set_from_pixbuf(pixbuf)
            self.image_preview.set_tooltip_text(pictag_image.path_full)
            latitude, longitude = pictag_image.position_get()
            self.image_preview_label.set_markup(_("<big>%(path)s</big>\n"
                                                  "date/time: %(datetime)s\n"
                                                  "latitude: %(latitude)s N\n"
                                                  "longitude : %(longitude)s E\n"
                                                  % {'path': os.path.basename(pictag_image.path_full),
                                                     'datetime': pictag_image.dt or "-",
                                                     'latitude': latitude or "-",
                                                     'longitude': longitude or "-"}))
            self.image_preview.show()
            self.image_preview_label.show()
        elif len(pathlist) == 0:
            self.image_preview.hide()
            self.image_preview_label.hide()
        else:
            #multiple images selected. disable preview
            self.image_preview.hide()
            markup = _("%d pictures selected\n") % (len(pathlist))
            self.image_preview_label.set_markup(markup)
            self.image_preview_label.show()


    def on_button_select_folder_clicked(self, widget):
        """ choose the folder with images """
        dialog = Gtk.FileChooserDialog(_("Please choose a folder"), self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             "Select", Gtk.ResponseType.OK))
        dialog.set_default_size(800, 400)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            #update liststore
            self.liststore_update(dialog.get_filename())
            #update last used path in settings
            self.settings.set_string("image-path-latest", dialog.get_filename())
        elif response == Gtk.ResponseType.CANCEL:
            pass
        #don't show any preview stuff
        self.image_preview.hide()
        self.image_preview_label.hide()
        dialog.destroy()


    def view_zoom_in(self, widget):
        """ map zoom in """
        self.view.zoom_in()


    def view_zoom_out(self, widget):
        """ map zoom out """
        self.view.zoom_out()

    
    def __marker_layer_images_update(self):
        """ update the image markers """
        self.marker_layer_images.remove_all()
        for row in self.liststore:
            pictag_image = row[0]
            if pictag_image.marker:
                self.marker_layer_images.add_marker(pictag_image.marker)


    def marker_layer_images_toggle(self, widget):
        """ """
        if widget.get_active():
            self.__marker_layer_images_update()
            self.marker_layer_images.show()
        else:
            self.marker_layer_images.hide()
            self.marker_layer_images.remove_all()


    def view_mouse_click_cb(self, actor, event, view):
        """ mouse clicked on the map view """
        x, y = event.x, event.y
        lon, lat = view.x_to_longitude(x), view.y_to_latitude(y)
        logger.debug("map mouse click at: %f %f" % (lon, lat))

        #set for all selected image the current position
        selection = self.treeview_images.get_selection()
        (model, pathlist) = selection.get_selected_rows()
        for path in pathlist:
            tree_iter = model.get_iter(path)
            pictag_image = model.get_value(tree_iter, 0)
            pictag_image.position_set(lat, lon)
            pictag_image.save()

        context_id = self.statusbar.get_context_id("metadata-written")
        self.statusbar.push(context_id, _("%d image(s) saved" % (len(pathlist))))
            
        #update the red position marker
        self.marker_layer_position.remove_all()
        marker = Champlain.Point()
        marker.set_size(20)
        color = Clutter.Color.new(255, 0, 0, 100)
        marker.set_color(color)
        marker.set_location(lat, lon)
        self.marker_layer_position.add_marker(marker)
        self.marker_layer_position.show()

        self.__marker_layer_images_update()

        return True


    def view_motion_event_cb(self, actor, event, view):
        """ mouse motion on the map view """
        x, y = event.x, event.y
        lon, lat = view.x_to_longitude(x), view.y_to_latitude(y)
        context_id = self.statusbar.get_context_id("mouse-pos")
        self.statusbar.push(context_id, _("%(latitude).5f °N / %(longitude).5f °E") % 
                            {'latitude':lat, 'longitude':lon})
        return True


    def view_leave_event_cb(self, actor, event, view):
        """ mouse leave the map view """
        context_id = self.statusbar.get_context_id("mouse-pos")
        self.statusbar.push(context_id, "")
        return True


    def map_source_changed(self, widget):
        model = widget.get_model()
        iter = widget.get_active_iter()
        id = model.get_value(iter, 0)
        map_source_factory = Champlain.MapSourceFactory.dup_default()
        source = map_source_factory.create_cached_source(id);
        self.view.set_property("map-source", source)


    def view_state_changed(self, view, paramspec, image):
        state = view.get_state()
        if state == Champlain.State.LOADING:
            image.set_from_stock(Gtk.STOCK_NETWORK, Gtk.IconSize.BUTTON)
            image.set_tooltip_text(_("loading data..."))
        else:
            image.clear()


    def get_current_location(self):
        """
        Gets the current location from geolocation via IP (only method
        currently supported)"""

        import dbus
        bus = dbus.SessionBus()

        try:
            geoclue = bus.get_object(
                'org.freedesktop.Geoclue.Providers.UbuntuGeoIP',
                '/org/freedesktop/Geoclue/Providers/UbuntuGeoIP')
        except dbus.exceptions.DBusException:
            geoclue = bus.get_object(
                'org.freedesktop.Geoclue.Providers.Hostip',
                '/org/freedesktop/Geoclue/Providers/Hostip')
        
        position_info = geoclue.GetPosition(
            dbus_interface='org.freedesktop.Geoclue.Position')

        position = {}
        position['timestamp'] = position_info[1]
        position['latitude'] = position_info[2]
        position['longitude'] = position_info[3]
        position['altitude'] = position_info[4]
        
        return position['latitude'], position['longitude']


    def image_position_changed(self, image):
        self.__marker_layer_images_update()
    
    
    def liststore_append_idle(self, image):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(image.path_full, 32, 32)
        #pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size("/home/tom/devel/pictag-old/bilder-test/address-book-new.png", 32, 32)
        self.liststore.append([image, pixbuf, os.path.splitext(os.path.basename(image.path_full))[0], image.dt])
        #logger.debug("appended '%s'" % (image.path_full))
        #update the window even if we have big files
        while Gtk.events_pending():
            Gtk.main_iteration()

        #update the marker layers
        #self.__marker_layer_images_update()
        return False


    def liststore_fill(self, images, step=5):
      '''Generator to fill the listmodel of a treeview progressively.'''
      n = 0
      self.treeview_images.freeze_child_notify()
      for img in images:
          #fill the liststore model
          image = PictagImage(img)
          pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(image.path_full, 32, 32)
          self.liststore.append([image, pixbuf, os.path.splitext(os.path.basename(image.path_full))[0], image.dt])


	      # yield to gtk main loop once awhile
          n += 1
          if (n % step) == 0:
              self.treeview_images.thaw_child_notify()
              yield True
              #update the marker layers
              self.__marker_layer_images_update()
              self.treeview_images.freeze_child_notify()

      self.treeview_images.thaw_child_notify()
      # stop idle_add()
      yield False

    def liststore_update(self, path):
        """ update the list with images """
        #cleanup current list entries
        self.liststore.clear()
        #remove all markers
        self.marker_layer_images.remove_all()
        #add new images from given path

        images = list()
        if os.path.isdir(path):
            for filename in os.listdir(path):
                if filename.upper().endswith("JPG") or filename.upper().endswith("PNG"):
                    images.append(os.path.join(path, filename))
            

        loader = self.liststore_fill(images)
        GLib.idle_add(loader.next)

