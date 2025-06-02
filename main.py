import hashlib
import os
import time
import gi
gi.require_version('Gdk', '3.0')
import logging
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction # Keep this import, but we'll switch to RunScriptAction for activation
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction # Make sure this is imported
from ulauncher.api.shared.event import ItemEnterEvent, KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

logger = logging.getLogger(__name__)

gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gtk
from gi.repository import Wnck

XDG_FALLBACK = os.path.join(os.getenv("HOME"), ".cache")
XDG_CACHE = os.getenv("XDG_CACHE_HOME", XDG_FALLBACK)
CACHE_DIR = os.path.join(XDG_CACHE, "ulauncher_window_switcher")


def is_hidden_window(window):
    state = window.get_state()
    return state & Wnck.WindowState.SKIP_PAGER or state & Wnck.WindowState.SKIP_TASKLIST


def list_windows():
    screen = Wnck.Screen.get_default()
    # We need to force the update as screen is populated lazily by default
    screen.force_update()
    # We need to wait for all events to be processed
    while Gtk.events_pending():
        Gtk.main_iteration()
    return [window for window in screen.get_windows() if not is_hidden_window(window)]


# The activate function using Wnck will no longer be used for the final activation,
# as we're switching to wmctrl for that specific step.
# def activate(window):
#     workspace = window.get_workspace()
#     if workspace is not None:
#         workspace.activate(int(time.time()))
#
#     window.activate(int(time.time()))


class WindowItem:
    def __init__(self, window, previous_selection):
        self.id = window.get_xid()
        self.app_name = (
            window.get_application().get_name()
        )
        self.title = window.get_name()
        self.icon = self.retrieve_or_save_icon(window.get_icon())
        self.is_last = window.get_xid() == previous_selection

    def retrieve_or_save_icon(self, icon):
        file_name = hashlib.sha224(self.app_name.encode("utf-8")).hexdigest()
        icon_full_path = os.path.join(CACHE_DIR, file_name + ".png") # Use os.path.join for better path handling
        if not os.path.isfile(icon_full_path):
            try:
                icon.savev(icon_full_path, "png", [], [])
            except Exception as e:
                logger.error(f"Failed to save icon for {self.app_name} (XID: {self.id}): {e}")
                # Fallback to a default icon if saving fails
                return "images/icon.svg"
        return icon_full_path

    def to_extension_item(self):
        return ExtensionResultItem(
            icon=self.icon,
            name=self.app_name,
            description=self.title,
            selected_by_default=self.is_last,
            # --- MODIFICATION STARTS HERE ---
            # Change from ExtensionCustomAction to RunScriptAction using wmctrl
            on_enter=RunScriptAction("wmctrl -ia {}".format(self.id)),
            # --- MODIFICATION ENDS HERE ---
        )

    def is_matching(self, keyword):
        ascii_keyword = keyword.lower()
        return (
            ascii_keyword in self.app_name.lower()
            or ascii_keyword in self.title.lower()
        )


class WindowSwitcherExtension(Extension):
    def __init__(self):
        super(WindowSwitcherExtension, self).__init__()
        self.selection = None
        self.items = []
        self.previous_selection = None
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        # The ItemEnterEvent Listener is no longer needed if we're using RunScriptAction for activation
        # self.subscribe(ItemEnterEvent, ItemEnterEventListener())
        # Ensure the icon cache directory is created
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or str()
        if len(query.strip()) == 0:
            logger.info("Generating Window List")
            query = ""
            extension.items = [
                WindowItem(window, extension.previous_selection)
                for window in list_windows()
            ]
        matching_items = [
            window_item.to_extension_item()
            for window_item in extension.items
            if window_item.is_matching(query)
        ]
        return RenderResultListAction(matching_items)


# The ItemEnterEventListener class is no longer needed if we're using RunScriptAction
# class ItemEnterEventListener(EventListener):
#     def on_event(self, event, extension):
#         for window in list_windows():
#             if window.get_xid() == event.get_data():
#                 previous_selection = extension.selection
#                 extension.previous_selection = previous_selection
#                 extension.selection = window.get_xid()
#                 activate(window)
#                 break
#         # Wnck.shutdown() should not be here


if __name__ == "__main__":
    WindowSwitcherExtension().run()