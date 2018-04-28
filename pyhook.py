#!/usr/bin/python
#
#    This requires: 
#    at least python-xlib 1.4
#    xwindows must have the "record" extension present, and active.
#    

import sys
import os
import re
import time
import socket
import datetime
import threading
from Tkinter import Tk

from Xlib import X, XK, display, error
from Xlib.ext import record
from Xlib.protocol import rq

"""
    Requirements:
        sudo apt-get install libxtst-dev
        sudo apt-get install python-xlib
"""
class HookManager(threading.Thread):
    """This is the main class. Instantiate it, and you can hand it KeyDown and KeyUp (functions in your own code) which execute to parse the pyxhookkeyevent class that is returned.
    This simply takes these two values for now:
    KeyDown = The function to execute when a key is pressed, if it returns anything. It hands the function an argument that is the pyxhookkeyevent class.
    KeyUp = The function to execute when a key is released, if it returns anything. It hands the function an argument that is the pyxhookkeyevent class.
    """
    __input_stack = list()
    __cmd_count = 1
    __typed = True
    
    def __init__(self):
        threading.Thread.__init__(self)
        self.finished = threading.Event()
        
        # Give these some initial values
        self.mouse_position_x = 0
        self.mouse_position_y = 0
        self.ison = {"shift":False, "caps":False}
        
        # Compile our regex statements.
        self.isshift = re.compile('^Shift')
        self.iscaps = re.compile('^Caps_Lock')
        self.shiftablechar = re.compile('^[a-z0-9]$|^minus$|^equal$|^bracketleft$|^bracketright$|^semicolon$|^backslash$|^apostrophe$|^comma$|^period$|^slash$|^grave$')
        self.logrelease = re.compile('.*')
        self.isspace = re.compile('^space$')
        
        # Assign default function actions (do nothing).
        self.KeyDown = lambda x: True
        self.KeyUp = lambda x: True
        self.MouseAllButtonsDown = lambda x: True
        self.MouseAllButtonsUp = lambda x: True
        
        self.contextEventMask = [X.KeyPress,X.MotionNotify]
        
        # Hook to our display.
        self.local_dpy = display.Display()
        self.record_dpy = display.Display()
        
        # Setting previous count figure
        try:
            with open("logs.txt", "r") as myfile: 
                self.__cmd_count = int(myfile.readlines()[-1][4]) + 1
        except Exception as ex:
            pass

        
    def run(self):
        # Check if the extension is present
        if not self.record_dpy.has_extension("RECORD"):
            print "RECORD extension not found"
            sys.exit(1)
        r = self.record_dpy.record_get_version(0, 0)
        print "RECORD extension version %d.%d" % (r.major_version, r.minor_version)

        # Create a recording context; we only want key and mouse events
        self.ctx = self.record_dpy.record_create_context(
                0,
                [record.AllClients],
                [{
                        'core_requests': (0, 0),
                        'core_replies': (0, 0),
                        'ext_requests': (0, 0, 0, 0),
                        'ext_replies': (0, 0, 0, 0),
                        'delivered_events': (0, 0),
                        'device_events': tuple(self.contextEventMask), #(X.KeyPress, X.ButtonPress),
                        'errors': (0, 0),
                        'client_started': False,
                        'client_died': False,
                }])

        # Enable the context; this only returns after a call to record_disable_context,
        # while calling the callback function in the meantime
        self.record_dpy.record_enable_context(self.ctx, self.processevents)
        # Finally free the context
        self.record_dpy.record_free_context(self.ctx)

    def cancel(self):
        self.finished.set()
        self.local_dpy.record_disable_context(self.ctx)
        self.local_dpy.flush()
    
    def printevent(self, event):
        
        if "BackSpace" in str(event):
            self.__input_stack = self.__input_stack[:-1]
            return
            
        cmd = None
        
        if "mouse" in str(event):
            process_name, _, _ = str(event).split("|")
            key = ''
            ascii = ''
            return
        
        process_name, key, ascii, _ = str(event).split("|")
        self.__input_stack.append((process_name, key, ascii))
        
        if len(self.__input_stack) >= 3:
            cntrl = self.__input_stack[0][1].lower()
            shift = self.__input_stack[1][1].lower()
            cntrl_v = self.__input_stack[2][1].lower()
            if "control" in cntrl and (("v" in shift) or ("shift" in shift and "v" in cntrl_v)):
                self.__typed = False
                
                if "return" in key.lower():
                    r = Tk()
                    r.withdraw()
                    cp_data = r.clipboard_get()
                    r.destroy()
                    cmd = (cp_data, self.__input_stack[:-1][0][0])
        
        if "return" in key.lower() and not cmd:
            cmd = ("".join([x[1] for x in self.__input_stack[:-1]]), self.__input_stack[:-1][0][0])
                    
        with open("logs.txt", "a") as myfile: 
            if cmd:
                cmd_time = str(datetime.datetime.now())
                machine_name = str(socket.gethostname())
                     
                command = '<xy>%d %s %s %s "%s" enter "%s" on %s' % (self.__cmd_count, cmd_time, 
                                                             machine_name, "typed" if self.__typed else "cp-pased",cmd[0], cmd[1], "keyboard")
                myfile.write(command + "\n")
                self.__cmd_count += 1
                self.__input_stack = list()
    
    def HookKeyboard(self):
        pass
        # We don't need to do anything here anymore, since the default mask 
        # is now set to contain X.KeyPress
        #self.contextEventMask[0] = X.KeyPress
    
    def HookMouse(self):
        pass
        # We don't need to do anything here anymore, since the default mask 
        # is now set to contain X.MotionNotify
        
        # need mouse motion to track pointer position, since ButtonPress events
        # don't carry that info.
        #self.contextEventMask[1] = X.MotionNotify
    
    def processevents(self, reply):
        if reply.category != record.FromServer:
            return
        if reply.client_swapped:
            print "* received swapped protocol data, cowardly ignored"
            return
        if not len(reply.data) or ord(reply.data[0]) < 2:
            # not an event
            return
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, self.record_dpy.display, None, None)
            if event.type == X.KeyPress:
                hookevent = self.keypressevent(event)
                self.KeyDown(hookevent)
            elif event.type == X.KeyRelease:
                hookevent = self.keyreleaseevent(event)
                self.KeyUp(hookevent)
            elif event.type == X.ButtonPress:
                hookevent = self.buttonpressevent(event)
                self.MouseAllButtonsDown(hookevent)
            elif event.type == X.ButtonRelease:
                hookevent = self.buttonreleaseevent(event)
                self.MouseAllButtonsUp(hookevent)
            elif event.type == X.MotionNotify:
                # use mouse moves to record mouse position, since press and release events
                # do not give mouse position info (event.root_x and event.root_y have 
                # bogus info).
                self.mousemoveevent(event)
        
        #print "processing events...", event.type

    def keypressevent(self, event):
        matchto = self.lookup_keysym(self.local_dpy.keycode_to_keysym(event.detail, 0))
        if self.shiftablechar.match(self.lookup_keysym(self.local_dpy.keycode_to_keysym(event.detail, 0))): ## This is a character that can be typed.
            if self.ison["shift"] == False:
                keysym = self.local_dpy.keycode_to_keysym(event.detail, 0)
                return self.makekeyhookevent(keysym, event)
            else:
                keysym = self.local_dpy.keycode_to_keysym(event.detail, 1)
                return self.makekeyhookevent(keysym, event)
        else: ## Not a typable character.
            keysym = self.local_dpy.keycode_to_keysym(event.detail, 0)
            if self.isshift.match(matchto):
                self.ison["shift"] = self.ison["shift"] + 1
            elif self.iscaps.match(matchto):
                if self.ison["caps"] == False:
                    self.ison["shift"] = self.ison["shift"] + 1
                    self.ison["caps"] = True
                if self.ison["caps"] == True:
                    self.ison["shift"] = self.ison["shift"] - 1
                    self.ison["caps"] = False
            return self.makekeyhookevent(keysym, event)
    
    def keyreleaseevent(self, event):
        if self.shiftablechar.match(self.lookup_keysym(self.local_dpy.keycode_to_keysym(event.detail, 0))):
            if self.ison["shift"] == False:
                keysym = self.local_dpy.keycode_to_keysym(event.detail, 0)
            else:
                keysym = self.local_dpy.keycode_to_keysym(event.detail, 1)
        else:
            keysym = self.local_dpy.keycode_to_keysym(event.detail, 0)
        matchto = self.lookup_keysym(keysym)
        if self.isshift.match(matchto):
            self.ison["shift"] = self.ison["shift"] - 1
        return self.makekeyhookevent(keysym, event)

    def buttonpressevent(self, event):
        #self.clickx = self.rootx
        #self.clicky = self.rooty
        return self.makemousehookevent(event)

    def buttonreleaseevent(self, event):
        #if (self.clickx == self.rootx) and (self.clicky == self.rooty):
            ##print "ButtonClick " + str(event.detail) + " x=" + str(self.rootx) + " y=" + str(self.rooty)
            #if (event.detail == 1) or (event.detail == 2) or (event.detail == 3):
                #self.captureclick()
        #else:
            #pass
        
        return self.makemousehookevent(event)
        
        #    sys.stdout.write("ButtonDown " + str(event.detail) + " x=" + str(self.clickx) + " y=" + str(self.clicky) + "\n")
        #    sys.stdout.write("ButtonUp " + str(event.detail) + " x=" + str(self.rootx) + " y=" + str(self.rooty) + "\n")
        #sys.stdout.flush()

    def mousemoveevent(self, event):
        self.mouse_position_x = event.root_x
        self.mouse_position_y = event.root_y

    # need the following because XK.keysym_to_string() only does printable chars
    # rather than being the correct inverse of XK.string_to_keysym()
    def lookup_keysym(self, keysym):
        for name in dir(XK):
            if name.startswith("XK_") and getattr(XK, name) == keysym:
                return name.lstrip("XK_")
        return "[%d]" % keysym

    def asciivalue(self, keysym):
        asciinum = XK.string_to_keysym(self.lookup_keysym(keysym))
        if asciinum < 256:
            return asciinum
        else:
            return 0
    
    def makekeyhookevent(self, keysym, event):
        storewm = self.xwindowinfo()
        if event.type == X.KeyPress:
            MessageName = "key down"
        elif event.type == X.KeyRelease:
            MessageName = "key up"
        return pyxhookkeyevent(storewm["handle"], storewm["name"], storewm["class"], self.lookup_keysym(keysym), self.asciivalue(keysym), False, event.detail, MessageName)
    
    def makemousehookevent(self, event):
        storewm = self.xwindowinfo()
        if event.detail == 1:
            MessageName = "mouse left "
        elif event.detail == 3:
            MessageName = "mouse right "
        elif event.detail == 2:
            MessageName = "mouse middle "
        elif event.detail == 5:
            MessageName = "mouse wheel down "
        elif event.detail == 4:
            MessageName = "mouse wheel up "
        else:
            MessageName = "mouse " + str(event.detail) + " "

        if event.type == X.ButtonPress:
            MessageName = MessageName + "down"
        elif event.type == X.ButtonRelease:
            MessageName = MessageName + "up"
        return pyxhookmouseevent(storewm["handle"], storewm["name"], storewm["class"], (self.mouse_position_x, self.mouse_position_y), MessageName)
    
    def xwindowinfo(self):
        try:
            windowvar = self.local_dpy.get_input_focus().focus
            wmname = windowvar.get_wm_name()
            wmclass = windowvar.get_wm_class()
            wmhandle = str(windowvar)[20:30]
        except:
            ## This is to keep things running smoothly. It almost never happens, but still...
            return {"name":None, "class":None, "handle":None}
        if (wmname == None) and (wmclass == None):
            try:
                windowvar = windowvar.query_tree().parent
                wmname = windowvar.get_wm_name()
                wmclass = windowvar.get_wm_class()
                wmhandle = str(windowvar)[20:30]
            except:
                ## This is to keep things running smoothly. It almost never happens, but still...
                return {"name":None, "class":None, "handle":None}
        if wmclass == None:
            return {"name":wmname, "class":wmclass, "handle":wmhandle}
        else:
            return {"name":wmname, "class":wmclass[0], "handle":wmhandle}

