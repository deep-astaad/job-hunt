import { defineManifest } from "@crxjs/vite-plugin";
import pkg from "../package.json";

export default defineManifest({
  manifest_version: 3,
  name: "AppFill — Job Application Autofiller",
  version: pkg.version,
  description: pkg.description,
  // Work on any platform; documented privacy tradeoff. The content script also
  // runs in all frames so embedded ATS iframes (Workday/Greenhouse) are covered.
  host_permissions: ["<all_urls>"],
  permissions: [
    "storage",
    "scripting",
    "activeTab",
    "unlimitedStorage",
    "tabs",
    "contextMenus",
  ],
  commands: {
    "fill-form": {
      suggested_key: { default: "Ctrl+Shift+L", mac: "Command+Shift+L" },
      description: "AppFill: fill the current form",
    },
  },
  background: {
    service_worker: "src/background/service-worker.ts",
    type: "module",
  },
  content_scripts: [
    {
      matches: ["<all_urls>"],
      js: ["src/content/index.ts"],
      run_at: "document_idle",
      all_frames: true,
    },
    {
      // BYO-LLM handoff: only the chat providers' own pages.
      matches: [
        "https://claude.ai/*",
        "https://chatgpt.com/*",
        "https://chat.openai.com/*",
        "https://gemini.google.com/*",
        "https://www.kimi.com/*",
        "https://kimi.com/*",
        "https://kimi.moonshot.cn/*",
      ],
      js: ["src/content/webchat.ts"],
      run_at: "document_idle",
    },
  ],
  action: {
    default_popup: "src/popup/index.html",
    default_title: "AppFill",
  },
  options_page: "src/options/index.html",
  icons: {
    "16": "icons/icon-16.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png",
  },
  web_accessible_resources: [
    {
      resources: ["icons/*"],
      matches: ["<all_urls>"],
    },
  ],
});
