// Right-click menu: "Download with AnyVideo" on pages, links and videos.
if (typeof importScripts === "function") importScripts("common.js"); // Chrome service worker

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "anyvideo",
    title: "Download with AnyVideo",
    contexts: ["page", "link", "video"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const target = info.linkUrl || info.pageUrl || tab?.url;
  if (!isWebPage(target)) return;
  const server = await getServer();
  chrome.tabs.create({ url: appUrl(server, target) });
});
