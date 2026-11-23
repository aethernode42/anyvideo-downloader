const $ = (s) => document.querySelector(s);
let tabUrl = "";

async function checkServer(server) {
  try {
    const r = await fetch(`${server}/healthz`, { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

async function open(auto) {
  const server = await getServer();
  await chrome.tabs.create({ url: appUrl(server, tabUrl, auto) });
  window.close();
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  tabUrl = tab?.url || "";
  const server = await getServer();
  $("#server").value = server;

  const usable = isWebPage(tabUrl);
  $("#page").textContent = usable ? tabUrl : "Open a page with a video, then click this button.";
  for (const id of ["#best", "#mp3", "#choose"]) $(id).disabled = !usable;

  const local = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(server);
  const has = local || (await chrome.permissions.contains({ origins: [`${new URL(server).origin}/*`] }));
  const up = has && (await checkServer(server));
  if (up) {
    $("#status").innerHTML = '<b class="ok">●</b> AnyVideo is ready';
  } else if (local) {
    $("#status").innerHTML = '<b class="warn">●</b> AnyVideo isn\'t running on this computer';
    $("#help").hidden = false;
  } else {
    $("#status").textContent = `Using ${server}`;
  }
}

$("#best").onclick = () => open("best");
$("#mp3").onclick = () => open("mp3");
$("#choose").onclick = () => open("");

$("#save").onclick = async () => {
  let value = $("#server").value.trim() || DEFAULT_SERVER;
  try {
    const u = new URL(value);
    if (!/^https?:$/.test(u.protocol)) throw new Error();
    value = u.origin;
  } catch {
    $("#status").textContent = "That address isn't valid.";
    return;
  }
  const local = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/i.test(value);
  if (!local) {
    // Asked only for the server the user typed, and only when they save it.
    const ok = await chrome.permissions.request({ origins: [`${value}/*`] });
    if (!ok) {
      $("#status").textContent = "Permission was not granted, so the address wasn't saved.";
      return;
    }
  }
  await chrome.storage.sync.set({ server: value });
  $("#status").textContent = "Saved.";
  init();
};

init();
