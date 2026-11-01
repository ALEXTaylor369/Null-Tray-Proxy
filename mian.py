import sys
from Xlib import X, display
from Xlib.protocol import event
from Xlib.ext import composite, damage as xdamage, xtest
import pydbus

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Id" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <signal name="NewIcon"/>
  </interface>
</node>
"""

dpy = display.Display()
proxies = []


class Proxy:
    def __init__(self, wid, idx):
        self.wid = wid
        self.win = dpy.create_resource_object("window", wid)
        self.w = 1
        self.h = 1
        self.pix = b""
        self.path = "/SNI/" + str(idx)

        scr = dpy.screen()
        self.box = scr.root.create_window(
            -100, -100, 64, 64, 0, scr.root_depth,
            X.InputOutput, X.CopyFromParent, override_redirect=True)
        composite.redirect_window(self.box, composite.CompositeRedirectManual)
        self.win.reparent(self.box, 0, 0)
        self.box.map()
        self.win.map()
        dpy.sync()

        self.dmg = self.win.create_damage(xdamage.DamageReportNonEmpty)

        self.bus = pydbus.SessionBus()
        self.pub = self.bus.publish("org.kde.StatusNotifierItem", self.path, self)

    @property
    def Id(self):
        return "xembed-py"

    @property
    def Status(self):
        return "Active"

    @property
    def IconPixmap(self):
        return [(self.w, self.h, self.pix)] if self.pix else []

    def Activate(self, x, y):
        self.click(1)

    def ContextMenu(self, x, y):
        self.click(3)

    def NewIcon(self):
        pass

    def grab(self):
        g = self.win.get_geometry()
        if g.width <= 1 or g.height <= 1:
            return
        img = self.win.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xffffffff)
        self.w, self.h, self.pix = g.width, g.height, img.data
        print("抓图 %dx%d %d bytes" % (self.w, self.h, len(self.pix)))
        self.pub.NewIcon()

    def click(self, btn):
        t = self.win.translate_coords(dpy.screen().root, self.w // 2, self.h // 2)
        x, y = t.x, t.y
        if x < 0 or y < 0:
            x, y = 100, 100
        xtest.fake_input(dpy, X.MotionNotify, x=x, y=y)
        xtest.fake_input(dpy, X.ButtonPress, btn)
        xtest.fake_input(dpy, X.ButtonRelease, btn)
        dpy.sync()


def main():
    scr = dpy.screen()
    root = scr.root

    atom = dpy.intern_atom("_NET_SYSTEM_TRAY_S" + str(scr.id))
    tray = root.create_window(0, 0, 1, 1, 0, scr.root_depth, X.InputOutput, X.CopyFromParent)
    tray.set_selection_owner(atom, X.CurrentTime)
    dpy.sync()
    if dpy.get_selection_owner(atom) != tray:
        print("托盘被占了")
        return 1

    mgr = event.ClientMessage(
        window=root,
        client_type=dpy.intern_atom("MANAGER"),
        data=(32, [X.CurrentTime, atom, tray.id, 0, 0]),
    )
    root.send_event(mgr, event_mask=X.StructureNotifyMask)
    dpy.flush()

    tray.change_attributes(event_mask=X.SubstructureNotifyMask)
    root.change_attributes(event_mask=X.SubstructureNotifyMask)

    op = dpy.intern_atom("_NET_SYSTEM_TRAY_OPCODE")
    dmg_base = dpy.query_extension("DAMAGE").first_event

    print("托盘代理启动")

    while True:
        ev = dpy.next_event()
        if ev.type == X.ClientMessage and ev.client_type == op:
            if ev.data[1] == 0:
                wid = ev.data[2]
                print("新图标:", wid)
                proxies.append(Proxy(wid, len(proxies)))
        elif ev.type == dmg_base + 0:
            for p in proxies:
                if p.wid == ev.window.id:
                    p.grab()
                    break


if __name__ == "__main__":
    sys.exit(main())