class pyxhookkeyevent:
    """This is the class that is returned with each key event.f
    It simply creates the variables below in the class.
    
    Window = The handle of the window.
    WindowName = The name of the window.
    WindowProcName = The backend process for the window.
    Key = The key pressed, shifted to the correct caps value.
    Ascii = An ascii representation of the key. It returns 0 if the ascii value is not between 31 and 256.
    KeyID = This is just False for now. Under windows, it is the Virtual Key Code, but that's a windows-only thing.
    ScanCode = Please don't use this. It differs for pretty much every type of keyboard. X11 abstracts this information anyway.
    MessageName = "key down", "key up".
    """
    
    def __init__(self, Window, WindowName, WindowProcName, Key, Ascii, KeyID, ScanCode, MessageName):
        self.Window = Window
        self.WindowName = WindowName
        self.WindowProcName = WindowProcName
        self.Key = Key
        self.Ascii = Ascii
        self.KeyID = KeyID
        self.ScanCode = ScanCode
        self.MessageName = MessageName
    
    def __str__(self):
        """
        return "Window Handle: " + str(self.Window) + "\nWindow Name: " + str(self.WindowName) + "\nWindow's Process Name: " + str(self.WindowProcName) + "\nKey Pressed: " + str(self.Key) + "\nAscii Value: " + str(self.Ascii) + "\nKeyID: " + str(self.KeyID) + "\nScanCode: " + str(self.ScanCode) + "\nMessageName: " + str(self.MessageName) + "\n"
        """
        return "%s|%s|%s|%s" % (self.WindowProcName, self.Key, self.Ascii, self.MessageName)

