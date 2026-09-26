// Android Chrome cannot use `new Notification()`; it needs a service worker to show one.
self.addEventListener("notificationclick", (e) => { e.notification.close(); });
