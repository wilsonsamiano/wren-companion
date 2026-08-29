import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

function isWren(win) {
    if (!win)
        return false;
    const wm = (win.get_wm_class() || '').toLowerCase();
    const gtk = (win.get_gtk_application_id?.() || '').toLowerCase();
    const title = win.get_title?.() || '';
    return wm.includes('wren') || gtk.includes('wren') || title === 'Wren';
}

function pin(win) {
    if (!isWren(win))
        return;
    try {
        win.make_above();
    } catch (_e) {}
    try {
        win.stick();
    } catch (_e) {}
    try {
        if (win.unminimize)
            win.unminimize();
    } catch (_e) {}
}

export default class WrenTop extends Extension {
    enable() {
        this._created = global.display.connect('window-created', (_d, win) => {
            pin(win);
            if (win.connect) {
                win.connect('shown', () => pin(win));
                win.connect('unmanaged', () => {});
            }
        });
        this._restacked = global.display.connect('restacked', () => {
            for (const actor of global.get_window_actors())
                pin(actor.meta_window);
        });
        for (const actor of global.get_window_actors())
            pin(actor.meta_window);
    }

    disable() {
        if (this._created)
            global.display.disconnect(this._created);
        if (this._restacked)
            global.display.disconnect(this._restacked);
        this._created = 0;
        this._restacked = 0;
    }
}