class pyxhookmouseevent:
    """This is the class that is returned with each key event.f
    It simply creates the variables below in the class.
    
    Window = The handle of the window.
    WindowName = The name of the window.
    WindowProcName = The backend process for the window.
    Position = 2-tuple (x,y) coordinates of the mouse click
    MessageName = "mouse left|right|middle down", "mouse left|right|middle up".
    """
    
    def __init__(self, Window, WindowName, WindowProcName, Position, MessageName):
        self.Window = Window
        self.WindowName = WindowName
        self.WindowProcName = WindowProcName
        self.Position = Position
        self.MessageName = MessageName
    
    def __str__(self):
        """
        print "===",str(str(self.WindowProcName) + str(self.Position) + str(self.MessageName))
        return "Window Handle: " + str(self.Window) + "\nWindow Name: " + str(self.WindowName) + "\nWindow's Process Name: " + str(self.WindowProcName) + "\nPosition: " + str(self.Position) + "\nMessageName: " + str(self.MessageName) + "\n"
        """
        return "%s|%s|%s" % (self.WindowProcName, self.Position, self.MessageName)

    
if __name__ == '__main__':
    hm = HookManager()
    hm.HookKeyboard()
    hm.HookMouse()
    hm.KeyDown = hm.printevent
    hm.MouseAllButtonsDown = hm.printevent
    hm.start()
    time.sleep(20)
hm.cancel()