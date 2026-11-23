// Shared by the popup and the background script.
const DEFAULT_SERVER = "http://127.0.0.1:8765";

async function getServer() {
  const { server } = await chrome.storage.sync.get({ server: DEFAULT_SERVER });
  return server.replace(/\/+$/, "");
}

function appUrl(server, pageUrl, auto) {
  const q = new URLSearchParams({ url: pageUrl });
  if (auto) q.set("auto", auto);
  return `${server}/?${q}`;
}

function isWebPage(url) {
  return /^https?:\/\//i.test(url || "");
}
