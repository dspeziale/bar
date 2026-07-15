/* QuickLunch Service Worker — Web Push */
'use strict';

self.addEventListener('push', function (e) {
    var d = {};
    try { d = e.data.json(); } catch (_) {}
    e.waitUntil(
        self.registration.showNotification(d.title || 'QuickLunch', {
            body:              d.body || '',
            data:              { url: d.url || '/' },
            vibrate:           [300, 100, 300, 100, 300],
            requireInteraction: true,
            tag:               'quicklunch-order'
        })
    );
});

self.addEventListener('notificationclick', function (e) {
    e.notification.close();
    var targetUrl = (e.notification.data && e.notification.data.url) || '/';

    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (cs) {
            /* Cerca una finestra già aperta sul sito e naviga alla URL giusta */
            for (var i = 0; i < cs.length; i++) {
                var c = cs[i];
                if ('focus' in c) {
                    return c.focus().then(function (fc) {
                        if ('navigate' in fc) return fc.navigate(targetUrl);
                    });
                }
            }
            /* Nessuna finestra aperta — ne apre una nuova */
            if (clients.openWindow) return clients.openWindow(targetUrl);
        })
    );
});
