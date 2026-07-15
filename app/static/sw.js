/* QuickLunch Service Worker — Web Push */
'use strict';

self.addEventListener('push', function (e) {
    var d = {};
    try { d = e.data.json(); } catch (_) {}
    e.waitUntil(
        self.registration.showNotification(d.title || 'QuickLunch', {
            body:    d.body || '',
            data:    { url: d.url || '/' },
            vibrate: [200, 100, 200]
        })
    );
});

self.addEventListener('notificationclick', function (e) {
    e.notification.close();
    var url = (e.notification.data && e.notification.data.url) || '/';
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (cs) {
            for (var i = 0; i < cs.length; i++) {
                if ('focus' in cs[i]) { cs[i].focus(); return; }
            }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});
