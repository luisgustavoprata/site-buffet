/* Recebe as notificações do site, mesmo com a página fechada, e mostra na barra do sistema. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Brunoise Gastronomia";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: "/static/icone-192.png",
    badge: "/static/selo-96.png",
    tag: data.tag || "brunoise",
    lang: "pt-BR",
    data: { url: data.url || "/" },
  }));
});

// Tocar na notificação abre o site na página certa (ou traz para frente a aba já aberta).
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const tabs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const tab = tabs.find((t) => new URL(t.url).origin === self.location.origin);
    if (tab) {
      await tab.focus();
      if ("navigate" in tab) {
        try {
          await tab.navigate(url);
        } catch {
          /* aba não controlada: fica na página atual */
        }
      }
      return;
    }
    await self.clients.openWindow(url);
  })());
});
